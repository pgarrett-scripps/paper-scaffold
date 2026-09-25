# Review actions

One row per finding a review skill raised. This file is the memory between
reviews: read it before reviewing or fixing anything, so a finding is raised
once and closed once. `just check-actions` validates it (inside `just verify`);
`just check-actions --open` lists what is still open.

Rules:

1. Columns are fixed: `id | severity | status | source | summary | fix | closed`.
   Keep one row per line; write a literal pipe inside a cell as `\|`.
2. `id` is `A-` plus four digits, never reused or renumbered. Add a row with
   `just actions-add <severity> "<source>" "<summary>" "<fix>"`: it takes a
   lock and the next free id, so two sessions never write the same one.
3. `severity` is `blocker`, `major` or `minor`. `status` is `open`, `done` or
   `wontfix`.
4. `source` is the findings file under `reviews/` and the finding's reference
   in it (`2026-09-22-claim-audit.md#row 4`). `summary` is one line. `fix` is the
   owner: a skill (`/paper:copy-edit`) or `analysis change`, `bibliography
   change`, `author decision`.
5. Review skills append; they never edit the manuscript. A finding already
   `open` or `done` here is not added again. One that was `done` but has come
   back is reopened in place: `status` back to `open`, and `closed` becomes
   `reopened <date>: <why>`.
6. Whoever fixes a row sets `status` to `done` and `closed` to the commit hash,
   or `uncommitted: <note>` until it is committed. A commit message line
   `Closes: A-0012` names the rows it fixes; `just close-actions` then writes
   its hash, and `just check-actions` fails when a recorded hash disagrees. `wontfix` needs a reason in
   `closed`. Every `done` or `wontfix` row has a `closed` value.

| id | severity | status | source | summary | fix | closed |
|---|---|---|---|---|---|---|
