# History

What changed in the pipeline, and why. Read the "Decisions reversed" section
before proposing a change that looks obvious. Several obvious things were tried
here and were wrong.

Entries are deliberately short: what changed, the one-line reason, and the
upgrade step. The full arguments live as comments next to the mechanisms they
justify, where someone touching the code will actually read them.

## Versioning

The version lives in one place, `version` in `pyproject.toml`, and travels with
the scaffold when it is copied into a project. `just version` prints it.

What bumps what is judged from the manuscript's point of view, not the code's:

- **Major** breaks a manuscript. An existing `paper.typ`, `si-body.typ`, or
  `analysis/` has to be edited to keep working.
- **Minor** adds a capability without touching an existing manuscript. A new
  check, a new metric, a new recipe.
- **Patch** fixes something without changing the interface.

Tag every release: `git tag -a v1.2.3 -m "..."`.

### Upgrading a project built on an older version

From inside the project. The upstream clone is `--scaffold PATH`, else
`$PAPER_SCAFFOLD`, else found through `.agents/skills`, a sibling
`paper-scaffold` directory, or `~/Repos/paper-scaffold`:

```bash
just version                        # what the project is on
just upgrade-plan                   # plan to the latest tag, or: just upgrade-plan v3.23.0
just upgrade-plan --apply-pristine  # copy only the files the project never touched
```

The plan lists every "Upgrade:" line between the project's version and the
target, oldest first, folds a pure copy step that a later release repeats,
and names the customized files each line touches. It then classes every
scaffold-owned file: **pristine** (identical to upstream at the project's
current version, so replacing it loses nothing), **customized** (changed both
locally and upstream; lines on each side, and whether `git merge-file` would
conflict), **new-upstream**, **removed-upstream**, **project-only**,
**at-target**, and **unchanged**. `--apply-pristine` copies the pristine and
new files only, refuses when git shows any of them dirty, and leaves removals,
customized files and the `version` line to you. `--json` is the same plan for
an agent.

Then merge each customized file by hand, with
`git -C <scaffold> diff vOLD..vNEW -- <path>` beside it, set
`version` in `pyproject.toml`, and run `just paper` and `just verify`. There is
still deliberately no automatic merge: a manuscript diverges from the scaffold
the moment real writing starts, and a merge tool cannot tell your
customization from the placeholder it replaced. The tool takes over the
bookkeeping only; every file that would need merging, it leaves to you. Read
the major entries first, since those need an edit rather than a copy. For
moving an existing manuscript onto the scaffold, see MIGRATING.md.

(A project older than 3.23.0 has no `tools/upgrade_plan.py`: run the scaffold's
copy with `--project PATH`, or copy the tool and the recipe in first. Before
2.0.0 the toolchain sat in the root, so upgrading from 1.x is by hand:
`git -C <scaffold> diff vOLD..vNEW -- justfile *.py tests/`.)

---

## 3.23.0 (upgrade-plan)

`just upgrade-plan [target]` (`tools/upgrade_plan.py`) plans a scaffold
upgrade from inside a derived project. Ten papers made about 105 upgrade
commits in 60 days, most of them copying files the project had never touched,
one release at a time. The plan reads old releases with `git show` from a
local clone, never the network: the "Upgrade:" lines for every release in
(current, target], and a class per scaffold-owned file, where owned means
what `scripts/new-paper.sh` copies minus what CLAUDE.md says the project owns.
Pristine files can be replaced with `--apply-pristine`; customized ones still
get a hand merge, with a three-way summary to size it. `--json` serves agents,
and `--from` overrides a `version` line that is wrong. Upgrade: copy
`tools/upgrade_plan.py` and `tests/upgrade_plan_cases.py`, add
`upgrade_plan_cases` to `CASE_MODULES` in `tests/run.py`, add the
`upgrade-plan` recipe after `version` in the justfile, and replace the "no
upgrade script" sentence in CLAUDE.md's "Paper scaffold" paragraph.

## Unreleased

Seven read-only review skills join the four editing skills in
`.claude/skills/`: `claim-audit` walks every quantitative claim to the code
that computes it through `just trace`; `methods-vs-code` compares the methods
section with the analysis parameter by parameter; `figure-review` checks each
figure and table against its caption, citing sentences, and statistics;
`prose-review` flags vague, decorative, or machine-sounding wording and
proposes only replacements the evidence supports; `literature-check`
reads each cited work against the sentence citing it, searches for missing
foundational or competing work, and may only propose a reference it
resolved online in the same pass; `story-review` is the developmental
pass, proposing message, structure, float, and analysis changes ranked by
cost against acceptance with the stated aim of a defensible paper that gets
published rather than a perfect one; `peer-review` convenes a small panel of reviewer personas and an editor, with
loose parameters, and depends on no external review pipeline. Each writes a
dated findings file under `reviews/` and routes every fix to the editing
skill that owns it, so a review never edits the manuscript. `review-all`
runs the fix-list reviews concurrently, the literature check on request
and the story review never, as forked agents, with an optional model per run,
and merges the findings into one ranked list with a ship verdict. The review
skills carry `context: fork` and `model: opus`, so they run as their own
agents on Opus and hand back only the report. Upgrade: copy the eight new directories under
`.claude/skills/`.

CLAUDE.md carries a short "Paper scaffold" paragraph -- what the scaffold owns,
what the project owns, how numbers reach the prose, the build and gate
commands, and how an upgrade is done -- with a `SCAFFOLD_VERSION` placeholder
that `scripts/new-paper.sh` fills with the release the copy came from. Every
derived manuscript on this machine now carries the same paragraph at 3.20.3.
Upgrade: optional; copy the paragraph into CLAUDE.md with the version written
in.

## 3.23.0 (submission outputs)

The journal upload set is upstream. Four papers each built their own split
PDFs, split Word files and standalone graphic, three different ways. Now one
tool, `tools/submission.py`, writes them into `submission/` with a
`manifest.json`. The recipes are `just main-pdf`, `si-pdf`, `main-docx`,
`si-docx`, `toc-graphic`, `cover-letter`, and `just submission` for all of
them. Every split file is cut from the manuscript that `just paper` captured,
never from a second compile. It refuses to build while the source differs from
that capture, so its page, figure and reference numbers always match
`paper.pdf`.

- **PDFs.** They are page ranges of one compile, split at a new `<si-start>`
  probe in `paper.typ`.
- **Word files.** They are split at the SI heading of the Word projection.
- **Graphical abstract.** It follows the profile's new
  `[graphical-abstract] file-format` (TIF for the four ACS profiles, as the
  ACS guideline says). It is flattened onto white, and its resolution is set
  so it fits the journal's box. It fails if that resolution is under
  `min-dpi`.
- **Cover letter.** `cover-letter.typ` is a new, optional template. It reads
  `config.typ` and `#s()`, and takes the journal name from the profile. If the
  file is absent, the step is skipped.
- **Graphic placement.** `journal.toml [placement]` gains `submission`, which
  defaults to `journal`.

Each output is recorded in `.build-state/submission.json`. The set stays
outside `verify`, for the same reason as the audiobooks. `just check` prints a
note, not a failure. `just check-submission` is the strict version, and
`preflight` now builds the set and runs that check. Project-specific packaging
stays downstream: figure QC for one journal, source-data archives and delivery
bundles.

