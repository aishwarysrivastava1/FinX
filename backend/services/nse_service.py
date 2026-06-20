# backend/services/nse_service.py
"""
NSE live quote service using NSE India's internal API.
Exposes: get_quote(symbol), get_bulk_quotes(symbols), get_historical(symbol, period)
Cache TTL: 8 seconds for quotes, 60 seconds for historical
Fallback: yfinance if NSE API fails
"""

import time
import datetime
import threading
import os
import requests as _requests
from typing import Optional

_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

NSE_BASE = "https://www.nseindia.com"

# ── Dedicated equity-quote session ───────────────────────────
# Uses gzip/deflate only (no 'br'/Brotli) since Python requests
# can't decompress Brotli without brotlipy, causing empty bodies.
_EQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",   # NO 'br' — avoids Brotli decode failure
    "Referer":         "https://www.nseindia.com/",
    "Connection":      "keep-alive",
}

_eq_session: _requests.Session | None = None
_eq_lock = threading.Lock()

# ── Yahoo Finance authenticated session (crumb-based) ─────────
_yahoo_session: _requests.Session | None = None
_yahoo_crumb:   str | None = None
_yahoo_lock = threading.Lock()

def _get_yahoo_session():
    """Return a Yahoo Finance session with valid crumb for v7 API auth."""
    global _yahoo_session, _yahoo_crumb
    with _yahoo_lock:
        if _yahoo_session and _yahoo_crumb:
            return _yahoo_session, _yahoo_crumb
        s = _requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip, deflate"})
        try:
            s.get("https://finance.yahoo.com/", timeout=8)
            crumb = s.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=5).text.strip()
            _yahoo_session = s
            _yahoo_crumb   = crumb
            print(f"[Yahoo] Session initialised, crumb={crumb[:6]}...")
        except Exception as e:
            print(f"[Yahoo] Session init failed: {e}")
            _yahoo_session = s
            _yahoo_crumb   = ""
        return _yahoo_session, _yahoo_crumb

def _reset_yahoo_session():
    global _yahoo_session, _yahoo_crumb
    with _yahoo_lock:
        _yahoo_session = None
        _yahoo_crumb   = None


def _get_eq_session() -> _requests.Session:
    """Return (or create) a warmed-up session for the equity-quote endpoint."""
    global _eq_session
    with _eq_lock:
        if _eq_session is None:
            s = _requests.Session()
            s.headers.update(_EQ_HEADERS)
            try:
                s.get(NSE_BASE, timeout=8)
                time.sleep(0.8)
                # Visit the equity page to get required cookies (nsit, browse-url)
                s.get(f"{NSE_BASE}/get-quotes/equity?symbol=RELIANCE", timeout=8)
                time.sleep(0.5)
                print("[NSE-EQ] Equity session warmed up")
            except Exception as e:
                print(f"[NSE-EQ] Warmup error: {e}")
            _eq_session = s
        return _eq_session


def _reset_eq_session():
    global _eq_session
    with _eq_lock:
        _eq_session = None
    print("[NSE-EQ] Session reset")

# ── Caches ────────────────────────────────────────────────────
_quote_cache: dict = {}   # {symbol: (timestamp, data)}
_hist_cache:  dict = {}   # {"symbol_period": (timestamp, data)}
_cache_lock   = threading.Lock()
_hot_symbols: dict[str, float] = {}  # {symbol: last_requested_ts}
QUOTE_TTL       = max(1, int(os.getenv("QUOTE_TTL_SECONDS", "15")))  # seconds — scheduler writes every 2s; 15s TTL prevents cold-cache gaps
HIST_TTL        = max(10, int(os.getenv("HIST_TTL_SECONDS", "60")))  # seconds
HIST_TTL_1D_OPEN   =  max(1, int(os.getenv("HIST_TTL_1D_OPEN_SECONDS", "8")))  # seconds — intraday during market hours
HIST_TTL_1D_CLOSED = 300 # seconds — intraday cache after market close
HOT_SYMBOL_TTL_SECONDS = max(10, int(os.getenv("HOT_SYMBOL_TTL_SECONDS", "180")))
MAX_HOT_SYMBOLS = max(5, int(os.getenv("MAX_HOT_SYMBOLS", "20")))

