# Journals and word limits

Journal profiles, and the word-count scopes and limits they join.

## Journal profiles: the venue's limits, with their source

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
