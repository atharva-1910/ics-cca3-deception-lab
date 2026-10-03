"""Experiment driver (HANDOVER §6.10, §12.4).

For Experiment C: for each defense (D0/D1/D2[/D3]) and agent (N/H), run `seeds`
times. Each run: reset store from snapshot, plant the defense, run the recon
agent, copy ground_truth.json into the run dir, and score it.

Needs the live lab (docker compose up) and Ollama for real runs; the per-run
steps are small subprocess calls so a single config/seed can be run by hand too
(§12.3). This script orchestrates, it does not reimplement the agent or scorer.

    python eval/run_benchmark.py --experiment C --seeds 1-3 \
        --agents naive,hardened --defenses D0,D1,D2
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from eval.score_belief import score  # noqa: E402

PY = sys.executable
GROUND_TRUTH = REPO / "ground_truth.json"


def parse_seeds(spec: str) -> list[int]:
    if "-" in spec:
        a, b = spec.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in spec.split(",")]


def reset():
    subprocess.run([PY, str(REPO / "store" / "seed.py"), "--snapshot", "base"],
                   check=True, cwd=REPO)


def plant_defense(defense: str, seed: int, run_id: str):
    if defense == "D0":
        # static baseline: nothing planted beyond the seeded hosts
        GROUND_TRUTH.write_text(json.dumps(
            {"run_id": run_id, "real": [], "planted_false": [],
             "prize": "", "decoys": []}, indent=2))
    elif defense == "D1":
        subprocess.run([PY, str(REPO / "baselines" / "inject.py"),
                        "--run-id", run_id], check=True, cwd=REPO)
    elif defense in ("D2", "D3"):
        subprocess.run([PY, str(REPO / "narrative" / "generator.py"),
                        "--template", "t1", "--seed", str(seed),
                        "--run-id", run_id], check=True, cwd=REPO)
        if defense == "D3":
            subprocess.run([PY, str(REPO / "baselines" / "inject.py"),
                            "--run-id", run_id, "--out",
                            str(REPO / "ground_truth.d1.json")], check=True, cwd=REPO)
    else:
        raise ValueError(defense)


def run_agent(variant: str, defense: str, seed: int, run_id: str) -> Path:
    out_dir = REPO / "results" / "C" / f"{variant[0].upper()}-{defense}" / f"{seed:02d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([PY, str(REPO / "attacker" / "recon_agent.py"),
                    "--variant", variant, "--defense", defense,
                    "--seed", str(seed), "--run-id", run_id,
                    "--out", str(out_dir)], check=True, cwd=REPO)
    return out_dir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", default="C")
    ap.add_argument("--seeds", default="1-10")
    ap.add_argument("--agents", default="naive,hardened")
    ap.add_argument("--defenses", default="D0,D1,D2")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan without running the agent")
    args = ap.parse_args()

    seeds = parse_seeds(args.seeds)
    agents = args.agents.split(",")
    defenses = args.defenses.split(",")
    plan = [(d, a, s) for d in defenses for a in agents for s in seeds]
    print(f"Experiment {args.experiment}: {len(plan)} runs")

    for defense, variant, seed in plan:
        run_id = f"{args.experiment}-{variant[0].upper()}-{defense}-{seed:02d}"
        if args.dry_run:
            print("  would run", run_id)
            continue
        reset()
        plant_defense(defense, seed, run_id)
        out_dir = run_agent(variant, defense, seed, run_id)
        shutil.copyfile(GROUND_TRUTH, out_dir / "ground_truth.json")
        report = json.loads((out_dir / "report.json").read_text())
        gt = json.loads((out_dir / "ground_truth.json").read_text())
        result = score(report, gt)
        (out_dir / "score.json").write_text(json.dumps(result, indent=2))
        print(f"  {run_id}: PBCS={result['PBCS']} prize={result['prize_adoption']}")


if __name__ == "__main__":
    main()