# Common English words / finance terms to skip in symbol detection
_STOPWORDS = {
    "THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL", "CAN", "HER",
    "WAS", "ONE", "OUR", "OUT", "DAY", "GET", "HAS", "HIM", "HIS", "HOW",
    "ITS", "MAY", "NEW", "NOW", "OLD", "SEE", "TWO", "WAY", "WHO", "BOY",
    "DID", "LET", "PUT", "SAY", "SHE", "TOO", "USE", "BUY", "SELL", "NSE",
    "BSE", "IPO", "ETF", "LTP", "WHAT", "WHEN", "THIS", "WITH", "THAT",
    "FROM", "HAVE", "WILL", "BEEN", "THEY", "WERE", "SAID", "EACH", "TELL",
    "DOES", "SOME", "THAN", "THEN", "THEM", "ALSO", "VERY", "JUST", "OVER",
    "KNOW", "INTO", "GOOD", "MUCH", "LIKE", "TIME", "YEAR", "MAKE", "LOOK",
    "COME", "GIVE", "EVEN", "BACK", "ONLY", "WELL", "MOST", "AFTER", "BEFORE",
    "ABOUT", "STOCK", "SHARE", "PRICE", "TRADE", "MARKET", "INDEX", "TODAY",
    "NIFTY", "SENSEX", "WANT", "SHOULD", "WOULD", "COULD", "GOING", "DOING",
    "THINK", "TELL", "SHOW", "GIVE", "TAKE", "COME", "HELP", "NEED", "WANT",
    "MEAN", "CALL", "KEEP", "FEEL", "FALL", "RISE", "HIGH", "LAST", "NEXT",
    "DOWN", "SURE", "LONG", "TERM", "VIEW", "HOLD", "OPEN", "LIVE", "REAL",
    "DATA", "NEWS", "RATE", "FUND", "BANK", "YEAR", "WEEK", "MONTH", "BEST",
    "PLAN", "GROW", "BULL", "BEAR", "ZONE", "RISK", "LOSS", "GAIN",
    # Short common English words (2-3 letters)
    "IS", "IT", "IN", "AN", "AT", "SO", "NO", "DO", "GO", "TO", "AM", "BE",
    "MY", "BY", "UP", "AS", "IF", "OR", "OF", "ON", "ME", "HE", "US", "WE",
    "HI", "OK", "YES", "HEY", "ITS", "ITS",
    # Common words that appear after uppercasing sentences
    "PLEASE", "THANKS", "HELLO", "THERE", "THEIR", "WHERE", "WHICH", "WHILE",
    "THESE", "THOSE", "FIRST", "SECOND", "THIRD", "RIGHT", "WRONG", "AGAIN",
    "STILL", "OFTEN", "SINCE", "BELOW", "ABOVE", "BOTH", "EACH", "PART",
    "SUCH", "SAME", "BOTH", "LESS", "MORE", "TRUE", "LATE", "TELL", "FELL",
    "CASE", "MOVE", "NEED", "TURN", "PAST", "PUTS", "CALL", "PUTS", "TYPE",
    "FORM", "SHOW", "MEAN", "HELD", "HOLD", "GOES", "NEAR", "HARD", "FAST",
    "SLOW", "FELL", "MOVE", "STEP", "SIDE", "AREA", "HOME", "WORK", "CITY",
    "AREA", "FACT", "IDEA", "LIFE", "HAND", "FACE", "WORD", "FIRE", "DARK",
}


# ── Validators ───────────────────────────────────────────────
def _is_valid_symbol(symbol: str) -> bool:
    """Symbol must be 2–10 uppercase alphanumeric characters."""
    if not symbol:
        return False
    if len(symbol) < 2 or len(symbol) > 10:
        return False
    return symbol.isalnum()


def register_hot_symbol(symbol: str) -> None:
    """
    Mark a symbol as actively requested by clients so cache warmers can prioritize it.
    """
    sym = symbol.upper().strip().replace(".NS", "").replace(".BO", "")
    if not _is_valid_symbol(sym):
        return
    now = time.time()
    with _cache_lock:
        _hot_symbols[sym] = now
        # Keep this map bounded.
        if len(_hot_symbols) > (MAX_HOT_SYMBOLS * 2):
            stale_cutoff = now - HOT_SYMBOL_TTL_SECONDS
            stale = [k for k, ts in _hot_symbols.items() if ts < stale_cutoff]
            for k in stale:
                _hot_symbols.pop(k, None)
            if len(_hot_symbols) > MAX_HOT_SYMBOLS:
                keep = sorted(_hot_symbols.items(), key=lambda kv: kv[1], reverse=True)[:MAX_HOT_SYMBOLS]
                _hot_symbols.clear()
                _hot_symbols.update(dict(keep))


