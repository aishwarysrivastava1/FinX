# backend/services/search_service.py
"""
Smart NSE stock search with typo correction.
Uses difflib fuzzy matching — no extra dependencies required.
"""
from difflib import get_close_matches
from typing import List, Dict

# ── NSE stock master list (symbol → company name) ────────────
NSE_STOCKS: Dict[str, str] = {
    # Nifty 50 + popular mid/small caps
    'RELIANCE':    'Reliance Industries Ltd',
    'TCS':         'Tata Consultancy Services Ltd',
    'INFY':        'Infosys Ltd',
    'HDFCBANK':    'HDFC Bank Ltd',
    'ICICIBANK':   'ICICI Bank Ltd',
    'TATAMOTORS':  'Tata Motors Ltd',
    'WIPRO':       'Wipro Ltd',
    'BAJFINANCE':  'Bajaj Finance Ltd',
    'SUNPHARMA':   'Sun Pharmaceutical Industries Ltd',
    'ITC':         'ITC Ltd',
    'SBIN':        'State Bank of India',
    'ADANIENT':    'Adani Enterprises Ltd',
    'MARUTI':      'Maruti Suzuki India Ltd',
    'NESTLEIND':   'Nestle India Ltd',
    'POWERGRID':   'Power Grid Corporation of India Ltd',
    'HINDUNILVR':  'Hindustan Unilever Ltd',
    'KOTAKBANK':   'Kotak Mahindra Bank Ltd',
    'BAJAJFINSV':  'Bajaj Finserv Ltd',
    'AXISBANK':    'Axis Bank Ltd',
    'LT':          'Larsen & Toubro Ltd',
    'ASIANPAINT':  'Asian Paints Ltd',
    'HCLTECH':     'HCL Technologies Ltd',
    'TECHM':       'Tech Mahindra Ltd',
    'TITAN':       'Titan Company Ltd',
    'ULTRACEMCO':  'UltraTech Cement Ltd',
    'ONGC':        'Oil & Natural Gas Corporation Ltd',
    'NTPC':        'NTPC Ltd',
    'M&M':         'Mahindra & Mahindra Ltd',
    'BHARTIARTL':  'Bharti Airtel Ltd',
    'ADANIPORTS':  'Adani Ports and SEZ Ltd',
    'COALINDIA':   'Coal India Ltd',
    'GRASIM':      'Grasim Industries Ltd',
    'DIVISLAB':    "Divi's Laboratories Ltd",
    'DRREDDY':     "Dr. Reddy's Laboratories Ltd",
    'CIPLA':       'Cipla Ltd',
    'BAJAJ-AUTO':  'Bajaj Auto Ltd',
    'EICHERMOT':   'Eicher Motors Ltd',
    'JSWSTEEL':    'JSW Steel Ltd',
    'TATASTEEL':   'Tata Steel Ltd',
    'HINDALCO':    'Hindalco Industries Ltd',
    'BPCL':        'Bharat Petroleum Corporation Ltd',
    'INDUSINDBK':  'IndusInd Bank Ltd',
    'HEROMOTOCO':  'Hero MotoCorp Ltd',
    'APOLLOHOSP':  'Apollo Hospitals Enterprise Ltd',
    'BRITANNIA':   'Britannia Industries Ltd',
    'TATACONSUM':  'Tata Consumer Products Ltd',
    'SBILIFE':     'SBI Life Insurance Company Ltd',
    'HDFCLIFE':    'HDFC Life Insurance Company Ltd',
    'ICICIPRULI':  'ICICI Prudential Life Insurance Company Ltd',
    'PIDILITIND':  'Pidilite Industries Ltd',
    'HAVELLS':     'Havells India Ltd',
    'BERGEPAINT':  'Berger Paints India Ltd',
    'MUTHOOTFIN':  'Muthoot Finance Ltd',
    'BANDHANBNK':  'Bandhan Bank Ltd',
    'IDFCFIRSTB':  'IDFC First Bank Ltd',
    'FEDERALBNK':  'Federal Bank Ltd',
    'RBLBANK':     'RBL Bank Ltd',
    'PNB':         'Punjab National Bank',
    'BANKBARODA':  'Bank of Baroda',
    'CANARABANK':  'Canara Bank',
    'UNIONBANK':   'Union Bank of India',
    'MARICO':      'Marico Ltd',
    'DABUR':       'Dabur India Ltd',
    'COLPAL':      'Colgate-Palmolive (India) Ltd',
    'GODREJCP':    'Godrej Consumer Products Ltd',
    'EMAMILTD':    'Emami Ltd',
    'JUBLFOOD':    'Jubilant FoodWorks Ltd',
    'ZOMATO':      'Zomato Ltd',
    'NYKAA':       'FSN E-Commerce Ventures Ltd',
    'PAYTM':       'One97 Communications Ltd',
    'POLICYBZR':   'PB Fintech Ltd',
    'DELHIVERY':   'Delhivery Ltd',
    'NAUKRI':      'Info Edge (India) Ltd',
    'IRCTC':       'Indian Railway Catering and Tourism Corporation Ltd',
    'RVNL':        'Rail Vikas Nigam Ltd',
    'IRFC':        'Indian Railway Finance Corporation Ltd',
    'HAL':         'Hindustan Aeronautics Ltd',
    'BEL':         'Bharat Electronics Ltd',
    'BHEL':        'Bharat Heavy Electricals Ltd',
    'SAIL':        'Steel Authority of India Ltd',
    'NMDC':        'NMDC Ltd',
    'VEDL':        'Vedanta Ltd',
    'TATAPOWER':   'Tata Power Company Ltd',
    'TORNTPOWER':  'Torrent Power Ltd',
    'ADANIGREEN':  'Adani Green Energy Ltd',
    'ADANIPOWER':  'Adani Power Ltd',
    'SUZLON':      'Suzlon Energy Ltd',
    'INDIGO':      'InterGlobe Aviation Ltd',
    'SPICEJET':    'SpiceJet Ltd',
    'DLF':         'DLF Ltd',
    'GODREJPROP':  'Godrej Properties Ltd',
    'OBEROIRLTY':  'Oberoi Realty Ltd',
    'CHOLAFIN':    'Cholamandalam Investment and Finance Company Ltd',
    'LTIM':        'LTIMindtree Ltd',
    'LTTS':        'L&T Technology Services Ltd',
    'PERSISTENT':  'Persistent Systems Ltd',
    'COFORGE':     'Coforge Ltd',
    'MPHASIS':     'Mphasis Ltd',
    'OFSS':        'Oracle Financial Services Software Ltd',
    'KPIT':        'KPIT Technologies Ltd',
    'ZENSARTECH':  'Zensar Technologies Ltd',
    'TRENT':       'Trent Ltd',
    'VOLTAS':      'Voltas Ltd',
    'PAGEIND':     'Page Industries Ltd',
    'ABFRL':       'Aditya Birla Fashion and Retail Ltd',
    'DMART':       'Avenue Supermarts Ltd',
    'NIFTY50':     'Nifty 50 Index',
}

