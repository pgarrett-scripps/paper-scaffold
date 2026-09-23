---
name: new-figure
description: Add a generated manuscript figure or table, including its generator, asset declaration, caption, citations, and build checks. Use for new analysis assets, not wording-only caption edits.
---

# Add a generated figure or table

Work from the manuscript root and follow AGENTS.md/CLAUDE.md. Inspect the
project's analysis, available inputs, and assets.json before choosing a new
ID. Use `just trace <id> --json` if extending an existing asset. Follow the
requested content; do not invent results or substitute sample data when real
inputs are missing. Complete independent work and report what is needed if
an asset cannot yet be generated.

## Open review actions

Before editing, run `just check-actions --open` (silent when there is no
`reviews/ACTIONS.md`; a paper on a scaffold older than 3.24.0 has no recipe,
so read the file directly). Tell the user which open rows bear on this task:
rows whose `fix` is `/paper:new-figure`, and rows about the figures, tables
and captions in scope. Work on the rows the user asks for; do not widen the
task to clear the list.

## Generate and declare

Copy a relevant project generator, or gen_example_figure.py /
gen_example_table.py if present. Keep `gen_*_figure.py` / `gen_*_table.py` so
`just assets` discovers it. Derived papers may have removed the examples.

- Resolve paths from the script's location, not the shell's current directory.
  Write figures into figures/ and bare `#table(...)` files into si/.
- Tables carry the AUTO-GENERATED header. Captions and labels live in the
  manuscript wrapper. Do not hand-edit generated outputs.
- For Matplotlib PNGs, use `metadata={"Software": None}` and seed any RNG.
  Choose resolution for the intended print width; prose-check flags low DPI.
- Add dependencies to analysis/pyproject.toml and update its uv lock. Use the
  analysis environment, not an inline `uv run --with` installation.

Declare the file after writing it:

```python
from _assets import record
record("fig.yourname", str(OUT.relative_to(PAPER)), kind="figure",
       inputs=[str(SRC.relative_to(PAPER))], desc="what it shows")
```

For a table use a tbl. ID and kind="table". Include every data file read in
inputs, relative to the manuscript root; the script and its local imports
are recorded automatically. Follow the project's _assets.py contract.

## Connect it to the manuscript

```typst
#figure(fig("fig.yourname", width: 70%), caption: [...]) <fig:yourname>
#figure(tbl("tbl.yourname"), caption: [...]) <tbl:yourname>
```

Use the appropriate wrapper and cite it with @fig:yourname or @tbl:yourname.
Each included .typ file needs its own fig()/tbl() import from assets.typ,
with a path relative to that file; it does not inherit the caller's imports.
Route computed caption/prose numbers through stats.json and s(), with the
corresponding stats.typ import.

Check wordcount.typ imports fig()/tbl() and names them in its eval scope.
The scaffold already wires this; preserve it in a customized manuscript.
Keep floats in the intended body scope, and do not move body markers merely
to fix a count.

## Validate and finish

```bash
just assets
just fmt
just paper
just wordcount
just verify
```

Inspect the generated plot/table and caption for the requested content;
passing hashes do not establish that the visualization is correct. Rebuild
other deliverables if the gate names them stale. Inspect the Word result
when that export is part of the request. Quote the final gate verdict, asset
summary, and exact word count/readability.

Review the generated diff. Stage the intended figures, tables, and manifest
updates as AGENTS.md directs, including the new generator when staging the
change; preserve unrelated staged work and do not commit unless requested.
Missing analysis is not a reason to adopt a new output as if it were generated.

## Close the review actions this fixed

For each ledger row this edit actually fixed, and that the checks above
confirm, edit its row in `reviews/ACTIONS.md`: `status` to `done`, `closed`
to the short hash of the commit that contains the fix. This skill does not
commit unless asked, so until then write `uncommitted: <what changed>`; the
commit that lands it, or the next session, replaces that with the hash. The
ledger edit rides in the following commit, since a commit cannot name its
own hash. Leave a row open when the fix is partial, and say which part
remains in the report. Run `just check-actions` after editing the ledger
and report the ids closed.