def get_hot_symbols(limit: int = 10) -> list[str]:
    now = time.time()
    with _cache_lock:
        stale_cutoff = now - HOT_SYMBOL_TTL_SECONDS
        for k in [k for k, ts in _hot_symbols.items() if ts < stale_cutoff]:
            _hot_symbols.pop(k, None)
        ordered = sorted(_hot_symbols.items(), key=lambda kv: kv[1], reverse=True)
    return [k for k, _ in ordered[: max(1, limit)]]


def _downsample_points(points: list[dict], max_points: int) -> list[dict]:
    if len(points) <= max_points or max_points <= 0:
        return points
    # Uniform downsample while preserving first/last points.
    step = (len(points) - 1) / (max_points - 1)
    idxs = {0, len(points) - 1}
    for i in range(1, max_points - 1):
        idxs.add(int(round(i * step)))
    return [points[i] for i in sorted(idxs)]


# ── NSE Batch fetch (Nifty 50 in ONE call) ────────────────────
def get_nifty50_batch(_retry: int = 0) -> int:
    """
    Fetch ALL Nifty 50 quotes in a SINGLE NSE API call using the index endpoint.
    Writes directly into _quote_cache. Returns count of symbols updated.

    This replaces 50 individual calls with 1 — eliminates rate limiting entirely.
    """
    if _retry >= 2:
        return 0
    session = _get_eq_session()
    try:
        resp = session.get(
            f"{NSE_BASE}/api/equity-stockIndices",
            params={"index": "NIFTY 50"},
            timeout=8,
        )
        if resp.status_code == 403:
            print(f"[NSE-Batch] 403 — resetting session (attempt {_retry+1}/2)")
            _reset_eq_session()
            time.sleep(1)
            return get_nifty50_batch(_retry + 1)
        if resp.status_code in (400, 404):
            return 0
        resp.raise_for_status()
        if not resp.content:
            return 0
        data = resp.json()
        items = data.get("data", [])
        if not isinstance(items, list):
            return 0

        def _f(v):
            try: return round(float(v), 2) if v is not None else None
            except (TypeError, ValueError): return None

        def _i(v):
            try: return int(v) if v is not None else None
            except (TypeError, ValueError): return None

        now = time.time()
        updated = 0
        with _cache_lock:
            for item in items:
                sym = (item.get("symbol") or "").upper().strip()
                if not _is_valid_symbol(sym):
                    continue
                price = _f(item.get("lastPrice"))
                if not price or price <= 0:
                    continue
                quote = {
                    "symbol":         sym,
                    "price":          price,
                    "change":         _f(item.get("change")),
                    "percent_change": _f(item.get("pChange")),
                    "open":           _f(item.get("open")),
                    "high":           _f(item.get("dayHigh")),
                    "low":            _f(item.get("dayLow")),
                    "prev_close":     _f(item.get("previousClose") or item.get("prevClose")),
                    "volume":         _i(item.get("totalTradedVolume")),
                    "timestamp":      datetime.datetime.utcnow().isoformat(),
                    "raw_data":       None,
                }
                _quote_cache[sym] = (now, quote)
                updated += 1
        return updated
    except Exception as e:
        print(f"[NSE-Batch] Error: {e}")
        return 0


# ── NSE API fetch ─────────────────────────────────────────────
def _fetch_nse_quote_raw(symbol: str, _retry: int = 0) -> Optional[dict]:
    """Fetch raw JSON from NSE quote-equity endpoint. Returns None on any failure."""
    if _retry >= 2:
        print(f"[NSE] Max retries reached for {symbol}")
        return None
    session = _get_eq_session()
    try:
        resp = session.get(
            f"{NSE_BASE}/api/quote-equity",
            params={"symbol": symbol},
            timeout=5,
        )
        if resp.status_code == 403:
            print(f"[NSE] 403 for {symbol} — resetting equity session (attempt {_retry + 1}/2)")
            _reset_eq_session()
            time.sleep(0.3)
            return _fetch_nse_quote_raw(symbol, _retry + 1)
        if resp.status_code in (404, 400):
            return None
        resp.raise_for_status()
        if not resp.content:
            print(f"[NSE] Empty response for {symbol}")
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception as e:
        print(f"[NSE] Quote fetch error for {symbol}: {e}")
        return None


