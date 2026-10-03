"""Aggregate scored runs into summary tables and charts (HANDOVER §12.4, §13.3).

Reads every results/<exp>/<config>/<seed>/score.json, writes summary.csv with
mean ± std per cell, runs a Mann-Whitney U test for D1 vs D2 under agent H (the
H4 comparison, §6.11) with effect size, and draws the grouped PBCS bar chart.

    python eval/aggregate.py --experiment C
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def load_scores(exp_dir: Path) -> "list[dict]":
    rows = []
    for score_file in exp_dir.rglob("score.json"):
        data = json.loads(score_file.read_text())
        # config dir looks like  N-D2 / H-D1
        config = score_file.parent.parent.name
        agent, _, defense = config.partition("-")
        data["agent"] = "hardened" if agent == "H" else "naive"
        data["defense"] = defense
        rows.append(data)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", default="C")
    args = ap.parse_args()
    exp_dir = REPO / "results" / args.experiment
    rows = load_scores(exp_dir)
    if not rows:
        print(f"no score.json under {exp_dir}; run the benchmark first")
        return

    import pandas as pd  # lazy: heavy deps only needed at aggregation time
    df = pd.DataFrame(rows)

    summary = (df.groupby(["defense", "agent"])["PBCS"]
               .agg(["mean", "std", "count"]).round(4))
    summary.to_csv(exp_dir / "summary.csv")
    print(summary)

    # H4: D1 vs D2 under agent H
    try:
        from scipy.stats import mannwhitneyu
        h = df[df["agent"] == "hardened"]
        d1 = h[h["defense"] == "D1"]["PBCS"]
        d2 = h[h["defense"] == "D2"]["PBCS"]
        if len(d1) and len(d2):
            u, p = mannwhitneyu(d2, d1, alternative="greater")
            effect = u / (len(d1) * len(d2))  # rank-biserial / common-language
            (exp_dir / "h4_test.json").write_text(json.dumps(
                {"comparison": "D2 > D1 | agent H", "U": u, "p_value": p,
                 "effect_size_cles": round(effect, 4),
                 "d1_mean": float(d1.mean()), "d2_mean": float(d2.mean())}, indent=2))
            print(f"H4  D2>D1 (agent H): U={u:.1f} p={p:.4f} CLES={effect:.3f}")
    except ImportError:
        print("scipy not installed; skipped Mann-Whitney U")

    # grouped bar chart: PBCS by defense, one bar per agent
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        pivot = df.pivot_table(index="defense", columns="agent",
                               values="PBCS", aggfunc="mean")
        ax = pivot.plot(kind="bar", rot=0)
        ax.set_ylabel("PBCS (planted belief corruption)")
        ax.set_title(f"Experiment {args.experiment}: PBCS by defense")
        plt.tight_layout()
        plt.savefig(exp_dir / "pbcs_by_defense.png", dpi=150)
        print(f"chart -> {exp_dir/'pbcs_by_defense.png'}")
    except ImportError:
        print("matplotlib not installed; skipped chart")


if __name__ == "__main__":
    main()
