from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from typing import Any, Dict, List

import json

from database import db_fetchall, db_fetchone, db_execute
from routers.auth import get_current_user


router = APIRouter()


SECTOR_HINTS = {
    # IT
    "TCS": "IT", "INFY": "IT", "WIPRO": "IT", "HCLTECH": "IT", "TECHM": "IT",
    "LTIM": "IT", "MPHASIS": "IT", "COFORGE": "IT", "PERSISTENT": "IT", "OFSS": "IT",
    "KPITTECH": "IT", "TATAELXSI": "IT",
    # Banking
    "HDFCBANK": "Banking", "ICICIBANK": "Banking", "SBIN": "Banking", "AXISBANK": "Banking",
    "KOTAKBANK": "Banking", "INDUSINDBK": "Banking", "BANDHANBNK": "Banking",
    "FEDERALBNK": "Banking", "IDFCFIRSTB": "Banking", "PNB": "Banking",
    "BANKBARODA": "Banking", "CANBK": "Banking", "UNIONBANK": "Banking",
    "RBLBANK": "Banking", "YESBANK": "Banking",
    # NBFC
    "BAJFINANCE": "NBFC", "BAJAJFINSV": "NBFC", "MUTHOOTFIN": "NBFC",
    "CHOLAFIN": "NBFC", "M&MFIN": "NBFC", "SHRIRAMFIN": "NBFC",
    "LICHSGFIN": "NBFC", "POONAWALLA": "NBFC",
    # Insurance
    "SBILIFE": "Insurance", "HDFCLIFE": "Insurance", "ICICIPRULI": "Insurance",
    "ICICIGI": "Insurance", "STARHEALTH": "Insurance",
    # Energy & Power
    "RELIANCE": "Energy", "ONGC": "Energy", "BPCL": "Energy", "IOC": "Energy",
    "HINDPETRO": "Energy", "GAIL": "Energy", "PETRONET": "Energy",
    "NTPC": "Energy", "POWERGRID": "Energy", "TATAPOWER": "Energy",
    "ADANIGREEN": "Energy", "ADANIPOWER": "Energy", "TORNTPOWER": "Energy",
    # Auto
    "TATAMOTORS": "Auto", "MARUTI": "Auto", "M&M": "Auto", "BAJAJ-AUTO": "Auto",
    "HEROMOTOCO": "Auto", "EICHERMOT": "Auto", "TVSMOTOR": "Auto",
    "ASHOKLEY": "Auto", "ESCORTS": "Auto", "BOSCHLTD": "Auto",
    "MOTHERSON": "Auto", "BHARATFORG": "Auto", "APOLLOTYRE": "Auto", "MRF": "Auto",
    # Pharma
    "SUNPHARMA": "Pharma", "DRREDDY": "Pharma", "CIPLA": "Pharma",
    "DIVISLAB": "Pharma", "BIOCON": "Pharma", "AUROPHARMA": "Pharma",
    "TORNTPHARM": "Pharma", "ALKEM": "Pharma", "LUPIN": "Pharma",
    "GLENMARK": "Pharma", "IPCALAB": "Pharma", "NATCOPHARM": "Pharma",
    # FMCG
    "ITC": "FMCG", "HINDUNILVR": "FMCG", "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG", "DABUR": "FMCG", "MARICO": "FMCG",
    "COLPAL": "FMCG", "GODREJCP": "FMCG", "EMAMILTD": "FMCG",
    "VBL": "FMCG", "UBL": "FMCG", "RADICO": "FMCG",
    # Metals & Mining
    "TATASTEEL": "Metals", "JSWSTEEL": "Metals", "HINDALCO": "Metals",
    "COALINDIA": "Metals", "VEDL": "Metals", "SAIL": "Metals",
    "NMDC": "Metals", "JINDALSTEL": "Metals", "NATIONALUM": "Metals",
    # Cement
    "ULTRACEMCO": "Cement", "SHREECEM": "Cement", "AMBUJACEM": "Cement",
    "ACC": "Cement", "DALMIACGEM": "Cement", "JKCEMENT": "Cement", "RAMCOCEM": "Cement",
    # Consumer Durables
    "TITAN": "Consumer", "HAVELLS": "Consumer", "VOLTAS": "Consumer",
    "BATAINDIA": "Consumer", "PAGEIND": "Consumer", "WHIRLPOOL": "Consumer",
    # Infrastructure & Real Estate
    "LT": "Infrastructure", "ADANIENT": "Infrastructure", "ADANIPORTS": "Infrastructure",
    "GMRINFRA": "Infrastructure", "DLF": "Real Estate", "GODREJPROP": "Real Estate",
    "OBEROIRLTY": "Real Estate", "PHOENIXLTD": "Real Estate", "PRESTIGE": "Real Estate",
    # Telecom
    "BHARTIARTL": "Telecom", "IDEA": "Telecom",
    # Paints & Chemicals
    "ASIANPAINT": "Paints", "BERGEPAINT": "Paints", "KANSAINER": "Paints",
    "PIDILITIND": "Chemicals", "SRF": "Chemicals", "DEEPAKNTR": "Chemicals",
    # Healthcare Services
    "APOLLOHOSP": "Healthcare", "FORTIS": "Healthcare", "MAXHEALTH": "Healthcare",
    "METROPOLIS": "Healthcare", "LALPATHLAB": "Healthcare",
    # Retail
    "DMART": "Retail", "TRENT": "Retail",
    # Financial Markets
    "BSE": "Financial Markets", "MCX": "Financial Markets",
    "CDSL": "Financial Markets", "ANGELONE": "Financial Markets",
    # Agriculture
    "UPL": "Agriculture", "PIIND": "Agriculture", "COROMANDEL": "Agriculture",
    # Media
    "ZEEL": "Media", "SUNTV": "Media", "PVRINOX": "Media",
    # Diversified
    "GRASIM": "Diversified",
}


