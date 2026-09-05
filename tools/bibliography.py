"""Read BibTeX once, with parse failures preserved as actionable errors."""
from pathlib import Path


def entries(path: Path) -> list[dict]:
    import bibtexparser
    library = bibtexparser.parse_file(str(path))
    if library.failed_blocks:
        raise ValueError(f"{path.name}: {len(library.failed_blocks)} malformed BibTeX block(s)")
    out = []
    for entry in library.entries:
        record = {f.key.lower(): (f.value or "").strip("{} ") for f in entry.fields}
        record.update(_key=entry.key, _type=entry.entry_type.lower())
        out.append(record)
    return out
