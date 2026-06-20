# backend/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import os, logging
import time
import threading
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)
logger    = logging.getLogger('[Scheduler]')
scheduler = BackgroundScheduler()
_live_cursor = 0

# Exposed to the frontend via `/api/health` for first-run seeding UX.
_WARMUP_STATE: Dict[str, Any] = {
    "active": False,
    "stage": "",
    "progress": 0,
    "started_at": None,
    "updated_at": None,
}
_WARMUP_LOCK = threading.Lock()


def get_warmup_state() -> Dict[str, Any]:
    with _WARMUP_LOCK:
        return dict(_WARMUP_STATE)


def _set_warmup_state(**patch: Any) -> None:
    with _WARMUP_LOCK:
        _WARMUP_STATE.update(patch)
        _WARMUP_STATE["updated_at"] = time.time()


def warmup_seed_if_needed() -> None:
    """
    First-run developer/demo experience:
    - If `signals` is empty, fetch last 7 days of NSE bulk/block deals.
    - Generate initial signals (up to 10 deal-derived signals).
    - If still empty, generate synthetic signals for top popular stocks.
    """
    from database import db_fetchone, db_fetchall, db_execute
    from services.nse_fetcher import (
        fetch_bulk_deals_lookback,
        fetch_block_deals_lookback,
        save_bulk_deals_to_db,
    )
    from services.indicators import POPULAR_STOCKS, get_stock_data
    from services.news_fetcher import get_stock_news
    from services.gpt import explain_signal

    # If we already have signals, do nothing.
    row = db_fetchone("SELECT COUNT(*) as cnt FROM signals")
    if row and int(row.get("cnt") or 0) > 0:
        return

    _set_warmup_state(active=True, stage="initializing", progress=0, started_at=time.time())
    logger.info("[Warmup] No signals found — warming up radar data...")

    # 1) Fetch last 7 days of deals.
    _set_warmup_state(stage="fetching_deals", progress=10)
    deals = fetch_bulk_deals_lookback(7) + fetch_block_deals_lookback(7)
    _set_warmup_state(stage="saving_deals", progress=25)
    saved = save_bulk_deals_to_db(deals)
    logger.info(f"[Warmup] Saved {saved} deals")

    # 2) Generate AI/rule-based signals for unsignalled deals.
    _set_warmup_state(stage="generating_signals", progress=40)
    unsignalled = db_fetchall(
        '''SELECT bd.* FROM bulk_deals bd
           LEFT JOIN signals s ON s.deal_id = bd.id
           WHERE s.id IS NULL
           ORDER BY bd.quantity DESC
           LIMIT 10'''
    )
    generated = 0
    for deal in unsignalled:
        try:
            stock = get_stock_data(deal["symbol"])
            if "error" in stock:
                continue
            signal = explain_signal(deal, stock)
            db_execute(
                '''INSERT INTO signals
                   (deal_id, symbol, explanation, signal_type, risk_level,
                    confidence, key_observation, disclaimer, ai_provider)
                   VALUES (?,?,?,?,?,?,?,?,?)''',
                (
                    deal["id"],
                    deal["symbol"],
                    signal.get("explanation", ""),
                    signal.get("signal_type", "neutral"),
                    signal.get("risk_level", "medium"),
                    signal.get("confidence", 50),
                    signal.get("key_observation", ""),
                    signal.get("disclaimer", "For educational purposes only. Not financial advice."),
                    signal.get("ai_provider"),
                ),
            )
            generated += 1
            if generated >= 10:
                break
            _set_warmup_state(progress=min(85, 40 + generated * 5))
            time.sleep(1.2)
        except Exception as e:
            logger.error(f"[Warmup] Error processing deal {deal.get('id')}: {e}")
            continue

    # 3) Still nothing? Create synthetic signals for popular stocks.
    if generated == 0:
        _set_warmup_state(stage="synthetic_popular_signals", progress=70)
        # Top 10 popular symbols (already used elsewhere for card prefetch).
        popular_symbols = [s.replace(".NS", "")[:10] for s in POPULAR_STOCKS[:10]]
        for i, sym in enumerate(popular_symbols):
            try:
                stock = get_stock_data(sym)
                if "error" in stock:
                    continue
                price = stock.get("current_price") or 0
                deal_id = db_execute(
                    '''INSERT INTO bulk_deals
                       (symbol, client_name, deal_type, quantity, price, deal_date)
                       VALUES (?,?,?,?,?,?)''',
                    (
                        sym,
                        "Market Intelligence",
                        "B",
                        0,
                        float(price) if price else 0.0,
                        time.strftime("%Y-%m-%d"),
                    ),
                )
                deal = {
                    "id": deal_id,
                    "symbol": sym,
                    "deal_type": "B",
                    "quantity": 0,
                    "price": price,
                    "deal_date": time.strftime("%Y-%m-%d"),
                    "client_name": "Market Intelligence",
                }
                signal = explain_signal(deal, stock)
                db_execute(
                    '''INSERT INTO signals
                       (deal_id, symbol, explanation, signal_type, risk_level,
                        confidence, key_observation, disclaimer, ai_provider)
                       VALUES (?,?,?,?,?,?,?,?,?)''',
                    (
                        deal_id,
                        sym,
                        signal.get("explanation", ""),
                        signal.get("signal_type", "neutral"),
                        signal.get("risk_level", "medium"),
                        signal.get("confidence", 50),
                        signal.get("key_observation", ""),
                        signal.get("disclaimer", "For educational purposes only. Not financial advice."),
                        signal.get("ai_provider"),
                    ),
                )
                generated += 1
                _set_warmup_state(progress=min(95, 70 + i * 3))
                time.sleep(0.8)
            except Exception as e:
                logger.error(f"[Warmup] Synthetic signal failed for {sym}: {e}")
                continue

    _set_warmup_state(active=False, stage="done", progress=100)
    logger.info(f"[Warmup] Done. Signals generated: {generated}")

