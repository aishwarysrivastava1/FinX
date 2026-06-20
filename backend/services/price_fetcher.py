"""
Robust price fetching + explicit data freshness tagging.

This module exists to remove reliance on `yfinance` (which is brittle for some NSE tickers)
and to ensure downstream AI/radar logic never "fakes" price data.
"""

from __future__ import annotations

import os
import json
import math
import time
import datetime as dt
from dataclasses import dataclass
from typing import Any, Literal, Optional

import requests

from database import db_fetchone, db_execute

from services import nse_service


Freshness = Literal["fresh", "stale", "unavailable"]
Source = Literal[
    "nse_quote",
    "alpha_vantage",
    "yahoo_chart",
    "stale_cache",
    "none",
]


@dataclass(frozen=True)
class DataFetchResult:
    freshness: Freshness
    source: Source
    timestamp: Optional[str]
    payload: Optional[dict[str, Any]]
    # When payload is not available, `payload` should be None.

    def to_stock_fields(self) -> dict[str, Any]:
        """
        Convert payload to the legacy `stock_data` keys the rest of the code expects,
        and add explicit freshness markers for the AI layer.
        """
        payload = self.payload or {}
        return {
            **payload,
            "price_data_quality": self.freshness,
            "price_source": self.source,
            "price_timestamp": self.timestamp,
        }


_FRESH_SECONDS = int(os.getenv("PRICE_FRESH_SECONDS", "3600"))       # 1 hour
_STALE_SECONDS = int(os.getenv("PRICE_STALE_SECONDS", "86400"))     # 24 hours

_ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY", "")

# Alpha Vantage often expects symbols differently by exchange.
# For now we attempt both raw and NSE-suffixed->stripped forms.
_SYMBOL_ALTERNATES = lambda s: [s, s.replace(".NS", "").replace(".BO", ""), s.replace(".NS", "").replace(".BO", "").upper()]


def _now_utc_iso() -> str:
    return dt.datetime.utcnow().isoformat()


def _parse_iso_ts(ts: Optional[str]) -> Optional[dt.datetime]:
    if not ts:
        return None
    try:
        return dt.datetime.fromisoformat(ts)
    except Exception:
        return None


def _age_seconds(ts: Optional[str]) -> Optional[float]:
    parsed = _parse_iso_ts(ts)
    if not parsed:
        return None
    return (dt.datetime.utcnow() - parsed).total_seconds()


def _quality_from_age(age: Optional[float]) -> Freshness:
    if age is None:
        return "unavailable"
    if age <= _FRESH_SECONDS:
        return "fresh"
    if age <= _STALE_SECONDS:
        return "stale"
    return "unavailable"


def _normalize_symbol(symbol: str) -> Optional[str]:
    if not symbol:
        return None
    s = symbol.upper().strip()
    s = s.replace(".BO", "").replace(".NS", "")
    # nse_service expects 2-10 uppercase alnum as validity.
    if not nse_service._is_valid_symbol(s):  # noqa: SLF001 - intentional internal reuse
        return None
    return s


def _validate_price(price: Any) -> bool:
    if price is None:
        return False
    if isinstance(price, (int, float)):
        if isinstance(price, float) and math.isnan(price):
            return False
        return price > 0
    try:
        p = float(price)
        if math.isnan(p):
            return False
        return p > 0
    except Exception:
        return False


