# Evidence: where the numbers come from

`stats.json` and `assets.json` say which script produced each number and
figure, and which files it read. They do not say which body of results those
files belong to, which release of the software produced them, or what
configuration that run read. A path written into a generator
(`RESULTS = "benchmark/results/run_0922"`) answers badly: a rerun under a new
version silently mixes two versions in one table, a recalibrated config
leaves results computed with the old setting looking current, and a path
copied from a shell works on one machine.

`evidence.toml` is optional. Without it nothing below applies except the
input, pending and hand-source checks at the end.

## The manifest

`evidence.toml`, at the manuscript root, names each body of evidence once:

```toml
[sets.run-a]
path = "benchmark/results/run-a_2026-09"      # repo-relative; `files = [...]` also works
software = { searchtool = "0.10.0" }           # tool -> version or commit
commit = "3f9a2c1"                             # optional: the producing commit
verify = "benchmark/results/run-a_2026-09/verification.json"
inputs = ["benchmark/config/search.toml"]      # what the run was configured by
status = "frozen"                              # or "pending", "held-out"
frozen_at = 2026-09-01
stats = ["bench.run-a.*"]                      # ids this set produces
assets = ["fig.run-a-*"]
note = "optional free text"

allow_mixed = ["cmp.versions.*"]               # ids that compare versions on purpose

[checks]
untracked_inputs = "warn"                      # off | warn | error
version_literals = "warn"                      # off | warn | error
```

Paths are relative to the manuscript root and checked lexically: `../` is
fine while it stays inside the git repository (a manuscript in `paper/`
reading `../benchmark/`), and a symlink to a data drive is fine because it is
never resolved. An absolute or `~` path is rejected. An unknown key is an
error, so a typo cannot silently turn a check off. Patterns are an exact id
or a prefix ending in `*`.

## In a generator

```python
from _assets import record, evidence      # _stats re-exports it too
runs = evidence("run-a")                   # a Path; an unknown set or missing path fails here
...
record("fig.run-a-recall", "figures/recall.png", kind="figure",
       inputs=[str(runs / "recall.tsv")])
```

Swapping a campaign is then one edit, in `evidence.toml`. Each entry records,
in an additive `evidence` field, `{set: {tool: version}}` for every set that
names its id (`stats`/`assets` patterns), holds one of its declared inputs, or
is passed as `record(..., evidence="run-a")`. A `Stats.write()` also records a
top-level `evidence` block naming the sets the generator resolved. An entry
that would combine two versions of one tool fails when it is written, unless
`allow_mixed` names it.

## The checks: `just check-evidence`

In `verify` (through the declarations stage). Errors:

- the manifest does not parse, or a path is a host path or leaves the repo;
- an entry was built with a version the manifest no longer declares
  (`just assets` fixes it), or mixes two versions of one tool;
- a set is `pending`, or a `pending` block remains (below);
- a verification file's `status` is not a pass (`verified`, `passed`, `ok`,
  `complete`), or it changed since the set was stamped;
- a config in `inputs` changed after the set was stamped: the results were
  produced with the old setting. Re-run, or re-stamp if the change cannot
  affect them;
- a `frozen` or `held-out` set's files changed since the stamp (paths and
  sizes, so a large tree stays cheap to check), or it has no `frozen_at`;
- a `held-out` set has no `first_scored_at`, or was frozen after it.

Warnings: a missing set path (an error with `--strict`, which `preflight`
runs), a set with no software or commit, software changed since the stamp, a
verification file recording host paths, and version literals in the prose
next to a tool's name that no set declares (`searchtool 0.7.0` while the
manifest says 0.10.0).

`just evidence-stamp [SET...]` records what those comparisons use, in
`evidence.lock.json` (commit it): each set's verification-file and input
hashes, its software, and a frozen set's tree. Stamp after checking a run,
the same deliberate "this is right" as `just pin`.

## What a version touches: `just impact`

```bash
just impact searchtool@0.7.0      # or `just impact searchtool` for every version
```

lists the sets produced by that version, every number and figure built from
them, and the prose lines that use each id: the list to re-check before a
version change goes into the paper. `just trace ID` shows the same from the
other side, under `evidence`.

## Pending results

A top-level `pending` block in `stats.json` (numbers) or `assets.json`
(figures, tables) lets a draft compile while a rerun is out:

```json
"pending": {"bench.run-a.*": "rerun at 0.10.0 in progress"}
```

`#s()` prints a boxed `[pending: id]`, `fig()`/`tbl()` a placeholder block,
for any matching id, declared or not. `check-evidence` fails on every pending
entry, so `verify` and `preflight` stay red until it is removed. A set's
`status = "pending"` fails the gate too, but does not change the PDF: list
its ids under `pending` for that.

## Without evidence.toml

Three checks apply to every paper:

- **Inputs git does not hold.** A declared input that is untracked or
  gitignored warns, one line per generator: a clone cannot rebuild from it.
  Commit it, or declare the data as an evidence set (inputs inside a set's
  path are the manifest's business). `[checks] untracked_inputs = "error"`
  makes it a gate. An input recorded as a host path warns; `just assets` now
  stores such paths relative to the manuscript.
- **Pending blocks** fail the gate, as above.
- **Hand entries name a source** (`origin.source`,
  [numbers.md](numbers.md#stats-json-is-yours-not-just-the-analysis-s)); it
  may be `evidence:SET`.