# All 50 movers symbols kept hot in the quote cache during market hours.
# Matches _SYMBOLS in routers/market.py — update both together.
_LIVE_SYMBOLS = [
    'RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK',
    'TATAMOTORS', 'WIPRO', 'BAJFINANCE', 'SUNPHARMA', 'ITC',
    'SBIN', 'ADANIENT', 'MARUTI', 'BHARTIARTL', 'AXISBANK',
    'KOTAKBANK', 'LT', 'HCLTECH', 'TITAN', 'ONGC',
    'NTPC', 'JSWSTEEL', 'TATASTEEL', 'DRREDDY', 'CIPLA',
    'EICHERMOT', 'HEROMOTOCO', 'BPCL', 'HINDALCO', 'COALINDIA',
    'ULTRACEMCO', 'TECHM', 'BAJAJFINSV', 'ASIANPAINT', 'NESTLEIND',
    'POWERGRID', 'DIVISLAB', 'GRASIM', 'INDUSINDBK', 'TATACONSUM',
    'BRITANNIA', 'APOLLOHOSP', 'SHREECEM', 'SBILIFE', 'HDFCLIFE',
    'PIDILITIND', 'DABUR', 'BERGEPAINT', 'MARICO', 'MUTHOOTFIN',
]


def run_radar_job():
    """
    The Opportunity Radar core loop — runs every RADAR_INTERVAL_HOURS (default 1h).
    Fetches NSE deals → saves → generates AI signals for unsignalled deals.
    Max 10 signals per run. Each deal wrapped in its own try/except.
    """
    logger.info('Radar job started')
    try:
        from services.nse_fetcher import fetch_bulk_deals, fetch_block_deals, save_bulk_deals_to_db
        from services.indicators import get_stock_data
        from services.gpt import explain_signal
        from database import db_fetchall, db_execute

        bulk = fetch_bulk_deals()
        block = fetch_block_deals()
        deals = bulk + block
        logger.info(f'Fetched {len(deals)} deals from NSE (bulk={len(bulk)}, block={len(block)})')

        # If NSE live endpoints return nothing (common on weekends/holidays),
        # do a 7-day lookback so the radar stays populated.
        if not deals:
            logger.info('[Radar] No deals from live endpoints — using 7-day lookback')
            from services.nse_fetcher import fetch_bulk_deals_lookback, fetch_block_deals_lookback
            deals = fetch_bulk_deals_lookback(7) + fetch_block_deals_lookback(7)
            logger.info(f'[Radar] Lookback fetched {len(deals)} deals')

        new_count = save_bulk_deals_to_db(deals)
        logger.info(f'Saved {new_count} new deals to DB')

        unsignalled = db_fetchall(
            '''SELECT bd.* FROM bulk_deals bd
               LEFT JOIN signals s ON s.deal_id = bd.id
               WHERE s.id IS NULL
               ORDER BY bd.quantity DESC
               LIMIT 10'''
        )

        for deal in unsignalled:
            try:
                stock = get_stock_data(deal['symbol'])
                if 'error' in stock:
                    logger.warning(f"No price data for {deal['symbol']} — skipping")
                    continue

                signal = explain_signal(deal, stock)

                db_execute(
                    '''INSERT INTO signals
                       (deal_id, symbol, explanation, signal_type, risk_level,
                        confidence, key_observation, disclaimer, ai_provider)
                       VALUES (?,?,?,?,?,?,?,?,?)''',
                    (
                        deal['id'],
                        deal['symbol'],
                        signal.get('explanation',     ''),
                        signal.get('signal_type',     'neutral'),
                        signal.get('risk_level',      'medium'),
                        signal.get('confidence',       50),
                        signal.get('key_observation', ''),
                        signal.get('disclaimer', 'For educational purposes only. Not financial advice.'),
                        signal.get('ai_provider'),
                    )
                )
                logger.info(f"Signal created: {deal['symbol']} — {signal.get('signal_type')}")
                time.sleep(2.5)

            except Exception as e:
                logger.error(f"Error processing deal {deal.get('id')}: {e}")
                continue

    except Exception as e:
        logger.error(f'Radar job failed: {e}')


