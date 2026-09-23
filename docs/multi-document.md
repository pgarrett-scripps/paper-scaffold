# Multi-chapter manuscripts

An optional `manuscript.toml` gives one project named PDF targets. A dissertation
can have a full-document target and one target per chapter, all using the same
chapter sources and one copy of the tooling. Existing paper projects need no
manifest or source changes; their commands keep the original behavior.

Native PDF builds support counted parts, readability, chapter checks, and
scoped wording-edit guards. Word export additionally supports the explicit
**dissertation template contract** in `examples/dissertation/`; arbitrary custom
Typst templates need their own capture adapter. `examples/chapters/` remains a
PDF-only example. Word export refuses an unsupported layout rather than
silently dropping front matter. Review visualization and narration still use
the single-paper path.

## Dissertation Word export

The dissertation adapter was ported from a working eight-chapter manuscript.
It evaluates Typst content, resolves each chapter's bibliography independently,
joins Pandoc trees, and writes one editable DOCX. It never converts a PDF into
Word. The included ACS CSL supplies matching numeric chapter references.

Try the complete example from the scaffold root:

```bash
uv run python tools/document_docx.py --root examples/dissertation
uv run python tools/document_docx.py first --root examples/dissertation
uv run python tools/document_docx.py --check --root examples/dissertation
```

In a project with the scaffold tools and justfile, `just paper` detects
`manuscript.toml`, builds all named PDFs, the default document's DOCX, and its
plain-text review copy. `just docx first` exports one chapter; `just docx all`
exports every target. `just document-docx` is an explicit equivalent for the
default Word target, and `just docx-check` checks its freshness without building.
`just document all` remains the PDF-only command.

Copy the example's `lib/`, `code.typ`, `word/reference.docx`, ACS CSL, manifest,
and wrappers together, then replace the example chapter content. The adapter
expects `lib/template.typ` with `dissertation` and `chapter-title-page` wrappers,
`lib/supplements.typ`, chapter IDs and citation prefixes, and an `abstract` part
in the full document's entrypoint. Keep the template's capture points aligned
with `tools/word_capture.py` when changing its implementation. Unknown semantic
constructs fail the export and preserve the last successful DOCX. The example
layout is a starting point, not a claim of compliance with any institution.

The Word template controls paragraph and character styles. Edit
`word/reference.docx` in Word to customize them; normal builds never overwrite
it. `uv run python tools/word_reference.py --root PROJECT` deliberately resets
it to the provided dissertation styles. Page sections, figure bounds and table
geometry are handled by the adapter and need code changes for a different page
layout. The defaults use Letter paper with one-inch margins, a full title page,
a separate copyright page, Roman front matter, and Arabic numbering from the
abstract. Major front-matter sections, chapter openings, chapter abstracts,
supplemental sections, and reference lists start on new pages. The first section
after each chapter abstract also starts on a new page; ordinary sections flow
continuously, with headings kept with their following content. These boundaries
and recalculated page numbers are automatic on every build.
The contents has linked page numbers, and the figure/table lists
retain complete captions with each opening sentence (the title) bold and the
remaining explanation in regular weight, preserving italics and equations;
bold emphasis stays in the body captions. Explicit table proportions, native equations, chapter
references and verbatim code remain editable.

Full front-matter pagination requires LibreOffice (`soffice`) and Poppler
(`pdfinfo`) on PATH. Page numbers are calculated from a temporary DOCX render;
only cached numbers are copied back. The original DOCX is never resaved through
LibreOffice. Font availability affects pagination, and final Microsoft Word
layout still needs review in Word. The DOCX also sets `updateFields`, so Word
recomputes every contents, figure and table page number from its own pagination
on open; the cached numbers are the fallback for viewers that do not update
fields. If the LibreOffice pass fails, the build reports it and keeps the DOCX
with uncached placeholders, which Word still fills on open. Captions carry
`keepLines`, so a caption never splits across a page. Changes to the Word template, CSL, tools, inputs or output invalidate
its separate `.build-state/word/` record.

Run `just test-docx` for the content, layout and template regression checks.
The complete scaffold `just test` also includes these checks.

## Try the example

From the scaffold root:

```bash
uv run python tools/documents.py build all --root examples/chapters
uv run python tools/documents.py verify all --root examples/chapters
uv run python tools/documents.py metrics thesis --root examples/chapters --json
```

The example produces a combined PDF and two chapter PDFs under
`examples/chapters/build/`. It uses Alexandria for separate chapter references;
the document tooling does not prescribe a bibliography or layout package.

For a project with the scaffold justfile:

