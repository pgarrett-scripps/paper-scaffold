# Versioning and upgrading

Which scaffold release a manuscript is on, and how to move it to a newer one. The full procedure is in [HISTORY.md](../HISTORY.md#upgrading-a-project-built-on-an-older-version).

## Versioning

From 4.0.0 the toolchain is the `paper-scaffold` package, and a paper's
`pyproject.toml` pins one release of it ([package](package.md)). `just version`
answers "what am I on": the installed release, the pin, and the release that
wrote `.paper/scaffold.lock.json`. [HISTORY.md](../HISTORY.md) records what
each release contains, what bumps major/minor/patch, and the "Upgrade:" lines a
paper acts on.

Upgrading a paper on 4.x:

```bash
uv add "paper-scaffold @ git+https://github.com/pgarrett-scripps/paper-scaffold@vX.Y.Z"
uv run paper sync     # prints the Upgrade: lines, rewrites the generated files
just paper && just verify
```

`just upgrade-notes` (alias `upgrade-plan`) reprints the Upgrade: lines
between the lock's release and the installed one. There is nothing to class
or merge: the toolchain is not in the paper. A local override
(`word/*.docx`, `journals/*.toml`) is kept; a change it needs from a newer
stock file is a hand merge of that one file.

A paper still on 3.x (a full toolchain copy) moves once with `paper migrate`
([package](package.md#migration-from-326x)).

Read HISTORY.md's "Decisions reversed" section before changing something that
looks obviously improvable. Several obvious improvements were tried here and were
wrong for reasons only visible from use.
