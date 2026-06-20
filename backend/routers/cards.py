# backend/routers/cards.py
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
import math
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from database import db_fetchone, db_execute
from services.indicators import get_stock_data
from services.news_fetcher import get_stock_news
from services.gpt import generate_signal_card
from services.nse_service import get_quote, get_historical
from services.symbol_resolver import normalize_symbol

router = APIRouter()

_MAX_SYMBOL_LEN = 10
_FALLBACK_SNAPSHOT = 'Technical analysis unavailable.'

# ── In-memory L1 card cache ───────────────────────────────────
# Hot path: sub-millisecond for symbols warmed by scheduler or recent requests.
# L1 (RAM) → L2 (SQLite) → fresh fetch + AI
_mem_card: dict = {}           # symbol → {'card': dict, 'ts': float}
_MEM_CARD_TTL = 15 * 60        # 15 min — mirrors DB cache TTL
_mem_lock = threading.Lock()

def _mem_get(symbol: str):
    with _mem_lock:
        e = _mem_card.get(symbol)
        if e and (time.time() - e['ts']) < _MEM_CARD_TTL:
            return e['card']
        _mem_card.pop(symbol, None)
        return None

def _mem_set(symbol: str, card: dict):
    """Write card to L1 cache. Called by endpoint and by scheduler prefetch."""
    with _mem_lock:
        _mem_card[symbol] = {'card': card, 'ts': time.time()}


