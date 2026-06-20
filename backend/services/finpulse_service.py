# backend/services/finpulse_service.py
"""Fetches market RSS, filters finance-related items, builds FinPulse card payloads. TTL cache."""

from __future__ import annotations

import time

import feedparser

from services.finpulse_utils import make_summary, rule_insights, sentiment_from_text, strip_html
from services.keyword_extractor import extract_keywords, find_nse_symbols, passes_finance_gate
from services.news_fetcher import ET_RSS_FEEDS
from services.search_service import NSE_STOCKS
from services.stock_mapper import card_symbol_fields

_CACHE: dict = {}
_CACHE_TTL_SEC = 300  # 5 minutes — keeps UI fast, avoids hammering RSS


def _parse_feed_entries() -> list[dict]:
    """Pull ET market feeds with title, link, date, and summary/description."""
    rows: list[dict] = []
    seen_urls: set[str] = set()
    for url in ET_RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:20]:
                link = entry.get("link", "") or ""
                title = (entry.get("title") or "").strip()
                if not title or not link or link in seen_urls:
                    continue
                seen_urls.add(link)
                raw_summary = entry.get("summary") or entry.get("description") or ""
                if not raw_summary:
                    content = entry.get("content")
                    if isinstance(content, list) and content:
                        raw_summary = content[0].get("value", "") or ""
                rows.append(
                    {
                        "headline": title,
                        "source": "ET Markets",
                        "url": link,
                        "published_at": entry.get("published", "") or entry.get("updated", ""),
                        "raw_summary": raw_summary or "",
                    }
                )
        except Exception as e:
            print(f"[FinPulse] RSS error {url}: {e}")
    return rows


def build_finpulse_payload(force_refresh: bool = False) -> dict:
    """Returns { items: [...], cached_at: iso }"""
    now = time.time()
    if (
        not force_refresh
        and _CACHE.get("data")
        and (now - float(_CACHE.get("ts", 0))) < _CACHE_TTL_SEC
    ):
        return _CACHE["data"]

    raw = _parse_feed_entries()
    items: list[dict] = []
    for row in raw:
        headline = row["headline"]
        raw_sum = row["raw_summary"]
        clean_for_gate = strip_html(raw_sum)
        if not passes_finance_gate(headline, clean_for_gate):
            continue

        symbols = find_nse_symbols(headline, clean_for_gate)
        summary = make_summary(headline, raw_sum)
        sent = sentiment_from_text(headline, raw_sum)
        keys = extract_keywords(headline, clean_for_gate, symbols)
        stocks = [
            card_symbol_fields(s, NSE_STOCKS.get(s))
            for s in symbols
        ]
        items.append(
            {
                "headline": headline,
                "summary": summary,
                "source": row["source"],
                "url": row["url"],
                "published_at": row["published_at"],
                "keywords": keys,
                "sentiment": sent,
                "matched_stocks": stocks,
                "insights": rule_insights(symbols, sent),
            }
        )
        if len(items) >= 24:
            break

    from datetime import datetime, timezone

    payload = {
        "items": items,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }
    _CACHE["data"] = payload
    _CACHE["ts"] = now
    return payload
