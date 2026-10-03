"""LLM/HTTP API decoy (HANDOVER §10.4).

FastAPI catch-all that forwards every request to the engine. RAG over
content/examples/ gives the LLM a nearby example to ground single-response
realism (after [15] DecoyPot); grounding for *session* consistency is the
store's job, done in the engine.

Env:
    DECOY_IP, ENGINE_URL, API_PORT (default 80)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

DECOY_IP = os.environ.get("DECOY_IP", "10.66.0.25")
ENGINE_URL = os.environ.get("ENGINE_URL", "http://orchestrator:9000")
API_PORT = int(os.environ.get("API_PORT", "80"))
EXAMPLES = Path(__file__).with_name("examples") / "api_examples.json"

app = FastAPI(title=f"api-decoy-{DECOY_IP}")
_examples = json.loads(EXAMPLES.read_text()) if EXAMPLES.exists() else []


def _retrieve(path: str) -> dict | None:
    """Trivial cosine-free retrieval: exact path, else longest shared prefix."""
    best, score = None, 0
    for ex in _examples:
        p = ex["path"]
        if p == path:
            return ex["response"]
        shared = len(os.path.commonprefix([p, path]))
        if shared > score:
            best, score = ex["response"], shared
    return best


@app.api_route("/{full_path:path}",
               methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def catch_all(full_path: str, request: Request):
    path = "/" + full_path
    hint = _retrieve(path)
    req_desc = f"{request.method} {path}"
    if hint is not None:
        req_desc += f"  (example of a similar endpoint: {json.dumps(hint)})"
    async with httpx.AsyncClient(timeout=70) as c:
        r = await c.post(f"{ENGINE_URL}/respond", json={
            "host": DECOY_IP, "protocol": "http",
            "session_id": "http-" + (request.client.host if request.client else "x"),
            "request": req_desc, "src": "10.66.0.100"})
        body = r.json().get("response", "{}")
    try:
        return JSONResponse(json.loads(body))
    except (json.JSONDecodeError, TypeError):
        return JSONResponse({"raw": body})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=API_PORT)
