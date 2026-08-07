# Migrating an existing manuscript onto this scaffold

`scripts/new-paper.sh` starts a paper from zero. This guide is for the other
case: a manuscript that already exists — prose written, figures committed,
possibly submitted once — moving onto the scaffold's tooling. It was written
by watching a real migration and collecting what it hit; the traps at the
bottom were each found the expensive way.

The work is inherently manual. A manuscript diverges from any scaffold the
moment real writing starts, so there is no script for this and deliberately
will not be — but the order below keeps every phase verifiable, and the
invariant keeps the paper itself safe while the machinery changes around it.

## The invariant: the paper must not change

Before touching anything, build the current PDF and snapshot its extracted
text. Once the scaffold's justfile is in place (phase 1), that is:

```bash
just text-baseline        # snapshot paper.pdf's words
just text-diff            # after each phase: word-level diff against it
```

Before phase 1, do the same by hand: `pdftotext paper.pdf baseline.txt` from
whatever the old build produces, then `git diff --word-diff --no-index`
against a fresh extraction.

At every phase boundary, rebuild and `just text-diff`. The extracted text must
be unchanged except for edits you chose to make — the diff is word-level
precisely because a reflow rewraps every line, and a line diff would report
the whole paper changed. This is the one check that catches a migration
silently eating a sentence, and it costs a minute per phase. When every change
shown is one you chose, `just text-baseline` again to accept the new state.

Also record the old word count. It will move (see trap 3), and you want to
know that the move is a definition change, not lost prose.

## Decisions to make before editing

Three questions shape the whole migration; answer them first.

**Where does the analysis live?** If it can move, move it inside the
manuscript as `analysis/`. This is load-bearing, not tidiness: the provenance
machinery resolves the manuscript root as `analysis/scripts/../..`, and the
code-input walk keeps exactly the modules under `analysis/`. A sibling
analysis repository means forking three tools instead of re-pointing a path.

**Can the analysis still run — is the data actually present?** Check before
planning, because the answer splits the asset phase in two (re-generate vs
adopt), and people are routinely wrong about it in the optimistic direction.

**Wholesale or file-by-file?** Copying the scaffold's files wholesale and
re-applying the project's specifics on top is usually right for the toolchain
(`tools/`, `justfile`, `tests/`, `pyproject.toml` + `uv.lock`), which the
project should not have diverged from meaningfully. The manuscript files
(`paper.typ`, `config.typ`, `si-body.typ`) go the other way: keep the
project's, wire in the scaffold's imports and markers.

## Keep the earned specifics

The scaffold ships placeholders; the project has scars. Anything that exists
because a specific failure happened wins over the scaffold's default:

- `prose-check.toml` exceptions, each with its reason
- extra `.typ` files (response letters, cover letters, shared macros)
- test-fixture cases added for constructs the project actually uses
- audio pronunciation and math maps
- any `just` recipe with a comment explaining a failure

Port these into the new files. Dropping them re-arms every trap they were
built to disarm.

## The phases

Each phase ends with a build and a diff against the baseline.

**1. Toolchain.** Copy `tools/`, `justfile`, `tests/`, `pyproject.toml`,
`uv.lock`, `CLAUDE.md`, `HISTORY.md` (start a fresh "migrated onto
paper-scaffold X.Y.Z" entry), `.gitignore`. `just doctor`, then `just setup`.
Nothing manuscript-facing has changed yet; the old build should still work.

**2. Manuscript wiring.** Bring the project's prose into the scaffold's
structure: `config.typ` for identity and abstract, the `// >>> BODY START` /
`// <<< BODY END` markers around the main text, `#import "stats.typ": s, n`
and `#import "assets.typ": fig, tbl` in `paper.typ` **and in `si-body.typ`**
(trap 2). `just paper` must build; the extracted text must match the baseline.

**3. Assets.** Two routes, per figure:

- *Analysis runs:* move it under `analysis/`, add a `record(...)` call per
  output (copy `gen_example_figure.py`'s shape), `just assets`. The manifest
  now knows what made each file and from what.
- *Analysis gone:* `just adopt note="where these files actually came from"`.
  The hash and reference checks apply; regeneration is honestly absent and
  the checks say so. If the analysis is ever restored, its `record()` call
  takes the id back.

Then replace every direct `#image("figures/...")` / `#include "si/..."` with
`fig("...")` / `tbl("...")` — `just prose-check` reports the ones you miss.

**4. Numbers.** Every number stated in a sentence, one of three ways: the
analysis computes it → declare in `gen_stats.py`, read back as `#s("id")`; no
script can → a hand entry in `stats.json` with `origin.by = "hand"` and a
note; genuinely just prose → leave it, and suppress the warning with a
comment when it appears. Guard what the sentences assume (`sign`, bounds) —
migration is exactly when a stale number is most likely to be sitting in the
prose.

**5. The gate.** Done means `just verify` is clean with zero errors. Triage
the warnings into `prose-check.toml` with a written reason each — never by
editing a rule. Then `just check-stats-deep` if the analysis runs, and report
anything that changes a number you would quote, even if the paper itself did
not change.

## The traps

1. **`analysis/` inside the manuscript is load-bearing** — see above. And if
   the repository publishes a package or crate, check its include/exclude
   list afterwards: a newly nested analysis tree can quietly ship to a
   registry.
2. **`#include` gives the included file its own scope.** Every included
   `.typ` that uses `s()`, `n()`, `fig()` or `tbl()` needs its own imports.
   The failure is `unknown variable: tbl` pointing *into* the included file,
   not at the missing import.
3. **The BODY markers define what the word count means.** Back matter — the
   bibliography above all — sits outside them and is not counted. If the old
   counter included it, the headline number drops without a word changing.
   Expected; confirm it is the definition moving and not the prose.
