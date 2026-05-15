#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path("/home/lean-data/futures")
CONFIG_PATH = Path("/home/lean-workspace/config/databento_config.py")

FUTURES_SYMBOLS = {
    "MGC": "Micro Gold",
    "MES": "Micro S&P 500",
    "MNQ": "Micro Nasdaq 100",
    "MCL": "Micro Crude Oil",
    "MSI": "Micro Silver",
    "M2K": "Micro Russell 2000",
    "MYM": "Micro Dow Jones",
}

PARENT_SYMBOLS = {
    "MGC": "MGC.FUT",
    "MES": "MES.FUT",
    "MNQ": "MNQ.FUT",
    "MCL": "MCL.FUT",
    "MSI": "SIL.FUT",
    "M2K": "M2K.FUT",
    "MYM": "MYM.FUT",
}


def load_api_key() -> str:
    key = (os.environ.get("DATABENTO_API_KEY") or "").strip()
    if key and key != "YOUR_KEY_HERE":
        return key
    if CONFIG_PATH.exists():
        namespace = {}
        exec(CONFIG_PATH.read_text(encoding="utf-8"), {}, namespace)
        key = str(namespace.get("DATABENTO_API_KEY") or "").strip()
        if key and key != "YOUR_KEY_HERE":
            return key
    raise RuntimeError(
        "DATABENTO_API_KEY is missing. Set it in the environment or in "
        "/home/lean-workspace/config/databento_config.py."
    )


def normalize_df(df):
    import pandas as pd

    frame = df.reset_index()
    timestamp_col = None
    for candidate in ("ts_event", "ts_recv", "timestamp", "time", "ts_ref"):
        if candidate in frame.columns:
            timestamp_col = candidate
            break
    if timestamp_col is None:
        raise RuntimeError(f"Unable to locate Databento timestamp column in {list(frame.columns)}")

    rename_map = {
        timestamp_col: "t",
        "open": "o",
        "high": "h",
        "low": "l",
        "close": "c",
        "volume": "v",
    }
    frame = frame.rename(columns=rename_map)
    required = ["t", "o", "h", "l", "c", "v"]
    missing = [name for name in required if name not in frame.columns]
    if missing:
        raise RuntimeError(f"Databento dataframe is missing columns: {missing}")

    frame = frame[required].copy()
    frame["t"] = pd.to_datetime(frame["t"], utc=True)
    frame = frame.sort_values("t").drop_duplicates(subset=["t"], keep="last")
    frame["t"] = (frame["t"].astype("int64") // 10**9).astype("int64")
    for col in ("o", "h", "l", "c"):
        frame[col] = frame[col].astype(float)
    frame["v"] = frame["v"].fillna(0).astype("int64")
    return frame


def fetch_symbol(symbol: str, start: str = "2020-01-01", end: str | None = None):
    import databento as db

    clean = str(symbol or "").upper().strip()
    if clean not in PARENT_SYMBOLS:
        raise ValueError(f"Unsupported futures symbol: {clean}")

    if end is None:
        end = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    client = db.Historical(key=load_api_key())
    parent_symbol = PARENT_SYMBOLS[clean]
    print(f"Fetching {clean} ({parent_symbol}) from {start} to {end}...")
    data = client.timeseries.get_range(
        dataset="GLBX.MDP3",
        symbols=[parent_symbol],
        stype_in="parent",
        schema="ohlcv-1d",
        start=start,
        end=end,
    )
    df = normalize_df(data.to_df())
    output_path = DATA_DIR / f"{clean}_daily.csv"
    df.to_csv(output_path, index=False)
    print(f"Saved {len(df)} bars to {output_path}")
    return df


def fetch_all(start: str = "2020-01-01", end: str | None = None) -> dict[str, int]:
    results = {}
    for symbol in FUTURES_SYMBOLS:
        try:
            df = fetch_symbol(symbol, start=start, end=end)
            results[symbol] = len(df)
        except Exception as exc:
            print(f"Error fetching {symbol}: {exc}")
            results[symbol] = 0
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Databento futures data into CSV files.")
    parser.add_argument("--symbol", default="", help="Single futures symbol to fetch, for example MGC")
    parser.add_argument("--start", default="2020-01-01", help="Inclusive start date, YYYY-MM-DD")
    parser.add_argument("--end", default="", help="Inclusive end date, YYYY-MM-DD")
    parser.add_argument("--all", action="store_true", help="Fetch all configured futures symbols")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    end = args.end or None
    if args.all or not args.symbol:
        result = fetch_all(start=args.start, end=end)
    else:
        frame = fetch_symbol(args.symbol, start=args.start, end=end)
        result = {args.symbol.upper(): len(frame)}
    print(json.dumps(result, indent=2))