def _rule_based_snapshot(stock_data: dict) -> str:
    """
    Generate a data-driven technical snapshot from all available indicators.
    Gracefully handles partial data — always returns a meaningful 1-3 sentence analysis.
    Priority: RSI → EMA signal → SMA-200 → 52W range → price action fallback.
    """
    sentences = []

    rsi        = stock_data.get('rsi')
    ema_signal = stock_data.get('ema_signal', '')
    ema20      = stock_data.get('ema20')
    ema50      = stock_data.get('ema50')
    sma200     = stock_data.get('sma200')
    price      = stock_data.get('current_price')
    prev_close = stock_data.get('prev_close')
    open_price = stock_data.get('open')
    day_high   = stock_data.get('high')
    day_low    = stock_data.get('low')
    high_52w   = stock_data.get('high_52w')
    low_52w    = stock_data.get('low_52w')
    volume     = stock_data.get('volume')
    avg_vol    = stock_data.get('avg_volume') or stock_data.get('avg_volume_20d')

    # 1. RSI — most actionable momentum signal
    if rsi is not None:
        try:
            rsi_val = round(float(rsi), 1)
            if rsi_val >= 70:
                sentences.append(
                    f'RSI at {rsi_val} is in overbought territory — buying momentum may be exhausting and a short-term pullback risk is elevated.'
                )
            elif rsi_val <= 30:
                sentences.append(
                    f'RSI at {rsi_val} is oversold — the stock may be approaching a potential mean-reversion bounce.'
                )
            elif rsi_val >= 60:
                sentences.append(
                    f'RSI at {rsi_val} reflects positive momentum building without hitting overbought extremes.'
                )
            elif rsi_val <= 40:
                sentences.append(
                    f'RSI at {rsi_val} reflects weakening momentum; watch for continued softening.'
                )
            else:
                sentences.append(
                    f'RSI at {rsi_val} sits in neutral territory, showing no strong directional bias.'
                )
        except (TypeError, ValueError):
            pass

    # 2. EMA crossover signal — trend direction
    if ema_signal:
        sig = ema_signal.lower()
        e20_str = f' (EMA-20: ₹{round(float(ema20)):,})' if ema20 else ''
        e50_str = f' above EMA-50 (₹{round(float(ema50)):,})' if ema50 else ''
        try:
            if 'bullish_crossover' in sig:
                sentences.append(
                    f'EMA-20 has freshly crossed above EMA-50{e20_str} — a golden cross forming a short-term bullish crossover.'
                )
            elif 'bearish_crossover' in sig:
                sentences.append(
                    f'EMA-20 has just crossed below EMA-50 — a death cross forming a short-term bearish crossover, warranting caution.'
                )
            elif 'bullish' in sig:
                sentences.append(
                    f'EMA-20 is trading{e20_str}{e50_str if ema50 else " above EMA-50"} — sustained short-term bullish momentum.'
                )
            elif 'bearish' in sig:
                sentences.append(
                    f'EMA-20 is below EMA-50{e20_str} — reflecting short-term downward pressure.'
                )
        except (TypeError, ValueError):
            pass

    # 3. SMA-200 — long-term structural view
    if sma200 is not None and price is not None:
        try:
            is_above = float(price) >= float(sma200)
            direction = 'above' if is_above else 'below'
            bias      = 'long-term bullish structure' if is_above else 'long-term bearish structure'
            sentences.append(
                f'Price is {direction} its 200-day SMA (₹{round(float(sma200)):,}), indicating {bias}.'
            )
        except (TypeError, ValueError):
            pass

    # 4. 52-week range position
    if price is not None and high_52w is not None and low_52w is not None:
        try:
            p, h, l = float(price), float(high_52w), float(low_52w)
            rng = h - l
            if rng > 0:
                pos = (p - l) / rng * 100
                if pos >= 85:
                    sentences.append(
                        f'Trading at {round(pos)}% of its 52-week range, near the annual high of ₹{h:,.0f} — limited upside buffer.'
                    )
                elif pos <= 15:
                    sentences.append(
                        f'Trading at only {round(pos)}% of its 52-week range, near the annual low of ₹{l:,.0f} — a potential support zone.'
                    )
                else:
                    sentences.append(
                        f'Price sits at {round(pos)}% of its 52-week range (₹{l:,.0f}–₹{h:,.0f}).'
                    )
        except (TypeError, ValueError):
            pass

    # If we have 2+ indicator sentences, return top 3 — done.
    if len(sentences) >= 2:
        # Optionally append volume if it's significantly unusual
        if volume is not None and avg_vol is not None and len(sentences) < 3:
            try:
                ratio = float(volume) / float(avg_vol)
                if ratio >= 2.0:
                    sentences.append(f'Volume is {ratio:.1f}x the average — unusually high activity signals possible institutional accumulation.')
                elif ratio <= 0.4:
                    sentences.append(f'Volume is only {ratio:.1f}x average, indicating limited market conviction.')
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        return ' '.join(sentences[:3])

    # 5. Price action fallback — when no historical indicator data is available
    if price is not None and prev_close is not None:
        try:
            chg_pct   = ((float(price) - float(prev_close)) / float(prev_close)) * 100
            direction = 'up' if chg_pct >= 0 else 'down'
            strength  = 'sharply ' if abs(chg_pct) > 2 else ''
            sentences.append(
                f'Stock is {strength}{direction} {abs(chg_pct):.2f}% from previous close of ₹{float(prev_close):,.2f}.'
            )
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    if price is not None and day_high is not None and day_low is not None:
        try:
            intra_range = float(day_high) - float(day_low)
            if float(day_low) > 0:
                intra_pct = (intra_range / float(day_low)) * 100
                sentences.append(
                    f'Intraday range spans ₹{float(day_low):,.2f}–₹{float(day_high):,.2f} ({intra_pct:.1f}% spread).'
                )
        except (TypeError, ValueError):
            pass

    if price is not None and open_price is not None:
        try:
            gap_pct = ((float(price) - float(open_price)) / float(open_price)) * 100
            if abs(gap_pct) > 0.5:
                direction = 'above' if gap_pct > 0 else 'below'
                sentences.append(
                    f'Currently trading {abs(gap_pct):.2f}% {direction} today\'s open (₹{float(open_price):,.2f}).'
                )
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    if volume is not None and avg_vol is not None:
        try:
            ratio = float(volume) / float(avg_vol)
            if ratio >= 1.5:
                sentences.append(f'Volume at {ratio:.1f}x average, signalling elevated institutional activity.')
            elif ratio <= 0.5:
                sentences.append(f'Volume is light at {ratio:.1f}x average, showing limited market conviction.')
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    if sentences:
        return ' '.join(sentences[:3])

    if price is not None:
        return (
            f'Live price available at ₹{float(price):,.2f} but insufficient historical data '
            f'to compute RSI, EMA crossovers, or SMA-200 — check NSE for full chart history.'
        )
    return 'Insufficient market data available. Please check NSE directly for current technical levels.'


