# Slides and audio

Talk decks and narrated audiobooks: both reuse the manuscript, both sit outside the gate.

## Slide decks reuse the paper's material, and are outside the gate

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
`manuscript.toml` project (see [multi-document.md](multi-document.md)), which
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

## Audio

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
