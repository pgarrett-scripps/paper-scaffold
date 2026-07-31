# History

What changed in the pipeline, and why. Read the "Decisions reversed" section
before proposing a change that looks obvious. Several obvious things were tried
here and were wrong.

## Versioning

The version lives in one place, `version` in `pyproject.toml`, and travels with
the scaffold when it is copied into a project. `just version` prints it.

What bumps what is judged from the manuscript's point of view, not the code's:

- **Major** breaks a manuscript. An existing `paper.typ`, `si-body.typ`, or
  `analysis/` has to be edited to keep working. Renaming the BODY markers,
  changing where `analysis/` writes, or changing the `si/` include contract are
  all major.
- **Minor** adds a capability without touching an existing manuscript. A new
  check, a new metric, a new recipe.
- **Patch** fixes something without changing the interface. A regex that was
  missing a case, a wrong path, a doc correction.

Tag every release: `git tag -a v1.2.3 -m "..."`.

### Upgrading a project built on an older version

A project carries its version in its own `pyproject.toml`, and this file, both
copied at the time. To upgrade:

```bash
just version                                    # what the project is on
git -C ~/Repos/paper-scaffold log --oneline vOLD..vNEW
git -C ~/Repos/paper-scaffold diff vOLD..vNEW -- justfile *.py tests/
```

Then apply what you want by hand. There is deliberately no automatic upgrade: a
manuscript directory diverges from the scaffold the moment real writing starts,
and a merge tool cannot tell your `paper.typ` from the placeholder it replaced.
Read the major entries below first, since those are the ones that need an edit
rather than a copy.

---

## 1.0.2

Five fixes, all found by porting the scaffold into a second real manuscript
(`koth`). None change an interface; an existing project takes them by copying
`typst_prose.py`, `readability.py`, `prose_check.py` and `tests/`.

**`#ref(<x>)` was not recognized.** `typst_prose.REFN` matched only the
manuscript's own `#refn(` helper. Typst's native `#ref(` is the more natural
thing for an author to write, and koth is written almost entirely in it. The
result was a bare `#ref( )` surviving into the word count, the reading-level
score and the narration, in 68 places, with the PDF correct throughout. `REFN` is
now `#refn?\(`, and `tests/run.py` forbids a leaked `#ref` the way it already
forbade `refn`.

**Reference SITES were counted as float definitions.** `check_reference_order`
scanned for a bare `<fig:x>`, which `#ref(<fig:x>)` and `#refn(<fig:x>)` contain
just as a definition does. Each float was therefore numbered by its LAST
occurrence in the file, so a figure cited twice moved. In koth the checker
believed the main text defined 15 figures, in citation order, and reported a
"Figure 10" that does not exist; there are five. A definition is now a label
following a closing paren, which is where Typst attaches one. The same scan in
`check_structure` had the same fault, attributing a float to whichever document
cited it first.

**Tables labelled `tab:` were invisible.** The float vocabulary was `fig|tbl|eq`.
koth labels every table `tab:`, so all 37 of them were silently exempt from the
uncited-float and reference-order checks while the checker reported clean. The
prefix is a project convention, not a Typst rule, so both spellings are now
recognized through one `FLOAT` constant. Fixing this immediately turned up an SI
table that nothing cited.

**`\u{XXXX}` escapes reached the prose verbatim.** A manuscript writing
subscripts as `log\u{2082}` had the word counter treat that as one opaque token
and the narrator read it aloud as "log u 2082", 41 times.
`typst_prose.unescape_unicode()` resolves the escape to the character, so the
count sees the word a reader sees and the narrator's spoken-Unicode map can
handle the result like any other symbol.

**`word-repetition` fired on repeated file paths.** It ran on the prose with
inline code UNWRAPPED, because a journal counts an inline-code term as a word. A
sentence listing three reproducer scripts under one directory then read as that
directory name three times. It now runs on `spellable`, the same code-removed
text the spelling check uses, for the same reason. That was 12 of koth's 18
findings, and a checker whose warnings are mostly noise is a checker nobody
reads.

## 1.0.1

Three fixes, all found by porting 1.0.0 into a real manuscript (`FeNovo`). None
of them change an interface, so an existing project can take them by copying
`justfile`, `readability.py` and `tests/run.py`.

**`just fmt` rebuilt the PDF.** The recipe's closing message was double-quoted
and contained `` `just paper` ``. just evaluates a backquoted string as a shell
command, so formatting the sources ran a full compile and printed a word count
nobody asked for. Single-quoted now, with the explanation above the recipe rather
than inside it, since recipe-body `#` comments are echoed.

**The sentinel gap did not cover inline code.** `readability.clean` unwraps an
inline-code span into a bare word, because a journal counts it as one. Under a
sentinel gap the caller is looking for adjacent duplicate words instead, and an
unwrapped `` `--proteome-k K` `` reads as a doubled "k K" the author never wrote
— firing the one duplicate-word rule that gates. Inline code is now dropped
whole under a non-default gap, and the regression cases cover it.

**CLAUDE.md described checks that no longer exist.** It told an agent that
`just check` covers audiobook staleness and figure-copy drift. Both were removed
in 1.0.0 (see "Decisions reversed"), so the instruction sent agents looking for
output that never appears. It now describes what `check` actually does and points
at the reversal.

---

## 1.0.0

