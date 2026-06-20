# backend/services/market_hours.py
"""
NSE market hours utility (IST).
Open: 09:15 IST — Close: 15:30 IST, Monday–Friday.
All functions are pure / zero-side-effect — safe to call freely.
"""
import datetime

_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

MARKET_OPEN  = datetime.time(9,  15)
MARKET_CLOSE = datetime.time(15, 30)


def now_ist() -> datetime.datetime:
    """Return current datetime in IST."""
    return datetime.datetime.now(tz=_IST)


def is_market_open(dt: datetime.datetime | None = None) -> bool:
    """
    Return True if the NSE equity market is currently open.
    Checks weekday (Mon–Fri) and time window (09:15–15:30 IST).
    Pass `dt` to override the current time (useful for testing).
    """
    if dt is None:
        dt = now_ist()
    # Weekday: Mon=0 … Fri=4; Sat=5, Sun=6 → closed
    if dt.weekday() > 4:
        return False
    t = dt.time()
    return MARKET_OPEN <= t <= MARKET_CLOSE


def market_status() -> dict:
    """
    Return a status dict with IST time, date, open flag, and weekday.
    Used by the /market/status endpoint and the scheduler.
    """
    dt = now_ist()
    return {
        "is_open":  is_market_open(dt),
        "time_ist": dt.strftime("%H:%M"),
        "date_ist": dt.strftime("%Y-%m-%d"),
        "weekday":  dt.strftime("%A"),
    }
