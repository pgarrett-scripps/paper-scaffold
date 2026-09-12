"""Opt-in document targets and counted parts, shared by chapter tools.

Paths are project-relative. A part is prose between explicit BODY markers;
entrypoints and templates remain author-owned Typst, never generated on build.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

MANIFEST = "manuscript.toml"
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
START = re.compile(r"(?m)^// >>> BODY START[^\n]*\n")
END = re.compile(r"(?m)^// <<< BODY END[^\n]*(?:\n|$)")


def keys(data: dict, allowed: set[str], where: str):
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError(f"{where}: expected only {', '.join(sorted(allowed))}")


def local_path(root: Path, value: str, *, exists=True) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError(f"expected a project-relative path, got {value!r}")
    path = root / value
    if ".." in Path(value).parts or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"path escapes the project: {value}")
    if Path(value).parts[0] in (".git", ".build-state", ".edit-guard"):
        raise ValueError(f"reserved path: {value}")
    if exists and not path.is_file():
        raise ValueError(f"missing project file: {value}")
    return path


def body_span(src: str, name: str) -> tuple[int, int]:
    starts, ends = list(START.finditer(src)), list(END.finditer(src))
    if len(starts) != 1 or len(ends) != 1 or starts[0].end() > ends[0].start():
        raise ValueError(f"{name}: expected exactly one ordered BODY START / BODY END pair")
    return starts[0].end(), ends[0].start()


@dataclass(frozen=True)
class Part:
    id: str
    source: str
    bibliography: str | None = None
    citation_prefix: str = ""


@dataclass(frozen=True)
class Document:
    id: str
    entrypoint: str
    output: str
    parts: tuple[str, ...]


@dataclass
class Project:
    root: Path
    default: str
    parts: dict[str, Part]
    documents: dict[str, Document]

    def select(self, name: str | None) -> list[Document]:
        if name == "all":
            return list(self.documents.values())
        name = name or self.default
        if name not in self.documents:
            raise ValueError(f"unknown document {name!r}; choose {', '.join(self.documents)} or all")
        return [self.documents[name]]

    def sources(self, document: Document) -> dict[str, str]:
        from manuscript_sources import source_files
        found = source_files(self.root, entrypoints=(document.entrypoint,))
        actual = {p.id for p in self.parts.values() if p.source in found}
        if actual != set(document.parts):
            raise ValueError(f"{document.id}: declared parts do not match literal includes "
                             f"(declared {list(document.parts)}, found {sorted(actual)})")
        return found

    def prose(self, part: Part) -> str:
        """Expand literal body includes in order, never imported macro definitions."""
        from manuscript_sources import mask, matches
        include = re.compile(r'#include\s+"([^"\n]+)"')

        def expand(path: Path, stack=(), *, counted=False):
            if path in stack:
                raise ValueError(f"cyclic prose include: {path}")
            src = path.read_text()
            if counted:
                a, b = body_span(src, str(path))
                src = src[a:b]
            calls = matches(include, src)
            # A dynamic include cannot silently disappear from prose checks.
            rest = list(mask(src, strings=True))
            for m in calls:
                rest[m.start():m.end()] = " " * (m.end() - m.start())
            if re.search(r"#include\b", "".join(rest)):
                raise ValueError(f"{path}: dynamic prose includes need explicit support")
            for m in reversed(calls):
                target = (self.root / m[1].lstrip("/") if m[1].startswith("/")
                          else path.parent / m[1]).resolve()
                if not target.is_relative_to(self.root):
                    raise ValueError(f"prose include outside project: {m[1]}")
                src = src[:m.start()] + expand(target, (*stack, path)) + src[m.end():]
            return src

        return expand(self.root / part.source, counted=True)


def load_project(root: Path) -> Project:
    root = root.resolve()
    data = tomllib.loads((root / MANIFEST).read_text())
    keys(data, {"schema_version", "default_document", "parts", "documents"}, MANIFEST)
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("manuscript.toml: schema_version must be 1")
    parts, documents = {}, {}
    for collection in ("parts", "documents"):
        if not isinstance(data.get(collection), dict) or not data[collection]:
            raise ValueError(f"manuscript.toml: {collection} must be a nonempty table")
        for name in data[collection]:
            if not ID.fullmatch(name) or name == "all":
                raise ValueError(f"invalid {collection} id: {name!r}")
    for name, spec in data["parts"].items():
        keys(spec, {"source", "bibliography", "citation_prefix"}, f"part {name}")
        source = spec.get("source")
        path = local_path(root, source)
        if path.suffix != ".typ":
            raise ValueError(f"{name}: source must be a Typst file")
        body_span(path.read_text(), source)
        bib = spec.get("bibliography")
        if bib is not None:
            local_path(root, bib)
        prefix = spec.get("citation_prefix", "")
        if not isinstance(prefix, str):
            raise ValueError(f"{name}: citation_prefix must be a string")
        parts[name] = Part(name, source, bib, prefix)
    if len({p.source for p in parts.values()}) != len(parts):
        raise ValueError("each part must have a distinct source")
    for name, spec in data["documents"].items():
        keys(spec, {"entrypoint", "output", "parts"}, f"document {name}")
        entry = spec.get("entrypoint")
        if local_path(root, entry).suffix != ".typ":
            raise ValueError(f"{name}: entrypoint must be a Typst file")
        output = spec.get("output")
        if local_path(root, output, exists=False).suffix != ".pdf":
            raise ValueError(f"{name}: this release supports PDF document outputs")
        selected = spec.get("parts")
        if (not isinstance(selected, list) or not selected
                or any(not isinstance(p, str) or p not in parts for p in selected)
                or len(set(selected)) != len(selected)):
            raise ValueError(f"{name}: parts must be unique declared part IDs")
        documents[name] = Document(name, entry, output, tuple(selected))
    if len({d.output for d in documents.values()}) != len(documents):
        raise ValueError("documents must have distinct outputs")
    default = data.get("default_document")
    if not isinstance(default, str) or default not in documents:
        raise ValueError("default_document must name a declared document")
    if set(parts) != {p for d in documents.values() for p in d.parts}:
        raise ValueError("every part must belong to a document")
    return Project(root, default, parts, documents)
