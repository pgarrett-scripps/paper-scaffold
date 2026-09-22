# Getting started

Starting a paper, what the toolchain needs, and the pitfalls that bite first.

## Quick start

```bash
git clone https://github.com/pgarrett-scripps/paper-scaffold
cd paper-scaffold
just doctor                          # is the toolchain present and new enough?

./scripts/new-paper.sh ~/papers/my-paper
```

The script asks for the title, author, and the rest of the identity, copies the
working files, fills in `config.typ`, builds the first PDF, and starts a git
history that belongs to the new paper. Every field also has a flag, so a
scripted run needs no terminal:

```bash
./scripts/new-paper.sh --yes --title "My Paper" --author "Ada Lovelace" ~/papers/mine
./scripts/new-paper.sh --help
```

**Do not start a paper with `cp -r`.** It copies `.git` too, so `just version`
reports the *scaffold's* last commit as the manuscript's state — confidently, and
wrongly. It also drags along `.build-state/`, which then claims the new paper's
outputs were built from sources it has never seen.

Then, in the new directory:

1. Replace the abstract in `config.typ`. Title, authors and keywords are already
   filled in; the abstract is prose and is left for you.
2. Replace the placeholder prose in `paper.typ` and `si-body.typ`.
3. Replace `references.bib`.
4. Put your analysis in `analysis/`, keeping `just assets` as its front door. Or
   delete `analysis/` entirely if the paper has no generated assets.

Nothing else should need editing. Use `just verify` for local consistency
checks and `just preflight` before an actual submission. Neither replaces
reviewing the manuscript's scientific content.

Three parts are optional. `analysis/` (no generated assets) and `audio/` (no
narration) can simply be deleted: every recipe and check adapts rather than
failing. The generated-numbers mechanism (`stats.typ` + `stats.json` +
`analysis/scripts/gen_stats.py`) and the generated-asset one (`assets.typ` +
`assets.json`) also come out, but not by deleting alone —
Typst cannot conditionally import a file that is not there, so three `.typ` files
have to drop their import. The exact edits are under
[Numbers in prose](numbers.md#numbers-in-prose-sid-not-a-typed-numeral).

## Requirements

Install [Typst](https://github.com/typst/typst),
[just](https://github.com/casey/just), [uv](https://docs.astral.sh/uv/), and
[Python 3.10+](https://www.python.org/downloads/) before using the build commands.
The quick start also uses [Git](https://git-scm.com/downloads) to clone the
scaffold and give your manuscript its own version history.

Run `just doctor` and it will tell you which of these you are missing, and
whether the ones you have are new enough.

- `typst` **0.14 or newer**, `just`, `uv`, `python3`
- `typstyle` for `just fmt` and `just fmt-check` (`cargo install typstyle`)
- `git` is **not** required by any check; the staleness checks are content hashes
- a network connection for `just audio-setup` (the voice model) and the first
  PDF build (the `arkheion` template)

The Typst floor is 0.14: the oldest version the pipeline is tested against,
held by a CI matrix. It was first set there because the HTML Word route, since
removed, silently lost every figure on 0.13; it stays because nothing older
has been run through the pandoc route.

`just setup` builds the Python environment from `pyproject.toml` and commits the
resolution to `uv.lock`, so every machine gets the same versions. There are two
environments on purpose: the manuscript toolchain at the root (pandoc, cairosvg,
textstat, small and stable, locked and shipped with the scaffold) and the
analysis in `analysis/pyproject.toml` (whatever the science needs, rewritten per
project). Keeping them apart means a project's churning analysis dependencies do
not invalidate the toolchain lock. The audiobook extras are a `--group audio` so a
clone that never builds audio stays light.

The first PDF build fetches the `arkheion` template from Typst Universe and
caches it.

## Things that will bite you

**Typst line continuations.** A method chain broken across lines after `#let x =`
or inside `[...]` ends at the first newline, and the continuation is read as
literal text. The error is confusing (`unknown variable: a` pointing at a closure
parameter). Wrap multi-line chains in a code block `{ ... }`. `config.typ` has a
worked example.

**Regenerated figures churning bytes.** matplotlib stamps a creation date into
PNG metadata by default, which makes every regeneration look like real drift to
`just check`. The bundled generator passes `metadata={"Software": None}`; do the
same in yours, and seed any RNG.

**The SI is not compiled on its own.** `si-body.typ` is body-only. Its title page,
S-prefixed numbering, and counter resets are applied by `paper.typ` at the include
site, so the whole manuscript is one compilation with one label namespace and
cross-references resolve in both directions.
