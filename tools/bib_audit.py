#!/usr/bin/env python3
"""Check every DOI in the bibliography against its registered metadata.

WHY THIS IS SEPARATE FROM prose_check.py. It needs the network. A check that can
fail because an API was slow does not belong in a gate people are supposed to
trust, so this is its own recipe, run deliberately before submission rather than
on every save. `just verify` never calls it.

WHAT IT CATCHES. A DOI can resolve while the title or authors beside it are
invented, copied from another paper, or merely mistyped. Compare the fields a
reader uses to identify the work with the metadata its publisher registered,
in addition to checking for retractions and dead DOI links. A paper can also be
retracted years after you cite it, so the answer has a shelf life and the check
is worth re-running late.

Crossref is free, needs no key, and asks only that you identify yourself in the
User-Agent so they can contact you about a misbehaving script.

Usage:
    python3 bib_audit.py                # audit references.bib
    python3 bib_audit.py --timeout 30   # slower link
"""
from __future__ import annotations

import json
import html
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# The manuscript root, one level up: this file lives in tools/.
ROOT = Path(__file__).resolve().parent.parent
API = "https://api.crossref.org/works/"

# Crossref registers journal articles. Software and dataset DOIs -- Zenodo,
# figshare, Dryad -- are minted through DataCite, a different registrar, so a
# Crossref 404 does not mean the DOI is broken. Checked second, and only on a
# 404: any methods-heavy paper cites at least one of these, and reporting a
# correct software DOI as "does not resolve" failed preflight over a citation
# that was fine. (Found downstream, in the dnoise manuscript.)
DATACITE = "https://api.datacite.org/dois/"

# Crossref asks for a contact address so they can reach whoever is hammering
# them. config.typ has one; fall back to the project URL rather than inventing an
# address that does not exist.
UA = "paper-scaffold bib-audit (https://github.com/pgarrett-scripps/paper-scaffold)"

# Crossref relates a paper and the notices about it in BOTH directions, and the
# direction matters. `update-to` lives on the NOTICE and points at what it
# retracts; `updated-by` lives on the PAPER and points at the notices. Reading
# `update-to` here found nothing on the Wakefield MMR paper, which has been
# retracted since 2010 -- the check looked like it worked and detected nothing.
# Crossref populates this partly from Retraction Watch.
UPDATED_BY = "updated-by"
WITHDRAWN = {"retraction", "withdrawal", "removal"}
CONCERNING = {"expression_of_concern", "expression-of-concern", "correction",
              "corrigendum", "erratum"}

# A second, independent signal: several publishers prefix the title once a paper
# is withdrawn. Not reliable on its own, and not every publisher does it, but it
# catches a record whose relations are missing or not yet propagated.
TITLE_MARKERS = ("retracted:", "retracted article:", "withdrawn:")


@dataclass(frozen=True)
class MetadataIssue:
    """One disagreement between a BibTeX entry and its DOI record."""

    field: str
    local: str
    registered: str
    fatal: bool


def _text(value: object) -> str:
    """Plain comparison text from BibTeX, Crossref, or DataCite markup."""
    if value is None:
        return ""
    s = html.unescape(str(value))
    s = re.sub(r"<[^>]+>", " ", s)              # JATS in Crossref titles
    # BibTeX accents may wrap their letter (\v{c}, \"{o}) or not (\'i).
    # Keep the letter before removing the remaining TeX command names.
    s = re.sub(r"\\(?:['\"`^~=.uvHckbdtr])\s*\{?([A-Za-z])\}?",
               r"\1", s)
    s = re.sub(r"\\[A-Za-z]+\*?", "", s)       # simple TeX commands
    s = s.translate(str.maketrans("", "", "{}"))
    s = unicodedata.normalize("NFKD", s).casefold()
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", s))


def _one(value: object) -> str:
    """The first non-empty string in a scalar/list metadata field."""
    if isinstance(value, list):
        return next((str(x) for x in value if x), "")
    return str(value or "")


def _display(value: object, limit: int = 100) -> str:
    s = " ".join(str(value or "<missing>").split())
    return s if len(s) <= limit else s[:limit - 3] + "..."


def _bib_people(value: str) -> list[tuple[str, str]]:
    """Return (last surname token, first given initial) for BibTeX authors.

    Full BibTeX name grammar is large. These two stable pieces deliberately
    accept initials, omitted middle names, and particles while still catching
    the expensive errors: the wrong person, a missing author, or wrong order.
    """
    people = []
    for raw in re.split(r"\s+and\s+", value.strip(), flags=re.IGNORECASE):
        raw = raw.strip(" {}")
        if not raw:
            continue
        if "," in raw:
            family, given = (part.strip() for part in raw.split(",", 1))
        else:
            words = raw.split()
            family, given = words[-1], " ".join(words[:-1])
        family_words = _text(family).split()
        given_words = _text(given).split()
        people.append((family_words[-1] if family_words else "",
                       given_words[0][0] if given_words else ""))
    return people