def fetch_current_price(symbol: str) -> DataFetchResult:
    """
    Fetch current price + change% with explicit freshness.
    Returns freshness='unavailable' when no data is possible.
    """
    sym = _normalize_symbol(symbol)
    if not sym:
        return DataFetchResult("unavailable", "none", None, None)

    # 0) Cache-first: use nse_service in-memory quote cache (warmed every 1s by scheduler)
    try:
        import time as _t
        from services.nse_service import _quote_cache, _cache_lock, QUOTE_TTL
        with _cache_lock:
            entry = _quote_cache.get(sym)
        if entry and (_t.time() - entry[0]) < QUOTE_TTL:
            q = entry[1]
            if q and _validate_price(q.get("price")):
                ts = q.get("timestamp") or _now_utc_iso()
                return DataFetchResult(
                    freshness="fresh",
                    source="nse_quote",
                    timestamp=ts,
                    payload={
                        "current_price": q.get("price"),
                        "change_pct":    q.get("percent_change"),
                        "open":          q.get("open"),
                        "high":          q.get("high"),
                        "low":           q.get("low"),
                        "prev_close":    q.get("prev_close"),
                        "volume":        q.get("volume"),
                    },
                )
    except Exception:
        pass

    # 1) Primary: NSE quote-equity (session warmed) via nse_service internals.
    try:
        raw = nse_service._fetch_nse_quote_raw(sym)  # noqa: SLF001
        if raw and isinstance(raw.get("priceInfo"), dict):
            normalized = nse_service._normalize_quote(sym, raw)  # noqa: SLF001
            ts = normalized.get("timestamp")
            if _validate_price(normalized.get("price")):
                age = _age_seconds(ts)
                freshness = _quality_from_age(age)
                _persist_price_cache(sym, normalized, ts, "nse_quote", freshness)
                return DataFetchResult(
                    freshness=freshness,
                    source="nse_quote",
                    timestamp=ts,
                    payload={
                        "current_price": normalized.get("price"),
                        "change_pct": normalized.get("percent_change"),
                        "open": normalized.get("open"),
                        "high": normalized.get("high"),
                        "low": normalized.get("low"),
                        "prev_close": normalized.get("prev_close"),
                        "volume": normalized.get("volume"),
                    },
                )
    except Exception:
        # Fall through to Alpha/stale cache.
        pass

    # 2) Fallback 1: Alpha Vantage
    alpha_result = _alpha_vantage_quote_any(sym)
    if alpha_result and _validate_price(alpha_result["current_price"]):
        ts = alpha_result.get("timestamp") or _now_utc_iso()
        freshness = _quality_from_age(_age_seconds(ts))
        _persist_price_cache(sym, alpha_result, ts, "alpha_vantage", freshness)
        return DataFetchResult(
            freshness=freshness,
            source="alpha_vantage",
            timestamp=ts,
            payload=alpha_result,
        )

    # 3) Fallback 2: stale cache (last known good price)
    cached = _read_price_cache(sym)
    if cached:
        ts = cached.get("price_ts") or cached.get("price_timestamp") or cached.get("updated_at")
        freshness = _quality_from_age(_age_seconds(ts))
        if freshness in ("fresh", "stale"):
            return DataFetchResult(
                freshness=freshness,
                source="stale_cache",
                timestamp=ts,
                payload={
                    "current_price": cached.get("price"),
                    "change_pct": cached.get("change_pct"),
                    "open": cached.get("open"),
                    "high": cached.get("high"),
                    "low": cached.get("low"),
                    "prev_close": cached.get("prev_close"),
                    "volume": cached.get("volume"),
                },
            )

    return DataFetchResult("unavailable", "none", None, None)


