import time
from datetime import date, timedelta

import requests

from database import db_execute, db_fetchone

NSE_BASE = "https://www.nseindia.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}

_session = None


def get_nse_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(HEADERS)
        try:
            _session.get(NSE_BASE, timeout=5)
            time.sleep(1)
            # Session warmup pattern: hit a few NSE pages to populate cookies
            # used by the internal APIs (bulk deals + equity quotes).
            _session.get(f"{NSE_BASE}/get-quotes/equity?symbol=RELIANCE", timeout=5)
            time.sleep(0.5)
            _session.get(f"{NSE_BASE}/market-data/bulk-deals", timeout=5)
            time.sleep(0.5)
            print("[NSE] Session warmed up successfully")
        except Exception as e:
            print(f"[NSE] Session warmup error: {e}")
    return _session


def reset_session():
    global _session
    _session = None
    print("[NSE] Session reset")


def _date_candidates(ds: str) -> list[str]:
    """
    NSE internal archives are picky about date formatting.
    Try both `DD-MM-YYYY` and `YYYY-MM-DD` variants.
    """
    if not ds:
        return []
    ds = ds.strip()
    if ds.count("-") != 2:
        return [ds]

    a, b, c = ds.split("-")
    # DD-MM-YYYY
    if len(a) == 2 and len(c) == 4:
        alt = f"{c}-{b}-{a}"
        return [ds, alt]
    # YYYY-MM-DD
    if len(a) == 4 and len(c) == 2:
        alt = f"{c}-{b}-{a}"
        return [ds, alt]
    return [ds]


def fetch_bulk_deals(from_date: str = None, to_date: str = None, _retry: int = 0) -> list:
    """
    Fetch bulk deals from NSE.
    Priority: /api/bulk-deals (no date) → /api/bulk-deal-archives (with date).
    Max 3 retries on 403.
    """
    if _retry >= 3:
        print("[NSE] fetch_bulk_deals: max retries reached, returning []")
        return []
    session = get_nse_session()

    # ── Attempt 1: direct no-date endpoint (live deals, usually available) ──
    if from_date is None and to_date is None:
        try:
            resp = session.get(f"{NSE_BASE}/api/bulk-deals", timeout=8)
            if resp.status_code == 403:
                reset_session()
                return fetch_bulk_deals(from_date, to_date, _retry + 1)
            if resp.status_code == 200 and resp.content:
                payload = resp.json()
                if isinstance(payload, list):
                    data = payload
                else:
                    data = payload.get("data", [])
                if data:
                    print(f"[NSE] /api/bulk-deals returned {len(data)} deals")
                    return data
        except Exception as e:
            print(f"[NSE] Direct bulk-deals error: {e}")

    # ── Attempt 2: archived endpoint with date range ──
    today = date.today().strftime("%d-%m-%Y")
    from_ds = from_date or today
    to_ds = to_date or today
    from_candidates = _date_candidates(from_ds)
    to_candidates = _date_candidates(to_ds)
    try:
        last_err: str | None = None
        for fd in from_candidates:
            for td in to_candidates:
                params = {"from": fd, "to": td}
                resp = session.get(
                    f"{NSE_BASE}/api/historical/bulk-deals",
                    params=params,
                    timeout=8,
                )
                if resp.status_code == 403:
                    print(f"[NSE] 403 received - resetting session (attempt {_retry + 1}/3)")
                    reset_session()
                    return fetch_bulk_deals(from_date, to_date, _retry + 1)
                if resp.status_code == 404:
                    last_err = f"404 for from={fd} to={td}"
                    continue
                resp.raise_for_status()
                payload = resp.json()
                if isinstance(payload, list):
                    data = payload
                else:
                    # The response shape differs across NSE deployments.
                    # Accept both `{"data":[...]}` and a direct list.
                    data = payload.get("data", []) or payload.get("deals", []) or payload.get("bulkDeals", []) or []  # noqa: E501
                if data:
                    return data
        if last_err:
            print(f"[NSE] Bulk archive empty: {last_err}")
        return []
    except Exception as e:
        print(f"[NSE] Bulk deals fetch error: {e}")
        return []


