"""LAN mode checks. SignalDesk refuses to open the LAN entry point unless every check passes, and
there is no plaintext LAN listener at all: the only non-loopback socket is HTTPS with sign-in.

Checks: a private (not loopback, link-local or wildcard) address to bind; a port distinct from the
loopback app and Colibri; a certificate and key that load together, are in date, live outside the
repository, and whose subjectAltName covers every hostname devices will type; a password set.
"""
from __future__ import annotations

import ipaddress
import ssl
from datetime import datetime, timezone
from pathlib import Path

from .config import Config

REPO = Path(__file__).resolve().parent.parent


def cert_names(cert_file: str) -> tuple[set[str], datetime | None]:
    """subjectAltName entries (DNS names lower-cased, IP addresses normalised) and expiry.
    Uses the standard library's certificate decoder; no extra package is needed."""
    info = ssl._ssl._test_decode_cert(cert_file)  # noqa: SLF001 - stdlib, stable for many releases
    names = set()
    for kind, value in info.get("subjectAltName", ()):
        if kind == "DNS":
            names.add(value.lower())
        elif kind == "IP Address":
            names.add(str(ipaddress.ip_address(value.strip())))
    expires = datetime.strptime(info["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc) if info.get("notAfter") else None
    return names, expires


def _covered(host: str, names: set[str]) -> bool:
    try:
        return str(ipaddress.ip_address(host)) in names
    except ValueError:
        h = host.lower()
        return h in names or any(n.startswith("*.") and h.endswith(n[1:]) and h.count(".") == n.count(".") for n in names)


def check(cfg: Config) -> tuple[list[str], list[str]]:
    """(errors, warnings). Any error means LAN mode must not start."""
    lan, errors, warnings = cfg.lan, [], []
    try:
        ip = ipaddress.ip_address(lan.bind)
        if ip.is_loopback or ip.is_unspecified or ip.is_link_local or not ip.is_private or ip.is_multicast:
            errors.append(f"[lan] bind = \"{lan.bind}\" is not a private home-network address. Use this PC's Wi-Fi address "
                          "(run: Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias Wi-Fi). 0.0.0.0 and public addresses are refused.")
    except ValueError:
        errors.append("[lan] bind is missing. Set it to this PC's Wi-Fi address, e.g. bind = \"192.168.1.10\".")
    if lan.port in (cfg.server.port, 8000) or not 1024 <= lan.port <= 65535:
        errors.append(f"[lan] port = {lan.port} clashes with the loopback app or Colibri; use 8443.")
    hosts = [str(h).strip() for h in lan.hostnames if str(h).strip()]
    if not hosts:
        errors.append("[lan] hostnames is empty. List exactly what your phone will type, e.g. hostnames = [\"192.168.1.10\"].")
    cert, key = Path(lan.cert_file or "_missing_"), Path(lan.key_file or "_missing_")
    for label, p in (("cert_file", cert), ("key_file", key)):
        if not p.is_file():
            errors.append(f"[lan] {label} not found: {p}. Create it with scripts\\lan-setup.ps1 (see docs\\LAN_AND_PANEL.md).")
        elif REPO in p.resolve().parents:
            errors.append(f"[lan] {label} is inside the code repository ({p}). Keep certificates and keys in the data directory.")
    if cert.is_file() and key.is_file():
        try:
            ssl.create_default_context(ssl.Purpose.CLIENT_AUTH).load_cert_chain(str(cert), str(key))
        except (ssl.SSLError, OSError) as e:
            errors.append(f"[lan] The certificate and key do not load together ({e}). Re-create them with scripts\\lan-setup.ps1.")
        try:
            names, expires = cert_names(str(cert))
            missing = [h for h in hosts if not _covered(h, names)]
            if missing:
                errors.append(f"[lan] The certificate does not cover {', '.join(missing)} (it covers {', '.join(sorted(names)) or 'nothing'}). "
                              "Re-create it for exactly the names in [lan] hostnames.")
            if expires and expires < datetime.now(timezone.utc):
                errors.append(f"[lan] The certificate expired on {expires:%Y-%m-%d}. Renew it with scripts\\lan-setup.ps1.")
            elif expires and (expires - datetime.now(timezone.utc)).days < 30:
                warnings.append(f"The LAN certificate expires on {expires:%Y-%m-%d}. Renew it soon with scripts\\lan-setup.ps1.")
        except (ssl.SSLError, OSError, ValueError, KeyError) as e:
            errors.append(f"[lan] Could not read the certificate ({e}).")
    if not cfg.auth_path.exists():
        errors.append("No sign-in password is set. Run:  .venv\\Scripts\\python -m signaldesk auth set-password")
    return errors, warnings


def allowed_hosts(cfg: Config) -> set[str]:
    return {h.lower() for h in cfg.lan.hostnames}


def allowed_origins(cfg: Config) -> set[str]:
    port = "" if cfg.lan.port == 443 else f":{cfg.lan.port}"
    return {f"https://{h if ':' not in h else '[' + h + ']'}{port}".lower() for h in cfg.lan.hostnames}
