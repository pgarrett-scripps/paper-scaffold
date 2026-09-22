# paper-scaffold documentation

Setup, commands, and technical details for working on a manuscript.
New here? Start with the [overview and quick start](README.md).

## Find what you need

| Task | Read |
|---|---|
| Set up a new paper | [Requirements](#requirements), [quick start](#quick-start) |
| Find a command | [Command reference](#what-to-run) |
| Find the file to edit | [Project layout](#layout) |
| Connect results to the text | [Numbers in prose](#numbers-in-prose-sid-not-a-typed-numeral) |
| Add a figure or table | [Generated tables](#the-si-contract-generated-tables-never-hand-typed-numbers), [asset declarations](#figures-and-tables-by-id-figfigx-not-a-filename) |
| Inspect a result's source | [Tracing numbers and assets](#tracing-numbers-and-assets) |
| Compare manuscript versions | [Reviewing changes](#reviewing-changes-between-versions) |
| Work with an AI editor | [Shared workflows](#working-with-an-ai) |
| Export to Word | [Word export](#the-word-export-is-more-delicate-than-it-looks) |
| Check the writing | [Prose metrics](#reading-the-prose-metrics), [rule configuration](#suppressing-a-finding-prose-checktoml) |
| Select sections and set word limits | [Word-count scopes and limits](#word-count-scopes-and-limits) |
| Listen to a draft | [Audio](#audio) |
| Troubleshoot | [Requirements](#requirements), [common pitfalls](#things-that-will-bite-you) |

Existing manuscript: follow [MIGRATING.md](MIGRATING.md).

Dissertation or book: [MULTI-DOCUMENT.md](MULTI-DOCUMENT.md) describes optional
named PDF targets, chapter metrics and checks, wording-edit guards, and the
dissertation Word adapter. `just paper` detects a multi-document manifest;
existing single-paper projects keep their normal build behavior.

## Quick start

```bash
git clone https://github.com/pgarrett-scripps/paper-scaffold
cd paper-scaffold
just doctor                          # is the toolchain present and new enough?

./scripts/new-paper.sh ~/papers/my-paper
```

The script asks for the title, author, and the rest of the identity, copies the
working files, fills in `config.typ`, builds the first PDF, and starts a git
history that belongs to the new paper. Every field also has a flag, so a
scripted run needs no terminal:

```bash
./scripts/new-paper.sh --yes --title "My Paper" --author "Ada Lovelace" ~/papers/mine
./scripts/new-paper.sh --help
```

**Do not start a paper with `cp -r`.** It copies `.git` too, so `just version`
reports the *scaffold's* last commit as the manuscript's state — confidently, and
wrongly. It also drags along `.build-state/`, which then claims the new paper's
outputs were built from sources it has never seen.

Then, in the new directory:

1. Replace the abstract in `config.typ`. Title, authors and keywords are already
   filled in; the abstract is prose and is left for you.
2. Replace the placeholder prose in `paper.typ` and `si-body.typ`.
3. Replace `references.bib`.
4. Put your analysis in `analysis/`, keeping `just assets` as its front door. Or
   delete `analysis/` entirely if the paper has no generated assets.

Nothing else should need editing. Use `just verify` for local consistency
checks and `just preflight` before an actual submission. Neither replaces
reviewing the manuscript's scientific content.

Three parts are optional. `analysis/` (no generated assets) and `audio/` (no
narration) can simply be deleted: every recipe and check adapts rather than
failing. The generated-numbers mechanism (`stats.typ` + `stats.json` +
`analysis/scripts/gen_stats.py`) and the generated-asset one (`assets.typ` +
`assets.json`) also come out, but not by deleting alone —
Typst cannot conditionally import a file that is not there, so three `.typ` files
have to drop their import. The exact edits are under
[Numbers in prose](#numbers-in-prose-sid-not-a-typed-numeral).

## What to run

| Command | Does |
|---|---|
| `just verify` | **The gate.** Formatting, extractors, prose rules and staleness, in one pass |
| `just preflight` | **The submission gate.** Fresh builds + `verify` + deep stats + DOI audit |
| `just doctor` | Are the external tools installed and new enough? |
| `just paper` | Build `paper.pdf`, `paper.docx`, and `paper.review.txt`, with word counts and readability |
| `just pdf` | Build only `paper.pdf`, with word counts and readability |
| `just draft` | Compile `paper-draft.pdf` with unresolved `#s()` numbers shown as `?id?` |
| `just watch` | Live preview, recompiling on save |
| `just fmt` | Reflow the hand-written Typst sources (typstyle, 80 cols) |
| `just docx` | Export `paper.docx` for journals and co-authors |
| `just slides [name]` | Build a slide deck from `slides/` -> `slides/<name>.pdf` (all decks with no name) |
| `just slides-handout [name]` | Build the handout form, with every `#pause` reveal flattened |
| `just slides-check [name]` | Deck staleness plus the four slide-only prose rules. Not in `verify` |
| `just slides-notes <name>` | Export `#speaker-note` text to `slides/<name>.pdfpc` for a presenter tool |
| `just slides-list` | What decks exist, and whether each is current |
| `just review-text [target]` | Export a compact `.review.txt` with prose, equations and numbered captions for AI review |
| `just wordcount` | Journal-style counts and configured section checks without rebuilding |
| `just journal` | Everything the selected journal profile says, against the manuscript |
| `just check-journal` | Keyword count, figure and table counts, graphical abstract size. In `verify` |
| `just journals` | The profiles under `journals/` and which one `journal.toml` selects |
| `just wordcount --sections` | List exact section paths available for word-count checks |
| `just check-words` | Enforce configured minimum/maximum word counts; also runs in `verify` |
| `just readability` | Flesch-Kincaid / reading ease / fog without rebuilding |
| `just assets` | Regenerate every generated figure, table and prose number (delegates to `analysis/`) |
| `just check` | Report every artifact that has fallen behind its source |
| `just trace <id> --json` | Inspect a statistic or asset, its uses, provenance, and checks as structured data |
| `just pin` | Record hashes for the files listed under `pinned` in `stats.json` |
| `just text-baseline` / `text-diff` | Snapshot the PDF's words; word-level diff after a structural refactor |
| `just review-baseline <name>` | Save a resolved manuscript version, including its figures and bibliography |
| `just review <name> [new-name]` | Highlight changes against the current manuscript or another saved version |
| `just edit-baseline` / `edit-check` | Check that wording edits preserve retained numbers, helper IDs, citations, declarations, and structure |
| `just test` | Assert the prose extractors handle every construct, before and after a reflow |
| `just prose-check` | Check the prose, plus figure resolution and table shape, against STYLE.md |
| `just word-audit` | Count flagged words across the manuscript without rebuilding |
| `just prose-check --list-rules` | Every rule, its severity, and how to configure it |
| `just bib-audit` | Check DOI metadata, retractions and dead links against Crossref/DataCite (network) |
| `just viz` | Diagnostics about the draft -> `viz/`: nine plots plus `report.json` for tools |
| `just density` | Numerals, parentheticals, acronyms, passives per 1,000 words, and section outliers |
| `just setup` | Build the Python environment (uv, locked) |
| `just version` | Which scaffold version this manuscript is built on |
| `just audio-setup` | One-time: install the audio deps and download the voice model |
| `just audiobook` | Chaptered `.m4b` of the main text |
| `just all` | PDF + Word + both audiobooks, then `just check` |

## Word-count scopes and limits

`word-limits.toml` selects what each word-count check includes and sets optional
minimum and maximum word counts. Run `just wordcount --sections` to see the
available paths, then edit the configuration. For example:

```toml
schema_version = 1

[[checks]]
name = "Abstract"
include = ["abstract"]
min = 100
max = 250

[[checks]]
name = "Main text without Methods"
include = ["main"]
exclude = ["main/Methods"]
min = 2000
max = 4000

[[checks]]
name = "Results"
include = ["main/Results"]
max = 1500
```

These bounds are examples, not default journal requirements. The shipped file
has no active bounds. Omit `min` or `max` when that bound does not apply; both
are inclusive, nonnegative integers. With neither bound, a check just reports
its selected count. An absent file or empty `checks` list disables the gate.

Paths are case-sensitive: `abstract`, `main`, and `si` select entire regions;
`main/Methods` selects that heading and every subsection until the next heading
of equal or higher level. A nested path looks like `main/Methods/Sampling`.
Headings in included files participate in the same hierarchy. A literal `/`
in a heading is displayed as `%2F` in its path (`%` becomes `%25`); copy paths
from `--sections`. Duplicate heading paths cannot be selected individually.
Rename them or select their common parent. Renamed or missing selections fail
explicitly rather than silently reducing the count.

Every check takes the union of its `include` paths, then subtracts its `exclude`
paths. Overlaps count once; exclusions win. An exclusion outside the included
scope is an error. Multiple independent checks may cover the same text. To
count the main text and SI together, use `include = ["main", "si"]`; add
`"abstract"` explicitly if it belongs in that limit.

Counts still use the evaluated Typst content and the existing wordometer rules:
headings and inline code count; references, citations, figures, tables inside
figures, captions, equations, and block code do not. The main text remains
bounded by BODY markers, the abstract comes from `config.typ`, and SI comes
from `si-body.typ`. Front matter and back matter outside those scopes are not
selectable. These selections affect word-count checks only; they do not remove
content from exports or change readability, spelling, or standard main/SI
totals. This configuration currently applies to the single-paper workflow;
named document metrics keep their existing `manuscript.toml` part scopes.

`just wordcount` and `just paper` display counts and any violations without
blocking a draft build on length alone. `just check-words` fails for violated
bounds, and runs inside `just verify` and therefore `just preflight`. Invalid
configuration or a count that cannot be completed is an error in either mode.
The gate reads current sources without writing a PDF or regenerating analysis;
if formatted statistics are stale, it asks for `just render-stats`.

For structured output, use `just check-words --json`, or
`uv run python tools/wordcount.py --json` for a report without enforcement.
JSON includes standard counts, section counts, selected paths, bounds, and
statuses. A section row holds its own words before the next heading; the human
`--sections` listing includes descendant words. The Python CLI exits 0 for a
completed passing check, 1 for a violated bound, and 2 for an incomplete check;
`just` wraps nonzero exit codes.

## Working with an AI

`just review-text` writes `paper.review.txt` for upload to an AI reviewer.
`just paper` runs the PDF, Word, and review-text exports together; `just pdf`,
`just docx`, and `just review-text` remain available for individual formats.
It preserves wording, headings, evaluated numbers, equations in plain-text
notation, code, and numbered figure/table captions. Images, table bodies,
reference lists, page furniture, and repeated front matter are omitted.
Citation keys remain in brackets so feedback can identify the cited source;
figure/table references use compiled numbers. Other cross-references retain
their source labels. This is an export, not an AI summary or rewrite.

The export evaluates current Typst sources in a temporary copy and does not
require a current PDF or Word file. Main prose comes from BODY markers;
single-paper exports also include the configured title/abstract, back matter
before the bibliography, and included `si-body.typ`. Manifest projects export
their selected BODY parts in order: `just review-text chapter-id` selects a
chapter and `just review-text all` exports every target. Each text file sits
beside its corresponding PDF, with `.review.txt` replacing `.pdf`.

Unknown content constructs stop the export rather than silently deleting text;
arbitrary context-dependent prose needs explicit exporter support. Existing
exports remain intact on failure. Re-run the command after edits; these review
copies are not included in the PDF/Word freshness gate. They support prose and
argument review, but visual, table-data, and bibliography checks require the
full manuscript.

Open the manuscript repository in Claude Code or Codex and give your editing
request. Both use the same standing instructions: `AGENTS.md` links to
`CLAUDE.md`. The agent edits source files and runs the pipeline through `just`.
No MCP server is required.

For prose work, agents read and edit the Typst source directly. After a
successful build, `paper.resolved.typ` provides a readable text view with the
statistics, tables, and reference numbers filled in. It is generated and must
not be edited. Check `just check-build` before treating it as current; during
edits, use the source and `just trace <id> --json` to inspect a displayed number.
`just resolve` also builds the PDF, so it is not needed for each prose change.
The final `just paper` refreshes the resolved text.

Ordinary wording edits use text review and command-line checks. PDF or image
inspection is reserved for requested visual review, layout or figure changes,
and specific rendering defects. Copy-editing records its initial metrics with
`just wordcount` and `just readability`, then builds after editing and runs
`just verify`. The writing review also checks defined terminology and concrete,
supported claims using [STYLE.md](STYLE.md#scientific-terms-and-concrete-claims).

Twelve workflows ship as skills: four that edit (`copy-edit`, `fix-verify`,
`declare-number`, `new-figure`) and seven read-only reviews (`claim-audit`,
`methods-vs-code`, `figure-review`, `prose-review`, `literature-check`,
`story-review`, `peer-review`) that write findings under `reviews/`, plus
`review-all`, which runs the fix-list reviews in parallel (the network-bound
literature check only on request; the story review is a plan to discuss and
stays out) and merges them. Their maintained files live in `plugins/paper/skills/`
in the scaffold and reach every paper as the `paper` Claude Code plugin
(`.claude/settings.json` enables it; the `paper-scaffold` marketplace serves it).
`.agents/skills` is a symlink into the scaffold checkout so Codex discovers the
same instructions. Neither is copied by `new-paper.sh`.

| Skill | Does |
|---|---|
| `copy-edit` | Polish the requested prose while guarding retained numbers, helper IDs, citations, and structure |
| `fix-verify` | Diagnose failed or incomplete checks and repair the cause while preserving author edits |
| `declare-number` | Connect a number to the right source; check that a literal conversion preserves displayed text |
| `new-figure` | Add a generated plot/table, declaration, caption, citations, and the required imports and checks |

For example, use `/copy-edit Shorten the Results section` in Claude Code or
`$copy-edit Shorten the Results section` in Codex. The workflows can also be
selected from a matching plain-language request. Start a new agent session
after installing the shared paths and check that these four skills appear in
its skill list. Discovery locations are documented by
[Claude Code](https://code.claude.com/docs/en/skills) and
[Codex](https://learn.chatgpt.com/docs/build-skills).

The skills instruct the agent to run the relevant checks and report their
results. Checks establish mechanical consistency; the agent must still read
the edited prose for scientific meaning. Instructions alone do not force an
agent to run a check. A check that could not finish must be reported as
incomplete, not passed.

## Code blocks

Language-tagged fences get syntax highlighting automatically:

````typst
```python
def normalize(values):
    return values / values.max()
```
````

Use `python`, `bash`, `json`, or another supported language after the opening
fence. Untagged or unknown languages display literal monospace text. Single
backticks keep short identifiers such as `values.max()` inline.

The PDF uses `code.typ` for a light background, padding, a monospace font,
and blocks that can continue across pages. Long lines wrap visually. Word
export (`just docx`) keeps the code editable, preserves its indentation and
line breaks, and applies matching background and font sizing. Typst and
Pandoc use their own syntax palettes, so token colors can differ. Both use
the language tag you supply; neither guesses the language or executes code.

The main manuscript enables the style already. For another document, add
this after its template setup:

```typst
#import "code.typ": code-style
#show: code-style
```

Adjust the import path for a nested document. PDF styling lives in `code.typ`;
Word's corresponding `SourceCode` and `VerbatimChar` styles are set in
`tools/export_docx.py`. Block code stays outside prose metrics and narration; inline
code still counts as words. Captions, numbered listings, and external-file
snippets are not part of this initial support.

## Tracing numbers and assets

Use `just trace <id>` before editing a claim or its supporting asset:

```bash
just trace effect.treated_over_control
just trace fig.example --json
```

`--json` emits exactly one JSON object on stdout. The stable envelope contains
`schema_version` (currently 1), `id`, `status`, `exit_code`, and `findings`.
A completed inspection also returns the declaration, display value for a
statistic, declared input hashes, usage locations (`path`, `line`, `context`),
and suggested commands. Findings carry stable rule IDs. Suggestions are never
executed automatically, and some findings require an author decision instead
of a command.

`status` is `ok`, `failed`, or `incomplete`. `exit_code` is respectively 0, 1,
or 2; an invalid request also uses 2. The underlying Python CLI returns those
codes. `just` collapses failed recipes to a nonzero wrapper status, so agents
should use the JSON fields to distinguish failure from incomplete inspection.
If an ID exists in both manifests, select `--kind stats` or `--kind assets`.

Trace checks recorded consistency. It does not run the analysis or establish
scientific correctness. Usage discovery follows literal calls and literal
Typst includes/imports from the manuscript entrypoints; dynamically computed
IDs and paths are outside that source index. Comments, raw examples, and old
`paper.resolved.typ` output do not count as uses. Missing declared inputs are
reported as incomplete, not silently treated as verified.

The command behavior matters as much as its name:

| Intent | Command | Cost and changes |
|---|---|---|
| Understand one declaration | `just trace <id> --json` | Reads sources/declarations; may refresh the local hash cache; never runs analysis |
| Make a wording pass | `just edit-baseline`, edit, `just edit-check` | Checks literal numbers, helper IDs, citation occurrences, headings, and declarations, including the abstract and literal includes |
| Build deliverables | `just paper`, `just docx` | Writes build artifacts; never regenerates analysis outputs |
| Check current work | `just verify` | Cheap local checks; rebuilds nothing |
| Refresh declared results | `just assets` | Runs analysis and updates tracked generated outputs; potentially expensive |
| Check a submission | `just preflight` | Builds outputs, runs gates and deep statistics, and requires online bibliography checks to complete |

The edit guard protects mechanical invariants, not prose meaning. Numeric
statements may be dropped, but new or substituted statistic calls, changed
asset calls, and edited declarations fail. Snapshots from before this protection
was added must be recorded again before starting another pass.

## Project scope

The scaffold supports writing and checking a manuscript, linking claims to
declared results, and producing deliverables. Agents use the same source files
and commands as authors, with shared skills for the recurring workflows.
Keep changes focused on concrete manuscript problems and preserve the cheap
local checks, generated-file ownership, and existing export paths.

## Reviewing changes between versions

Save the version you have finished reviewing, then compare after editing:

```bash
just review-baseline reviewed
# Edit prose or regenerate analysis outputs.
just review reviewed
```

Open `.review/review.html`. It shows the previous and current passages side by
side, highlights added and removed words, and includes tables, equations,
captions, figures, and the reference list. The section navigator shows where each edit belongs; **Next** / **Previous**
(or **J** / **K**) move between edits. **Content edits** hides automatic citation
renumbering; choose **All changes** to include it or **Full paper** for context.
Changed numbers are highlighted as complete values. Unchanged passages appear
once in Full paper mode. A changed number is
visible even when its `#s("id")` call did not change. Figures are stored with
each version, so overwriting a plot does not change what the old version shows.
Soft line wrapping does not count as a writing edit. Citation renumbering is
distinguished from changing the cited work. Moved passages may appear as a
removal and an addition; formatting rules and page layout are not compared.

`just review-versions` lists saved names without rebuilding.

Names are permanent: a command refuses to overwrite an existing version. To
compare two saved versions, use `just review reviewed revised`. Saved versions
live in `.review/versions/`, outside the disposable `.build-state/` cache.
They are local and gitignored; back up `.review/` if you want to retain this
review history. New papers do not inherit it. Neither review command reruns
analysis. Saving or comparing against current work makes a fresh strict build,
so unresolved notes and missing inputs fail visibly.

PDF, Word, and review now share a captured intermediate manuscript under
`.build-state/manuscripts/<id>/`. Its `paper.typ` contains resolved literal
statistic calls and asset paths while retaining Typst imports, include scopes,
labels, equations, and layout rules. It includes copies of the input files.
Typst supplies the actual heading and float numbers for the Word adaptation.
`paper.word.typ` is that adaptation; the root `paper.resolved.typ` remains a
convenient preview of it. Both are generated and must not be hand-edited.
`just resolve` refreshes this intermediate and its PDF.

`just paper` overlaps PDF compilation with the independent Word/review
preparation, then runs word count and readability together. Reports still
appear in order. Word front matter and numbering share one fresh Typst query.
Every invocation builds fresh, and both preparation paths
must succeed before the PDF is published; source-change and concurrent-build
checks remain in place.

The snapshot manifest records input and output hashes and the Typst version.
The HTML report embeds images and works offline. Recompiling a saved source tree
still requires the external toolchain, fonts, and Typst packages; a snapshot
does not vendor those. Custom Typst constructs must be supported by the Word
adapter as well as Typst. A mismatch in exported figures or heading numbering
fails the shared build rather than silently omitting content.

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
opposite failed; HISTORY.md records which failure produced which line. The
rest of this guide is the long form — skim the section heads and read the
ones you are about to touch.

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

## The parts worth understanding

### `config.typ` is the only place the paper's identity lives

Title, authors, affiliations, abstract, keywords, date, institution, and
bibliography style. The PDF template reads it, the Word front matter is derived
from it (including the numbered affiliation superscripts, so they cannot drift),
the word counter counts the abstract out of it, and `audio/config.py` parses the
title out of it so the narration can never announce a title the paper no longer
has.

### The BODY START / BODY END markers

`paper.typ` carries two marker comments:

```typst
// >>> BODY START
= Introduction
...
// <<< BODY END
```

Three tools slice the prose out at those markers, because "what counts as the
paper's prose" is not the whole file: the front matter, the back matter, the
acknowledgments, and the bibliography all have to be excluded from a journal word
count, a reading-level score, and a narration. Each tool fails loudly if the
markers go missing rather than guessing. Do not delete them.

### Two reference lists: the SI carries its own

The Supporting Information goes to the journal as its own file, so it needs its
own reference list. Typst allows exactly one native `#bibliography` per
document ("multiple bibliographies are not yet supported"), and the SI is
compiled as an appendix to the main text so cross-references resolve across
both halves. The SI's list therefore comes from
[Alexandria](https://typst.app/universe/package/alexandria), which routes
citations to it **by prefix**:

```typst
// paper.typ, once, above the template
#show: alexandria(prefix: "si-", read: p => read(p))

// si-body.typ, last in the file
#set heading(numbering: none)
#bibliographyx(
  "references.bib",
  prefix: "si-",
  title: [References],
  style: paper-bib-style,
) <si-references>
```

Cite `@si-key` in `si-body.typ` and `@key` in `paper.typ`. Both lists number
from 1, and each prints only the works its own half cites; one work cited in
both appears in both, with a different number in each. Both read the same
`references.bib` — one bibliography file, two lists — so `just bib-audit`,
the duplicate-DOI check and the uncited-entry check all keep working
unchanged.

**The failure this arrangement has, and what catches it.** A bare `@key` in
the SI compiles, renders an ordinary superscript, and quietly joins the MAIN
reference list, where a reader of the separately submitted SI cannot follow
it. Nothing on the page says so. `just prose-check` reports it as
`misrouted-citation`, and reports the two prefixes drifting apart as
`si-bibliography-prefix` (Typst refuses that too, but from inside the
Alexandria package, pointing at neither line).

The SI's list is excluded from the SI word count (the `<si-references>` label,
in `wordcount.typ`), dropped by the readability report and the narrator, and
omitted from the plain-text review copy, exactly as the main list is. `just
docx` sets both lists, one citeproc run each.

A manuscript that wants one list deletes the show rule and the
`#bibliographyx` call and writes plain `@key` throughout; every tool then
behaves as it did before this existed.

### Slide decks reuse the paper's material, and are outside the gate

A talk is made from the same figures and the same numbers as the paper, so it
is built from the same declarations rather than retyped. A deck lives in
`slides/`, is built by name (`just slides talk` -> `slides/talk.pdf`), and gets
four things from the manuscript:

| In a deck | Comes from |
|---|---|
| `#s("id")` | `stats.json`, the same number the paper prints |
| `#fig("fig.id")`, `#tbl("tbl.id")` | `assets.json`, so `just assets` updates the talk too |
| `@key` | `references.bib`, listed by `#deck-references()` |
| title, authors, institution, date | `slides/config.typ` — the talks' own |

The first three are the manuscript's, by id, and are checked: a slide that
restates a number gets the number the paper prints. The identity is separate,
in `slides/config.typ`, because a talk title is usually not the paper title, the
author line drops affiliation superscripts, and the date is the seminar's. One
deck that differs overrides at its call site
(`#show: deck.with(title: [...], date: "...")`); the file is what every other
deck starts from. The trade is stated where it is made: a deck *can* disagree
with the paper about its title and nothing checks that, while a number is the
opposite, because a wrong number is a wrong claim and a shorter title is just a
title. Keeping them separate is also what lets a deck build in a
`manuscript.toml` project (see [MULTI-DOCUMENT.md](MULTI-DOCUMENT.md)), which
has no root `config.typ` at all.

`slides/theme.typ` is the only place Touying is configured: the theme, the
section furniture, handout mode and the references slide. A deck imports that
one file, and `slides/theme.typ` and `slides/config.typ` are the two files under
`slides/` that are not decks — `just slides` never tries to build either.

**Decks are outside the gate, deliberately.** A stale deck does not fail
`just verify` or `just check`, and an unformatted one does not either (hence
`just slides-fmt` rather than adding decks to `typst_sources`, since
`fmt-check` runs inside `verify`). A talk falls behind the moment a sentence
changes, the fix costs one recompile, and a nag that is almost always present
is one people learn to scroll past — the same reasoning that keeps `just viz`
and the audiobooks out. Ask deliberately, with `just slides-check`.

What a deck *is* held to, every time:

- **Its ids must resolve.** `#s("effect.typo")` fails the deck's compile exactly
  as it fails the paper's.
- **`just check-stats` counts a deck as a reader**, so a number quoted only in a
  talk stops being reported as declared-but-unread, and `just trace <id>` lists
  the deck among the use sites.
- **`just check-assets` counts a deck as a reference**, so a figure shown only
  in a talk is not an orphan. An id a deck references but `assets.json` does not
  declare is a *warning* naming `just slides-check`, not the error the same
  mistake is in the manuscript — a half-written talk must not be able to fail
  the manuscript's gate.
- **Four prose rules**, under `just slides-check`: em dashes, British spellings,
  doubled words, and a numeral typed where the analysis already computes it.
  Every rule that judges sentences is off, because slide text is fragments: a
  bullet has no terminal punctuation, so the sentence splitter reads a whole
  slide as one enormous sentence and `long-sentence` fires on everything. The
  rule ids are the manuscript's own, so `prose-check.toml` suppressions apply
  unchanged.

Slide text is **not** in the journal word count or the readability report.

Handout mode (`just slides-handout`) flattens every `#pause` group to its final
state, and is selected with `--input handout=true` rather than by editing the
deck. `#speaker-note[...]` stays out of the presented PDF and exports to a
`.pdfpc` sidecar with `just slides-notes`. `#show: appendix` starts backup
slides and freezes the slide counter, so the footer keeps reading the length of
the talk you gave.

Touying's nicer citation mode — a footnote on the slide that makes the claim —
is deliberately not used: touying 0.6.1 targets Typst 0.12 and recovers the
entries through a `grid` show rule that Typst 0.14 no longer produces. The note
in `slides/theme.typ` says what to change when that is fixed upstream.

### Journal profiles: the venue's limits, with their source

A journal's rules are numbers an author carries in their head and discovers
at submission. Here they live in one file per venue and manuscript type under
`journals/`, and `journal.toml` picks one:

```toml
profile = "jpr-article"
[sections]
methods = "main/Methods"     # the section JPR leaves out of its word count
[placement]
pdf = "preprint"             # graphical abstract under the abstract
docx = "journal"             # ... or on the last page, labeled as ACS asks
```

Four ship: `jpr-article`, `jpr-technical-note`, `jasms-article`, and
`jasms-technical-note`. Every profile carries the URL its numbers were read
from, the date the journal printed on those guidelines, and the date they were
read; a profile without all three does not load. When a limit changes, re-read
the source, change the number, and move `checked`. `[notes]` quotes the
journal's own sentence beside each rule, so `just journal` can show the rule
and its wording together.

Nothing here is a second checker. The profile's word limits join
`word-limits.toml`'s checks in `just check-words`, so one table answers "am I
within limits" whoever set them. Its figure resolution floor joins
`prose-check.toml`'s `min-figure-dpi` in `just prose-check`, beneath the
project's own value. `just check-journal`, inside `verify`, covers what neither
does: the keyword count in `config.typ`, the figures and tables in the main
text (the SI does not count, which is the journal's own distinction and the
BODY markers' too), and the graphical abstract measured against the journal's
box. A section a profile refers to by role, such as the experimental section
JPR excludes, is mapped to this manuscript's section path in `[sections]`, and
an unmapped role is a loud error naming the fix. A limit that covers the
reference list, as JASMS's Technical Note limit does, selects the
`references` region: the main text's list as citeproc sets it from
`references.bib` and the CSL for the Word file, which is what the journal
counts, rendered to plain text through pandoc and counted like everything
else. `just wordcount` shows it as its own row; the PDF's list is Typst's
rendering and differs by a few words of punctuation.

**The graphical abstract** is the one thing a profile changes about the output
rather than the checks. `paper.typ` declares it once, as `#let toc-graphic =
fig("fig.toc", width: 3.25in)` with an optional `toc-caption`, and
`[placement]` says where each output renders it: `preprint` under the abstract,
front and center, as an archive server shows it; `journal` on the last page of
the main manuscript, before the SI, under the heading "For Table of Contents
Only" that ACS prescribes; `none` nowhere. The build passes the choice to the
PDF as `--input toc=...` and to the Word resolver as `--toc`, so the two
outputs differ without the source changing, and a placement change marks both
outputs stale. The defaults are preprint for the PDF and journal for the Word
file, because that is where each one goes. The shipped graphic is generated
by `analysis/scripts/gen_toc_figure.py` at exactly the ACS box, 975 x 525 px;
a graphic drawn by hand goes under `figures/`, is declared with `just adopt`,
and is referenced the same way.

What is deliberately not checked: figure widths against the journal's column
sizes. The PDF here is the arkheion layout, not the journal's, so a physical
width check would be noise until production; the resolution floor covers the
part that actually bites.

### The `si/` contract: generated tables, never hand-typed numbers

Tables whose numbers come from an analysis are written by a script into
`si/*.typ` as a bare `#table(...)`, and `si-body.typ` wraps them in a `#figure`
that supplies the caption and label. Every generated file opens with a
"do not edit by hand" header.

`analysis/scripts/gen_example_table.py` is the template. Copy it per table.
`just assets` runs every `gen_*_table.py`, so the *discovery* needs no wiring
beyond matching the filename pattern.

**It does need wiring beyond that, and it is worth knowing before you start.**
Adding a figure or table is four steps, not one:

1. Copy the example generator, keep the `gen_*_figure.py` / `gen_*_table.py`
   name, and write into `figures/` or `si/`.
2. Call `record("fig.yourname", …, kind="figure", inputs=[…])` at the end of it.
   That declares the id; `inputs` is the data it read.
3. Reference it in the prose by id, not by filename:
   `#figure(fig("fig.yourname"), caption: [...]) <fig:yourname>`.
4. If this is the project's first one, add `fig`/`tbl` to `wordcount.typ`'s eval
   scope. Missing this leaves `just paper` working and only `just wordcount`
   failing, which is the least obvious way for it to break.

Step 2 is what buys the per-file staleness checking, and step 3 is what stops the
manifest rotting into a ledger nobody reads. Neither is free, and the trade is
deliberate.

The point is that a number in the manuscript should be traceable to the analysis
that produced it. Re-run the analysis and the manuscript updates.

### Numbers in prose: `#s("id")`, not a typed numeral

A table tracks the analysis because a script writes it. A number in a *sentence*
is typed by hand, and that is where drift lives: a unit error, a percentage
stale after a re-run, a value fixed in the table but not in the paragraph beside
it.

`analysis/scripts/gen_stats.py` declares the numbers the prose states and writes
them into `stats.json`. The manuscript reads them back:

```typst
the treated group scored #s("effect.treated_over_control") over control
```

Three things make it hold:

- **An unknown id fails the build.** `#s(...)` panics at compile time, so a
  number that stops existing is loud rather than blank. `tools/readability.py` and the
  narrator resolve the same call, because they read the source, not the PDF.
- **Guards run when the file is generated.** Each entry's `expect` block can
  assert a sign or a plausibility band. If a sentence says "fell" and a re-run
  turns the value positive, `just assets` fails and names the assumption,
  instead of the paper shipping "fell by -3.1%". A band catches the unit error.
  The fresh value is judged against the guard *as it stands in `stats.json`* —
  the author's — not against whatever the script happened to pass.
- **`just prose-check` flags a typed numeral** — one that matches a declared
  value (use `#s()` instead), and one that matches *nothing* declared, which is
  worse: mistyped, stale from an earlier draft, or from a source nobody
  recorded. Four ways out, each leaving a trail: compute it (`#s()`), declare
  it by hand with a note, vouch for it in place with `#lit("40")` when it is
  genuinely just prose, or suppress the value in `prose-check.toml` with a
  written reason. `lit()` deliberately does not silence the first rule — a
  computed value wrapped in it is still flagged. Years and short counts are
  skipped, and prose-check reports how many literals are vouched inline, so
  the count cannot grow silently.
- **`just check-stats` re-checks the committed file, without running anything.**
  Every guard is re-run against the values as they sit in `stats.json`; each
  generated value is compared to the checksum its generator recorded, so a
  hand-edit is caught; and the `sources` block hashes the code and data behind
  the numbers, so "the analysis moved" is answered in milliseconds. The guards
  above only fire while the generator runs, which does nothing for a value edited
  afterwards.
- **`just check-stats-deep` re-runs the generator and diffs.** Stronger — it
  recomputes from the data rather than comparing fingerprints — and it costs
  whatever your analysis costs, so it is deliberately not part of `just verify`.
  `verify` must rebuild nothing; run this before submitting.

### stats.json is yours, not just the analysis's

The split is by field, and it follows what each field *is*. The script owns the
`value` — a fact about the data, which nobody else can honestly write — plus
the `checksum` that catches a hand-edit to it and the `origin` that says who
wrote it and when it last changed. Everything else in an entry is the author's,
edited in `stats.json` directly:

- `fmt` and `unit` — how the number is shown. An editorial choice, not an
  analysis result.
- `desc` — what the number is, for whoever audits the file later.
- `expect` — what the *prose* assumes ("fell", "roughly 80–90%"). That
  assumption lives next to the sentence, so the author maintains it. A
  one-sided bound (`min` with no `max`) is fine.

The arguments to `st.add(...)` beyond the value are seeds: they fill in a new
entry so the file is never born empty, and are ignored once the entry exists —
with a note when they differ from the file, so a stale script argument is
visible rather than silently dead.

Every entry also records `origin.by`: the script that generated it, or
`"hand"`. A generator rewrites only its own entries, so a number you add by
hand survives `just assets` instead of being silently overwritten by it.
`origin.at` is when the value last *changed* — a re-run that reproduces the
same number leaves it alone, so the date means something.

```json
"cohort.sites": {
  "value": 4, "fmt": "",
  "expect": {"sign": "+"},
  "origin": {"by": "hand", "note": "study protocol v3, Table 1"}
}
```

A hand entry must carry `origin.note` saying where the number came from, and it
is guarded exactly as tightly as a derived one. What it cannot get is
re-derivation: `check-stats-deep` recomputes generated values from the data and
compares, and nothing can do that for a number that came off a printout. The
note is the audit trail instead.

That is also why `stats.json` sits at the manuscript root rather than under
`si/`: a file you are invited to edit is not generated output, and cannot be
guarded by "did anything change".

### Pinned files: watching what no script reads

Provenance the pipeline records automatically stops at what a generator
imported or declared. Plenty of files matter without any script reading them —
a raw instrument export, a protocol document, an upstream config. Declare those
by hand in `stats.json`:

```json
"pinned": {
  "analysis/data/raw_export_2026-06.csv": null
}
```

`just pin` records the sha256, and from then on `just check-stats` (so `just
verify`) reports when the file changes. The fix it names is deliberate: check
the numbers that depend on it, then `just pin` again to accept the new state.
Generators carry the block through untouched — declaring what is worth watching
is the author's call, made in the file.

**`stats.json` stores no rendered string.** It holds the `value` and the `fmt`;
`tools/render_stats.py` turns them into `stats-rendered.json`, which is what
`stats.typ` reads. Every recipe that compiles regenerates it first, and it is
gitignored, so it can never be stale and never disagrees with its source.

That step exists because Typst has no format spec — no thousands separator, no
`+.2f` — and its `str()` rounds floats where Python's does not
(`1.0899999999999999` is `1.09` there, the full expansion here). Doing the
formatting in the document would mean reimplementing Python's spec in a language
that cannot express it, and storing the result beside the value would put a
derived field in a source file, free to drift.

One formatter, `typst_prose.display_of`, is used by the renderer *and* by the
word count and the narrator, so the PDF and the extractors cannot disagree about
what a number looks like.

While ids are still in flux, `just draft` renders an unresolved one as a loud
`?id?` placeholder instead of stopping the compile, and writes `paper-draft.pdf`
so a placeholder can never reach the real PDF. `n("id")` fails even there: no
placeholder can stand in for a number inside an expression without making the
arithmetic that reads it silently wrong.

Available in the SI as well as the main text. `si-body.typ` imports the helpers
itself rather than inheriting them, because Typst's `include` gives the included
file its own scope: without that import an `#s("id")` in the SI fails with
`unknown variable: s` even though `paper.typ` imports it one line above the
include. The SI is the data-heavy half, so it is where generated numbers belong
most.

To drop the mechanism from a project that states no computed numbers, four steps.
Typst has no conditional import and no way to ask whether a file exists, so the
references have to come out by hand; each one is commented to say so.

```bash
rm stats.typ stats.json analysis/scripts/gen_stats.py
```

1. Delete the `#import "stats.typ": n, s` line from **`paper.typ`,
   `si-body.typ` and `wordcount.typ`**. All three carry it.
2. In `wordcount.typ`, also drop the helpers from the eval scope:
   `scope: (refn: refn, s: s, n: n, fig: asset-fig, tbl: asset-tbl)` becomes
   `scope: (refn: refn, fig: asset-fig, tbl: asset-tbl)`. The import alone is not
   enough — this line names them again, and missing it is the one that bites,
   because `just paper` still works and only `just wordcount` fails.
3. Remove any `#s()` / `#n()` calls left in the prose.

The generated-**assets** mechanism comes out the same way and separately:

```bash
rm assets.typ assets.json
```

Delete the `#import "assets.typ": fig, tbl` line from `paper.typ` and
`si-body.typ`, drop `fig: asset-fig, tbl: asset-tbl` (and the import above it)
from `wordcount.typ`, remove the `record(...)` calls from the generators in
`analysis/scripts/`, and go back to naming files directly:
`#figure(image("figures/x.png"), ...)`.

Verified by doing exactly this to a copy and confirming `just paper`,
`just wordcount`, `just readability` and the narration all still work.

### Figures and tables by id: `fig("fig.x")`, not a filename

The same contract as numbers, for files. Each generator calls `record(...)` to
declare what it wrote, into `assets.json`:

```json
"fig.example": {
  "path": "figures/example_figure.png",
  "kind": "figure",
  "hash": "sha256:b100e70d…",
  "origin": {"by": "analysis/scripts/gen_example_figure.py",
             "at": "2026-08-06T18:20:00Z"},
  "inputs": {
    "analysis/scripts/gen_example_figure.py": "sha256:1b2fcdf2…",
    "analysis/scripts/example_data.csv":      "sha256:c19c8377…"
  }
}
```

and the manuscript references the id rather than the path:

```typst
#figure(fig("fig.example", width: 70%), caption: [...]) <fig:example>
```

**Referencing by id is what makes the manifest worth having.** A manifest that
merely sits beside the files it describes rots, because nothing reads it. This
one is on the path the compile takes, so an undeclared id stops the build the
same way an undeclared `#s("id")` does — it cannot quietly stop being true.
`just prose-check` reports naming a declared asset directly as an error, which is
what keeps the bypass closed.

`just check-assets` then checks per entry: the output still hashes to
what was recorded (so a hand-edit to a generated file is caught and *attributed*),
the generator still exists, and the declared inputs are unchanged. `origin.at`
is when the output last *changed*: a regeneration that produces byte-identical
output (seeded RNG, no embedded timestamps) keeps the old date, so the
timestamp carries information.

Inputs are part automatic, part declared. The generator and every module it
imports from `analysis/` are recorded by walking `sys.modules`, which is exact
because imports are always Python-level. **Data files are declared by hand**
(`inputs=[...]`), because the automatic version is not exact: an audit hook on
`open` cannot see reads that HDF5, parquet and most binary readers do from C, and
would record an empty input set for precisely the formats that matter. A missed
input means a stale figure reported as current, so that half stays explicit.

An input that is not present — the normal state of a fresh clone, since
`analysis/data/` is untracked — is reported as unverified, never as stale.

This replaced `.assets-stamp`, a pair of whole-tree hashes that fired on the same
failures and could only report "analysis/ has changed" without naming the figure
it ruined — and that also fired on a new file no generator imports, a change
which by definition altered no output.

What went with it: **an input a generator reads without declaring or importing is
now invisible.** Nothing checks it — and nothing meaningfully did before. The
stamp excluded `analysis/data/`, so whether it caught an undeclared read depended
on where the file sat, not on whether it mattered.

There is no automatic answer that is actually right: an audit hook cannot see
C-level reads, a directory hash misses anything outside it and fires on changes
that altered nothing. So the scaffold no longer pretends to have one. **Which
files are worth tracking is the author's call**, declared in `inputs=[...]`, and
`record()` prints a note when a generator declares none — the omission is visible
where it is made rather than discovered from a wrong figure.

### `analysis/` lives inside the manuscript, and writes to it directly

The analysis that produces the numbers is a subdirectory, not a sibling
repository. It writes its figures into `figures/` and its tables into `si/` with
no staging copy in between.

That last part is the point. A copy is the single most reliable way for a
manuscript to go quietly wrong: a re-analysis updates the plot upstream, the copy
in `figures/` is untouched, and the PDF keeps rendering a figure that no longer
matches the numbers in its own caption. Writing to the destination removes the
failure rather than adding a guard for it.

**The location is load-bearing, not a taste.** The provenance machinery
resolves the manuscript root as `analysis/scripts/../..`, and the
`sys.modules` walk keeps exactly the modules whose paths start with
`analysis/`. An analysis kept as a sibling repository means forking those
tools, not just re-pointing a path — if you are migrating an existing paper,
moving the analysis under the manuscript is what lets the scaffold work
unmodified. (And if the repository publishes a package or crate, check its
include/exclude list afterwards: a newly nested analysis tree can quietly ship
to a registry.)

**The contract is one recipe.** `analysis/justfile` exposes `assets`, which
regenerates everything the manuscript includes. `just assets` at the top level
delegates to it and knows nothing else. Whatever is inside `analysis/` is that
project's business: sixty numbered scripts, one notebook, a Snakemake pipeline.
Keep `assets` as the front door and the manuscript never has to care.

A paper with no computed results simply has no `analysis/` directory, and the
recipes say so instead of failing.

`figures/` and `si/` are generated but **tracked**, so a fresh clone compiles
without re-running an analysis that may take hours. (`paper.pdf` is not tracked —
see below.) `just check-assets` guards them per file through `assets.json`: each
entry records a hash of the output and of every input its generator declared, so
editing a generator and forgetting to re-run it is reported — with the figure and
the script named.

Hashes rather than commit dates, because the generators are deterministic on
purpose. Re-running one after an edit that does not move the output produces no
new commit, and a date-based check would then nag with no way to satisfy it.

### `just check` reports staleness; `just preflight` gates a submission

`just check` exits non-zero if anything is stale, and covers the failure modes
that actually happen:

- `paper.pdf` or `paper.docx` built from sources that have since changed. `just
  paper` and `just docx` record the hash of what they rendered in `.build-state/`;
  `just check-build` recompares it. Hashes are captured before rendering stats
  or resolving exports, and checked again before replacing the deliverable.
  A source edit during the build preserves the last good output and fails.
  Compiler dependencies, included chapters, CSL files, and the Word filter
  participate in the check. Concurrent manuscript builds are refused.
- An output that is **not the file that build produced** — overwritten,
  truncated, or restored from somewhere else. The stamp records the output's own
  hash too; without it, a `paper.pdf` copied in from Downloads passes as
  current, because the source stamp only proves a build happened.

The declaration checks in `just verify` also compare generated figures, tables,
and statistics against their recorded code, data, and analysis environment.

`just preflight` is the day-of-submission command: fresh builds of both
outputs, the whole `verify` gate, `check-stats-deep` (re-derives every
generated number from the analysis and diffs), and `bib-audit` (every DOI's
title, authors and publication details against Crossref or DataCite, plus
retractions and dead links). Those last two are too slow and too network-bound
for `verify`, and "run them before submitting" scattered across the docs is a
ritual — this is the ritual as one command.

Preflight requires a completed DOI audit (`bib-audit --require-complete`).
Network failures cannot produce a successful submission gate. The standalone
audit remains tolerant of an offline connection. A deep statistics check that
cannot run or obtain a fresh writer receipt also exits nonzero; it never treats
a copy of the old values as proof of regeneration.

The DOI audit does not mistake a resolving link for a verified citation. It
compares each entry with the metadata registered by the publisher: title,
author order, and year mismatches fail; venue, volume, issue, and page
differences are printed for review because online-first and print records often
differ there. Comparisons ignore capitalization, punctuation, markup, initials
versus full given names, and the different dashes used for BibTeX page ranges.
If a registrar omitted a field, the audit says nothing about that field rather
than pretending it verified information it never received.

**Neither output is tracked in git**, and neither is `.build-state/`. Git keeps
every version of a binary forever, a clone pays for all of them, and removing one
means rewriting history. Ship the PDF as a release asset or a CI artifact.

That is also why staleness is a content hash rather than a commit date: nothing
here reads git history any more, so the checks work in an exported tree, a shallow
clone, or no repository at all. `.build-state/` stays untracked because it
describes *local* build output — tracking it would let a rebuild on one machine
report every other checkout stale.

The audiobooks are deliberately not checked. Every prose edit would mark them
stale and clearing that costs minutes of narration, so the warning was almost
always present and almost never acted on.

### The Word export is more delicate than it looks

The native paper exporter now uses `word/paper-reference.docx` for reusable Word
styles. Edit that file in Word to change headings, body text, captions or code;
builds preserve those changes. The template has single-spaced image paragraphs
and references, and removes conflicting theme settings where concrete fonts or
colors are specified. Template edits invalidate the build fingerprint.
`uv run python tools/paper_word_reference.py` explicitly resets this template;
normal builds never regenerate it. Older projects without the file retain the
existing code-style fallback. The legacy HTML exporter does not use this template.
`--black-headings` sets the title and headings in black instead of blue.

After pandoc writes the file, `export_docx.paginate` sets the keep rules the
PDF follows without being told: a table row never splits, a short table stays
on one page, a caption stays with its figure or table, and a page break
starts the next paragraph instead of standing alone as an empty one. Column
widths come from the source: `columns: (2fr, 1fr, 1fr)` reaches Word as
proportional widths, while `columns: 3` is left for Word to size.
`uv run python tools/export_docx.py --main-only` (after `just docx`) writes
`paper-main.docx` without the SI, for journals that take the SI as a separate
upload. Optional `paper-running-title`, `paper-corresponding-email` and
`paper-corresponding-phone` bindings in `config.typ` add those lines to the
Word front matter. The author whose `email:` matches the corresponding email
gets a star.
For multi-chapter Word exports, see [MULTI-DOCUMENT.md](MULTI-DOCUMENT.md).


`just docx` goes `just resolve` → pandoc's native Typst reader. The resolver
replaces every project helper (`#s()`, `fig()`, cross-references, the
bibliography's style variable) with plain Typst in `paper.resolved.typ`, and
pandoc — a real evaluator, from `uv` (`pypandoc-binary`), no system install —
turns that into **native, editable Word equations**, real tables, and a
reference list set by citeproc from `references.bib`. A manuscript whose SI
carries its own list gets both: citeproc sets one list per run, so each
stretch of the projection is converted separately and the Pandoc trees are
joined, with the second list's anchors renamed so a work cited in both halves
is not two Word bookmarks with one id. Citations follow
`<style>.csl` in the manuscript root when present (the scaffold ships
`american-chemical-society.csl`, matching the default `paper-bib-style`);
otherwise pandoc's default applies, with a printed note. Every citation key is
checked against the `.bib` before converting, because citeproc renders a
missing one as bold prose and still exits 0. When the output looks wrong, read
`paper.resolved.typ` — it is exactly what pandoc was fed.

This is the only Word route. The one it replaced went Typst → HTML → pandoc,
and is recorded under "Decisions reversed" in HISTORY.md. The PDF path is
entirely unaffected by the export.

### Formatting: the editor and the CLI must agree

`just fmt` runs [typstyle](https://github.com/Enter-tainer/typstyle), which is the
same engine the [tinymist](https://marketplace.visualstudio.com/items?itemName=myriad-dreamin.tinymist)
editor extension uses as its formatter backend. So format-on-save and `just fmt`
can produce byte-identical output, but only if they are configured identically,
and by default they are not:

| | tinymist default | `just fmt` |
|---|---|---|
| Line width | 120 | `fmt_width` (80) |
| Prose wrapping | off | on (`--wrap-text`) |

Left alone, every save reflows the manuscript one way and every `just fmt`
reflows it back, producing a churning diff that neither tool owns. The committed
`.vscode/settings.json` pins `tinymist.formatterPrintWidth` and
`tinymist.formatterProseWrap` to match the justfile. If you change `fmt_width`,
change both.

`--wrap-text` is the flag that matters for a manuscript: without it typstyle
formats code and leaves markup lines however long they already were, and in a
paper the long lines are the prose.

| Command | Does |
|---|---|
| `just fmt` | Reflow the hand-written sources in place |
| `just fmt-check` | Exit non-zero if reformatting is needed (CI / pre-commit gate) |

`typst_sources` deliberately excludes `si/*.typ`, which the generator scripts own
and would rewrite unformatted on the next run. `.vscode/settings.json` marks them
read-only in the editor for the same reason.

**Reformatting can break the prose extractors.** typstyle will break a long line
*inside* a function call or an emphasis pair, turning `#refn(<sec:methods>)` and
`_Saccharomyces cerevisiae_` into three-line forms. Any stripper regex written for
the one-line version then leaks a bare `#refn(` into the word count and the
narration, or leaves the literal underscores for the voice to pronounce. Both
happened in the manuscript this scaffold came from, and the PDF looked fine
throughout.

`tests/fixture.typ` carries a case for each, and `just test` asserts the extracted
prose is unchanged by a reflow. Add a case there when you add a construct.

The recognition patterns those checks protect (`#refn(`, `#link(`, emphasis, and
the balanced-paren stripper) live in `tools/typst_prose.py`, imported by both
`tools/readability.py` and `audio/extract_prose.py`. They are shared because keeping
them in two files meant fixing each of those three bugs twice.

### Reading the prose metrics

Four commands look at the writing rather than the build.

`just readability` is Flesch-Kincaid and friends. Useful, but it only knows word
length and sentence length.

`just density` counts what FK is blind to and what actually makes a Results
section unreadable: numerals, parentheticals (and what fraction of the words sit
inside them), acronyms, nominalizations, passives, and hedges, all per 1,000
words. **Read it relatively, not absolutely.** There is no published limit for any
of these and anyone quoting one is guessing, so the second table flags sections
that depart from *this paper's own median* by 1.6x. A Methods section running at
three times your own parenthetical rate is a real signal you can act on.

`just prose-check` enforces the mechanical rules in STYLE.md and adds two
structural checks. Anything this project has earned an exception to goes in
`prose-check.toml` (see below). A figure or table that no text ever references is an error,
since most journals require every one to be cited and a reader who is never sent
to a figure will not look at it. Two more are warnings: figures cited out of
numerical order (a copy-editing return at many journals, but a conventions
paragraph legitimately forward-references, so it does not gate), and an acronym
used repeatedly but never expanded (what counts as common knowledge is
field-specific).

### Vocabulary review: `just word-audit`

`just word-audit` reads current sources and watches 111 exact word forms: the
original 21 from Juzek and Ward's
[COLING 2025 study](https://aclanthology.org/2025.coling-main.426/), Appendix A,
Table 2, plus an editorial selection of 45 style words from
[Kobak et al.'s annotated dataset](https://github.com/berenslab/llm-excess-vocab/blob/main/results/excess_words.csv).
An author-preference group contains 17 words, including `tractable`, `robust`,
and `parsimonious`. Another group adds 28 explicit word-family extensions,
including `leveraged`, `underscored`, and `tractability`. Both are recorded as
editorial choices without claiming research evidence for each added form.
Preserve precise technical uses, such as computational tractability; review
vague uses in context. Editorial sources require a citation, location, and
explanatory note rather than a research URL.

The original list and the separately attributed `[[extensions]]` groups live in
`word-watchlist.toml`. JSON findings identify their source groups, and the
report includes all sources. The expansion is not a published ranking.
Inflections such as `delve`, `delves`, `delved`, and `delving` remain separate,
as in the published analysis. Other forms are not silently added or stemmed.

The report combines the abstract, main text, and SI into one manuscript total.
It shows the total number of flagged word occurrences, the number of distinct
flagged words, and a per-word count sorted from most to least frequent. Every
occurrence counts, including a single use and uses spread across paragraphs or
sections. There are no frequency thresholds, rates, or paragraph-based warnings.
Matches are case-insensitive whole tokens; hyphenated compounds and words with
apostrophes stay intact. Counts use letter-based tokens, not the journal word
count. Headings, citations, references, code, equations, figures, tables, and
captions are excluded. Literal includes are followed; missing, cyclic, and
dynamic includes fail visibly. Like the existing prose metrics, this is a
source scan, not a Typst evaluator: computed prose and custom macros may need
manual review. The abstract must use `#let paper-abstract = [...]`.

The study concerns scientific abstracts and older models; applying the list to
full manuscripts is an editorial extension. No finding establishes AI
authorship, predicts a detector result, or requires changing a technical term.

Run it before and after a wording pass. `just word-audit --json` prints the
counts and source metadata for comparing drafts (report schema version 2).
Exceptions belong in the manifest's `[allow]` table, mapping a watched word to
a written reason. Allowed occurrences remain visible but are excluded from
the flagged total and counted separately. Manifest schema version 2 removes
the old `[limits]` table; old threshold configurations are rejected rather than
silently ignored. No manuscript text is edited and no model or network call is
made. Counts are advisory, never a pass/fail score; invalid configuration or
unreadable sources fail. The audit is not part of `verify`.

For `manuscript.toml` projects, the audit combines the default document's declared
parts. Use `just word-audit --document NAME` or `--document all` to choose targets.
With `all`, each target gets its own total, so shared parts in alternative exports
are not added into one inflated total. Abstracts in this mode are counted only
when they are included in a declared part's body.

### Suppressing a finding: `prose-check.toml`

Every finding carries a stable rule id and, where the rule is about a particular
value, the value that triggered it. A project silences one by naming both:

```toml
disable = ["semicolon-count"]        # a whole rule, off

[allow]                              # or just these values
unexpanded-acronym = ["TOF", "DIA-NN"]
british-spelling   = ["Grey"]        # a surname, not a colour
reference-order    = ["fig:si-lowab-retention"]

[limits]
max-sentence-words = 40
```

Three things keep it from becoming a place problems go to hide:

- **Every finding prints its own silencer**, once per rule, so the file is
  discoverable without reading the docs.
- **Suppressions are counted, never silent.** The footer says how many are
  hidden, and `--show-suppressed` lists them.
- **A typo is an error.** `acronym` instead of `unexpanded-acronym` fails with the
  list of valid rules rather than quietly suppressing nothing.

`just prose-check --list-rules` prints every rule, its severity, and what a
suppression matches on. Errors are suppressible too, since a surname or a figure
cited only from elsewhere is a real exception.

### `tests/` is the permanent smoke test

`tests/fixture.typ` is a deliberately dense pile of every construct any extractor
special-cases: citations, both reference forms, emphasis across a line break,
things that only look like markup (`smooth_*`, `"K*,R*"`, `analysis.tdf_bin`),
links, inline and display math, symbol tokens, block code, and figure captions.

`just test` checks three properties: the extracted prose matches
`tests/expected/`, a typstyle reflow changes neither output, and no forbidden
token (a leaked caption, citation key, or call name) appears in the result. `just
test-update` rewrites the golden files, which is also how a regression gets
blessed into the baseline by accident, so read the diff.

This is separate from the manuscript on purpose. Anything relying on placeholder
prose for coverage would be tested once, at clone time, and never again.

Everything else `just test` runs lives in a **case module** beside it — one file
per subject (`stats_cases.py`, `bibliography_cases.py`, `export_cases.py`,
`slide_cases.py`, …), each exporting `run_cases() -> bool`. `run.py` lists them
in `CASE_MODULES`, names the one that failed, and that list is the only place to
edit to add another. Each module owns its own fixtures and runs on its own while
you iterate:

```bash
uv run python tests/stats_cases.py
```

### Audio

Offline Piper TTS. `audio/extract_prose.py` rewrites the Typst source into
speakable text (citations, cross-references, math, `#sym.*` tokens, figure blocks
and code blocks all removed or verbalized), Piper narrates it, and ffmpeg muxes
chapters and cover art into an `.m4b` with one chapter per section.

Everything project-specific is in `audio/config.py`: the voice, the metadata
blurbs, a `PRONUNCIATION` map for words the voice mangles, and a `MATH` map from
inline equations to spoken English. Add every inline equation that appears in
running prose; anything unmapped falls back to reading the raw Typst, which is
usually wrong. Display equations are dropped rather than read.

One inherent trait: stripped cross-references leave sentences like "resolves to
and the bare-number kind" in the narration. Write around it in prose you care
about hearing, or accept it.

The engine is `piper-tts`, a uv dependency in the `audio` group, exactly like
pandoc and ffmpeg elsewhere in this directory: nothing is installed system-wide
and there is no binary to download by hand. **This runs on Linux, both Intel and
Apple Silicon Macs, and Windows.** It previously fetched a piper release tarball
by curl, pinned to a build that shipped x86_64 Linux only, which made the
audiobooks the one part of the scaffold that could not run on a Mac.

The voice model (~60 MB) and every generated audio file are gitignored, so a
fresh clone needs `just audio-setup` once. Change `VOICE_NAME` in
`audio/config.py` and re-run it to switch voices; the name is resolved against
piper's own index, so nothing else has to be kept in step with it.

## Requirements

Install [Typst](https://github.com/typst/typst),
[just](https://github.com/casey/just), [uv](https://docs.astral.sh/uv/), and
[Python 3.10+](https://www.python.org/downloads/) before using the build commands.
The quick start also uses [Git](https://git-scm.com/downloads) to clone the
scaffold and give your manuscript its own version history.

Run `just doctor` and it will tell you which of these you are missing, and
whether the ones you have are new enough.

- `typst` **0.14 or newer**, `just`, `uv`, `python3`
- `typstyle` for `just fmt` and `just fmt-check` (`cargo install typstyle`)
- `git` is **not** required by any check; the staleness checks are content hashes
- a network connection for `just audio-setup` (the voice model) and the first
  PDF build (the `arkheion` template)

The Typst floor is 0.14: the oldest version the pipeline is tested against,
held by a CI matrix. It was first set there because the HTML Word route, since
removed, silently lost every figure on 0.13; it stays because nothing older
has been run through the pandoc route.

`just setup` builds the Python environment from `pyproject.toml` and commits the
resolution to `uv.lock`, so every machine gets the same versions. There are two
environments on purpose: the manuscript toolchain at the root (pandoc, cairosvg,
textstat, small and stable, locked and shipped with the scaffold) and the
analysis in `analysis/pyproject.toml` (whatever the science needs, rewritten per
project). Keeping them apart means a project's churning analysis dependencies do
not invalidate the toolchain lock. The audiobook extras are a `--group audio` so a
clone that never builds audio stays light.

The first PDF build fetches the `arkheion` template from Typst Universe and
caches it.

## Things that will bite you

**Typst line continuations.** A method chain broken across lines after `#let x =`
or inside `[...]` ends at the first newline, and the continuation is read as
literal text. The error is confusing (`unknown variable: a` pointing at a closure
parameter). Wrap multi-line chains in a code block `{ ... }`. `config.typ` has a
worked example.

**Regenerated figures churning bytes.** matplotlib stamps a creation date into
PNG metadata by default, which makes every regeneration look like real drift to
`just check`. The bundled generator passes `metadata={"Software": None}`; do the
same in yours, and seed any RNG.

**The SI is not compiled on its own.** `si-body.typ` is body-only. Its title page,
S-prefixed numbering, and counter resets are applied by `paper.typ` at the include
site, so the whole manuscript is one compilation with one label namespace and
cross-references resolve in both directions.

## Versioning

The scaffold version lives in `pyproject.toml` and is copied into every project
built from it, so `just version` answers "what am I on" from inside a derived
manuscript. [HISTORY.md](HISTORY.md) records what each release contains, what
bumps major/minor/patch, and how to pull a later version's changes into an
existing project.

Read HISTORY.md's "Decisions reversed" section before changing something that
looks obviously improvable. Several obvious improvements were tried here and were
wrong for reasons only visible from use.

## Notes for agents

The working rules for editing a manuscript built on this scaffold are in
[CLAUDE.md](CLAUDE.md): what never to hand-edit, what to run before calling the
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

MIT, see [LICENSE](LICENSE). It covers the scaffold and its tooling, not any
manuscript you write with it. `scripts/new-paper.sh` carries the notice into a
new project as `LICENSE.scaffold`, renamed so that a `LICENSE` at the root of a
manuscript directory does not read as a claim about the paper, which is a
different question and yours to answer.