```bash
just documents
just document all
just document methods
just document-verify methods
just document-metrics methods
just document-edit-baseline methods
# Edit wording in the chapter.
just document-edit-check methods
```

The default target is selected when `document` or `document-metrics` has no
argument. `document-check` and `document-verify` default to all targets. Checks
never rebuild. Metrics come from a successful, current build; stale metrics
fail and name the rebuild command.

## Manifest

```toml
schema_version = 1
default_document = "thesis"

[parts.methods]
source = "chapters/methods/chapter.typ"
bibliography = "chapters/methods/references.bib"
citation_prefix = "methods-"

[documents.thesis]
entrypoint = "dissertation.typ"
output = "build/dissertation.pdf"
parts = ["methods"]

[documents.methods]
entrypoint = "chapter-methods.typ"
output = "build/methods.pdf"
parts = ["methods"]
```

Add parts and list them in each document's rendered order. IDs must contain
letters, numbers, underscores or hyphens, start with a letter or number, and
cannot be `all`. Paths are relative to the manifest, must stay inside the
project, and must not target build-state or git directories. Source files and
output paths must be distinct within their respective lists. Unknown settings,
missing files, undeclared parts, duplicate includes and count-order mismatches
are errors, not silently ignored configuration.

Each part has exactly one pair of marker comments:

```typst
// Chapter imports, title page and contributions go above the markers.
// >>> BODY START
== Abstract
The chapter's abstract and prose go here.
// <<< BODY END
// The chapter's bibliography and uncounted back matter go below.
```

Keep imports in each included file's own scope. The example has author-owned
standalone wrappers that apply the same layout and bibliography rules before
including each chapter. Builds never regenerate or replace those wrappers.
Institution-specific margins, front matter and page-number rules belong in the
project's template. Decide how standalone chapters handle cross-chapter
references explicitly; a reference to an omitted target will fail compilation.

A part may also be a marked abstract within the main entrypoint. This lets the
full dissertation report its abstract separately while standalone chapters
omit it. Chapter abstracts inside chapter markers count as chapter prose.
Only declared parts are prose-checked and measured; author/contribution blocks
and other unmarked front/back matter are not included. Compilation and source
fingerprints still cover their actual inputs.

## Counts and checks

Word counts use the same pinned Typst wordometer and exclusions as the paper
counter: citations, references, figures/tables/captions, math and block code do
not count; headings and inline code do. Readability uses the existing extractor,
which also excludes headings. Its word total is therefore a different measure.
Metrics report the scope alongside results in JSON. The per-part metrics are
also stored in `.build-state/documents/<id>.json`.

Counting instruments a temporary copy, preserving include locations and macro
imports. The final PDF is compiled from the original, uninstrumented sources.
The count query must find each declared part exactly once and in manifest order.
Literal nested prose includes are expanded for prose checking. Dynamic prose
includes fail as unsupported instead of producing incomplete counts/checks that
look successful. Arbitrary Typst-generated prose is outside the source-based
checker, just as it is for single-paper checks.

Bibliography paths and prefixes are optional; declare them when a part owns a
reference list. Bibliography checks strip the declared prefix from citation keys
and keep separate chapter lists separate. Typst compilation establishes actual
reference resolution. Shared `stats.json` and `assets.json` declarations can use
chapter-prefixed IDs; source tracing follows every declared document's literal
includes/imports. `document-verify` runs the existing project-wide declaration
checks when manifests are present. It also checks prose, chapter bibliography
metadata, and selected PDF freshness. It does not claim formatting, online DOI
auditing, or deep reanalysis. Keep project-specific checks in your `verify`
recipe, and run the scaffold test suite when updating the tooling.

Copied numbers and figures do not automatically gain analysis provenance.
Migrating rendered paper text retains that limitation until declarations are
deliberately adopted. Do not label an imported value as freshly recomputed.

## Build state and upgrades

Each output records its own content hashes, compiler-discovered dependencies,
selected manifest configuration, executing tool versions, and PDF hash. Editing
chapter B invalidates B and the combined dissertation, while A stays current
unless a shared input changes. A failed compile, changed input during build,
unstable dependency graph, or failed count query preserves the last good PDF.
Builds share the existing project lock, so simultaneous publishers are refused.
The compile, the count query and readability scoring run concurrently; the
fingerprint checks cover all three, and a build that stops early kills the
compilers it started.

Keep one toolchain per dissertation. Upgrade tooling together, preserving the
manifest, prose, templates, bibliography rules, and local exceptions. Follow
`docs/migrating.md`: build a baseline, compare extracted PDF text at each
phase, and inspect rendered pages. Record the imported scaffold version and any modified
tool hashes. This release does not introduce an automatic upgrade/merge command.
