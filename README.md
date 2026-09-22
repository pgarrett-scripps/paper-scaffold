# paper-scaffold

[![CI](https://github.com/pgarrett-scripps/paper-scaffold/actions/workflows/ci.yml/badge.svg)](https://github.com/pgarrett-scripps/paper-scaffold/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Typst 0.14+](https://img.shields.io/badge/Typst-0.14%2B-239dad)

**Keep your paper connected to the analysis behind it.**

paper-scaffold is a starting project for research manuscripts. Write in Typst,
a text-based typesetting system, connect your results to the text, and build
PDF and editable Word files from the same source. It includes a manuscript
template, example analysis, and checks that catch outdated results and exports.

[Start a paper](#quick-start) · [Bring an existing manuscript](MIGRATING.md) ·
[Read the documentation](DOCUMENTATION.md)

## Why use it?

Re-run an analysis, and the figure changes. The number you copied into the
Results section may not. As a paper goes through revisions, those small
mismatches become hard to spot.

paper-scaffold gives results a name that the manuscript reads directly.
Regenerate the analysis outputs and rebuild the paper, and linked numbers,
figures, and tables update together. Checks report when declared inputs have
changed or an export needs rebuilding.

- **Less copying between analysis and prose.** Reference a computed result
  wherever you discuss it, with formatting you control.
- **Results you can trace.** Look up the script, declared inputs, or documented
  source behind a number or figure.
- **PDF and Word from one manuscript.** Share an editable Word export with
  co-authors, including equations, tables, and references.
- **Checks before you share.** Find stale outputs, broken references, and prose
  issues; get word counts and readability reports when you build.
- **Support for revision.** Compare saved versions, guard numbers and citations
  during wording edits, or listen to a draft as an audiobook.

The checks help keep the manuscript consistent with its declared sources.
Scientific interpretation and correctness still need your review.

## Who is it for?

Researchers who write in plain-text files and want their manuscript, analysis,
and revision history in one project. It is especially useful when results
change during drafting or several people edit the paper.

You will use a terminal and edit Typst files. The project includes worked
examples for connecting your analysis. Shared editing workflows are also
available for [Claude Code and Codex](DOCUMENTATION.md#working-with-an-ai).
For a dissertation or book, see the [multi-document guide](MULTI-DOCUMENT.md).

## Quick start

You need **Typst 0.14+, just, uv, Python 3.10+, and Git** for this walkthrough.
`just` runs the project's commands; `uv` manages its Python dependencies.
See [requirements](DOCUMENTATION.md#requirements) for setup details. The first
build needs internet access to download dependencies and the Typst template.

1. **Get the scaffold and check your tools.**

   ```bash
   git clone https://github.com/pgarrett-scripps/paper-scaffold
   cd paper-scaffold
   just doctor
   ```

   Install any tools reported as missing before continuing.

2. **Create your manuscript.**

   ```bash
   ./scripts/new-paper.sh ~/papers/my-paper
   cd ~/papers/my-paper
   ```

   The script asks for your title and author details, creates a separate project
   with its own Git history, and builds the first PDF and Word files. Open
   `paper.pdf` to see the example manuscript. If a build could not finish, run
   `just doctor` and follow its guidance.

3. **Make it yours.**

   | File | What to put there |
   |---|---|
   | `config.typ` | Title, authors, abstract, and keywords |
   | `paper.typ` | Main text |
   | `si-body.typ` | Supporting information |
   | `references.bib` | Bibliography, for both reference lists |
   | `journal.toml` | Which journal's limits the paper is held to, from `journals/` |
   | `slides/` | Talk decks, built from the same figures and numbers |
   | `slides/config.typ` | The talks' title, authors and date, separate from the paper's |

   The Supporting Information prints its own reference list, since journals
   take it as a separate file. Cite `@si-key` in `si-body.typ` and `@key` in
   `paper.typ`; both read `references.bib`.

   Replace the examples in `analysis/` when you are ready to connect your own
   results. The [documentation](DOCUMENTATION.md#the-parts-worth-understanding)
   explains how to add numbers, figures, and tables.

4. **Build and check your changes.**

   ```bash
   just paper     # PDF, editable Word, review text, and prose metrics
   just verify    # Local consistency checks
   ```

   After changing your analysis, run `just assets` before rebuilding. Before
   submission, run `just preflight` for fresh exports, analysis checks, and an
   online bibliography audit.

## Go further

| You want to… | Start here |
|---|---|
| Find a command or understand the files | [Documentation](DOCUMENTATION.md) |
| Move an existing manuscript into the scaffold | [Migration guide](MIGRATING.md) |
| Write a dissertation or book | [Multi-document guide](MULTI-DOCUMENT.md) |
| Set your writing conventions | [Prose style](STYLE.md) |
| Include/exclude sections and set word limits | [Word-count configuration](DOCUMENTATION.md#word-count-scopes-and-limits) |
| See changes and upgrade guidance | [Version history](HISTORY.md) |

## License

[MIT](LICENSE) covers the scaffold and its tools. Your manuscript is yours;
new projects carry the tooling notice as `LICENSE.scaffold`.