def prefetch_popular_stocks():
    """
    Runs at startup (30s delay) to pre-warm card cache for popular NSE stocks.
    Cache TTL: 1 hour (vs 15 min for user-triggered refreshes).
    """
    from services.indicators import POPULAR_STOCKS, get_stock_data
    from services.news_fetcher import get_stock_news
    from services.gpt import generate_signal_card
    from database import db_execute
    from datetime import datetime, timedelta
    import json

    logger.info('Pre-fetching signal cards for popular stocks...')
    for ns_symbol in POPULAR_STOCKS[:10]:
        symbol = ns_symbol.replace('.NS', '')
        try:
            stock = get_stock_data(symbol)
            if 'error' in stock:
                continue
            news = get_stock_news(symbol)
            card = generate_signal_card(symbol, stock, news)
            dates  = stock.get('dates_30d', [])
            prices = stock.get('price_30d', [])
            # Fetch real 5-min intraday so trends['1d'] is never stale daily data
            try:
                from services.nse_service import get_historical as _gh
                intraday_points = _gh(symbol, '1d') or []
            except Exception:
                intraday_points = []
            trends = {
                '1m': [{'time': d, 'price': p} for d, p in zip(dates, prices)],
                '1w': [{'time': d, 'price': p} for d, p in zip(dates[-7:],  prices[-7:])],
                '1d': intraday_points,   # proper 5-min intraday, not daily close data
            }
            card.update({
                'price_30d':     prices,
                'dates_30d':     dates,
                'current_price': stock.get('current_price'),
                'change_pct':    stock.get('change_pct'),
                'rsi':           stock.get('rsi'),
                'ema_signal':    stock.get('ema_signal'),
                'rsi_zone':      stock.get('rsi_zone'),
                'symbol':        symbol,
                'trends':        trends,
                'news': [
                    {'headline': n.get('headline', ''), 'source': n.get('source', ''), 'url': n.get('url', '')}
                    for n in news[:4]
                ],
            })
            expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()
            db_execute(
                'INSERT OR REPLACE INTO card_cache (symbol, card_json, expires_at) VALUES (?,?,?)',
                (symbol, json.dumps(card), expires)
            )
            # Also warm L1 in-memory cache so first request is sub-ms
            try:
                from routers.cards import _mem_set
                _mem_set(symbol, card)
            except Exception:
                pass
            logger.info(f'Pre-fetched card: {symbol}')
            time.sleep(3)
        except Exception as e:
            logger.error(f'Pre-fetch failed for {symbol}: {e}')


