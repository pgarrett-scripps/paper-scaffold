"""audio/extract_prose.py: what the audiobook voice is handed."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "audio"))


def run_cases() -> bool:
    """Both bugs the spectrl SI audiobook shipped with (3.24.2).

    A multi-line directive narrated as source for its continuation lines, and
    every cross-reference was deleted, so "as seen in Table S1" was spoken as
    "as seen in". Skipped, like the fixture's narration, without audio/.
    """
    try:
        import extract_prose as ep
    except ImportError:
        return True
    import resolve_typst as rt

    ok = True
    body = ("= Main <sec:main>\n#figure(image(\"a.png\"), caption: [c]) <fig:a>\n"
            + rt._SI_MARK + "\n= Setup\n== Detail <sec:detail>\n"
            "#figure(table(), caption: [t]) <tbl:roles>\n"
            "#figure(image(\"b.png\"), caption: [d]) <fig:b>\n")
    refs = rt.label_numbers(body)
    cases = [
        # (name, source, must appear, must NOT appear)
        ("wrapped import is dropped whole",
         '#import "@preview/x:0.2.0": (\n  get-bib,\n  render-bib,\n)\nProse.',
         "Prose.", "render-bib"),
        ("let with a code block is dropped whole",
         "#let f(path, ..args) = {\n  let b = g(path)\n  if b > 0 { b }\n}\nProse.",
         "Prose.", "args"),
        ("SI table spoken", "@tbl:roles compares them.", "Table S1 compares", "@"),
        ("parenthetical SI figure spoken", "dots (@fig:b).", "(Figure S1)", "@"),
        ("main-text figure stays unprefixed", "see @fig:a.", "see Figure 1.", "S1"),
        ("SI section", "as in @sec:detail.", "as in Section S1.1.", "@"),
        ("refn is the bare number", "Table #refn(<tbl:roles>) holds", "Table S1 holds",
         "refn"),
        ("supplement brackets", "@fig:b[Panel] shows", "Panel S1 shows", "["),
        ("citations are still dropped", "shown before @smith2020.", "shown before.",
         "smith"),
        ("an unknown label is dropped, not read", "see @fig:gone.", "see.", "gone"),
    ]
    for name, src, want, forbid in cases:
        got = ep.clean(src, refs)
        if (want and want not in got) or (forbid and forbid in got):
            print(f"  FAIL narration: {name}: {got!r}")
            ok = False
    return _data_file_cases(ep) and ok


def _data_file_cases(ep) -> bool:
    """uno-paper's audiobook read `#dfile("...")` aloud, call and all."""
    import typst_prose
    saved = typst_prose.DATA_FILES
    typst_prose.DATA_FILES = {"files": ["tbl.a", "tbl.b"],
                              "name": "Supplementary Data File", "short": "File"}
    try:
        got = ep.clean('Depths are in #dfile("tbl.b"), of #dfile-count().', {})
    finally:
        typst_prose.DATA_FILES = saved
    if "in Supplementary Data File 2, of 2." not in got or "dfile" in got:
        print(f"  FAIL narration: data file spoken as printed: {got!r}")
        return False
    return True