# ── Parallel fetch helpers ────────────────────────────────────
def _fetch_yfinance(symbol: str) -> dict:
    try:
        result = get_stock_data(symbol)
        return result if 'error' not in result else {'symbol': symbol}
    except Exception as e:
        print(f'[Cards] yfinance error for {symbol}: {e}')
        return {'symbol': symbol}

def _fetch_nse_quote(symbol: str) -> dict:
    try:
        q = get_quote(symbol)
        return q or {}
    except Exception as e:
        print(f'[Cards] NSE quote error for {symbol}: {e}')
        return {}

def _fetch_news(symbol: str) -> list:
    try:
        return get_stock_news(symbol) or []
    except Exception as e:
        print(f'[Cards] News error for {symbol}: {e}')
        return []

def _fetch_intraday(symbol: str) -> list:
    try:
        return get_historical(symbol, '1d') or []
    except Exception as e:
        print(f'[Cards] Intraday error for {symbol}: {e}')
        return []


def _fetch_history(symbol: str, period: str) -> list:
    try:
        return get_historical(symbol, period) or []
    except Exception as e:
        print(f'[Cards] History error for {symbol} period={period}: {e}')
        return []


@router.get('/card/{symbol}')
def get_signal_card(symbol: str, force_refresh: bool = False):
    """
    Returns an AI-generated NSE Signal Card for a given stock ticker.
    Cache TTL: 15 minutes. Use force_refresh=true to bypass cache.
    All data fetches (yfinance, NSE quote, news, intraday) run in parallel.
    """
    symbol = normalize_symbol(symbol)
    if not symbol or len(symbol) > _MAX_SYMBOL_LEN:
        return JSONResponse(
            status_code=400,
            content={
                'success': False,
                'data': None,
                'error': f'Invalid symbol. Must be 1-{_MAX_SYMBOL_LEN} characters.',
            },
        )

    # ── L1 cache check (sub-ms RAM hit) ─────────────────────
    if not force_refresh:
        mem = _mem_get(symbol)
        if mem is not None:
            return {'success': True, 'data': {'cached': True, 'card': mem}, 'error': None}

    # ── L2 cache check (SQLite) ──────────────────────────────
    if not force_refresh:
        try:
            cached = db_fetchone(
                'SELECT card_json, expires_at FROM card_cache WHERE symbol=?',
                (symbol,)
            )
            if cached and cached['expires_at'] > datetime.utcnow().isoformat():
                card_obj = json.loads(cached['card_json'])
                _mem_set(symbol, card_obj)   # promote DB hit → L1
                return {
                    'success': True,
                    'data': {'cached': True, 'card': card_obj},
                    'error': None,
                }
        except Exception as e:
            print(f'[Cards] Cache read error for {symbol}: {e}')

    # ── Parallel fetch: yfinance + NSE quote + news + intraday + long-range history ─
    # All 4 sources run concurrently — reduces wall time from ~sum to ~max
    stock_data   = {'symbol': symbol}
    nse_quote    = {}
    news         = []
    intraday     = []
    hist_5y      = []
    hist_max     = []

    with ThreadPoolExecutor(max_workers=6) as ex:
        f_yf       = ex.submit(_fetch_yfinance,  symbol)
        f_quote    = ex.submit(_fetch_nse_quote, symbol)
        f_news     = ex.submit(_fetch_news,      symbol)
        f_intraday = ex.submit(_fetch_intraday,  symbol)
        f_5y       = ex.submit(_fetch_history,   symbol, '5y')
        f_max      = ex.submit(_fetch_history,   symbol, 'max')

        # Collect each independently — one slow/failed source doesn't block others
        try:
            stock_data = f_yf.result(timeout=15)
        except Exception as e:
            print(f'[Cards] yfinance timeout/error for {symbol}: {e}')
            stock_data = {'symbol': symbol}
        try:
            nse_quote  = f_quote.result(timeout=10)
        except Exception as e:
            print(f'[Cards] NSE quote timeout/error for {symbol}: {e}')
            nse_quote = {}
        try:
            news       = f_news.result(timeout=10)
        except Exception as e:
            print(f'[Cards] News timeout/error for {symbol}: {e}')
            news = []
        try:
            intraday   = f_intraday.result(timeout=10)
        except Exception as e:
            print(f'[Cards] Intraday timeout/error for {symbol}: {e}')
            intraday = []
        try:
            hist_5y    = f_5y.result(timeout=12)
        except Exception as e:
            print(f'[Cards] 5Y history timeout/error for {symbol}: {e}')
            hist_5y = []
        try:
            hist_max   = f_max.result(timeout=14)
        except Exception as e:
            print(f'[Cards] Max history timeout/error for {symbol}: {e}')
            hist_max = []

    # ── Merge NSE live quote over yfinance data ───────────────
    if nse_quote:
        for src_key, dst_key in [
            ('price',          'current_price'),
            ('percent_change', 'change_pct'),
            ('open',           'open'),
            ('high',           'high'),
            ('low',            'low'),
            ('prev_close',     'prev_close'),
            ('volume',         'volume'),
        ]:
            if nse_quote.get(src_key) is not None:
                stock_data[dst_key] = nse_quote[src_key]

    # ── Indicator enrichment: if yfinance returned no RSI/EMA, retry get_stock_data ──
    # This happens when fetch_close_series has < 50 bars but still has a live price.
    if stock_data.get('rsi') is None and stock_data.get('ema20') is None:
        try:
            _tech = get_stock_data(symbol)
            if 'error' not in _tech:
                for _k in ('rsi', 'rsi_zone', 'ema20', 'ema50', 'sma200',
                           'ema_signal', 'high_52w', 'low_52w', 'avg_volume_20d',
                           'price_30d', 'dates_30d'):
                    if _tech.get(_k) is not None:
                        stock_data[_k] = _tech[_k]
        except Exception:
            pass

    # ── Guard: if price unavailable, build a limited card rather than hard-fail ──
    cp = stock_data.get('current_price')
    _price_unavailable = cp is None or (isinstance(cp, float) and math.isnan(cp)) or (isinstance(cp, (int, float)) and cp <= 0)
    if _price_unavailable:
        stock_data['current_price'] = None
        stock_data.setdefault('change_pct', None)
        # Provide a minimal fallback card so the UI shows something useful
        limited_card = {
            'symbol':              symbol,
            'sentiment':           'neutral',
            'sentiment_score':     50,
            'sentiment_reason':    f'Live price data for {symbol} is temporarily unavailable (low liquidity / trading halt). Analysis based on available data only.',
            'technical_snapshot':  f'Price feed unavailable for {symbol}. This may be due to trading suspension, very low liquidity, or a data provider outage. Check NSE directly for current status.',
            'news_impact_score':   50,
            'news_impact_summary': 'Unable to cross-reference news impact without a current price.',
            'risk_flags':          ['Price data unavailable — exercise caution'],
            'actionable_context':  f'Verify {symbol} trading status on NSE before acting. Stock may be suspended or illiquid.',
            'disclaimer':          'For educational purposes only. Not financial advice.',
            'current_price':       None,
            'change_pct':          None,
            'price_30d':           [],
            'dates_30d':           [],
            'news':                [{'headline': n['headline'], 'source': n['source'], 'url': n.get('url', '')} for n in news[:5]],
            'trends':              {'1d': [], '1w': [], '1m': [], '5y': [], 'max': []},
        }
        _mem_set(symbol, limited_card)
        return {'success': True, 'data': {'cached': False, 'card': limited_card}, 'error': None}

    # ── AI card generation ────────────────────────────────────
    try:
        card = generate_signal_card(symbol, stock_data, news)
    except Exception as e:
        print(f'[Cards] Generation failed for {symbol}: {e}')
        card = {
            'symbol':              symbol,
            'sentiment':           'neutral',
            'sentiment_score':     50,
            'sentiment_reason':    'Analysis temporarily unavailable.',
            'technical_snapshot':  'Technical analysis unavailable.',
            'news_impact_score':   50,
            'news_impact_summary': 'News data unavailable.',
            'risk_flags':          [],
            'actionable_context':  'Please check NSE and ET Markets directly.',
            'disclaimer':          'For educational purposes only. Not financial advice.',
        }
        news = []

    # ── Rule-based snapshot fallback ─────────────────────────
    # Triggers when AI is unavailable, returns a generic placeholder, or produces
    # text containing "unavailable", "insufficient", "unable", or "cannot".
    _snap = (card.get('technical_snapshot') or '').strip()
    _snap_lower = _snap.lower()
    _needs_fallback = (
        not _snap
        or _snap == _FALLBACK_SNAPSHOT
        or 'unavailable' in _snap_lower
        or 'insufficient' in _snap_lower
        or 'unable to' in _snap_lower
        or 'cannot' in _snap_lower
        or len(_snap) < 40          # suspiciously short — probably a placeholder
    )
    if _needs_fallback:
        card['technical_snapshot'] = _rule_based_snapshot(stock_data)

    # ── Enrich card ───────────────────────────────────────────
    card['symbol']        = symbol
    card['current_price'] = stock_data.get('current_price')
    card['change_pct']    = stock_data.get('change_pct')
    card['open']          = stock_data.get('open')
    card['high']          = stock_data.get('high')
    card['low']           = stock_data.get('low')
    card['prev_close']    = stock_data.get('prev_close')
    card['volume']        = stock_data.get('volume')
    card['rsi']           = stock_data.get('rsi')
    card['ema_signal']    = stock_data.get('ema_signal')
    card['rsi_zone']      = stock_data.get('rsi_zone')
    card['ema20']         = stock_data.get('ema20')
    card['ema50']         = stock_data.get('ema50')
    card['sma200']        = stock_data.get('sma200')
    card['high_52w']      = stock_data.get('high_52w')
    card['low_52w']       = stock_data.get('low_52w')
    card['price_data_quality'] = stock_data.get('price_data_quality')
    card['price_source']  = stock_data.get('price_source')
    card['price_timestamp'] = stock_data.get('price_timestamp')
    card['price_30d']     = stock_data.get('price_30d', [])
    card['dates_30d']     = stock_data.get('dates_30d', [])
    card['news']          = [
        {'headline': n['headline'], 'source': n['source'], 'url': n.get('url', '')}
        for n in news[:5]
    ]

    # ── Trend datasets ────────────────────────────────────────
    dates  = stock_data.get('dates_30d', [])
    prices = stock_data.get('price_30d', [])
    trends = {
        '1m': [{'time': d, 'price': p} for d, p in zip(dates, prices)],
        '1w': [{'time': d, 'price': p} for d, p in zip(dates[-7:], prices[-7:])],
        # Keep 1D strictly intraday to avoid showing week-like x-axis under 1D tab.
        '1d': intraday if len(intraday) >= 2 else [],
        '5y': hist_5y,
        'max': hist_max,
    }
    card['trends'] = trends

    # ── Save to L1 (RAM) + L2 (SQLite), 15-min TTL ──────────
    _mem_set(symbol, card)
    try:
        expires = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
        db_execute(
            'INSERT OR REPLACE INTO card_cache (symbol, card_json, expires_at) VALUES (?,?,?)',
            (symbol, json.dumps(card), expires)
        )
    except Exception as e:
        print(f'[Cards] Cache write error for {symbol}: {e}')

    return {'success': True, 'data': {'cached': False, 'card': card}, 'error': None}