def _registered_people(authors: object) -> tuple[list[tuple[str, str]], str]:
    people: list[tuple[str, str]] = []
    shown = []
    for author in authors if isinstance(authors, list) else []:
        if not isinstance(author, dict):
            continue
        family = _one(author.get("family") or author.get("familyName"))
        given = _one(author.get("given") or author.get("givenName"))
        name = _one(author.get("name"))
        if not family and name:
            if "," in name:
                family, given = (part.strip() for part in name.split(",", 1))
            else:
                words = name.split()
                family, given = words[-1], " ".join(words[:-1])
        family_words = _text(family).split()
        given_words = _text(given).split()
        people.append((family_words[-1] if family_words else "",
                       given_words[0][0] if given_words else ""))
        shown.append(", ".join(x for x in (family, given) if x) or name)
    return people, " and ".join(shown)


def _years(message: dict) -> set[str]:
    out = set()
    for key in ("published-print", "published-online", "published", "issued"):
        parts = (message.get(key) or {}).get("date-parts", [])
        if parts and parts[0]:
            out.add(str(parts[0][0]))
    return out


def _record(state: str, message: dict) -> dict:
    """Common comparison fields from a Crossref or DataCite response."""
    if state == "datacite":
        titles = message.get("titles") or []
        title = next((_one(t.get("title")) for t in titles
                      if isinstance(t, dict) and t.get("title")), "")
        container = message.get("container") or {}
        first, last = container.get("firstPage"), container.get("lastPage")
        page = "-".join(str(x) for x in (first, last) if x)
        return {
            "title": title,
            "authors": message.get("creators") or [],
            "years": ({str(message["publicationYear"])}
                      if message.get("publicationYear") else set()),
            "venues": [_one(container.get("title"))],
            "volume": _one(container.get("volume")),
            "issue": _one(container.get("issue")),
            "pages": page,
        }
    event = message.get("event") or ""
    if isinstance(event, dict):
        event = event.get("name") or ""
    return {
        "title": _one(message.get("title")),
        "authors": message.get("author") or [],
        "years": _years(message),
        "venues": [*list(message.get("container-title") or []),
                   _one(event)],
        "volume": _one(message.get("volume")),
        "issue": _one(message.get("issue")),
        "pages": _one(message.get("page") or message.get("article-number")),
    }


def _metadata_issues(entry: dict, state: str,
                     message: dict) -> list[MetadataIssue]:
    """Material metadata disagreements; no network and intentionally testable."""
    record = _record(state, message)
    out: list[MetadataIssue] = []

    def issue(field: str, local: object, registered: object,
              fatal: bool) -> None:
        out.append(MetadataIssue(field, _display(local),
                                 _display(registered), fatal))

    title = entry.get("title", "")
    local_title = _text(title).split()
    registered_title = _text(record["title"]).split()
    if registered_title and local_title != registered_title:
        # Some old deposits contain only a product or proceedings name. That
        # cannot verify the rest of the local title, but neither does it prove
        # the local title wrong. Keep it visible without failing preflight.
        visibly_incomplete = (len(registered_title) <= 3
                              and local_title[:len(registered_title)]
                              == registered_title)
        issue("title", title, record["title"], not visibly_incomplete)

    registered_people, registered_authors = _registered_people(record["authors"])
    local_authors = entry.get("author", "")
    local_people = _bib_people(local_authors)
    abbreviated = bool(local_people and local_people[-1] == ("others", ""))
    if abbreviated:
        local_people = local_people[:-1]
    authors_match = (registered_people[:len(local_people)] == local_people
                     if abbreviated else registered_people == local_people)
    if registered_people and not authors_match:
        issue("author", local_authors, registered_authors, True)

    years = record["years"]
    local_year = str(entry.get("year", ""))
    if years and local_year not in years:
        issue("year", local_year, " or ".join(sorted(years)), True)

    venue = entry.get("journal") or entry.get("booktitle") or ""
    venues = [v for v in record["venues"] if v]
    local_venue = _text(venue)
    registered_venues = [_text(v) for v in venues]
    venue_matches = any(
        local_venue == candidate
        or (min(len(local_venue), len(candidate)) >= 15
            and (local_venue in candidate or candidate in local_venue))
        for candidate in registered_venues
    )
    if venue and venues and not venue_matches:
        issue("venue", venue, " or ".join(venues), False)

    for field in ("volume", "issue"):
        local = (entry.get("issue") or entry.get("number") or ""
                 if field == "issue" else entry.get(field, ""))
        registered = record[field]
        if local and registered and _text(local) != _text(registered):
            issue(field, local, registered, False)

    local_pages, registered_pages = entry.get("pages", ""), record["pages"]
    if (local_pages and registered_pages
            and _text(local_pages) != _text(registered_pages)):
        issue("pages", local_pages, registered_pages, False)
    return out


def _entries():
    sys.path.insert(0, str(ROOT))
    import prose_check
    bibs = sorted(ROOT.glob("*.bib"))
    if not bibs:
        print("no .bib file here, nothing to audit")
        return []
    out = []
    for b in bibs:
        out += prose_check._bib_entries(b)
    return out


