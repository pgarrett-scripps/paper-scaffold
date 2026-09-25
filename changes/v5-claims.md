# v5-claims: claims held to the numbers

## What changed

- **Uncertainty fields.** `st.add(..., lo=, hi=, level=, n=, sd=, se=)` writes script-owned fields next to the value, checked for consistency by `just assets` and `just check-stats`; an entry with any of them gets a `v3:` checksum covering value and interval (entries without them keep `v2:`).
- **`#ci("id")`** prints an interval (`1.71–2.49`, or `95% CI 1.71–2.49` with `level: true`) from the entry's own lo/hi and fmt, or from existing sibling ids `x.lo`/`x.hi` (`x_lo`/`x_hi`). Resolved identically by Typst, the word count, narration and Word export; `stats-rendered.json` gains an `intervals` table.
- **`expect` relations.** `gt`/`ge`/`lt`/`le` (an id or list) and `ratio_to`/`diff_to` (`{"id", "min", "max"}`, seeded from `(id, min, max)`) replace hand-derived ratio ids; broken or dangling relations are errors in `just assets` and `just check-stats`.
- **`measurement`** (author-owned: `single-run`, `replicated`, `exclusive`) and the `single-run-timing` rule on timing sentences that read a single-run value.
- **Wording rules** in prose-check: `bound-rounding` ("below #s(x)" where rounding put the shown number on the wrong side), `interval-wording` ("excludes zero" that the interval's ends contradict).
- **`#lit(v, unlike: "id")`** (or a tuple of ids): a named vouch that clears `derivable-number` only for the ids it names; `stale-vouch` warns when a named id is gone or no longer collides. The prose-check footer counts plain and named vouches separately. (`not:` from the design was renamed `unlike:` because `not` is a Typst keyword.)
- **`claims.toml`** registry: `[[claim]] id, phrase, retired = [...], note`; `retired-claim` fails on a retired wording in paper, abstract, SI, cover letter, `[sources] typst` and manuscript.toml parts.
- **Cover letter** (`cover-letter.typ`) now gets the sentence rules, `derivable-number`, `unaccounted-number` and the claim rules, letterhead stripped; capped at warnings by default (`[prose] cover_letter = "warn" | "error" | "off"`).
- **Shared vocabularies.** `[prose] vocab = ["proteomics", "prose/lab.toml"]` merges add-only `[allow]` / `[vocabulary.*] add` lists; ships `vocab/proteomics.toml`.
- **`[[software]]`** pins (`name`, `repo`, `ref`, `docs`, `note`) in project.toml; `/paper:methods-vs-code` compares the Methods against that release's code and docs at `ref`. `/paper:declare-number` and `/paper:claim-audit` know the new fields, relations and `claims.toml`.

## Upgrade:

- Run `uv run paper sync`: `stats.typ` gains `ci()` and `lit(..., unlike:)`, `wordcount.typ` evaluates `ci`. Add `ci` to the `#import "stats.typ": ...` line of any file that uses it.
- Nothing is required otherwise. New prose rules (`bound-rounding`, `interval-wording`, `single-run-timing`, `stale-vouch`) are warnings; expect some `bound-rounding` warnings on existing papers (about a dozen across the surveyed papers, all genuine rounding) — fix with a fmt edit or "about", or disable in `prose-check.toml`.
- May fail on existing papers: a `cover-letter.typ` is now checked (warnings only unless `cover_letter = "error"`); `retired-claim` is an error, but only once a paper writes `claims.toml`; relation and uncertainty checks are errors, but only for fields a paper declares.
- Optional: move sibling `x.lo`/`x.hi` ids to `st.add(lo=, hi=)` and write `#ci("x")`; move hand-derived ratio/difference guard ids to `expect` relations; mark timing values with `measurement`.