def fetch_close_series(symbol: str, window_days: int = 120) -> DataFetchResult:
    """
    Fetch daily close series for indicator computation.

    Returns `payload={"dates": [...], "closes": [...], "ohlc": {...}}` when available.
    """
    sym = _normalize_symbol(symbol)
    if not sym:
        return DataFetchResult("unavailable", "none", None, None)

    # 0) Cache-first: serve from DB if data is fresh (avoids expensive external calls)
    cached = _read_close_series_cache(sym)
    if cached:
        ts = cached.get("series_ts") or cached.get("updated_at")
        age = _age_seconds(ts)
        if age is not None and age < _FRESH_SECONDS:
            try:
                series_json = json.loads(cached.get("series_json") or "null") or {}
                closes = series_json.get("closes") or []
                dates  = series_json.get("dates")  or []
                if len(closes) >= 50:
                    series_json["timestamp"] = ts
                    return DataFetchResult(
                        freshness="fresh",
                        source="stale_cache",
                        timestamp=ts,
                        payload=series_json,
                    )
            except Exception:
                pass

    # 1) Alpha Vantage daily series (attempt multiple symbol forms)
    alpha_series = _alpha_vantage_daily_series_any(sym)
    if alpha_series and len(alpha_series.get("closes", [])) >= 50:
        ts = alpha_series.get("timestamp") or _now_utc_iso()
        freshness = _quality_from_age(_age_seconds(ts))
        _persist_close_series_cache(sym, alpha_series, ts, "alpha_vantage", freshness)
        return DataFetchResult(
            freshness=freshness,
            source="alpha_vantage",
            timestamp=ts,
            payload=alpha_series,
        )

    # 2) Yahoo chart API (works without yfinance; last-resort "secondary" provider)
    yahoo_series = _yahoo_close_series_any(sym, window_days=window_days)
    if yahoo_series and len(yahoo_series.get("closes", [])) >= 50:
        ts = yahoo_series.get("timestamp") or _now_utc_iso()
        freshness = _quality_from_age(_age_seconds(ts))
        _persist_close_series_cache(sym, yahoo_series, ts, "yahoo_chart", freshness)
        return DataFetchResult(
            freshness=freshness,
            source="yahoo_chart",
            timestamp=ts,
            payload=yahoo_series,
        )

    # 3) stale cache
    cached = _read_close_series_cache(sym)
    if cached:
        ts = cached.get("series_ts") or cached.get("updated_at")
        freshness = _quality_from_age(_age_seconds(ts))
        if freshness in ("fresh", "stale"):
            try:
                series_json = json.loads(cached.get("series_json") or "null") or {}
                closes = series_json.get("closes") or []
                dates = series_json.get("dates") or []
                if len(closes) >= 50:
                    series_json["timestamp"] = ts
                    return DataFetchResult(
                        freshness=freshness,
                        source="stale_cache",
                        timestamp=ts,
                        payload=series_json,
                    )
            except Exception:
                pass

    return DataFetchResult("unavailable", "none", None, None)


