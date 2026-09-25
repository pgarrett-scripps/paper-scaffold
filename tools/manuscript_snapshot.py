"""A resolved source tree shared by publishing and revision review.

Keep Typst scopes, layout rules and references intact. Resolve only literal
project helper calls, then let Typst evaluate the captured document. Word's
lossy adaptation happens afterward and never becomes the PDF's input.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from atomic_io import write_text
from manuscript_sources import mask
from resolve_typst import _paren_end, front_matter_probe

from paths import ROOT, locate, tool  # the manuscript (tools/paths.py)
SCHEMA = 1
HELPER = re.compile(r'(?<![\w.\-])(#?)(s|n|lit|fig|tbl)\(\s*("(?:\\.|[^"\\])*")')


def code_positions(src: str) -> set[int]:
    """Track code/content delimiters so bare call-shaped prose stays prose.

    This only locates literal helper calls. It does not evaluate Typst or
    replace its parser; the captured source is still compiled by Typst.
    """
    visible = mask(src, strings=True)
    frames = [("markup", None)]
    positions = set()
    statements = {"let", "set", "show", "import", "include", "if", "else",
                  "for", "while", "context", "return"}
    for i, char in enumerate(visible):
        if i and src[i - 1] == "\\":
            continue
        mode, end = frames[-1]
        if mode == "code":
            positions.add(i)
        if char == "#" and (i == 0 or src[i - 1] != "\\"):
            name = re.match(r"[\w-]+", visible[i + 1:])
            frames.append(("code", "line" if name and name[0] in statements else "expr"))
        elif char == end:
            frames.pop()
            if frames[-1][1] == "expr" and visible[i + 1:i + 2] != ".":
                frames.pop()
        elif mode == "code" and char in "([{":
            frames.append(("markup" if char == "[" else "code", {"(": ")", "[": "]", "{": "}"}[char]))
        elif char == "\n" and end in ("line", "expr"):
            frames.pop()
        elif char.isspace() and end == "expr":
            frames.pop()
    return positions


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def literal(value) -> str:
    if value is None:
        return "none"
    if isinstance(value, (str, int, float, bool)):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    raise ValueError(f"unsupported statistic value: {type(value).__name__}")


def resolve_source(src: str, stats: dict, assets: dict, where: str) -> str:
    """Replace calls without touching comments, strings, raw text or directives."""
    visible = mask(src, strings=True)
    code = code_positions(src)
    parens = "".join(c if i in code else " " for i, c in enumerate(visible))
    edits = []
    for m in HELPER.finditer(src):
        if not visible[m.start():m.start() + 1].strip():
            continue
        if not m[1] and m.start() not in code:
            continue
        if any(start <= m.start() < stop for start, stop, _ in edits):
            continue
        end = _paren_end(parens, src.index("(", m.start(), m.end()))
        if end is None:
            raise ValueError(f"{where}: unclosed {m[2]} call")
        prefix, helper, key = m[1], m[2], json.loads(m[3])
        tail_src = src[m.end():end - 1]
        # The tail is code. The wrapper gives the locator that context while
        # recursively resolving a statistic inside an asset's named argument.
        tail = (resolve_source("#(" + tail_src + ")", stats, assets, where)[2:-1]
                if HELPER.search(tail_src) else tail_src)
        if helper in ("s", "n", "lit"):
            # lit()'s `unlike:` names ids for prose-check; it renders nothing.
            if tail.strip().strip(",").strip() and not (
                    helper == "lit" and re.match(r"\s*,\s*unlike\s*:", tail)):
                raise ValueError(f"{where}: unsupported arguments to {helper}({key!r})")
            if helper == "lit":
                value = key
            else:
                if key not in stats:
                    raise ValueError(f"{where}: unknown statistic {key!r}")
                value = stats[key]["display" if helper == "s" else "value"]
            # A string expression preserves special characters as text. Pasting
            # the display string into markup would turn '#' or '_' into code.
            replacement = prefix + "(" + literal(value) + ")"
        else:
            if key not in assets:
                raise ValueError(f"{where}: unknown asset {key!r}")
            entry = assets[key]
            wanted = "figure" if helper == "fig" else "table"
            if entry.get("kind") != wanted:
                raise ValueError(f"{where}: {key!r} is not a {wanted}")
            path = Path(entry["path"])
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"{where}: asset path must stay inside the manuscript")
            # Manifest paths are project-relative, even inside a nested include.
            target = json.dumps("/" + path.as_posix())
            if helper == "fig":
                replacement = prefix + f"image({target}{tail})"
            else:
                if tail.strip().strip(",").strip():
                    raise ValueError(f"{where}: tbl() does not accept extra arguments")
                replacement = prefix + f"(include {target})"
        edits.append((m.start(), end, replacement))
    for start, end, replacement in reversed(edits):
        src = src[:start] + replacement + src[end:]
    return src


def materialize(root: Path, destination: Path, sources: dict) -> None:
    """Copy captured inputs; preserve directories so includes retain scope."""
    destination.mkdir(parents=True, exist_ok=True)
    for name, value in sources.items():
        if value is None or Path(name).is_absolute():
            continue  # External compiler packages are fingerprinted, not vendored.
        path = locate(root, name)
        if not path.is_file():
            raise ValueError(f"snapshot input disappeared: {name}")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    rendered = root / "stats-rendered.json"
    stats = json.loads(rendered.read_text()).get("values", {}) if rendered.exists() else {}
    if rendered.exists():
        shutil.copyfile(rendered, destination / rendered.name)
    assets_path = destination / "assets.json"
    assets = json.loads(assets_path.read_text()).get("values", {}) if assets_path.exists() else {}
    for path in destination.rglob("*.typ"):
        name = path.relative_to(destination).as_posix()
        if name in ("stats.typ", "assets.typ", "wordcount.typ"):
            continue
        path.write_text(resolve_source(path.read_text(), stats, assets, name))


NUMBER_PROBE = r'''
#include "paper.typ"
#context metadata((review_numbering_schema: 1,
  elements: query(selector(figure).or(heading).or(math.equation)).map(e => {
    let kind = if e.func() == figure { "figure" } else if e.func() == heading { "heading" } else { "equation" }
    let num = if e.numbering == none { none } else {
      let c = if e.func() == figure { counter(figure.where(kind: e.kind)) } else { counter(e.func()) }
      numbering(e.numbering, ..c.at(e.location()))
    }
    (kind: kind, label: if e.has("label") { str(e.label) } else { none },
     number: num, supplement: e.at("supplement", default: none))
  })
))
'''


def content_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(content_text(v) for v in value)
    if isinstance(value, dict):
        if "text" in value:
            return value["text"]
        for key in ("children", "body"):
            if key in value:
                return content_text(value[key])
    raise ValueError(f"unsupported Typst numbering content: {value!r}")


def query_numbers(folder: Path, *, front_matter: Path | None = None) -> list[dict]:
    """Evaluate numbering, optionally capturing front matter in the same pass."""
    probe = folder / "review-query.typ"
    probe.write_text(NUMBER_PROBE + (front_matter_probe(label=False) if front_matter else ""))
    try:
        result = subprocess.run(["typst", "query", "--root", str(folder),
                                 str(probe), "metadata", "--field", "value"],
                                cwd=folder, check=True, capture_output=True, text=True)
        values = json.loads(result.stdout)
        records = [v["elements"] for v in values
                   if isinstance(v, dict) and v.get("review_numbering_schema") == 1]
        if len(records) != 1:
            raise ValueError("could not obtain manuscript numbering from Typst")
        for row in records[0]:
            row["number"] = None if row["number"] is None else content_text(row["number"])
            row["supplement"] = content_text(row["supplement"])
        if front_matter is not None:
            metadata = [v for v in values
                        if isinstance(v, dict) and v.get("front_matter_schema") == 1]
            if len(metadata) != 1:
                raise ValueError("could not obtain manuscript front matter from Typst")
            write_text(front_matter, json.dumps(metadata[0], ensure_ascii=False))
        return records[0]
    finally:
        probe.unlink(missing_ok=True)


def project_word(folder: Path, numbers: list[dict], *, front_matter: Path | None = None,
                 toc: str | None = None) -> None:
    write_text(folder / "numbering.json", json.dumps(numbers, indent=2))
    args = [sys.executable, str(tool("resolve_typst.py")),
            "--root", str(folder), "--numbers", str(folder / "numbering.json"),
            "--output", str(folder / "paper.word.typ")]
    if front_matter is not None:
        args.extend(["--front-matter", str(front_matter)])
    if toc is not None:
        args.extend(["--toc", toc])
    subprocess.run(args, check=True, cwd=folder)


def seal(folder: Path, sources: dict, dependencies: list[str]) -> dict:
    files = {p.relative_to(folder).as_posix(): sha(p)
             for p in sorted(folder.rglob("*")) if p.is_file() and p.name != "manifest.json"}
    version = subprocess.run(["typst", "--version"], capture_output=True,
                             check=True, text=True).stdout.strip()
    identity = hashlib.sha256(json.dumps({"sources": sources, "typst": version},
                                         sort_keys=True).encode()).hexdigest()
    manifest = {"schema_version": SCHEMA, "id": identity, "sources": sources,
                "dependencies": dependencies, "typst": version, "files": files}
    write_text(folder / "manifest.json", json.dumps(manifest, indent=2))
    return manifest


def validate(folder: Path) -> dict:
    manifest = json.loads((folder / "manifest.json").read_text())
    if manifest.get("schema_version") != SCHEMA:
        raise ValueError(f"{folder}: unsupported snapshot version")
    for name, expected in manifest["files"].items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("invalid snapshot path")
        if not (folder / path).is_file() or sha(folder / path) != expected:
            raise ValueError(f"snapshot was modified: {folder / path}")
    return manifest
