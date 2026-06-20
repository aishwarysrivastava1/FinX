# backend/services/finpulse_utils.py
"""Rule-based sentiment, short summaries, and insight lines for FinPulse cards."""

from __future__ import annotations

import re
from html import unescape

from services.search_service import NSE_STOCKS

_POS = frozenset(
    (
        "profit",
        "beat",
        "surge",
        "rally",
        "gain",
        "growth",
        "upgrade",
        "high",
        "record",
        "jump",
        "soar",
        "bull",
        "optim",
        "outperform",
    )
)
_NEG = frozenset(
    (
        "loss",
        "fall",
        "plunge",
        "crash",
        "downgrade",
        "cut",
        "slump",
        "concern",
        "probe",
        "fine",
        "drag",
        "bear",
        "drop",
        "fraud",
        "delay",
        "ban",
        "weak",
    )
)


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    t = re.sub(r"<[^>]+>", " ", raw)
    t = unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def make_summary(headline: str, raw_body: str, max_chars: int = 280) -> str:
    """2–3 line style summary: prefer cleaned RSS body; fall back to headline."""
    body = strip_html(raw_body)
    if not body:
        return headline.strip()
    # Trim to ~2–3 lines worth of characters
    if len(body) <= max_chars:
        return body
    cut = body[: max_chars - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.strip() + "…"


def sentiment_from_text(headline: str, body: str) -> str:
    blob = f"{headline} {strip_html(body)}".lower()
    p = sum(1 for w in _POS if w in blob)
    n = sum(1 for w in _NEG if w in blob)
    if p > n:
        return "positive"
    if n > p:
        return "negative"
    return "neutral"


def rule_insights(symbols: list[str], sentiment: str) -> list[str]:
    """Short, deterministic insight strings (no ML)."""
    insights: list[str] = []
    sym = symbols[0] if symbols else ""
    label = NSE_STOCKS.get(sym, sym) if sym else ""

    if sym:
        if sentiment == "positive":
            insights.append(
                f"This may impact {sym} positively due to constructive cues in this story."
            )
        elif sentiment == "negative":
            insights.append(f"Potential risk for {sym} due to cautious or negative wording.")
        else:
            insights.append(f"Worth watching {sym} ({label}) for near-term price reaction.")
        if len(symbols) > 1:
            insights.append(f"Also referenced: {', '.join(symbols[1:4])}.")
    else:
        if sentiment == "positive":
            insights.append("Broader market tone looks constructive from this headline.")
        elif sentiment == "negative":
            insights.append("Potential headwind narrative — verify against your positions.")
        else:
            insights.append("Macro/market update — check holdings that match this theme.")

    return insights[:3]
