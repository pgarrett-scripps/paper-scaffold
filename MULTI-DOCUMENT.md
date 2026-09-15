# Multi-chapter manuscripts

An optional `manuscript.toml` gives one project named PDF targets. A dissertation
can have a full-document target and one target per chapter, all using the same
chapter sources and one copy of the tooling. Existing paper projects need no
manifest or source changes; their commands keep the original behavior.

This first release supports native PDF builds, counted parts, readability,
chapter prose/bibliography checks, and scoped wording-edit guards. It does not
adapt chapter bibliographies or custom dissertation templates to Word, resolved
version review, visualization, or narration. The existing `docx`, `review`, `viz`,
and audio commands remain single-paper commands. Do not run them against a
chapter project and assume they cover it.

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

Keep one toolchain per dissertation. Upgrade tooling together, preserving the
manifest, prose, templates, bibliography rules, and local exceptions. Follow
`MIGRATING.md`: build a baseline, compare extracted PDF text at each phase, and
inspect rendered pages. Record the imported scaffold version and any modified
tool hashes. This release does not introduce an automatic upgrade/merge command.
