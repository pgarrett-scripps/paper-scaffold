#!/usr/bin/env python3
"""Write si/stats.json: every number the manuscript states in prose.

THIS IS THE TEMPLATE FOR THE stats CONTRACT. Replace the example values with
your own. The rules that make it worth following:

  1. Every number that appears in a SENTENCE is declared here and read back as
     `#s("id")`. A number typed straight into the prose is one nothing can check.
     `just prose-check` flags a typed numeral that matches a declared value.
  2. Values come from the analysis output, never from a constant typed into this
     script. A number that only exists in the manuscript is a number nobody can
     reproduce.
  3. Guard anything the prose makes an assumption about. If a sentence says
     "higher", the value is guarded `sign="+"`, so the day it turns negative this
     script fails instead of the paper contradicting itself.
  4. Rounding is set here with `fmt`, next to the analysis, not in Typst.

Unlike the table and figure generators there is ONE of these per project: it
writes a single file, so splitting it across scripts would mean each clobbering
the last. Import from other modules if it grows.
"""
from __future__ import annotations

import csv
from pathlib import Path

from _stats import Stats

HERE = Path(__file__).resolve().parent
SRC = HERE / "example_data.csv"


def main() -> int:
    with SRC.open(newline="") as fh:
        rows = list(csv.DictReader(fh))

    observed = {r["condition"]: float(r["observed"]) for r in rows}
    best = max(observed, key=observed.get)
    control = observed["Control"]

    st = Stats()

    # The headline effect. Guarded on sign because the prose describes it as an
    # increase over control; a re-run that reversed it would fail here.
    st.add("effect.treated_over_control", observed["Treated"] - control,
           fmt="+.2f",
           desc="Treated minus Control observed effect",
           sign="+", between=(0, 10))

    # A ratio. Bounded well away from zero, which is what catches a denominator
    # that changed meaning.
    st.add("effect.treated_fold", observed["Treated"] / control, fmt=".2f",
           unit="x",
           desc="Treated effect as a fold change over Control",
           sign="+", between=(0.1, 100))

    # A count, with a thousands separator set once so every mention matches.
    st.add("cohort.total_n", sum(int(r["n"]) for r in rows), fmt=",",
           desc="Total participants across all conditions",
           sign="+")

    st.add("cohort.n_conditions", len(rows), fmt=",",
           desc="Number of conditions compared",
           sign="+")

    # A label. Not a number, so it takes no guard.
    st.add("effect.best_condition", best,
           desc="Condition with the highest observed effect")

    return st.write()


if __name__ == "__main__":
    raise SystemExit(main())
