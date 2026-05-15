#!/usr/bin/env python3
"""
inject_prices.py - injects GET /api/prices into main.py on the server.

On the droplet (after push to main), path must be api/ on GitHub:
  curl -s https://raw.githubusercontent.com/CEMTrading888/cem-bot-builder/main/api/inject_prices.py | python3
"""
import ast
import os
import sys
import textwrap

LOG = "/var/www/cemtrading888/inject_prices_log.txt"
TARGET = "/var/www/cemtrading888/main.py"


def log(msg: str) -> None:
    print(msg)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


try:
    open(LOG, "w", encoding="utf-8").close()
except Exception:
    pass

log("=== inject_prices.py START ===")

if not os.path.exists(TARGET):
    log(f"ERROR: {TARGET} not found - skip prices inject")
    sys.exit(0)

try:
    src = open(TARGET, encoding="utf-8").read()
except Exception as e:
    log(f"READ FAILED: {e}")
    sys.exit(1)

START_MARKER = "# === CEM_PRICES_INJECT_START ==="
END_MARKER = "# === CEM_PRICES_INJECT_END ==="
if START_MARKER in src and END_MARKER in src:
    before = src[: src.index(START_MARKER)]
    after = src[src.index(END_MARKER) + len(END_MARKER) :]
    src = before + after
    log("Stripped previous prices injection block")

