#!/usr/bin/env bash
# Report journal-style word counts for the manuscript: main text, Supporting
# Information, and total. Counts only what counts toward a journal word limit
# (see wordcount.typ for exactly what is excluded vs. included). Pure query --
# does not build paper.pdf.
set -euo pipefail
# The manuscript root, one level up: this script lives in tools/.
cd "$(dirname "$0")/.."

json=$(typst query wordcount.typ '<wc>' --field value --one)

# uv run rather than bare python3: the table renders through rich, which lives
# in the locked toolchain environment. The exemption list stays one caption
# line -- the full version lives in wordcount.typ, where it is enforced.
uv run --quiet python - "$json" <<'PY'
import json, sys
sys.path.insert(0, "tools")
from report import console, table

d = json.loads(sys.argv[1])
t = table("Journal word count",
          caption="excludes refs, floats, captions, math, block code")
t.add_column()
t.add_column("words", justify="right")
t.add_column("chars", justify="right")
t.add_row("Abstract [dim](own limit; not in total)[/]",
          f"{d['abstract_words']:,}", f"{d['abstract_chars']:,}")
t.add_row("Main text", f"{d['main_words']:,}", f"{d['main_chars']:,}")
t.add_row("Supporting Information", f"{d['si_words']:,}", f"{d['si_chars']:,}")
t.add_row("[bold]Total (main + SI)[/]",
          f"[bold]{d['total_words']:,}[/]", f"[bold]{d['total_chars']:,}[/]")
console.print(t)
PY