class Holding(BaseModel):
    symbol: str
    quantity: float = 0

    @field_validator("symbol")
    @classmethod
    def norm_symbol(cls, v: str) -> str:
        v = (v or "").strip().upper()
        if not v:
            raise ValueError("symbol required")
        return v


class PortfolioSubmitRequest(BaseModel):
    holdings: List[Holding]


@router.post("/portfolio")
def submit_portfolio(
    req: PortfolioSubmitRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    holdings_json = json.dumps([h.model_dump() for h in req.holdings])
    db_execute(
        "INSERT OR REPLACE INTO user_portfolios (user_id, holdings_json) VALUES (?,?)",
        (int(user["id"]), holdings_json),
    )
    return {"success": True, "data": {"saved": True}, "error": None}


@router.get("/portfolio")
def get_portfolio(user: Dict[str, Any] = Depends(get_current_user)):
    row = db_fetchone(
        "SELECT holdings_json, updated_at FROM user_portfolios WHERE user_id=?",
        (int(user["id"]),),
    )
    if not row:
        return {
            "success": True,
            "data": {
                "analysis": {},
                "updated_at": None,
                "message": "No portfolio submitted yet.",
            },
            "error": None,
        }

    try:
        holdings = json.loads(row["holdings_json"] or "[]")
    except Exception:
        holdings = []

    if not holdings:
        return {"success": True, "data": {"analysis": {}, "updated_at": row.get("updated_at")}, "error": None}

    total_qty = sum(float(h.get("quantity") or 0) for h in holdings)
    if total_qty <= 0:
        weights = [1 / len(holdings) for _ in holdings]
    else:
        weights = [float(h.get("quantity") or 0) / total_qty for h in holdings]

    max_w = max(weights) if weights else 0

    # Herfindahl-Hirschman Index (0–10000): lower = more diversified
    hhi = int(sum(w ** 2 for w in weights) * 10000)
    # Normalise to 0-100 score: 100 = perfectly equal weights, 0 = single stock
    n = len(holdings)
    hhi_min = int(10000 / n) if n > 0 else 10000
    diversification_score = int(max(0, min(100, (1 - (hhi - hhi_min) / max(10000 - hhi_min, 1)) * 100)))

    sector_conc: Dict[str, float] = {}
    for h, w in zip(holdings, weights):
        sym = str(h.get("symbol") or "").upper().replace(".NS", "").replace(".BO", "")
        sector = SECTOR_HINTS.get(sym, "Other")
        sector_conc[sector] = sector_conc.get(sector, 0) + w * 100

    top_sectors = sorted(sector_conc.items(), key=lambda x: x[1], reverse=True)[:3]
    unique_sectors = len([s for s in sector_conc if s != "Other"])

    risk_factors = []
    if max_w >= 0.5:
        risk_factors.append(f"High single-stock concentration: top holding is {round(max_w * 100, 1)}% of portfolio.")
    if n <= 3:
        risk_factors.append("Limited diversification — fewer than 4 holdings.")
    if sector_conc.get("Other", 0) > 40:
        risk_factors.append("Several holdings have unknown sector — add symbols in NSE format (e.g. RELIANCE, TCS).")
    if hhi > 2500:
        risk_factors.append(f"HHI concentration index is {hhi} (above 2500 indicates high concentration).")
    if unique_sectors == 1 and n > 1:
        risk_factors.append("All holdings are in the same sector — consider cross-sector diversification.")
    if not risk_factors:
        risk_factors.append("Portfolio shows healthy diversification across holdings and sectors.")

    high_signals = db_fetchall(
        "SELECT symbol, signal_type FROM signals ORDER BY created_at DESC LIMIT 10"
    )
    high_set = {str(r.get("symbol") or "").upper() for r in high_signals if r.get("symbol")}
    overlap = [h.get("symbol") for h in holdings if str(h.get("symbol") or "").upper() in high_set][:5]

    analysis = {
        "sector_concentration_top": [{"sector": s, "pct": round(p, 2)} for s, p in top_sectors],
        "unique_sectors": unique_sectors,
        "top_risk_factors": risk_factors,
        "diversification_score": diversification_score,
        "hhi": hhi,
        "hhi_label": "Low" if hhi < 1500 else "Moderate" if hhi < 2500 else "High",
        "holdings_count": n,
        "overlap_with_high_signal_stocks": overlap,
    }

    return {
        "success": True,
        "data": {"analysis": analysis, "updated_at": row.get("updated_at")},
        "error": None,
    }

