#!/usr/bin/env python3
"""
inject_candles_databento.py - injects GET /api/candles into main.py on the server.
"""
import ast
import os
import sys
import textwrap

LOG = "/var/www/cemtrading888/inject_candles_databento_log.txt"
TARGET = os.environ.get("CEM_TARGET_MAIN", "/var/www/cemtrading888/main.py")


def log(msg: str) -> None:
    print(msg)
    try:
        with open(LOG, "a", encoding="utf-8") as handle:
            handle.write(msg + "\n")
    except Exception:
        pass


try:
    open(LOG, "w", encoding="utf-8").close()
except Exception:
    pass

log("=== inject_candles_databento.py START ===")

if not os.path.exists(TARGET):
    log(f"ERROR: {TARGET} not found - skip candles inject")
    sys.exit(0)

try:
    src = open(TARGET, encoding="utf-8").read()
except Exception as exc:
    log(f"READ FAILED: {exc}")
    sys.exit(1)

START_MARKER = "# === CEM_DATABENTO_CANDLES_INJECT_START ==="
END_MARKER = "# === CEM_DATABENTO_CANDLES_INJECT_END ==="
if START_MARKER in src and END_MARKER in src:
    before = src[: src.index(START_MARKER)]
    after = src[src.index(END_MARKER) + len(END_MARKER) :]
    src = before + after
    log("Stripped previous Databento candles injection block")

