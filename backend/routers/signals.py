# backend/routers/signals.py
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from database import db_fetchall, db_fetchone, db_execute
from services.nse_fetcher import fetch_bulk_deals, fetch_block_deals, fetch_bulk_deals_lookback, save_bulk_deals_to_db
from services.indicators import get_stock_data
from services.gpt import explain_signal
from services.nse_service import get_bulk_quotes
from services.symbol_resolver import normalize_symbol
import time

router = APIRouter()

# Short-lived in-memory cache — avoids hammering get_bulk_quotes on every frontend poll
_sig_cache: dict = {}   # cache_key → {'data': list, 'ts': float}
_SIG_CACHE_TTL = 4.5    # seconds — expires just before 5 s frontend poll; quote cache (15 s) always warm

# Technical enrichment cache — prevents repeated get_stock_data calls per symbol
# Each entry lives 5 min; get_stock_data itself uses SQLite caches so is fast when warm
_tech_enrich_cache: dict = {}   # symbol → {'data': dict, 'ts': float}
_TECH_ENRICH_TTL = 300          # 5 minutes

import json as _json

def _get_tech_for_symbol(symbol: str) -> dict:
    """
    Returns technical indicators for a symbol.
    Priority: memory cache → card_cache (SQLite) → get_stock_data (uses SQLite caches).
    Never raises — returns empty dict on any failure.
    """
    now = time.time()
    cached = _tech_enrich_cache.get(symbol)
    if cached and (now - cached['ts']) < _TECH_ENRICH_TTL:
        return cached['data']

    KEYS = ('rsi', 'rsi_zone', 'ema_signal', 'ema20', 'ema50', 'sma200', 'high_52w', 'low_52w')

    # 1) Try card_cache first — pure SQLite, sub-millisecond
    try:
        row = db_fetchone('SELECT card_json FROM card_cache WHERE symbol=?', (symbol,))
        if row and row.get('card_json'):
            card = _json.loads(row['card_json'])
            data = {k: card.get(k) for k in KEYS}
            if any(v is not None for v in data.values()):
                _tech_enrich_cache[symbol] = {'data': data, 'ts': now}
                return data
    except Exception:
        pass

    # 2) Fall back to get_stock_data — uses close_series_cache (SQLite), fast when warm
    try:
        tech = get_stock_data(symbol)
        if 'error' not in tech:
            data = {k: tech.get(k) for k in KEYS}
            _tech_enrich_cache[symbol] = {'data': data, 'ts': now}
            return data
    except Exception:
        pass

    # 3) Cache empty result so we don't retry every poll
    _tech_enrich_cache[symbol] = {'data': {}, 'ts': now}
    return {}


