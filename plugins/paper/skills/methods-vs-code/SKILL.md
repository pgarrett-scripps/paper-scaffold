---
name: methods-vs-code
description: Compare the methods section, parameter by parameter, against what the analysis code actually does. Use to catch methods drift (thresholds, filters, software versions, seeds, normalization) before review or submission. Read-only.
context: fork
agent: general-purpose
model: opus
---

# Check the methods against the analysis code

Work from the manuscript root and follow AGENTS.md/CLAUDE.md. This skill is
read-only: it never edits prose or code. The code in `analysis/` is the
ground truth for what was done; the methods section is the claim about it.
Where they disagree, report which one is wrong only if the evidence says so;
otherwise report the disagreement and ask.

Scope defaults to the Methods section of paper.typ plus any methods material
in si-body.typ. The user may narrow it to one subsection or one script.

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

## Build the parameter table from the prose

Read the methods source directly. Extract every statement that names a
concrete procedural choice, one row each with `file:line`:

- thresholds and cutoffs (FDR, q-value, score, fold change, minimum
  observations, missingness)
- filters and exclusions, and the order they are applied in
- normalization, transformation, imputation, and batch handling
- the statistical test or model, its sidedness, correction, and grouping
- software, package, and database names with versions and settings
- random seeds, replicate counts, and what "n" refers to
- input files, accessions, and instrument or acquisition settings the
  analysis depends on

A step the prose describes in words with no parameter is still a row; the
question is then whether the code performs that step at all.

## Build the same table from the code

Read every script under `analysis/scripts/` that `assets.json` or
`stats.json` names in an `origin.by`, plus the modules they import, plus
`analysis/pyproject.toml` and `analysis/uv.lock` for versions, and
`evidence.toml` (when present) for the software versions and configs behind
each result set; `just impact TOOL` lists the ids a version touches. Record the
actual value or behavior for each row: the literal in the code, the default
of the library call when the code passes nothing, and the order of
operations. Note a parameter the code sets that the prose never mentions.

Do not run the analysis. Do not treat a comment or docstring in the code as
what the code does; read the call.

## Compare

One verdict per row:

- **matches**: same value, same order, same scope.
- **drift**: different value, or a step present on one side only. Quote both
  sides. If the git history of the script shows the code changed after the
  prose was written, say so; otherwise do not guess which side is stale.
- **silent default**: the prose states a value the code never sets, and the
  library default happens to match or not. Name the library and the default.
- **unstated**: the code makes a choice the methods do not mention that a
  reader would need to reproduce the result (a filter, a seed, a version).
- **unverifiable**: the data or a dependency is absent, or the step lives in
  code outside `analysis/`. Say where.

Where a row's value also appears as a `#s()` id, prefer the id in the prose
and say so; a typed threshold that the code also holds is a `/paper:declare-number`
case.

## Report

Write `reviews/<YYYY-MM-DD>-methods-vs-code.md` (create the directory). Shape:

1. A one-paragraph verdict with the count in each category and the drifts
   that would change a result if the prose were right.
2. The comparison table: severity (blocker / major / minor), location in
   prose, location in code, prose says, code does, verdict, routed fix.
3. Unstated choices as a list the author can paste into the methods once
   confirmed.

Route fixes to `/paper:copy-edit` (wording), `/paper:declare-number` (a typed
parameter the code holds), "analysis change" (the code is wrong), or
"author decision" (which side is right is a scientific call). Apply none of
them here. Finish by printing the verdict paragraph and the file path.

## Update the action ledger

After writing the findings file, and before the final print:

1. Every comparison row whose verdict is not **matches**
   becomes one action; the unstated-choices list is one action per choice.
2. Skip a finding that matches an `open` or `wontfix` row. Reopen a matching
   `done` row whose problem is back: `status` to `open`, `closed` to
   `reopened <YYYY-MM-DD>: <what came back>`.
3. Append each remaining finding as a row: the next id (`just check-actions`
   prints it), its severity, `open`, source
   `<YYYY-MM-DD>-methods-vs-code.md#<ref>` naming the finding, a one-line summary,
   the routed fix as `fix`, and an empty `closed`.
4. Run `just check-actions` and repair any format error in the rows you
   wrote. Print the ids you added or reopened with the verdict.

When `/paper:review-all` launched this review (its prompt says so), skip
this section: review-all merges every review into the ledger once, after all
of them finish, so parallel reviews never write the file at the same time.