def _fetch(doi: str, timeout: float):
    """Metadata for a DOI: Crossref first, DataCite on a Crossref 404.

    Returns ('ok', crossref-message) | ('datacite', attributes) |
    ('missing'|'error', detail). Only Crossref records get the retraction
    checks -- DataCite has no equivalent relation -- so a DataCite hit means
    "resolves, registrar has no retraction concept to consult".
    """
    url = API + urllib.parse.quote(doi, safe="")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            return "ok", json.load(fh).get("message", {})
    except urllib.error.HTTPError as e:
        if e.code != 404:
            return "error", f"HTTP {e.code}"
    except Exception as e:                      # timeout, DNS, TLS, offline
        return "error", str(e)[:60]

    url = DATACITE + urllib.parse.quote(doi, safe="")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            attrs = (json.load(fh).get("data") or {}).get("attributes", {})
            return "datacite", attrs
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "missing", "neither Crossref nor DataCite has this DOI"
        return "error", f"HTTP {e.code} (DataCite)"
    except Exception as e:
        return "error", str(e)[:60]


def audit(timeout: float = 15.0, *, entries: list[dict] | None = None,
          fetch=None, pause: bool = True, require_complete: bool = False) -> int:
    """Audit the bibliography; injectable inputs keep regression tests offline."""
    entries = _entries() if entries is None else entries
    if not entries:
        return 0
    fetch = fetch or _fetch

    withdrawn, concerns, missing, errors = [], [], [], []
    metadata_errors, metadata_warnings = [], []
    checked = datacite = 0

    for e in entries:
        doi = (e.get("doi") or "").strip()
        if not doi:
            continue                            # prose_check reports these offline
        sys.path.insert(0, str(ROOT))
        import prose_check
        doi = prose_check._normalize_doi(doi)
        state, msg = fetch(doi, timeout)
        checked += 1
        key = e["_key"]
        if state == "missing":
            missing.append((key, doi, msg))
        elif state == "error":
            errors.append((key, doi, msg))
        elif state == "datacite":
            datacite += 1                       # resolves; no retraction data
            for item in _metadata_issues(e, state, msg):
                target = metadata_errors if item.fatal else metadata_warnings
                target.append((key, doi, item))
        else:
            for item in _metadata_issues(e, state, msg):
                target = metadata_errors if item.fatal else metadata_warnings
                target.append((key, doi, item))
            kinds = {(u.get("type") or "").lower()
                     for u in (msg.get(UPDATED_BY) or [])}
            title = ((msg.get("title") or [""])[0] or "").strip().lower()
            if kinds & WITHDRAWN or title.startswith(TITLE_MARKERS):
                why = ", ".join(sorted(kinds & WITHDRAWN)) or "title says so"
                withdrawn.append((key, doi, why))
            elif kinds & CONCERNING:
                concerns.append((key, doi, ", ".join(sorted(kinds & CONCERNING))))
        if pause:
            time.sleep(0.05)                    # be a good citizen

    via = (f" ({datacite} via DataCite: software/data DOIs, "
           f"no retraction data to consult)" if datacite else "")
    print(f"checked {checked} DOI(s) against Crossref{via}\n")
    rc = 0
    if withdrawn:
        rc = 1
        print("RETRACTED -- do not cite without saying why:")
        for key, doi, kind in withdrawn:
            print(f"  {key}  {doi}  ({kind})")
    if concerns:
        print("\nflagged by a later notice, worth reading before you cite it:")
        for key, doi, kind in concerns:
            print(f"  {key}  {doi}  ({kind})")
    if missing:
        rc = 1
        print("\nDOI does not resolve -- a typo, or a DOI that was never issued:")
        for key, doi, msg in missing:
            print(f"  {key}  {doi}")
    if metadata_errors:
        rc = 1
        print("\nBIBLIOGRAPHY DOES NOT MATCH DOI METADATA:")
        for key, doi, item in metadata_errors:
            print(f"  {key}  {doi}  {item.field}: "
                  f"bibliography={item.local!r}; registered={item.registered!r}")
    if metadata_warnings:
        print("\nmetadata differences worth checking (non-fatal):")
        for key, doi, item in metadata_warnings:
            print(f"  {key}  {doi}  {item.field}: "
                  f"bibliography={item.local!r}; registered={item.registered!r}")
    if errors:
        # NOT a failure. Being offline is not a bibliography defect, and treating
        # it as one is how a network check starts getting skipped.
        print("\ncould not be checked (network, not a defect):")
        for key, doi, msg in errors:
            print(f"  {key}  {doi}  {msg}")

    if not (withdrawn or concerns or missing or errors or metadata_errors
            or metadata_warnings):
        print("every DOI resolves, matches its bibliography entry, and none "
              "is retracted")
    return rc or (2 if errors and require_complete else 0)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    try:
        return audit(args.timeout, require_complete=args.require_complete)
    except (OSError, ValueError) as exc:
        print(f"bibliography audit failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
