# backend/services/advanced_analytics.py
import yfinance as yf
import pandas as pd
import time as _time
from datetime import datetime, timedelta
import json
from services.indicators import add_ns_suffix, compute_rsi_manual
from services.news_fetcher import get_stock_news
from services.gpt import groq_call, load_prompt, parse_json_response
from database import db_fetchall

SECTORS = {
    "RELIANCE": "Energy", "TCS": "IT", "INFY": "IT", "HDFCBANK": "Banking",
    "ICICIBANK": "Banking", "TATAMOTORS": "Auto", "WIPRO": "IT", "BAJFINANCE": "NBFC",
    "SUNPHARMA": "Pharma", "ITC": "FMCG", "SBIN": "Banking", "ADANIENT": "Infrastructure",
    "MARUTI": "Auto", "NESTLEIND": "FMCG", "POWERGRID": "Energy",
    # Extended
    "AXISBANK": "Banking", "KOTAKBANK": "Banking", "INDUSINDBK": "Banking",
    "HCLTECH": "IT", "TECHM": "IT", "LTIM": "IT", "MPHASIS": "IT",
    "DRREDDY": "Pharma", "CIPLA": "Pharma", "DIVISLAB": "Pharma", "LUPIN": "Pharma",
    "BAJAJFINSV": "NBFC", "MUTHOOTFIN": "NBFC", "CHOLAFIN": "NBFC",
    "NTPC": "Energy", "ONGC": "Energy", "BPCL": "Energy", "IOC": "Energy",
    "TATASTEEL": "Metals", "JSWSTEEL": "Metals", "HINDALCO": "Metals", "COALINDIA": "Metals",
    "HINDUNILVR": "FMCG", "BRITANNIA": "FMCG", "DABUR": "FMCG", "MARICO": "FMCG",
    "ULTRACEMCO": "Cement", "SHREECEM": "Cement", "AMBUJACEM": "Cement",
    "BHARTIARTL": "Telecom", "TITAN": "Consumer", "ASIANPAINT": "Paints",
    "LT": "Infrastructure", "ADANIPORTS": "Infrastructure",
    "APOLLOHOSP": "Healthcare", "DIVISLAB": "Pharma",
    "SBILIFE": "Insurance", "HDFCLIFE": "Insurance",
    "EICHERMOT": "Auto", "HEROMOTOCO": "Auto", "BAJAJ-AUTO": "Auto",
}

# ── In-memory backtest cache (24 h TTL) ───────────────────────────────────────
_backtest_cache: dict = {}
_BACKTEST_CACHE_TTL = 24 * 3600  # seconds


def _cache_get(key: str):
    entry = _backtest_cache.get(key)
    if entry and (_time.time() - entry["ts"]) < _BACKTEST_CACHE_TTL:
        return entry["result"]
    return None


def _cache_set(key: str, result: dict):
    _backtest_cache[key] = {"result": result, "ts": _time.time()}


def get_pattern_success_rate(symbol: str, signal_type: str) -> dict:
    """
    Back-tests a signal over 2 years of daily data.
    Returns the % of times the stock was higher 5 days after the signal triggered.
    Results are cached in-memory for 24 hours so demo clicks are instant.
    """
    cache_key = f"{symbol.upper()}:{signal_type}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    ns_symbol = add_ns_suffix(symbol)
    try:
        ticker = yf.Ticker(ns_symbol)
        hist = ticker.history(period="2y")
        if hist.empty:
            result = {"error": "No data found", "symbol": symbol, "win_rate": None, "occurrences": 0}
            _cache_set(cache_key, result)
            return result

        close = hist["Close"]
        occurrences = 0
        successes = 0

        if signal_type.lower() == "rsi < 30":
            rsi = compute_rsi_manual(close, 14)
            for i in range(14, len(rsi) - 5):
                if rsi.iloc[i - 1] >= 30 and rsi.iloc[i] < 30:
                    occurrences += 1
                    if close.iloc[i + 5] > close.iloc[i]:
                        successes += 1
        else:
            ema20 = close.ewm(span=20, adjust=False).mean()
            ema50 = close.ewm(span=50, adjust=False).mean()
            for i in range(50, len(close) - 5):
                if ema20.iloc[i - 1] <= ema50.iloc[i - 1] and ema20.iloc[i] > ema50.iloc[i]:
                    occurrences += 1
                    if close.iloc[i + 5] > close.iloc[i]:
                        successes += 1

        win_rate = (successes / occurrences * 100) if occurrences > 0 else 0
        result = {
            "symbol": symbol,
            "signal_type": signal_type,
            "occurrences": occurrences,
            "win_rate": round(win_rate, 2),
            "successes": successes,
        }
        _cache_set(cache_key, result)
        return result
    except Exception as e:
        print(f"[Analytics] Error in get_pattern_success_rate for {symbol}: {e}")
        result = {"error": str(e), "symbol": symbol, "win_rate": None, "occurrences": 0}
        _cache_set(cache_key, result)
        return result

