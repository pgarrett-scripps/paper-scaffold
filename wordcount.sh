#!/usr/bin/env bash
# Report journal-style word counts for the manuscript: main text, Supporting
# Information, and total. Counts only what counts toward a journal word limit
# (see wordcount.typ for exactly what is excluded vs. included). Pure query --
# does not build paper.pdf.
set -euo pipefail
cd "$(dirname "$0")"

json=$(typst query wordcount.typ '<wc>' --field value --one)

python3 - "$json" <<'PY'
import json, sys
d = json.loads(sys.argv[1])
rows = [
    ("Abstract",              d["abstract_words"], d["abstract_chars"]),
    ("Main text",             d["main_words"],     d["main_chars"]),
    ("Supporting Information", d["si_words"],       d["si_chars"]),
    ("Total (main + SI)",     d["total_words"],    d["total_chars"]),
]
name_w = max(len(r[0]) for r in rows)
print("Journal word count  (excl. refs, citations, figures/tables + captions,")
print("                     math, images, block code; incl. headings, inline code)")
print("  Abstract is counted separately (own journal limit); not in the total.")
print(f"  {'':<{name_w}}  {'words':>8}  {'chars':>9}")
for name, w, c in rows:
    print(f"  {name:<{name_w}}  {w:>8,}  {c:>9,}")
PY
