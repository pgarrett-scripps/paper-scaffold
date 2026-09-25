#!/usr/bin/env python3
"""Map each failing `expect` guard to the sentences that read its id.

A guard fails in gen_stats.py, far from the sentence whose assumption it
encodes ("fell", "roughly 80-90%"). The fix is a judgement about that
sentence, so the failure is only useful next to it. `_stats.write()` records
every failing guard of the last run in .build-state/stats-guard-failures.json;
this reads it and prints, per id, the value, the guard, and each sentence in
the manuscript (and slides) that reads the id with `#s()` or `#n()`.

    just assets --explain       # run the analysis; on a guard failure, explain
    just explain-guards         # explain the last recorded failure again
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from paths import ROOT  # the manuscript (tools/paths.py)

FAILURES = ".build-state/stats-guard-failures.json"
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z#@(\[])")


def sentence(src: str, offset: int) -> str:
    """The sentence of `src` around `offset`, whitespace collapsed."""
    start = src.rfind("\n\n", 0, offset)
    end = src.find("\n\n", offset)
    para_start = 0 if start < 0 else start + 2
    para = src[para_start:len(src) if end < 0 else end]
    at = offset - para_start
    pos = 0
    for piece in SENTENCE_END.split(para):
        pos = para.find(piece, pos)
        if pos <= at < pos + len(piece) + 1:
            return " ".join(piece.split())
        pos += len(piece)
    return " ".join(para.split())


def uses(root: Path, ids: set[str]) -> dict[str, list[tuple[str, int, str]]]:
    from manuscript_sources import CALL, matches, slide_files, source_files
    sources = dict(source_files(root))
    sources.update(slide_files(root, strict=False))
    out: dict[str, list] = {id: [] for id in ids}
    for path, src in sources.items():
        for m in matches(CALL, src):
            if m.group(1) in ("s", "n") and m.group(2) in ids:
                line = src.count("\n", 0, m.start()) + 1
                out[m.group(2)].append((path, line, sentence(src, m.start())))
    return out


def main(argv=None) -> int:
    root = ROOT
    path = root / FAILURES
    if not path.is_file():
        print("no recorded guard failure: the last `just assets` passed every guard")
        return 0
    failed = json.loads(path.read_text())
    found = uses(root, set(failed))
    for id, rec in failed.items():
        print(f"\n{id} = {rec.get('value')!r}  guard {json.dumps(rec.get('expect', {}))}")
        print(f"  {rec.get('message', '')}")
        if not found[id]:
            print("  no sentence reads this id; relax or drop the guard in stats.json")
        for where, line, text in found[id]:
            print(f"  {where}:{line}: {text}")
    print(f"\n{len(failed)} failing guard(s). Decide per sentence: the analysis "
          "changed (reword the sentence, then update `expect` in stats.json) or "
          "the analysis is wrong (fix it and re-run just assets).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