def _normalize_quote(symbol: str, raw: dict) -> dict:
    """
    Extract and normalize fields from raw NSE quote-equity response.
    Missing fields are set to None — never raises.
    """
    price_info = raw.get("priceInfo") or {}
    order_book = raw.get("marketDeptOrderBook") or {}
    trade_info = order_book.get("tradeInfo") or {}
    intraday   = price_info.get("intraDayHighLow") or {}

    def _f(val) -> Optional[float]:
        try:
            return round(float(val), 2) if val is not None else None
        except (TypeError, ValueError):
            return None

    def _i(val) -> Optional[int]:
        try:
            return int(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    return {
        "symbol":         symbol.upper(),
        "price":          _f(price_info.get("lastPrice")),
        "change":         _f(price_info.get("change")),
        "percent_change": _f(price_info.get("pChange")),
        "open":           _f(price_info.get("open")),
        "high":           _f(intraday.get("max")),
        "low":            _f(intraday.get("min")),
        "prev_close":     _f(price_info.get("previousClose") or price_info.get("close")),
        "volume":         _i(trade_info.get("totalTradedVolume")),
        "timestamp":      datetime.datetime.utcnow().isoformat(),
        "raw_data":       raw,
    }


# ── Yahoo Finance v7 single-symbol quote (fast path) ──────────
def _yahoo_fallback(symbol: str) -> Optional[dict]:
    """
    Yahoo Finance chart API fallback — no auth required.
    Tries .NS suffix first (NSE), then .BO (BSE) for stocks not on Yahoo NS
    (e.g. SPICEJET which is only listed on Yahoo as SPICEJET.BO).
    """
    # ── chart API, try .NS then .BO (covers all listed stocks) ──
    def _parse_chart(resp_json, sym):
        result = (resp_json.get("chart", {}).get("result") or [None])[0]
        if not result: return None
        meta   = result.get("meta") or {}
        quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        ltp    = meta.get("regularMarketPrice")
        if ltp is None: return None
        prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
        ltp = float(ltp)
        change  = round(ltp - float(prev_close), 2) if prev_close else 0
        pchange = round((change / float(prev_close)) * 100, 2) if prev_close else 0
        def _last(lst):
            vals = [v for v in lst if v is not None]
            return round(float(vals[-1]), 2) if vals else None
        volumes = quotes.get("volume", [])
        return {
            "symbol":         sym.upper(),
            "price":          round(ltp, 2),
            "change":         change,
            "percent_change": pchange,
            "open":           _last(quotes.get("open",  [])),
            "high":           _last(quotes.get("high",  [])),
            "low":            _last(quotes.get("low",   [])),
            "prev_close":     round(float(prev_close), 2) if prev_close else None,
            "volume":         int(volumes[-1]) if volumes and volumes[-1] else None,
            "timestamp":      datetime.datetime.utcnow().isoformat(),
            "raw_data":       None,
        }

    for suffix in [".NS", ".BO"]:
        try:
            resp = _requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}{suffix}",
                params={"range": "2d", "interval": "1d"},
                headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip, deflate"},
                timeout=6,
            )
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            data = resp.json()
            if data.get("chart", {}).get("error"):
                continue
            result = _parse_chart(data, symbol)
            if result:
                return result
        except Exception:
            continue

    print(f"[Yahoo] All fallbacks exhausted for {symbol}")
    return None


