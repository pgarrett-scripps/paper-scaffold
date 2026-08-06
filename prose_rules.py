#!/usr/bin/env python3
"""Findings, rules, and per-project suppression for prose_check.

Split out from prose_check.py so the reporting contract is in one place. A
finding is not a string: it carries a stable `rule` id and, where the rule is
about a particular value, a `subject`. Suppression matches on those two, which is
the only reason a project can say "TOF is fine here" without editing the checker.

Suppressions live in `prose-check.toml` beside STYLE.md. STYLE.md is the policy a
person reads; this is the machine-checkable subset plus the exceptions this
particular manuscript has earned.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:            # Python 3.10
    import tomli as tomllib            # type: ignore

CONFIG_NAME = "prose-check.toml"


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str          # "error" or "warn"
    message: str
    subject: str = ""      # the value a suppression matches on, if any
    where: str = ""        # "main", "SI", or "" for whole-manuscript checks
    context: str = ""

    def line(self) -> str:
        head = f"{self.where}: " if self.where else ""
        tail = f"  {self.context}" if self.context else ""
        return f"{head}{self.message}{tail}"


# rule id -> (severity, what `subject` holds). A rule with no subject can only be
# turned off wholesale, via `disable`.
RULES: dict[str, tuple[str, str]] = {
    "em-dash":            ("error", ""),
    "british-spelling":   ("error", "the word"),
    "doubled-word":       ("error", "the repeated word"),
    "uncited-figure":     ("error", "the label, e.g. fig:example"),
    "long-sentence":      ("warn",  ""),
    "verbose-phrase":     ("warn",  "the phrase"),
    "double-hedge":       ("warn",  "the phrase"),
    "opener-run":         ("warn",  "the opening word"),
    "word-repetition":    ("warn",  "the word"),
    "semicolon-count":    ("warn",  ""),
    "reference-order":    ("warn",  "the label cited early"),
    "unexpanded-acronym": ("warn",  "the acronym"),
    "derivable-number":   ("warn",  "the typed value"),
    "orphaned-asset":     ("warn",  "the file name"),
}

DEFAULT_LIMITS = {
    "max-sentence-words": 40,   # a hard run-on line, not the 25-word aim
    "opener-run": 3,            # N consecutive sentences opening with one word
    "repeat-in-sentence": 3,    # times a distinctive word may repeat in a sentence
}


@dataclass
class Config:
    disable: set[str] = field(default_factory=set)
    allow: dict[str, set[str]] = field(default_factory=dict)
    limits: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_LIMITS))
    path: Path | None = None

    def suppresses(self, f: Finding) -> bool:
        if f.rule in self.disable:
            return True
        return bool(f.subject) and f.subject.lower() in self.allow.get(f.rule, set())

    def limit(self, name: str) -> int:
        return self.limits.get(name, DEFAULT_LIMITS[name])


def _bad(msg: str) -> None:
    sys.exit(f"error: {CONFIG_NAME}: {msg}")


def load_config(root: Path) -> Config:
    """Read prose-check.toml, or return defaults if the project has none.

    Unknown rule names are a hard error. A typo in a suppression file silently
    suppresses nothing, and the author goes on believing a rule is off when it is
    not, so it is worth failing over.
    """
    path = root / CONFIG_NAME
    if not path.exists():
        return Config()

    with path.open("rb") as fh:
        raw = tomllib.load(fh)

    unknown_top = set(raw) - {"disable", "allow", "limits"}
    if unknown_top:
        _bad(f"unknown section(s) {sorted(unknown_top)}; "
             f"expected 'disable', 'allow' or 'limits'")

    disable = set(raw.get("disable", []))
    bad = disable - set(RULES)
    if bad:
        _bad(f"unknown rule(s) in disable: {sorted(bad)}\n"
             f"       known rules: {', '.join(sorted(RULES))}")

    allow_raw = raw.get("allow", {})
    bad = set(allow_raw) - set(RULES)
    if bad:
        _bad(f"unknown rule(s) in [allow]: {sorted(bad)}\n"
             f"       known rules: {', '.join(sorted(RULES))}")
    for rule in allow_raw:
        if not RULES[rule][1]:
            _bad(f"[allow].{rule} has no per-value form; it matches no particular "
                 f"value, so put it in `disable` instead")
    allow = {r: {str(v).lower() for v in vs} for r, vs in allow_raw.items()}

    limits = dict(DEFAULT_LIMITS)
    limits_raw = raw.get("limits", {})
    bad = set(limits_raw) - set(DEFAULT_LIMITS)
    if bad:
        _bad(f"unknown limit(s): {sorted(bad)}; "
             f"expected {', '.join(sorted(DEFAULT_LIMITS))}")
    for k, v in limits_raw.items():
        if not isinstance(v, int) or v < 1:
            _bad(f"limit {k!r} must be a positive integer, got {v!r}")
        limits[k] = v

    return Config(disable=disable, allow=allow, limits=limits, path=path)


def silencer(f: Finding) -> str:
    """How to make this finding stop appearing. Printed once per rule, because a
    suppression file nobody knows about is a suppression file nobody uses."""
    if f.subject and RULES[f.rule][1]:
        return f'add "{f.subject}" to [allow].{f.rule} in {CONFIG_NAME}'
    return f'add "{f.rule}" to disable in {CONFIG_NAME}'


def report(findings: list[Finding], cfg: Config, *, show_suppressed: bool,
           strict: bool) -> int:
    """Print the findings and return the exit code."""
    kept, hidden = [], []
    for f in findings:
        (hidden if cfg.suppresses(f) else kept).append(f)

    errors = [f for f in kept if f.severity == "error"]
    warns = [f for f in kept if f.severity == "warn"]

    seen_rules: set[str] = set()
    for f in errors + warns:
        tag = "ERROR" if f.severity == "error" else "warn "
        print(f"  {tag}  {f.rule:<18} {f.line()}")
        if f.rule not in seen_rules:
            seen_rules.add(f.rule)
            print(f"         {'':<18} silence: {silencer(f)}")

    if show_suppressed and hidden:
        print(f"\n  suppressed by {CONFIG_NAME}:")
        for f in hidden:
            print(f"    {f.rule:<18} {f.line()}")

    if not kept and not hidden:
        print("  prose check clean")
    else:
        parts = [f"{len(errors)} error(s)", f"{len(warns)} warning(s)"]
        if hidden:
            note = "" if show_suppressed else " (--show-suppressed to list)"
            parts.append(f"{len(hidden)} suppressed{note}")
        print("\n  " + ", ".join(parts))
        print(f"  rules: STYLE.md   (warnings are judgement calls, not gates)")

    return 1 if errors or (strict and warns) else 0


def list_rules() -> int:
    print("Rules, and what a suppression matches on:\n")
    for rule, (sev, subj) in sorted(RULES.items()):
        tag = "error" if sev == "error" else "warn"
        how = f'[allow].{rule} = ["..."]  ({subj})' if subj else "disable only"
        print(f"  {rule:<20} {tag:<6} {how}")
    print(f"\nLimits (in [limits]): "
          f"{', '.join(f'{k} = {v}' for k, v in DEFAULT_LIMITS.items())}")
    print(f"\nAll of it goes in {CONFIG_NAME}, beside STYLE.md.")
    return 0
