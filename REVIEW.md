# Repository review, September 4, 2026

The review began with scaffold 3.16.0 at commit `adcf5b9`. The working tree now
contains the 3.17.0 hardening changes, tracing, and shared agent skills. This
report records their status and validation limits. It is not a feature roadmap
or evidence that a release has been published.

The existing architecture remains: authors edit manuscript sources and the
presentation fields of declarations; analysis owns generated values and assets;
local checks inspect recorded consistency; submission checks also re-run
statistics and audit the bibliography. See [DOCUMENTATION.md](DOCUMENTATION.md)
for current usage and [HISTORY.md](HISTORY.md#3170) for changes and upgrade steps.

## Correctness findings addressed

| Original failure | Implemented change |
|---|---|
| A multiline `#ref()` was counted as another float definition, producing the wrong reference number in Word | The resolver excludes reference spans from definition discovery. Tests cover multiline and repeated references and compare numbering with Typst. |
| The wording guard accepted substituted statistic/asset IDs and missed the abstract and repeated citations | Snapshots include helper IDs, declaration content, citation occurrences, and literal manuscript includes, including config.typ. |
| Build stamps missed included chapters, nested CSL files, and the Word filter; source capture began after transformations | A Python build tool captures inputs before transformations, incorporates compiler dependencies where compiled, and checks again before publishing. State is per output, output bytes are hashed, and overlapping builds are refused. |
| A generator that wrote nothing could be reported as having re-derived the seeded values | Deep checking requires a fresh invocation-bound writer receipt and checks produced IDs and values. Incomplete execution is nonzero. |
| Numerical guards and malformed declarations behaved differently in writers and checkers | Shared validation handles guard types, finite values, and manifest shapes. Writers replace manifests atomically. |

Additional fixes cover forwarded command-line options, BibTeX parsing, copying
new papers without local build artifacts, singleton keyword tuples, and running
tests when the optional formatter is absent. Analysis project/lock hashes are
now part of provenance. Python 3.10 has its conditional TOML dependency, and
the CI verification matrix rejects lock drift.

## Implemented agent support

`just trace <id> --json` gathers a statistic or asset's declaration, recorded
inputs, literal source uses, and current consistency findings. It reports
whether inspection passed, failed, or was incomplete without running analysis.

The four existing skills cover wording edits, repairing failed checks,
declaring numbers, and adding generated figures/tables. Claude Code discovers
them in `.claude/skills/`; Codex uses the relative `.agents/skills` symlink to
the same files. Their instructions preserve author changes, use tracing where
relevant, and distinguish mechanical checks from review of scientific meaning.
The pipeline does not provide an MCP server.

## Validation completed locally

- `just paper` followed by `just verify` passed, including 21 hardening cases
  and the existing extractor suite.
- Both Word export paths were exercised. The native output retained its
  abstract, headings, two editable equations, two tables, and one image. The
  fallback retained headings, abstract, and both equations as images. The final
  paper.docx uses the native path. These were structural checks, not a
  page-by-page visual review.
- `just check-stats-deep` actually re-derived all five sample statistics.
- All four skills passed the skill validator through both discovery paths.
  The new-paper integration case checks that the copied symlink resolves to
  the copied skills, with their content preserved.
- `git diff --check` passed. Scratch fixtures exercised failure cases without
  changing the example manuscript's claims.

The local sandbox required `UV_CACHE_DIR=/tmp/paper-scaffold-uv-cache`; this is
an execution constraint, not a repository defect.

The example manuscript's printed metrics were:

| Scope | Words | Characters | Words/sentence | FK grade | Reading ease | Fog |
|---|---:|---:|---:|---:|---:|---:|
| Abstract | 107 | 615 | — | — | — | — |
| Main text | 204 | 1,066 | 13.4 | 7.7 | 64 | 11.1 |
| Supporting Information | 116 | 657 | 12.9 | 9.7 | 49 | 12.7 |
| Main + SI | 320 | 1,723 | 13.2 | 8.4 | 58 | 11.7 |

## Validation limits and remaining checks

The expanded Python/Typst CI matrix has not been demonstrated by this local
session. Python 3.10, full cross-platform manuscript builds, live bibliography
auditing, and audiobook synthesis were not run locally. Network failure
behavior was tested with injected responses. This is not a completed preflight.

The build and regression evidence comes from the example paper and scratch
fixtures. A real manuscript with customized analysis and included sections
still needs a trial before treating those workflows as validated for that paper.

The source index follows literal helper calls and literal Typst includes and
imports. Dynamically computed IDs and paths are outside that index. The export
resolver handles a supported Typst subset; it is not a general Typst evaluator.
Checks establish recorded consistency, not scientific correctness. CI action
commit pins and release-binary digest verification were not added in this pass.

Further work should address a demonstrated manuscript problem. No additional
feature implementation is scheduled by this review.