Upgrade: copy `tools/submission.py`, the new justfile recipes and the
`all`/`preflight`/`check`/`clean` changes, `submission/` in `.gitignore`, and
the `file-format` lines in `journals/*.toml`. Add
`#context [#metadata(here().page()) <si-start>]` to `paper.typ` directly after
the `#pagebreak()` that opens the SI. Do this after the journal-layout graphic,
so the main text ends with that page. Copy `cover-letter.typ` only if you want
a letter. If the project has its own main-pdf, si-pdf, main-docx or si-docx
recipes or a tool behind them, delete those. Keep project extras such as
figure QC and source-data packaging, and point them at `submission/`, which is
where the outputs now land, not the root.

## 3.22.0

`/paper:review-all` now splits the model by the kind of review. The four
checklist reviews (`claim-audit`, `methods-vs-code`, `figure-review`,
`prose-review`) compare the manuscript against a fixed standard and run on
Sonnet; `peer-review` and `literature-check` are judgment calls and stay on
Opus. Opus draws down the plan's rate-limit window several times faster than
Sonnet, and the checklists do not lose findings on Sonnet. "all on opus"
restores the old behaviour for one run. No manuscript-side change. Each repo pins its plugin version, so run
`claude plugin update paper@paper-scaffold --scope project` in each paper
(`paper-plugin-update` on this machine does all of them).

## 3.21.0

Skills moved out of `.claude/skills/` into a Claude Code plugin, `paper`, served
from this repository as the `paper-scaffold` marketplace. Eleven repos carried
byte-identical copies and every skill fix meant twelve files times eleven
commits. Now a paper enables `paper@paper-scaffold` in `.claude/settings.json`
and gets the current skills. Slash names gain the plugin prefix:
`/review-all` is `/paper:review-all`. The review skills also share one
`paper.review.txt` generated once by `/paper:review-all`, instead of each
agent re-reading the Typst sources.

Upgrade: `git rm -r .claude/skills`, add `{"enabledPlugins": {"paper@paper-scaffold": true}}`
to `.claude/settings.json`, `claude plugin marketplace add pgarrett-scripps/paper-scaffold`
once per machine, and repoint `.agents/skills` at `<scaffold>/plugins/paper/skills`.

## 3.20.3

Three fixes the 3.20 roll-out across ten manuscripts found. `just paper`,
`just docx` and `just docx-check` chose the dissertation Word adapter on the
mere presence of `manuscript.toml`, then failed a manifest that names only
PDF targets; they now require `lib/template.typ` as well and otherwise keep
the paper's route. The standalone-directive strip in the Word resolver and
the prose cleaner was line-based, so a `#show` rule typstyle had broken
across lines left its continuation lines behind as prose; it now follows
the brackets to the line that closes the statement. And author names and
affiliations are emitted escaped, so a corresponding-author `*` no longer
opens emphasis and an email address no longer reads as a citation pandoc
fails the export over. Upgrade: copy `tools/typst_prose.py`,
`tools/resolve_typst.py`, `tools/readability.py`, `tests/export_cases.py`,
and the three `manuscript.toml` conditions in the justfile.

## 3.20.2

`tests/slide_cases.py` failed four cases in a manuscript with no `slides/`
directory, which made `just test` and therefore `just verify` fail in exactly
the projects the 3.20.0 note said were unaffected. The three cases that read
the shipped deck now skip when it is absent, as `tests/new_paper_cases.py`
already does for `scripts/new-paper.sh`. Upgrade: copy
`tests/slide_cases.py`.

## 3.20.1

The Word resolver honoured `toc-graphic = none` by emitting a literal `#none`
and the caption. It now treats `none` as no graphic, as `just check-journal`
already did. Upgrade: copy `tools/resolve_typst.py`; only a manuscript that
sets the binding to `none` is affected.

## 3.20.0

Journal profiles. `journals/<name>.toml` carries one venue's limits for one
manuscript type -- word limits and what they exclude, abstract and keyword
caps, figure and table counts, the figure resolution floor, and the graphical
abstract's box -- together with the URL they were read from, the date the
journal printed on its guidelines, and the date they were read. A profile
without that provenance does not load. `journal.toml` selects one and maps the
roles it names (the experimental section JPR leaves out of its count) onto
this manuscript's section paths. Four ship, read from the ACS guidelines
dated 2026-08-27: JPR Article and Technical Note, JASMS Article and Technical
Note.

Nothing is a second checker: the profile's word limits join `just
check-words`, its resolution floor joins `just prose-check` beneath the
project's own `min-figure-dpi`, and `just check-journal` (in `verify`) covers
keywords, main-text float counts, and the graphical abstract measured against
the journal's box. `just journal` prints the whole card with the journal's own
wording; `just journals` lists the profiles. A limit that covers the reference
list (JASMS's Technical Note) selects a `references` region: the main text's
list as citeproc sets it for the Word file, rendered through pandoc and
counted; `just wordcount` shows it as its own row.

The graphical abstract is declared once in `paper.typ` (`toc-graphic`,
`toc-caption`) and placed per output by `journal.toml`'s `[placement]`: under
the abstract for a preprint, on the last page of the main manuscript under
"For Table of Contents Only" for the journal, or nowhere. The PDF defaults to
the preprint layout and the Word file to the journal's, the build passes each
its choice, and a placement change marks both outputs stale. A shipped
generator draws a placeholder at exactly the ACS box (975 x 525 px); a drawn
graphic is adopted with `just adopt` and referenced the same way.

Also fixed on the way: `just prose-check`'s figure resolution check only ever
measured `image("literal")` calls, so a figure placed through `fig("id")` --
every figure in this scaffold -- was never measured, while the generator's
comment said it was. It now resolves ids through `assets.json` and reads
absolute widths (`width: 3.25in`) as well as percentages.

Upgrade: copy `journals/`, `journal.toml`, `tools/journal.py`,
`tests/journal_cases.py`, the `journal*` recipes and the `verify` stage, and
the updated `tools/wordcount.py`, `tools/prose_rules.py`,
`tools/prose_check.py`, `tools/resolve_typst.py`, `tools/manuscript_snapshot.py`
and `tools/build_state.py`. Add the `toc-graphic` block to `paper.typ` (the
scaffold's shows where) or set `toc-graphic = none`. A project with no
`journal.toml` behaves as before, except that its `fig()` figures are now
measured.

The HTML Word route is gone. `just docx-html`, `tools/typst2docx.py`, the
`docx-mode` conditionals in `paper.typ` and the `paper-author-line` binding
they read from `config.typ` are removed; `just docx` through pandoc's Typst
reader is the only export, and has been the default since 3.18. The route
could not carry the SI's own reference list, which was the last reason to keep
it. The PDF renders identically and `paper.docx` is byte-identical. The typst
floor stays at 0.14, now as the oldest version the pandoc route has been run
under.

Upgrade: delete `tools/typst2docx.py`, drop the `docx-html` recipe, and remove
every `docx-mode` branch from `paper.typ`, keeping the `else` content. A
project that still carries `paper-author-line` in `config.typ` may keep or
drop it.

`tests/run.py` is a fixture harness and a registry again. It had grown to 2,271
lines: the golden-file extractor check it documents, plus fourteen unrelated
suites that ran as a side effect of `structural_cases()`, which chained thirteen
of them at its end. A failure in the Word export was reported under "structural
cases", and adding a suite meant editing a function about prose rules. Those
suites are now one case module per subject under `tests/` -- `prose_cases.py`,
`bibliography_cases.py`, `asset_cases.py`, `stats_cases.py`,
`stats_ownership_cases.py`, `resolver_cases.py`, `export_cases.py`,
`adoption_cases.py`, `new_paper_cases.py`, joining the five that already lived
this way -- listed in `CASE_MODULES`, which names whichever one fails. Every
module now also runs on its own (`uv run python tests/stats_cases.py`); three
that could not before, because they read `sys.path` as `run.py` had left it, set
it themselves. No case changed. The split found one real coupling: the adoption
cases imported `_assets` off a path `stats_cases()` happened to add first.

Upgrade: copy `tests/` wholesale. Nothing outside it changed.

Slide decks are part of the pipeline. A deck lives in `slides/`, is built by
name with `just slides <name>`, and reuses the manuscript's own declarations:
`#s("id")` from `stats.json`, `#fig("id")` / `#tbl("id")` from `assets.json`,
and `references.bib`. The talks' own identity -- title, author line,
institution, date, aspect ratio -- is `slides/config.typ`, separate from the
manuscript's `config.typ` because a talk title is usually not the paper title,
and because a `manuscript.toml` project has no root `config.typ` to read.
Touying supplies
the slides (metropolis theme, speaker notes, handout mode, appendix); all of it
is configured in `slides/theme.typ`. `just slides-handout`, `just slides-notes`
(a `.pdfpc` sidecar for presenter tools), `just slides-draft`, `just
slides-list` and `just slides-fmt` round it out.