NEW_ROUTE = textwrap.dedent(
    """

# === CEM_DATABENTO_CANDLES_INJECT_START ===
import csv as _cem_candles_csv
import os as _cem_candles_os
import subprocess as _cem_candles_subprocess
import time as _cem_candles_time
from pathlib import Path as _cem_candles_Path
from fastapi.responses import JSONResponse as _cem_candles_JSONResponse

_CEM_CANDLES_DATA_DIR = _cem_candles_Path("/home/lean-data/futures")
_CEM_CANDLES_FETCH_SCRIPT = _cem_candles_Path("/home/lean-workspace/fetch_futures_data.py")
_CEM_CANDLES_FETCH_PYTHON = _cem_candles_Path("/home/lean-workspace/.venv/bin/python")
_CEM_CANDLES_ENV_FILE = _cem_candles_Path("/var/www/cemtrading888/.env")
_CEM_CANDLES_CONFIG_FILE = _cem_candles_Path("/home/lean-workspace/config/databento_config.py")
_CEM_CANDLES_CACHE = {}
_CEM_CANDLES_CACHE_TTL = float((_cem_candles_os.getenv("CEM_CANDLES_CACHE_TTL") or "300").strip() or "300")
_CEM_CANDLES_SYMBOLS = {"MGC", "MES", "MNQ", "MCL", "MSI", "M2K", "MYM"}
_CEM_CANDLES_RESOLUTION_MAP = {"D": "daily", "1D": "daily", "DAILY": "daily"}


def _cem_candles_clean(symbol: str) -> str:
    return "".join(ch for ch in str(symbol or "").upper() if ch.isalnum() or ch in "-_")


def _cem_candles_resolution(resolution: str) -> str:
    clean = str(resolution or "D").strip().upper()
    return _CEM_CANDLES_RESOLUTION_MAP.get(clean, "")


def _cem_candles_csv_path(symbol: str, resolution: str = "daily"):
    return _CEM_CANDLES_DATA_DIR / f"{symbol}_{resolution}.csv"


def _cem_candles_load_key() -> str:
    key = (_cem_candles_os.getenv("DATABENTO_API_KEY") or "").strip()
    if key and key != "YOUR_KEY_HERE":
        return key
    if _CEM_CANDLES_ENV_FILE.exists():
        try:
            for line in _CEM_CANDLES_ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                env_key, env_value = stripped.split("=", 1)
                if env_key.strip() == "DATABENTO_API_KEY":
                    key = env_value.strip()
                    break
        except Exception:
            key = ""
    if key and key != "YOUR_KEY_HERE":
        return key
    if _CEM_CANDLES_CONFIG_FILE.exists():
        namespace = {}
        try:
            exec(_CEM_CANDLES_CONFIG_FILE.read_text(encoding="utf-8"), {}, namespace)
            key = str(namespace.get("DATABENTO_API_KEY") or "").strip()
        except Exception:
            key = ""
    if key and key != "YOUR_KEY_HERE":
        return key
    return ""


def _cem_candles_read_csv(path, count: int):
    rows = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = _cem_candles_csv.DictReader(handle)
        for row in reader:
            try:
                t = int(float(row.get("t") or row.get("timestamp") or row.get("time") or 0))
                o = float(row.get("o") or row.get("open"))
                h = float(row.get("h") or row.get("high"))
                l = float(row.get("l") or row.get("low"))
                c = float(row.get("c") or row.get("close"))
                v = int(float(row.get("v") or row.get("volume") or 0))
            except Exception:
                continue
            rows.append({"t": t, "o": round(o, 6), "h": round(h, 6), "l": round(l, 6), "c": round(c, 6), "v": v})
    rows.sort(key=lambda item: item["t"])
    if count > 0:
        rows = rows[-count:]
    return rows


def _cem_candles_fetch_symbol(symbol: str, start: str = "2020-01-01"):
    key = _cem_candles_load_key()
    if not key:
        raise RuntimeError(
            "DATABENTO_API_KEY is missing. Add it to /var/www/cemtrading888/.env "
            "or /home/lean-workspace/config/databento_config.py."
        )
    if not _CEM_CANDLES_FETCH_SCRIPT.exists():
        raise RuntimeError(f"Missing Databento fetch script: {_CEM_CANDLES_FETCH_SCRIPT}")
    if not _CEM_CANDLES_FETCH_PYTHON.exists():
        raise RuntimeError(f"Missing LEAN workspace Python: {_CEM_CANDLES_FETCH_PYTHON}")
    env = dict(_cem_candles_os.environ)
    env["DATABENTO_API_KEY"] = key
    proc = _cem_candles_subprocess.run(
        [str(_CEM_CANDLES_FETCH_PYTHON), str(_CEM_CANDLES_FETCH_SCRIPT), "--symbol", symbol, "--start", start],
        capture_output=True,
        text=True,
        timeout=240,
        env=env,
    )
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(message or f"Databento fetcher exited with code {proc.returncode}")


def _cem_candles_get_bars(symbol: str, resolution: str, count: int, refresh: bool = False, start: str = "2020-01-01"):
    clean = _cem_candles_clean(symbol) or "MGC"
    if clean not in _CEM_CANDLES_SYMBOLS:
        raise ValueError(f"Unsupported futures symbol: {clean}")
    resolution_key = _cem_candles_resolution(resolution)
    if not resolution_key:
        raise ValueError(f"Unsupported resolution: {resolution}")
    safe_count = max(int(count or 0), 1)
    cache_key = f"{clean}:{resolution_key}:{safe_count}:{int(bool(refresh))}"
    now = _cem_candles_time.time()
    cached = _CEM_CANDLES_CACHE.get(cache_key)
    if cached and now - cached.get("ts", 0) < _CEM_CANDLES_CACHE_TTL:
        return cached.get("bars") or []
    path = _cem_candles_csv_path(clean, resolution_key)
    if refresh or not path.exists():
        _cem_candles_fetch_symbol(clean, start=start)
    if not path.exists():
        raise FileNotFoundError(f"Databento CSV not found for {clean}: {path}")
    bars = _cem_candles_read_csv(path, safe_count)
    if not bars:
        raise RuntimeError(f"Databento CSV exists but contains no bars: {path}")
    _CEM_CANDLES_CACHE[cache_key] = {"ts": now, "bars": bars}
    return bars


@app.get("/api/candles")
async def api_candles(symbol: str = "MGC", resolution: str = "D", count: int = 1260, refresh: int = 0, start: str = "2020-01-01"):
    clean = _cem_candles_clean(symbol) or "MGC"
    try:
        bars = _cem_candles_get_bars(clean, resolution, count, bool(int(refresh or 0)), start=start)
    except ValueError as exc:
        return _cem_candles_JSONResponse({"success": False, "symbol": clean, "error": str(exc)}, status_code=400)
    except FileNotFoundError as exc:
        return _cem_candles_JSONResponse({"success": False, "symbol": clean, "error": str(exc)}, status_code=404)
    except RuntimeError as exc:
        return _cem_candles_JSONResponse({"success": False, "symbol": clean, "error": str(exc)}, status_code=503)
    except Exception as exc:
        return _cem_candles_JSONResponse(
            {"success": False, "symbol": clean, "error": f"Databento candles fetch failed: {exc}"},
            status_code=502,
        )
    return {
        "success": True,
        "symbol": clean,
        "resolution": _cem_candles_resolution(resolution),
        "count": len(bars),
        "bars": bars,
    }
# === CEM_DATABENTO_CANDLES_INJECT_END ===
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
except SyntaxError as exc:
    log(f"SYNTAX ERROR: {exc}")
    lines = patched.split("\n")
    start = max(0, (exc.lineno or 1) - 3)
    end = min(len(lines), (exc.lineno or 1) + 3)
    for idx, line in enumerate(lines[start:end], start=start + 1):
        log(f"  {idx}: {line}")
    sys.exit(1)

try:
    open(TARGET, "w", encoding="utf-8").write(patched)
    log(f"INJECT OK - wrote {len(patched)} bytes")
except Exception as exc:
    log(f"WRITE FAILED: {exc}")
    sys.exit(1)

log("=== DONE ===")
