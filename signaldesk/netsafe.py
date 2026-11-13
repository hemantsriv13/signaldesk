"""Outbound HTTP with guard rails.

* Only http(s) on ports 80/443, and only to hosts that resolve to public addresses: loopback,
  private, link-local, multicast and reserved ranges are refused (so a pasted URL cannot reach
  Colibri, the router or anything else on this machine or network). Redirects are followed by
  hand and every hop is checked again.
* Bounded concurrency, a minimum interval per host, timeouts, a size cap, and bounded retries
  with backoff on 429/5xx (Retry-After is respected up to a limit).
* Pages fetched on request (manual URLs) also honour robots.txt.

The connection itself goes to the address that passed the check: the transport resolves the host
once, refuses the request if any answer is non-public, and connects to that validated address
(TLS still verifies the certificate against the host name). A DNS answer that changes between the
check and the connection therefore cannot redirect the request to a local or private machine.
Proxy settings from the environment are ignored for the same reason.
"""
from __future__ import annotations

import ipaddress
import socket
import threading
import time
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

from .config import FetchConfig


class FetchError(Exception):
    pass


class BlockedURL(FetchError):
    pass


def _embedded_v4(ip: ipaddress._BaseAddress) -> ipaddress._BaseAddress:
    """The IPv4 address hidden in IPv4-mapped, 6to4, Teredo or NAT64 forms, if any."""
    if ip.version == 6:
        if ip.ipv4_mapped:
            return ip.ipv4_mapped
        if ip.sixtofour:
            return ip.sixtofour
        if ip.teredo:
            return ip.teredo[1]
        if ip in ipaddress.ip_network("64:ff9b::/96"):
            return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return ip


def public_ip(ip: ipaddress._BaseAddress) -> bool:
    """Only globally routable unicast addresses. Loopback, private, link-local, CGNAT, multicast,
    reserved, unspecified and documentation ranges are refused, in IPv4 and IPv6."""
    for a in {ip, _embedded_v4(ip)}:
        if not a.is_global or a.is_multicast or a.is_reserved or a.is_loopback or a.is_link_local or a.is_private or a.is_unspecified:
            return False
    return True


