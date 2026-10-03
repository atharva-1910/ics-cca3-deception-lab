"""Agent loop + prober tests with scripted backends (no Ollama / no live lab)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from attacker.prober import detect_contradiction, probe_scripted  # noqa: E402
from attacker.recon_agent import ReconAgent, parse_action  # noqa: E402


def test_parse_action_from_noisy_text():
    txt = 'Thought: scan first.\n{"tool":"nmap_scan","args":{"target":"10.66.0.0/24"}}\nok'
    assert parse_action(txt) == {"tool": "nmap_scan",
                                 "args": {"target": "10.66.0.0/24"}}


def test_agent_reaches_report_and_enforces_allowlist():
    # Scripted model: try an out-of-scope scan, then report.
    script = iter([
        '{"tool":"nmap_scan","args":{"target":"8.8.8.8"}}',
        '{"tool":"nmap_scan","args":{"target":"10.66.0.0/24","flags":"-sV"}}',
        '{"tool":"report","args":{"hosts":[{"ip":"10.66.0.10","label":"real",'
        '"confidence":0.9}],"recommended_target":{"host":"10.66.0.10","reason":"x"}}}',
    ])
    observations = []

    def fake_llm(prompt):
        return next(script)

    def fake_nmap(target, flags="-sV"):
        # real tool validates scope; reuse the real validator via the tool module
        from attacker.tools import assert_network_in_scope
        assert_network_in_scope(target)
        return {"10.66.0.10": {"state": "up"}}

    agent = ReconAgent(variant="naive", llm_fn=fake_llm,
                       tools={"nmap_scan": fake_nmap})
    report = agent.run()
    assert report["recommended_target"]["host"] == "10.66.0.10"
    # the 8.8.8.8 attempt must have been refused, not executed
    refusals = [t for t in agent.transcript
                if isinstance(t.get("action"), dict)
                and t["action"].get("args", {}).get("target") == "8.8.8.8"]
    assert refusals, "expected the out-of-scope action to appear in the transcript"


def test_agent_token_cap_halts():
    agent = ReconAgent(variant="naive", llm_fn=lambda p: "no action here",
                       tools={}, token_cap=1)
    agent.run()
    assert any(t.get("halt") == "token_cap" for t in agent.transcript)


def test_prober_flags_contradiction():
    seen = {}
    assert detect_contradiction("cat /x", "A", seen) is False
    assert detect_contradiction("cat /x", "B", seen) is True


def test_prober_scripted_no_contradiction_when_consistent():
    # An always-consistent host: every command returns a stable answer.
    answers = {}

    def ask(host, session, command):
        return answers.setdefault(command, f"stable:{command}")

    result = probe_scripted("10.66.0.21", "s", ask=ask)
    assert result["contradictions_per_30"] == 0
    assert result["turns_to_detection"] == 30
