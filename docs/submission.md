# Submission outputs

The journal upload set built by `just submission`.

## The upload set: `just submission`

A journal's form wants the manuscript, the SI, the graphical abstract and a
cover letter as separate files. `just submission` writes them to `submission/`
with a `manifest.json` (each file's role, hash, and the manuscript it came
from), after a fresh `just paper`:

- `manuscript.pdf` and `supporting-information.pdf` are page ranges of ONE
  compile of the captured manuscript, cut at the `<si-start>` probe in
  `paper.typ`. The SI is still an appendix of the same document, so its
  numbering and every cross-reference match `paper.pdf`. The graphical
  abstract lands per `[placement].submission` in `journal.toml` (default
  `journal`: the last page of the main text).
- `manuscript.docx` and `supporting-information.docx` are the Word projection
  split at its SI heading, each converted by the ordinary Word export.
- `toc-graphic.<fmt>` is the declared `toc-graphic` in the profile's
  `[graphical-abstract] file-format`, flattened to RGB, with its resolution set
  so it fits the journal's box, and refused below `min-dpi`.
- `cover-letter.pdf` is `cover-letter.typ`, which reads the title and authors
  from `config.typ`, numbers through `#s()`, and the journal name from the
  profile. Delete the file and the step is skipped.

The split files refuse to build while the source differs from the last
`just paper` capture. Each output is recorded in `.build-state/submission.json`.
The set is outside `verify` for the audiobooks' reason: `just check` notes a
stale set, `just check-submission` fails on it, and `just preflight` rebuilds
and checks it.
