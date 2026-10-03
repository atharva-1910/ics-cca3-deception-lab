"""JSONL interaction logger (HANDOVER §10.6, §11.2).

One record per request. The record is sufficient to replay a session
(acceptance test §10.6), so it captures request, response source, latency and a
response hash plus whether a planted fact was hit.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path


class JsonlLogger:
    def __init__(self, path: os.PathLike | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._fh = self.path.open("a", encoding="utf-8")

    def log(self, *, run_id, session_id, src, dst, host_type, gen_type,
            protocol, request, response, response_source, latency_ms,
            planted_hit=False):
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.", time.gmtime())
                  + f"{int(time.time()*1000) % 1000:03d}Z",
            "run_id": run_id,
            "session_id": session_id,
            "src": src,
            "dst": dst,
            "host_type": host_type,
            "gen_type": gen_type,
            "protocol": protocol,
            "request": request,
            "response_source": response_source,
            "latency_ms": latency_ms,
            "response_sha1": hashlib.sha1(response.encode("utf-8", "replace")).hexdigest()[:8],
            "planted_hit": planted_hit,
        }
        line = json.dumps(rec)
        with self._lock:
            self._fh.write(line + "\n")
            self._fh.flush()
        return rec

    def close(self):
        self._fh.close()
