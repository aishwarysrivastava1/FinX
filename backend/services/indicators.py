import math
import requests

from services.price_fetcher import fetch_close_series, fetch_current_price

POPULAR_STOCKS = [
    "RELIANCE.NS",
    "TCS.NS",
    "INFY.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "TATAMOTORS.NS",
    "WIPRO.NS",
    "BAJFINANCE.NS",
    "SUNPHARMA.NS",
    "ITC.NS",
    "SBIN.NS",
    "ADANIENT.NS",
    "MARUTI.NS",
    "NESTLEIND.NS",
    "POWERGRID.NS",
]


def add_ns_suffix(symbol: str) -> str:
    symbol = symbol.upper().strip()
    if symbol.startswith("^"):
        return symbol
    return symbol if (symbol.endswith(".NS") or symbol.endswith(".BO")) else f"{symbol}.NS"


def compute_rsi_manual(closes: list[float], length: int = 14) -> list[float | None]:
    """
    RSI (Wilder) computed from close prices.
    Returns a list aligned to `closes` where the first `length` values are `None`.
    """
    if not closes or len(closes) < length + 1:
        return [None] * len(closes or [])

    rsi: list[float | None] = [None] * len(closes)

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, length + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))

    avg_gain = sum(gains) / length
    avg_loss = sum(losses) / length

    def _rsi(avg_g: float, avg_l: float) -> float:
        if avg_l == 0:
            return 100.0
        rs = avg_g / avg_l
        return 100.0 - (100.0 / (1.0 + rs))

    # RSI value starts at index `length`
    rsi[length] = _rsi(avg_gain, avg_loss)

    for i in range(length + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gain = max(diff, 0.0)
        loss = max(-diff, 0.0)

        # Wilder smoothing
        avg_gain = ((avg_gain * (length - 1)) + gain) / length
        avg_loss = ((avg_loss * (length - 1)) + loss) / length
        rsi[i] = _rsi(avg_gain, avg_loss)

    return rsi


def interpret_rsi(rsi_val: float | None) -> str:
    if rsi_val is None:
        return "unknown"
    v = float(rsi_val)
    if v >= 70:
        return "overbought"
    if v >= 60:
        return "approaching_overbought"
    if v <= 30:
        return "oversold"
    if v <= 40:
        return "approaching_oversold"
    return "neutral"


def compute_ema(closes: list[float], span: int) -> list[float]:
    """Exponential moving average over a list of closes."""
    if not closes:
        return []
    alpha = 2.0 / (span + 1.0)
    ema: list[float] = []
    prev = closes[0]
    ema.append(prev)
    for i in range(1, len(closes)):
        cur = closes[i]
        nxt = (cur * alpha) + (prev * (1.0 - alpha))
        ema.append(nxt)
        prev = nxt
    return ema


def compute_sma_last(closes: list[float], window: int) -> float | None:
    """Simple moving average of the last `window` values."""
    if not closes or len(closes) < window:
        return None
    tail = closes[-window:]
    return sum(tail) / float(window)


def _get_stock_data_yahoo_direct(symbol: str, period: str = "3mo") -> dict:
    """
    Fetch stock history directly from Yahoo Finance chart API.
    Used as fallback when yfinance library fails (Brotli decode errors).
    """
    # Legacy helper kept for backward compatibility, but the production path
    # now uses `services.price_fetcher` + pure-Python indicator math.
    return {"error": "Legacy indicator helper unused", "symbol": symbol}
    _range_map = {"1mo": "1mo", "3mo": "3mo", "6mo": "6mo", "1y": "1y"}
    yf_range = _range_map.get(period, "3mo")
    try:
        resp = _req.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS",
            params={"range": yf_range, "interval": "1d"},
            headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip, deflate"},
            timeout=12,
        )
        resp.raise_for_status()
        data  = resp.json()
        res   = (data.get("chart", {}).get("result") or [None])[0]
        if not res:
            return {"error": "No data", "symbol": symbol}

        meta       = res.get("meta") or {}
        timestamps = res.get("timestamp") or []
        q          = ((res.get("indicators") or {}).get("quote") or [{}])[0]
        closes     = q.get("close",  [])
        opens      = q.get("open",   [])
        highs      = q.get("high",   [])
        lows       = q.get("low",    [])
        volumes    = q.get("volume", [])

        # Filter out None values, keeping aligned lists
        valid = [(ts, c, o, h, l, v) for ts, c, o, h, l, v
                 in zip(timestamps, closes, opens, highs, lows, volumes)
                 if c is not None]
        if len(valid) < 5:
            return {"error": "Insufficient data", "symbol": symbol}

        dates_all  = [str(_dt.datetime.utcfromtimestamp(r[0]).date()) for r in valid]
        close_arr  = pd.Series([r[1] for r in valid], dtype=float)

        # Compute indicators from close prices
        if USE_PANDAS_TA and ta:
            rsi_s   = ta.rsi(close_arr, length=14)
            ema20_s = ta.ema(close_arr, length=20)
            ema50_s = ta.ema(close_arr, length=50)
        elif USE_TA_LIB:
            rsi_s   = RSIIndicator(close=close_arr, window=14).rsi()
            ema20_s = EMAIndicator(close=close_arr, window=20).ema_indicator()
            ema50_s = EMAIndicator(close=close_arr, window=50).ema_indicator()
        else:
            rsi_s   = compute_rsi_manual(close_arr, 14)
            ema20_s = close_arr.ewm(span=20, adjust=False).mean()
            ema50_s = close_arr.ewm(span=50, adjust=False).mean()

        def _safe_last(s):
            """Return last non-NaN value of a Series, or None if series is None/empty."""
            if s is None or len(s) == 0:
                return None
            v = s.iloc[-1]
            return float(v) if pd.notna(v) else None

        last_rsi   = _safe_last(rsi_s)
        last_ema20 = _safe_last(ema20_s)
        last_ema50 = _safe_last(ema50_s)

        ema_signal = "neutral"
        if last_ema20 and last_ema50:
            prev_ema20 = float(ema20_s.iloc[-2]) if (ema20_s is not None and len(ema20_s) >= 2) else last_ema20
            prev_ema50 = float(ema50_s.iloc[-2]) if (ema50_s is not None and len(ema50_s) >= 2) else last_ema50
            if last_ema20 > last_ema50:
                ema_signal = "bullish_crossover" if prev_ema20 <= prev_ema50 else "bullish"
            elif last_ema20 < last_ema50:
                ema_signal = "bearish_crossover" if prev_ema20 >= prev_ema50 else "bearish"

        ltp = float(meta.get("regularMarketPrice") or valid[-1][1])
        prev_c = float(valid[-2][1]) if len(valid) >= 2 else ltp
        change_pct = round((ltp - prev_c) / prev_c * 100, 2) if prev_c else 0

        last_30 = [round(r[1], 2) for r in valid[-30:]]
        dates_30 = dates_all[-30:]

        highs = [r[3] for r in valid if r[3] is not None and r[3] > 0]
        lows  = [r[4] for r in valid if r[4] is not None and r[4] > 0]
        return {
            "symbol":        symbol.upper(),
            "current_price": round(ltp, 2),
            "change_pct":    change_pct,
            "volume":        int(valid[-1][5] or 0),
            "rsi":           round(float(last_rsi), 1) if last_rsi else None,
            "ema20":         round(float(last_ema20), 2) if last_ema20 else None,
            "ema50":         round(float(last_ema50), 2) if last_ema50 else None,
            "sma200":        None,
            "ema_signal":    ema_signal,
            "rsi_zone":      interpret_rsi(last_rsi),
            "price_30d":     last_30,
            "dates_30d":     dates_30,
            "high_52w":      round(max(highs), 2) if highs else None,
            "low_52w":       round(min(lows),  2) if lows  else None,
            "avg_volume_20d": int(sum(r[5] for r in valid[-20:] if r[5]) / min(20, len(valid))),
        }
    except Exception as e:
        print(f"[Indicators-Direct] Error for {symbol}: {e}")
        return {"error": str(e), "symbol": symbol}

