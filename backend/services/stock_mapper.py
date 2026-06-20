# backend/services/stock_mapper.py
"""Maps NSE symbols to Yahoo Finance–style tickers for display/links."""

from typing import Optional


def to_yahoo_nse(symbol: str) -> str:
    """e.g. RELIANCE → RELIANCE.NS"""
    s = (symbol or "").strip().upper()
    if not s:
        return ""
    return f"{s}.NS"


def card_symbol_fields(symbol: str, company_name: Optional[str] = None) -> dict:
    """
    Payload fragment for clients: navigate with `symbol` (NSE, matches CardPage);
    `yahoo_symbol` for external-style display.
    """
    sym = (symbol or "").strip().upper()
    return {
        "symbol": sym,
        "yahoo_symbol": to_yahoo_nse(sym) if sym else "",
        "label": company_name or sym,
    }
