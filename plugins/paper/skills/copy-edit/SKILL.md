---
name: copy-edit
description: Tighten or polish manuscript wording directly in Typst, preserving scientific terminology, numbers, citations, and structure. Use for wording-only edits, not new results, structural rewrites, or PDF layout review.
---

# Copy-edit manuscript wording

Work from the manuscript root and follow AGENTS.md/CLAUDE.md and STYLE.md.
Edit the section the user names, including the abstract in config.typ when
requested. With no named scope, edit the main text between the body markers.
Follow literal includes when the requested section lives in another file.
Use source text and current resolved Typst for review, following the reading
workflow in AGENTS.md/CLAUDE.md. Do not invoke PDF or image-viewing skills for
ordinary copy-editing.

## Open review actions

Before editing, run `just check-actions --open` (silent when there is no
`reviews/ACTIONS.md`; a paper on a scaffold older than 3.24.0 has no recipe,
so read the file directly). Tell the user which open rows bear on this task:
rows whose `fix` is `/paper:copy-edit`, and rows about the sentences and
sections in scope. Work on the rows the user asks for; do not widen the task
to clear the list.

## Before editing

Inspect existing changes so you can preserve work already in progress. Run
`just wordcount` and `just readability` for before-edit metrics without a PDF
build, then `just edit-baseline` before changing prose. A separate pass can use a tag:
`just edit-baseline short-results` and `just edit-check short-results`.
When resuming a pass, keep its original baseline; do not replace it to erase
failures. An old snapshot format needs a new baseline before a new pass.

## Make the requested edits

Apply the requested emphasis and STYLE.md. Keep scientific meaning,
qualifications, comparisons, and the association between claims and citations.
Use `just trace <id> --json` when a statistic or asset needs explanation;
trace checks recorded consistency, not the science.

- Edit hand-written prose only. Keep generated tables and figures untouched.
- Preserve headings, labels, body markers, floats, citation occurrences, and
  asset IDs. Move a citation with its sentence, not to a different claim.
- Keep a citation key exactly as written, prefix included. In `si-body.typ`
  citations read `@si-key`, which is what puts them in the SI's own reference
  list; dropping the prefix moves the work to the main text's list silently.
- Preserve retained numbers and s()/n() IDs. STYLE.md permits dropping a
  redundant numeric statement, but not introducing or substituting one.
  Do not change between s(), n(), lit(), and typed numerals in this workflow.
- Keep stats.json and assets.json declarations unchanged. A request to revise
  results or restructure sections is broader than wording-only editing; use
  the appropriate workflow rather than weakening the guard.
- Preserve defined scientific terms and the quantity they name. Apply
  STYLE.md's "Scientific terms and concrete claims" review: replace vague
  claims with supported specifics, never with invented jargon or mechanisms.
  Keep coherent paragraphs and remove redundant explanations nearby.

## Check the result

```bash
just fmt
just edit-check
just paper
just verify
```

Use the same tag for edit-check if the baseline was tagged. In a revision round
(answering reviewers), `just edit-check <tag> --revision` accepts new `#s()`
ids, citations, floats and headings but still fails on a typed numeral. On failure,
inspect the offending changes and correct your edits while preserving user
work. Never reset whole files or re-baseline just to obtain a pass.

The guard checks mechanical invariants. Read the edited sentences and their
context in the refreshed paper.resolved.typ for meaning even when it passes.
Check terminology, claim scope, and uncertainty against the source. Do not
render page images or open the PDF for this wording-only workflow. If verify
names another stale deliverable, rebuild it with the named recipe and rerun
the gate. Report checks that could not run as incomplete, with their cause.

Once these checks pass and the text review is complete, stop. Further builds
require a new edit or a specific failure to resolve.

Report the edit-check verdict, exact before/after word counts and readability,
and a representative sentence change. Do not estimate missing baseline metrics.

## Close the review actions this fixed

For each ledger row this edit actually fixed, and that the checks above
confirm, edit its row in `reviews/ACTIONS.md`: `status` to `done`, `closed`
to the short hash of the commit that contains the fix. This skill does not
commit unless asked, so until then write `uncommitted: <what changed>`. The
commit that lands the fix carries a `Closes: A-0012` line (several:
`Closes: A-0012, A-0013`) in its message; `just close-actions` then writes
that commit's hash into each named row, and `just check-actions` fails when
a recorded hash disagrees with the commit that says it closes the row. Leave a row open when the fix is partial, and say which part
remains in the report. Run `just check-actions` after editing the ledger
and report the ids closed.
