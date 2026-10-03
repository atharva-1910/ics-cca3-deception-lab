"""Agent tools and the hard target allow-list (HANDOVER §10.7, §17; CLAUDE.md §2).

THE RULE: every tool and any helper that takes a target MUST reject any target
that does not resolve into 10.66.0.0/24, checked before the call executes. This
is a hard-coded allow-list, not a config value and not overridable by a flag,
env var, or argument. A rejected target raises TargetRejected (logged, never a
silent pass and never clamped/rewritten to something in range).

The validator resolves hostnames first, then checks the resolved IP, so a
planted decoy hostname is allowed only when the lab resolver maps it to a
10.66.0.x address. Loopback, link-local, the cloud metadata IP, and the Docker
host are all out of range and rejected.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Callable
from urllib.parse import urlparse

LAB_SUBNET = ipaddress.ip_network("10.66.0.0/24")

# Never reachable through these tools regardless of resolution outcome.
_ALWAYS_DENY_NAMES = {
    "host.docker.internal", "gateway.docker.internal",
    "localhost", "localhost.localdomain",
}


class TargetRejected(Exception):
    """Raised when a target is not inside the lab subnet."""


def _extract_host(target: str) -> str:
    """Pull the host part out of an IP, host:port, or URL."""
    t = target.strip()
    if "://" in t:
        return urlparse(t).hostname or ""
    # bare host or host:port (but not an IPv6 literal, which we don't use here)
    if t.count(":") == 1:
        t = t.split(":", 1)[0]
    return t


def assert_in_scope(target: str,
                    resolver: Callable[[str], str] = socket.gethostbyname) -> str:
    """Return the canonical in-scope IP for ``target`` or raise TargetRejected."""
    host = _extract_host(target)
    if not host:
        raise TargetRejected(f"empty/unparseable target: {target!r}")
    if host.lower() in _ALWAYS_DENY_NAMES:
        raise TargetRejected(f"denied host name: {host!r}")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # It's a name: resolve through the (lab) resolver, then re-check.
        try:
            resolved = resolver(host)
        except Exception as exc:  # noqa: BLE001 - resolution failure => reject
            raise TargetRejected(f"cannot resolve {host!r}: {exc}") from exc
        try:
            ip = ipaddress.ip_address(resolved)
        except ValueError as exc:
            raise TargetRejected(f"{host!r} resolved to non-IP {resolved!r}") from exc

    if ip not in LAB_SUBNET:
        raise TargetRejected(f"{target!r} -> {ip} is outside {LAB_SUBNET}")
    return str(ip)


def assert_network_in_scope(target: str) -> str:
    """Validate an nmap target that may be a CIDR range or a single host."""
    t = target.strip()
    if "/" in t:
        net = ipaddress.ip_network(t, strict=False)
        if not net.subnet_of(LAB_SUBNET):
            raise TargetRejected(f"{target!r} is not within {LAB_SUBNET}")
        return str(net)
    return assert_in_scope(t)


# --------------------------------------------------------------------- tools
# Heavy third-party deps are imported lazily so this module (and the allow-list
# tests) load with only the standard library.

def nmap_scan(target: str, flags: str = "-sV") -> dict:
    """T1595/T1046. Scan a single lab host or an in-lab CIDR."""
    scope = assert_network_in_scope(target)
    import nmap  # python-nmap
    nm = nmap.PortScanner()
    nm.scan(hosts=scope, arguments=flags)
    out = {}
    for host in nm.all_hosts():
        out[host] = {
            "state": nm[host].state(),
            "tcp": {p: nm[host]["tcp"][p] for p in nm[host].all_tcp()}
            if "tcp" in nm[host] else {},
        }
    return out


def ssh_exec(host: str, user: str, command: str,
             password: str | None = None, key: str | None = None,
             timeout: int = 15) -> str:
    """T1021.004/T1078. Run one command over SSH on a lab host."""
    ip = assert_in_scope(host)
    import paramiko
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    pkey = paramiko.RSAKey.from_private_key(_StringIO(key)) if key else None
    client.connect(ip, username=user, password=password, pkey=pkey,
                   timeout=timeout, allow_agent=False, look_for_keys=False)
    try:
        _in, out, err = client.exec_command(command, timeout=timeout)
        return out.read().decode(errors="replace") + err.read().decode(errors="replace")
    finally:
        client.close()


def http_get(url: str, headers: dict | None = None, timeout: int = 15) -> dict:
    """HTTP discovery against a lab API decoy."""
    assert_in_scope(url)  # validates the resolved host of the URL
    import requests
    r = requests.get(url, headers=headers or {}, timeout=timeout)
    return {"status": r.status_code, "headers": dict(r.headers), "body": r.text}


class _StringIO:
    """Tiny helper so a key string can be fed to paramiko without importing io at top."""
    def __new__(cls, s):
        import io
        return io.StringIO(s)


# Tool registry handed to the ReAct agent.
TOOLS = {
    "nmap_scan": nmap_scan,
    "ssh_exec": ssh_exec,
    "http_get": http_get,
}