def _get_signal_symbols() -> list:
    """Returns unique symbols from the latest signals (for price pre-warming)."""
    try:
        from database import db_fetchall
        rows = db_fetchall('SELECT DISTINCT symbol FROM signals ORDER BY created_at DESC LIMIT 30')
        return [r['symbol'] for r in rows if r.get('symbol')]
    except Exception:
        return []


def refresh_live_quotes():
    """
    Refresh all Nifty 50 quotes every 2 s.
    Primary: 1 NSE batch call → all 50 symbols.
    Fallback: Yahoo Finance batch if NSE returns < 10 results (rate-limited / down).
    Also batches signal symbols + hot symbols (user-searched) via Yahoo.
    """
    try:
        from services.market_hours import is_market_open
        if not is_market_open():
            return
        from services.nse_service import (
            get_nifty50_batch, get_yahoo_batch, get_historical,
            get_hot_symbols, get_bulk_quotes,
        )
        from concurrent.futures import ThreadPoolExecutor

        # Primary: 1 NSE API call → all 50 Nifty 50 quotes
        updated = get_nifty50_batch()
        logger.debug(f'[LiveQuotes] NSE batch: {updated} symbols')

        # Fallback: Yahoo batch if NSE batch returned too few (403 / outage)
        if updated < 10:
            y = get_yahoo_batch(_LIVE_SYMBOLS)
            logger.debug(f'[LiveQuotes] Yahoo fallback batch: {y} symbols')

        # Batch-refresh signal symbols + hot symbols via Yahoo (1 call for all)
        nifty_set = set(_LIVE_SYMBOLS)
        hot = get_hot_symbols(limit=10)
        sig_syms = _get_signal_symbols()
        extra = list({s for s in (hot + sig_syms) if s not in nifty_set})
        if extra:
            get_yahoo_batch(extra[:50])   # single Yahoo batch call for all extras

        # Warm intraday cache for actively viewed symbols
        hot5 = get_hot_symbols(limit=5)
        if hot5:
            def _wi(s):
                try: get_historical(s, '1d')
                except: pass
            with ThreadPoolExecutor(max_workers=5) as ex:
                for sym in hot5:
                    ex.submit(_wi, sym)

    except Exception as e:
        logger.warning(f'[LiveQuotes] Refresh error: {e}')


def refresh_movers_cache():
    """
    Pre-warm the market movers in-memory cache so the /market/movers
    endpoint always responds from cache (< 5 ms) during market hours.
    Runs every 8 seconds — just inside the 8-second quote TTL window.
    """
    try:
        from services.market_hours import is_market_open
        if not is_market_open():
            return
        # Trigger the movers endpoint logic directly to refresh its cache
        from routers.market import _SYMBOLS, _cache
        from services.nse_service import get_bulk_quotes
        from services.search_service import NSE_STOCKS
        import time as _time

        quotes = get_bulk_quotes(_SYMBOLS)
        stocks = []
        for sym, q in quotes.items():
            if not q or q.get('price') is None:
                continue
            pct = q.get('percent_change')
            try:
                pct = float(pct) if pct is not None else 0.0
            except (ValueError, TypeError):
                pct = 0.0
            stocks.append({
                'symbol':     sym,
                'name':       NSE_STOCKS.get(sym, sym),
                'price':      q['price'],
                'change_pct': round(pct, 2),
                'change':     q.get('change', 0),
            })

        if not stocks:
            return

        by_pct   = sorted(stocks, key=lambda x: x['change_pct'], reverse=True)
        by_price = sorted(stocks, key=lambda x: float(x['price']))

        gainers_pos = [s for s in by_pct if s['change_pct'] > 0]
        gainers = gainers_pos[:10]
        if len(gainers) < 10:
            gainers += [s for s in by_pct if s['change_pct'] <= 0][:10 - len(gainers)]

        losers_neg = [s for s in reversed(by_pct) if s['change_pct'] < 0]
        losers = losers_neg[:10]
        if len(losers) < 10:
            losers += [s for s in by_pct if s['change_pct'] >= 0][-10 + len(losers):]

        _cache['movers'] = {
            'data': {
                'gainers':   gainers,
                'losers':    losers,
                'cheapest':  by_price[:10],
                'expensive': list(reversed(by_price))[:10],
                'total':     len(stocks),
            },
            'ts': _time.time(),
        }
        logger.debug(f'[MoversCache] Pre-warmed — {len(stocks)} stocks')
    except Exception as e:
        logger.warning(f'[MoversCache] Refresh error: {e}')


