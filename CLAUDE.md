# Working in this directory

Instructions for an agent editing the manuscript. Read [README.md](README.md) for
what the pipeline does and [STYLE.md](STYLE.md) for prose conventions.

## Never do these

**Never hand-edit `si/*.typ`.** Those files are written by
`analysis/scripts/gen_*_table.py` and carry an "AUTO-GENERATED, do not edit by
hand" header. An edit survives until the next `just assets` and then vanishes,
usually unnoticed. Change the generator or the data it reads.
`just check-assets-manifest` catches it now, and names the file.

**`stats.json` is the exception: you MAY edit it.** It is the one generated file
that is also yours. Add a value with `origin.by = "hand"` and an `origin.note`
saying where the number came from, and `just assets` will not overwrite it. A
number that a script could compute still belongs in `gen_stats.py`; this is for
the ones no script can — a protocol figure, a vendor spec, a value from a paper.

**Never hand-edit files under `figures/`.** They are written by `analysis/`.
Change the script that produces the plot and run `just assets`.

**Never name a generated figure or table by filename.** They are declared in
`assets.json` by the script that writes them and referenced by id:
`#figure(fig("fig.example"), caption: [...])`. Naming the path directly bypasses
the manifest, so it stops describing the manuscript; `just prose-check` reports
that as an error. Add a new one by calling `record(...)` in the generator.

**Never type a result into the prose.** Declare it in
`analysis/scripts/gen_stats.py` and read it back as `#s("id")`. A typed numeral
drifts from the table beside it and nothing notices; `just prose-check` reports
one that matches a declared value. Guard anything the sentence assumes: if the
prose says "fell", declare it `sign="-"` so a re-run that reverses the sign fails
the build instead of shipping "fell by -3.1%". If a number is worth stating, it
is worth being traceable.

**Never delete the `// >>> BODY START` / `// <<< BODY END` markers** in
`paper.typ`. The word counter, the readability report, and the narrator all slice
the prose at them, and each hard-fails without them.

## Before saying the work is done

Two commands, in this order:

```bash
just paper      # rebuild, and print the current word count and readability
just verify     # the gate: formatting, extractors, prose rules, staleness
```

"I edited the text" is not done. "`just verify` is clean" is done. It rebuilds
nothing, so run it as often as you like; when it reports something stale it also
names the recipe that clears it.

Quote the word count and readability numbers `just paper` prints. Do not
estimate them.

What `verify` runs, and what each one is for:

- **`just fmt-check`** -- the hand-written sources are reflowed to 80 columns.
  Skipped with a note if typstyle is not installed.
- **`just test`** -- the prose extractors still handle every construct, before
  and after a reflow. This is the one that matters when you touch inline markup,
  math, links, or cross-references: those are recognized by regexes in
  `tools/typst_prose.py` that a reflow can break silently, which has happened three
  times (see that file for the cases).
- **`just prose-check`** -- fails on em dashes, British spellings, doubled words,
  and uncited figures; reports long sentences, verbosity, repetition, and
  unexpanded acronyms as warnings you should read rather than silence.
- **`just check-stats`** -- re-runs every guard in `stats.json` against the
  committed values, re-runs `gen_stats.py` and diffs the values it owns, insists a
  hand-entered number carries a note, and reports ids nothing reads.
- **`just check-assets-manifest`** -- per generated file: does it still hash to
  what was recorded, does its generator still exist, have its declared inputs
  changed, and does anything reference it.
- **`just check`** -- a `paper.pdf` or `paper.docx` built from sources that have
  since changed, and `figures/` and `si/` older than the `analysis/` code behind
  them. Neither output is tracked in git; `just paper` and `just docx` record what
  they rendered in `.build-stamp` and `just check-build` recompares it. No check
  reads git history, so they all work outside a repository.

`just check` deliberately does not check the audiobooks, and there is no upstream
figure copy to compare against any more. See HISTORY.md's "Decisions reversed"
before adding either back.

Do not silence a prose-check finding by editing `tools/prose_check.py`. Add it to
`prose-check.toml` with a comment saying why, so the exception is reviewable, and
run `just prose-check --show-suppressed` occasionally to see what has
accumulated.

## Numbers about the draft

`just viz` writes `viz/report.json` alongside its plots. Read it rather than
re-deriving anything from the source: it already holds the section metrics, the
longest sentences with their text, which floats are cited once or not at all,
and the bibliography's age and self-citation share. Deriving those separately
gets a different answer, because this pipeline strips citations, math, code and
captions before measuring anything and an ad-hoc count does not.

Two more worth running by hand, not part of the gate: `just density` shows which
section is densest relative to the rest of the paper, and `just doctor` reports
whether the external toolchain is present and new enough.

If you taught an extractor to handle a new construct, add a case for it to
`tests/fixture.typ` and regenerate the golden files with `just test-update`,
reading the diff before you commit it. Do not add coverage by putting the
construct in `paper.typ`: that prose is placeholder and gets deleted.

## When adding a table or figure

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

Then `just assets && git add figures si assets.json stats.json .assets-stamp`,
because all of those are tracked.

## Editing the Typst preamble

The `docx-mode` block in `paper.typ` is load-bearing for `just docx` and inert on
the PDF path. It exists because Typst's HTML export silently discards the
template's front matter, all section headings, and every equation. If you change
it, verify with `just docx` and confirm the headings and abstract survive, not
just that the command exits 0.

Typst gotcha worth knowing: a method chain broken across lines after `#let x =`
or inside `[...]` ends at the first newline, and the continuation is parsed as
literal text. The error points at a closure parameter and reads
`unknown variable: a`. Wrap the chain in a code block `{ ... }`.

## Python

One environment per concern, both managed by uv. The manuscript toolchain is
`pyproject.toml` at the root; the analysis has its own in `analysis/`. Run things
with `uv run`, never a bare `python3` that picks up whatever is on PATH, and never
`uv run --with X` inline: add the dependency to the right pyproject so the lock
stays honest.

**Every tool lives in `tools/`, not the root.** The root is for what a person
edits and what a build produces. A new checker or metric goes in `tools/` and
gets a `just` recipe; adding one to the root is how this directory got cluttered
the first time.

Each tool sits one level down, so it resolves paths against the manuscript root
with `ROOT = Path(__file__).resolve().parent.parent`, not `.parent`. Copy that
line from an existing one rather than writing `Path(".")`, which works when you
run it by hand from the root and breaks under `just` from anywhere else.

## Scope

Do not restructure the pipeline to fix a one-off problem. The staleness checks,
the generated-table contract, and the docx bypass each exist because a specific
failure happened. Ask before removing one.
