"""Shared validation for authored declarations and generated statistics.

No analysis imports: this module also works when analysis/ has been removed.
Legacy manifests remain readable; malformed data never becomes an empty ledger.
"""
from __future__ import annotations

import json
import math
from pathlib import Path


class ManifestError(ValueError):
    pass


def guard_errors(value, expect) -> list[str]:
    errors = []
    if not isinstance(expect, dict):
        return ["expect must be an object with sign, min, or max guards"]
    unknown = set(expect) - {"sign", "min", "max"}
    if unknown:
        errors.append(f"expect has unknown keys: {', '.join(sorted(unknown))}")
    numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
    if numeric and isinstance(value, float) and not math.isfinite(value):
        errors.append("value must be finite; NaN and infinity cannot be stated")
    if expect and not numeric:
        errors.append("value has a guard but is not numeric")
    sign = expect.get("sign")
    if "sign" in expect:
        if not isinstance(sign, str) or sign not in ("+", "-", "nonzero"):
            errors.append("expect.sign must be '+', '-', or 'nonzero'")
        elif numeric and not {"+": value > 0, "-": value < 0,
                              "nonzero": value != 0}[sign]:
            errors.append(f"value {value} violates sign '{sign}'; review the claim")
    bounds = {}
    for name in ("min", "max"):
        if name not in expect:
            continue
        bound = expect[name]
        if (isinstance(bound, bool) or not isinstance(bound, (int, float))
                or (isinstance(bound, float) and not math.isfinite(bound))):
            errors.append(f"expect.{name} must be a finite number")
        else:
            bounds[name] = bound
    if len(bounds) == 2 and bounds["min"] > bounds["max"]:
        errors.append("expect.min exceeds expect.max")
    elif numeric and (("min" in bounds and value < bounds["min"])
                      or ("max" in bounds and value > bounds["max"])):
        errors.append(f"value {value} is outside its declared range {bounds}")
    return errors


def validate(doc, kind: str) -> dict:
    """Validate shape before consumers evaluate ownership, hashes, or guards."""
    if not isinstance(doc, dict) or not isinstance(doc.get("values"), dict):
        raise ManifestError("manifest must be an object with a values object")
    def finite_tree(value, path):
        if isinstance(value, float) and not math.isfinite(value):
            raise ManifestError(f"{path}: NaN and infinity are not valid declaration data")
        if isinstance(value, dict):
            for key, child in value.items():
                finite_tree(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                finite_tree(child, f"{path}[{index}]")
    finite_tree(doc, "manifest")
    for key in ("sources", "pinned"):
        block = doc.get(key)
        if block is not None and not isinstance(block, dict):
            raise ManifestError(f"{key} must be an object")
    for owner, inputs in (doc.get("sources") or {}).items():
        if not isinstance(inputs, dict) or any(not isinstance(h, str)
                                              for h in inputs.values()):
            raise ManifestError(f"sources.{owner} must map paths to hash strings")
    pending = doc.get("pending")
    if pending is not None and (not isinstance(pending, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in pending.items())):
        raise ManifestError('pending must map an id or "prefix*" to a reason string')
    for owner, sets in (doc.get("evidence") or {}).items():
        if not _evidence_map(sets):
            raise ManifestError(f"evidence.{owner} must map set names to {{tool: version}}")
    for id, rec in doc["values"].items():
        if not isinstance(rec, dict):
            raise ManifestError(f"{id}: entry must be an object")
        if "evidence" in rec and not _evidence_map(rec["evidence"]):
            raise ManifestError(f"{id}: evidence must map set names to {{tool: version}}")
        checked = rec.get("checked_against")
        if checked is not None and (not isinstance(checked, dict) or any(
                h is not None and not isinstance(h, str) for h in checked.values())):
            raise ManifestError(f"{id}: checked_against must map paths to a hash or null")
        origin = rec.get("origin")
        if origin is not None:
            if not isinstance(origin, dict):
                raise ManifestError(f"{id}: origin must be an object")
            for field in ("by", "note", "at", "source"):
                if field in origin and not isinstance(origin[field], str):
                    raise ManifestError(f"{id}: origin.{field} must be a string")
        if kind == "stats":
            if "value" not in rec or not isinstance(rec["value"], (str, int, float, bool)):
                raise ManifestError(f"{id}: value must be a number, string, or boolean")
            for field in ("fmt", "unit", "desc", "checksum"):
                if field in rec and not isinstance(rec[field], str):
                    raise ManifestError(f"{id}: {field} must be a string")
        else:
            for field in ("path", "kind", "hash"):
                if field in rec and not isinstance(rec[field], str):
                    raise ManifestError(f"{id}: {field} must be a string")
            inputs = rec.get("inputs", {})
            if not isinstance(inputs, dict) or any(not isinstance(h, str)
                                                  for h in inputs.values()):
                raise ManifestError(f"{id}: inputs must map paths to hash strings")
    return doc


def _evidence_map(sets) -> bool:
    return isinstance(sets, dict) and all(
        isinstance(sw, dict) and all(isinstance(v, str) for v in sw.values())
        for sw in sets.values())


def pending_match(pending: dict, id: str) -> str | None:
    """The reason an id is declared pending, or None.

    A key is an exact id or a prefix ending in `*`, the one pattern syntax
    stats.typ and assets.typ can match too.
    """
    for key, reason in (pending or {}).items():
        if (key.endswith("*") and id.startswith(key[:-1])) or key == id:
            return reason
    return None


def load(path: Path, kind: str) -> dict:
    try:
        return validate(json.loads(path.read_text(encoding="utf-8")), kind)
    except (OSError, ValueError) as exc:
        raise ManifestError(f"{path.name}: {exc}") from None