def start_scheduler():
    """
    Configures and starts the APScheduler background scheduler.
    Guard against duplicate starts (e.g. uvicorn --reload).
    """
    interval_hours = int(os.getenv('RADAR_INTERVAL_HOURS', '1'))

    scheduler.add_job(
        run_radar_job,
        trigger          = IntervalTrigger(hours=interval_hours),
        id               = 'opportunity_radar',
        max_instances    = 1,
        replace_existing = True,
    )

    import datetime as dt

    scheduler.add_job(
        run_radar_job,
        trigger          = 'date',
        run_date         = dt.datetime.now() + dt.timedelta(seconds=10),
        id               = 'radar_startup',
        replace_existing = True,
    )

    # Batch-fetch all Nifty 50 + signal symbols at startup
    def _startup_batch():
        try:
            from services.nse_service import get_nifty50_batch, get_yahoo_batch
            n = get_nifty50_batch()
            logger.info(f'[Startup] NSE batch pre-warmed {n} Nifty 50 quotes')
            if n < 10:
                n2 = get_yahoo_batch(_LIVE_SYMBOLS)
                logger.info(f'[Startup] Yahoo fallback pre-warmed {n2} quotes')
            # Also pre-warm signal symbols (non-Nifty-50) via Yahoo batch
            sig_syms = _get_signal_symbols()
            nifty_set = set(_LIVE_SYMBOLS)
            extra = [s for s in sig_syms if s not in nifty_set]
            if extra:
                n3 = get_yahoo_batch(extra[:50])
                logger.info(f'[Startup] Signal symbols pre-warmed {n3} quotes')
        except Exception as e:
            logger.warning(f'[Startup] Batch warm failed: {e}')

    scheduler.add_job(
        _startup_batch,
        trigger          = 'date',
        run_date         = dt.datetime.now() + dt.timedelta(seconds=5),
        id               = 'batch_startup_warm',
        replace_existing = True,
    )

    # Warm movers cache at startup so Radar page loads instantly on first visit.
    scheduler.add_job(
        refresh_movers_cache,
        trigger          = 'date',
        run_date         = dt.datetime.now() + dt.timedelta(seconds=10),
        id               = 'movers_startup_warm',
        replace_existing = True,
    )

    # First-run warmup job (demo UX): run after prefetch_popular_stocks kicks in.
    scheduler.add_job(
        warmup_seed_if_needed,
        trigger          = 'date',
        run_date         = dt.datetime.now() + dt.timedelta(seconds=45),
        id               = 'warmup_seed_if_needed',
        replace_existing = True,
        max_instances    = 1,
    )

    scheduler.add_job(
        prefetch_popular_stocks,
        trigger          = 'date',
        run_date         = dt.datetime.now() + dt.timedelta(seconds=30),
        id               = 'prefetch_startup',
        replace_existing = True,
    )

    live_refresh_seconds   = max(2, int(os.getenv('LIVE_REFRESH_SECONDS',   '2')))   # batch NSE call every 2 s
    movers_refresh_seconds = max(2, int(os.getenv('MOVERS_REFRESH_SECONDS', '3')))   # movers rebuild every 3 s (all cache hits)

    # Live quote cache warmer — all 50 movers symbols
    scheduler.add_job(
        refresh_live_quotes,
        trigger          = IntervalTrigger(seconds=live_refresh_seconds),
        id               = 'live_quote_refresh',
        max_instances    = 1,
        replace_existing = True,
    )

    # Movers cache pre-warmer
    # Keeps /market/movers always served from in-memory cache (< 5 ms)
    scheduler.add_job(
        refresh_movers_cache,
        trigger          = IntervalTrigger(seconds=movers_refresh_seconds),
        id               = 'movers_cache_refresh',
        max_instances    = 1,
        replace_existing = True,
    )

    if not scheduler.running:
        scheduler.start()
        logger.info(f'Scheduler started — Opportunity Radar runs every {interval_hours}h')
    else:
        logger.info(f'Scheduler already running — jobs ensured (Radar interval {interval_hours}h)')