Decks are outside the gate: `just verify`, `just check` and `just fmt` say
nothing about them, and `just slides-check` answers staleness plus four prose
rules on demand. Two things in `verify` DO change, because the id index now
includes decks: a number or figure used only in a talk is no longer reported as
declared-but-unread, and `just trace <id>` lists the deck among its use sites.
An id a deck references but nothing declares is a warning, not an error -- a
half-written talk must not fail the manuscript's gate.

Upgrade: nothing to do; a project with no `slides/` directory behaves exactly as
before. To adopt, copy `slides/`, `tools/slides.py`, `tests/slide_cases.py` and
the `slides*` recipes, then replace the example deck.

The Supporting Information carries its own reference list, for journals that
take the SI as a separate file. Typst allows one native `#bibliography` per
document, so the SI's is set by Alexandria: `#show: alexandria(prefix: "si-",
read: p => read(p))` in `paper.typ`, `#bibliographyx(..., prefix: "si-")` at
the foot of `si-body.typ`, and every SI citation written `@si-key`. Both lists
number from 1 and each prints only the works its own half cites. The Word
export converts each list with its own citeproc run and joins the trees.
`just prose-check`
reports a bare `@key` in the SI, which compiles and quietly joins the MAIN
list, and prefixes that disagree between the two files.

CI's figure-survival check now counts images embedded in `paper.docx`
against `fig()` call sites, which is exact on the pandoc route because
equations are native Word math.

Upgrade: nothing to do. A manuscript with one bibliography behaves exactly as
before, down to the bytes of its Word export. To adopt the second list, copy
the Alexandria show rule into `paper.typ` and the `#bibliographyx` call into
`si-body.typ` from the scaffold, then prefix the SI's citation keys.

Word generation now carries the dissertation pipeline's reusable reference
styles, full-caption front lists, page-number caching, independent chapter
bibliographies, proportional table columns and OOXML property-order fixes.
`examples/dissertation/` supplies the supported template contract and a small
working example. `just paper` selects the document pipeline when a manifest is
present. Single papers use `word/paper-reference.docx`; custom styles survive
builds and template edits invalidate freshness.

Upgrade: copy the new `tools/document_docx.py`, `tools/word_*.py`,
`tools/paper_word_reference.py`, updated exporter/build-state tools, `word/`, ACS
CSL, tests and justfile recipes together. Existing dissertation templates need
the documented capture contract; arbitrary multi-document layouts are not
silently adapted. Full Word contents pagination also needs LibreOffice and
Poppler. Existing local template edits should be merged rather than replaced.


Optional `word-limits.toml` defines independent word-count checks with section
inclusions, exclusions, and inclusive minimum/maximum bounds. `just wordcount
--sections` lists paths from evaluated Typst content, including nested headings
and includes. Overlaps count once; unknown or ambiguous selections fail.
Standard journal totals and content exemptions are unchanged.

`just check-words` enforces the configured limits inside `verify` and
`preflight`; draft builds report length violations without refusing to build.
The shipped configuration leaves all bounds unset. This applies to the
single-paper workflow; named document part scopes are unchanged.

Upgrade: copy `wordcount.typ`, `wordcount-sections.typ`, `tools/wordcount.py`,
`tools/wordcount.sh`, and the updated build-state tool, tests, and justfile
recipes together. Add `word-limits.toml` to enable checks in an existing paper.

## 3.19.0

Optional `manuscript.toml` declares named PDF targets and counted chapter parts.
`just document <id>` builds the full document or an independent chapter from the
same sources, without requiring Word adaptation. Per-target state tracks actual
compiler dependencies, selected configuration, tooling, and output hashes.
Failed or concurrent builds preserve the last good output.

`document-metrics` reports Typst word counts and readability per part and refuses
stale results. `document-verify` checks nested chapter prose, separate prefixed
bibliographies, project-wide declarations when present, and output freshness.
`document-edit-baseline` / `document-edit-check` scope the existing mechanical
guard to one target. Literal source discovery also covers declared entrypoints.

Upgrade: copy `tools/`, tests, and the added justfile recipes together, and merge
the pyproject/lock version. Existing single-paper projects need no source edits.
For a chapter project, add the manifest and explicit counted-body markers and
keep its own layout and standalone entrypoint wrappers. See MULTI-DOCUMENT.md
and examples/chapters. Chapter Word export, resolved review, and automatic
toolchain upgrades are not part of this release.

## 3.18.0

PDF, Word, and revision review now use a shared captured manuscript. Literal
statistics and asset paths are resolved while Typst layout and include scopes
survive. Word uses the compiled heading/float numbers, including unlabeled
figures, instead of independently guessing them.

`just review-baseline <name>` saves a version with its figures and bibliography;
`just review <name> [new-name]` writes an offline HTML comparison. Versions are
immutable, local, and excluded from new-paper copies. The existing edit guard
and PDF text-diff commands keep their separate purposes.

Section links locate edits, complete numbers are highlighted, and content edits
are separated from automatic display/numbering changes. Full-paper context
renders unchanged passages once, avoiding duplicate figures and text. Navigation
shows the current edit and supports J/K. `just review-versions` lists saved names.
The review remains a standalone local HTML file, without a review-status database.

Upgrade: copy the updated `tools/`, tests, justfile, and `.gitignore`, then
rebuild PDF and Word. Existing source files need no edits for the scaffold's
supported constructs. The shared build now also requires successful Word
adaptation; custom constructs that the adapter cannot preserve need explicit
support before they can pass. `paper.resolved.typ` remains a Word preview;
the shared source tree is under `.build-state/manuscripts/`.

## 3.17.0

Hardening the checks around AI editing, plus `just trace <id> --json` as a small
inspection interface. Trace returns source locations, declarations, guards,
input hashes, findings, and an explicit checked/failed/incomplete status. It
never runs analysis; dynamically computed calls are outside its source index.

- Reflowed native references no longer count as float definitions in Word.
- The edit guard protects helper IDs, citation occurrences, declarations, the
  abstract, and literal includes. Older snapshots require a new baseline.
