# backend/services/keyword_extractor.py
"""Lightweight keyword + NSE symbol extraction from headlines and summaries."""

from __future__ import annotations

import re
from typing import Iterable

from services.search_service import NSE_STOCKS

# Strict gate: at least one must appear to treat item as finance/market relevant (per product spec).
FINANCE_GATE_KEYWORDS = frozenset(
    (
        "stock",
        "market",
        "shares",
        "ipo",
        "nse",
        "bse",
        "earnings",
        "revenue",
        "profit",
        "loss",
    )
)

# Extra terms surfaced as “keywords” on cards (not all are used for gating).
FINANCE_EXTRA_KEYWORDS = frozenset(
    (
        "sensex",
        "nifty",
        "rbi",
        "economy",
        "gdp",
        "inflation",
        "dividend",
        "quarter",
        "guidance",
        "deal",
        "merger",
        "acquisition",
        "fund",
        "investor",
        "trading",
        "index",
        "fii",
        "dii",
    )
)

_ALL_EXTRACT = FINANCE_GATE_KEYWORDS | FINANCE_EXTRA_KEYWORDS

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9&.-]*")


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def passes_finance_gate(headline: str, body: str) -> bool:
    """True if copy matches gate keywords or mentions a known NSE listing."""
    if find_nse_symbols(headline, body):
        return True
    blob = _normalize_for_match(f"{headline} {body}")
    return any(k in blob for k in FINANCE_GATE_KEYWORDS)


def find_nse_symbols(headline: str, body: str) -> list[str]:
    """Detect NSE ticker tokens and well-known company names from project master list."""
    text_u = f"{headline} {body}".upper()
    blob_l = _normalize_for_match(f"{headline} {body}")
    found: list[str] = []
    seen: set[str] = set()

    def _add(sym: str):
        sym = sym.upper().strip()
        if sym in NSE_STOCKS and sym not in seen:
            seen.add(sym)
            found.append(sym)

    for m in _TOKEN_RE.finditer(text_u):
        tok = m.group(0).strip().upper().replace(".", "")
        # normalize BAJAJ-AUTO style
        if tok in NSE_STOCKS:
            _add(tok)

    for sym, name in NSE_STOCKS.items():
        nl = name.lower()
        if len(nl) < 6:
            continue
        if nl in blob_l:
            _add(sym)
            continue
        for suf in (" limited", " ltd"):
            if nl.endswith(suf):
                short = nl[: -len(suf)].strip()
                if len(short) >= 6 and short in blob_l:
                    _add(sym)
                break

    return found


def extract_keywords(headline: str, body: str, symbols: Iterable[str], limit: int = 10) -> list[str]:
    """Surface finance keywords + labels for symbols mentioned."""
    blob = _normalize_for_match(f"{headline} {body}")
    out: list[str] = []
    seen: set[str] = set()

    def push(term: str):
        t = term.strip()
        if not t or t.lower() in seen:
            return
        seen.add(t.lower())
        out.append(t)

    for s in symbols:
        if s.upper() in NSE_STOCKS:
            push(s.upper())
            short = NSE_STOCKS[s.upper()].replace(" Ltd", "").strip()
            if short:
                push(short)

    acronym = {"ipo": "IPO", "nse": "NSE", "bse": "BSE", "gdp": "GDP", "rbi": "RBI", "fii": "FII", "dii": "DII"}
    for k in sorted(_ALL_EXTRACT, key=len, reverse=True):
        if k in blob:
            push(acronym.get(k, k))

    return out[:limit]
