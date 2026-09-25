---
name: declare-number
description: Connect a manuscript number to a computed statistic, documented hand entry, inline literal, or justified exception. Use when adding a number or resolving numerical provenance warnings.
---

# Declare a manuscript number

Work from the manuscript root and follow AGENTS.md/CLAUDE.md. Scope this to
the numbers the user names or the numerical warnings being fixed. Inspect
stats.json and use `just trace <id> --json` for candidate existing entries.
Matching digits alone do not establish identity: check quantity, units,
population, and context. Reuse the right existing ID rather than duplicate it.

When converting an existing literal without changing its meaning, run
`just paper` then `just text-baseline` before editing. Preserve displayed
numbers, units, and punctuation. Adding a requested result intentionally
changes the text and does not require an unchanged-text comparison. The
wording-only edit guard is unsuitable for intentional declaration changes.

## Open review actions

Before editing, run `just check-actions --open` (silent when there is no
`reviews/ACTIONS.md`; a paper on a scaffold older than 3.24.0 has no recipe,
so read the file directly). Tell the user which open rows bear on this task:
rows whose `fix` is `/paper:declare-number`, and rows about the numbers and
statistic ids in scope. Work on the rows the user asks for; do not widen the
task to clear the list.

## Choose the appropriate tier

1. **Computed result:** use real analysis and its inputs. Add a new entry
   through gen_stats.py with `st.add(...)`, and declare the data read in
   `st.write(inputs=[...])`. Seed fmt, desc, unit, and justified sign/range
   guards for a new ID. Run `just assets`. Never turn a prose literal into a
   generator constant and call that a reproducible calculation.
2. **Externally sourced number:** when no project script computes it, add a
   hand entry to stats.json with value, fmt, origin.by = "hand", and an
   origin.note identifying the actual source and location. Include unit,
   desc, and expect where useful. Reference it with `#s("id")`.
3. **Deliberate prose literal:** use `#lit("40")` with the original digits.
   This vouches only for that occurrence and only suppresses unaccounted-number.
   It cannot suppress derivable-number. If a computed result shares the digits
   but represents another quantity, investigate the collision rather than
   assigning the wrong statistic.
4. **Global value exception:** use prose-check.toml with a written reason only
   when justified across the manuscript. Prefer a local declaration when other
   occurrences of the same digits still need checking.

For an existing computed entry, the generator owns value, checksum, and origin.
Edit fmt, unit, desc, and expect in stats.json; changing generator seeds will
not update them. Trace's display field shows the formatted statistic. Inspect
all affected uses before changing a shared format or guard.

For a literal conversion, compare that display and surrounding prose with the
original. Do not silently substitute different digits. If the user already
requested a numerical correction, make and report it; otherwise explain the
discrepancy and obtain the missing author decision. Do not invent data or
provenance when the source is unavailable.

## Validate

Run `just fmt`, `just paper`, and `just prose-check`. For a conversion that
should preserve the text, also run `just text-diff` and inspect its output;
unchanged word counts alone cannot establish unchanged wording. If generated
analysis changed, run `just check-stats-deep` to check re-derivation.

Rebuild any other deliverable named stale, then finish with `just paper` and
`just verify`. Report the ID or literal/exception chosen, deliberate display
changes, check results, and exact word count/readability. If a comparison or
re-derivation could not run, report that limit explicitly.

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
