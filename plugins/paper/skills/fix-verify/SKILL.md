---
name: fix-verify
description: Diagnose and fix failing manuscript pipeline checks while preserving author edits, generated-file ownership, and verification rules. Use when verify or a specific check reports a problem.
---

# Fix a failing pipeline check

Work from the manuscript root and follow AGENTS.md/CLAUDE.md. Start with the
reported failure or run `just verify`. Inspect existing changes before editing.
Use `just trace <id> --json` for findings about a statistic or asset. Read its
findings and status, including incomplete, before choosing a fix.

## Choose the fix from the evidence

- **Missing, unknown, stale, or replaced PDF/Word output:** rebuild with the
  named recipe. State lives in `.build-state/`; never edit or copy it to make
  an old output appear current. For a concurrent build or source edit during
  compilation, finish the edit or let the build finish, then retry sequentially.
- **Generated statistic checksum mismatch:** inspect the entry and generator,
  then regenerate with `just assets` once the analysis is correct. This
  preserves author-owned fmt, unit, desc, and expect. Do not restore all of
  stats.json from Git, hand-edit generated values/checksums, or relabel a
  generated value as hand-entered to bypass the finding.
- **Guard violation:** determine whether the calculation is wrong or the
  claim is outdated. Fix the analysis or update the claim and its justified
  expect together, within the user's request. Existing guards live in
  stats.json; generator arguments only seed new entries. Do not relax a guard
  merely because the value fails it. If the scientific intent is unclear,
  identify the decision needed and continue independent fixes.
- **Changed declared inputs:** inspect what changed, then `just assets` to
  regenerate. `just check-stats-deep` re-runs statistics for comparison without
  updating committed values; it is stronger and potentially expensive.
- **Changed pinned file:** inspect the change and its effect on claims before
  `just pin` deliberately accepts it. Pinning does not regenerate analysis.
- **Asset mismatch or missing generator:** repair the generator and regenerate.
  If analysis is permanently gone and preserving the existing output is
  intended, consult `just adopt` and its scope before recording real provenance.
  A temporarily unavailable dependency is not a reason to adopt outputs.
- **Missing provenance or malformed declaration:** repair the specific field
  from real evidence. Do not invent a source or replace the ledger with an
  empty one. Use the four tiers for genuinely hand-entered numbers.
- **Bypassed asset:** use its declared fig()/tbl() ID, preserving its content.
- **Unresolved todo:** address the note before removing its marker.
- **Formatting:** `just fmt`, followed by the extractor tests in verify.
- **Extractor failure:** fix the extractor, add the construct to
  tests/fixture.typ, then `just test-update`; inspect the golden diff.

## Warnings and incomplete checks

Matching digits do not prove two quantities are the same. Use declare-number
when a warning needs a provenance declaration; check the quantity, units,
population, and rendered digits before substituting an ID. Use copy-edit for
wording-only batches, including its before-edit guard.

Address style warnings relevant to the request. Deliberate exceptions belong
in prose-check.toml with a reason, not in checker code. Unavailable data,
uncompleted re-derivation, and an offline required audit mean verification is
incomplete. Resolve the cause when possible; otherwise report it without
claiming success. Trace does not re-run analysis. Ordinary verify does not
include deep statistics or online bibliography checks.

## Finish

Rebuild any stale Word output with its named recipe. Finish with `just paper`
then `just verify`; quote its verdict and exact word count/readability. Rerun
an originally failing deep or online check when it is part of the task. Use
`just preflight` for an actual submission, not every local repair.
