# paper-scaffold documentation

Setup, commands, and technical details for working on a manuscript, one page
per subsystem. New here? Start with the [overview and quick start](../README.md).
Agents: the working rules are in [CLAUDE.md](../CLAUDE.md); this folder has
the reasons behind them.

## Find what you need

| Task | Read |
|---|---|
| Set up a new paper | [Getting started](getting-started.md) |
| Find a command | [Commands](commands.md) |
| Find the file to edit | [Project layout](#layout), [manuscript sources](manuscript.md) |
| Connect results to the text | [Numbers in prose](numbers.md) |
| Add a figure or table | [Generated figures and tables](assets.md) |
| Inspect a result's source | [Tracing numbers and assets](numbers.md#tracing-numbers-and-assets) |
| Understand the gates and staleness | [Builds, staleness and the gates](build-and-staleness.md) |
| Compare manuscript versions | [Reviewing changes](build-and-staleness.md#reviewing-changes-between-versions) |
| Work with an AI editor | [AI editing and review](working-with-ai.md) |
| Export to Word | [Word export](word-export.md) |
| Build the journal upload set | [Submission outputs](submission.md) |
| Select a journal, sections and word limits | [Journals and word limits](journals.md) |
| Check the writing | [Prose checks, formatting and tests](prose-checks.md) |
| Make a talk or listen to a draft | [Slides and audio](slides-and-audio.md) |
| Add a paper-specific stage, recipe or Word fix without editing the scaffold | [Extension hooks](hooks.md) |
| Upgrade to a newer scaffold | [Versioning and upgrading](upgrading.md), [HISTORY.md](../HISTORY.md) |
| Troubleshoot | [Requirements](getting-started.md#requirements), [common pitfalls](getting-started.md#things-that-will-bite-you) |

Existing manuscript: follow [migrating.md](migrating.md) (in the scaffold
checkout; new papers do not carry it).

Dissertation or book: [multi-document.md](multi-document.md) describes optional
named PDF targets, chapter metrics and checks, wording-edit guards, and the
dissertation Word adapter. `just paper` detects a multi-document manifest;
existing single-paper projects keep their normal build behavior.

Release notes older than 3.20.0 are in [history-archive.md](history-archive.md)
(scaffold checkout only).

## The ideas

```
A number worth stating is worth tracing.
Declared and read back beats typed and remembered.
A copy is the thing that goes stale.
A manifest nothing reads is already wrong.
The value is the analysis's; how it reads is the author's.
What cannot be discovered must be declared,
    and an honest partial answer beats one that looks total.
A check that never fails is not a check.
The gate you run constantly must cost nothing;
    the gate that costs something must be one command.
A ritual with conditions is a ritual skipped.
A warning with an expensive fix is a warning ignored.
Silence is not success -- fail where the mistake was made.
Hashes, not dates; content, not history.
"It changed" means it changed, not that the script ran.
Every guarantee was proven by breaking it first.
```

Each line is a decision this repository actually made, usually after the
opposite failed; [HISTORY.md](../HISTORY.md) records which failure produced
which line. The rest of this guide is the long form — skim the section heads
and read the ones you are about to touch.

## Layout

```
paper.typ  config.typ  si-body.typ    the manuscript
stats.typ  assets.typ  wordcount.typ  Typst helpers it imports
stats.json  assets.json               what the analysis declared: numbers, figures
references.bib                        the bibliography
justfile  pyproject.toml              how to build it, and what with
prose-check.toml                      this project's prose exceptions

tools/       the Python and shell toolchain. Nothing here is imported by the
             manuscript; every one of them READS it. Run through `just`.
analysis/    your analysis. Writes into figures/ and si/. Own environment.
figures/ si/ generated, and tracked, so a fresh clone compiles
slides/      talk decks (Typst + Touying). Sources tracked, PDFs not.
             theme.typ configures Touying; config.typ is the talks' own
             identity. Outside the gate. Optional, deletable.
audio/       narration. Optional, deletable.
tests/       the extractor fixture, its golden files, and one case module
             per subject. run.py lists them; each runs standalone too.
scripts/     new-paper.sh, which makes a manuscript out of this directory
```

The root holds what a person edits and what a build produces. Everything that
processes the manuscript lives in `tools/`, and each of those resolves paths
against the repository root (`.parent.parent`, since they sit one level down),
so they still run from anywhere via `just`.

## Notes for agents

The working rules for editing a manuscript built on this scaffold are in
[CLAUDE.md](../CLAUDE.md): what never to hand-edit, what to run before calling the
work done, and the Typst and Python conventions.

`AGENTS.md` is a **symlink** to that same file, so tools following either
convention read one document. It is a symlink rather than a copy on purpose: two
files of instructions drift, and the one that drifts is always the one the agent
happened to read. Preserve it as a symlink if you move the directory around by
hand (`scripts/new-paper.sh` uses `tar` rather than `cp -r` for exactly this
reason).

## Provenance

Extracted from the `dnoise` manuscript pipeline. The design decisions encoded
here (commit-date PDF checking, byte-compared figure copies, generated SI tables,
the resolver's own front matter) each came from a specific way that manuscript went
wrong.

## License

MIT, see [LICENSE](../LICENSE). It covers the scaffold and its tooling, not any
manuscript you write with it. `scripts/new-paper.sh` carries the notice into a
new project as `LICENSE.scaffold`, renamed so that a `LICENSE` at the root of a
manuscript directory does not read as a claim about the paper, which is a
different question and yours to answer.
