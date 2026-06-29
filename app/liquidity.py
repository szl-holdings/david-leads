# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads V8.2 · P1-A SEC EDGAR Form 4 liquidity monitor
"""
liquidity.py — SEC EDGAR Form 4 insider-transaction liquidity-event monitor.

Given an employer name, resolve its CIK (SEC company_tickers.json), pull the company's
recent Form 4 insider-transaction filings (data.sec.gov submissions), and detect recent
insider SELL activity — a public, daily-updated proxy that option/RSU liquidity is moving
through that employer's workforce (Aidentified / Windfall surface this as a wealth trigger).

Doctrine: public-data only (SEC EDGAR is fully public); UA header required by SEC; 12s
timeout with graceful, clearly-labelled [SAMPLE] fallback — never fabricate a LIVE result.
"""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

UA = "SZL-David-Leads research@szlholdings.com"
TIMEOUT = 12
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
_RECENT_DAYS = 120          # how far back a Form 4 is still "recent" liquidity context
_MAX_PARSE = 4              # cap Form 4 docs we fetch to classify buy vs sell (budget-safe)

_TICKER_CACHE: dict[str, Any] = {"map": None}


def _get(url: str, timeout: int = TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if r.headers.get("Content-Encoding") == "gzip":
        import gzip
        data = gzip.decompress(data)
    return data


def _resolve_cik(employer: str) -> dict[str, Any] | None:
    """Resolve an employer name to a zero-padded 10-digit CIK via SEC company_tickers.json."""
    if _TICKER_CACHE["map"] is None:
        raw = _get(_TICKERS_URL)
        _TICKER_CACHE["map"] = json.loads(raw)
    table = _TICKER_CACHE["map"] or {}
    needle = employer.lower().strip()
    best = None
    for row in table.values():
        title = str(row.get("title", "")).lower()
        if needle and (needle in title or title in needle):
            # prefer the shortest title match (closest to the bare company name)
            if best is None or len(title) < len(best["title"].lower()):
                best = {"cik": int(row["cik_str"]), "title": row.get("title", ""),
                        "ticker": row.get("ticker", "")}
    if best:
        best["cik10"] = str(best["cik"]).zfill(10)
    return best


def _classify_sells(cik: int, accessions: list[str], primary_docs: list[str]) -> int:
    """Fetch up to _MAX_PARSE recent Form 4 primary docs and count those reporting a
    disposition/sale (transactionCode 'S' or acquiredDisposedCode 'D'). Best-effort."""
    sells = 0
    for acc, doc in list(zip(accessions, primary_docs))[:_MAX_PARSE]:
        try:
            acc_nodash = acc.replace("-", "")
            url = "https://www.sec.gov/Archives/edgar/data/%d/%s/%s" % (cik, acc_nodash, doc)
            body = _get(url, timeout=6).decode("utf-8", "ignore")
            if re.search(r"<transactionCode>\s*S\s*</transactionCode>", body) or \
               re.search(r"<transactionAcquiredDisposedCode>\s*<value>\s*D", body) or \
               re.search(r"<value>\s*D\s*</value>", body):
                sells += 1
        except Exception:
            continue
    return sells


def liquidity_signal(employer: str) -> dict[str, Any]:
    """Detect recent insider SELL activity at `employer` via SEC EDGAR Form 4.

    Returns {found, recent_sells, recent_form4, latest_date, employer, cik, ticker,
             citation_url, public:True, mode:"LIVE"|"SAMPLE", note}. Honest [SAMPLE]
    fallback (no fabricated counts) whenever SEC is unreachable or the employer is unknown."""
    employer = (employer or "").strip()
    if not employer:
        return _sample(employer, "no employer supplied")
    try:
        company = _resolve_cik(employer)
        if not company:
            return _sample(employer, "employer not found in SEC company index")
        cik10 = company["cik10"]
        sub = json.loads(_get(_SUBMISSIONS_URL.format(cik10=cik10)))
        recent = (sub.get("filings", {}) or {}).get("recent", {}) or {}
        forms = recent.get("form", []) or []
        dates = recent.get("filingDate", []) or []
        accns = recent.get("accessionNumber", []) or []
        docs = recent.get("primaryDocument", []) or []
        cutoff = (datetime.now(timezone.utc) - timedelta(days=_RECENT_DAYS)).date().isoformat()
        f4_idx = [i for i, f in enumerate(forms) if f == "4" and i < len(dates) and dates[i] >= cutoff]
        recent_form4 = len(f4_idx)
        latest_date = max((dates[i] for i in f4_idx), default=None)
        sell_accns = [accns[i] for i in f4_idx if i < len(accns)]
        sell_docs = [docs[i] for i in f4_idx if i < len(docs)]
        recent_sells = _classify_sells(company["cik"], sell_accns, sell_docs) if recent_form4 else 0
        citation_url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=%s&type=4" % cik10
        return {
            "found": recent_sells > 0,
            "recent_sells": recent_sells,
            "recent_form4": recent_form4,
            "latest_date": latest_date,
            "employer": company["title"],
            "cik": company["cik"],
            "ticker": company.get("ticker", ""),
            "citation_url": citation_url,
            "public": True,
            "mode": "LIVE",
            "note": ("Insider SELL activity detected in last %dd (option/RSU liquidity proxy)." % _RECENT_DAYS)
                    if recent_sells > 0 else
                    ("%d recent Form 4 filing(s); no sale-coded transaction parsed in the sampled subset." % recent_form4),
        }
    except Exception as e:
        return _sample(employer, "SEC unreachable (%s)" % type(e).__name__)


def _sample(employer: str, why: str) -> dict[str, Any]:
    """Honest [SAMPLE] fallback — no fabricated LIVE counts."""
    return {
        "found": False,
        "recent_sells": None,
        "recent_form4": None,
        "latest_date": None,
        "employer": employer,
        "cik": None,
        "ticker": "",
        "citation_url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=4",
        "public": True,
        "mode": "SAMPLE",
        "note": "[SAMPLE] " + why + " — SEC EDGAR Form 4 is public; retry when reachable.",
    }