def _alpha_vantage_quote_any(symbol: str) -> Optional[dict[str, Any]]:
    if not _ALPHA_VANTAGE_KEY:
        return None
    for sym in _SYMBOL_ALTERNATES(symbol):
        try:
            # TIME_SERIES_DAILY_ADJUSTED provides the "latest close" (not real-time).
            url = "https://www.alphavantage.co/query"
            params = {
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": sym,
                "outputsize": "compact",
                "apikey": _ALPHA_VANTAGE_KEY,
            }
            resp = requests.get(url, params=params, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            data = resp.json()
            ts_key = "Time Series (Daily)"  # common key
            if "Error Message" in data or "Note" in data:
                continue
            series = data.get(ts_key) or data.get("Time Series (Daily Adjusted)") or data.get("Time Series (Daily) ")
            if not isinstance(series, dict) or not series:
                continue

            # Pick last two trading days.
            dates = sorted(series.keys(), reverse=True)[:2]
            if len(dates) < 2:
                continue
            last = series[dates[0]]
            prev = series[dates[1]]
            last_close = float(last.get("4. close") or last.get("4. close") or 0)
            prev_close = float(prev.get("4. close") or prev.get("4. close") or 0)
            if last_close <= 0:
                continue
            change_pct = ((last_close - prev_close) / prev_close * 100) if prev_close else 0.0
            return {
                "current_price": round(last_close, 2),
                "change_pct": round(change_pct, 2),
                "open": None,
                "high": None,
                "low": None,
                "prev_close": round(prev_close, 2),
                "volume": None,
                "timestamp": _now_utc_iso(),
            }
        except Exception:
            continue
    return None


def _alpha_vantage_daily_series_any(symbol: str) -> Optional[dict[str, Any]]:
    if not _ALPHA_VANTAGE_KEY:
        return None
    for sym in _SYMBOL_ALTERNATES(symbol):
        try:
            url = "https://www.alphavantage.co/query"
            params = {
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": sym,
                "outputsize": "compact",
                "apikey": _ALPHA_VANTAGE_KEY,
            }
            resp = requests.get(url, params=params, timeout=14, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            data = resp.json()
            if "Error Message" in data or "Note" in data:
                continue
            series = data.get("Time Series (Daily)") or data.get("Time Series (Daily Adjusted)") or {}
            if not isinstance(series, dict) or not series:
                continue

            # Sort ascending for indicator calculations.
            dates_sorted = sorted(series.keys())
            # take a window based on requested size
            take = max(60, int(window_days * 0.9))
            dates_sorted = dates_sorted[-take:]

            closes: list[float] = []
            dates_out: list[str] = []
            for d in dates_sorted:
                row = series.get(d) or {}
                close_str = row.get("4. close") or row.get("4. close") or row.get("4. close (adjusted)") or row.get("4. close (adjusted)")  # noqa: E501
                if close_str is None:
                    continue
                try:
                    c = float(close_str)
                except Exception:
                    continue
                if math.isnan(c) or c <= 0:
                    continue
                closes.append(round(c, 4))
                dates_out.append(str(d))

            if len(closes) < 60:
                continue

            return {"dates": dates_out, "closes": closes, "timestamp": _now_utc_iso()}
        except Exception:
            continue
    return None


def _yahoo_close_series_any(symbol: str, window_days: int = 120) -> Optional[dict[str, Any]]:
    """
    Fetch close series from Yahoo chart endpoint (without `yfinance` library).
    """
    # Try both with and without suffix. The Yahoo endpoint typically uses .NS for India.
    candidates = [f"{symbol}.NS", symbol]
    for s in candidates:
        try:
            # Ask for a larger range, then slice.
            resp = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{s}",
                params={"range": "1y", "interval": "1d"},
                headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip, deflate"},
                timeout=14,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("chart", {}).get("error"):
                continue
            result = (data.get("chart", {}).get("result") or [None])[0]
            if not result:
                continue
            timestamps = result.get("timestamp") or []
            q = ((result.get("indicators") or {}).get("quote") or [{}])[0]
            closes = q.get("close") or []
            items: list[tuple[str, float]] = []
            for ts, c in zip(timestamps, closes):
                if c is None:
                    continue
                try:
                    c_f = float(c)
                except Exception:
                    continue
                if math.isnan(c_f) or c_f <= 0:
                    continue
                t = dt.datetime.fromtimestamp(ts, tz=dt.timezone(dt.timedelta(hours=5, minutes=30)))
                items.append((t.strftime("%Y-%m-%d"), round(c_f, 4)))

            if len(items) < 60:
                continue
            # slice to requested window
            items = items[-max(60, window_days):]
            dates = [d for d, _ in items]
            closes_out = [c for _, c in items]
            return {"dates": dates, "closes": closes_out, "timestamp": _now_utc_iso()}
        except Exception:
            continue
    return None


def _persist_price_cache(symbol: str, payload: dict[str, Any], ts: str, source: str, freshness: Freshness) -> None:
    try:
        db_execute(
            """
            INSERT OR REPLACE INTO price_cache
              (symbol, price, change_pct, open, high, low, prev_close, volume, price_ts, source, freshness)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                symbol,
                payload.get("price") if "price" in payload else payload.get("current_price"),
                payload.get("change_pct"),
                payload.get("open"),
                payload.get("high"),
                payload.get("low"),
                payload.get("prev_close"),
                payload.get("volume"),
                ts,
                source,
                freshness,
            ),
        )
    except Exception:
        pass


def _read_price_cache(symbol: str) -> Optional[dict[str, Any]]:
    try:
        return db_fetchone(
            "SELECT * FROM price_cache WHERE symbol=?",
            (symbol,),
        )
    except Exception:
        return None


def _persist_close_series_cache(symbol: str, series_payload: dict[str, Any], ts: str, source: str, freshness: Freshness) -> None:
    try:
        db_execute(
            """
            INSERT OR REPLACE INTO close_series_cache
              (symbol, series_json, series_ts, source, freshness)
            VALUES (?,?,?,?,?)
            """,
            (
                symbol,
                json.dumps(
                    {
                        "dates": series_payload.get("dates") or [],
                        "closes": series_payload.get("closes") or [],
                    }
                ),
                ts,
                source,
                freshness,
            ),
        )
    except Exception:
        pass


def _read_close_series_cache(symbol: str) -> Optional[dict[str, Any]]:
    try:
        return db_fetchone(
            "SELECT * FROM close_series_cache WHERE symbol=?",
            (symbol,),
        )
    except Exception:
        return None