- Build fingerprints include compiler dependencies, included chapters, nested
  CSL files, and the Word filter. A Python tool captures before transformations,
  checks again before publishing, preserves last good outputs, and refuses
  overlapping builds. Per-output records replace the old `.build-stamp` file
  under `.build-state/`; the staleness check still rebuilds nothing.
- Deep statistics require an invocation-bound receipt from `Stats.write()`;
  a no-op or unavailable generator cannot count as re-derived. Submission also
  requires the bibliography audit to complete; standalone offline use remains
  tolerant. Writer and checker share numerical guard validation.
- Analysis lock/config hashes join provenance. Manifest writes are atomic;
  malformed declarations and nonfinite values receive named errors.
- New papers exclude local artifacts and correctly emit singleton keyword
  tuples. Documented CLI flags reach their tools. BibTeX parsing is shared;
  indented entries work and malformed blocks fail visibly. Tests run without
  typstyle while explicitly skipping the reflow-dependent check.
- Python 3.10 declares its TOML dependency; CI checks 3.10/3.12 and rejects lock
  drift. A separate hardening suite covers the new contracts.
- Claude Code and Codex discover the same four skills through a relative
  `.agents/skills` link to `.claude/skills`. The workflows preserve author
  changes during repairs, distinguish incomplete checks, and use tracing to
  establish which declaration a claim actually refers to.

Upgrade: copy tools/, tests/, justfile, and analysis/scripts/_stats.py,
_assets.py, and _provenance.py together; merge the pyproject/lock dependency
change. Run `just assets` to record environment provenance, then `just paper`
and `just docx` to create the new build records. Renew any edit baseline before
starting another wording pass. Copy `.claude/skills/` and the `.agents/skills`
symlink together for shared skill discovery, and start a new agent session.
No manuscript syntax changes are required.

## 3.16.0

`just bib-audit` verifies the citation attached to each DOI, not only the DOI
itself. A resolving DOI used to pass even when an AI or a bad copy supplied the
wrong title, authors, or year beside it. Crossref and DataCite responses now
normalize into the same record shape and are compared with `references.bib`.
Wrong identity fields fail preflight; venue, volume, issue, and pages are review
warnings because registrars commonly disagree across online and print versions.
The offline suite covers false title, author, year, venue, volume, issue, and
page data, harmless formatting differences, DataCite records, and the command's
failure status. Upgrade: copy tools/bib_audit.py, tests/run.py, justfile, and the
README bibliography-audit description.

The resolver rejoins citation clusters the 80-column reflow split across
lines. Typst groups adjacent citations across a soft line break, so the PDF
collapsed `@a @b @c\n@d @e @f` into one range; pandoc's Typst reader only
groups citations on one line, and a real manuscript's Word export shipped
reading "10-12 13-15" where the PDF read "10-15". Found by an author reading
their own export. Only a single newline is joined -- a blank line is a
paragraph break. Upgrade: copy tools/resolve_typst.py and tests/run.py.

## 3.15.1

The Word export's author line carries the affiliation superscripts. The head
printed a bare name list above a numbered affiliation list nothing pointed
into: the front-matter probe flattened each author to a.name. It now returns
(name, affils) records, the numbers computed by Typst itself as positions in
paper-affiliations -- the same list the head prints, so the markers cannot
disagree with it -- and the resolver emits them as `#super[...]`, which
pandoc reads natively into real Word superscripts. Both config shapes
normalize in the probe (`affiliation: "..."` and `affiliations: (...)`); an
author with no resolvable affiliation gets no marker; the SI title block
keeps plain names, exactly as si-authors shows. Upgrade: copy
tools/resolve_typst.py and tests/run.py.

## 3.15.0

The Word export carries the whole paper, in the paper's order. Found by
actually reading a real manuscript's export: no figure numbers anywhere, no
SI title page, the reference list after the entire SI, and the back matter
missing outright. Each was a structural gap in the resolve -> pandoc route,
not a conversion bug, so each fix lives in the resolver or the exporter and
carries a regression case.

- Captions and headings now carry the PDF's numbers as literal text
  ("Figure 3: ", "2.1.", SI "S1"): pandoc numbers nothing, so every
  cross-reference the 3.14.0 pass resolved pointed at a number no caption or
  heading showed. The same event scan that numbers the refs writes the
  definitions.
- The back matter travels: the prose between BODY END and `#bibliography`
  (data availability, author information, acknowledgment) was dropped with
  the template, though a journal reads those sections from the Word file.
  The slice refuses the SI-appendix machinery (page break, counter surgery)
  when a manuscript has no bibliography to stop at.
- The bibliography stays in the PDF's position -- after the back matter,
  BEFORE the SI -- instead of being appended last. The exporter anchors the
  reference list there with a `#block[]<refs>` under the References heading,
  promoted to a Div by the new tools/refs_div.lua: citeproc fills a Div with
  id "refs", and without one appends the list at the very end of the
  document, under the SI.
- The SI gets its title block (heading, paper title, author line),
  synthesized from config.typ: the PDF builds it from layout primitives
  inside a docx-mode conditional, neither of which travels. A `#heading`
  CALL rather than `= ` markup, so it cannot tick Section S1 away from the
  SI's first real section.
- Keywords, and the `toc-graphic` / `toc-caption` bindings when the front
  matter has them, land under the abstract as plain content -- the same
  pieces the docx-mode front matter emits on the HTML route.
- check_citations no longer reads an email's `@` as a citation key: escaped
  (`\@scripps`) or mid-word (`"mailto:pgarrett@scripps.edu"`) is not
  citation syntax to Typst, and each briefly refused a build as "@scripps
  not in the bibliography" once the back matter traveled.

Upgrade: copy tools/resolve_typst.py, tools/export_docx.py, tests/run.py,
and the new tools/refs_div.lua.

## 3.14.1

The resolver test suite carries its own table fixture. The
`markup table gains a content block` case inlines its target file, and it
pointed at `si/example_table.typ` -- which exists here, and not in a derived
manuscript that deleted the example generators. Found porting 3.13.1 into a
real paper: the suite failed on a file the manuscript's analysis has every
right not to declare. The case now writes a temp table and resolves it by
absolute path. Upgrade: copy tests/run.py.

## 3.14.0

`just docx` now goes resolve -> pandoc: NATIVE editable Word equations, real
tables, and a reference list set by citeproc. The HTML route -- equations
rasterized into images -- is `just docx-html`, kept as a fallback while this
one earns trust. The 3.13.0 known gap is closed, plus one nobody had
measured:

- The bibliography: `#bibliography(...)` sits in back matter, which the body
  slice drops, so every citation in the export dangled. The resolver now
  carries the call through with its `style:` identifier resolved to the
  string literal in config.typ -- the resolved file compiles standalone,
  references and all. The exporter (tools/export_docx.py) swaps the call for
  its title as a heading and hands the .bib paths to citeproc, because
  pandoc's reader parses the call without wiring it in.
- Cross-references: pandoc renders a Typst ref as an EMPTY link -- no pages
  to point at -- so every "see Figure 3" silently became "see " in the Word
  file. The resolver now resolves each ref to the literal text the PDF
  shows, reimplementing the deterministic numbering: floats count per kind
  in document order (tbl/tab share the Table counter), headings nest, and
  the SI resets both with the "S" prefix, exactly as paper.typ's back-matter
  counter block does. A ref whose label no exported float or heading carries
  is an error, not a link left to vanish.
