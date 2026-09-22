---
name: claim-audit
description: Check every quantitative claim in the manuscript against the computation behind it, using stats.json, trace, and the analysis code. Use to find overstated, unguarded, or unsupported claims before review or submission. Read-only.
context: fork
agent: general-purpose
model: opus
---

# Audit the manuscript's claims against their evidence

Work from the manuscript root and follow AGENTS.md/CLAUDE.md and STYLE.md
("Scientific terms and concrete claims", "Claims"). This skill is read-only:
it never edits prose, stats.json, or the analysis. It writes one findings
file and routes each fix to the skill that owns it.

Scope defaults to the abstract (config.typ) and every section between the
BODY markers in paper.typ. The user may narrow it to a section, a file such
as si-body.typ, or a list of statistic ids.

## Build the claim ledger

1. Read the source, not the PDF. Read paper.typ and config.typ directly. If
   `just check-build` reports the build current, also read paper.resolved.typ
   for the sentences with numbers filled in; otherwise use
   `just trace <id> --json` for each displayed value. Do not rebuild in order
   to read a sentence.
2. Extract every sentence that makes a claim a reader could test: a number,
   a direction ("increased", "fell", "improved"), a comparison ("higher
   than", "comparable to", "no difference"), a strength word
   ("significantly", "robust", "consistent"), or a scope ("across all
   conditions", "in every replicate"). One ledger row per claim, with
   `file:line`, the sentence, and the `#s()` / `#fig()` / `#tbl()` ids it
   rests on. A claim with no id and no citation is a row too.
3. For each id, run `just trace <id> --json` and open the generator named in
   `origin.by`. Read the code path that produces the value: the population it
   is computed over, the filter applied before it, the denominator, the test
   or estimator, the units, and whether the number is a point estimate, a
   mean, a median, or a count.

## Judge each claim

Give each row one verdict:

- **supported**: the sentence's verb, scope, and strength match what the code
  computes and the value's `expect` guard already encodes the assumption.
- **unguarded**: supported today, but the prose assumes something the guard
  does not check (a sign, a bound, a ranking). Propose the exact `expect`
  to add. Existing guards are edited in stats.json, not in gen_stats.py.
- **overstated**: the evidence is weaker than the wording. Typical cases:
  "significantly" with no test, or a test on a different quantity;
  "increased" for a near-tie whose interval includes the null; a mean
  described as if every replicate moved; a mechanism asserted for an
  observation; a scope wider than the population the code filtered to.
- **mismatched**: the sentence describes a different quantity from the one
  the id computes (a fold change read as a difference, intensity read as
  abundance, a per-run number read as per-sample).
- **unverifiable**: the value is hand-entered without a note that supports
  it, the generator is missing, the data it reads is absent, or the claim
  carries no id and no citation. Say what would make it verifiable.

Matching digits do not establish identity. Check quantity, units, population,
and filter before calling a claim supported. Trace does not re-run analysis;
if a verdict depends on a value being current, say that
`just check-stats-deep` was not run, do not run it unasked.

Read the paragraph around each overstated or mismatched claim: the fix is
often a scope phrase, not a deletion.

## Report

Write `reviews/<YYYY-MM-DD>-claim-audit.md` (create the directory; it is
the author's to commit or ignore). Shape:

1. A one-paragraph verdict: how many claims, how many in each category,
   and the two or three findings that matter most.
2. The ledger as a table: severity (blocker / major / minor), location,
   claim, id(s), what the code computes, verdict, and the routed fix.
3. Proposed guards as a ready-to-apply list of stats.json `expect` edits.

Route every fix to an existing owner: wording to `/copy-edit`, a number with
no declaration to `/declare-number`, a guard or checksum problem to
`/fix-verify`, a wrong computation to "analysis change", and an ambiguity
only the author can resolve to "author decision" with the question stated.
Do not apply any of them in this pass.

Finish by printing the verdict paragraph and the file path. Do not run
`just paper` or `just verify`; nothing was edited.
