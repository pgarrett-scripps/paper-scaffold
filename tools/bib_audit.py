#!/usr/bin/env python3
"""Check every DOI in the bibliography against Crossref: does it resolve, and has
the work been retracted?

WHY THIS IS SEPARATE FROM prose_check.py. It needs the network. A check that can
fail because an API was slow does not belong in a gate people are supposed to
trust, so this is its own recipe, run deliberately before submission rather than
on every save. `just verify` never calls it.

WHAT IT CATCHES. Citing a retracted paper is the expensive kind of mistake: it
survives review, it is found after publication, and it is entirely avoidable. A
paper can also be retracted years after you cite it, so the answer has a shelf
life and the check is worth re-running late.

Crossref is free, needs no key, and asks only that you identify yourself in the
User-Agent so they can contact you about a misbehaving script.

Usage:
    python3 bib_audit.py                # audit references.bib
    python3 bib_audit.py --timeout 30   # slower link
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
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


def audit(timeout: float = 15.0) -> int:
    entries = _entries()
    if not entries:
        return 0

    withdrawn, concerns, missing, errors = [], [], [], []
    checked = datacite = 0

    for e in entries:
        doi = (e.get("doi") or "").strip()
        if not doi:
            continue                            # prose_check reports these offline
        sys.path.insert(0, str(ROOT))
        import prose_check
        doi = prose_check._normalize_doi(doi)
        state, msg = _fetch(doi, timeout)
        checked += 1
        key = e["_key"]
        if state == "missing":
            missing.append((key, doi, msg))
        elif state == "error":
            errors.append((key, doi, msg))
        elif state == "datacite":
            datacite += 1                       # resolves; no retraction data
        else:
            kinds = {(u.get("type") or "").lower()
                     for u in (msg.get(UPDATED_BY) or [])}
            title = ((msg.get("title") or [""])[0] or "").strip().lower()
            if kinds & WITHDRAWN or title.startswith(TITLE_MARKERS):
                why = ", ".join(sorted(kinds & WITHDRAWN)) or "title says so"
                withdrawn.append((key, doi, why))
            elif kinds & CONCERNING:
                concerns.append((key, doi, ", ".join(sorted(kinds & CONCERNING))))
        time.sleep(0.05)                        # be a good citizen

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
    if errors:
        # NOT a failure. Being offline is not a bibliography defect, and treating
        # it as one is how a network check starts getting skipped.
        print("\ncould not be checked (network, not a defect):")
        for key, doi, msg in errors:
            print(f"  {key}  {doi}  {msg}")

    if not (withdrawn or concerns or missing or errors):
        print("every DOI resolves, none retracted")
    return rc


def main() -> int:
    timeout = 15.0
    if "--timeout" in sys.argv:
        timeout = float(sys.argv[sys.argv.index("--timeout") + 1])
    return audit(timeout)


if __name__ == "__main__":
    raise SystemExit(main())