First release. The pipeline was extracted from the `dnoise` manuscript, where
every piece of it was written in response to something that had actually gone
wrong.

**Build.** Typst to PDF with the Supporting Information appended as one
compilation, so cross-references resolve in both directions and numbering cannot
drift. Word export through Typst's HTML output and pandoc, with the template
bypassed and equations rasterized, because HTML export silently discards the
template's front matter, every section heading, and all math.

**Identity.** `config.typ` is the single source for title, authors,
affiliations, abstract, keywords, and bibliography style. The Word front matter
derives its numbered affiliation superscripts from the same author list the PDF
template uses. `audio/config.py` parses the title out of `config.typ` rather than
holding its own copy, after a finished audiobook spent weeks announcing a title
the paper no longer had.

**Generated assets.** `analysis/` lives inside the manuscript and writes figures
into `figures/` and tables into `si/` directly. Its whole contract with the
manuscript is one recipe, `assets`. Both output directories are tracked, so a
fresh clone compiles without re-running an analysis that may take hours, and
`just check-assets` guards them with a content stamp.

**Prose tooling.** Journal word counts with the exemptions spelled out,
readability metrics, density metrics (numerals, parentheticals, acronyms,
nominalizations, passives, hedges per 1,000 words, with per-section outliers
judged against the paper's own median), and `prose-check` for the mechanical
rules in `STYLE.md`.

**Formatting.** `just fmt` runs typstyle, and `.vscode/settings.json` pins
tinymist to the same width and prose-wrap setting so format-on-save and the CLI
cannot fight.

**Staleness.** `just check` reports a committed `paper.pdf` that predates a
source commit, a Word export older than what it renders, and generated assets
older than the analysis that produced them.

**Audio.** Offline Piper narration into chaptered `.m4b` files with cover art.

---

## Decisions reversed

Each of these was built, shipped, and then undone. They are recorded because all
of them look reasonable in the abstract, and the reasons they failed are only
visible from use.

### Construct coverage in the placeholder prose

The first skeleton put one of every special-cased Typst construct into
`paper.typ`, so `just all` on a fresh clone was a smoke test. The flaw is fatal
and was pointed out immediately: placeholder prose is deleted the moment real
writing starts, so the test ran exactly once and then the constructs went
untested for the life of the project, which is the failure it was meant to
prevent.

Coverage now lives in `tests/fixture.typ`, which is never part of the manuscript,
with golden files and a reflow-invariance assertion. `paper.typ` is a short
placeholder that says to replace it.

### A general "-ise to -ize" spelling rule

The American-English check started with a regex for the whole `-ise` family. Run
against the real manuscript it flagged the name of the software itself, `dnoise`
and `denoise`, on every mention. A checker that cries wolf on the project's own
vocabulary gets switched off within a week. The British list is now explicit and
grown by hand.

### Spell-checking inline code

`readability.clean` unwraps an inline-code term into a bare word, because
journals count it as a word. Spell-checking that output then flagged the DIA-NN
column name `Ms1.Normalised` as a British spelling. The spelling pass now runs on
a variant with code removed rather than unwrapped.

### Commit dates for generated-asset staleness

`check-assets` first compared the commit date of `figures/` and `si/` against
`analysis/`. Dogfooding hit the case it cannot handle within minutes: the
generators are deterministic on purpose, so re-running them after an edit that
does not move the output produces nothing to commit, and the check then nags
forever with no way to satisfy it.

Replaced with `.assets-stamp`, a content hash of the analysis source written when
`just assets` runs. It clears whether or not the bytes changed, and needs no git.

### `figures.map` and an external analysis tree

The analysis was originally modeled as a sibling directory that figures were
copied out of, governed by `figures.map` and policed by a byte-compare. The copy
was the whole problem: a re-analysis updated the plot upstream, the copy in
`figures/` stayed put, and the PDF kept rendering a figure that no longer matched
its own caption. Moving the analysis inside the manuscript and writing to the
destination removed the failure instead of guarding it.

### `fmt-verify`, and five other recipes

`just --list` reached 30 entries, which is the first thing a newcomer sees.
`fmt-verify` was superseded by `just test`, compared a no-op once sources were
always formatted, and restored via `git checkout --`, the most dangerous line in
the repo. Four one-flag wrappers and a redundant flat-narration path went with
it. The two `.m4b` staleness checks went too: every prose edit marked both
audiobooks stale and clearing that cost minutes of narration, so the warning was
almost always present and almost never acted on.

---

## Bugs worth remembering

**A reflow can break the prose extractors.** typstyle breaks long lines inside a
call or an emphasis pair, so `#refn(<sec:x>)`, `_Saccharomyces cerevisiae_`, and
`#link(` all became multi-line forms. Patterns written for the one-line version
then leaked a bare `#refn(` into the word count and the narration, or left
literal underscores for the voice to pronounce. The PDF looked correct
throughout. The recognition patterns now live in `typst_prose.py`, shared by both
extractors, because each of those three fixes otherwise had to be made twice.

**Typst line continuations.** A method chain broken across lines after `#let x =`
or inside `[...]` ends at the first newline, and the continuation is parsed as
literal text. The error points at a closure parameter and reads
`unknown variable: a`. Wrap the chain in a code block.

**matplotlib stamps a creation date into PNG metadata.** Every regeneration then
looks like real drift. Pass `metadata={"Software": None}` and seed any RNG.
