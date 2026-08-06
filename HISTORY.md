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
git -C ~/Repos/paper-scaffold diff vOLD..vNEW -- justfile tools/ tests/ scripts/
```

That path list was `justfile *.py tests/` before 2.0.0, when the toolchain sat
in the root. Upgrading from 1.x means the `*.py` half of it matches nothing and
reports a clean diff over the files that changed most.

Then apply what you want by hand. There is deliberately no automatic upgrade: a
manuscript directory diverges from the scaffold the moment real writing starts,
and a merge tool cannot tell your `paper.typ` from the placeholder it replaced.
Read the major entries below first, since those are the ones that need an edit
rather than a copy.

---

## 2.0.0

The scaffold became something that can be handed to someone else. Until now it
was a directory that worked on the machine it was written on, documented well
enough to be copied by hand. Most of this release is the difference between
those two things, and most of the bugs below were found by asking what happens
on a machine that is not this one.

Major because the layout changed. Nothing in `paper.typ`, `si-body.typ` or
`analysis/` has to be edited, so by the letter of the policy above this is a
minor. It is a major anyway, because the upgrade instructions themselves broke:
the toolchain is no longer `*.py` in the root, and a 1.x project running the old
diff command sees a clean result over the files that changed most. A version
number that makes someone read the entry is doing its job.

### The toolchain moved to `tools/`

The root had reached 28 files, nine of them Python and shell that nothing in the
manuscript imports -- they all read it. That is the split: the root is what a
person edits and what a build produces, `tools/` is what processes it. 19 files
left in the root, and a layout map in the README, which it never had.

Six tools defined `HERE = Path(__file__).resolve().parent` meaning "the
manuscript root", which stopped being true when they moved down a level. They
are `ROOT` now and point at `.parent.parent`; a variable called HERE pointing at
its parent directory is how the next bug gets written.

**Upgrading:** create `tools/`, move `prose_check.py`, `prose_rules.py`,
`readability.py`, `typst_prose.py`, `typst2docx.py`, `density.py`, `viz.py`,
`bib_audit.py` and `wordcount.sh` into it, fix those path constants, and take the
new `justfile`. `audio/extract_prose.py` and `tests/run.py` both reach for the
shared patterns and need their `sys.path` updated too.

### Starting a paper: `scripts/new-paper.sh`

The documented way to start a manuscript was `cp -r`, which copies `.git` along
with everything else. The new paper then carried the scaffold's history, and two
checks answered the wrong question while reporting confidently: `check-pdf`
compared the paper against the *scaffold's* commits, and `just version` reported
the scaffold's last commit as the manuscript's state.

The script copies the working files, fills in `config.typ`, builds the first PDF
and Word export, and starts a history belonging to the paper. Interactive, or
every field as a flag.

Three things it does that are not obvious. It copies with `tar`, not `cp -r`, so
the `AGENTS.md` symlink stays a symlink rather than becoming a second copy of
CLAUDE.md free to drift. It builds the PDF *before* the first commit, because
`check-pdf` compares commit dates and the reverse order makes a brand-new
manuscript report itself stale. And it builds the Word export nobody asked for on
day one, because `paper.docx` is gitignored and `just check` reports a missing
one -- without it the first thing a new manuscript does is fail its own gate.

It is tested in `tests/run.py` rather than as its own recipe, and skips itself in
a derived manuscript, where `scripts/` is gone: a paper does not make papers.

### `just verify`, and `just doctor`

`verify` runs `fmt-check`, `test`, `prose-check` and `check` in one pass,
rebuilding nothing. Every part of it already existed and was already documented;
what did not exist was a single thing to run. The instruction was a four-step
ritual with two conditions in it ("if you changed prose...", "if you changed
inline markup..."), and a conditional ritual is one people skip -- the conditions
need a judgement about which files a change touched that is easy to get wrong
from inside the edit. CLAUDE.md is now `just paper && just verify`.

`doctor` reports whether the external tools are present and new enough, instead
of leaving a missing one to surface as "command not found" from inside whichever
recipe needed it first. `just setup` depends on it, because `uv sync` succeeding
proves nothing about typst.

### The Typst floor is 0.14, and the obvious answer was wrong

`--features html` and `html.frame()` both arrived in 0.13, so 0.13 is the
obvious floor. On 0.13 `just docx` runs, exits 0, and silently contains **no
figures**: that version's HTML export emits no `<img>` for an `image()` call,
while tables and the rasterized equations survive. The result is a .docx that
looks finished with every plot missing.

Established by running 0.13.1, 0.14.2 and 0.15.1 through `just docx` and
comparing the output, not by reading a changelog.

CI holds the floor by counting `<img>` in the export against `image()` calls in
the source. Counting embedded images in the .docx cannot do it, and that was the
first attempt: 0.13 keeps both rasterized equations, so the file still contains
images and still looks fine.

### CI

Every bug in this repository's history was found by hand-porting the scaffold
into another manuscript. That works and it is slow, and it only happens when
someone starts a paper.

Three jobs: the gate across a Typst version matrix, a generated manuscript built
from `new-paper.sh` and checked, and the audio toolchain on Linux and macOS.
Tools install from pinned release binaries by curl rather than marketplace
actions.

### Piper is a uv dependency

The audiobooks were the one part of this directory that could not run on a Mac.
Piper was a binary tarball fetched by curl, pinned to a release that shipped
x86_64 Linux only. `piper-tts` on PyPI ships abi3 wheels covering Linux, both
Macs and Windows, and installs with everything else -- which is what pandoc and
ffmpeg already did here.

Narration is a library call now rather than a subprocess, so the ONNX model
loads once instead of once per chapter. `VOICE_LANG` is gone: it held a
hand-built path into a HuggingFace repo that had to be kept in step with
`VOICE_NAME`, and a mismatch arrived as a 404 that read like a network failure.

The migration left `_audio-check` still gating on `piper/piper`, which is the
kind of thing that passes locally forever. Only a fresh clone would have hit it.

### The SI could not use generated numbers

Only `paper.typ` imported `stats.typ`, and Typst's `include` gives the included
file its own scope, so `#s("id")` anywhere in `si-body.typ` failed with
`unknown variable: s` one line below a file that imports it. The SI is the
data-heavy half and is where a generated number most belongs.

