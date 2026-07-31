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

= Math and code

Inline math such as $alpha$, a subscripted one such as $t_"obs" <= t_"max"$, and a
quoted-subscript one such as $|"median"_"orig" - "median"_"arm"|$ are verbalized by
the narrator and dropped by the readability report. Symbol tokens
#sym.minus 3, #sym.tilde 5, and 10 #sym.plus.minus 2 become words.

A display equation is dropped rather than read aloud:

$ E = sum_(i=1)^n w_i (x_i - mu)^2 $

Block code is exempt from the word count and skipped by the narrator:

```python
def example(threshold: float = 0.5) -> bool:
    return threshold > 0
```

Inline `code` terms, by contrast, count as ordinary words.

= Figures and tables

Whole figures, including their captions, are excluded from the word count and are
never narrated.

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
