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


# Script-owned uncertainty beside a value (5.0.0): the interval's ends, its
# coverage level as a fraction (0.95), the sample size, and the spread. Written
# by Stats.add(); covered by the v3 checksum; rendered by `#ci("id")`.
UNCERTAINTY = ("lo", "hi", "level", "n", "sd", "se")

# How a value was measured, author-owned. A timing claim on a single-run value
# is the thing `single-run-timing` warns about.
MEASUREMENTS = ("single-run", "replicated", "exclusive")

# Relations between ids in `expect` (5.0.0). The comparisons take an id or a
# list of ids; ratio_to and diff_to take {"id", "min", "max"} or a list of them.
COMPARISONS = {"gt": (lambda a, b: a > b, ">"), "ge": (lambda a, b: a >= b, ">="),
               "lt": (lambda a, b: a < b, "<"), "le": (lambda a, b: a <= b, "<=")}
RELATIONS = ("ratio_to", "diff_to")
GUARD_KEYS = {"sign", "min", "max", *COMPARISONS, *RELATIONS}


def _number(x) -> bool:
    return (isinstance(x, (int, float)) and not isinstance(x, bool)
            and not (isinstance(x, float) and not math.isfinite(x)))


def _relation_shape(expect: dict) -> list[str]:
    """Shape errors of the relation keys, without looking at other ids."""
    errors = []
    for key in COMPARISONS:
        if key in expect:
            ids = expect[key] if isinstance(expect[key], list) else [expect[key]]
            if not ids or any(not isinstance(i, str) or not i for i in ids):
                errors.append(f"expect.{key} must be an id or a list of ids")
    for key in RELATIONS:
        if key in expect:
            items = expect[key] if isinstance(expect[key], list) else [expect[key]]
            for item in items:
                if (not isinstance(item, dict) or not isinstance(item.get("id"), str)
                        or set(item) - {"id", "min", "max"}
                        or not ({"min", "max"} & set(item))
                        or any(not _number(item[b]) for b in ("min", "max") if b in item)):
                    errors.append(f"expect.{key} must be {{\"id\", \"min\", \"max\"}} "
                                  f"with at least one finite bound (or a list of them)")
                    break
                if "min" in item and "max" in item and item["min"] > item["max"]:
                    errors.append(f"expect.{key} for {item['id']}: min exceeds max")
    return errors


def relation_errors(id: str, rec: dict, values: dict, *,
                    missing_ok: bool = False) -> list[str]:
    """The relations in `rec["expect"]` checked against the other entries.

    "A is at least 3-fold B" used to need a hand-derived guard id holding the
    ratio; here it is one line in A's expect: {"ratio_to": {"id": "B", "min": 3}}.
    An id the relation names but the file lacks is an error, except while a
    generator is still writing (`missing_ok`), when another script may add it.
    """
    expect = rec.get("expect") or {}
    if not isinstance(expect, dict):
        return []
    value = rec.get("value")
    errors = []
    def other(ref):
        if ref not in values:
            if not missing_ok:
                errors.append(f"expect names {ref!r}, which stats.json does not declare")
            return None
        v = values[ref].get("value") if isinstance(values[ref], dict) else None
        if not _number(v):
            errors.append(f"expect compares with {ref!r}, whose value is not numeric")
            return None
        return v
    if not _number(value):
        return []
    for key, (test, symbol) in COMPARISONS.items():
        if key not in expect:
            continue
        for ref in expect[key] if isinstance(expect[key], list) else [expect[key]]:
            b = other(ref)
            if b is not None and not test(value, b):
                errors.append(f"value {value} is not {symbol} {ref} ({b}); "
                              f"review the claim that relates them")
    for key in RELATIONS:
        if key not in expect:
            continue
        for item in expect[key] if isinstance(expect[key], list) else [expect[key]]:
            if not isinstance(item, dict):
                continue
            b = other(item.get("id"))
            if b is None:
                continue
            if key == "ratio_to":
                if b == 0:
                    errors.append(f"ratio to {item['id']} is undefined: its value is 0")
                    continue
                got, what = value / b, "ratio to"
            else:
                got, what = value - b, "difference from"
            lo, hi = item.get("min"), item.get("max")
            if (lo is not None and got < lo) or (hi is not None and got > hi):
                errors.append(f"{what} {item['id']} is {got:.6g}, outside "
                              f"[{lo if lo is not None else '-inf'}, "
                              f"{hi if hi is not None else 'inf'}]; review the claim")
    return errors


