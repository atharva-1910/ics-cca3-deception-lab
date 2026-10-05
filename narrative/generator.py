"""Clue-chain generator for the False-Belief Attack (HANDOVER §6.6, Module 9).

Builds an ordered chain of mutually-confirming fake facts across decoy hosts and
writes them into the consistency store in ONE transaction (§6.5 consistency +
fixed-seed rules), then emits ground_truth.json (§6.7) listing the planted facts
so the scorer can classify the agent's report.

Facts, not instructions: every rendered artifact passes narrative/lint.py.

Usage:
    python narrative/generator.py --template t1 --seed 7 \
        --topology topology.json --run-id C-H-D2-07
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from random import Random

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "store"))

from narrative.lint import lint_no_instructions  # noqa: E402
try:
    from store.state import Store  # noqa: E402
except ImportError:  # pragma: no cover
    from state import Store  # type: ignore

TEMPLATE_DIR = Path(__file__).with_name("templates")
TEMPLATE_FILES = {
    "t1": "t1_web_db_backup.yaml",
    "t2": "t2_dev_git_ci.yaml",
    "t3": "t3_mon_dc.yaml",
}

# Deterministic fallback names/users per role (used when no LLM filler is given).
_ROLE_NAMES = {
    "web": "web-01", "db": "db-internal-02", "backup": "bk-vault-01",
    "workstation": "dev-ws-07", "git": "git.corp.local", "vault": "vault-ci-01",
    "monitoring": "mon-01", "dc": "dc-01.corp.local",
}
_ROLE_USERS = {
    "web": "app_rw", "db": "app_rw", "backup": "backup",
    "workstation": "developer", "git": "gitbot", "vault": "ci",
    "monitoring": "zbx", "dc": "svc_backup",
}
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


def gen_password(rng: Random, n: int = 14) -> str:
    specials = "!@#$%^&*-_+"
    body = "".join(rng.choice(_ALPHABET) for _ in range(n - 2))
    return body + rng.choice(specials) + rng.choice("0123456789")


def gen_key_blob(rng: Random) -> str:
    return "".join(rng.choice(_ALPHABET + "+/") for _ in range(64))


def load_template(name: str) -> dict:
    fname = TEMPLATE_FILES.get(name, name)
    path = TEMPLATE_DIR / fname
    return yaml.safe_load(path.read_text())


def _host_id_for_ip(store: Store, ip: str, fallback_name: str) -> str:
    row = store.get_host_by_ip(ip)
    return row["host_id"] if row else fallback_name


def build_chain(template: dict, decoy_hosts: list[dict], seed: int,
                store: Store, llm=None, run_id: str = "run") -> dict:
    """Plant the chain; return the ground_truth dict."""
    rng = Random(seed)
    hops = template["hops"]
    if len(decoy_hosts) < len(hops):
        raise ValueError(f"need >= {len(hops)} decoys, got {len(decoy_hosts)}")

    ips = [d["ip"] for d in decoy_hosts[:len(hops)]]
    names, users, passwords = [], [], []
    for hop in hops:
        role = hop["role"]
        if llm is not None:
            fill = llm(hop.get("name_slot"), seed)
            names.append(fill.get("host", _ROLE_NAMES.get(role, role)))
            users.append(fill.get("user", _ROLE_USERS.get(role, "user")))
        else:
            names.append(_ROLE_NAMES.get(role, f"{role}-decoy"))
            users.append(_ROLE_USERS.get(role, "user"))
        passwords.append(gen_password(rng))
    key_blob = gen_key_blob(rng)

    planted_facts: list[list] = []

    def subst(s: str, i: int) -> str:
        ctx = {
            "this_host": names[i], "this_ip": ips[i],
            "user": users[i], "pass": passwords[i], "key": key_blob,
        }
        if i + 1 < len(hops):
            ctx.update(next_host=names[i + 1], next_ip=ips[i + 1],
                       next_user=users[i + 1], next_pass=passwords[i + 1])
        out = s
        for k, v in ctx.items():
            out = out.replace("{" + k + "}", str(v))
        return out

    with store.transaction():
        for i, hop in enumerate(hops):
            host_id = _host_id_for_ip(store, ips[i], names[i])
            store.add_host(host_id, ips[i], names[i],
                           persona=f'{hop["role"]} server', gen_type="llm_store")
            store.set_hostname(host_id, names[i])

            # The account that exists on this hop (previous hop's clue points here).
            if hop.get("accepts_cred"):
                store.add_user(host_id, users[i], password=passwords[i],
                               uid=1000 + i, planted=1)

            for art in hop.get("artifacts", []):
                content = subst(art["template"], i)
                lint_no_instructions(content)  # facts, not instructions
                path = subst(art["path"], i)
                if art.get("append"):
                    existing = store.read_file(host_id, path)
                    if existing is not None:
                        content = existing["content"] + content
                # ensure parent dirs exist
                parent = path.rsplit("/", 1)[0] or "/"
                if parent != "/":
                    store.mkdir(host_id, parent, planted=1)
                store.write_file(host_id, path, content,
                                 owner=subst(art.get("owner", "root"), i),
                                 mode=art.get("mode", "0644"), planted=1)
                for triple in art.get("facts", []):
                    planted_facts.append([subst(str(x), i) for x in triple])

    # Deduplicate planted facts.
    uniq = {tuple(f): f for f in planted_facts}
    planted = [{"s": f[0], "p": f[1], "o": f[2]} for f in uniq.values()]

    prize_name = names[template["prize_hop"]]
    ground_truth = {
        "run_id": run_id,
        "template": template["name"],
        "seed": seed,
        "real": _real_facts(store),
        "planted_false": planted,
        "prize": prize_name,
        "decoys": ips,
    }
    return ground_truth


def _real_facts(store: Store) -> list[dict]:
    """Ground-truth facts for real hosts, keyed by IP (the agent usually reports
    real hosts by IP with an empty/unknown hostname). Includes label and the
    host's service so a correct report scores as 'true', not 'other_false'."""
    out = []
    for row in store.conn.execute("SELECT * FROM hosts WHERE gen_type='real'"):
        ip = row["ip"]
        out.append({"s": ip, "p": "is_host", "o": True})
        out.append({"s": ip, "p": "label", "o": "real"})
        persona = (row["persona"] or "").lower()
        if "web" in persona:
            out.append({"s": ip, "p": "runs_service", "o": "http"})
        elif "ssh" in persona:
            out.append({"s": ip, "p": "runs_service", "o": "ssh"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default="t1")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--topology", default=str(REPO / "topology.json"))
    ap.add_argument("--db", default=str(REPO / "store" / "state.db"))
    ap.add_argument("--run-id", default="run")
    ap.add_argument("--out", default=None, help="ground_truth.json path")
    args = ap.parse_args()

    template = load_template(args.template)
    topo_path = Path(args.topology)
    if topo_path.exists():
        decoys = json.loads(topo_path.read_text())["decoys"]
    else:
        # fall back to the fixed decoy block from HANDOVER §6.7
        decoys = [{"ip": f"10.66.0.2{i}"} for i in range(1, 5)]
        print("warning: no topology.json; using default decoy IPs", file=sys.stderr)

    store = Store(args.db)
    gt = build_chain(template, decoys, args.seed, store, run_id=args.run_id)

    out = Path(args.out) if args.out else REPO / "ground_truth.json"
    out.write_text(json.dumps(gt, indent=2))
    print(f"planted {len(gt['planted_false'])} facts; prize={gt['prize']}; "
          f"wrote {out}")


if __name__ == "__main__":
    main()