_clusters_cache: dict = {}
_CLUSTERS_TTL = 5 * 60  # 5 minutes


def get_institutional_clusters() -> dict:
    """
    Queries bulk_deals within the last 30 days.
    Groups by sector, flags if >= 2 different institutions entered same sector.
    Cached in-memory for 5 minutes.
    """
    cached = _clusters_cache.get('clusters')
    if cached and (_time.time() - cached['ts']) < _CLUSTERS_TTL:
        return cached['data']

    try:
        cutoff_dt = datetime.utcnow() - timedelta(days=30)
        cutoff_str = cutoff_dt.strftime('%Y-%m-%d %H:%M:%S')
        cutoff_date = cutoff_dt.strftime('%Y-%m-%d')
        deals = db_fetchall(
            "SELECT symbol, client_name, deal_type FROM bulk_deals WHERE fetched_at >= ? OR deal_date >= ?",
            (cutoff_str, cutoff_date)
        )

        sector_institutions = {}
        for d in deals:
            sym = d["symbol"].upper().replace(".NS", "")
            sector = SECTORS.get(sym, "Other")
            client = d.get("client_name", "Unknown")
            if sector not in sector_institutions:
                sector_institutions[sector] = set()
            sector_institutions[sector].add(client)

        clusters = []
        for sector, clients in sorted(sector_institutions.items(), key=lambda x: -len(x[1])):
            if len(clients) >= 2:
                clusters.append({
                    "sector": sector,
                    "institution_count": len(clients),
                    "flag": "High Conviction Sector Cluster",
                    "clients": list(clients)[:5]
                })

        result = {"clusters": clusters}
        _clusters_cache['clusters'] = {'data': result, 'ts': _time.time()}
        return result
    except Exception as e:
        print(f"[Analytics] Error in get_institutional_clusters: {e}")
        return {"error": str(e), "clusters": []}

def analyze_management_tone(symbol: str) -> dict:
    """
    Fetches news/commentary and uses GPT to compare sentiment tone shift.
    """
    docs = get_stock_news(symbol, max_age_minutes=60*24*7) # Look back a week to get enough articles
    snippets = [n["headline"] for n in docs[:4]] if docs else []
    
    _fallback = {
        "symbol": symbol,
        "tone_shift_score": 0.0,
        "explanation": "Not enough news data to determine management tone shift."
    }
    
    if not snippets:
        return _fallback
        
    try:
        prompt_template = load_prompt("tone.txt")
        if not prompt_template:
            prompt_template = "Analyze the tone shift from these news snippets: {news_snippets}. Return JSON with 'tone_shift_score' (-1.0 to 1.0) and 'explanation'."
            
        prompt = prompt_template.format(news_snippets=json.dumps(snippets, indent=2))
        raw = groq_call(prompt, json_mode=True, max_tokens=256)
        
        parsed = parse_json_response(raw, fallback=_fallback)
        parsed["symbol"] = symbol
        return parsed
    except Exception as e:
        print(f"[Analytics] Error in analyze_management_tone for {symbol}: {e}")
        return _fallback