def get_stock_data(symbol: str, period: str = "3mo") -> dict:
    """
    Unified stock data for radar/cards:
    - Current price from NSE quote (with explicit freshness tagging)
    - Close series from multi-source provider (Alpha Vantage, Yahoo chart, stale cache)
    - Compute RSI + EMA signals from the close series

    IMPORTANT: When price data is unavailable (or invalid), return an `error` dict.
    Downstream code is expected to skip signal/card generation in that case.
    """
    try:
        current = fetch_current_price(symbol).to_stock_fields()
        series = fetch_close_series(symbol, window_days=180).payload or {}

        price = current.get("current_price")
        if not isinstance(price, (int, float)) or price <= 0 or (isinstance(price, float) and math.isnan(price)):
            return {"error": "Price data unavailable", "symbol": (symbol or "").upper()}

        closes = series.get("closes") or []
        dates = series.get("dates") or []
        # Minimum 15 bars — enough for RSI(14). EMA-50/SMA-200 only computed when enough bars exist.
        if not closes or len(closes) < 15 or len(dates) < 15:
            return {"error": "Insufficient price history", "symbol": (symbol or "").upper()}

        # Indicators — each computed only when enough history is available
        rsi_vals   = compute_rsi_manual(closes, 14)
        ema20_vals = compute_ema(closes, 20) if len(closes) >= 20 else []
        ema50_vals = compute_ema(closes, 50) if len(closes) >= 50 else []
        sma200_last = compute_sma_last(closes, 200) if len(closes) >= 200 else None

        last_idx = len(closes) - 1
        prev_idx = last_idx - 1 if last_idx >= 1 else last_idx

        last_rsi   = rsi_vals[last_idx]   if rsi_vals   and last_idx < len(rsi_vals)   else None
        last_ema20 = ema20_vals[last_idx] if ema20_vals and last_idx < len(ema20_vals) else None
        last_ema50 = ema50_vals[last_idx] if ema50_vals and last_idx < len(ema50_vals) else None

        change_pct = current.get("change_pct")
        if change_pct is None or (isinstance(change_pct, float) and math.isnan(change_pct)):
            prev_close = closes[prev_idx] if prev_idx >= 0 else closes[last_idx]
            change_pct = round((closes[last_idx] - prev_close) / prev_close * 100, 2) if prev_close else 0.0

        ema_signal = "neutral"
        if last_ema20 is not None and last_ema50 is not None:
            prev_ema20 = ema20_vals[prev_idx] if len(ema20_vals) > prev_idx else last_ema20
            prev_ema50 = ema50_vals[prev_idx] if len(ema50_vals) > prev_idx else last_ema50
            if float(last_ema20) > float(last_ema50):
                ema_signal = "bullish_crossover" if float(prev_ema20) <= float(prev_ema50) else "bullish"
            elif float(last_ema20) < float(last_ema50):
                ema_signal = "bearish_crossover" if float(prev_ema20) >= float(prev_ema50) else "bearish"

        last_30 = [round(float(c), 2) for c in closes[-30:]]
        dates_30 = dates[-30:]

        window_52w = 252
        closes_52w = closes[-window_52w:]
        high_52w = max(closes_52w) if closes_52w else None
        low_52w = min(closes_52w) if closes_52w else None

        return {
            "symbol": (symbol or "").upper(),
            "current_price": round(float(price), 2),
            "change_pct": change_pct,
            "volume": current.get("volume"),
            "rsi": round(float(last_rsi), 1) if last_rsi is not None else None,
            "ema20": round(float(last_ema20), 2) if last_ema20 is not None else None,
            "ema50": round(float(last_ema50), 2) if last_ema50 is not None else None,
            "sma200": round(float(sma200_last), 2) if sma200_last is not None else None,
            "ema_signal": ema_signal,
            "rsi_zone": interpret_rsi(last_rsi),
            "price_30d": last_30,
            "dates_30d": dates_30,
            "high_52w": round(high_52w, 2) if high_52w is not None else None,
            "low_52w": round(low_52w, 2) if low_52w is not None else None,
            "avg_volume_20d": None,
            "price_data_quality": current.get("price_data_quality"),
            "price_source": current.get("price_source"),
            "price_timestamp": current.get("price_timestamp"),
        }
    except Exception as e:
        return {"error": f"Indicator pipeline error: {e}", "symbol": (symbol or "").upper()}


def get_nifty_snapshot() -> dict:
    """
    Small helper for chat context.
    Uses Yahoo chart endpoint directly (no yfinance).
    """
    try:
        resp = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI",
            params={"range": "5d", "interval": "1d"},
            headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip, deflate"},
            timeout=12,
        )
        resp.raise_for_status()
        data = resp.json()
        res = (data.get("chart", {}).get("result") or [None])[0]
        if not res:
            return {}
        timestamps = res.get("timestamp") or []
        q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
        closes = q.get("close") or []
        valid = [(ts, c) for ts, c in zip(timestamps, closes) if c is not None]
        if len(valid) < 2:
            return {}
        last_close = float(valid[-1][1])
        prev_close = float(valid[-2][1])
        change_pct = round((last_close - prev_close) / prev_close * 100, 2) if prev_close else 0.0
        return {
            "nifty50": round(last_close, 2),
            "nifty50_change_pct": change_pct,
            "nifty50_direction": "up" if change_pct > 0 else "down",
        }
    except Exception:
        return {}