The two sides disagreed, which is the worse half. `readability.py`,
`wordcount.typ` and the SI narration all resolve `#s()` out of `si-body.typ` and
always did, so the tooling reported a number the compiler refused to produce.

**Upgrading:** add `#import "stats.typ": n, s` to `si-body.typ`.

Removing the mechanism was also documented wrong. Three `.typ` files import it,
and `wordcount.typ` names the helpers a second time in its eval scope, so the old
instructions left `just paper` working and `just wordcount` failing -- the
command you run constantly is fine and the one you run before submitting is not.
Now a four-step procedure, verified by doing exactly it to a copy.

### Four extractor leaks

`#n("id")` was never handled at all. Rarer in prose than `s`, and an unhandled
one put the call text verbatim into the word count and gave the narrator
`#n("cohort.total_n")` to read aloud.

The other three came from testing constructs the fixture did not contain, which
is the trap a fixture sets: everything in it passes, and what a real manuscript
uses instead was never looked at.

- **A bare `#link("url")` leaked entirely.** The pattern required the
  `[shown text]` bracket. `#link("https://...")` with no body is valid Typst
  that renders the URL as its own visible text, and it is what a data- or
  code-availability statement is written with -- the one section every paper now
  has. This is the `#ref(` failure again, which reached 68 places.
- **A bare `#table(` in prose leaked.** Only `#figure(` was stripped.
- **A footnote welded onto the word it annotates.** The generic `#name[` rule is
  gap-free on purpose, so `H#sub[2]O` stays "H2O". A footnote attaches the same
  way and must not: "high#footnote[...]" counted and narrated as one word.

All four have fixture cases. Links now go through `strip_links()` in
`typst_prose.py`, shared, because these two extractors have been fixed
separately three times already.

Probed at the same time and found correct, so unchanged: `config.typ`'s
`surname-of` across suffixes, single names, hyphens and particles, and all four
draft-mode behaviours.

### `.assets-stamp` carries two hashes

The stamp covered the analysis *source*, so it caught a generator edited and not
re-run. It never caught the reverse: an edit to the *generated* file. That is the
rule CLAUDE.md states most loudly and nothing enforced it, and the failure is
quiet and total -- the edit renders, every check reports current, and the next
`just assets` overwrites it. An "AUTO-GENERATED" header is a request; this is a
check.

**Upgrading:** run `just assets` once to rewrite the stamp in the new two-line
form. The old single-hash file is reported as stale rather than guessed at.

### Distribution

`LICENSE` (MIT). The whole use case is copying this directory, which nobody
could legally do. `new-paper.sh` carries it into a new project renamed
`LICENSE.scaffold`, so a `LICENSE` at a manuscript root does not read as a claim
about the paper.

`AGENTS.md`, a symlink to `CLAUDE.md`, so tools following either convention read
one document. A symlink rather than a copy for the reason everything else here
is shared: the copy drifts, and the drifted one is what the agent read.

## 1.6.0

**The bibliography is checked.** It was the last artifact in the directory that
nothing read. Typst already fails on a citation with no entry, so only the
reverse directions were open, and all of them survive every rebuild silently.

Offline, in `just prose-check`:

- **`duplicate-reference`** (error) -- two keys, one DOI. The same work entered
  twice is how a manuscript ends up citing one paper inconsistently.
- **`uncited-reference`**, **`missing-doi`**, **`implausible-year`** (warnings).

Two decisions came from running it against a real 52-entry bibliography:

*Not duplicate title.* A title match flagged `pxd070049` and
`vanpuyvelde2026genbeta` -- a PRIDE dataset and the preprint describing it, which
share a title and are correctly cited as two things. Duplicate DOI is the signal
that means what it looks like.

*`missing-doi` only from 2000 onward.* DOIs were introduced then and older work
was retrofitted patchily, so demanding one from a foundational 1952 citation
reports an absence nobody can fix, on exactly the references papers cite most.
Both of this scaffold's own example entries are pre-DOI, and the rule flagged
both before the era check went in.

**`just bib-audit`** (new recipe) checks every DOI against Crossref: does it
resolve, and has the work been retracted? Online, so it is deliberately NOT in
`just verify` -- a gate that can fail because an API was slow is one people learn
to skip. Being offline is reported, not failed.

The retraction check shipped wrong the first time and looked right. Crossref
relates a paper and its notices in both directions: `update-to` lives on the
NOTICE and points at what it retracts, `updated-by` lives on the PAPER. Reading
`update-to` returned nothing for the Wakefield MMR paper, retracted since 2010.
Caught only by testing against a known-retracted DOI rather than reading the API
docs and believing them. A test now pins the field name.

Against the 52-entry bibliography this was developed on: 50 DOIs checked, none
retracted, none unresolvable.

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
