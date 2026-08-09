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
from dataclasses import dataclass, field, replace
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
    "misspelling":        ("error", "the misspelled word"),
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
    "unaccounted-number": ("warn",  "the typed value"),
    "unresolved-todo":    ("warn",  "the note text"),
    "orphaned-asset":     ("warn",  "the file name"),
    "bypassed-asset":     ("error", "the file path"),
    "low-resolution-figure": ("warn", "the file name"),
    "oversized-table":    ("warn",  "the file name"),
    "duplicate-reference": ("error", "the shared DOI"),
    "uncited-reference":  ("warn",  "the entry key"),
    "missing-doi":        ("warn",  "the entry key"),
    "implausible-year":   ("warn",  "the entry key"),
}

DEFAULT_LIMITS = {
    "max-sentence-words": 40,   # a hard run-on line, not the 25-word aim
    "opener-run": 3,            # N consecutive sentences opening with one word
    "repeat-in-sentence": 3,    # times a distinctive word may repeat in a sentence
    # Effective resolution of a raster figure AS PRINTED, not as stored. 300 is
    # the usual floor for a halftone or photograph; journals often ask 600 or
    # more for line art, which most plots are.
    "min-figure-dpi": 300,
    # Width of the text block, which is what a `width: 100%` figure spans. The
    # default is this scaffold's arkheion page measured with `typst query`:
    # A4 (210 mm) less 25 mm margins. Change it if you change the page or
    # template, or every DPI here is computed against the wrong ruler.
    "figure-text-width-mm": 160,
    # Table shape. A table wider than this cramps every column; longer than this
    # breaks across pages and loses its header; a cell this long stops being a
    # value and starts being a paragraph, wrapping to several lines and pushing
    # the row heights around.
    "max-table-columns": 8,
    "max-table-rows": 40,
    "max-cell-chars": 60,
}


# Vocabularies a project may add to or subtract from. The shipped lists are a
# starting point, not a judgement about your field: "essentially" is filler in
# most prose and load-bearing in some, and a checker you cannot teach is one you
# end up disabling wholesale.
#
# Each maps a config key to what it holds. `phrases` are replacement pairs
# ("in order to" -> "to"); `words` are plain lists.
VOCABULARIES = {
    "verbose-phrase":   "phrases",   # filler -> what to write instead
    "british-spelling": "phrases",   # British -> American
    "common-words":     "words",     # too ordinary to count as a repetition
    "abbreviations":    "words",     # "et al." -- a period that does not end a sentence
}


@dataclass
class Config:
    disable: set[str] = field(default_factory=set)
    allow: dict[str, set[str]] = field(default_factory=dict)
    limits: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_LIMITS))
    severity: dict[str, str] = field(default_factory=dict)
    vocab: dict[str, dict] = field(default_factory=dict)
    path: Path | None = None

    def severity_of(self, rule: str) -> str:
        """The severity this project wants, falling back to the shipped default.

        Whether a rule should stop a build is a project's call, not this file's.
        A group that never uses an em dash may want it as a warning; one about to
        submit may want every long sentence to be an error.
        """
        return self.severity.get(rule, RULES[rule][0])

    def vocabulary(self, name: str, base):
        """`base` with this project's additions and removals applied."""
        spec = self.vocab.get(name, {})
        out = dict(base) if isinstance(base, dict) else set(base)
        add, remove = spec.get("add"), spec.get("remove", [])
        if add:
            out.update(add)
        for item in remove:
            key = item.lower()
            if isinstance(out, dict):
                out.pop(key, None)
            else:
                out.discard(key)
        return out

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

    # A malformed file is a typo in a config, not a bug in the checker, so it
    # gets the same one-line treatment as every other bad entry here. The common
    # one is a second `[severity]` or `[limits]` block appended to the end.
    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as e:
        _bad(f"is not valid TOML: {e}")

    known_top = {"disable", "allow", "limits", "severity", "vocabulary"}
    unknown_top = set(raw) - known_top
    if unknown_top:
        _bad(f"unknown section(s) {sorted(unknown_top)}; "
             f"expected one of {', '.join(sorted(known_top))}")

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

    severity = raw.get("severity", {})
    bad = set(severity) - set(RULES)
    if bad:
        _bad(f"unknown rule(s) in [severity]: {sorted(bad)}\n"
             f"       known rules: {', '.join(sorted(RULES))}")
    for rule, sev in severity.items():
        if sev not in ("error", "warn"):
            _bad(f"[severity].{rule} must be 'error' or 'warn', got {sev!r}. "
                 f"To switch a rule off entirely, put it in `disable`.")

    vocab_raw = raw.get("vocabulary", {})
    bad = set(vocab_raw) - set(VOCABULARIES)
    if bad:
        _bad(f"unknown vocabular(ies): {sorted(bad)}; "
             f"expected {', '.join(sorted(VOCABULARIES))}")
    vocab: dict[str, dict] = {}
    for name, spec in vocab_raw.items():
        unknown = set(spec) - {"add", "remove"}
        if unknown:
            _bad(f"[vocabulary.{name}] has unknown key(s) {sorted(unknown)}; "
                 f"expected 'add' or 'remove'")
        kind = VOCABULARIES[name]
        add = spec.get("add", {} if kind == "phrases" else [])
        if kind == "phrases":
            if not isinstance(add, dict):
                _bad(f"[vocabulary.{name}].add must be a table of "
                     f"\"found\" = \"write instead\" pairs, got {add!r}")
            add = {str(k).lower(): str(v) for k, v in add.items()}
        else:
            if not isinstance(add, list):
                _bad(f"[vocabulary.{name}].add must be a list, got {add!r}")
            add = {str(v).lower() for v in add}
        remove = spec.get("remove", [])
        if not isinstance(remove, list):
            _bad(f"[vocabulary.{name}].remove must be a list, got {remove!r}")
        vocab[name] = {"add": add, "remove": [str(v).lower() for v in remove]}

    return Config(disable=disable, allow=allow, limits=limits,
                  severity=severity, vocab=vocab, path=path)


