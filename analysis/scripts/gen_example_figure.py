#!/usr/bin/env python3
"""Write ../../figures/example_figure.png -- the figure half of the asset contract.

Note where this writes: straight into the manuscript's figures/ directory, not
into a staging area that something copies across afterwards. The copy is what
goes stale. A re-analysis updates the plot upstream, the copy in the manuscript
is untouched, and the PDF keeps rendering a figure that no longer matches its own
caption. Writing to the destination removes that failure rather than guarding it.

Picked up by `just assets` on the filename pattern gen_*_figure.py, so a new
figure needs no wiring.
"""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
PAPER = HERE.parent.parent          # analysis/scripts/ -> analysis/ -> paper/
SRC = HERE / "example_data.csv"
OUT = PAPER / "figures" / "example_figure.png"


def main() -> int:
    with SRC.open(newline="") as fh:
        rows = list(csv.DictReader(fh))

    labels = [r["condition"] for r in rows]
    obs = [float(r["observed"]) for r in rows]
    lo = [float(r["observed"]) - float(r["ci_low"]) for r in rows]
    hi = [float(r["ci_high"]) - float(r["observed"]) for r in rows]

    # dpi is set for the size the figure is PRINTED at, not the size it is
    # saved at. This one is placed at `width: 70%` of a 160 mm text block, so
    # 5.0 in x 300 dpi = 1500 px lands at ~340 dpi on the page. At the previous
    # 200 it was 227 dpi, under the 300 floor `just prose-check` enforces --
    # crisp on screen, soft on paper, and caught only after acceptance.
    fig, ax = plt.subplots(figsize=(5.0, 3.0), dpi=300)
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
    # `just check` see every regeneration as a real change.
    fig.savefig(OUT, metadata={"Software": None})
    plt.close(fig)
    print(f"wrote {OUT.relative_to(PAPER)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
