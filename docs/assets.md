# Generated figures and tables

Where figures and tables come from, how they are declared, and how the analysis is wired in.

## The `si/` contract: generated tables, never hand-typed numbers

Tables whose numbers come from an analysis are written by a script into
`si/*.typ` as a bare `#table(...)`, and `si-body.typ` wraps them in a `#figure`
that supplies the caption and label. Every generated file opens with a
"do not edit by hand" header.

`analysis/scripts/gen_example_table.py` is the template. Copy it per table.
`just assets` runs every `gen_*_table.py`, so the *discovery* needs no wiring
beyond matching the filename pattern.

**It does need wiring beyond that, and it is worth knowing before you start.**
Adding a figure or table is four steps, not one:

1. Copy the example generator, keep the `gen_*_figure.py` / `gen_*_table.py`
   name, and write into `figures/` or `si/`.
2. Call `record("fig.yourname", …, kind="figure", inputs=[…])` at the end of it.
   That declares the id; `inputs` is the data it read.
3. Reference it in the prose by id, not by filename:
   `#figure(fig("fig.yourname"), caption: [...]) <fig:yourname>`.
4. If this is the project's first one, add `fig`/`tbl` to `wordcount.typ`'s eval
   scope. Missing this leaves `just paper` working and only `just wordcount`
   failing, which is the least obvious way for it to break.

Step 2 is what buys the per-file staleness checking, and step 3 is what stops the
manifest rotting into a ledger nobody reads. Neither is free, and the trade is
deliberate.

The point is that a number in the manuscript should be traceable to the analysis
that produced it. Re-run the analysis and the manuscript updates.

## Adding a table or figure, step by step


A table: copy `analysis/scripts/gen_example_table.py`, keep the filename pattern
`gen_*_table.py` so `just assets` picks it up with no wiring, and write a bare
`#table(...)` into `../../si/` with the auto-generated header and no caption or
label. Then wrap it in a `#figure` in `si-body.typ`, where the caption and label
live:

```typst
#figure(tbl("tbl.yourname"), caption: [...]) <tbl:yourname>
```

A figure: copy `analysis/scripts/gen_example_figure.py`, keep the pattern
`gen_*_figure.py`, and write straight into `../../figures/`. Set
`metadata={"Software": None}` and seed any RNG, or every regeneration churns the
PNG bytes and shows up as a diff that is not a real change. Reference it as
`#figure(fig("fig.yourname", width: 70%), caption: [...]) <fig:yourname>`.

**Either way, call `record(...)` at the end of the generator**, which is what
declares the id the manuscript uses:

```python
from _assets import record
record("fig.yourname", str(OUT.relative_to(PAPER)), kind="figure",
       inputs=[str(SRC.relative_to(PAPER))], desc="what it shows")
```

`inputs` is the DATA it read; the script and its imports are recorded
automatically. Paths are relative to the manuscript root, not to `analysis/`.

Then `just assets && git add figures si assets.json stats.json`, because all
of those are tracked.

## Figures and tables by id: `fig("fig.x")`, not a filename

The same contract as numbers, for files. Each generator calls `record(...)` to
declare what it wrote, into `assets.json`:

```json
"fig.example": {
  "path": "figures/example_figure.png",
  "kind": "figure",
  "hash": "sha256:b100e70d…",
  "origin": {"by": "analysis/scripts/gen_example_figure.py",
             "at": "2026-08-06T18:20:00Z"},
  "inputs": {
    "analysis/scripts/gen_example_figure.py": "sha256:1b2fcdf2…",
    "analysis/scripts/example_data.csv":      "sha256:c19c8377…"
  }
}
```

and the manuscript references the id rather than the path:

```typst
#figure(fig("fig.example", width: 70%), caption: [...]) <fig:example>
```

**Referencing by id is what makes the manifest worth having.** A manifest that
merely sits beside the files it describes rots, because nothing reads it. This
one is on the path the compile takes, so an undeclared id stops the build the
same way an undeclared `#s("id")` does — it cannot quietly stop being true.
`just prose-check` reports naming a declared asset directly as an error, which is
what keeps the bypass closed.

