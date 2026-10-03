"""Clue-chain generator test (HANDOVER §10.9): walking T1 reaches the prize with
every credential working, and lint passes on all planted content."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from narrative.generator import build_chain, load_template  # noqa: E402
from narrative.lint import lint_no_instructions  # noqa: E402
from store.state import fresh  # noqa: E402

DECOYS = [
    {"ip": "10.66.0.21"}, {"ip": "10.66.0.22"},
    {"ip": "10.66.0.23"}, {"ip": "10.66.0.24"},
]


def test_t1_chain_reachable_and_consistent(tmp_path):
    store = fresh(tmp_path / "chain.db")
    gt = build_chain(load_template("t1"), DECOYS, seed=7, store=store, run_id="T")

    assert gt["prize"] == "bk-vault-01"
    assert len(gt["planted_false"]) >= 4

    # Hop A (web) config.php names the db host + working cred that hop B accepts.
    web_id = store.get_host_by_ip("10.66.0.21")["host_id"]
    cfg = store.read_file(web_id, "/var/www/app/config.php")["content"]
    assert "db-internal-02" in cfg

    # The valid_cred fact must actually authenticate on the db decoy (reachability).
    cred = next(f for f in gt["planted_false"] if f["p"] == "valid_cred")
    user, pw = cred["o"].split(":", 1)
    db_id = store.get_host_by_ip("10.66.0.22")["host_id"]
    assert store.check_password(db_id, user, pw)

    # /etc/hosts on web resolves the db hostname to the db decoy IP.
    hosts = store.read_file(web_id, "/etc/hosts")["content"]
    assert "10.66.0.22 db-internal-02" in hosts

    # every planted file passes the instruction lint
    for row in store.conn.execute("SELECT content FROM files WHERE planted=1"):
        lint_no_instructions(row["content"])


def test_fixed_seed_is_deterministic(tmp_path):
    s1 = fresh(tmp_path / "a.db")
    g1 = build_chain(load_template("t1"), DECOYS, seed=5, store=s1)
    s2 = fresh(tmp_path / "b.db")
    g2 = build_chain(load_template("t1"), DECOYS, seed=5, store=s2)
    assert g1["planted_false"] == g2["planted_false"]