def fetch_bulk_deals_lookback(days: int = 7) -> list:
    """
    Fetch bulk deals from the past N calendar days.
    Used to seed the DB when today returns nothing.
    """
    from datetime import timedelta
    all_deals: list = []
    for offset in range(1, days + 1):
        d = date.today() - timedelta(days=offset)
        ds = d.strftime("%d-%m-%Y")
        deals = fetch_bulk_deals(ds, ds)
        if deals:
            all_deals.extend(deals)
            print(f"[NSE] Lookback {ds}: {len(deals)} deals")
            if len(all_deals) >= 30:   # enough to seed signals
                break
    return all_deals


def fetch_block_deals(_retry: int = 0) -> list:
    """Fetch block deals from NSE with max 3 retries on 403 and timeout=8."""
    return fetch_block_deals_for_dates(None, None, _retry=_retry)


def fetch_block_deals_for_dates(from_date: str | None, to_date: str | None, _retry: int = 0) -> list:
    """Fetch block deals for a specific date range (used for lookback)."""
    if _retry >= 3:
        print("[NSE] fetch_block_deals: max retries reached, returning []")
        return []
    session = get_nse_session()
    today = date.today().strftime("%d-%m-%Y")
    from_ds = from_date or today
    to_ds = to_date or today
    from_candidates = _date_candidates(from_ds)
    to_candidates = _date_candidates(to_ds)
    try:
        last_err: str | None = None
        for fd in from_candidates:
            for td in to_candidates:
                resp = session.get(
                    f"{NSE_BASE}/api/historical/block-deals",
                    params={"from": fd, "to": td},
                    timeout=8,
                )
                if resp.status_code == 403:
                    print(f"[NSE] 403 received (block) - resetting session (attempt {_retry + 1}/3)")
                    reset_session()
                    return fetch_block_deals(_retry + 1)
                if resp.status_code == 404:
                    last_err = f"404 for from={fd} to={td}"
                    continue
                resp.raise_for_status()
                payload = resp.json()
                if isinstance(payload, list):
                    data = payload
                else:
                    data = payload.get("data", []) or payload.get("deals", []) or payload.get("blockDeals", []) or []  # noqa: E501
                if data:
                    return data
        if last_err:
            print(f"[NSE] Block archive empty: {last_err}")
        return []
    except Exception as e:
        print(f"[NSE] Block deals fetch error: {e}")
        return []


def fetch_block_deals_lookback(days: int = 7) -> list:
    """
    Fetch block deals for the past N calendar days.
    Used to seed the DB when today returns nothing.
    """
    all_deals: list = []
    for offset in range(1, days + 1):
        d = date.today() - timedelta(days=offset)
        ds = d.strftime("%d-%m-%Y")
        deals = fetch_block_deals_for_dates(ds, ds, _retry=0)
        if deals:
            all_deals.extend(deals)
            print(f"[NSE] Block lookback {ds}: {len(deals)} deals")
            if len(all_deals) >= 30:
                break
    return all_deals


def save_bulk_deals_to_db(deals: list) -> int:
    count = 0
    for d in deals:
        try:
            raw_qty = str(d.get("quantityTraded", 0) or 0).replace(",", "")
            quantity = int(raw_qty) if raw_qty.isdigit() else 0
            existing = db_fetchone(
                "SELECT id FROM bulk_deals WHERE symbol=? AND deal_date=? AND quantity=?",
                (d.get("symbol", ""), d.get("dealDate", ""), quantity),
            )
            if not existing:
                db_execute(
                    """INSERT INTO bulk_deals
                       (symbol, client_name, deal_type, quantity, price, deal_date)
                       VALUES (?,?,?,?,?,?)""",
                    (
                        d.get("symbol", "").upper(),
                        d.get("clientName", ""),
                        d.get("buySellType", d.get("dealType", "")),
                        quantity,
                        float(str(d.get("tradePrice", 0) or 0).replace(",", "")),
                        d.get("dealDate", date.today().isoformat()),
                    ),
                )
                count += 1
        except Exception as e:
            print(f"[NSE] Error saving deal {d}: {e}")
            continue
    return count