@router.get('/signals')
def get_signals(
    limit:      int = Query(20, ge=1, le=100),
    risk_level: str = Query(None, pattern='^(high|medium|low)$'),
    symbol:     str = Query(None, max_length=10),
):
    """Returns latest AI-explained signals from the Opportunity Radar."""
    try:
        cache_key = f'{limit}:{risk_level}:{symbol}'
        cached = _sig_cache.get(cache_key)
        if cached and (time.time() - cached['ts']) < _SIG_CACHE_TTL:
            return {'success': True, 'data': {'signals': cached['data']}, 'error': None}

        query      = 'SELECT * FROM signals'
        params     = []
        conditions = []

        if risk_level:
            conditions.append('risk_level = ?')
            params.append(risk_level)
        if symbol:
            conditions.append('symbol = ?')
            params.append(normalize_symbol(symbol)[:10])

        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        query += ' ORDER BY created_at DESC LIMIT ?'
        params.append(limit)

        signals = db_fetchall(query, tuple(params))

        # Enrich with live NSE price data
        if signals:
            unique_symbols = list({s['symbol'] for s in signals if s.get('symbol')})
            try:
                quotes = get_bulk_quotes(unique_symbols)
                for sig in signals:
                    q = quotes.get(sig.get('symbol'))
                    sig['price']          = q['price']          if q else None
                    sig['percent_change'] = q['percent_change'] if q else None
            except Exception as e:
                print(f'[Signals] Price enrichment failed: {e}')

        # Enrich with technical indicators (card_cache → get_stock_data fallback)
        if signals:
            for sig in signals:
                sym = sig.get('symbol')
                if not sym:
                    continue
                tech = _get_tech_for_symbol(sym)
                sig['rsi']        = tech.get('rsi')
                sig['rsi_zone']   = tech.get('rsi_zone')
                sig['ema_signal'] = tech.get('ema_signal')
                sig['ema20']      = tech.get('ema20')
                sig['ema50']      = tech.get('ema50')
                sig['sma200']     = tech.get('sma200')
                sig['high_52w']   = tech.get('high_52w')
                sig['low_52w']    = tech.get('low_52w')

        # Replace stale "temporarily unavailable" explanations with rule-based analysis
        _STALE = 'Signal analysis temporarily unavailable.'
        stale_ids = [
            s['deal_id'] for s in signals
            if s.get('explanation') == _STALE and s.get('deal_id')
        ]
        if stale_ids:
            try:
                from services.gpt import _rule_based_signal_explanation
                ph = ','.join('?' * len(stale_ids))
                deals_rows = db_fetchall(
                    f'SELECT * FROM bulk_deals WHERE id IN ({ph})',
                    tuple(stale_ids),
                )
                deals_map = {d['id']: d for d in deals_rows}
                for sig in signals:
                    if sig.get('explanation') == _STALE and sig.get('deal_id') in deals_map:
                        deal = deals_map[sig['deal_id']]
                        stock = {
                            'symbol':        sig.get('symbol', ''),
                            'current_price': sig.get('price'),
                            'change_pct':    sig.get('percent_change') or 0,
                            'rsi':           None,
                            'ema_signal':    'neutral',
                            'high_52w':      None,
                            'low_52w':       None,
                        }
                        rb = _rule_based_signal_explanation(deal, stock)
                        sig.update({
                            'explanation':     rb['explanation'],
                            'signal_type':     rb.get('signal_type',     sig.get('signal_type', 'neutral')),
                            'risk_level':      rb.get('risk_level',      sig.get('risk_level',  'medium')),
                            'confidence':      rb.get('confidence',      sig.get('confidence',   50)),
                            'key_observation': rb.get('key_observation', sig.get('key_observation', '')),
                            'ai_provider':     rb.get('ai_provider',     sig.get('ai_provider', 'rule_based')),
                        })
            except Exception as e:
                print(f'[Signals] Stale explanation fix failed: {e}')

        _sig_cache[cache_key] = {'data': signals, 'ts': time.time()}
        return {'success': True, 'data': {'signals': signals}, 'error': None}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={'success': False, 'data': None, 'error': str(e)},
        )


@router.get('/signals/{signal_id}')
def get_signal_by_id(signal_id: int):
    """Returns a single signal by its database ID."""
    try:
        row = db_fetchone('SELECT * FROM signals WHERE id=?', (signal_id,))
        if not row:
            return JSONResponse(
                status_code=404,
                content={'success': False, 'data': None, 'error': 'Signal not found'},
            )
        return {'success': True, 'data': row, 'error': None}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={'success': False, 'data': None, 'error': str(e)},
        )


@router.post('/signals/refresh')
def manual_refresh():
    """
    Manually triggers the Opportunity Radar pipeline.
    Fetches NSE deals → saves → generates AI signals.
    Returns counts: new_deals saved, signals_generated.
    """
    try:
        deals = fetch_bulk_deals() + fetch_block_deals()
        # If today has no deals (market closed / not yet published), look back up to 7 days
        if not deals:
            print('[Refresh] Today has no deals — looking back up to 7 days')
            deals = fetch_bulk_deals_lookback(7)
        saved = save_bulk_deals_to_db(deals)

        unsignalled = db_fetchall(
            '''SELECT bd.* FROM bulk_deals bd
               LEFT JOIN signals s ON s.deal_id = bd.id
               WHERE s.id IS NULL
               ORDER BY bd.fetched_at DESC LIMIT 10'''
        )

        generated = 0
        for deal in unsignalled:
            try:
                stock = get_stock_data(deal['symbol'])
                if 'error' in stock:
                    print(f"[Refresh] No price data for {deal['symbol']} — skipping")
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
                generated += 1
                time.sleep(2.5)
            except Exception as e:
                print(f"[Refresh] Error processing deal {deal.get('id')}: {e}")
                continue

        return {
            'success': True,
            'data': {'new_deals': saved, 'signals_generated': generated},
            'error': None,
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={'success': False, 'data': None, 'error': str(e)},
        )


