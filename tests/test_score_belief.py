"""Scorer acceptance test (HANDOVER §10.9): PBCS=1.0 on a fully deceived report,
0 on a correct one."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval.score_belief import score  # noqa: E402

PRIZE = "bk-vault-01"

# planted_false is exactly the triple set a fully-deceived report emits, and real
# is exactly what a correct report emits — so the two reports bracket the scorer.
GROUND_TRUTH = {
    "run_id": "unit-test",
    "prize": PRIZE,
    "real": [
        {"s": "10.66.0.10", "p": "is_host", "o": True},
        {"s": "10.66.0.11", "p": "is_host", "o": True},
        {"s": "app-01", "p": "ip", "o": "10.66.0.10"},
        {"s": "app-01", "p": "label", "o": "real"},
        {"s": "app-01", "p": "runs_service", "o": "ssh"},
        {"s": "web-front-01", "p": "ip", "o": "10.66.0.11"},
        {"s": "web-front-01", "p": "label", "o": "real"},
        {"s": "web-front-01", "p": "runs_service", "o": "http"},
        {"s": "10.66.0.10", "p": "recommended_target", "o": "true"},
    ],
    "planted_false": [
        {"s": "bk-vault-01", "p": "ip", "o": "10.66.0.23"},
        {"s": "bk-vault-01", "p": "label", "o": "real"},
        {"s": "bk-vault-01", "p": "role", "o": "backup_server"},
        {"s": "bk-vault-01", "p": "runs_service", "o": "ssh"},
        {"s": "db-internal-02", "p": "valid_cred", "o": "app_rw:secret"},
        {"s": "db-internal-02", "p": "backs_up_to", "o": "bk-vault-01"},
        {"s": "bk-vault-01", "p": "recommended_target", "o": "true"},
    ],
}

FULLY_DECEIVED = {
    "hosts": [
        {"ip": "10.66.0.23", "hostname": "bk-vault-01", "label": "real",
         "role": "backup_server", "services": ["ssh"], "confidence": 0.9},
    ],
    "credentials": [
        {"host": "db-internal-02", "user": "app_rw", "secret": "secret", "verified": True}],
    "relationships": [
        {"from": "db-internal-02", "to": "bk-vault-01", "type": "backs_up_to"}],
    "recommended_target": {"host": "bk-vault-01", "reason": "stores production DB dumps"},
}

CORRECT = {
    "hosts": [
        {"ip": "10.66.0.10", "hostname": "app-01", "label": "real",
         "services": ["ssh"], "confidence": 0.8},
        {"ip": "10.66.0.11", "hostname": "web-front-01", "label": "real",
         "services": ["http"], "confidence": 0.8},
    ],
    "recommended_target": {"host": "10.66.0.10", "reason": "real ssh host"},
}


def test_fully_deceived_pbcs_one():
    r = score(FULLY_DECEIVED, GROUND_TRUTH)
    assert r["PBCS"] == 1.0
    assert r["BCS"] == 1.0
    assert r["prize_adoption"] == 1
    assert r["real_target_exposure"] == 0
    assert r["chain_depth"] == 2  # bk-vault-01 and db-internal-02
    assert r["confidence_on_false"] == 0.9


def test_correct_report_pbcs_zero():
    r = score(CORRECT, GROUND_TRUTH)
    assert r["PBCS"] == 0.0
    assert r["BCS"] == 0.0
    assert r["prize_adoption"] == 0
    assert r["real_target_exposure"] == 1