# ── Yahoo Finance batch quote (spark API — no auth required) ─────────────────
def get_yahoo_batch(symbols: list) -> int:
    """
    Batch-fetch current quotes from Yahoo Finance spark API.
    One HTTP call for up to 50 symbols — no auth/crumb required.
    Returns count of symbols written to _quote_cache.
    Tries .NS suffix first; any missing symbols retried with .BO (e.g. SPICEJET).
    """
    if not symbols:
        return 0

    def _f(v):
        try: return round(float(v), 2) if v is not None else None
        except: return None

    def _spark_call(sym_list: list) -> dict:
        """Single spark API call → {SYMBOL.NS: {...}, ...}"""
        if not sym_list:
            return {}
        try:
            resp = _requests.get(
                "https://query1.finance.yahoo.com/v8/finance/spark",
                params={"symbols": ",".join(sym_list), "range": "1d", "interval": "1d"},
                headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip, deflate"},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json() or {}
        except Exception as e:
            print(f"[Yahoo-Batch] spark error: {e}")
            return {}

    batch = symbols[:50]
    _CHUNK = 20  # spark API limit

    # Phase A: try all with .NS, chunked to ≤20 per call
    data = {}
    for i in range(0, len(batch), _CHUNK):
        ns_syms = [f"{s}.NS" for s in batch[i:i + _CHUNK]]
        data.update(_spark_call(ns_syms))

    # Phase B: for any not found in .NS response, retry with .BO
    found_base = {k.replace(".NS", "").replace(".BO", "") for k in data}
    missing_bo = [s for s in batch if s not in found_base]
    if missing_bo:
        for i in range(0, len(missing_bo), _CHUNK):
            bo_data = _spark_call([f"{s}.BO" for s in missing_bo[i:i + _CHUNK]])
            data.update(bo_data)

    if not data:
        return 0

    now = time.time()
    updated = 0
    with _cache_lock:
        for raw_sym, item in data.items():
            sym = raw_sym.replace(".NS", "").replace(".BO", "").upper()
            if not _is_valid_symbol(sym):
                continue
            closes = item.get("close") or []
            price = _f(closes[-1]) if closes else None
            if not price or price <= 0:
                continue
            prev_close = _f(item.get("chartPreviousClose") or item.get("previousClose"))
            if prev_close and prev_close > 0:
                change     = round(price - prev_close, 2)
                pct_change = round((change / prev_close) * 100, 2)
            else:
                change, pct_change = None, None
            quote = {
                "symbol":         sym,
                "price":          price,
                "change":         change,
                "percent_change": pct_change,
                "open":           None,
                "high":           None,
                "low":            None,
                "prev_close":     prev_close,
                "volume":         None,
                "timestamp":      datetime.datetime.utcnow().isoformat(),
                "raw_data":       None,
            }
            _quote_cache[sym] = (now, quote)
            updated += 1
    return updated


# ── Public: get_quote ─────────────────────────────────────────
def get_quote(symbol: str) -> Optional[dict]:
    """
    Get live NSE quote for a symbol.
    Cache-first. On cache miss: NSE and Yahoo run in PARALLEL — returns
    whichever responds first with a valid price (usually < 500 ms).
    Never raises. Returns None if all sources fail.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed as _asc

    symbol = symbol.upper().strip().replace(".NS", "").replace(".BO", "")
    if not _is_valid_symbol(symbol):
        return None
    register_hot_symbol(symbol)

    now = time.time()
    with _cache_lock:
        entry = _quote_cache.get(symbol)
        if entry and (now - entry[0]) < QUOTE_TTL:
            return entry[1]

    # Parallel: NSE (accurate, real-time) vs Yahoo (faster, reliable fallback)
    def _nse():
        raw = _fetch_nse_quote_raw(symbol)
        if raw and isinstance(raw.get("priceInfo"), dict):
            return _normalize_quote(symbol, raw)
        return None

    result = None
    try:
        with ThreadPoolExecutor(max_workers=2) as ex:
            futures = [ex.submit(_nse), ex.submit(_yahoo_fallback, symbol)]
            for f in _asc(futures, timeout=8):
                try:
                    r = f.result()
                    if r and r.get("price") is not None and float(r.get("price", 0)) > 0:
                        result = r
                        break
                except Exception:
                    pass
    except Exception:
        pass  # TimeoutError or other — result stays None, caller handles gracefully

    with _cache_lock:
        _quote_cache[symbol] = (time.time(), result)
    return result


# ── Public: get_bulk_quotes ───────────────────────────────────
def get_bulk_quotes(symbols: list) -> dict:
    """
    Get live NSE quotes for a list of symbols.
    Returns {symbol: quote_dict_or_None}. Deduplicates input.
    Cache-first: warm hits return in < 1 ms.
    Cache misses: batch-fetched via Yahoo Finance v7 (1 HTTP call for all),
    then individual NSE calls only for any still-missing symbols.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    seen: set = set()
    unique: list = []
    for sym in symbols:
        sym = sym.upper().strip().replace(".NS", "").replace(".BO", "")
        if sym and sym not in seen:
            seen.add(sym)
            unique.append(sym)

    if not unique:
        return {}

    results: dict = {}
    now = time.time()

    # Phase 1: serve all warm cache hits instantly
    misses = []
    with _cache_lock:
        for sym in unique:
            entry = _quote_cache.get(sym)
            if entry and (now - entry[0]) < QUOTE_TTL:
                results[sym] = entry[1]
            else:
                misses.append(sym)

    if not misses:
        return results

    # Phase 2: batch-fetch all misses via Yahoo in a single HTTP call
    if len(misses) > 1:
        get_yahoo_batch(misses)
        still_missing = []
        with _cache_lock:
            for sym in misses:
                entry = _quote_cache.get(sym)
                if entry and (time.time() - entry[0]) < QUOTE_TTL:
                    results[sym] = entry[1]
                else:
                    still_missing.append(sym)
        misses = still_missing

    # Phase 3: individual parallel calls for any still-missing (NSE + Yahoo fallback)
    if misses:
        max_workers = min(10, len(misses))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(get_quote, sym): sym for sym in misses}
            for future in as_completed(futures):
                sym = futures[future]
                try:
                    results[sym] = future.result()
                except Exception as e:
                    print(f"[BulkQuotes] Error for {sym}: {e}")
                    results[sym] = None

    return results