def silencer(f: Finding) -> str:
    """How to make this finding stop appearing. Printed once per rule, because a
    suppression file nobody knows about is a suppression file nobody uses."""
    if f.subject and RULES[f.rule][1]:
        return f'add "{f.subject}" to [allow].{f.rule} in {CONFIG_NAME}'
    return f'add "{f.rule}" to disable in {CONFIG_NAME}'


def report(findings: list[Finding], cfg: Config, *, show_suppressed: bool,
           strict: bool) -> int:
    """Print the findings and return the exit code."""
    # Severity is applied here rather than where each Finding is built: one place
    # to get right, and no check has to know the config exists to honour it.
    # Findings are frozen, so this rebuilds rather than assigns.
    findings = [replace(f, severity=cfg.severity_of(f.rule)) for f in findings]

    kept, hidden = [], []
    for f in findings:
        (hidden if cfg.suppresses(f) else kept).append(f)

    errors = [f for f in kept if f.severity == "error"]
    warns = [f for f in kept if f.severity == "warn"]

    from rich.text import Text
    from report import SEVERITY_STYLE, console, findings

    rows = []
    seen_rules: set[str] = set()
    for f in errors + warns:
        msg = Text(f.line())
        # The silence hint rides in the same cell as the first finding of its
        # rule, dim, rather than being its own pseudo-finding line.
        if f.rule not in seen_rules:
            seen_rules.add(f.rule)
            msg.append(f"\nsilence: {silencer(f)}", style="dim")
        rows.append((f.severity, f.rule, msg))
    findings(rows)

    if show_suppressed and hidden:
        console.print(f"  suppressed by {CONFIG_NAME}:", style="dim")
        findings([("note", f.rule, f.line()) for f in hidden])

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
    # Width from the longest rule name, not a constant: a new rule that is one
    # character longer than the guess silently breaks the column.
    w = max(len(r) for r in RULES)
    print("Rules. Default severity shown; every one can be re-rated or "
          "switched off.\n")
    for rule, (sev, subj) in sorted(RULES.items()):
        how = f'[allow].{rule} = ["..."]  ({subj})' if subj else "disable only"
        print(f"  {rule:<{w}}  {sev:<5}  {how}")

    print(f"\nEverything below goes in {CONFIG_NAME}, beside STYLE.md.\n")
    print("  [severity]        re-rate any rule: <rule> = \"error\" | \"warn\"")
    print("  disable = [...]   switch a rule off entirely")
    print("  [allow]           keep a rule on, exempt named values")
    print(f"\n  [limits]          "
          f"{', '.join(f'{k} = {v}' for k, v in DEFAULT_LIMITS.items())}")
    print("\n  [vocabulary.<name>]   add = ..., remove = [...]")
    for name, kind in sorted(VOCABULARIES.items()):
        shape = ('add = { "found" = "write instead" }' if kind == "phrases"
                 else 'add = ["word", ...]')
        print(f"    {name:<18} {shape}")
    return 0
