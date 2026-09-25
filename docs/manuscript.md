# The manuscript sources

How `paper.typ`, `config.typ` and `si-body.typ` fit together.

## `config.typ` is the only place the paper's identity lives

Title, authors, affiliations, abstract, keywords, date, institution, and
bibliography style. The PDF template reads it, the Word front matter is derived
from it (including the numbered affiliation superscripts, so they cannot drift),
the word counter counts the abstract out of it, and `audio/config.py` parses the
title out of it so the narration can never announce a title the paper no longer
has.

## The BODY START / BODY END markers

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

## Two reference lists: the SI carries its own

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

A journal that wants one list for the whole paper: remove the Alexandria
setup and declare `[bibliography] single = true` in `project.toml`
([hooks.md](hooks.md#one-reference-list)).

The SI's list is excluded from the SI word count (the `<si-references>` label,
in `wordcount.typ`), dropped by the readability report and the narrator, and
omitted from the plain-text review copy, exactly as the main list is. `just
docx` sets both lists, one citeproc run each.

An SI that cites nothing through the prefix prints no list and no heading.
Alexandria's own `bibliographyx` prints its "References" heading regardless,
so `si-body.typ` defines a local `bibliographyx` above the call that renders
the list only when it has entries; the call itself is unchanged. The resolved
text and the SI Word file drop the list in the same case. `full: true` keeps
it.

A manuscript that wants one list deletes the show rule and the
`#bibliographyx` call and writes plain `@key` throughout; every tool then
behaves as it did before this existed.

## Describing the SI: `#si-contents` (opt-in)

Journals ask for a sentence saying what the Supporting Information holds (ACS
calls it "Associated Content"). Written by hand, it drifts: a section is
renamed or a figure added and the sentence still lists the old ones. To derive
it instead, import the helper `assets.typ` ships and write `#si-contents`
where the sentence goes (normally in the back matter, outside the body
markers, so it does not count as prose):

```typst
#import "assets.typ": fig, tbl, si-contents
```

It reads the SI's numbered level-1 headings and float counts after the
`<si-start>` probe at layout time. Before 5.0.0 this block was copied into
each `paper.typ`; a paper that still has its own `#let si-contents` either
keeps it (and does not import the name) or deletes it and imports it.

It prints, for example, "Sections S1 Methods, S2 Data. Figures S1–S3 and
Table S1 (PDF)." The Word export substitutes the same sentence from its own
numbering pass, which counts **labeled** SI floats only; give every SI figure
and table a label, as cross-referencing needs anyway. `just test` compiles
the helper in `assets.typ` and compares it with the resolver's sentence, so a
change to one is a change to both. A manuscript that does not write `#si-contents` is unaffected.

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
