# Prose checks, formatting and tests

The checks that read the writing, the formatter, and the extractor tests behind them.

## Formatting: the editor and the CLI must agree

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

## Reading the prose metrics

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

Two more warnings cover how the main text sends a reader into the SI.
`cross-reference-order` numbers the SI's floats by where they sit in the SI and
requires the main text to reach them first in that order (Figure S2 before S6),
which the per-document order check cannot see. `unreached-si-section` names a
labeled level-1 SI section that the main text never points at, by its label,
a subsection's label, or a float inside it.

Two house-style rules are off until `prose-check.toml` names them in
`enable = [...]`, because only some journals want them. `list-in-prose` flags
a bulleted (`- `) or numbered (`+ `) list item in running prose, and
`bold-in-prose` flags bold used for emphasis, allowing a bold span alone on its
line or a run-in label that opens a line and ends in a period or colon
(`*Early stopping.* Extension halts...`). Both read the raw source, skipping
comments, code, math and figure blocks, since the cleaned prose has already
unwrapped the markup they are about.

## Numbers about the draft: `just viz`

`just viz` writes `viz/report.json` alongside its plots. Read it rather than
re-deriving anything from the source: it already holds the section metrics, the
longest sentences with their text, which floats are cited once or not at all,
and the bibliography's age and self-citation share. Deriving those separately
gets a different answer, because this pipeline strips citations, math, code and
captions before measuring anything and an ad-hoc count does not.

Two more worth running by hand, not part of the gate: `just density` shows which
section is densest relative to the rest of the paper, and `just doctor` reports
whether the external toolchain is present and new enough.

## Vocabulary review: `just word-audit`

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

## Suppressing a finding: `prose-check.toml`

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

## `tests/` is the permanent smoke test

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
