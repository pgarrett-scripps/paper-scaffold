---
name: fix-verify
description: Take a failing `just verify` (or any pipeline check) and fix each finding the way this pipeline intends — never by weakening a check, editing a generated file, or silencing without a written reason.
---

# Fix a failing gate

Run `just verify` (or start from output the user pasted) and clear it. Every
finding class has one intended fix; applying a different one usually creates
the next failure. Work through errors first, then triage warnings.

## The fix table

| Finding | The intended fix | Never |
|---|---|---|
| `STALE: paper.pdf/docx` | `just paper` / `just docx` | edit `.build-stamp` |
| `REPLACED: ... not the file that build produced` | rebuild; if deliberate restoration, rebuild anyway — the stamp follows builds | copy stamps around |
| checksum mismatch on a stats value | the value was hand-edited: `git checkout stats.json`, then change the ANALYSIS and `just assets` — or take it over honestly with `origin.by="hand"` + note | keep the edited value |
| guard (`expect`) violated | either the analysis changed meaning (fix it) or the sentence's assumption is stale (reword the sentence AND update `expect` in stats.json) | delete the guard to pass |
| `sources ... has changed` | `just assets` (or `just check-stats-deep` to see which values move) | re-pin blindly |
| pinned file changed | check the numbers that depend on it, then `just pin` to accept | `just pin` without looking |
| asset hash changed / unclaimed file | generated: fix the generator, `just assets`. No generator exists: `just adopt note="..."` | hand-edit files in `figures/` or `si/` |
| `bypassed-asset` | reference by id: `fig("...")`/`tbl("...")` | keep the filename path |
| hand entry with no note | write the real provenance into `origin.note` | invent a note |
| `unresolved-todo` | resolve the note, then delete the call | delete the call unresolved |
| fmt-check | `just fmt`, then `just test` still passes | reflow by hand |
| extractor test failure | teach the extractor in `tools/typst_prose.py`, add a fixture case, `just test-update`, READ the golden diff | edit golden files directly |

## Warnings are triage, not chores

- `derivable-number`: replace the typed numeral with `#s("id")` **only if the
  rendered string is identical**; otherwise flag it to the user — swapping
  changes the paper.
- `unaccounted-number`: four tiers, weakest to strongest claim — `#lit("x")`
  for deliberate prose, hand entry with note if it deserves an audit trail,
  `gen_stats.py` if the analysis computes it, `prose-check.toml` with a
  written reason for a global exception.
- Style warnings (long-sentence, verbosity, repetition): fix the prose or
  leave them standing; suppress in `prose-check.toml` only with a reason a
  reviewer would accept, **never by editing `tools/prose_check.py`**.

## Rules of engagement

Read the comment above any recipe or check before overriding it — every one
exists because a specific failure happened; HISTORY.md's "Decisions reversed"
lists the obvious ideas that were tried and were wrong. If the intended fix
requires something unavailable (the analysis data is gone, a tool is
missing), say exactly that rather than substituting a workaround that fakes
green. Done means `just verify` exits clean and you quote its final line.
