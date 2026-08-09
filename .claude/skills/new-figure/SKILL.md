---
name: new-figure
description: Add a generated figure or table end to end — generator script, record() declaration, id reference in the prose, wordcount scope — the four steps where forgetting the last one breaks only `just wordcount`.
---

# Add a figure or table

Four steps, and the fourth is the one that bites: it leaves `just paper`
working and only `just wordcount` failing, which is the least obvious way to
break. Do all four, then prove it.

## 1. The generator

Copy the example (`analysis/scripts/gen_example_figure.py` or
`gen_example_table.py`) and keep the filename pattern — `gen_*_figure.py` /
`gen_*_table.py` — so `just assets` discovers it with no wiring. Figures
write into `../../figures/`; tables write a BARE `#table(...)` into
`../../si/` with the AUTO-GENERATED header and no caption or label (the
caption lives in the manuscript, step 3).

For figures: `metadata={"Software": None}` on savefig and seed any RNG, or
every regeneration churns the PNG bytes and shows up as a diff that is not a
real change. Mind print resolution — `prose-check` flags below 300 dpi at
the rendered width.

## 2. Declare it

At the end of the generator:

```python
from _assets import record
record("fig.yourname", str(OUT.relative_to(PAPER)), kind="figure",
       inputs=[str(SRC.relative_to(PAPER))], desc="what it shows")
```

`inputs` is the DATA it read (paths relative to the manuscript root — the
script and its imports are recorded automatically). An empty `inputs` prints
a note for a reason: an undeclared input is a change nothing can detect.

## 3. Reference it by id, never by filename

```typst
#figure(fig("fig.yourname", width: 70%), caption: [...]) <fig:yourname>
#figure(tbl("tbl.yourname"), caption: [...]) <tbl:yourname>
```

Cite it from the text (`@fig:yourname`) — an uncited float is a prose-check
ERROR. A filename path (`image("figures/...")`) is the bypass the manifest
exists to prevent, and is also an error.

## 4. The wordcount scope (first asset in a project only)

`wordcount.typ` must import `fig`/`tbl` AND name them in its eval `scope:`
line — the import alone is not enough. The scaffold ships this wired; check
it survived if this manuscript has diverged.

## Prove it

```bash
just assets                 # runs the generator, records the declaration
just paper && just wordcount
just verify                 # check-assets: hash, generator, inputs, reference
git add figures si assets.json stats.json
```

Quote check-assets' summary line ("N declared asset(s), no errors"). If the
data the generator needs is absent or the analysis cannot run, stop and say
so — `just adopt` is for committed outputs whose analysis is GONE, not a
shortcut past writing the generator.
