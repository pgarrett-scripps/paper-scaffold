# Versioning and upgrading

Which scaffold release a manuscript is on, and how to move it to a newer one. The full procedure is in [HISTORY.md](../HISTORY.md#upgrading-a-project-built-on-an-older-version).

## Versioning

The scaffold version lives in `pyproject.toml` and is copied into every project
built from it, so `just version` answers "what am I on" from inside a derived
manuscript. [HISTORY.md](../HISTORY.md) records what each release contains, what
bumps major/minor/patch, and how to pull a later version's changes into an
existing project. `just upgrade-plan` does the bookkeeping for that: it lists
the Upgrade: lines in order and says which scaffold files still match the
release the project came from (safe to replace) and which need a hand merge.

Read HISTORY.md's "Decisions reversed" section before changing something that
looks obviously improvable. Several obvious improvements were tried here and were
wrong for reasons only visible from use.
