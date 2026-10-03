"""Consistency prober for Experiment B (HANDOVER §10.8, §13).

Sends follow-ups that revisit earlier facts and flags a contradiction when a
later response conflicts with an earlier one in the same session. Two modes:

  scripted : fixed question bank (attacker/questions.yaml), {ref} slots filled
             from the session so far.
  llm      : an LLM instructed to hunt contradictions, given the session so far.

Metric: turns-to-detection = follow-up turns until the first confirmed
contradiction (30 if none); contradiction count per 30-turn session.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
QUESTIONS = Path(__file__).with_name("questions.yaml")
ENGINE_URL = os.environ.get("ENGINE_URL", "http://127.0.0.1:9000")
MAX_TURNS = 30


def _load_questions() -> list[str]:
    data = yaml.safe_load(QUESTIONS.read_text())
    return list(itertools.chain.from_iterable(data.values()))


def _fill(q: str, mem: dict) -> str:
    for slot in re.findall(r"\{(\w+)\}", q):
        q = q.replace("{" + slot + "}", mem.get(slot, {
            "last_file": "/etc/hosts", "last_dir": "/home",
            "last_user": "root", "last_service": "ssh"}.get(slot, "x")))
    return q


def _ask(host: str, session_id: str, command: str) -> str:
    import httpx
    r = httpx.post(f"{ENGINE_URL}/respond", timeout=70, json={
        "host": host, "protocol": "ssh", "session_id": session_id,
        "request": command, "user": "ubuntu", "src": "10.66.0.100"})
    return r.json().get("response", "")


def detect_contradiction(command: str, response: str, seen: dict) -> bool:
    """A contradiction = same command, different normalised response (§10.8)."""
    key = command.strip()
    norm = response.strip()
    if key in seen and seen[key] != norm:
        return True
    seen.setdefault(key, norm)
    return False


def probe_scripted(host: str, session_id: str, ask=_ask) -> dict:
    questions = _load_questions()[:MAX_TURNS]
    seen: dict[str, str] = {}
    mem: dict[str, str] = {}
    turns_to_detection = MAX_TURNS
    contradictions = 0
    log = []
    for i, raw_q in enumerate(questions, 1):
        q = _fill(raw_q, mem)
        resp = ask(host, session_id, q)
        if q.startswith("cat ") and "No such" not in resp:
            mem["last_file"] = q.split()[1]
        hit = detect_contradiction(q, resp, seen)
        log.append({"turn": i, "q": q, "contradiction": hit})
        if hit:
            contradictions += 1
            if turns_to_detection == MAX_TURNS:
                turns_to_detection = i
    return {"host": host, "turns_to_detection": turns_to_detection,
            "contradictions_per_30": contradictions, "log": log}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True, help="decoy IP to probe")
    ap.add_argument("--session", default="probe-1")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    result = probe_scripted(args.host, args.session)
    out = Path(args.out) if args.out else REPO / "results" / "B" / f"probe-{args.host}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(f"turns_to_detection={result['turns_to_detection']} "
          f"contradictions={result['contradictions_per_30']} -> {out}")


if __name__ == "__main__":
    main()