NEW_ROUTE = textwrap.dedent(
    """

# === CEM_PRICES_INJECT_START ===
import json as _cem_prices_json
import os as _cem_prices_os
import time as _cem_prices_time
import urllib.parse as _cem_prices_up
import urllib.request as _cem_prices_uq

_CEM_PRICE_CACHE = {}
_CEM_PRICE_CACHE_TTL = float((_cem_prices_os.getenv("CEM_PRICES_CACHE_TTL") or "10").strip() or "10")
_CEM_HISTORY_CACHE = {}
_CEM_HISTORY_CACHE_TTL = float((_cem_prices_os.getenv("CEM_HISTORY_CACHE_TTL") or "900").strip() or "900")
_CEM_PRICE_SYMBOL_MAP = {
    "MGC": (_cem_prices_os.getenv("FINNHUB_SYMBOL_MGC") or "MGC").strip() or "MGC",
    "MES": (_cem_prices_os.getenv("FINNHUB_SYMBOL_MES") or "MES").strip() or "MES",
    "MNQ": (_cem_prices_os.getenv("FINNHUB_SYMBOL_MNQ") or "MNQ").strip() or "MNQ",
    "GC": (_cem_prices_os.getenv("FINNHUB_SYMBOL_GC") or "GC").strip() or "GC",
    "CL": (_cem_prices_os.getenv("FINNHUB_SYMBOL_CL") or "CL").strip() or "CL",
}
_CEM_HISTORY_SYMBOL_MAP = {
    "MGC": "MGC=F",
    "MES": "MES=F",
    "MNQ": "MNQ=F",
    "MYM": "MYM=F",
    "M2K": "M2K=F",
    "MCL": "MCL=F",
    "GC": "GC=F",
    "ES": "ES=F",
    "NQ": "NQ=F",
    "CL": "CL=F",
    "BRK.B": "BRK-B",
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "USD/CHF": "USDCHF=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CAD": "USDCAD=X",
    "NZD/USD": "NZDUSD=X",
    "EUR/GBP": "EURGBP=X",
    "EUR/JPY": "EURJPY=X",
    "GBP/JPY": "GBPJPY=X",
    "AUD/JPY": "AUDJPY=X",
    "USD/MXN": "USDMXN=X",
    "USD/ZAR": "USDZAR=X",
    "USD/INR": "USDINR=X",
    "USD/CNH": "USDCNH=X",
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "BNB": "BNB-USD",
    "XRP": "XRP-USD",
    "ADA": "ADA-USD",
    "AVAX": "AVAX-USD",
    "DOGE": "DOGE-USD",
    "MATIC": "MATIC-USD",
    "DOT": "DOT-USD",
    "LINK": "LINK-USD",
    "UNI": "UNI-USD",
    "LTC": "LTC-USD",
    "BCH": "BCH-USD",
    "ATOM": "ATOM-USD",
    "NEAR": "NEAR-USD",
    "APT": "APT-USD",
    "ARB": "ARB-USD",
    "OP": "OP-USD",
    "PEPE": "PEPE-USD",
    "SHIB": "SHIB-USD",
    "SPY": "SPY",
    "QQQ": "QQQ",
}
_CEM_HISTORY_INTERVALS = {"1d", "1wk", "1mo", "1h", "30m", "15m", "5m", "1m"}
_CEM_HISTORY_RANGES = {"1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max", "ytd"}
_CEM_ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co/query"
_CEM_TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"
_CEM_COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
_CEM_CFTC_COT_BASE_URL = (
    (_cem_prices_os.getenv("CFTC_COT_BASE_URL") or "https://publicreporting.cftc.gov").strip()
    or "https://publicreporting.cftc.gov"
)

def _cem_prices_token():
    return (
        (_cem_prices_os.getenv("FINNHUB_API_KEY") or "").strip()
        or (_cem_prices_os.getenv("FINNHUB_TOKEN") or "").strip()
        or (_cem_prices_os.getenv("FINNHUB_KEY") or "").strip()
    )

def _cem_prices_clean(symbol: str) -> str:
    return "".join(ch for ch in str(symbol or "").upper() if ch.isalnum() or ch in "/=._-")

def _cem_prices_env_key(symbol: str) -> str:
    safe = []
    for ch in symbol:
        safe.append(ch if ch.isalnum() else "_")
    return "FINNHUB_SYMBOL_" + "".join(safe)

def _cem_history_symbol(symbol: str) -> str:
    clean = _cem_prices_clean(symbol) or "MGC"
    mapped = (_CEM_HISTORY_SYMBOL_MAP.get(clean) or clean).strip()
    if not mapped:
        return "MGC=F"
    return mapped

def _cem_prices_truthy(value) -> bool:
    return str(value or "").strip().lower() not in {"", "0", "false", "no", "off"}

def _cem_market_data_provider_status():
    alpha_key = (_cem_prices_os.getenv("ALPHA_VANTAGE_KEY") or "").strip()
    twelve_key = (_cem_prices_os.getenv("TWELVE_DATA_KEY") or "").strip()
    coingecko_key = (_cem_prices_os.getenv("COINGECKO_KEY") or "").strip()
    return {
        "alpha_vantage": {
            "configured": bool(alpha_key),
            "key_env": "ALPHA_VANTAGE_KEY",
            "base_url": _CEM_ALPHA_VANTAGE_BASE_URL,
            "auth": {"query_param": "apikey"},
        },
        "twelve_data": {
            "configured": bool(twelve_key),
            "key_env": "TWELVE_DATA_KEY",
            "base_url": _CEM_TWELVE_DATA_BASE_URL,
            "auth": {"query_param": "apikey", "authorization_prefix": "apikey "},
        },
        "coingecko": {
            "configured": bool(coingecko_key),
            "key_env": "COINGECKO_KEY",
            "base_url": _CEM_COINGECKO_BASE_URL,
            "auth": {"header": "x-cg-demo-api-key", "query_param": "x_cg_demo_api_key"},
        },
        "cftc_cot": {
            "configured": True,
            "key_env": None,
            "base_url": _CEM_CFTC_COT_BASE_URL,
            "auth": {"type": "public"},
        },
    }

def _cem_prices_fetch_one(symbol: str):
    token = _cem_prices_token()
    if not token:
        return None
    env_key = _cem_prices_env_key(symbol)
    mapped = (_cem_prices_os.getenv(env_key) or _CEM_PRICE_SYMBOL_MAP.get(symbol) or symbol).strip()
    if not mapped:
        return None
    now = _cem_prices_time.time()
    cached = _CEM_PRICE_CACHE.get(symbol)
    if cached and now - cached.get("ts", 0) < _CEM_PRICE_CACHE_TTL:
        return cached.get("data")
    qs = _cem_prices_up.urlencode({"symbol": mapped, "token": token})
    req = _cem_prices_uq.Request(
        f"https://finnhub.io/api/v1/quote?{qs}",
        headers={"Accept": "application/json", "User-Agent": "CEMTrading888/1.0"},
        method="GET",
    )
    try:
        with _cem_prices_uq.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8")
    except Exception:
        return None
    try:
        payload = _cem_prices_json.loads(raw)
        price = float(payload.get("c"))
        change_pct = float(payload.get("dp"))
    except Exception:
        return None
    if price <= 0:
        return None
    data = {
        "price": round(price, 4 if abs(price) < 1 else 2),
        "change_pct": round(change_pct, 4),
    }
    _CEM_PRICE_CACHE[symbol] = {"ts": now, "data": data}
    return data

def _cem_prices_fetch_history(symbol: str, interval: str = "1d", range: str = "5y"):
    clean = _cem_prices_clean(symbol) or "MGC"
    interval = (interval or "1d").strip()
    range = (range or "5y").strip()
    if interval not in _CEM_HISTORY_INTERVALS:
        interval = "1d"
    if range not in _CEM_HISTORY_RANGES:
        range = "5y"
    cache_key = f"{clean}:{interval}:{range}"
    now = _cem_prices_time.time()
    cached = _CEM_HISTORY_CACHE.get(cache_key)
    if cached and now - cached.get("ts", 0) < _CEM_HISTORY_CACHE_TTL:
        return cached.get("data")
    yahoo = _cem_history_symbol(clean)
    qs = _cem_prices_up.urlencode({"interval": interval, "range": range})
    req = _cem_prices_uq.Request(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{_cem_prices_up.quote(yahoo, safe='')}?{qs}",
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 CEMTrading888/1.0",
        },
        method="GET",
    )
    try:
        with _cem_prices_uq.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
        payload = _cem_prices_json.loads(raw)
        result = ((payload or {}).get("chart") or {}).get("result") or []
        first = result[0] if result else {}
        timestamps = first.get("timestamp") or []
        quotes = (((first.get("indicators") or {}).get("quote") or [{}])[0]) or {}
        opens = quotes.get("open") or []
        highs = quotes.get("high") or []
        lows = quotes.get("low") or []
        closes = quotes.get("close") or []
        volumes = quotes.get("volume") or []
        bars = []
        for idx, ts in enumerate(timestamps):
            try:
                o = opens[idx]
                h = highs[idx]
                l = lows[idx]
                c = closes[idx]
                if None in (o, h, l, c):
                    continue
                if not all(isinstance(v, (int, float)) for v in (o, h, l, c)):
                    continue
                volume = volumes[idx] if idx < len(volumes) and isinstance(volumes[idx], (int, float)) else 0
                bars.append({
                    "t": int(ts),
                    "o": round(float(o), 6),
                    "h": round(float(h), 6),
                    "l": round(float(l), 6),
                    "c": round(float(c), 6),
                    "v": int(volume),
                })
            except Exception:
                continue
        data = {"symbol": clean, "yahoo": yahoo, "interval": interval, "range": range, "bars": bars, "ohlcv": bars, "count": len(bars)}
    except Exception as exc:
        data = {"symbol": clean, "yahoo": yahoo, "interval": interval, "range": range, "bars": [], "ohlcv": [], "count": 0, "error": str(exc)}
    _CEM_HISTORY_CACHE[cache_key] = {"ts": now, "data": data}
    return data

@app.get("/api/prices")
async def api_prices(symbols: str = "MGC,MES,MNQ,GC,CL", symbol: str = "", interval: str = "1d", range: str = "5y", ohlcv: int = 0):
    if _cem_prices_truthy(ohlcv) or _cem_prices_clean(symbol):
        return _cem_prices_fetch_history(symbol or "MGC", interval, range)
    out = {}
    seen = set()
    for raw in str(symbols or "").split(","):
        symbol = _cem_prices_clean(raw)
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        quote = _cem_prices_fetch_one(symbol)
        if quote is not None:
            out[symbol] = quote
        if len(seen) >= 25:
            break
    return out

@app.get("/api/market-data/providers")
async def api_market_data_providers():
    providers = _cem_market_data_provider_status()
    return {
        "providers": providers,
        "configured_count": sum(1 for provider in providers.values() if provider.get("configured")),
    }
# === CEM_PRICES_INJECT_END ===
"""
)

insert_pos = src.rfind("\nif __name__")
if insert_pos == -1:
    insert_pos = len(src)
    log("No 'if __name__' found - appending at end")
else:
    log(f"Inserting before 'if __name__' at pos {insert_pos}")

patched = src[:insert_pos] + NEW_ROUTE + src[insert_pos:]

try:
    ast.parse(patched)
    log("SYNTAX OK")
except SyntaxError as e:
    log(f"SYNTAX ERROR: {e}")
    lines = patched.split("\n")
    start = max(0, (e.lineno or 1) - 3)
    end = min(len(lines), (e.lineno or 1) + 3)
    for i, ln in enumerate(lines[start:end], start=start + 1):
        log(f"  {i}: {ln}")
    sys.exit(1)

try:
    open(TARGET, "w", encoding="utf-8").write(patched)
    log(f"INJECT OK - wrote {len(patched)} bytes")
except Exception as e:
    log(f"WRITE FAILED: {e}")
    sys.exit(1)

log("=== DONE ===")