@router.post('/signals/backfill-ai')
def backfill_ai_signals(limit: int = Query(10, ge=1, le=100)):
    """
    Maintenance endpoint (dev use):
    - Re-runs Llama-based explain_signal for existing rule-based signals.
    - Clears cached cards whose technical_snapshot uses the old fallback text so they regenerate on next view.
    """
    try:
        # 1) Upgrade existing rule-based Opportunity Radar signals
        stale_signals = db_fetchall(
            '''
            SELECT s.*
            FROM signals s
            WHERE (s.ai_provider = 'rule_based'
                   OR s.explanation = 'Signal analysis temporarily unavailable.')
            ORDER BY s.created_at DESC
            LIMIT ?
            ''',
            (limit,),
        )

        upgraded = 0
        for sig in stale_signals:
            deal_id = sig.get('deal_id')
            symbol  = sig.get('symbol')
            if not deal_id or not symbol:
                continue

            try:
                deal = db_fetchone('SELECT * FROM bulk_deals WHERE id=?', (deal_id,))
                if not deal:
                    continue

                stock = get_stock_data(symbol)
                if 'error' in stock:
                    print(f"[Backfill] No price data for {symbol} — skipping")
                    continue

                ai = explain_signal(deal, stock)
                db_execute(
                    '''
                    UPDATE signals
                    SET explanation     = ?,
                        signal_type     = ?,
                        risk_level      = ?,
                        confidence      = ?,
                        key_observation = ?,
                        disclaimer      = ?,
                        ai_provider     = ?
                    WHERE id = ?
                    ''',
                    (
                        ai.get('explanation', sig.get('explanation', '')),
                        ai.get('signal_type', sig.get('signal_type', 'neutral')),
                        ai.get('risk_level', sig.get('risk_level', 'medium')),
                        int(ai.get('confidence', sig.get('confidence', 50)) or 50),
                        ai.get('key_observation', sig.get('key_observation', '')),
                        ai.get('disclaimer', sig.get('disclaimer', 'For educational purposes only. Not financial advice.')),
                        ai.get('ai_provider', 'llama'),
                        sig['id'],
                    ),
                )
                upgraded += 1
                time.sleep(1.0)
            except Exception as e:
                print(f"[Backfill] Failed to upgrade signal {sig.get('id')}: {e}")
                continue

        # 2) Clear all cached cards so they regenerate with Llama on next request
        try:
            deleted = db_execute(
                '''
                DELETE FROM card_cache
                ''',
                (),
            )
        except Exception as e:
            print(f"[Backfill] Failed to clear stale card_cache rows: {e}")
            deleted = 0

        return {
            'success': True,
            'data': {
                'signals_upgraded': upgraded,
                'stale_cards_cleared': deleted,
            },
            'error': None,
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={'success': False, 'data': None, 'error': str(e)},
        )


@router.get('/bulk-deals')
def get_bulk_deals(limit: int = Query(20, ge=1, le=100)):
    """Returns raw bulk deal data without AI explanation."""
    try:
        deals = db_fetchall(
            'SELECT * FROM bulk_deals ORDER BY fetched_at DESC LIMIT ?',
            (limit,)
        )
        return {'success': True, 'data': {'deals': deals}, 'error': None}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={'success': False, 'data': None, 'error': str(e)},
        )
