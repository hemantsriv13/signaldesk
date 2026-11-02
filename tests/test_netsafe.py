import socket

import httpx
import pytest

from signaldesk.config import FetchConfig
from signaldesk.netsafe import BlockedURL, Fetcher, check_url


def resolver(ip):
    return lambda host, port, proto=0: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]


@pytest.mark.parametrize("url", [
    "file:///C:/Users/secret.txt", "ftp://example.com/x", "http://localhost:8000/v1/models", "http://127.0.0.1/", "http://example.com:8000/",
    "http://user:pw@example.com/", "http://printer.local/", "http://router.lan/",
])
def test_refuses_local_and_odd_urls(url):
    with pytest.raises(BlockedURL):
        check_url(url, resolver("93.184.216.34"))


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "172.16.0.1", "169.254.169.254", "0.0.0.0", "::1", "fd00::1", "100.64.0.1"])
def test_refuses_hosts_resolving_to_private_addresses(ip):
    with pytest.raises(BlockedURL):
        check_url("https://innocent-looking.example/", resolver(ip))


def test_allows_public():
    assert check_url("https://boards-api.greenhouse.io/v1/boards/x/jobs", resolver("104.18.1.1"))


def test_redirect_to_private_address_is_refused():
    def handler(req):
        if req.url.host == "public.example":
            return httpx.Response(302, headers={"location": "http://internal.example/admin"})
        return httpx.Response(200, text="secret")

    def resolve(host, port, proto=0):
        ip = "10.1.1.1" if host == "internal.example" else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    f = Fetcher(FetchConfig(per_host_interval_seconds=0), transport=httpx.MockTransport(handler), resolve=resolve, sleep=lambda s: None)
    with pytest.raises(BlockedURL):
        f.get("https://public.example/start")


def test_retries_are_bounded_and_respect_size_cap():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503)

    f = Fetcher(FetchConfig(per_host_interval_seconds=0), transport=httpx.MockTransport(handler), resolve=resolver("93.184.216.34"), sleep=lambda s: None)
    with pytest.raises(Exception):
        f.get("https://example.com/", retries=2)
    assert len(calls) == 3

    big = Fetcher(FetchConfig(per_host_interval_seconds=0, max_bytes=10), transport=httpx.MockTransport(lambda r: httpx.Response(200, text="x" * 100)),
                  resolve=resolver("93.184.216.34"), sleep=lambda s: None)
    with pytest.raises(Exception, match="larger"):
        big.get("https://example.com/")


def test_robots_txt_is_honoured_for_pages():
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private")
        return httpx.Response(200, text="<html></html>", headers={"content-type": "text/html"})

    f = Fetcher(FetchConfig(per_host_interval_seconds=0), transport=httpx.MockTransport(handler), resolve=resolver("93.184.216.34"), sleep=lambda s: None)
    with pytest.raises(BlockedURL, match="robots"):
        f.get("https://example.com/private/page", check_robots=True)
    assert f.get("https://example.com/public", check_robots=True).status == 200
