---
name: copy-edit
description: A wording-only editing pass (grammar, tightening, de-hedging) over the manuscript or a named section, proven safe by the edit guard — numbers, references, floats and headings must survive exactly.
---

# Copy-edit pass

A wording-only pass over the prose. The user may name a scope ("the
Discussion", "si-body.typ", "the whole paper") and an emphasis ("grammar",
"tighten", "de-hedge", "shorten by ~10%"); with no scope, do the main text
body. This skill exists because wording passes are where numbers get silently
mangled, so the pass is bracketed by the guard that makes that impossible.

## The bracket — never skip either end

```bash
just edit-baseline      # BEFORE touching anything
# ... the editing pass ...
just edit-check         # proves only wording changed
just fmt && just paper && just verify
```

If `edit-check` reports FATAL, do not rationalize it: find the edit that
invented or altered the token and revert that edit. A number may be DROPPED
(it reports as a note; STYLE.md permits thinning) — never changed, never
introduced.

## Hard constraints during the pass

- **Never edit a number**, including inside `#lit("...")` — the vouched string
  is the author's exact digits. Never convert between `#s()`, `#lit()` and
  bare numerals; that is `/declare-number`'s job, not a copy-edit.
- **Never touch** `#s()`/`#n()` calls, `fig()`/`tbl()` ids, `@citations`,
  `#refn(<...>)` targets, labels `<sec:x>`, or headings. Reordering a sentence
  around a citation is fine; the citation itself moves with its claim.
- **Edit only hand-written sources** (`paper.typ`, `si-body.typ`, and files
  listed in `typst_sources`). Nothing under `si/` or `figures/`.
- Keep edits inside the `// >>> BODY START` / `// <<< BODY END` markers unless
  the user names front/back matter explicitly.

## What the pass actually does

Apply STYLE.md. The mechanical layer (`just prose-check`) already catches em
dashes, British spellings, doubled words and misspellings — fix any it
reports, then do what it cannot: cut filler, split run-ons (the report flags
sentences past 40 words), collapse double hedges, prefer verbs over
nominalizations, keep one idea per sentence. `just density` names the
sections that depart from the paper's own norms — start there when the user
gives no scope.

## Report when done

Quote, never estimate: the `edit-check` verdict, the word count and
readability lines `just paper` printed (before and after), and one or two
representative sentence-level diffs so the user can judge the register. If
readability moved the wrong way, say so plainly.
