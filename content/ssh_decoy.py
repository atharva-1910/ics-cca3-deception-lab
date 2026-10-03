"""LLM/SSH decoy listener (HANDOVER §10.4, §7.2).

A thin asyncssh server that holds NO state: it authenticates against the engine
(which checks the consistency store) and forwards every command to the engine's
POST /respond, returning whatever the engine answers (store handler or LLM).
One of these runs per decoy container with a static lab IP, so nmap sees
separate hosts.

Env:
    DECOY_IP    this decoy's lab IP (the 'host' key sent to the engine)
    ENGINE_URL  http://orchestrator:9000
    SSH_PORT    default 22
"""
from __future__ import annotations

import asyncio
import os
import uuid

import asyncssh
import httpx

DECOY_IP = os.environ.get("DECOY_IP", "10.66.0.21")
ENGINE_URL = os.environ.get("ENGINE_URL", "http://orchestrator:9000")
SSH_PORT = int(os.environ.get("SSH_PORT", "22"))
BANNER = os.environ.get("SSH_BANNER", "SSH-2.0-OpenSSH_8.9p1 Ubuntu-3ubuntu0.4")


async def _respond(host_user: str, session_id: str, command: str) -> str:
    async with httpx.AsyncClient(timeout=70) as c:
        r = await c.post(f"{ENGINE_URL}/respond", json={
            "host": DECOY_IP, "protocol": "ssh", "session_id": session_id,
            "request": command, "user": host_user, "src": "10.66.0.100"})
        r.raise_for_status()
        return r.json().get("response", "")


class _Server(asyncssh.SSHServer):
    def connection_made(self, conn):
        self._conn = conn

    def begin_auth(self, username):
        return True  # force password auth

    def password_auth_supported(self):
        return True

    def validate_password(self, username, password):
        try:
            r = httpx.post(f"{ENGINE_URL}/auth", timeout=10, json={
                "host": DECOY_IP, "user": username, "password": password})
            return bool(r.json().get("ok", False))
        except Exception:
            return False


async def _handle(process: asyncssh.SSHServerProcess):
    user = process.get_extra_info("username")
    session_id = "ssh-" + uuid.uuid4().hex[:8]
    command = process.command
    if command:  # non-interactive: ssh user@host "cmd"
        out = await _respond(user, session_id, command)
        process.stdout.write(out + ("\n" if not out.endswith("\n") else ""))
        process.exit(0)
        return
    # interactive shell
    process.stdout.write(f"Welcome to {DECOY_IP}\n")
    async for line in process.stdin:
        line = line.rstrip("\n")
        if line.strip() in ("exit", "logout"):
            break
        if not line.strip():
            process.stdout.write("$ ")
            continue
        out = await _respond(user, session_id, line)
        process.stdout.write(out + "\n$ ")
    process.exit(0)


async def main():
    host_key = asyncssh.generate_private_key("ssh-rsa")
    await asyncssh.create_server(
        _Server, "", SSH_PORT, server_host_keys=[host_key],
        server_version=BANNER, process_factory=_handle)
    print(f"ssh decoy {DECOY_IP} listening on :{SSH_PORT} -> {ENGINE_URL}")
    await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (OSError, asyncssh.Error) as exc:
        raise SystemExit(f"ssh decoy failed: {exc}")
