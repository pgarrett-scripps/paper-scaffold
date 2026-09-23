# paper-scaffold

[![CI](https://github.com/pgarrett-scripps/paper-scaffold/actions/workflows/ci.yml/badge.svg)](https://github.com/pgarrett-scripps/paper-scaffold/actions/workflows/ci.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22905759.svg)](https://doi.org/10.5281/zenodo.22905759)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Typst 0.14+](https://img.shields.io/badge/Typst-0.14%2B-239dad)

**Keep your paper connected to the analysis behind it.**

paper-scaffold is a starting project for research manuscripts written in
Typst. Your analysis declares its results; the manuscript reads them by name;
one command builds the PDF and an editable Word file; another checks that
nothing has gone stale.

[Start a paper](#quick-start) ·
[Bring an existing manuscript](docs/migrating.md) ·
[Documentation](docs/README.md)

## Why use it?

Re-run an analysis and the figure changes, but the number you copied into the
Results section does not. paper-scaffold removes the copying:

- **Numbers by name.** Write `#s("recall.gain")`, not `12.4%`. The value comes
  from the analysis, with a checksum, the code and data behind it, and guards
  on what the sentence assumes ("fell" fails the build if the sign flips).
- **Figures and tables by name.** Generators declare their outputs, and
  `just verify` reports any that are older than their code or data.
- **PDF and Word from one source.** Word export has native equations and
  references, for co-authors and journals that want `.docx`.
- **Journal-ready.** Word limits, figure counts and graphical-abstract size
  come from a journal profile; `just submission` writes the upload set.
- **Safe to hand to an AI.** An edit guard lets a wording pass drop a number
  but never invent one. Packaged skills for Claude Code and Codex audit claims
  and methods against the code that computes them ([details](docs/working-with-ai.md)).

The checks keep the manuscript consistent with its sources. Whether the
science is right is still your call.

## Quick start

You need **Typst 0.14+, just, uv, Python 3.10+ and Git**
([requirements](docs/getting-started.md#requirements)). The first build
downloads the Typst template.

```bash
git clone https://github.com/pgarrett-scripps/paper-scaffold
cd paper-scaffold
just doctor                              # reports any missing tool
./scripts/new-paper.sh ~/papers/my-paper # asks for title and authors, builds a first PDF
cd ~/papers/my-paper
```

Then edit:

| File | What goes there |
|---|---|
| `config.typ` | Title, authors, abstract, keywords |
| `paper.typ` | Main text |
| `si-body.typ` | Supporting Information (cite as `@si-key`; it has its own reference list) |
| `references.bib` | Bibliography for both lists |
| `journal.toml` | Which journal profile in `journals/` the paper is held to |
| `analysis/` | Your analysis; replace the examples when you connect real results |

And build:

```bash
just assets     # after changing the analysis: regenerate figures, tables, numbers
just paper      # PDF, Word, review text, word counts and readability
just verify     # the gate: formatting, prose rules, limits, staleness
just preflight  # before submitting: fresh builds, deep checks, DOI audit, submission/
```

## Go further

| You want to… | Start here |
|---|---|
| Find a command or understand the files | [Documentation](docs/README.md) |
| Move an existing manuscript in | [Migration guide](docs/migrating.md) |
| Write a dissertation or book | [Multi-document guide](docs/multi-document.md) |
| Build talk slides from the same numbers | [Slides and audio](docs/slides-and-audio.md) |
| Upgrade a paper to a newer scaffold | [Upgrading](docs/upgrading.md) (move the pin, `uv run paper sync`) |
| See what changed | [Version history](HISTORY.md) |

## Citing

If paper-scaffold helped with your manuscript, please cite it:

> Garrett, P. T. *paper-scaffold: provenance-checked Typst manuscripts that
> are safe for AI agents to edit.* Zenodo.
> [doi:10.5281/zenodo.22905759](https://doi.org/10.5281/zenodo.22905759)

The DOI always resolves to the latest release; [CITATION.cff](CITATION.cff)
has the full metadata.

## License

[MIT](LICENSE) covers the scaffold and its tools. Your manuscript is yours;
new projects carry the tooling notice as `LICENSE.scaffold`.
