# v5-gates

## What changed

- `just check-submission` checks the data and code availability statement (`tools/availability.py`, `just availability`): cited accessions missing from it, placeholders, no section, no archived code DOI. Configured by `[availability]` in project.toml.
- `just assets` / `just stats` refuse to drop an id gen_stats.py stopped declaring; `--prune` (or `PAPER_STATS_PRUNE=1`) retires it.
- Every failing `expect` guard of a run is reported at once and recorded; `just assets --explain` and `just explain-guards` print each beside the sentences that read the id.
- A whole-number float with no `fmt` prints `14`, not `14.0`.
- `[stats] si-only` / `evidence-only` globs in project.toml exempt ids from check-stats' "unused" warning; a glob matching nothing warns.
- `just gate [paper|all]`: fmt, `just assets` only when stale, the build, verify; stops at the first failure.
- A clean `just verify` records a pass stamp for the exact tree; `just check-verify-stamp` compares; `just install-hooks` adds an optional pre-commit hook.
- `just paper` holds the build lock for the whole build and waits (`PAPER_BUILD_WAIT`, default 900 s) for another session's build instead of failing; the holder is named.
- A build refuses to start below `PAPER_MIN_FREE_MB` (default 500) free disk.
- A stale output names the files that changed (`check-build`, `check-submission`).
- `/paper:reviewer-response` skill and `just response-init` / `response` / `check-response`: a response letter whose points cite ledger rows; `check-response` (a verify stage while the letter exists) fails on a done point without committed rows or a cited row that does not exist.
- `just tag-submission <name>`: annotated tag `submitted/<name>` with the PDF hash and tree fingerprint, plus a saved review version.
- `just diff-pdf <name>`: text-level diff (pdftotext + difflib) against the submitted PDF, as `.review/diff-<name>.pdf` and `.html`; method in docs/submission.md.
- `just edit-check <tag> --revision`: new ids, citations, floats and headings are notes; a typed numeral still fails.
- `just edit-check` treats `#ci("id")` like `#s("id")` (a changed id fails; a dropped call is a note, as dropped `#s()`/`#n()` calls now are), and reads the digits in `#lit(v, unlike: "id")` ids as names, not typed numbers.
- `just actions-add` / `actions-reserve`: ledger rows and ids under a lock with a next-id file, so concurrent sessions never collide.
- `Closes: A-0012` commit trailers and `just close-actions`; `just check-actions` fails when a done row's hash is not the commit carrying its trailer, warns when a hash names no commit.
- Review skills write rows through `just actions-add` and take `no-ledger`; editing skills close rows through the trailer.

## Upgrade:

- Run `uv run paper sync` (justfile). No manuscript edit is required for `just verify`.
- **New error in `just check-submission` / `just preflight`:** the availability check. Most existing papers fail it on `no-archive` (no Zenodo, figshare, Software Heritage, OSF or Dryad DOI for the code) and some on `missing` (an accession cited in the text but not in the statement) or `placeholder`. Fix the statement, or opt out in project.toml: `[availability] require_code_archive = false`, `disable = ["<pattern>"]`, or `enabled = false`. Run `just availability` to see the findings.
- **`just assets` now stops when gen_stats.py no longer declares an id stats.json holds.** Check the named ids (a rename leaves prose on the old id), then `just assets --prune`.
- A guard failure message now lists every failing id, not the first.
- **`check-actions` may now fail** on a done row whose hash differs from the commit whose message says `Closes:` that row. Pre-existing ledgers without trailers are unaffected; a hash naming no commit only warns.
- `just paper` now waits for another build instead of failing at once; set `PAPER_BUILD_WAIT=0` for the old behaviour.
- A paper whose `stats.json` has ids read only by SI tables or kept as evidence can list them under `[stats]` in project.toml to silence the unused warnings.
- Add `reviewer-response.pdf` to the paper's `.gitignore` when starting a revision round.
- A paper with the pre-commit hook installed needs `just verify` (or `just gate`) before each commit touching the manuscript; it is off unless `just install-hooks` is run.
