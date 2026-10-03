"""Engine core tests (HANDOVER §10.6): deterministic answers from the store,
LLM only as fallback, and one JSONL record per request."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from orchestrator.engine import respond  # noqa: E402
from orchestrator.logger import JsonlLogger  # noqa: E402
from store.state import fresh  # noqa: E402


@pytest.fixture
def ctx(tmp_path):
    store = fresh(tmp_path / "e.db")
    store.add_host("web-01", "10.66.0.21", "web-01", gen_type="llm_store")
    store.add_user("web-01", "ubuntu", password="pw", uid=1000)
    store.write_file("web-01", "/var/www/app/config.php",
                     "DB_HOST=db-internal-02\n", planted=1)
    logger = JsonlLogger(tmp_path / "log.jsonl")
    return store, logger, {}, tmp_path


def _llm_should_not_run(prompt):
    raise AssertionError("LLM called for a deterministic command")


def test_deterministic_from_store(ctx):
    store, logger, sessions, _ = ctx
    out = respond(store, logger, sessions,
                  {"host": "10.66.0.21", "session_id": "s1",
                   "request": "cat /var/www/app/config.php", "user": "ubuntu"},
                  llm_fn=_llm_should_not_run)
    assert "db-internal-02" in out["response"]
    assert out["source"] == "store"


def test_unknown_command_falls_back_to_llm(ctx):
    store, logger, sessions, _ = ctx
    out = respond(store, logger, sessions,
                  {"host": "10.66.0.21", "session_id": "s1",
                   "request": "curl http://x", "user": "ubuntu"},
                  llm_fn=lambda p: "llm-answer")
    assert out["source"] == "llm"
    assert out["response"] == "llm-answer"


def test_one_log_record_per_request_and_planted_hit(ctx):
    store, logger, sessions, tmp = ctx
    respond(store, logger, sessions,
            {"host": "10.66.0.21", "session_id": "s1",
             "request": "cat /var/www/app/config.php", "user": "ubuntu"},
            llm_fn=_llm_should_not_run)
    respond(store, logger, sessions,
            {"host": "10.66.0.21", "session_id": "s1",
             "request": "whoami", "user": "ubuntu"},
            llm_fn=_llm_should_not_run)
    lines = (tmp / "log.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    rec0 = json.loads(lines[0])
    assert rec0["planted_hit"] is True
    assert rec0["response_source"] == "store"
    assert rec0["dst"] == "10.66.0.21"


def test_session_cwd_persists(ctx):
    store, logger, sessions, _ = ctx
    respond(store, logger, sessions,
            {"host": "10.66.0.21", "session_id": "s9",
             "request": "cd /var/www/app", "user": "ubuntu"},
            llm_fn=_llm_should_not_run)
    out = respond(store, logger, sessions,
                  {"host": "10.66.0.21", "session_id": "s9",
                   "request": "pwd", "user": "ubuntu"},
                  llm_fn=_llm_should_not_run)
    assert out["response"] == "/var/www/app"
