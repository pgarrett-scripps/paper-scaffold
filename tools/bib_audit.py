#!/usr/bin/env python3
"""Check every DOI in the bibliography against its registered metadata.

An entry with no DOI -- software, a dataset, a repository -- is identified only
by its URL, so that URL is fetched instead and what the page says about itself
(the repository's owner and description, the crate's owners) is printed beside
the bibliography's own title and authors for a person to compare.

WHY THIS IS SEPARATE FROM prose_check.py. It needs the network. A check that can
fail because an API was slow does not belong in a gate people are supposed to
trust, so this is its own recipe, run deliberately before submission rather than
on every save. `just verify` never calls it.

WHAT IT CATCHES. A DOI can resolve while the title or authors beside it are
invented, copied from another paper, or merely mistyped. A URL is cheaper still
to invent: `github.com/<plausible-owner>/<tool>` reads fine and fetches
nothing, and a real repository can be credited to the wrong maintainer. Compare the fields a
reader uses to identify the work with the metadata its publisher registered,
in addition to checking for retractions and dead DOI links. A paper can also be
retracted years after you cite it, so the answer has a shelf life and the check
is worth re-running late.

A registrar record can itself be wrong. Name the entry in prose-check.toml's
[allow].doi-metadata, as its key or as key:field to excuse one field, with
the reason as a comment beside it; the mismatch is still printed, but no
longer fails, and an allowance that stops matching anything is reported.

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
from paths import ROOT  # the manuscript (tools/paths.py)
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

# Entries without a DOI are checked by URL. Two hosts carry nearly every
# software citation and expose an API that names the owner, which a rendered
# page does not: GitHub's answers 404 for a repository that never existed and
# follows a rename, and crates.io's lists the crate's owners. crates.io in
# particular serves its HTML only to a browser-like Accept header, so a plain
# GET reports a live crate as 404 -- which is how the API route was found.
# (Found downstream, in the koth manuscript.)
GITHUB_API = "https://api.github.com/repos/"
CRATES_API = "https://crates.io/api/v1/crates/"

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


# Registered titles that name the kind of deposit rather than the work, as
# _text() leaves them. Grow it when a repository turns out to do the same.
GENERIC_DEPOSIT_TITLES = {"dataset", "proteomexchange dataset"}


@dataclass(frozen=True)
class MetadataIssue:
    """One disagreement between a BibTeX entry and its DOI record."""

    field: str
    local: str
    registered: str
    fatal: bool


# Words an ISO 4 / CASSI abbreviation drops outright: articles, prepositions,
# conjunctions. Not "a": in "U. S. A." it is an initial, not an article.
_VENUE_STOPWORDS = {"of", "the", "for", "and", "in", "on", "at", "to", "an"}


def _abbreviates(short: str, full: str) -> bool:
    """True if `short` is an ISO 4 / CASSI abbreviation of `full`.

    Both arguments are _text() output. ACS style wants "J. Proteome Res.", but
    Crossref registers the full title and only some publishers add a
    short-container-title, so a correct abbreviation was reported as the wrong
    journal on nearly every entry. Stopwords aside, the two must align ONE TO
    ONE, in order: each abbreviated word is a prefix of its full word ("Mol."
    for "Molecular") or a contraction of it ("Natl." for "National": four
    letters or more, the word's own first and last letters, the rest in
    order; shorter, "Res." would contract "Reviews"). One to one is the part
    that matters.
    Letting the full title keep unmatched words accepted "Nature" for
    "Nature Methods", which is a real miscitation, not a style difference.
    "Anal. Chem." still does not match "Analytical Biochemistry".
    """
    def words(s: str) -> list[str]:
        return [w for w in s.split() if w not in _VENUE_STOPWORDS]

    def shortens(a: str, w: str) -> bool:
        if w.startswith(a):
            return True
        it = iter(w[1:-1])
        return (len(a) >= 4 and a[0] == w[0] and a[-1] == w[-1]
                and all(c in it for c in a[1:-1]))

    s, f = words(short), words(full)
    return bool(s) and len(s) == len(f) and all(map(shortens, s, f))


def _text(value: object) -> str:
    """Plain comparison text from BibTeX, Crossref, or DataCite markup."""
    if value is None:
        return ""
    s = html.unescape(str(value))
    s = re.sub(r"<[^>]+>", " ", s)              # JATS in Crossref titles
    # A registry record whose accents were lost in a charset conversion reads
    # "Mu?ller". Dropping the "?" rejoins the word, which then matches the
    # entry's "M{\"u}ller" once the accent is stripped below.
    s = s.replace("?", "")
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
        parts = [part.strip() for part in raw.split(",")]
        if len(parts) >= 3 and _text(parts[1]) in SUFFIXES:
            family, given = parts[0], ", ".join(parts[2:])   # Last, Jr, First
        elif len(parts) >= 2:
            family, given = parts[0], ", ".join(parts[1:])
        else:
            family, given = _split_display(raw)
        people.append((_surname(family), _initial(given)))
    return people


# Generational suffixes are not part of the surname, wherever a registrar or a
# BibTeX author put them: "Yates, III, John R." (BibTeX's three-part form),
# "{Yates III}, John R." (braced), and Crossref's "given": "John R. III" all
# name the same person as "Yates, John R". Before this, the three-part form
# was read as surname "Yates", initial "I", and failed an author line that
# was correct.
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def _surname(family: object) -> str:
    # Only TRAILING suffix words go, and never the last word left: a surname
    # that is itself "V" stays "v".
    words = _text(family).split()
    while len(words) > 1 and words[-1] in SUFFIXES:
        words.pop()
    return words[-1] if words else ""


def _split_display(name: str) -> tuple[str, str]:
    """(family, given) from "John R. Yates III": the surname is the last word
    that is not a suffix, and the suffix rides with it for _surname to drop."""
    words = name.split()
    n = len(words)
    while n > 2 and _text(words[n - 1]) in SUFFIXES:
        n -= 1
    return " ".join(words[n - 1:]), " ".join(words[:n - 1])


def _initial(given: object) -> str:
    # A suffix never leads a given name ("John R. III"), and an initial can
    # spell one: "V." for Vladimir must stay "v", not vanish as a suffix.
    words = _text(given).split()
    return words[0][0] if words else ""


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
                family, given = _split_display(name)
        people.append((_surname(family), _initial(given)))
        shown.append(", ".join(x for x in (family, given) if x) or name)
    return people, " and ".join(shown)


def _years(message: dict) -> set[str]:
    out = set()
    for key in ("published-print", "published-online", "published", "issued"):
        parts = (message.get(key) or {}).get("date-parts", [])
        if parts and parts[0] and parts[0][0]:     # [[null]] occurs
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
                   *list(message.get("short-container-title") or []),
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
        # A repository that registers every deposit under one generic title
        # ("Dataset", "ProteomeXchange dataset") says nothing about the title
        # either, and the entry's descriptive title is the useful one.
        generic_deposit = " ".join(registered_title) in GENERIC_DEPOSIT_TITLES
        visibly_incomplete = generic_deposit or (
            len(registered_title) <= 3
            and local_title[:len(registered_title)] == registered_title)
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
        # Online-first and issue years routinely straddle New Year, and not
        # every record carries both. A year one apart stays visible for
        # review; a failed identity check is kept for a larger disagreement.
        adjacent = local_year.isdigit() and any(
            year.isdigit() and abs(int(local_year) - int(year)) <= 1
            for year in years)
        issue("year", local_year, " or ".join(sorted(years)), not adjacent)

    venue = entry.get("journal") or entry.get("booktitle") or ""
    venues = [v for v in record["venues"] if v]
    local_venue = _text(venue)
    registered_venues = [_text(v) for v in venues]
    venue_matches = any(
        local_venue == candidate
        or (min(len(local_venue), len(candidate)) >= 15
            and (local_venue in candidate or candidate in local_venue))
        or _abbreviates(local_venue, candidate)
        or _abbreviates(candidate, local_venue)
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

    # An article number is often written "Article 123" or "article e123" in
    # the entry and registered as the bare "123"/"e123".
    local_pages, registered_pages = entry.get("pages", ""), record["pages"]
    local_page_text = " ".join(
        t for t in _text(local_pages).split() if t != "article")
    if (local_pages and registered_pages
            and local_page_text != _text(registered_pages)):
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


def _url_target(url: str) -> tuple[str, str]:
    """Classify a URL: ('github', 'owner/name') | ('crates', name) | ('web', url).

    Pure, so the offline suite can pin the parsing; the network lives in
    _fetch_url.
    """
    parsed = urllib.parse.urlparse(url.strip())
    host = parsed.netloc.lower().removeprefix("www.")
    parts = [p for p in parsed.path.split("/") if p]
    if host == "github.com" and len(parts) >= 2:
        owner, name = parts[0], parts[1].removesuffix(".git")
        return "github", f"{owner}/{name}"
    if host == "crates.io" and len(parts) >= 2 and parts[0] == "crates":
        return "crates", parts[1]
    return "web", url.strip()


def _get_json(url: str, timeout: float) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        return json.load(fh)


def _same_place(a: str, b: str) -> bool:
    pa, pb = urllib.parse.urlparse(a), urllib.parse.urlparse(b)
    return (pa.netloc.lower().removeprefix("www.")
            == pb.netloc.lower().removeprefix("www.")
            and pa.path.rstrip("/") == pb.path.rstrip("/"))


def _fetch_url(url: str, timeout: float):
    """What a DOI-less entry's URL says about itself.

    Returns ('ok', page) | ('moved', page) | ('missing', detail) |
    ('error', detail), where page is {"name", "about", "owner"}. 'moved' is a
    repository that now lives under another name: it resolves, but the citation
    names something that was renamed or transferred, which is worth a look.
    """
    kind, target = _url_target(url)
    try:
        if kind == "github":
            data = _get_json(GITHUB_API + target, timeout)
            page = {"name": data.get("full_name") or "",
                    "about": data.get("description") or "",
                    "owner": (data.get("owner") or {}).get("login") or ""}
            moved = page["name"].lower() != target.lower()
            return ("moved" if moved else "ok"), page
        if kind == "crates":
            crate = _get_json(CRATES_API + target, timeout).get("crate") or {}
            owners = (_get_json(CRATES_API + target + "/owners", timeout)
                      .get("users") or [])
            return "ok", {"name": crate.get("name") or target,
                          "about": crate.get("description") or "",
                          "owner": ", ".join(o.get("login") or o.get("name")
                                             or "" for o in owners)}
        req = urllib.request.Request(
            url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            final = fh.geturl()
            body = fh.read(200_000).decode("utf-8", "replace")
        m = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
        page = {"name": final,
                "about": " ".join(html.unescape(m.group(1)).split()) if m else "",
                "owner": ""}
        return ("ok" if _same_place(final, url) else "moved"), page
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return "missing", f"HTTP {e.code}"
        return "error", f"HTTP {e.code}"
    except Exception as e:                      # timeout, DNS, TLS, offline
        return "error", str(e)[:60]


def _plain(value: object) -> str:
    """A BibTeX field as a person wrote it, minus the protective braces."""
    return " ".join(str(value or "").translate(str.maketrans("", "", "{}"))
                    .split())


def _allowed() -> set[str]:
    """prose-check.toml's [allow].doi-metadata: entry keys, or key:field.

    Lower-cased, as every [allow] value is. A registrar record can be wrong
    (Crossref once fused an author's name with "cor"), or lack a published
    correction the entry carries; then the bibliography is right and must not
    be edited to match. The allowance lives with every other exception, where
    its reason is written as a comment, rather than in the .bib.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from prose_rules import load_config
    return set(load_config(ROOT).allow.get("doi-metadata", set()))


def _checked_keys(entries: list[dict], errors: list, missing: list) -> set[str]:
    """Keys whose DOI record was actually compared this run."""
    skipped = {key for key, _doi, _msg in errors + missing}
    return {e["_key"] for e in entries
            if (e.get("doi") or "").strip() and e["_key"] not in skipped}


def audit(timeout: float = 15.0, *, entries: list[dict] | None = None,
          fetch=None, fetch_url=None, pause: bool = True,
          require_complete: bool = False,
          allowed: set[str] | None = None) -> int:
    """Audit the bibliography; injectable inputs keep regression tests offline."""
    entries = _entries() if entries is None else entries
    if not entries:
        return 0
    fetch = fetch or _fetch
    fetch_url = fetch_url or _fetch_url
    allowed = _allowed() if allowed is None else allowed

    withdrawn, concerns, missing, errors = [], [], [], []
    metadata_errors, metadata_warnings, metadata_allowed = [], [], []
    url_pages, url_moved, url_missing, url_errors = [], [], [], []
    used: set[str] = set()
    checked = datacite = 0

    def sort_issues(key: str, doi: str, e: dict, state: str, msg: dict):
        for item in _metadata_issues(e, state, msg):
            names = {key.lower(), f"{key}:{item.field}".lower()} & allowed
            if names:
                used.update(names)
                metadata_allowed.append((key, doi, item))
            else:
                target = metadata_errors if item.fatal else metadata_warnings
                target.append((key, doi, item))

    for e in entries:
        doi = (e.get("doi") or "").strip()
        if not doi:
            # No DOI: the URL is the entry's only identity. An entry with
            # neither is prose_check's to report, offline.
            url = (e.get("url") or "").strip()
            if url:
                state, msg = fetch_url(url, timeout)
                bucket = {"missing": url_missing, "error": url_errors,
                          "moved": url_moved}.get(state, url_pages)
                bucket.append((e, url, msg))
                if pause:
                    time.sleep(0.05)
            continue
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
            sort_issues(key, doi, e, state, msg)
        else:
            sort_issues(key, doi, e, state, msg)
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
    n_urls = len(url_pages) + len(url_moved) + len(url_missing) + len(url_errors)
    urls = (f" and {n_urls} URL-only entr{'y' if n_urls == 1 else 'ies'}"
            if n_urls else "")
    print(f"checked {checked} DOI(s) against Crossref{via}{urls}\n")
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
    if metadata_allowed:
        # Still printed: the allowance excuses the mismatch, it does not hide
        # it, and the reason sits beside the key in prose-check.toml.
        print("\nmismatch allowed by [allow].doi-metadata in prose-check.toml "
              "(the registrar is wrong; see the reason there):")
        for key, doi, item in metadata_allowed:
            print(f"  {key}  {doi}  {item.field}: "
                  f"bibliography={item.local!r}; registered={item.registered!r}")
    checked_keys = {k.lower() for k in _checked_keys(entries, errors, missing)}
    stale = sorted(a for a in allowed - used
                   if a.split(":", 1)[0] in checked_keys)
    if stale:
        # The registrar fixed its record, or the entry changed: an allowance
        # that excuses nothing would silently excuse the next real mismatch.
        print("\n[allow].doi-metadata entries that no longer excuse anything "
              "(delete them from prose-check.toml):")
        for a in stale:
            print(f"  {a}")
    if url_missing:
        rc = 1
        print("\nURL DOES NOT RESOLVE -- a typo, or a repository that never "
              "existed:")
        for e, url, msg in url_missing:
            print(f"  {e['_key']}  {url}  ({msg})")
    if url_moved:
        print("\nURL now resolves somewhere else (renamed or transferred; "
              "cite the current home):")
        for e, url, page in url_moved:
            print(f"  {e['_key']}  {url}  ->  {page['name']}")
    if url_pages:
        # Nothing registers a title or author list for a URL, so this cannot
        # be judged mechanically. Put what the page says beside what the
        # bibliography says and let a person read the two lines.
        print("\nURL-only entries resolve. What each page says about itself, "
              "under what the bibliography says:")
        for e, url, page in url_pages:
            local = _display(_plain(e.get("title")) or "<no title>", 90)
            who = _display(_plain(e.get("author")), 60)
            about = page["about"] or "<no description>"
            owner = f"  owner {page['owner']}" if page.get("owner") else ""
            print(f"  {e['_key']}  {url}")
            print(f"      bibliography: {local}  ({who})")
            print(f"      page:         {page['name']}{owner}: "
                  f"{_display(about, 90)}")
    if errors or url_errors:
        # NOT a failure. Being offline is not a bibliography defect, and treating
        # it as one is how a network check starts getting skipped. An
        # unreachable URL does not block --require-complete either: plenty of
        # sites refuse a script outright, and that is not the citation's fault.
        print("\ncould not be checked (network, not a defect):")
        for key, doi, msg in errors:
            print(f"  {key}  {doi}  {msg}")
        for e, url, msg in url_errors:
            print(f"  {e['_key']}  {url}  {msg}")

    if not (withdrawn or concerns or missing or errors or metadata_errors
            or metadata_warnings or metadata_allowed or url_missing
            or url_moved or url_errors):
        tail = " and every URL-only entry resolves" if url_pages else ""
        print("every DOI resolves, matches its bibliography entry, and none "
              f"is retracted{tail}")
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