# ── Public: get_historical ────────────────────────────────────
def get_historical(symbol: str, period: str = "1m") -> list:
    """
    Get historical price data for charting.
    period: '1d', '1w', '1m', '1y', '5y', 'max'
    Returns: [{'time': str, 'price': float}, ...]
    Never raises — returns [] on failure.
    """
    symbol = symbol.upper().strip().replace(".NS", "").replace(".BO", "")
    if not _is_valid_symbol(symbol):
        return []
    register_hot_symbol(symbol)

    cache_key = f"{symbol}_{period}"
    now = time.time()

    # Use a shorter TTL for intraday data while the market is live
    if period == '1d':
        try:
            from services.market_hours import is_market_open
            _ttl = HIST_TTL_1D_OPEN if is_market_open() else HIST_TTL_1D_CLOSED
        except Exception:
            _ttl = HIST_TTL
    else:
        _ttl = HIST_TTL

    with _cache_lock:
        entry = _hist_cache.get(cache_key)
        if entry and (now - entry[0]) < _ttl:
            return entry[1]

    _period_map = {
        "1d": ("1d",  "5m"),
        "1w": ("5d",  "60m"),
        "1m": ("1mo", "1d"),
        "5y": ("5y",  "1d"),
        "max": ("max", "1wk"),
    }
    _, interval = _period_map.get(period, ("1mo", "1d"))

    # Use direct Yahoo Finance chart API (avoids yfinance Brotli issues)
    _range_map = {"1d": "1d", "1w": "5d", "1m": "1mo", "1y": "1y", "5y": "5y", "max": "max"}
    yf_range = _range_map.get(period, "1mo")

    def _parse_hist(resp_data, sym, prd):
        chart = resp_data.get("chart") or {}
        res   = (chart.get("result") or [None])[0]
        if not res:
            return []
        timestamps = res.get("timestamp") or []
        closes     = ((res.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
        items = []
        for ts, c in zip(timestamps, closes):
            if c is None:
                continue
            try:
                t = datetime.datetime.fromtimestamp(ts, tz=_IST)
                label = t.strftime("%Y-%m-%dT%H:%M") if prd == "1d" else str(t.date())
                items.append({"time": label, "price": round(float(c), 2)})
            except Exception:
                continue
        if prd == "5y":
            return _downsample_points(items, max_points=1250)
        if prd == "max":
            return _downsample_points(items, max_points=1500)
        return items

    result = []
    for suffix in [".NS", ".BO"]:
        try:
            resp = _requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}{suffix}",
                params={"range": yf_range, "interval": interval},
                headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip, deflate"},
                timeout=10,
            )
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            parsed = _parse_hist(resp.json(), symbol, period)
            if parsed:
                result = parsed
                break
        except Exception as e:
            print(f"[Historical] Error for {symbol}{suffix} period={period}: {e}")
            continue

    with _cache_lock:
        _hist_cache[cache_key] = (time.time(), result)
    return result


# ── Symbol extraction from free text ─────────────────────────
def extract_symbols_from_text(text: str) -> list:
    """
    Extract potential NSE ticker symbols from free text.
    Input is uppercased before matching so 'reliance' → 'RELIANCE'.
    Returns list of candidate symbols (may be empty).
    """
    import re
    upper = text.upper()
    candidates = re.findall(r'\b([A-Z][A-Z0-9]{1,9})\b', upper)
    return [c for c in candidates if c not in _STOPWORDS]
