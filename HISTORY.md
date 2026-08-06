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

## 1.5.0

**`misspelling`, from codespell's dictionary.** Runs on the same code-removed
prose the British-spelling check uses, so a tool's own flag is never reported as
a typo.

The choice of tool is the whole point, and it was made from measurement rather
than preference. Three candidates were run against 15,175 words of a real
manuscript:

- **pyspellchecker** flagged 418 words, 18% of the vocabulary. After discarding
  hyphenated compounds whose parts are all known, 181 remained, and they were
  `bruker`, `cerevisiae`, `centroider`, `ddapasef`, `carbamidomethyl`,
  `bonferroni` -- essentially no typos. A dictionary check asks "is this word in
  the wordlist", which on a scientific manuscript flags the subject matter.
- **proselint** produced 7 findings, of which 3 were `--reanalyse`, a DIA-NN
  command-line option it could not tell from prose. This pipeline already solves
  that, which is exactly why the check has to run on cleaned prose.
- **codespell** produced **zero** false positives and caught every injected typo.
  It ships curated confusion pairs rather than a dictionary, so it only fires
  when confident.

Zero findings on a finished manuscript is the right result: the check costs
nothing now and is there for the next typo typed.

One implementation note worth keeping. Matching word-by-word disagreed with
codespell on exactly one token: `mis-transferred`. codespell's list contains
fragments that are wrong only standing alone (`mis -> miss, mist`), so splitting
a compound and matching its prefix invents a finding codespell itself does not
make. Words adjacent to a hyphen are therefore skipped by this check and NOT by
the British one, whose list is curated and must still catch the `colour` in
`colour-coded`. Both behaviours have cases.

Grammar checking was considered and rejected for now. `language_tool_python` is
the only serious option; it needs Java 17 or newer and downloads about 250 MB, so
it breaks the clone-and-run property. If it is ever added it belongs behind its
own recipe with `just doctor` reporting the JVM, never in `just verify`.

## 1.4.0

**Severity and vocabulary are the project's call.** Before this, a rule could be
switched off or have named values exempted, and its thresholds could be moved,
but two things were fixed in Python: whether a rule was an error or a warning,
and the word lists it judged against.

Both are project policy, not properties of the checker. Whether an em dash should
stop a build depends on the house style; whether "essentially" is filler depends
on the field. A checker you cannot teach gets switched off wholesale, which is
the outcome every one of these rules exists to avoid.

- **`[severity]`** re-rates any rule, in both directions. `long-sentence` can be
  an error before submission; `em-dash` can be a warning for a group that
  tolerates them. Applied in `report()` rather than where each Finding is built,
  so there is one place to get right and no check needs to know the config
  exists. `Finding` is frozen, so it rebuilds rather than assigns -- the first
  version silently did nothing, and the test now covers exactly that.
- **`[vocabulary.<name>]`** takes `add` and `remove` for `verbose-phrase`,
  `british-spelling`, `common-words` and `abbreviations`. The shipped lists
  become a starting point instead of a verdict.

What did NOT move, and why: the `RULES` registry stays in Python. It is not
configuration, it is a manifest of what the code implements, and a test asserts
every rule the checker can emit is declared there. Putting it in TOML would not
let anyone add a rule -- there would be no implementation behind it -- it would
only split one tightly-coupled pair across two files where they can drift.
`DEFAULT_LIMITS` stays for the same kind of reason: it is already overridable in
`[limits]`, so shipping the defaults as TOML too would add a file without adding
a capability.

Also: `--list-rules` computes its column width from the longest rule name.
`low-resolution-figure` was one character past the hard-coded guess and pushed
its own row out of line.

## 1.3.0

Two checks for the defects that only appear in the proof, when the analysis is
finished and regenerating an asset is most annoying.

**`low-resolution-figure`.** The number that matters is not what the file stores,
it is pixels divided by the width the figure is actually rendered at. Effective
dpi is computed from the `width: NN%` in the `image(...)` call against the text
block, with no width treated as full width, which is how Typst scales an image to
its container. Vector formats are skipped, having no resolution to be below.

The default text width, 160 mm, is this scaffold's arkheion page measured with
`typst query` (A4 less 25 mm margins), not a plausible-looking guess. Change
`figure-text-width-mm` if you change the page, or every dpi is computed against
the wrong ruler.

The check immediately caught the scaffold's own example figure at 227 dpi. Fixed
in the generator rather than suppressed: a template that ships below its own
standard teaches the wrong thing.

**`oversized-table`.** Columns, rows, and the longest cell. A generated table
grows a column per condition or a row per run, and the first sign is a proof
where the columns are unreadably narrow, a header is stranded on the previous
page, or one long cell wraps to three lines and drags its row with it. None of
that is visible from the source.

