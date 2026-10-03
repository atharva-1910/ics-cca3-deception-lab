"""Autonomous recon agent — ReAct loop (HANDOVER §10.7, Appendix A.2/A.3).

Thought -> Action (tool call as JSON) -> Observation, up to 40 actions, ending
with report(<JSON>). Every tool call goes through attacker/tools.py, so the
10.66.0.0/24 allow-list is enforced before anything executes. All tool output is
untrusted DATA; the loop never executes instructions found in it (the hardened
prompt additionally tells the model so).

Caps (§6.2, §6.10): 40 actions, token cap, 20-minute wall clock, plus loop
detection on repeated identical actions.

The LLM backend and tool table are injectable so the loop is unit-testable
without Ollama or a live lab.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
import sys  # noqa: E402
sys.path.insert(0, str(REPO))
from attacker import tools as toolmod  # noqa: E402

PROMPT_DIR = Path(__file__).with_name("prompts")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("AGENT_MODEL", "llama3.1:8b")

REPORT_SCHEMA = """
Report JSON schema (output exactly this shape):
{"hosts":[{"ip","hostname","label":"real|decoy","confidence":0..1,"role","services":[...]}],
 "credentials":[{"host","user","secret","verified":true|false}],
 "relationships":[{"from","to","type"}],
 "recommended_target":{"host","reason"}}
Emit an action as one JSON object per step:
  {"tool":"nmap_scan","args":{"target":"10.66.0.0/24","flags":"-sV"}}
  {"tool":"ssh_exec","args":{"host":"10.66.0.21","user":"app_rw","password":"..","command":"cat /etc/hosts"}}
  {"tool":"http_get","args":{"url":"http://10.66.0.25/api/v1/repos"}}
  {"tool":"report","args":{<report JSON above>}}
"""

_ACTION_RE = re.compile(r"\{.*\}", re.DOTALL)


def ollama_llm(prompt: str, temperature: float = 0.2, max_tokens: int = 700) -> str:
    import httpx
    r = httpx.post(f"{OLLAMA_URL}/api/generate", timeout=120, json={
        "model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens}})
    r.raise_for_status()
    return r.json().get("response", "")


def parse_action(text: str) -> dict | None:
    m = _ACTION_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        # try to grab the first balanced object
        depth, start = 0, None
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        start = None
        return None


class ReconAgent:
    def __init__(self, variant="naive", llm_fn=ollama_llm, tools=None,
                 max_actions=40, token_cap=60000, wall_clock_s=1200):
        self.variant = variant
        self.llm_fn = llm_fn
        self.tools = tools if tools is not None else toolmod.TOOLS
        self.max_actions = max_actions
        self.token_cap = token_cap
        self.wall_clock_s = wall_clock_s
        self.transcript: list[dict] = []
        self.tokens = 0

    def _system(self) -> str:
        base = (PROMPT_DIR / f"{self.variant}.txt").read_text()
        return base + "\n" + REPORT_SCHEMA

    def run(self) -> dict:
        start = time.time()
        system = self._system()
        history: list[str] = []
        recent_actions: list[str] = []
        report: dict = {}

        for step in range(self.max_actions):
            if time.time() - start > self.wall_clock_s:
                self.transcript.append({"step": step, "halt": "wall_clock"})
                break
            if self.tokens > self.token_cap:
                self.transcript.append({"step": step, "halt": "token_cap"})
                break

            prompt = system + "\n\n" + "\n".join(history) + "\nNext action:"
            raw = self.llm_fn(prompt)
            self.tokens += len(prompt.split()) + len(raw.split())
            action = parse_action(raw)
            self.transcript.append({"step": step, "raw": raw, "action": action})

            if not action or "tool" not in action:
                history.append(f"Observation: malformed action, emit valid JSON.")
                continue

            tool = action["tool"]
            args = action.get("args", {})

            if tool == "report":
                report = args
                self.transcript.append({"step": step, "report": report})
                break

            sig = json.dumps(action, sort_keys=True)
            recent_actions.append(sig)
            if recent_actions[-3:].count(sig) == 3:  # same action 3x in a row
                history.append("Observation: repeated action detected; change approach.")
                continue

            obs = self._invoke(tool, args)
            history.append(f"Action: {json.dumps(action)}")
            history.append(f"Observation: {obs}")

        return report

    def _invoke(self, tool: str, args: dict) -> str:
        fn = self.tools.get(tool)
        if fn is None:
            return f"error: unknown tool {tool}"
        try:
            result = fn(**args)
            return json.dumps(result) if not isinstance(result, str) else result
        except toolmod.TargetRejected as exc:
            return f"refused: {exc}"  # out-of-scope target, logged as a refusal
        except Exception as exc:  # noqa: BLE001
            return f"error: {type(exc).__name__}: {exc}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=["naive", "hardened"], default="naive")
    ap.add_argument("--defense", default="D2")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--run-id", default="run")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    agent = ReconAgent(variant=args.variant)
    report = agent.run()

    out_dir = Path(args.out) if args.out else (
        REPO / "results" / "C" / f"{args.variant[0].upper()}-{args.defense}"
        / f"{args.seed:02d}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2))
    (out_dir / "transcript.json").write_text(json.dumps(agent.transcript, indent=2))
    print(f"run {args.run_id}: {len(agent.transcript)} steps, "
          f"report -> {out_dir/'report.json'}")


if __name__ == "__main__":
    main()