`just check-assets` then checks per entry: the output still hashes to
what was recorded (so a hand-edit to a generated file is caught and *attributed*),
the generator still exists, and the declared inputs are unchanged. `origin.at`
is when the output last *changed*: a regeneration that produces byte-identical
output (seeded RNG, no embedded timestamps) keeps the old date, so the
timestamp carries information.

Inputs are part automatic, part declared. The generator and every module it
imports from `analysis/` are recorded by walking `sys.modules`, which is exact
because imports are always Python-level. **Data files are declared by hand**
(`inputs=[...]`), because the automatic version is not exact: an audit hook on
`open` cannot see reads that HDF5, parquet and most binary readers do from C, and
would record an empty input set for precisely the formats that matter. A missed
input means a stale figure reported as current, so that half stays explicit.

An input that is not present — the normal state of a fresh clone, since
`analysis/data/` is untracked — is reported as unverified, never as stale.

A figure entry also records its **print geometry** under `print`: `width_in`,
`height_in` and `dpi` read back from the written raster (after any
`bbox_inches="tight"` crop), and `min_pt`, the smallest visible type on it,
when the generator passes the matplotlib figure as `record(..., fig=fig)`. A
figure no matplotlib canvas drew may state `min_pt=` instead. Journal rules are
a column width in inches and a type floor in points, and neither is visible in
the manuscript source.

`record()` takes an advisory lock around its read-modify-write of
`assets.json` (`.build-state/assets.lock`), so a project that runs its
generators in parallel does not lose entries.

This replaced `.assets-stamp`, a pair of whole-tree hashes that fired on the same
failures and could only report "analysis/ has changed" without naming the figure
it ruined — and that also fired on a new file no generator imports, a change
which by definition altered no output.

What went with it: **an input a generator reads without declaring or importing is
now invisible.** Nothing checks it — and nothing meaningfully did before. The
stamp excluded `analysis/data/`, so whether it caught an undeclared read depended
on where the file sat, not on whether it mattered.

There is no automatic answer that is actually right: an audit hook cannot see
C-level reads, a directory hash misses anything outside it and fires on changes
that altered nothing. So the scaffold no longer pretends to have one. **Which
files are worth tracking is the author's call**, declared in `inputs=[...]`, and
`record()` prints a note when a generator declares none — the omission is visible
where it is made rather than discovered from a wrong figure.

## `analysis/` lives inside the manuscript, and writes to it directly

The analysis that produces the numbers is a subdirectory, not a sibling
repository. It writes its figures into `figures/` and its tables into `si/` with
no staging copy in between.

That last part is the point. A copy is the single most reliable way for a
manuscript to go quietly wrong: a re-analysis updates the plot upstream, the copy
in `figures/` is untouched, and the PDF keeps rendering a figure that no longer
matches the numbers in its own caption. Writing to the destination removes the
failure rather than adding a guard for it.

**The location is load-bearing, not a taste.** The provenance machinery
resolves the manuscript root as `analysis/scripts/../..`, and the
`sys.modules` walk keeps exactly the modules whose paths start with
`analysis/`. An analysis kept as a sibling repository means forking those
tools, not just re-pointing a path — if you are migrating an existing paper,
moving the analysis under the manuscript is what lets the scaffold work
unmodified. (And if the repository publishes a package or crate, check its
include/exclude list afterwards: a newly nested analysis tree can quietly ship
to a registry.)

**The contract is one recipe.** `analysis/justfile` exposes `assets`, which
regenerates everything the manuscript includes. `just assets` at the top level
delegates to it and knows nothing else. Whatever is inside `analysis/` is that
project's business: sixty numbered scripts, one notebook, a Snakemake pipeline.
Keep `assets` as the front door and the manuscript never has to care.

A paper with no computed results simply has no `analysis/` directory, and the
recipes say so instead of failing.

`figures/` and `si/` are generated but **tracked**, so a fresh clone compiles
without re-running an analysis that may take hours. (`paper.pdf` is not tracked —
see below.) `just check-assets` guards them per file through `assets.json`: each
entry records a hash of the output and of every input its generator declared, so
editing a generator and forgetting to re-run it is reported — with the figure and
the script named.

Hashes rather than commit dates, because the generators are deterministic on
purpose. Re-running one after an edit that does not move the output produces no
new commit, and a date-based check would then nag with no way to satisfy it.
