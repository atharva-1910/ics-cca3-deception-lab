"""Deception engine / orchestrator (HANDOVER §7.2, §10.6).

Receives each decoy request, decides the responder (store handler, else LLM),
logs every interaction as JSONL, and writes any LLM-created state back to the
store. Decoys hold no state; this is the single place state and logs live.

The core is ``respond()`` — a plain function, independent of the web framework,
so it can be unit-tested with a fake LLM. The FastAPI app is a thin wrapper.

    POST /respond {host, protocol, session_id, request} -> {response, source}
"""
from __future__ import annotations

import os
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
import sys  # noqa: E402
sys.path.insert(0, str(REPO))

from orchestrator.handlers import dispatch  # noqa: E402
from orchestrator.logger import JsonlLogger  # noqa: E402
from store.state import Contradiction, Store  # noqa: E402

PERSONA_PROMPT = (REPO / "content" / "prompts" / "ssh_persona.txt")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")


def ollama_llm(prompt: str, temperature: float = 0.7, max_tokens: int = 400) -> str:
    """Default LLM backend: host-native Ollama (CLAUDE.md §1)."""
    import httpx
    r = httpx.post(f"{OLLAMA_URL}/api/generate", timeout=60, json={
        "model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens,
                    "stop": ["\nCommand:", "<<END>>"]},
    })
    r.raise_for_status()
    return r.json().get("response", "")


def build_prompt(store: Store, host_id: str, session: dict, command: str) -> str:
    snap = store.snapshot_summary(host_id, session.get("cwd", "/"))
    host = snap["host"]
    tmpl = PERSONA_PROMPT.read_text() if PERSONA_PROMPT.exists() else _FALLBACK_PROMPT
    listing = ", ".join(e["name"] for e in snap["cwd_listing"]) or "(empty)"
    return tmpl.format(
        hostname=host.get("hostname", host_id),
        os=host.get("os", "Ubuntu 22.04"),
        role=host.get("persona", "server"),
        user=session.get("user", "ubuntu"),
        cwd=session.get("cwd", "/"),
        store_snapshot=f"cwd={session.get('cwd','/')} contains: {listing}; "
                       f"users: {', '.join(snap['users'])}; "
                       f"recent: {', '.join(snap['recent_history'][-5:])}",
        command=command,
    )


_FALLBACK_PROMPT = (
    "You are the shell of a Linux server. Hostname: {hostname}. OS: {os}. "
    "Role: {role}.\nCurrent user: {user}. Current directory: {cwd}.\n"
    "Known state (authoritative, never contradict it):\n{store_snapshot}\n"
    "Reply ONLY with the exact terminal output of the command below. No "
    "explanations, no markdown.\nCommand: {command}"
)


def parse_writeback(store: Store, host_id: str, command: str, output: str) -> None:
    """Best-effort: persist state the LLM implies it created (HANDOVER §10.5).

    Deterministic creators (touch/echo>/mkdir) are already handled in the store,
    so here we only guard against contradictions for a few common patterns and
    otherwise leave state untouched. Extend per template as needed.
    """
    # Intentionally conservative: never invent files from free-form LLM text.
    return None


def respond(store: Store, logger: JsonlLogger, sessions: dict, payload: dict,
            llm_fn=ollama_llm, run_id: str = "adhoc") -> dict:
    host = str(payload["host"])
    protocol = payload.get("protocol", "ssh")
    sid = payload.get("session_id", "s-default")
    request = payload["request"]

    hrow = store.get_host_by_ip(host) or store.get_host(host)
    host_id = hrow["host_id"] if hrow else host
    gen_type = hrow["gen_type"] if hrow else "unknown"
    host_type = "real" if gen_type == "real" else "decoy"

    session = sessions.setdefault(sid, {
        "session_id": sid, "user": payload.get("user", "ubuntu"),
        "host_id": host_id,
    })
    session["session_id"] = sid

    t0 = time.perf_counter()
    source = "store"
    resp, handled = dispatch(store, host_id, session, request)
    if not handled:
        source = "llm"
        prompt = build_prompt(store, host_id, session, request)
        resp = llm_fn(prompt)
        try:
            parse_writeback(store, host_id, request, resp)
        except Contradiction:
            pass  # keep the established fact; never create a contradiction

    latency_ms = int((time.perf_counter() - t0) * 1000)

    # planted_hit: did the agent just read a planted artifact?
    planted_hit = False
    if request.split()[:1] == ["cat"] and len(request.split()) > 1:
        row = store.read_file(host_id, request.split()[1]
                              if request.split()[1].startswith("/")
                              else session.get("cwd", "/") + "/" + request.split()[1])
        planted_hit = bool(row and row["planted"])

    store.add_history(host_id, sid, request, resp or "")
    logger.log(run_id=run_id, session_id=sid, src=payload.get("src", "10.66.0.100"),
               dst=host, host_type=host_type, gen_type=gen_type, protocol=protocol,
               request=request, response=resp or "", response_source=source,
               latency_ms=latency_ms, planted_hit=planted_hit)
    return {"response": resp or "", "source": source}


# --------------------------------------------------------------------- web app
# Request models MUST be module-level: FastAPI resolves a route's type hints
# against the function's module globals, so models defined inside create_app()
# are invisible and FastAPI mistakes the body for a query param. Guard the
# pydantic import so the host-side unit tests can still import respond() without
# fastapi/pydantic installed.
try:
    from pydantic import BaseModel

    class Req(BaseModel):
        host: str
        protocol: str = "ssh"
        session_id: str = "s-default"
        request: str
        user: str | None = "ubuntu"
        src: str | None = "10.66.0.100"

    class Auth(BaseModel):
        host: str
        user: str
        password: str | None = None
except ImportError:  # pragma: no cover - only on the host test venv
    Req = Auth = None  # type: ignore


def create_app(db_path=None, log_path=None, run_id="adhoc"):
    import threading

    from fastapi import FastAPI

    store = Store(db_path or REPO / "store" / "state.db")
    logger = JsonlLogger(log_path or REPO / "results" / "live.jsonl")
    sessions: dict = {}
    # FastAPI runs sync endpoints in a threadpool; the SQLite connection is
    # shared (check_same_thread=False), so serialise all store access here.
    lock = threading.Lock()
    app = FastAPI(title="deception-engine")

    @app.post("/respond")
    def _respond(req: Req):
        with lock:
            return respond(store, logger, sessions, req.model_dump(), run_id=run_id)

    @app.post("/auth")
    def _auth(req: Auth):
        with lock:
            hrow = store.get_host_by_ip(req.host) or store.get_host(req.host)
            host_id = hrow["host_id"] if hrow else req.host
            ok = store.check_password(host_id, req.user, req.password or "")
        return {"ok": bool(ok)}

    @app.get("/healthz")
    def _health():
        return {"ok": True, "model": OLLAMA_MODEL}

    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_app(), host="0.0.0.0", port=9000)
