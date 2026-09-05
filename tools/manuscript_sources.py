"""Locate literal includes/imports and helper uses without reading raw examples.

This is a source index, not a Typst evaluator. Dynamic paths and computed IDs
cannot be inferred; callers must report that limit instead of guessing.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRYPOINTS = ("paper.typ", "config.typ", "si-body.typ")
CALL = re.compile(r'(?<![\w-])#?(s|n|fig|tbl)\(\s*"([^"\n]+)"')
DEPENDENCY = re.compile(r'#(?:include|import)\s+"([^"\n]+)"')


def mask(src: str, *, strings: bool = False) -> str:
    """Blank comments/raw spans (and optionally strings), preserving offsets."""
    out = list(src)
    i = 0
    while i < len(src):
        start = i
        if src.startswith("//", i):
            end = src.find("\n", i)
            i = len(src) if end < 0 else end
        elif src.startswith("/*", i):
            depth, i = 1, i + 2
            while i < len(src) and depth:
                if src.startswith("/*", i):
                    depth += 1; i += 2
                elif src.startswith("*/", i):
                    depth -= 1; i += 2
                else:
                    i += 1
        elif src[i] == "`":
            fence = re.match(r"`+", src[i:]).group()
            end = src.find(fence, i + len(fence))
            i = len(src) if end < 0 else end + len(fence)
        elif src[i] == '"':
            i += 1
            while i < len(src):
                if src[i] == "\\":
                    i += 2
                elif src[i] == '"':
                    i += 1; break
                else:
                    i += 1
            if not strings:
                continue
        elif src[i] == "\\":
            i += 2
        else:
            i += 1
            continue
        out[start:i] = ["\n" if c == "\n" else " " for c in src[start:i]]
    return "".join(out)


def matches(pattern, src: str):
    visible = mask(src)
    code = mask(src, strings=True)
    return [m for m in pattern.finditer(visible) if code[m.start():m.start()+1].strip()]


def source_files(root: Path = ROOT) -> dict[str, str]:
    found = {}
    active = set()

    def visit(path: Path):
        path = path.resolve()
        if path in active:
            raise ValueError(f"cyclic manuscript include/import: {path}")
        try:
            name = path.relative_to(root.resolve()).as_posix()
        except ValueError:
            raise ValueError(f"manuscript source is outside the project: {path}") from None
        if name in found:
            return
        if not path.is_file():
            raise ValueError(f"missing manuscript source: {name}")
        active.add(path)
        src = path.read_text(encoding="utf-8")
        found[name] = src
        for m in matches(DEPENDENCY, src):
            target = m.group(1)
            if target.startswith("@") or not target.endswith(".typ"):
                continue
            visit(root / target.lstrip("/") if target.startswith("/")
                  else path.parent / target)
        active.remove(path)

    for name in ENTRYPOINTS:
        if (root / name).is_file():
            visit(root / name)
    return found


def usages(root: Path = ROOT) -> list[dict]:
    out = []
    for path, src in source_files(root).items():
        for m in matches(CALL, src):
            line = src.count("\n", 0, m.start()) + 1
            start = src.rfind("\n", 0, m.start()) + 1
            closing = src.find(")", m.end())
            end = src.find("\n", closing if closing >= 0 else m.end())
            context = " ".join(src[start:end if end >= 0 else len(src)].split())
            out.append({"id": m.group(2), "helper": m.group(1), "path": path,
                        "line": line, "context": context})
    return out
