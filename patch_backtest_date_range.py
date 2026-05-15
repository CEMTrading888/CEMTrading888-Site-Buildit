#!/usr/bin/env python3
"""
Apply on server after deploying index.html Phase 1 date range (March 29 2026 spec).

Legacy helper for POST /api/backtest-replay JSON to optionally include:
  start_date, end_date (YYYY-MM-DD)
  backtest_period_filter: "" | "fed_weeks" | "earnings"  (optional; fed/earnings filtering TBD)

Patches typical yfinance flows: after df is loaded, if start_date and end_date are present,
slice the index. Adjust file path for your deployment.
"""
from __future__ import annotations

import os
import re
import sys

CANDIDATES = [
    "/var/www/cemtrading888/backtest.py",
    "/home/cemtrading888/backtest.py",
    "/opt/cemtrading888/backtest.py",
    "/app/backtest.py",
]


def main() -> int:
    path = os.environ.get("BACKTEST_PY_PATH", "")
    if not path:
        for c in CANDIDATES:
            if os.path.isfile(c):
                path = c
                break
    if not path or not os.path.isfile(path):
        print("backtest.py not found; set BACKTEST_PY_PATH", file=sys.stderr)
        return 1

    src = open(path, encoding="utf-8", errors="replace").read()
    marker = "# CEM_DATE_RANGE_FILTER"
    if marker in src:
        print("Already patched:", path)
        return 0

    # Insert after first plausible dataframe assignment (df = ...)
    m = re.search(r"^(\s*df\s*=\s*yf\.download\([^\n]+\)\s*$)", src, re.MULTILINE)
    if not m:
        m = re.search(r"^(\s*df\s*=\s*.+$)", src, re.MULTILINE)
    if not m:
        print("Could not find df = ... line in", path, file=sys.stderr)
        return 1

    indent = re.match(r"^(\s*)", m.group(1)).group(1)
    block = f"""
{indent}{marker}
{indent}_sd = body.get("start_date") or body.get("start")
{indent}_ed = body.get("end_date") or body.get("end")
{indent}if _sd and _ed:
{indent}    try:
{indent}        import pandas as pd
{indent}        _s = pd.Timestamp(_sd)
{indent}        _e = pd.Timestamp(_ed)
{indent}        df = df[(df.index >= _s) & (df.index <= _e)]
{indent}    except Exception:
{indent}        pass
{indent}_bpf = body.get("backtest_period_filter") or ""
{indent}if _bpf == "fed_weeks":
{indent}    pass
{indent}elif _bpf == "earnings":
{indent}    pass
"""
    insert_at = m.end()
    new_src = src[:insert_at] + block + src[insert_at:]
    open(path, "w", encoding="utf-8").write(new_src)
    print("Patched:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