Cells are found by tracking bracket depth, not by a non-greedy `\[.*?\]`, because
a cell legitimately contains brackets of its own and the lazy match cuts it at
the first inner close -- a long cell containing a link would measure as a few
characters and pass. `columns:` is read in all three spellings, including the
repeat form `(1fr,) * 12`: read as a bare tuple it counts one column and every
row count derived from it is wrong by that factor. Both have regression cases.

New limits, all overridable in `prose-check.toml`: `min-figure-dpi` (300),
`figure-text-width-mm` (160), `max-table-columns` (8), `max-table-rows` (40),
`max-cell-chars` (60).

Each check was confirmed to fail its tests when disabled.

## 1.2.0

Three additions, all additive.

**`just draft`.** `#s("id")` panics on an unknown id, which is right for a real
build: a number that stopped existing must not render blank. While drafting it is
the wrong trade, because renaming a value breaks every call site at once and
until the last one is fixed there is no PDF at all, not even to read the
paragraph you were in the middle of writing.

Draft mode renders an unresolved id as a loud `?id?` placeholder and writes
**`paper-draft.pdf`, never `paper.pdf`**. Keeping the output file separate is
what makes this safe: a placeholder cannot reach a PDF anyone would mistake for
the finished paper, so `check` needs to know nothing about the mode. `n("id")`
still fails in draft mode, because no placeholder can stand in for a number
inside an expression without making the arithmetic that reads it silently wrong.

**`orphaned-asset`.** `uncited-figure` catches a float the manuscript defines but
never references. Nothing caught the opposite: a generated table dropped from
`si-body.typ`, or a figure whose `image(...)` line was rewritten, keeps being
regenerated by `just assets` forever while appearing nowhere. Every staleness
check reports it current, correctly -- it is simply not in the paper. Matched on
filename anywhere in the `.typ` sources rather than by parsing includes, since a
false negative is far cheaper than telling someone to delete a file the
manuscript needs. `si/stats.json` is exempt: it is read by id, never by name.

**`audio/` is genuinely optional.** It was documented as deletable and was not:
`just all` had a hard dependency on `audiobook-all`, and `tests/run.py` imported
`extract_prose` at module level, so deleting the directory broke the default
build and the whole test suite on a project that had declined a feature it never
asked for. `all` now skips narration when the directory is absent and says so,
and the test run reports "no audio/ so narration skipped" rather than quietly
testing half of what its summary line claims.

Verified by deleting `audio/` and running `test`, `prose-check`, `readability`
and `all` against a manuscript without it.

## 1.1.0

**Numbers in prose are generated, guarded, and checked.** Tables and figures
always tracked the analysis, because a script wrote them. Numbers in sentences
were typed, and that is where drift lives: a unit error, a percentage stale after
a re-run, a value corrected in the table but not in the paragraph beside it. A
manuscript built on this scaffold had exactly that failure, in three places, with
the tables correct throughout.

New and additive. An existing project takes it by copying `stats.typ`,
`typst_prose.py`, `readability.py`, `prose_check.py`, `prose_rules.py`,
`audio/extract_prose.py`, `analysis/scripts/_stats.py` and `gen_stats.py`, then
adding the `stats` recipe to `analysis/justfile` and `s` to the eval scope in
`wordcount.typ`. A project that states no computed numbers deletes the three
stats files and is otherwise unaffected.

- `analysis/scripts/gen_stats.py` declares every number the prose states and
  writes `si/stats.json`. ONE script, not a glob like the table and figure
  generators: they would all write the same file, so a second would silently
  clobber the first.
- `#s("id")` reads it back and **panics at compile time** on an unknown id.
  `readability.py` and the narrator resolve the same call, since both read the
  source rather than the PDF. Stripping it would silently delete a number from
  the word count; leaving it would leak the call text into the narration.
- **Guards run at generation.** `sign="-"` and `between=(0, 100)` are assertions
  about what the analysis is allowed to produce. The case they exist for: a
  sentence reads "fell by #s(...)%", a re-run turns the value positive, and the
  paper ships "fell by -3.1%". The build now fails first, naming the assumption
  the sentence makes, rather than a reader finding it.
- **`derivable-number`** flags a typed numeral matching a declared value, which
  is what turns the convention into something enforced rather than intended.

Only *distinctive* values are compared: a decimal point, a thousands separator,
or four characters or more. A declared `3` would otherwise match every `3` in the
manuscript, and 1.0.2 already recorded what a mostly-noise checker is worth.

Rounding stays with the analysis, set per value with `fmt`. Typst has no
equivalent of siunitx, and reimplementing rounding in the document would put the
same decision in two places.

Every guard and the new rule were verified by breaking the mechanism and
confirming the tests fail, not by reading the code.

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