- Citation keys are checked against the .bib BEFORE converting: citeproc
  renders a missing key as bold prose and exits 0, which is a shipped-anyway
  failure this pipeline exists to refuse.
- Citations follow `<style>.csl` in the manuscript root when present; the
  scaffold ships american-chemical-society.csl to match the default
  paper-bib-style. Without one, pandoc's default applies, with a printed
  note -- visibly different, not silently wrong.

The docx-mode block in paper.typ is now load-bearing only for docx-html.
Upgrade: copy tools/resolve_typst.py, tools/export_docx.py,
tools/typst_prose.py, the justfile docx/docx-html/resolve/_stamp-manuscript
recipes, and your style's .csl; the tests gained export_cases().

## 3.13.1

Ten resolver fixes out of a code review, every one a way `paper.resolved.typ`
could differ silently from the PDF. The reviewed surface was small -- the
resolver, one shared regex, the tests -- but each bug shipped wrong output
without an error, which is the failure mode this scaffold exists to close.

- Raw spans are stashed before every pass and restored after: a documented
  `#s("id")` in backticks was being resolved or rejected, and a `#todo` in a
  fence refused an export the PDF builds clean.
- The `#todo` refusal now runs after the comment strip, so a note mentioned
  in a comment no longer blocks the export.
- Standalone `#import`/`#let`/`#set`/`#show` lines are stripped, exactly as
  readability.clean strips them. Left in, the "self-contained" output still
  imported the project helpers and the gitignored stats-rendered.json.
  Consequence: `refn()` is rewritten to its full definition,
  `ref(<x>, supplement: none)` -- plain `#ref()` rendered "Table Table S1".
- The matched leading `#` is captured and re-emitted for `fig`/`tbl`/`refn`:
  a markup-mode `#fig()` resolved to the literal words `image("...")`, and a
  markup-mode `#tbl()` now gains `#[...]`, since bare brackets in markup are
  text, not a content block.
- `ASSET_CALL` (typst_prose.py) gained a left word boundary, so a
  manuscript's own `#subfig()` is no longer matched on its `fig(` suffix.
  Its groups shifted by one; resolve_typst.py is the only consumer.
- Cross-reference labels may be multi-segment (`@fig:panel:a`), matching
  what typst_prose.CITE always allowed.
- si-body.typ is appended only when its `#include` did not survive the body
  slice, closing a double-SI path on manuscripts that include it inside the
  markers.
- `_abstract()` fails loud: a config.typ whose abstract the resolver cannot
  read is a ResolveError, not a silently empty Abstract section, and
  comments are stripped before the bracket count so a `]` in a comment
  cannot truncate it.
- tests/run.py: the fixture-stats swap is try/finally-guarded, SystemExit is
  caught per case (resolve_stats raises it for unknown ids), and each fix
  above carries a regression case.

## 3.13.0

`just resolve` -> `paper.resolved.typ`: the manuscript as plain Typst, with
every project helper replaced by what it produces. Groundwork, not yet an
export path.

WHY IT IS WORTH HAVING. Pandoc reads Typst -- a real evaluator, not a regex --
which means a Word file with NATIVE editable equations, and LaTeX for a
journal that demands source. It cannot evaluate OUR helpers, and those are
ours to resolve. One resolution step feeds every export; the alternative is
each exporter growing its own copy of `#s()`, which is how the word count,
the readability report and the narrator each grew one.

Measured on a real 3,259-line manuscript: 195 native Word equations, 36 real
Word tables, 19 images, 40 headings; in LaTeX, 221 math spans, 45 citation
commands, 215 cross-references, 34 tables. Zero raw-Typst leaks.

Four bugs found building it, all now regression cases -- three of which only
a real manuscript exposed:

- `#refn(\n  <tbl:x>,\n)`: the trailing comma typstyle leaves after breaking
  a long call. Every shared pattern in typst_prose.py ends `,?\s*\)` for this
  exact reason; the first draft's did not. Fourth time in this repository.
- si-body.typ documents its own usage with a literal `#s("id")` IN A COMMENT,
  so the resolver asked stats.json for a value named "id". Comments are
  stripped first now, whole-line only, as readability.clean does.
