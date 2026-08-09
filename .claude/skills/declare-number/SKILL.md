---
name: declare-number
description: Take a number typed in the prose (or about to be) and route it through the right tier — computed #s(), hand entry with a note, inline #lit() vouch, or a toml exception — then make the edit and prove nothing rendered differently.
---

# Declare a number properly

Input: one or more numerals the user names, or the current
`unaccounted-number` / `derivable-number` warnings from `just prose-check`.
For each, decide the tier by asking the questions IN THIS ORDER — each tier is
a stronger claim than the one below it, and a number takes the strongest tier
it can honestly hold.

## The decision ladder

1. **Does the analysis compute it (or could `gen_stats.py` derive it from
   data that exists)?** → Declare it in `analysis/scripts/gen_stats.py` with
   `st.add("group.name", value, fmt=..., desc=...)`, seed a guard for whatever
   the sentence assumes (`sign=`, `between=`), run `just assets`, and replace
   the typed numeral with `#s("group.name")`.
   **Check the rendering first**: the declared display (`value` + `fmt`) must
   equal the typed string exactly, or the swap changes the paper — if it
   differs, tell the user which digits would change and let them choose.

2. **No script can compute it, but it deserves an audit trail** (a protocol
   figure, a vendor spec, a value from a cited paper)? → Add a hand entry to
   `stats.json`: `value`, `fmt`, `origin.by = "hand"`, and an `origin.note`
   naming the actual source ("Bruker timsTOF spec sheet", "protocol v3,
   Table 1"). Guard it if the prose assumes a direction or range. Reference
   it as `#s("id")`.

3. **It is deliberate prose** — a temperature, a fold-range, a count nobody
   computed? → Wrap it where it stands: `#lit("40")`. String argument, exact
   digits as typed. This silences `unaccounted-number` at that spot only and
   never silences `derivable-number` — if the wrapped value matches a
   declared one, tier 1 was the right answer.

4. **A value that recurs legitimately everywhere** (a year-like code, an
   instrument model number)? → `[allow].unaccounted-number` in
   `prose-check.toml`, with a comment giving the reason.

## Prove it

`just render-stats && just paper` must build; the printed word count must not
move for tier-3 wraps; `just prose-check` must show the warning gone (and the
vouched-inline count up by exactly the wraps made); `just verify` clean. For
tier 1–2, quote the new stats.json entry back to the user. If several numbers
were routed, report the tier chosen per number in one table.