_ALL_SYMBOLS   = list(NSE_STOCKS.keys())
_NAME_TO_SYM   = {name.lower(): sym for sym, name in NSE_STOCKS.items()}

POPULAR_DEFAULT = ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK']


def search_stock(query: str) -> List[Dict[str, str]]:
    """
    Smart stock search with typo correction.

    Steps (in priority order):
    1. Exact symbol match
    2. Symbol prefix match
    3. Company name prefix match
    4. Symbol / name substring match
    5. Fuzzy symbol match (handles typos like "relaince" → RELIANCE)
    6. Fuzzy name match

    Returns up to 5 matches as [{symbol, name}].
    """
    if not query or not query.strip():
        return [{'symbol': s, 'name': NSE_STOCKS[s]} for s in POPULAR_DEFAULT]

    q     = query.strip().lower()
    q_up  = q.upper()

    results: List[Dict[str, str]] = []
    seen: set = set()

    def _add(sym: str):
        if sym not in seen and sym in NSE_STOCKS:
            seen.add(sym)
            results.append({'symbol': sym, 'name': NSE_STOCKS[sym]})

    # 1. Exact symbol
    if q_up in NSE_STOCKS:
        _add(q_up)

    # 2. Symbol prefix
    for sym in _ALL_SYMBOLS:
        if len(results) >= 5:
            break
        if sym.startswith(q_up):
            _add(sym)

    # 3. Company name prefix
    for sym, name in NSE_STOCKS.items():
        if len(results) >= 5:
            break
        if name.lower().startswith(q):
            _add(sym)

    # 4. Substring in symbol
    for sym in _ALL_SYMBOLS:
        if len(results) >= 5:
            break
        if q_up in sym:
            _add(sym)

    # 5. Substring in company name
    for sym, name in NSE_STOCKS.items():
        if len(results) >= 5:
            break
        if q in name.lower():
            _add(sym)

    # 6. Fuzzy symbol match — handles typos (e.g. "relaince" → RELIANCE)
    if len(results) < 5:
        fuzzy_syms = get_close_matches(q_up, _ALL_SYMBOLS, n=5, cutoff=0.5)
        for sym in fuzzy_syms:
            if len(results) >= 5:
                break
            _add(sym)

    # 7. Fuzzy company name match
    if len(results) < 5:
        name_keys  = list(_NAME_TO_SYM.keys())
        fuzzy_names = get_close_matches(q, name_keys, n=5, cutoff=0.4)
        for nk in fuzzy_names:
            if len(results) >= 5:
                break
            _add(_NAME_TO_SYM[nk])

    # Fallback: return popular stocks if nothing matched
    if not results:
        return [{'symbol': s, 'name': NSE_STOCKS[s]} for s in POPULAR_DEFAULT]

    return results[:5]