- The SI vanished: paper.typ `#include`s it OUTSIDE the BODY markers (back
  matter does, by this scaffold's convention), so slicing the body dropped it
  and with it every table. Read as its own file now, as readability.py does.
- An inlined table put `#table(` into `#figure(...)`'s argument list -- code
  mode, where a leading `#` is a syntax error. Wrapped in content brackets,
  which is what `include` meant semantically.

KNOWN GAP, measured rather than assumed: the resolved export is 2,029 words
short of the PDF, and 489 of the 700 missing vocabulary items are the
bibliography, which the resolver does not yet emit. Most of the rest are
pdftotext hyphenation artifacts. No evidence the reader loses prose -- the
gaps are things this tool does not write yet, and they must be closed before
any export path is built on it.

## 3.12.1

Math in the Word export rendered ~9% smaller than the text around it: frames
carry the manuscript's em (11pt, typically) and pandoc's Word body is 12pt,
and the rasterizer sized images by raw ink points. Each frame's em is now
read from its own style attribute and rescaled to Word's.

Found while chasing a report from dnoise that $m/z$ arrived in Word as "a
weird small artifact". The dominant cause there was notation, not pipeline:
in Typst math, `/` builds a stacked fraction, so $m/z$ was a tiny m-over-z
in the PDF too, and crop-to-ink turned it into a 5px image in Word. The
slash the field convention wants is written `$m\/z$`. Worth knowing before
writing any inline ratio.

## 3.12.0

Four packaged AI workflows, as skills in `.claude/skills/` that travel with
new-paper.sh: `/copy-edit` (a wording pass bracketed by the edit guard),
`/fix-verify` (the intended fix per finding class, as a table -- never
weakening a check), `/declare-number` (the four-tier ladder as a procedure),
`/new-figure` (all four steps, wordcount scope included). The design rule:
each skill encodes the pipeline's contracts and ENDS by running the check
that proves it behaved, so an agent cannot report success without the
pipeline agreeing. A generic prompt does not know it must never edit a
number; a shipped one does.

## 3.11.0

Two additions in the #lit() spirit -- inline, self-enforcing, each closing a
gap between what the pipeline checks and what authors actually do:

- **`just edit-baseline` / `just edit-check`**: prove a copy-edit pass changed
  only wording. Snapshots every number, label, reference, figure and heading;
  afterwards a number may be DROPPED (a note -- STYLE.md permits thinning) but
  never INVENTED (fatal), and references, floats and headings must survive
  exactly. Judged manuscript-wide, because content legitimately moves between
  main text and SI. Upstreamed from the koth manuscript, which wrote it for
  exactly this and ran it in anger first. Snapshots live in .edit-guard/,
  local state like .build-stamp.
- **`#todo("...")`: a note that cannot ship.** Renders as a loud marker in
  draft mode; PANICS `just paper` and `just docx`, so a final PDF with an
  unresolved note is not producible -- where a `// FIXME` comment survives to
  submission silently. Stripped by the extractors (a note is not prose), a
  no-op in the word count, and surfaced by `just prose-check` as
  unresolved-todo so the gate shows open notes without a build.

Found while wiring it: paper.typ had never received the `lit` import -- the
3.10.0 sed missed its exact line and the placeholder never calls lit, so
nothing noticed. The import list is now `lit, n, s, todo` in all three files,
and the failure it would have caused is the include-scope gotcha CLAUDE.md
already documents.

## 3.10.0

`#lit("40")`: vouch for a deliberate prose literal in place, instead of a
value-level exception in prose-check.toml far from the sentence. Renders as
the text typed (string argument required -- Typst rounds bare floats its own
way), silences unaccounted-number at that spot only, and deliberately does
NOT silence derivable-number: a computed value wrapped in lit() still gets
flagged, because vouching must not bypass the stronger rule. prose-check
reports how many literals are vouched inline, so the count cannot grow
silently. The four tiers, weakest claim to strongest: #lit() -> hand entry
with a note -> #s(). Recognized by both extractors with fixture coverage,
reflowed form included.

## 3.9.2

`just --list` is the first thing a newcomer sees, and ten of its descriptions
were sentence fragments -- "watch means restarting it.", "and the one uv knows
nothing about." -- because just shows the LAST comment line before a recipe,
and rationale appended after the description line decapitated it. The
convention is now stated at the top of the justfile and every block ends with
its one-liner. Four plumbing recipes (default, render-stats, check-declared,
check-build) went [private]: callable and documented, off the front page.

## 3.9.1

`check-stats-deep`'s summary said "(re-derived)" whether or not anything was:
on an all-hand-entered manuscript _rederive has nothing generator-owned to do,
and on a frozen analysis it degrades to a note -- both still wore the
verification label. The status now comes from _rederive itself: "N value(s)
re-derived", "nothing generator-owned to re-derive", or "could not re-run the
generator". Found by the koth-paper pipeline audit; dnoise's audit hit the
other branch of the same defect.

## 3.9.0

The checkers report through rich (one shared findings table in report.py --
severity styled, messages wrapping in their own column, everything through
Text so a bracketed range is not eaten as markup), and audiobook synthesis
shows a progress bar for the minutes it always ran silent (transient, and
absent from piped logs, which keep their per-chapter lines).

Plus four fixes from a downstream audit of the scaffold by the dnoise agent:

- **Narration read `\u{2082}` escapes aloud.** The fix existed in the shared
  layer for the word count and was never wired into audio -- and the golden
  file had blessed the broken narration. Proven by the goldens themselves:
  readability.txt said log2 (the character), narration.txt said the escape.
- **bib-audit reported correct software/data DOIs as unresolvable.** Crossref
  registers articles; Zenodo/figshare/Dryad mint through DataCite. A Crossref
  404 now falls through to DataCite, which resolves the DOI but has no
  retraction concept, and the summary says so.
- **The fixture's #s() ids resolved against the manuscript's stats.json**,
  coupling the permanent fixture to the placeholder analysis it exists to
  outlive. tests/fixture-stats.json is owned by tests/ now; the manuscript's
  file is the fallback for fixtures already adapted to their own ids.
- **The hand-vs-generator id clash said "rename one of them"**, the opposite
  of the migration handover where the ids SHOULD collide. The message now
  describes the handover (delete the hand entry, seeds fill in); the takeover
  stays manual, because a hand entry with a note is authored data.

## 3.8.2

`unaccounted-number` met its first real manuscript and produced 189 warnings.
Three fixes from the encounter: a clause comma is no longer part of the number
("median 1, mean 2.67" reported '1,'), digits inside an identifier are not a
result ("PXD070049" reported '070049'), and each document now shows eight
findings plus a count of the rest -- one value reported once, because a
189-line wall is read by nobody. On the same manuscript: 19 lines.

## 3.8.1

Two fixes found downstream, in the dnoise manuscript, and taken upstream:

- **`check-stats-deep` ran the generator with the toolchain's interpreter**,
  which lacks the analysis environment's dependencies (pandas, typically), so
  it died on ModuleNotFoundError -- downgraded to a "could not re-run" note.
  The strongest check in the pipeline silently reduced itself to nothing on
  exactly the projects with a real analysis. It runs through `uv run` now,
  resolved from the generator's directory like analysis/justfile does, with a
  sys.executable fallback when uv is absent.
- **Two tests hardcoded `figures/example_figure.png`**, which a real
  manuscript deletes in its second week; the tests then failed for a reason
  unrelated to what they check. The figure is discovered from `figures/` now,
  and the cases skip with a note when none exists.

## 3.8.0

The console reports render through rich, styled once in `tools/report.py`:
real tables, right-aligned numbers, styling dropped automatically when piped.
Piped output gets a 200-column console, because rich's 80-column fallback
truncated "numerals" to "nume…" -- worse than no styling at all.
`wordcount.sh` runs its formatting through `uv run` now (rich lives in the
locked environment), so doctor's python3 requirement belongs to the justfile's
inline recipes alone.

## 3.7.1

The build report was a wall on a real manuscript: three stacked header blocks,
two disagreeing columns both named "words", a nine-column density table, and
section names truncated at 34 characters in a report whose job is to name
sections. Now: `just paper` prints the word count and readability as eleven
lines (density moved fully behind `just density`, where CLAUDE.md always said
it lived); readability lost its own words column rather than disagree with the
journal count above it; density aligns full section names and reports
"value (median N)".

## 3.7.0

`just text-baseline` / `just text-diff`: snapshot the PDF's extracted text,
word-diff it after a structural refactor. The one property no other check
watches — verify guards the machinery, not the words. Word-level because a
reflow rewraps every line. pdftotext (poppler) joins `doctor` as an optional
tool.

## 3.6.1

MIGRATING.md: the runbook for moving an existing manuscript onto the scaffold —
phases, the paper-must-not-change invariant, the traps from 3.6.0. Excluded
from `new-paper.sh` copies, along with `.hash-cache.json` and `viz/`, local
state its exclude list predated.

## 3.6.0

Lessons from watching a real migration — the seat the scaffold had never sat
in.

- **`just adopt note="..."`** declares figures/tables whose analysis is gone:
  `origin.by = "adopted"`, note mandatory (the hand-entry contract). Hash and
  reference checks still apply; regeneration is honestly absent and the checks
  say so. A generator later calling `record()` with the id takes it over.
- **Three load-bearing constraints written down**: `analysis/` must live inside
  the manuscript (the provenance resolution depends on it); `#include` gives a
  file its own scope, so every included `.typ` needs its own imports; the BODY
  markers define what the word count *means* (back matter excluded), so a
  migrated headline number drops without an edit.

## 3.5.0

The README gained the pipeline's ideas as fifteen lines, audited against the
code. Twelve held; three fixes made the rest true:

- **`unaccounted-number`** (warning): a distinctive numeral matching *nothing*
  declared was the only silent number in the paper. Years and short counts
  skipped.
- **check-stats renders every entry**: a broken `fmt` edited into stats.json
  used to pass verify and kill the next build instead.
- **`tools/hashcache.py`**: verify re-hashed every declared input on every run,
  gigabytes included. A (size, mtime_ns)-keyed cache decides *when* to re-hash;
  the sha256 stays the only recorded truth; recording paths still hash bytes
  directly.

## 3.4.1

Ten defects in the 3.3.0/3.4.0 code, found by adversarial review, each
verified before fixing. The theme: stats.json became hand-edited JSON, and
hand-edited JSON can be malformed in ways the code crashed on or silently
accepted.

- A malformed `values` block was treated as empty and rewritten, deleting
  every hand entry. Now refused, like invalid JSON always was.
- `_rederive` ran the generator against an empty shadow, so stale seed guards
  judged the values and a guard death was downgraded to a note — deep checking
  silently disabled by the documented workflow. The shadow now starts as a
  copy of the real file; a guard violation there is an error.
- NaN passed every range guard after the per-bound rewrite. Explicit error now,
  in generator and gate.
- Unknown `expect` keys, quoted bounds, and list-shaped `pinned` blocks were
  silences or gate-killing tracebacks. All named error findings now.
- Deleting an author-owned field resurrected the seed via `old.get(f,
  seed[f])`. Deletion is an edit: it stays deleted.
- A v1-checksum mismatch is a warning, not an error — v1 covered value+fmt and
  cannot tell the documented fmt edit from tampering.
- `just pin` no longer marks builds STALE: the stamp hashes stats.json without
  `pinned`.
- `origin.at` moves when 35 becomes 35.0: value comparison checks type.

## 3.4.0

Three holes between "the checks pass" and "the submitted file is not stale":

- **check-build checks the output itself.** The stamp only proved a build
  happened from the sources, not that the file on disk is that build's output —
  a paper.pdf swapped in from Downloads passed as current. The stamp now
  records the output's hash too (mismatch: REPLACED), and the source hash is
  captured *before* the compile so a mid-compile edit errs toward stale.
- **`just preflight`**: fresh builds + verify + check-stats-deep + bib-audit as
  one command. Three "run before submitting" notes in three places was a
  conditional ritual, and those get skipped. `just assets` deliberately not
  included — a rebuild, not a check.
- **render-stats removes stats-rendered.json when stats.json is gone**, so the
  derived file cannot outlive its source and be read by a compile.

## 3.3.0

The ownership of stats.json split by field, following what each field is.

- **The script owns `value` (plus checksum and origin); `fmt`, `unit`, `desc`
  and `expect` are the author's**, edited in stats.json and surviving `just
  assets`. `st.add(...)`'s extra arguments seed a *new* entry only; a stale
  seed is ignored with a note. The fresh value is judged against the *file's*
  guard — the author's — with one-sided bounds supported. Editing `expect` went
  from undetectable drift to the supported way to state an assumption.
- Checksums narrowed to the value alone (v2); v1 still verifies so existing
  manuscripts upgrade cleanly.
- **`pinned`**: files no generator declares, watched by hand — declare
  `"path": null` in stats.json, `just pin` records the hash, `check-stats`
  reports changes.
- **`origin.at`** on every value and asset: when it last *changed*, not when
  the script ran — identical output keeps its date.
- Fixed: the CI figure-survival check counted `image(` calls, which went to
  zero when figures moved behind the manifest, so it compared against zero and
  could never fail (it now counts `fig("` references and fails on zero);
  `.build-stamp` now covers render_stats.py, typst_prose.py and typst2docx.py;
  assorted stale references from the stats.json move.

## 3.2.0

`just verify` re-ran the analysis: `check-stats` re-derived every value by
re-running gen_stats.py, invisible on the scaffold's 0.02s example and ruinous
on a real project. Re-derivation moved behind `just check-stats-deep`; the
default path reads files only. Two cheaper checks replace it: a per-generator
`sources` hash block (has the analysis moved) and a per-entry `checksum` (was
a generated value hand-edited). Provenance consolidated into
`_provenance.py`, which also stopped recording the contract modules — editing
`_assets.py`'s docstring used to mark every asset stale.

**Upgrading:** `just assets` once; add `inputs=[...]` to `st.write()`.

## 3.1.0

Subtraction: five things that stopped earning their place, mostly made
redundant by 3.0.0.

- **`.assets-stamp` removed.** assets.json had taken over both its jobs with
  strictly better messages. What went with it, stated plainly: an input a
  generator reads without declaring or importing is now invisible — and no
  mechanism can enumerate inputs and be right, so the author declares what
  matters. Mitigations: `_unclaimed` became an error; `record()` notes an
  empty input list.
- `check-assets-manifest` renamed to `check-assets` (the stamp freed the name).
- Removed: `source` in stats.json (write-only, superseded by `origin.by`),
  `s-unit()` (called by nothing), a stale root `__pycache__`.
- `verify` runs the two declaration checks as one stage.
- The figure/table docs stopped claiming "no wiring" — a new asset needs
  `record(...)`, an id reference, and (once per project) the wordcount eval
  scope.

**Upgrading:** `git rm .assets-stamp`; rename any `check-assets-manifest`
reference.

## 3.0.0

Everything generated is declared and referenced by id; nothing generated is
tracked in git; staleness is answered by content hashes, never git history.

- **paper.pdf untracked; `check-pdf` replaced by `check-build`.** Builds record
  a content stamp of their sources in the untracked `.build-stamp`; the check
  recompares. This also fixed two quiet holes: the docx mtime check's glob
  missed stats.json, and the git check's source list missed stats.typ and
  wordcount.typ. No check reads git any more, so everything works in an
  exported tree.
- **stats.json moved to the root and became a file you own.** Entries record
  `origin.by` (script or `"hand"`); a generator replaces only its own entries,
  so hand-added numbers survive `just assets` — previously `write()` rebuilt
  the file and they vanished. Hand entries require `origin.note`.
  `check-stats` re-runs guards against committed values and re-derives.
- **The rendered string left stats.json.** `value` + `fmt` only;
  `tools/render_stats.py` renders `stats-rendered.json` (gitignored,
  regenerated by every compile) through the one shared formatter,
  `typst_prose.display_of` — Typst has no format spec and rounds floats
  differently, so the display cannot be decided by whichever language reads it.
- **assets.json: figures and tables declared by `record(...)`, referenced by
  `fig("id")` / `tbl("id")`.** The manifest is on the compile path, so an
  undeclared id fails the build — the ledger is load-bearing, not bookkeeping.
  `prose-check` errors on a declared file named directly. Inputs are part
  automatic (the sys.modules walk — exact, since imports are Python-level)
  and part declared (data files — an audit hook cannot see C-level reads).
- Found while building it: a bare `fig()` call leaked into the word count and
  narration (both extractors strip it now); the first input walk recorded 257
  inputs for one figure because `analysis/.venv` is inside `analysis/`.

**Upgrading:** gitignore paper.pdf and .build-stamp, `git rm --cached
paper.pdf`; `git mv si/stats.json stats.json` and repoint stats.typ; add
`record(...)` to each generator; replace `image("figures/x.png")` with
`fig("id")` and `include "si/x.typ"` with `tbl("id")`; import and scope
`fig`/`tbl` in paper.typ, si-body.typ and wordcount.typ — missing the eval
scope leaves `just paper` working and `just wordcount` failing.

## 2.0.0

The scaffold became something that can be handed to someone else.

- **Toolchain moved to `tools/`** (the root is what a person edits and a build
  produces). Path constants became `ROOT = ...parent.parent`.
- **`scripts/new-paper.sh`**: the documented start was `cp -r`, which carried
  the scaffold's git history and made two checks answer the wrong question.
  The script copies with tar (symlinks survive), fills config.typ, builds both
  outputs, starts a fresh history. Tested in `tests/run.py`.
- **`just verify` and `just doctor`**: one command for the gate (the old
  instruction was a four-step ritual with conditions, and conditional rituals
  get skipped); one report of whether the external tools are present and new
  enough.
- **Typst floor is 0.14, not the obvious 0.13**: on 0.13 `just docx` exits 0
  and silently drops every figure. Measured, not read from a changelog. CI
  holds the floor.
- **CI**: the gate on a Typst matrix, a generated manuscript, and audio on
  Linux + macOS — because every prior bug was found by slow hand-porting.
- **Piper became a uv dependency** (abi3 wheels: Linux, both Macs, Windows),
  replacing an x86_64-only curl'd tarball.
- **The SI could not use generated numbers**: only paper.typ imported
  stats.typ, and `include` gives a file its own scope. si-body.typ imports it
  now.
- **Four extractor leaks fixed** (`#n()`, bare `#link("url")`, bare `#table(`,
  footnotes welding onto words), all with fixture cases.
- `.assets-stamp` gained an output hash, so a hand-edit to a generated file
  was finally caught. LICENSE (MIT) added; AGENTS.md symlinks CLAUDE.md.

## 1.6.0

The bibliography is checked. Offline in prose-check: `duplicate-reference`
(error; same DOI twice), `uncited-reference`, `missing-doi` (2000 onward —
older work predates DOIs), `implausible-year`. Online in `just bib-audit`:
every DOI against Crossref for resolution and retraction — not in `verify`,
because a gate that fails on a slow API gets skipped. The retraction check
shipped reading the wrong Crossref field and was caught only by testing
against a known-retracted DOI; a test pins the field.

## 1.5.0

Spell checking via codespell's confusion pairs, chosen by measurement: on
15,175 real words, pyspellchecker flagged 418 (the subject matter),
proselint 7 (mostly tool flags), codespell zero false positives and every
injected typo. Runs on code-removed prose. Words adjacent to a hyphen are
skipped (codespell's fragment entries fire wrongly on split compounds) but not
for the British list, which must catch `colour-coded`.

## 1.4.0

Severity and vocabulary became the project's call: `[severity]` re-rates any
rule, `[vocabulary.*]` adds/removes words. The `RULES` registry stays in
Python — it is a manifest of what the code implements, not configuration.

## 1.3.0

Print-proof checks: `low-resolution-figure` (effective dpi at the *rendered*
width, against the measured 160 mm text block — it immediately caught the
scaffold's own example at 227 dpi, fixed in the generator) and
`oversized-table` (columns, rows, longest cell; bracket-depth parsing because
a lazy regex cuts a cell at its first inner bracket; all three `columns:`
spellings including `(1fr,) * 12`).

## 1.2.0

- **`just draft`**: unresolved `#s()` renders as `?id?` in `paper-draft.pdf`,
  never `paper.pdf`, so a placeholder cannot reach a file mistaken for the
  paper. `n()` still fails — no placeholder can sit inside arithmetic.
- **`orphaned-asset`**: a generated file the manuscript no longer includes was
  regenerated forever while appearing nowhere.
- **audio/ became genuinely optional**: deleting it used to break `just all`
  and the test suite.

## 1.1.0

Numbers in prose are generated, guarded, and checked. `gen_stats.py` declares
them; `#s("id")` reads them back and panics on an unknown id; guards
(`sign=`, `between=`) fail the build when the analysis changes meaning under a
sentence; `derivable-number` flags a typed numeral matching a declared value.
Only distinctive values are compared — a declared `3` would match every `3`.

## 1.0.2

Five fixes from porting into a second manuscript (`koth`): native `#ref(` was
unrecognized (68 leaks); reference *sites* were counted as float definitions
(a phantom "Figure 10"); `tab:` labels were invisible to the float checks (37
tables exempt while reporting clean); `\u{XXXX}` escapes reached the narrator
verbatim ("log u 2082", 41 times); `word-repetition` fired on repeated file
paths (12 of 18 findings were noise).

## 1.0.1

Three fixes from porting into a real manuscript (`FeNovo`): `just fmt` rebuilt
the PDF (a backquoted string in a just message is a shell command); the
sentinel gap turned unwrapped inline code into a false doubled-word; CLAUDE.md
described checks removed in 1.0.0.

## 1.0.0

First release, extracted from the `dnoise` manuscript, where every piece was
written in response to something that had actually gone wrong. Typst build
with SI appended in one compilation; Word export via HTML + pandoc with the
template bypassed and equations rasterized; `config.typ` as the single
identity source; `analysis/` inside the manuscript writing directly to
`figures/` and `si/`; word counts, readability, density, prose-check;
typstyle formatting pinned to the same width as the editor; staleness checks;
offline Piper audiobooks.

---

## Decisions reversed

Each of these was built, shipped, and then undone. They are recorded because all
of them look reasonable in the abstract, and the reasons they failed are only
visible from use.

### Construct coverage in the placeholder prose

The first skeleton put one of every special-cased Typst construct into
`paper.typ`, so `just all` on a fresh clone was a smoke test. Placeholder prose
is deleted the moment real writing starts, so the test ran exactly once and
then the constructs went untested for the life of the project. Coverage now
lives in `tests/fixture.typ`, which is never part of the manuscript.

### A general "-ise to -ize" spelling rule

The regex for the whole `-ise` family flagged the project's own software name,
`dnoise`/`denoise`, on every mention. A checker that cries wolf on the
project's vocabulary gets switched off within a week. The British list is
explicit and grown by hand.

### Spell-checking inline code

`readability.clean` unwraps inline code into a bare word (journals count it),
and spell-checking that output flagged the column name `Ms1.Normalised` as a
British spelling. The spelling pass runs on a code-removed variant instead.

### Commit dates for generated-asset staleness

Comparing commit dates of `figures/` against `analysis/` cannot handle
deterministic generators: re-running after a no-op edit produces nothing to
commit, so the check nagged forever with no way to satisfy it. Content hashes,
no git.

### `figures.map` and an external analysis tree

The analysis was a sibling directory figures were copied out of. The copy was
the whole problem: a re-analysis updated the plot upstream, the copy stayed
put, and the PDF kept rendering a figure that no longer matched its own
caption. The analysis moved inside and writes to the destination.

### `fmt-verify`, and five other recipes

`just --list` reached 30 entries. `fmt-verify` was superseded, compared a
no-op, and restored via `git checkout --`, the most dangerous line in the
repo. The `.m4b` staleness checks went too: every prose edit marked the
audiobooks stale, clearing that cost minutes of narration, and a warning
almost always present and almost never acted on erodes trust in the rest.

### The HTML Word route as a fallback

Word export first went Typst → HTML → pandoc, with a `docx-mode` flag that
bypassed the PDF template and `html.frame()` plus a rasterizer to bring the
equations Typst's HTML export drops back as images. When the pandoc route
arrived it was kept as a fallback "while the new one earns trust". It never
paid its way: it doubled the preamble with conditionals every editor had to
read past, it set the typst floor for a reason no longer relevant, and when the
SI got its own reference list it could not carry it, since the HTML export
drops the grid that list is set in. A fallback that refuses the scaffold's own
manuscript is not a fallback. Removed.

### Re-deriving every value in `just verify` (3.0.0 → 3.2.0)

The strongest possible stats check, run on every verify — affordable only
because the scaffold's own generator reads a four-row CSV. On a real analysis
the gate costs the analysis. The general lesson: the scaffold cannot surface a
cost that scales with project size, so anything whose cost depends on scale
needs a deliberate "what does this look like at 1000×" pass, not a green gate
on the example.

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

**A check can die silently when the thing it counts moves.** The CI
figure-survival check counted `image(` calls; the assets manifest reduced that
count to zero, and a comparison against zero passes forever. A counting check
must also fail when it counts nothing.
