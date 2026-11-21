"""Curated, Yahoo-verified NSE/BSE symbol catalog for the trading terminal.

These symbols drive both the Markets symbol picker and the TradingView chart
picker. They are separate from the live Yahoo watchlist, so the wider universe
does not slow down background polling or ML training.
"""

from typing import Any, Dict, List

# Indices confirmed available from Yahoo Finance spark.
INDICES: List[Dict[str, str]] = [
    {"symbol": "^NSEI", "name": "NIFTY 50", "exchange": "NSE"},
    {"symbol": "^NSEBANK", "name": "NIFTY BANK", "exchange": "NSE"},
    {"symbol": "^BSESN", "name": "BSE SENSEX", "exchange": "BSE"},
]

# All major Indian banks listed on NSE that Yahoo currently serves.
NSE_BANKS: List[str] = [
    "HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK",
    "FEDERALBNK", "BANKBARODA", "PNB", "CANBK", "UNIONBANK", "IDFCFIRSTB",
    "BANDHANBNK", "RBLBANK", "YESBANK", "IDBI", "INDIANB", "CENTRALBK",
    "KARURVYSYA", "BANKINDIA", "DHANLAXMI", "UCOBANK", "MAHABANK", "DCBBANK",
]

# Liquid NSE companies (large/mid caps across sectors, including NIFTY 50 names).
NSE_COMPANIES: List[str] = [
    "RELIANCE", "TCS", "INFY", "HCLTECH", "WIPRO", "TMPV", "BHARTIARTL", "LT",
    "HINDUNILVR", "ITC", "MARUTI", "ASIANPAINT", "DMART", "SUNPHARMA",
    "NESTLEIND", "TITAN", "ULTRACEMCO", "M&M", "BAJFINANCE", "BAJAJFINSV",
    "HDFCLIFE", "SBILIFE", "ICICIGI", "SHREECEM", "ONGC", "NTPC", "POWERGRID",
    "TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "COALINDIA", "DRREDDY", "CIPLA",
    "DIVISLAB", "BAJAJ-AUTO", "EICHERMOT", "TVSMOTOR", "HEROMOTOCO", "BOSCHLTD",
    "SIEMENS", "ABB", "LUPIN", "AUROPHARMA", "ALKEM", "TORNTPHARM", "MANKIND",
    "CONCOR", "ADANIENT", "ADANIPORTS", "ADANIGREEN", "TATAPOWER", "TATACONSUM",
    "VOLTAS", "CROMPTON", "HAVELLS", "DIXON", "KAYNES", "PERSISTENT", "MPHASIS",
    "TECHM", "TATAELXSI", "CHOLAFIN", "SHRIRAMFIN", "LICHSGFIN", "PFC", "RECLTD",
    "IRFC", "NHPC", "SJVN", "CUMMINSIND", "THERMAX", "BHEL", "BEL", "HAL",
    "GRASIM", "ACC", "AMBUJACEM", "JKCEMENT", "RAMCOCEM", "NYKAA", "TRENT",
    "INDIGO", "IRCTC", "RAILTEL", "RVNL", "NBCC", "KIRLOSENG", "TATACHEM",
    "APOLLOHOSP", "MAXHEALTH", "FORTIS", "METROPOLIS", "LALPATHLAB", "POLYMED",
]

# Yahoo-verified BSE listings for the same bellwether names.
BSE_COMPANIES: List[str] = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "SBIN", "INFY", "ITC", "LT",
    "BAJFINANCE", "HINDUNILVR", "MARUTI", "ASIANPAINT", "SUNPHARMA", "TATASTEEL",
    "ADANIENT", "HCLTECH", "WIPRO", "BHARTIARTL", "KOTAKBANK", "AXISBANK",
    "NESTLEIND", "TITAN", "ULTRACEMCO", "M&M", "BAJAJFINSV", "HDFCLIFE", "SBILIFE",
    "ICICIGI", "SHREECEM", "ONGC", "NTPC", "POWERGRID", "JSWSTEEL", "HINDALCO",
    "VEDL", "COALINDIA", "DRREDDY", "CIPLA", "DIVISLAB", "BAJAJ-AUTO", "EICHERMOT",
    "TVSMOTOR", "HEROMOTOCO", "BOSCHLTD", "SIEMENS", "VOLTAS", "HAVELLS", "DIXON",
    "CHOLAFIN", "SHRIRAMFIN", "IRFC", "NHPC", "BHEL", "BEL", "HAL", "GRASIM", "ACC",
    "TRENT", "INDIGO", "IRCTC", "APOLLOHOSP", "MAXHEALTH", "DMART", "TATAPOWER",
    "TATACONSUM", "ADANIPORTS", "ADANIGREEN", "TECHM", "PERSISTENT", "MPHASIS",
    "TATAELXSI", "CUMMINSIND", "JKCEMENT", "AMBUJACEM",
]


def _tv_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if s == "^NSEI":
        return "NSE:NIFTY50"
    if s == "^NSEBANK":
        return "NSE:BANKNIFTY"
    if s == "^BSESN":
        return "BSE:SENSEX"
    if s.endswith(".NS"):
        return "NSE:" + s[:-3]
    if s.endswith(".BO"):
        return "BSE:" + s[:-3]
    return "NSE:" + s


def _entries(symbols: List[str], suffix: str, exchange: str) -> List[Dict[str, str]]:
    return [
        {
            "symbol": f"{symbol}{suffix}",
            "name": symbol,
            "exchange": exchange,
            "tv_symbol": _tv_symbol(f"{symbol}{suffix}"),
        }
        for symbol in dict.fromkeys(symbols)
    ]


def market_catalog() -> Dict[str, Any]:
    indices = [{**item, "tv_symbol": _tv_symbol(item["symbol"])} for item in INDICES]
    groups = {
        "indices": indices,
        "banks": _entries(NSE_BANKS, ".NS", "NSE"),
        "nse_companies": _entries(NSE_COMPANIES, ".NS", "NSE"),
        "bse_companies": _entries(BSE_COMPANIES, ".BO", "BSE"),
    }
    return {
        **groups,
        "total": sum(len(items) for items in groups.values()),
        "note": "Yahoo-verified NSE/BSE symbols driving both Markets and TradingView pickers. TradingView's own symbol search is also available inside the chart.",
    }
