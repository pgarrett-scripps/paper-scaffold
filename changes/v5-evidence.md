# v5-evidence: where the numbers come from

## What changed

- `evidence.toml` (optional) names each body of evidence once: repo-relative path, software versions, commit, verification file, config inputs, status (`pending`/`frozen`/`held-out`), and the stat/asset ids it produces. Generators open data as `evidence("set")` (from `_assets` or `_stats`), which fails loudly on an unknown set, a missing path or a host path.
- `record()` and `Stats.write()` write an additive `evidence` field (`{set: {tool: version}}`) into each entry; an entry mixing two versions of one tool fails when written unless `allow_mixed` names it. `stats.json` gains an additive top-level `evidence` block per generator.
- `just check-evidence` (in `verify`; `--strict` in `preflight`): manifest schema, stale versions, mixed versions, verification status and hash, config inputs changed since the stamp, frozen/held-out trees and dates, pending declarations, untracked/ignored and host-path inputs, version literals in the prose that disagree with the manifest.
- `just evidence-stamp [SET...]` writes `evidence.lock.json`; `just impact TOOL[@VER]` lists the sets, numbers, figures and prose lines a version touches; `just trace` reports an `evidence` key.
- Declared inputs are stored repo-relative: an absolute path inside the repository and a symlinked in-repo data directory (lexical) both become relative; a path outside the repository is kept and warned about.
- Hand-entered stats need `origin.source` (repo path with optional `#anchor`, URL, DOI, commit, or `evidence:SET`); a host path is rejected.
- Pending: a top-level `pending` block (`{id-or-prefix*: reason}`) in `stats.json`/`assets.json` makes `#s()`, `fig()`, `tbl()` and `dfile()` render a visible placeholder; only `check-evidence` (so `verify`/`preflight`) fails.
- Adopted and hand tables may list `checked_against` files; `just adopt-checked ID` records their hashes and `check-assets` warns when one changes.
- `just assets` logs the generators it ran (`.build-state/assets-run.json`); `check-assets` warns about a recorded generator the last run did not execute, or (with no log) notes one no analysis recipe names.

## Upgrade:

- `uv run paper sync` copies `evidence.py` into `analysis/scripts/_toolchain/` and, on the move from 4.x, lists existing hand entries without `origin.source` in `.paper/grandfathered.json` (commit it): those warn, new ones are errors. Add sources to retire the warnings.
- New warnings that may appear on existing papers: declared inputs untracked or gitignored by git (one line per generator), input keys recorded as host paths (rerun `just assets`), generators missing from the last `just assets` run.
- New errors, only where a paper opts in: anything in `evidence.toml` (stale or mixed versions, a verification file that did not pass, a stamped config that changed, a moved frozen set, held-out ordering) and any `pending` entry. A paper without `evidence.toml` or `pending` blocks fails nothing new.
- `evidence.toml` and `evidence.lock.json` are committed; `.build-state/assets-run.json` is local.
