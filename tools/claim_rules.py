#!/usr/bin/env python3
"""Prose rules that hold a claim's WORDING to the number it states (5.0.0).

`#s("id")` guarantees the digits; nothing guaranteed the words around them.
Each rule here is a sentence that was published wrong in a real manuscript
with every number correctly generated:

  bound-rounding     "92 s or less" for a value of 92.2 shown with fmt ".0f";
                     "below 2.1 GB" for 2.13. The bound is judged against the
                     VALUE, and only where rounding changed it, so a threshold
                     quoted exactly never fires.
  interval-wording   "the interval excludes zero" beside an interval that
                     contains it; "a lower bound of zero" for [-0.31, 0];
                     "lower bound #s(x_hi)".
  single-run-timing  "3-fold faster", "takes 92 s" on a value whose
                     `measurement` is "single-run": one clock reading is not a
                     measured speed.
  stale-vouch        `#lit("24.0", unlike: "id")` naming an id that no longer
                     exists or no longer collides with the literal.
  retired-claim      a wording claims.toml retired, anywhere a reader can
                     meet it: the paper, the SI, the abstract, the cover
                     letter, [sources] typst files, manuscript.toml parts.

All read the SOURCE with the ids still in it, sentence by sentence. Tying a
phrase to the number it governs is a heuristic, so every rule but
retired-claim ships as a warning (docs/prose-checks.md).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:            # Python 3.10
    import tomli as tomllib            # type: ignore

from manuscript_sources import mask
from prose_rules import Finding
import typst_prose

CLAIMS = "claims.toml"


def load_values(stats_path: Path) -> dict:
    if not stats_path.is_file():
        return {}
    try:
        values = json.loads(stats_path.read_text()).get("values", {})
    except (OSError, ValueError):
        return {}
    return values if isinstance(values, dict) else {}


def derivable_index(values: dict) -> dict[str, list[str]]:
    """Distinctive display strings -> the ids that render them.

    derivable-number's index: a display with a decimal point, a thousands
    separator, or four characters or more. Shared so a named vouch
    (`#lit(..., unlike:)`) is judged against exactly what that rule matches.
    """
    wanted: dict[str, list[str]] = {}
    for id, rec in values.items():
        try:
            d = typst_prose.display_of(rec).strip()
        except (TypeError, ValueError, AttributeError):
            continue
        if not re.fullmatch(r"[+-]?[\d,]*\.?\d+", d):
            continue
        bare = d.lstrip("+-")
        if not ("." in bare or "," in bare or len(bare) >= 4):
            continue
        wanted.setdefault(bare, []).append(id)
    return wanted


def drop_named_vouches(src: str, wanted: dict[str, list[str]]) -> str:
    """Blank each `#lit(v, unlike: ...)` whose collisions are all named.

    The rest stay, so derivable-number still reads them: a plain lit() never
    silences it, and a named one only for the ids it names.
    """
    def sub(m: re.Match) -> str:
        named = set(typst_prose.lit_unlike(m.group(2)))
        hits = wanted.get(m.group(1).strip().lstrip("+-"), [])
        return " " if named and hits and set(hits) <= named else m.group(0)
    return re.sub(typst_prose.LIT, sub, src)


def vouch_counts(sources: dict[str, str]) -> tuple[int, int]:
    """(plain lit() calls, lit() calls naming the stats they are not)."""
    plain = named = 0
    for src in sources.values():
        for m in re.finditer(typst_prose.LIT, src):
            if m.group(2):
                named += 1
            else:
                plain += 1
    return plain, named


def _sentences(src: str) -> list[str]:
    """Sentences of masked source, ids intact. Crude on purpose: a sentence
    boundary is . ! or ? followed by space and something that starts one."""
    flat = re.sub(r"\s+", " ", mask(src))
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z#_*(\[])", flat) if s.strip()]


def _parse(display: str) -> float | None:
    d = display.strip().replace(",", "").replace("−", "-")
    try:
        return float(d.rstrip("%"))
    except ValueError:
        return None


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


S_CALL = r'#s\(\s*"([^"]+)"\s*,?\s*\)'
UPPER = ("below", "under", "less than", "fewer than", "lower than", "smaller than",
         "at most", "no more than", "not more than", "no greater than", "up to",
         "not exceeding", "no higher than", "≤", "$<$", "$<=$", "$lt.eq$",
         "$lt$")
LOWER = ("above", "over", "more than", "greater than", "higher than",
         "larger than", "at least", "exceeding", "exceeds", "exceeded",
         "no less than", "not less than", "no fewer than", "≥", "$>$",
         "$>=$", "$gt.eq$", "$gt$")
TAIL_UPPER = ("less", "fewer", "lower", "smaller", "below", "under")
TAIL_LOWER = ("more", "greater", "higher", "larger", "above", "over")


def _alt(words) -> str:
    return "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in words)


BEFORE = re.compile(
    rf"(?:(?<![\w$])({_alt(UPPER)})|(?<![\w$])({_alt(LOWER)}))\s*~?\s*{S_CALL}"
    # "ranges over 9 to 12" is a span, not a bound.
    r"(?!\s*\S{0,3}\s*(?:to|and|through|\u2013|-)\s)",
    re.I)
# "No error exceeded 0.028" states an upper bound with a lower-bound verb.
NEGATED = re.compile(r"\b(?:no|not|never|none|nothing|neither|nor)\b[^.;]{0,40}$", re.I)
AFTER = re.compile(
    rf"{S_CALL}\s*(?:[^\s.,;:()]{{1,8}}\s+)?or\s+(?:({_alt(TAIL_UPPER)})|({_alt(TAIL_LOWER)}))\b",
    re.I)


def check_bound_rounding(sources: dict[str, str], values: dict) -> list[Finding]:
    """A bound whose rounded number no longer bounds the value."""
    out: list[Finding] = []
    for name, src in sources.items():
        text = re.sub(r"\s+", " ", mask(src))
        found = [(m.group(3), bool(m.group(1)) != bool(NEGATED.search(text[max(0, m.start() - 60):m.start()])),
                  m.group(1) or m.group(2), m.start())
                 for m in BEFORE.finditer(text)]
        found += [(m.group(1), bool(m.group(2)), "or " + (m.group(2) or m.group(3)),
                   m.start()) for m in AFTER.finditer(text)]
        for id, upper, phrase, at in found:
            rec = values.get(id)
            if not isinstance(rec, dict) or not _number(rec.get("value")):
                continue
            try:
                display = typst_prose.display_of(rec)
            except (TypeError, ValueError):
                continue
            shown = _parse(display)
            if shown is None:
                continue
            if str(rec.get("fmt", "")).endswith("%"):
                shown /= 100
            value = rec["value"]
            if shown == value:
                continue          # quoted exactly: nothing rounding could break
            if (upper and value > shown) or (not upper and value < shown):
                side = "above" if upper else "below"
                out.append(Finding(
                    "bound-rounding", "warn",
                    f"'{phrase.strip()} {display}' but {id} is {value}, {side} "
                    f"the bound the rounded number states. Round the other way "
                    f"(a fmt edit in stats.json), drop the bound, or say "
                    f"'about'", subject=id, where=name,
                    context=f"...{text[max(0, at - 30):at + 70]}..."))
    return out


def _intervals_in(sentence: str, values: dict, intervals: dict) -> list[tuple[str, float, float]]:
    """(label, lo, hi) for each interval the sentence states."""
    out = []
    for m in re.finditer(typst_prose.CI, sentence):
        rec = intervals.get(m.group(1))
        if rec:
            lo, hi = _parse(rec["lo"]), _parse(rec["hi"])
            own = values.get(m.group(1), {})
            if _number(own.get("lo")) and _number(own.get("hi")):
                lo, hi = own["lo"], own["hi"]
            if lo is not None and hi is not None:
                out.append((m.group(1), lo, hi))
    ids = re.findall(S_CALL, sentence)
    for id in ids:
        rec = values.get(id, {})
        if _number(rec.get("lo")) and _number(rec.get("hi")):
            out.append((id, rec["lo"], rec["hi"]))
        for sep in (".", "_"):
            if id.endswith(sep + "lo") and id[:-3] + sep + "hi" in ids:
                lo, hi = values.get(id, {}).get("value"), values.get(id[:-3] + sep + "hi", {}).get("value")
                if _number(lo) and _number(hi):
                    out.append((id[:-3], lo, hi))
    return out


EXCLUDES = re.compile(r"\b(?:exclud(?:es|ed|ing)|(?:does|did|do)\s+not\s+(?:include|contain|cross|span|overlap)|(?:lies|lie|lay|sits?)\s+(?:entirely\s+)?(?:above|below))\s+(?:zero|0)\b", re.I)
INCLUDES = re.compile(r"\b(?:includ(?:es|ed|ing)|contain(?:s|ed|ing)?|cross(?:es|ed|ing)?|span(?:s|ned|ning)?|overlap(?:s|ped|ping)?|straddl(?:es|ed|ing))\s+(?:zero|0)\b", re.I)
BOUND_ZERO = re.compile(r"\b(lower|upper)\s+(?:bound|limit|end(?:point)?)\s+(?:of|at|is|was|equal\s+to|equals)\s+(?:zero|0)\b|\b(?:zero|0)\s+as\s+(?:its|the|their)\s+(lower|upper)\s+(?:bound|limit|end(?:point)?)\b", re.I)
BOUND_ID = re.compile(rf"\b(lower|upper)\s+(?:bound|limit|end(?:point)?)\s+(?:of\s+|at\s+|is\s+|was\s+)?{S_CALL}", re.I)


def check_interval_wording(sources: dict[str, str], values: dict) -> list[Finding]:
    """Words about an interval that its own ends contradict."""
    intervals = typst_prose.intervals_of(values) if values else {}
    out: list[Finding] = []
    for name, src in sources.items():
        for sentence in _sentences(src):
            def flag(msg: str) -> None:
                out.append(Finding("interval-wording", "warn", msg,
                                   where=name, context=f"...{sentence[:140]}..."))
            for m in BOUND_ID.finditer(sentence):
                side, id = m.group(1).lower(), m.group(2)
                end = id[-2:] if re.search(r"[._](lo|hi)$", id) else ""
                if (side, end) in (("lower", "hi"), ("upper", "lo")):
                    flag(f"'{side} bound' reads {id}, the interval's "
                         f"{'upper' if end == 'hi' else 'lower'} end")
            spans = _intervals_in(sentence, values, intervals)
            if not spans:
                continue
            excl, incl = EXCLUDES.search(sentence), INCLUDES.search(sentence)
            if excl and not incl:
                for label, lo, hi in spans:
                    if lo <= 0 <= hi:
                        flag(f"says the interval excludes zero, but {label} is "
                             f"[{lo}, {hi}]")
            elif incl and not excl:
                for label, lo, hi in spans:
                    if not lo <= 0 <= hi:
                        flag(f"says the interval includes zero, but {label} is "
                             f"[{lo}, {hi}]")
            for m in BOUND_ZERO.finditer(sentence):
                side = (m.group(1) or m.group(2)).lower()
                for label, lo, hi in spans:
                    end = lo if side == "lower" else hi
                    other = hi if side == "lower" else lo
                    if end != 0 and other == 0:
                        flag(f"calls zero the {side} bound, but {label} is "
                             f"[{lo}, {hi}]: zero is its "
                             f"{'upper' if side == 'lower' else 'lower'} bound")
    return out


TIMING = re.compile(
    r"\b(?:\d+(?:\.\d+)?\s*-?\s*(?:fold|x|×)\s+(?:faster|slower|quicker)|faster|slower|"
    r"speed-?ups?|run\s*-?times?|wall\s*-?clock|elapsed|took|takes|taking|"
    r"completed?\s+in|finish(?:es|ed)?\s+in|per\s+(?:second|minute|hour)|throughput)\b",
    re.I)
TIME_UNIT = re.compile(rf"{S_CALL}\s*(?:ms|s|sec|seconds?|min|minutes?|h|hours?|-fold|×)\b", re.I)


def check_single_run_timing(sources: dict[str, str], values: dict) -> list[Finding]:
    """A timing claim resting on a value measured once."""
    single = {id for id, rec in values.items()
              if isinstance(rec, dict) and rec.get("measurement") == "single-run"}
    if not single:
        return []
    out: list[Finding] = []
    for name, src in sources.items():
        for sentence in _sentences(src):
            ids = [id for id in re.findall(S_CALL, sentence) if id in single]
            if not ids:
                continue
            unit_hits = {m.group(1) for m in TIME_UNIT.finditer(sentence)}
            if not TIMING.search(sentence) and not (unit_hits & set(ids)):
                continue
            for id in dict.fromkeys(ids):
                out.append(Finding(
                    "single-run-timing", "warn",
                    f"a timing claim reads {id}, which stats.json marks "
                    f"measurement = \"single-run\". Replicate it (and mark it "
                    f"replicated or exclusive), or say it is one run",
                    subject=id, where=name, context=f"...{sentence[:140]}..."))
    return out


def check_stale_vouches(sources: dict[str, str], values: dict) -> list[Finding]:
    """`#lit(v, unlike: ...)` naming an id that is gone or no longer collides."""
    wanted = derivable_index(values)
    out: list[Finding] = []
    for name, src in sources.items():
        for m in re.finditer(typst_prose.LIT, mask(src)):
            hits = set(wanted.get(m.group(1).strip().lstrip("+-"), []))
            for id in typst_prose.lit_unlike(m.group(2)):
                if id not in values:
                    why = "stats.json does not declare it"
                elif id not in hits:
                    why = f"{id} no longer renders as {m.group(1)!r}"
                else:
                    continue
                out.append(Finding(
                    "stale-vouch", "warn",
                    f'#lit("{m.group(1)}", unlike: "{id}"): {why}. Drop the '
                    f"name, or name the stat it now collides with",
                    subject=id, where=name))
    return out


def claim_findings(sources: dict[str, str], stats_path: Path) -> list[Finding]:
    """Every wording-vs-number rule over the sources, against stats.json."""
    values = load_values(stats_path)
    if not values:
        return []
    return (check_bound_rounding(sources, values)
            + check_interval_wording(sources, values)
            + check_single_run_timing(sources, values)
            + check_stale_vouches(sources, values))


# --- the claim registry ----------------------------------------------------

def load_claims(root: Path) -> tuple[list[dict], list[Finding]]:
    """claims.toml: [[claim]] id, phrase (the current wording), retired, note."""
    path = root / CLAIMS
    if not path.is_file():
        return [], []
    def bad(msg: str) -> tuple[list[dict], list[Finding]]:
        return [], [Finding("project-config", "error", f"{CLAIMS}: {msg}", where=CLAIMS)]
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return bad(f"not valid TOML: {exc}")
    if set(raw) - {"claim"} or not isinstance(raw.get("claim", []), list):
        return bad("expected only [[claim]] tables")
    claims, seen = [], set()
    for i, c in enumerate(raw.get("claim", [])):
        if not isinstance(c, dict) or set(c) - {"id", "phrase", "retired", "note"}:
            return bad(f"claim[{i}] may hold only id, phrase, retired and note")
        if not isinstance(c.get("id"), str) or not c["id"] or c["id"] in seen:
            return bad(f"claim[{i}] needs a unique id")
        retired = c.get("retired", [])
        if (not isinstance(retired, list) or not retired
                or any(not isinstance(r, str) or not r.strip() for r in retired)):
            return bad(f"claim {c['id']!r}: retired must list the wordings to keep out")
        for field in ("phrase", "note"):
            if field in c and not isinstance(c[field], str):
                return bad(f"claim {c['id']!r}: {field} must be a string")
        seen.add(c["id"])
        claims.append(c)
    return claims, []


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def claim_texts(root: Path) -> dict[str, str]:
    """Every hand-written file a reader can meet a claim in."""
    names = ["paper.typ", "config.typ", "si-body.typ", "cover-letter.typ"]
    try:
        from project_hooks import typst_sources
        names += typst_sources(root)
    except (OSError, ValueError):
        pass
    if (root / "manuscript.toml").is_file():
        try:
            from document_project import load_project
            project = load_project(root)
            names += [part.source for part in project.parts.values()]
        except (OSError, ValueError, SystemExit):
            pass
    out = {}
    for name in dict.fromkeys(names):
        p = root / name
        if p.is_file():
            out[name] = p.read_text(encoding="utf-8")
    return out


def check_retired_claims(root: Path, texts: dict[str, str] | None = None) -> list[Finding]:
    """A retired wording anywhere a reader can meet it. An error: the registry
    exists because the wording was wrong, and it survived review once."""
    claims, out = load_claims(root)
    if not claims:
        return out
    texts = claim_texts(root) if texts is None else texts
    for name, src in texts.items():
        # Comments are notes, not claims; markup is flattened so a line break
        # or an emphasis inside the phrase does not hide it.
        flat = _norm(re.sub(r"[*_]", "", mask(src)))
        for c in claims:
            for variant in c["retired"]:
                at = flat.find(_norm(variant))
                if at >= 0:
                    note = f" ({c['note']})" if c.get("note") else ""
                    now = f"; the current wording is {c['phrase']!r}" if c.get("phrase") else ""
                    out.append(Finding(
                        "retired-claim", "error",
                        f"claim {c['id']!r}{note}: {variant!r} was retired{now}",
                        subject=c["id"], where=name,
                        context=f"...{flat[max(0, at - 30):at + len(variant) + 30]}..."))
    return out


# --- the cover letter ------------------------------------------------------

COVER = "cover-letter.typ"


def cover_letter_prose(src: str) -> str:
    """The letter's prose: after its last top-level directive line (the
    `#let`/`#set` preamble), with the letterhead's variable references
    (`#corresponding.name`, `#v(1em)`, `#paper-title`) dropped. They are
    template, not sentences; the number helpers stay for the number rules."""
    lines = src.splitlines()
    last = 0
    for i, line in enumerate(lines):
        if re.match(r"#(?:let|set|show|import|include)\b", line):
            last = i + 1
    body = "\n".join(lines[last:])
    return re.sub(r"#(?!(?:s|n|ci|lit|todo|link|footnote|refn?)\()"
                  r"[A-Za-z][\w.-]*(?:\([^()]*\))?(?:\s*\\(?=\s))?", " ", body)
