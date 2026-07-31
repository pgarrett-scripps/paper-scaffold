# Working in this directory

Instructions for an agent editing the manuscript. Read [README.md](README.md) for
what the pipeline does and [STYLE.md](STYLE.md) for prose conventions.

## Never do these

**Never hand-edit `si/*.typ`.** Those files are written by `scripts/gen_*.py` and
carry an "AUTO-GENERATED, do not edit by hand" header. An edit survives until the
next `just si-tables` and then vanishes, usually unnoticed. Change the generator
or the data it reads.

**Never hand-edit files under `figures/`.** They are copies, governed by
`figures.map`. Change the plot in the analysis tree and run `just figures`.

**Never type a result into the prose that no generated table or figure backs.**
If a number is worth stating, it is worth being traceable.

**Never delete the `// >>> BODY START` / `// <<< BODY END` markers** in
`paper.typ`. The word counter, the readability report, and the narrator all slice
the prose at them, and each hard-fails without them.

## Before saying the work is done

Run `just check`. It exits non-zero if the committed PDF predates a source
commit, if the Word export or an audiobook is older than what it renders, or if a
figure differs from its upstream copy. "I edited the text" is not done; "`just
check` is clean" is done.

If you changed prose, also run `just paper` so the word count and readability
numbers in your report are current, and quote them rather than estimating.

If you changed inline markup, math, links, or cross-references, run `just test`
and `just fmt-verify`. Those constructs are handled by regexes that a reflow can
break silently, which has happened before (see the `fmt-verify` comment in the
justfile for the three specific cases).

If you taught an extractor to handle a new construct, add a case for it to
`tests/fixture.typ` and regenerate the golden files with `just test-update`,
reading the diff before you commit it. Do not add coverage by putting the
construct in `paper.typ`: that prose is placeholder and gets deleted.

## When adding a table or figure

A table: copy `scripts/gen_example_table.py`, keep the filename pattern
`gen_*.py` so `just si-tables` picks it up with no wiring, emit a bare
`#table(...)` with the auto-generated header and no caption or label, then wrap it
in a `#figure` in `si-body.typ` where the caption and label live.

A figure: have the analysis write it, add a `dest source` row to `figures.map`,
run `just figures`. Set `metadata={"Software": None}` and seed any RNG in the
generator, or every regeneration churns the PNG bytes and `just check` reports
drift that is not real.

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

## Scope

Do not restructure the pipeline to fix a one-off problem. The staleness checks,
the generated-table contract, and the docx bypass each exist because a specific
failure happened. Ask before removing one.
