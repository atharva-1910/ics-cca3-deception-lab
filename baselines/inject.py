"""Plant the Mantis-style injection baseline D1 (HANDOVER §6.9, §10.9).

Unlike the D2 clue chain, D1 artifacts DELIBERATELY contain instructions, so they
do NOT go through narrative/lint.py. They are written into the consistency store
on the decoy hosts (so `cat /etc/motd` etc. return them) and a ground_truth.json
is emitted whose planted_false fact is the single target the injection pushes —
letting the same scorer compute PBCS for D1 and D2 on equal footing.

Usage:
    python baselines/inject.py --topology topology.json --run-id C-H-D1-07
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
try:
    from store.state import Store
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(REPO / "store"))
    from state import Store  # type: ignore

STRINGS = Path(__file__).with_name("injection_strings.yaml")


def plant(store: Store, decoys: list[dict], run_id: str) -> dict:
    cfg = yaml.safe_load(STRINGS.read_text())
    # The injection pushes the LAST decoy as the sole "production" target.
    prize_ip = decoys[-1]["ip"]
    planted = []
    with store.transaction():
        for d in decoys:
            hrow = store.get_host_by_ip(d["ip"])
            host_id = hrow["host_id"] if hrow else d["ip"]
            store.add_host(host_id, d["ip"], d.get("hostname", host_id),
                           gen_type="llm_store")
            for f in cfg.get("files", []):
                content = f["value"].replace("{prize_ip}", prize_ip)
                parent = f["path"].rsplit("/", 1)[0] or "/"
                if parent != "/":
                    store.mkdir(host_id, parent, planted=1)
                store.write_file(host_id, f["path"], content, planted=1)
    planted.append({"s": prize_ip, "p": "role", "o": "backup_server"})
    planted.append({"s": prize_ip, "p": "recommended_target", "o": "true"})
    return {
        "run_id": run_id, "template": "D1_injection",
        "real": [], "planted_false": planted,
        "prize": prize_ip, "decoys": [d["ip"] for d in decoys],
        "injection_banner": cfg.get("banners", []),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topology", default=str(REPO / "topology.json"))
    ap.add_argument("--db", default=str(REPO / "store" / "state.db"))
    ap.add_argument("--run-id", default="run")
    ap.add_argument("--out", default=str(REPO / "ground_truth.json"))
    args = ap.parse_args()

    decoys = json.loads(Path(args.topology).read_text())["decoys"]
    store = Store(args.db)
    gt = plant(store, decoys, args.run_id)
    Path(args.out).write_text(json.dumps(gt, indent=2))
    print(f"D1 injection planted on {len(decoys)} decoys; prize={gt['prize']}")


if __name__ == "__main__":
    main()
