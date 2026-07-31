#!/usr/bin/env python3
"""Write analysis/example_figure.png -- the upstream half of the figure contract.

Note where this writes: into the ANALYSIS tree, not into figures/. That is the
whole point of the arrangement. Figures are produced by the analysis that owns
the data, and `just figures` copies them into the manuscript according to
figures.map. `just check` then byte-compares the two, so a re-analysis that
changes a plot is reported as manuscript drift instead of silently leaving a
stale image in the PDF.

In a real project this script lives in the analysis repo (or its own directory)
and the manuscript's `analysis_root` in the justfile points at it. It is here so
the scaffold's loop is closed and testable out of the box.
"""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
SRC = HERE / "example_data.csv"
OUT = HERE.parent / "analysis" / "example_figure.png"


def main() -> int:
    with SRC.open(newline="") as fh:
        rows = list(csv.DictReader(fh))

    labels = [r["condition"] for r in rows]
    obs = [float(r["observed"]) for r in rows]
    lo = [float(r["observed"]) - float(r["ci_low"]) for r in rows]
    hi = [float(r["ci_high"]) - float(r["observed"]) for r in rows]

    fig, ax = plt.subplots(figsize=(5.0, 3.0), dpi=200)
    ax.errorbar(labels, obs, yerr=[lo, hi], fmt="o", capsize=4,
                color="#2563eb", ecolor="#94a3b8", markersize=7)
    ax.set_ylabel("Observed ratio")
    ax.set_ylim(0, 2.6)
    ax.grid(axis="y", alpha=0.25)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()

    OUT.parent.mkdir(exist_ok=True)
    # Deterministic bytes: matplotlib stamps a creation date into the PNG unless
    # told not to, which would make every regeneration look like real drift to
    # the byte-compare in `just check`.
    fig.savefig(OUT, metadata={"Software": None})
    plt.close(fig)
    print(f"wrote {OUT.relative_to(HERE.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
