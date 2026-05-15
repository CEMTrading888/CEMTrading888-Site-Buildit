#!/usr/bin/env python3
"""
inject_history.py — injects /api/history routes into main.py on the server.
Writes all output to a web-accessible log file for remote debugging.
"""
import os, sys, ast, subprocess, textwrap, stat, re

LOG = '/var/www/cemtrading888/inject_log.txt'
TARGET = '/var/www/cemtrading888/main.py'

def log(msg):
    print(msg)
    try:
        with open(LOG, 'a') as f:
            f.write(msg + '\n')
    except Exception:
        pass

# Clear log on each run
try:
    open(LOG, 'w').close()
except Exception:
    pass

log("=== inject_history.py START ===")
log(f"uid={os.getuid()} gid={os.getgid()}")
try:
    import pwd
    log(f"user={pwd.getpwuid(os.getuid()).pw_name}")
except Exception:
    pass

if not os.path.exists(TARGET):
    log(f"ERROR: {TARGET} not found")
    try:
        log(f"Contents of /var/www/cemtrading888/: {os.listdir('/var/www/cemtrading888/')}")
    except Exception as e:
        log(f"listdir: {e}")
    sys.exit(1)

log(f"TARGET: {TARGET}")

try:
    fstat = os.stat(TARGET)
    log(f"mode={oct(stat.S_IMODE(fstat.st_mode))} uid={fstat.st_uid} size={fstat.st_size}")
    log(f"writable: {os.access(TARGET, os.W_OK)}")
except Exception as e:
    log(f"stat: {e}")

try:
    src = open(TARGET).read()
    log(f"Read {len(src)} bytes OK")
except Exception as e:
    log(f"READ FAILED: {e}")
    sys.exit(1)

# Strip any previous injection block
START_MARKER = '# === CEM_HISTORY_INJECT_START ==='
END_MARKER   = '# === CEM_HISTORY_INJECT_END ==='
if START_MARKER in src and END_MARKER in src:
    before = src[:src.index(START_MARKER)]
    after = src[src.index(END_MARKER) + len(END_MARKER):]
    src = before + after
    log("Stripped previous injection block")

# Strip old V1 marker if present
OLD_MARKER = '# CEM_HISTORY_ROUTE_V1'
if OLD_MARKER in src:
    idx = src.index(OLD_MARKER)
    safe_end = len(src)
    for m in re.finditer(r'\nif __name__', src[idx:]):
        safe_end = idx + m.start()
        break
    log(f"Stripped old V1 marker ({safe_end - idx} chars)")
    src = src[:idx] + src[safe_end:]

NEW_ROUTE = textwrap.dedent("""

# === CEM_HISTORY_INJECT_START ===
@app.get("/api/history/ping")
async def history_ping():
    return {"ok": True, "route": "history_v3"}

@app.get("/api/history")
async def api_history(symbol: str = "MGC", interval: str = "1d", range: str = "5y"):
    import yfinance as yf
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
            return {"symbol": symbol, "bars": [], "ohlcv": [], "count": 0}
        if hasattr(df.columns, "levels"):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.capitalize() for c in df.columns]
        bars = []
        for ts, row in df.iterrows():
            try:
                t = int(ts.timestamp())
                o = float(row.get("Open", 0))
                h = float(row.get("High", 0))
                lv = float(row.get("Low", 0))
                c = float(row.get("Close", 0))
                v = float(row.get("Volume", 0))
                if o > 0 and h > 0 and lv > 0 and c > 0:
                    bars.append({"t": t, "o": round(o, 2), "h": round(h, 2),
                                 "l": round(lv, 2), "c": round(c, 2), "v": int(v)})
            except Exception:
                pass
        return {"symbol": symbol, "yahoo": tk, "bars": bars, "ohlcv": bars, "count": len(bars)}
    except Exception as e:
        return {"symbol": symbol, "bars": [], "ohlcv": [], "count": 0, "error": str(e)}
# === CEM_HISTORY_INJECT_END ===
""")

# Insert before `if __name__` block, or append at end
insert_pos = src.rfind('\nif __name__')
if insert_pos == -1:
    insert_pos = len(src)
    log("No 'if __name__' found — appending at end")
else:
    log(f"Inserting before 'if __name__' at pos {insert_pos}")

patched = src[:insert_pos] + NEW_ROUTE + src[insert_pos:]

try:
    ast.parse(patched)
    log("SYNTAX OK")
except SyntaxError as e:
    log(f"SYNTAX ERROR: {e}")
    lines = patched.split('\n')
    start = max(0, (e.lineno or 1) - 3)
    end = min(len(lines), (e.lineno or 1) + 3)
    for i, ln in enumerate(lines[start:end], start=start + 1):
        log(f"  {i}: {ln}")
    sys.exit(1)

try:
    open(TARGET, 'w').write(patched)
    log(f"INJECT OK — wrote {len(patched)} bytes to {TARGET}")
except Exception as e:
    log(f"WRITE FAILED: {e}")
    sys.exit(1)

try:
    result = subprocess.run(['pkill', '-f', 'uvicorn'], capture_output=True, text=True)
    log(f"pkill uvicorn: exit={result.returncode}")
except Exception as e:
    log(f"pkill: {e}")

log("=== DONE ===")
