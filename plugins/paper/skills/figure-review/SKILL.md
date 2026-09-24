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

## Read the action ledger first

`reviews/ACTIONS.md` records every finding earlier reviews raised and whether
it was fixed; its header states the rules. Read it before reviewing. If it is
missing, create it with `just check-actions --init` (a paper on a scaffold
older than 3.24.0 has no such recipe: write a file whose table header is
`| id | severity | status | source | summary | fix | closed |` with a
`|---|---|---|---|---|---|---|` separator under it). A problem that matches an
`open`, `done` or `wontfix` row is not a new finding: cite the existing id in
the findings file instead of raising it again. A `done` row whose problem is
back in the current text is reopened, not duplicated. Appending to the ledger
is the only write this skill makes outside its findings file; it still never
edits the manuscript.

## Gather, per asset

1. `just trace <id> --json` for the path, generator, declared inputs, and
   every citing sentence with its `file:line`.
2. The caption and every citing sentence, from `paper.review.txt` (run
   `just review-text` first unless the caller says it is current). The copy
   has captions numbered and numbers resolved, so this is one read for all
   assets instead of a source read per `#figure(...)` block. Use the trace
   `uses` for the `file:line` of each citing sentence; open paper.typ or
   si-body.typ only when a finding needs the exact source line quoted.
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
- **What the figure is for.** Each panel answers one question, and the
  caption states it and gives the answer as a number. A panel that explains
  a mechanism starts from a small annotated toy example before real data.
  Every phenomenon the text names (an artifact the method removes, say) is
  pictured somewhere. The plot type suits the data: dense 2D data in a
  heatmap, not an overplotted scatter; a structural gap not drawn as empty
  space. Compared conditions share axes and scales, and the baseline sits in
  the same panel. Where the text says "preserved" or "within", the tolerance
  band or pass/fail line is drawn. Replicates and spread are shown, not only
  means. The reasons are in the figure checklist of
  `.paper/docs/reviewer-lessons.md` (`docs/` in the scaffold itself); a
  missing schematic or panel is routed to `/paper:new-figure`.
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

Route fixes to `/paper:copy-edit` (caption or citing sentence), `/paper:new-figure` or
"generator change" (the plot itself), `/paper:declare-number` (a value in a
caption typed by hand), or "author decision". Apply none of them here.
Finish by printing the verdict paragraph and the file path. Nothing was
edited, so do not run `just paper` or `just verify`.

## Update the action ledger

After writing the findings file, and before the final print:

1. Every finding in the per-asset blocks becomes one action.
   Clean assets add nothing.
2. Skip a finding that matches an `open` or `wontfix` row. Reopen a matching
   `done` row whose problem is back: `status` to `open`, `closed` to
   `reopened <YYYY-MM-DD>: <what came back>`.
3. Append each remaining finding as a row: the next id (`just check-actions`
   prints it), its severity, `open`, source
   `<YYYY-MM-DD>-figure-review.md#<ref>` naming the finding, a one-line summary,
   the routed fix as `fix`, and an empty `closed`.
4. Run `just check-actions` and repair any format error in the rows you
   wrote. Print the ids you added or reopened with the verdict.

When `/paper:review-all` launched this review (its prompt says so), skip
this section: review-all merges every review into the ledger once, after all
of them finish, so parallel reviews never write the file at the same time.