def resolve_public(host: str, port: int, resolve=socket.getaddrinfo) -> list[str]:
    """Every address the host resolves to, if all of them are public. Raises otherwise."""
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal is not None:
        if not public_ip(literal):
            raise BlockedURL("Private and local network addresses are refused.")
        return [str(literal)]
    try:
        infos = resolve(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise FetchError(f"Could not resolve {host}.") from e
    addrs = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not public_ip(ip):
            raise BlockedURL("This host points to a private or local network address; it is refused.")
        addrs.append(str(ip))
    if not addrs:
        raise FetchError(f"Could not resolve {host}.")
    return addrs


class PinnedBackend:
    """httpcore network backend that connects only to addresses validated by resolve_public."""

    def __init__(self, resolve=socket.getaddrinfo):
        import httpcore
        self._inner = httpcore.SyncBackend()
        self._resolve = resolve

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        last = None
        for ip in resolve_public(host, port, self._resolve):
            try:
                return self._inner.connect_tcp(ip, port, timeout=timeout, local_address=local_address, socket_options=socket_options)
            except Exception as e:  # noqa: BLE001 - try the next validated address
                last = e
        raise last

    def connect_unix_socket(self, *a, **kw):
        raise BlockedURL("Unix sockets are not allowed.")

    def sleep(self, seconds):
        self._inner.sleep(seconds)


def pinned_transport(resolve=socket.getaddrinfo) -> httpx.HTTPTransport:
    import httpcore
    t = httpx.HTTPTransport(trust_env=False)
    t._pool = httpcore.ConnectionPool(ssl_context=httpx.create_ssl_context(trust_env=False), max_connections=20,
                                      max_keepalive_connections=10, keepalive_expiry=5.0, network_backend=PinnedBackend(resolve))
    return t


def check_url(url: str, resolve=socket.getaddrinfo) -> str:
    """Return the URL if it is safe to fetch, else raise BlockedURL. Runs before any request."""
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise BlockedURL(f"Only http and https links can be fetched (got {p.scheme or 'none'}).")
    if not p.hostname:
        raise BlockedURL("The link has no host name.")
    if p.username or p.password:
        raise BlockedURL("Links with embedded credentials are refused.")
    port = p.port or (443 if p.scheme == "https" else 80)
    if port not in (80, 443):
        raise BlockedURL("Only the standard web ports (80 and 443) are allowed.")
    host = p.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan", ".home.arpa", ".test", ".intranet", ".corp")) or "." not in host.strip("[]:") and ":" not in host:
        raise BlockedURL("Local and private network hosts are refused.")
    resolve_public(host, port, resolve)
    return url


@dataclass
class Response:
    url: str
    status: int
    headers: dict
    content: bytes

    @property
    def text(self) -> str:
        for enc in (self._charset(), "utf-8", "latin-1"):
            if not enc:
                continue
            try:
                return self.content.decode(enc)
            except (LookupError, UnicodeDecodeError):
                continue
        return self.content.decode("utf-8", "replace")

    def _charset(self) -> str | None:
        ct = self.headers.get("content-type", "")
        if "charset=" in ct:
            return ct.split("charset=")[-1].split(";")[0].strip()
        return None

    def json(self):
        import json
        return json.loads(self.content)


class Fetcher:
    def __init__(self, cfg: FetchConfig, transport: httpx.BaseTransport | None = None, resolve=socket.getaddrinfo, sleep=time.sleep):
        self.cfg = cfg
        self.sem = threading.Semaphore(cfg.concurrency)
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._host_sems: dict[str, threading.Semaphore] = {}
        self.resolve = resolve
        self.sleep = sleep
        # Real network access always goes through the pinned transport; tests pass a mock transport.
        self.client = httpx.Client(timeout=cfg.timeout_seconds, follow_redirects=False, trust_env=False,
                                   transport=transport or pinned_transport(resolve),
                                   headers={"User-Agent": cfg.user_agent, "Accept-Encoding": "gzip, deflate"})

    def _pace(self, host: str) -> None:
        with self._lock:
            wait = self._last.get(host, 0) + self.cfg.per_host_interval_seconds - time.monotonic()
            self._last[host] = max(time.monotonic(), self._last.get(host, 0) + self.cfg.per_host_interval_seconds)
        if wait > 0:
            self.sleep(wait)

    def allowed_by_robots(self, url: str) -> bool:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.get(base + "/robots.txt", retries=0, check_robots=False)
                rp.parse(r.text.splitlines() if r.status == 200 else [])
            except FetchError:
                rp.parse([])
            self._robots[base] = rp
        rp = self._robots[base]
        return rp.can_fetch(self.cfg.user_agent, url) if rp else True

    def get(self, url: str, *, retries: int = 2, check_robots: bool = False, accept: str | None = None) -> Response:
        if check_robots and not self.allowed_by_robots(url):
            raise BlockedURL("The site's robots.txt asks automated tools not to fetch this page.")
        headers = {"Accept": accept} if accept else {}
        attempt = 0
        while True:
            try:
                return self._get_once(url, headers)
            except _Retryable as e:
                attempt += 1
                if attempt > retries:
                    raise FetchError(str(e)) from None
                self.sleep(min(e.retry_after or 2 ** attempt, 30))

    def _get_once(self, url: str, headers: dict) -> Response:
        current = url
        for _ in range(6):
            check_url(current, self.resolve)
            host = urlparse(current).hostname or ""
            self._pace(host)
            with self._lock:
                host_sem = self._host_sems.setdefault(host, threading.Semaphore(max(1, getattr(self.cfg, "per_host_concurrency", 2))))
            with self.sem, host_sem:
                try:
                    with self.client.stream("GET", current, headers=headers) as r:
                        if r.status_code in (301, 302, 303, 307, 308) and "location" in r.headers:
                            current = urljoin(current, r.headers["location"])
                            continue
                        if r.status_code == 429 or r.status_code >= 500:
                            ra = r.headers.get("retry-after", "")
                            raise _Retryable(f"HTTP {r.status_code} from {urlparse(current).hostname}",
                                             float(ra) if ra.isdigit() else None)
                        body = bytearray()
                        for chunk in r.iter_bytes():
                            body.extend(chunk)
                            if len(body) > self.cfg.max_bytes:
                                raise FetchError(f"Response larger than {self.cfg.max_bytes:,} bytes; not read.")
                        return Response(str(r.url), r.status_code, {k.lower(): v for k, v in r.headers.items()}, bytes(body))
                except (httpx.TimeoutException, httpx.TransportError) as e:
                    raise _Retryable(f"{type(e).__name__} contacting {urlparse(current).hostname}") from None
        raise FetchError("Too many redirects.")

    def close(self) -> None:
        self.client.close()


class _Retryable(Exception):
    def __init__(self, msg: str, retry_after: float | None = None):
        super().__init__(msg)
        self.retry_after = retry_after
