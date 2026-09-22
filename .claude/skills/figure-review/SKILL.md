---
name: figure-review
description: Check each figure and table against its caption, the sentences that cite it, and the statistics it should match. Use for a visual pass over figures before review or submission, or when a figure is suspected of disagreeing with the text. Read-only.
context: fork
agent: general-purpose
model: opus
---

# Review figures and tables against the text

Work from the manuscript root and follow AGENTS.md/CLAUDE.md. This skill is
read-only: it never edits prose, generators, or files under `figures/` or
`si/`. It is the one review pass that is allowed to look at images, because
the question is whether the picture shows what the text says it shows.

Scope defaults to every `#fig()` and `#tbl()` id in `assets.json` that the
main text or SI cites. The user may name one or more ids.

## Gather, per asset

1. `just trace <id> --json` for the path, generator, declared inputs, and
   every citing sentence with its `file:line`.
2. The caption, from the `#figure(...)` block in paper.typ or si-body.typ.
3. Every sentence in the prose that cites the label, from the trace `uses`.
4. The rendered file. For a figure, view the PNG or SVG directly. For a
   generated table, read the `si/*.typ` file; do not rasterize the PDF for
   this unless a layout defect is the question.
5. The generator script, to know what the plot actually encodes: which
   column is on which axis, what the error bars are, what was filtered out,
   and whether the RNG is seeded.

## Check

For each asset, answer each of these and record the evidence:

- **Axes and units.** Every axis is labeled with a quantity and a unit, and
  the quantity name is the one the manuscript uses (see STYLE.md: intensity
  stays intensity). Log scales are stated. Tick ranges do not hide a
  comparison the text makes.
- **Legend and panels.** Every series in the legend is described in the
  caption; every panel letter the prose cites exists; no panel is left
  undescribed.
- **Caption vs image.** The caption's description of what is plotted, the
  error bars, the n, and the conditions match the generator and the picture.
- **Prose vs image.** Each citing sentence's claim is visible in the figure:
  the direction, the ordering of conditions, the rough magnitude. A sentence
  that cites the figure for something it does not show is a finding.
- **Numbers.** Where the prose gives a value from the same data (a `#s()` id
  from the same inputs), the figure agrees to the precision shown. Read the
  value with trace; do not estimate it from pixels and call that a match.
- **Journal profile.** Read `journal.toml` and its `journals/<profile>.toml`:
  figure count against `figures-max`, printed resolution against `min-dpi`
  for rasters, and the graphical abstract against its box. `just check-journal`
  already reports these; quote it rather than re-deriving.
- **Reproducibility of the file.** The generator seeds its RNG and sets
  `metadata={"Software": None}`; `just check-assets` is clean for this id.

## Report

Write `reviews/<YYYY-MM-DD>-figure-review.md` (create the directory). Shape:

1. A one-paragraph verdict: assets reviewed, how many clean, and the
   findings that would mislead a reader.
2. One block per asset with a finding: id, severity (blocker / major /
   minor), what the text says, what the figure shows, evidence, routed fix.
3. Assets with no findings as a single list.

Route fixes to `/copy-edit` (caption or citing sentence), `/new-figure` or
"generator change" (the plot itself), `/declare-number` (a value in a
caption typed by hand), or "author decision". Apply none of them here.
Finish by printing the verdict paragraph and the file path. Nothing was
edited, so do not run `just paper` or `just verify`.
