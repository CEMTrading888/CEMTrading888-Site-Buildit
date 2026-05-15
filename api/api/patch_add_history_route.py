#!/usr/bin/env python3
"""
Patches /var/www/cemtrading888/backtest.py to add a /api/history GET endpoint.
Safe to re-run: skips if already patched.
"""
import os, sys

TARGET = '/var/www/cemtrading888/backtest.py'

MARKER = '# CEM_HISTORY_ROUTE_V1'

NEW_ROUTE = r'''
# CEM_HISTORY_ROUTE_V1
@app.get("/api/history")
async def api_history(symbol: str = "MGC", interval: str = "1d", range: str = "5y"):
    import yfinance as yf, pandas as pd
    SYMBOL_MAP = {
        "MGC": "MGC=F", "GC": "GC=F", "MES": "MES=F", "ES": "ES=F",
        "MNQ": "MNQ=F", "NQ": "NQ=F", "MBT": "BTC-USD", "BTC": "BTC-USD",
    }
    tk = SYMBOL_MAP.get(symbol.upper(), symbol.upper() + "=F")
    PERIOD_MAP = {"1y": "1y", "2y": "2y", "5y": "5y", "max": "max"}
    period = PERIOD_MAP.get(range, "5y")
    try:
        df = yf.download(tk, period=period, interval=interval,
                         auto_adjust=True, progress=False)
        if df is None or df.empty:
            return {"symbol": symbol, "bars": [], "count": 0}
        # Flatten multi-level columns if present
        if hasattr(df.columns, 'levels'):
            df.columns = df.columns.get_level_values(0)
        df = df.rename(columns=str.capitalize)
        bars = []
        for ts, row in df.iterrows():
            try:
                t = int(ts.timestamp())
                o = float(row.get('Open', row.get('open', 0)))
                h = float(row.get('High', row.get('high', 0)))
                l = float(row.get('Low', row.get('low', 0)))
                c = float(row.get('Close', row.get('close', 0)))
                v = float(row.get('Volume', row.get('volume', 0)))
                if o > 0 and h > 0 and l > 0 and c > 0:
                    bars.append({"t": t, "o": round(o,2), "h": round(h,2),
                                 "l": round(l,2), "c": round(c,2), "v": int(v)})
            except Exception:
                pass
        return {"symbol": symbol, "yahoo": tk, "bars": bars,
                "ohlcv": bars, "count": len(bars)}
    except Exception as e:
        return {"symbol": symbol, "bars": [], "ohlcv": [], "count": 0, "error": str(e)}

@app.get("/api/history/ping")
async def history_ping():
    return {"ok": True, "route": "history"}
'''

if not os.path.exists(TARGET):
    print(f"ERROR: {TARGET} not found", file=sys.stderr)
    sys.exit(1)

src = open(TARGET).read()

if MARKER in src:
    print("ALREADY PATCHED — nothing to do")
    sys.exit(0)

# Find a good insertion point: after the last @app route or before if __name__
insert_pos = src.rfind('\nif __name__')
if insert_pos == -1:
    insert_pos = len(src)

patched = src[:insert_pos] + NEW_ROUTE + src[insert_pos:]
open(TARGET, 'w').write(patched)
print(f"PATCHED OK — added /api/history to {TARGET}")
