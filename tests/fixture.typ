// =============================================================================
// EXTRACTOR FIXTURE. This is not part of the manuscript and is never included by
// paper.typ. Do not delete it and do not "clean it up" -- it is deliberately a
// dense, ugly pile of every Typst construct that readability.py,
// audio/extract_prose.py, and wordcount.typ handle specially.
//
// `just test` runs the extractors over this file and diffs the result against
// tests/expected/. It then reflows a copy with typstyle and asserts the result is
// unchanged, because a line break in the wrong place is how these break.
//
// Add a case here whenever you add a construct to the manuscript that any
// extractor has to know about. Regenerate the golden files with `just test-update`
// after reviewing the diff.
// =============================================================================

#let refn(l) = ref(l, supplement: none)

// >>> BODY START

= Citations and cross-references

The word counter excludes citations, the readability report drops them, and the
narrator deletes them rather than reading a key aloud @lovelace1843. Two in a row
@lovelace1843 @hopper1952 must not leave a doubled separator. A parenthetical
reference (@fig:fixture) disappears whole, including its brackets. A mixed
parenthetical (@fig:fixture, Tables #refn(<tbl:fixture>) and #refn(<tbl:fixture>),
@sec:second) is the case that broke once, because the closing paren of the inner
call ended the outer parenthetical early.

An ordinary reference to @sec:second keeps its supplement. A bare-number one
prints as Section #refn(<sec:second>) through the helper.

Typst's own #ref(<sec:second>) form has to be stripped too, and is the more
natural thing for an author to write. A pattern that knew only the helper left a
bare "ref" in the word count, the reading-level score and the narration, and went
unnoticed because the PDF was correct throughout.

= Inline markup <sec:second>

*Strong text* and _emphasis_ both reach the prose as plain words. An italicized
binomial such as _Saccharomyces cerevisiae_ is the two-word case that a reflow
splits down the middle. So is _E. coli_ directly after a slash, as in
human/yeast/_E. coli_, which must still be recognized.

Things that look like markup but are not must survive untouched: the glob
`smooth_*`, the pair `msms_*`, the cleavage value `"K*,R*"`, and an identifier
like `analysis.tdf_bin`. A leading-dot term such as `.docx` must not be welded to
the word before it.

A link to #link("https://typst.app")[the Typst website] keeps its shown text and
drops its URL.

A link with NO shown text, #link("https://typst.app"), is the form a data
availability statement is written in, and it renders as the bare URL. It has to
go the same way: a pattern that required the bracketed text matched none of
these, so the whole call reached the word count and the narrator read the URL out
loud. The reflowed form #link(
  "https://typst.app",
) must go too.

A table written straight into the prose, rather than wrapped in a figure, is
excluded from the word count like any other table:
#table(columns: 2, [Condition], [Value], [alpha], [1.0])
and the text continues after it.

A footnote attaches to the word it annotates, with no space between
them#footnote[Which is exactly the problem: stripped without a gap, the note
welds onto that word and the pair counts and narrates as one.], and must not be
welded to it.

= Math and code

Inline math such as $alpha$, a subscripted one such as $t_"obs" <= t_"max"$, and a
quoted-subscript one such as $|"median"_"orig" - "median"_"arm"|$ are verbalized by
the narrator and dropped by the readability report. Symbol tokens
#sym.minus 3, #sym.tilde 5, and 10 #sym.plus.minus 2 become words, and an arrow
reads as a word too: 0.43 #sym.arrow.r 0.49. A token with no mapping is dropped
rather than spelled out: 0.5 #sym.prec 0.9.

A reference list that loses its numbers must not keep the conjunction that joined
them (Tables #refn(<tbl:fixture>) and #refn(<tbl:fixture>)).

An explicitly signed number, which is what a generated value formatted `+.2f`
looks like, is spoken with its sign rather than read as a bare figure: +1.09
against a baseline. A plus that is not a sign must survive untouched, as in
`C++11`.

#let fixture-directive = 1
// A Typst directive and a line comment must never be narrated.

A display equation is dropped rather than read aloud:

$ E = sum_(i=1)^n w_i (x_i - mu)^2 $

Block code is exempt from the word count and skipped by the narrator:

```python
def example(threshold: float = 0.5) -> bool:
    return threshold > 0
```

Inline `code` terms, by contrast, count as ordinary words.

A Unicode escape denotes a character and must reach the prose as one: a subscript
written log\u{2082} is a single word to a reader, not the four the raw escape
tokenizes into, and the narrator needs a character it can speak.

= Numbers read from the analysis

A generated number must be RESOLVED rather than stripped or left alone. The
extractors read the source and not the PDF, so a stripped `s` call silently
deletes a figure from the word count and a spoken sentence, while an unstripped
one leaks the call text into both. Across #s("cohort.n_conditions") conditions
and #s("cohort.total_n") participants the treated group scored
#s("effect.treated_over_control") over control, a #s("effect.treated_fold")-fold
change, best in #s("effect.best_condition").

This paragraph exists mainly for the reflow: `just fmt` with --wrap-text breaks a
long line INSIDE the call rather than before it, so any of the calls above can
arrive with the id on its own line and a trailing comma after it. The next one is
written that way explicitly, so the case stays covered even if the wrapper stops
choosing to break here: #s(
  "cohort.total_n",
) participants, already exploded.

The raw-value helper resolves too, to the unrounded value rather than the display
string: #n("cohort.total_n") participants and #n("cohort.n_conditions")
conditions. It is rarer in prose than `s`, and went unhandled for exactly that
reason until it leaked verbatim.

A note to self must vanish from the count and the narration
alike#todo("verify the buffer batch against the lab notebook"), including the
reflowed form#todo(
  "and this one arrives pre-exploded",
), while the prose around it survives.

A vouched literal resolves to exactly what was typed: the column ran at
#lit("40") degrees with a pooled mean of #lit("2.2"), and the exploded form
survives a reflow the same way the stats calls do: #lit(
  "12,345",
) events in total.

= Figures and tables

Whole figures, including their captions, are excluded from the word count and are
never narrated.

A generated figure or table is pulled in by id rather than by filename, through
the helpers in assets.typ. Nearly always inside a `#figure` block that is stripped
whole, so the case that matters is a bare one in running prose: here is a
figure #fig("fig.example") and here is a table #tbl("tbl.example"), both of which
must vanish rather than leaving the id behind to be counted and read aloud. A
call carrying layout arguments #fig("fig.example", width: 70%) goes the same way,
as does the reflowed form #fig(
  "fig.example",
) that a wrapped line produces.

#figure(
  table(
    columns: 2,
    table.header([Key], [Value]),
    [alpha], [1.0],
  ),
  caption: [This caption must not appear in the extracted prose, and neither must
    the word _fixturecaption_, which exists only so a leak is greppable.],
) <tbl:fixture>

#figure(
  rect(width: 2cm, height: 1cm),
  caption: [A second caption, also excluded. Sentinel: _fixturecaption_.],
) <fig:fixture>

// <<< BODY END