def uncertainty_errors(rec: dict) -> list[str]:
    """Consistency of the script-owned uncertainty fields and `measurement`."""
    errors = []
    for field in ("lo", "hi", "sd", "se"):
        if field in rec and not _number(rec[field]):
            errors.append(f"{field} must be a finite number")
    if "level" in rec and not (_number(rec["level"]) and 0 < rec["level"] < 1):
        errors.append("level must be a fraction between 0 and 1 (0.95, not 95)")
    if "n" in rec and (isinstance(rec["n"], bool) or not isinstance(rec["n"], int)
                       or rec["n"] < 1):
        errors.append("n must be a positive integer")
    for field in ("sd", "se"):
        if _number(rec.get(field)) and rec[field] < 0:
            errors.append(f"{field} must not be negative")
    if ("lo" in rec) != ("hi" in rec):
        errors.append("lo and hi come together: an interval needs both ends")
    elif _number(rec.get("lo")) and _number(rec.get("hi")) and rec["lo"] > rec["hi"]:
        errors.append(f"lo {rec['lo']} exceeds hi {rec['hi']}")
    if "level" in rec and "lo" not in rec:
        errors.append("level describes an interval, but the entry has no lo/hi")
    if "measurement" in rec and rec["measurement"] not in MEASUREMENTS:
        errors.append(f"measurement must be one of {', '.join(MEASUREMENTS)}")
    return errors


def guard_errors(value, expect) -> list[str]:
    errors = []
    if not isinstance(expect, dict):
        return ["expect must be an object with sign, min, or max guards"]
    unknown = set(expect) - GUARD_KEYS
    if unknown:
        errors.append(f"expect has unknown keys: {', '.join(sorted(unknown))}")
    numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
    if numeric and isinstance(value, float) and not math.isfinite(value):
        errors.append("value must be finite; NaN and infinity cannot be stated")
    if expect and not numeric:
        errors.append("value has a guard but is not numeric")
    errors += _relation_shape(expect)
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
    for id, rec in doc["values"].items():
        if not isinstance(rec, dict):
            raise ManifestError(f"{id}: entry must be an object")
        origin = rec.get("origin")
        if origin is not None:
            if not isinstance(origin, dict):
                raise ManifestError(f"{id}: origin must be an object")
            for field in ("by", "note", "at"):
                if field in origin and not isinstance(origin[field], str):
                    raise ManifestError(f"{id}: origin.{field} must be a string")
        if kind == "stats":
            if "value" not in rec or not isinstance(rec["value"], (str, int, float, bool)):
                raise ManifestError(f"{id}: value must be a number, string, or boolean")
            for field in ("fmt", "unit", "desc", "checksum", "measurement"):
                if field in rec and not isinstance(rec[field], str):
                    raise ManifestError(f"{id}: {field} must be a string")
            for field in UNCERTAINTY:
                if field in rec and (isinstance(rec[field], bool)
                                     or not isinstance(rec[field], (int, float))):
                    raise ManifestError(f"{id}: {field} must be a number")
        else:
            for field in ("path", "kind", "hash"):
                if field in rec and not isinstance(rec[field], str):
                    raise ManifestError(f"{id}: {field} must be a string")
            inputs = rec.get("inputs", {})
            if not isinstance(inputs, dict) or any(not isinstance(h, str)
                                                  for h in inputs.values()):
                raise ManifestError(f"{id}: inputs must map paths to hash strings")
    return doc


def load(path: Path, kind: str) -> dict:
    try:
        return validate(json.loads(path.read_text(encoding="utf-8")), kind)
    except (OSError, ValueError) as exc:
        raise ManifestError(f"{path.name}: {exc}") from None
