#!/usr/bin/env bash
# Report journal-style word counts for the manuscript: main text, Supporting
# Information, and total. Counts only what counts toward a journal word limit
# (see wordcount.typ for exactly what is excluded vs. included). Pure query --
# does not build paper.pdf.
set -euo pipefail
# The manuscript root, one level up: this script lives in tools/.
cd "$(dirname "$0")/.."

json=$(typst query wordcount.typ '<wc>' --field value --one)

python3 - "$json" <<'PY'
import json, sys
d = json.loads(sys.argv[1])
rows = [
    ("Abstract (own limit; not in total)", d["abstract_words"], d["abstract_chars"]),
    ("Main text",                          d["main_words"],     d["main_chars"]),
    ("Supporting Information",             d["si_words"],       d["si_chars"]),
    ("Total (main + SI)",                  d["total_words"],    d["total_chars"]),
]
name_w = max(len(r[0]) for r in rows)
# One header line. The full exemption list lives in wordcount.typ, where it is
# enforced; repeating it all here made every build print a paragraph.
print("Journal word count  (excludes refs, floats, captions, math, block code)")
print(f"  {'':<{name_w}}  {'words':>8}  {'chars':>9}")
for name, w, c in rows:
    print(f"  {name:<{name_w}}  {w:>8,}  {c:>9,}")
PY
