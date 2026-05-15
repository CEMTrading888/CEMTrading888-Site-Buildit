#!/usr/bin/env python3
"""
inject_backtest_replay.py - injects POST /api/backtest-replay into main.py on the server.

This route returns replay-ready OHLCV bars, indicators, equity curve, and trade markers
using Python 3.11 only. It is idempotent: previous injected blocks are stripped before
re-applying the latest version.
"""

import ast
import os
import sys
import textwrap

LOG = "/var/www/cemtrading888/inject_backtest_replay_log.txt"
TARGET = "/var/www/cemtrading888/main.py"


def log(message: str) -> None:
    print(message)
    try:
        with open(LOG, "a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except Exception:
        pass


try:
    open(LOG, "w", encoding="utf-8").close()
except Exception:
    pass

log("=== inject_backtest_replay.py START ===")

if not os.path.exists(TARGET):
    log(f"ERROR: {TARGET} not found - skip backtest replay inject")
    sys.exit(0)

try:
    src = open(TARGET, encoding="utf-8").read()
except Exception as exc:
    log(f"READ FAILED: {exc}")
    sys.exit(1)

START_MARKER = "# === CEM_BACKTEST_REPLAY_INJECT_START ==="
END_MARKER = "# === CEM_BACKTEST_REPLAY_INJECT_END ==="
if START_MARKER in src and END_MARKER in src:
    before = src[: src.index(START_MARKER)]
    after = src[src.index(END_MARKER) + len(END_MARKER) :]
    src = before + after
    log("Stripped previous backtest replay injection block")

NEW_ROUTE = textwrap.dedent(
    r"""

# === CEM_BACKTEST_REPLAY_INJECT_START ===
import json as _cem_bt_json
import math as _cem_bt_math
import urllib.parse as _cem_bt_up
import urllib.request as _cem_bt_uq
from datetime import datetime as _cem_bt_datetime, timezone as _cem_bt_timezone
from fastapi import Request
from fastapi.responses import JSONResponse

_CEM_BT_SYMBOL_MAP = {
    "MGC": "MGC=F",
    "GC": "GC=F",
    "MES": "MES=F",
    "ES": "ES=F",
    "MNQ": "MNQ=F",
    "NQ": "NQ=F",
    "M2K": "M2K=F",
    "MYM": "MYM=F",
    "CL": "CL=F",
    "MCL": "MCL=F",
    "MBT": "BTC-USD",
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
    "AAPL": "AAPL",
    "TSLA": "TSLA",
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
}


def _cem_bt_num(value, default):
    try:
        return float(value)
    except Exception:
        return float(default)


def _cem_bt_int(value, default, minimum=1, maximum=100000):
    try:
        number = int(round(float(value)))
    except Exception:
        number = int(default)
    return max(minimum, min(maximum, number))


def _cem_bt_clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def _cem_bt_symbol(symbol):
    raw = "".join(ch for ch in str(symbol or "MGC").upper() if ch.isalnum() or ch in "=./-_")
    return raw or "MGC"


def _cem_bt_range_code(date_range):
    mapping = {
        "3M": "3mo",
        "6M": "6mo",
        "1Y": "1y",
        "2Y": "2y",
        "5Y": "5y",
        "ALL": "10y",
    }
    return mapping.get(str(date_range or "").strip().upper(), "1y")


def _cem_bt_interval_config(timeframe):
    mapping = {
        "1M": {"interval": "1m", "aggregate": 1},
        "5M": {"interval": "5m", "aggregate": 1},
        "15M": {"interval": "15m", "aggregate": 1},
        "1H": {"interval": "60m", "aggregate": 1},
        "4H": {"interval": "60m", "aggregate": 4},
        "1D": {"interval": "1d", "aggregate": 1},
        "1W": {"interval": "1wk", "aggregate": 1},
    }
    return mapping.get(str(timeframe or "").strip().upper(), mapping["1D"])


def _cem_bt_range_days(range_code):
    mapping = {
        "7d": 7,
        "30d": 30,
        "60d": 60,
        "3mo": 91,
        "6mo": 182,
        "1y": 365,
        "2y": 730,
        "5y": 1825,
        "10y": 3650,
    }
    return mapping.get(range_code, 365)


def _cem_bt_pick_range(requested_range, interval):
    limits = {
        "1m": {"days": 7, "code": "7d"},
        "5m": {"days": 60, "code": "60d"},
        "15m": {"days": 60, "code": "60d"},
        "60m": {"days": 730, "code": "2y"},
        "1d": {"days": 3650, "code": "10y"},
        "1wk": {"days": 3650, "code": "10y"},
    }
    requested_days = _cem_bt_range_days(requested_range)
    limit = limits.get(interval, {"days": 365, "code": "1y"})
    return requested_range if requested_days <= limit["days"] else limit["code"]


def _cem_bt_parse_date_ts(value, end_of_day=False):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if len(raw) <= 10:
            parsed = _cem_bt_datetime.strptime(raw, "%Y-%m-%d")
            hour, minute, second = (23, 59, 59) if end_of_day else (0, 0, 0)
            parsed = parsed.replace(hour=hour, minute=minute, second=second)
        else:
            parsed = _cem_bt_datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_cem_bt_timezone.utc)
    else:
        parsed = parsed.astimezone(_cem_bt_timezone.utc)
    return int(parsed.timestamp())


def _cem_bt_filter_bars_by_dates(bars, start_date, end_date):
    if not isinstance(bars, list) or not bars:
        return []
    start_ts = _cem_bt_parse_date_ts(start_date, False)
    end_ts = _cem_bt_parse_date_ts(end_date, True)
    if start_ts is None and end_ts is None:
        return bars
    filtered = []
    for bar in bars:
        try:
            ts = int(bar.get("t", 0))
        except Exception:
            ts = 0
        if start_ts is not None and ts < start_ts:
            continue
        if end_ts is not None and ts > end_ts:
            continue
        filtered.append(bar)
    return filtered


def _cem_bt_aggregate_bars(bars, step):
    safe_step = max(1, int(step))
    if safe_step <= 1 or len(bars) <= 1:
        return bars
    out = []
    chunk = []
    for bar in bars:
        chunk.append(bar)
        if len(chunk) < safe_step:
            continue
        out.append({
            "t": int(chunk[-1]["t"]),
            "o": float(chunk[0]["o"]),
            "h": round(max(float(point["h"]) for point in chunk), 6),
            "l": round(min(float(point["l"]) for point in chunk), 6),
            "c": float(chunk[-1]["c"]),
            "v": int(sum(int(point.get("v", 0)) for point in chunk)),
        })
        chunk = []
    if chunk:
        out.append({
            "t": int(chunk[-1]["t"]),
            "o": float(chunk[0]["o"]),
            "h": round(max(float(point["h"]) for point in chunk), 6),
            "l": round(min(float(point["l"]) for point in chunk), 6),
            "c": float(chunk[-1]["c"]),
            "v": int(sum(int(point.get("v", 0)) for point in chunk)),
        })
    return out


def _cem_bt_fetch_history(symbol, interval, range_code):
    clean = _cem_bt_symbol(symbol)
    yahoo = _CEM_BT_SYMBOL_MAP.get(clean, clean)
    params = _cem_bt_up.urlencode({
        "interval": interval,
        "range": range_code,
        "includePrePost": "false",
        "events": "div,splits",
        "lang": "en-US",
        "region": "US",
    })
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{_cem_bt_up.quote(yahoo, safe='=')}" + f"?{params}"
    request = _cem_bt_uq.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; CEMTrading888/1.0; +https://cemtrading888.com)",
        },
    )
    with _cem_bt_uq.urlopen(request, timeout=20) as response:
        payload = _cem_bt_json.loads(response.read().decode("utf-8"))
    result = ((payload or {}).get("chart") or {}).get("result") or []
    first = result[0] if result else {}
    timestamps = first.get("timestamp") or []
    quote = (((first.get("indicators") or {}).get("quote") or [{}])[0]) or {}
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    bars = []
    for index, ts in enumerate(timestamps):
        try:
            open_price = opens[index]
            high_price = highs[index]
            low_price = lows[index]
            close_price = closes[index]
            if None in (open_price, high_price, low_price, close_price):
                continue
            if not all(isinstance(value, (int, float)) for value in (open_price, high_price, low_price, close_price)):
                continue
            volume = volumes[index] if index < len(volumes) and isinstance(volumes[index], (int, float)) else 0
            bars.append({
                "t": int(ts),
                "o": round(float(open_price), 6),
                "h": round(float(high_price), 6),
                "l": round(float(low_price), 6),
                "c": round(float(close_price), 6),
                "v": int(volume),
            })
        except Exception:
            continue
    bars.sort(key=lambda point: point["t"])
    return {"symbol": clean, "yahoo": yahoo, "interval": interval, "range": range_code, "bars": bars, "ohlcv": bars, "count": len(bars)}


def _cem_bt_ema(values, period):
    if not values:
        return []
    safe_period = max(1, int(period))
    alpha = 2.0 / (safe_period + 1.0)
    ema = []
    previous = float(values[0]) if isinstance(values[0], (int, float)) else 0.0
    for index, value in enumerate(values):
        price = float(value) if isinstance(value, (int, float)) else previous
        if index == 0:
            previous = price
            ema.append(previous)
            continue
        previous = price * alpha + previous * (1.0 - alpha)
        ema.append(previous)
    return ema


def _cem_bt_rsi(values, period):
    total = len(values)
    if total < 2:
        return []
    safe_period = max(1, int(period))
    rsi = [None] * total
    if total <= safe_period:
        return rsi
    avg_gain = 0.0
    avg_loss = 0.0
    for index in range(1, safe_period + 1):
        change = float(values[index]) - float(values[index - 1])
        if change > 0:
            avg_gain += change
        if change < 0:
            avg_loss += abs(change)
    avg_gain /= safe_period
    avg_loss /= safe_period

    def resolve():
        if avg_loss == 0.0 and avg_gain == 0.0:
            return 50.0
        if avg_loss == 0.0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    rsi[safe_period] = resolve()
    for index in range(safe_period + 1, total):
        change = float(values[index]) - float(values[index - 1])
        gain = change if change > 0 else 0.0
        loss = abs(change) if change < 0 else 0.0
        avg_gain = ((avg_gain * (safe_period - 1)) + gain) / safe_period
        avg_loss = ((avg_loss * (safe_period - 1)) + loss) / safe_period
        rsi[index] = resolve()
    return rsi


def _cem_bt_atr(bars, period):
    total = len(bars)
    safe_period = max(1, int(period))
    if total < 2:
        return [None] * total
    true_ranges = [None] * total
    for index in range(1, total):
        current = bars[index]
        prev_close = float(bars[index - 1]["c"])
        true_ranges[index] = max(
            float(current["h"]) - float(current["l"]),
            abs(float(current["h"]) - prev_close),
            abs(float(current["l"]) - prev_close),
        )
    atr_values = [None] * total
    if total <= safe_period:
        return atr_values
    atr = 0.0
    for index in range(1, safe_period + 1):
        atr += float(true_ranges[index] or 0.0)
    atr /= safe_period
    atr_values[safe_period] = atr
    for index in range(safe_period + 1, total):
        atr = ((atr * (safe_period - 1)) + float(true_ranges[index] or 0.0)) / safe_period
        atr_values[index] = atr
    return atr_values


def _cem_bt_macd(values, fast_period, slow_period, signal_period):
    fast_ema = _cem_bt_ema(values, fast_period)
    slow_ema = _cem_bt_ema(values, slow_period)
    macd_line = [fast_ema[index] - slow_ema[index] for index in range(len(values))]
    signal_line = _cem_bt_ema(macd_line, signal_period)
    histogram = [macd_line[index] - signal_line[index] for index in range(len(values))]
    return {
        "fast_ema": fast_ema,
        "slow_ema": slow_ema,
        "macd_line": macd_line,
        "signal_line": signal_line,
        "histogram": histogram,
    }


def _cem_bt_stddev(values):
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return _cem_bt_math.sqrt(max(variance, 0.0))


def _cem_bt_periods_per_year(bars):
    if len(bars) < 2:
        return 252.0
    diffs = []
    for index in range(1, len(bars)):
        diff = int(bars[index]["t"]) - int(bars[index - 1]["t"])
        if diff > 0:
            diffs.append(diff)
    if not diffs:
        return 252.0
    diffs.sort()
    median = diffs[len(diffs) // 2]
    return max(1.0, 31557600.0 / float(median))


def _cem_bt_sharpe(equity_curve, bars):
    if len(equity_curve) < 2:
        return 0.0
    returns = []
    previous = float(equity_curve[0])
    for current in equity_curve[1:]:
        current_value = float(current)
        if previous > 0:
            returns.append((current_value - previous) / previous)
        previous = current_value
    if len(returns) < 2:
        return 0.0
    stdev = _cem_bt_stddev(returns)
    if stdev <= 1e-12:
        return 0.0
    mean = sum(returns) / len(returns)
    return mean / stdev * _cem_bt_math.sqrt(_cem_bt_periods_per_year(bars))


def _cem_bt_drawdown_ratio(equity_curve):
    peak = None
    max_drawdown = 0.0
    for value in equity_curve:
        try:
            current = float(value)
        except Exception:
            continue
        if peak is None or current > peak:
            peak = current
        if peak and peak > 0:
            max_drawdown = max(max_drawdown, (peak - current) / peak)
    return max_drawdown


def _cem_bt_results_series(bars, equity_curve):
    out = []
    for index, bar in enumerate(bars):
        out.append({
            "time": int(bar["t"]),
            "price": round(float(bar["c"]), 6),
            "equity": round(float(equity_curve[index]), 2) if index < len(equity_curve) else None,
        })
    return out


@app.post("/api/backtest-replay")
async def api_backtest_replay(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    symbol = _cem_bt_symbol(body.get("symbol") or body.get("asset"))
    history_symbol = _cem_bt_symbol(body.get("ticker") or symbol)
    timeframe = str(body.get("timeframe") or "1D").strip().upper() or "1D"
    date_range = _cem_bt_range_code(body.get("date_range"))
    interval_config = _cem_bt_interval_config(timeframe)
    request_interval = interval_config["interval"]
    aggregate_step = interval_config["aggregate"]
    request_range = _cem_bt_pick_range(date_range, request_interval)

    try:
        pack = _cem_bt_fetch_history(history_symbol, request_interval, request_range)
    except Exception as exc:
        return JSONResponse({"status": "error", "message": f"Yahoo Finance fetch failed: {exc}"}, status_code=502)

    bars = _cem_bt_filter_bars_by_dates(pack.get("bars") or [], body.get("start_date"), body.get("end_date"))
    bars = _cem_bt_aggregate_bars(bars, aggregate_step)
    if len(bars) < 20:
        return JSONResponse({
            "status": "error",
            "message": "Not enough OHLCV bars returned for replay.",
            "symbol": symbol,
            "bars": [],
            "ohlcv": [],
            "count": 0,
        }, status_code=400)

    ema_fast_period = _cem_bt_int(body.get("ema_fast", 9), 9, 1, 500)
    ema_slow_period = _cem_bt_int(body.get("ema_slow", 21), 21, 1, 500)
    ema_trend_period = _cem_bt_int(body.get("ema_trend", 200), 200, 1, 500)
    rsi_period = _cem_bt_int(body.get("rsi_period", 14), 14, 1, 200)
    rsi_ob = _cem_bt_clamp(_cem_bt_num(body.get("rsi_ob", 70), 70), 1.0, 100.0)
    rsi_os = _cem_bt_clamp(_cem_bt_num(body.get("rsi_os", 30), 30), 0.0, 99.0)
    macd_fast_period = _cem_bt_int(body.get("macd_fast", 12), 12, 1, 200)
    macd_slow_period = _cem_bt_int(body.get("macd_slow", 26), 26, 1, 300)
    macd_signal_period = _cem_bt_int(body.get("macd_signal", 9), 9, 1, 200)
    atr_period = _cem_bt_int(body.get("atr_period", 14), 14, 1, 200)
    bb_period = _cem_bt_int(body.get("bb_period", 20), 20, 1, 300)
    stop_loss_pct = _cem_bt_clamp(_cem_bt_num(body.get("stop_loss", 1.5), 1.5), 0.05, 25.0)
    take_profit_pct = _cem_bt_clamp(_cem_bt_num(body.get("take_profit", 3.0), 3.0), 0.05, 100.0)
    position_size_pct = _cem_bt_clamp(_cem_bt_num(body.get("position_size", 95), 95) / 100.0, 0.01, 1.0)
    starting_equity = max(1.0, _cem_bt_num(body.get("account_size", 10000), 10000))
    max_hold_bars = max(4, min(400, int(round(max(ema_slow_period, ema_trend_period) / 2.0))))

    closes = [float(bar["c"]) for bar in bars]
    ema_fast = _cem_bt_ema(closes, ema_fast_period)
    ema_slow = _cem_bt_ema(closes, ema_slow_period)
    ema_trend = _cem_bt_ema(closes, ema_trend_period)
    rsi_values = _cem_bt_rsi(closes, rsi_period)
    atr_values = _cem_bt_atr(bars, atr_period)
    macd = _cem_bt_macd(closes, macd_fast_period, macd_slow_period, macd_signal_period)

    warmup_bars = min(
        len(bars) - 1,
        max(
            ema_fast_period,
            ema_slow_period,
            ema_trend_period,
            rsi_period + 1,
            macd_slow_period + macd_signal_period,
            atr_period + 1,
            bb_period,
        ),
    )

    equity = starting_equity
    equity_curve = [round(starting_equity, 2)] * len(bars)
    trade_markers = []
    open_trade = None
    win_streak = 0
    loss_streak = 0

    for index in range(warmup_bars, len(bars)):
        bar = bars[index]
        close = float(bar["c"])
        high = float(bar["h"])
        low = float(bar["l"])
        equity_curve[index] = round(equity, 2)

        if open_trade is None:
            cross_up = index > 0 and ema_fast[index] > ema_slow[index] and ema_fast[index - 1] <= ema_slow[index - 1]
            trend_ok = close > ema_trend[index]
            rsi_ok = True if rsi_values[index] is None else rsi_values[index] < rsi_ob
            macd_ok = macd["macd_line"][index] > macd["signal_line"][index]
            if cross_up and trend_ok and rsi_ok and macd_ok:
                qty = max(1, int((equity * position_size_pct) / max(close, 1.0)))
                stop_price = close * (1.0 - (stop_loss_pct / 100.0))
                target_price = close * (1.0 + (take_profit_pct / 100.0))
                open_trade = {
                    "entry_index": index,
                    "entry_time": int(bar["t"]),
                    "entry_price": close,
                    "stop_price": stop_price,
                    "target_price": target_price,
                    "qty": qty,
                    "atr": atr_values[index],
                    "side": "long",
                    "equity_before": equity,
                }
                equity_curve[index] = round(equity, 2)
            continue

        unrealized = (close - open_trade["entry_price"]) * open_trade["qty"]
        equity_curve[index] = round(equity + unrealized, 2)
        exit_reason = None
        exit_price = close

        if low <= open_trade["stop_price"]:
            exit_reason = "SL"
            exit_price = open_trade["stop_price"]
        elif high >= open_trade["target_price"]:
            exit_reason = "TP"
            exit_price = open_trade["target_price"]
        elif index > 0 and ema_fast[index] < ema_slow[index] and ema_fast[index - 1] >= ema_slow[index - 1]:
            exit_reason = "EMA_EXIT"
        elif (index - open_trade["entry_index"]) >= max_hold_bars:
            exit_reason = "TIME"

        if exit_reason is None:
            continue

        pnl = (exit_price - open_trade["entry_price"]) * open_trade["qty"]
        equity += pnl
        equity_curve[index] = round(equity, 2)
        if pnl >= 0:
            win_streak += 1
            loss_streak = 0
        else:
            loss_streak += 1
            win_streak = 0
        trade_markers.append({
            "id": f"trade-{len(trade_markers)}",
            "side": "long",
            "bar_enter": open_trade["entry_index"],
            "bar_exit": index,
            "entry_time": int(open_trade["entry_time"]),
            "exit_time": int(bar["t"]),
            "entry_price": round(open_trade["entry_price"], 6),
            "exit_price": round(exit_price, 6),
            "stop_price": round(open_trade["stop_price"], 6),
            "target_price": round(open_trade["target_price"], 6),
            "qty": open_trade["qty"],
            "pnl": round(pnl, 2),
            "pnl_pct": round((pnl / open_trade["equity_before"]), 6) if open_trade["equity_before"] > 0 else 0.0,
            "win": pnl >= 0,
            "reason": exit_reason,
            "equity_before": round(open_trade["equity_before"], 2),
            "equity_after": round(equity, 2),
            "atr": round(float(open_trade["atr"]), 6) if open_trade["atr"] is not None else None,
            "win_streak": win_streak,
            "loss_streak": loss_streak,
        })
        open_trade = None

    if open_trade is not None:
        last_index = len(bars) - 1
        last_bar = bars[last_index]
        exit_price = float(last_bar["c"])
        pnl = (exit_price - open_trade["entry_price"]) * open_trade["qty"]
        equity += pnl
        equity_curve[last_index] = round(equity, 2)
        if pnl >= 0:
            win_streak += 1
            loss_streak = 0
        else:
            loss_streak += 1
            win_streak = 0
        trade_markers.append({
            "id": f"trade-{len(trade_markers)}",
            "side": "long",
            "bar_enter": open_trade["entry_index"],
            "bar_exit": last_index,
            "entry_time": int(open_trade["entry_time"]),
            "exit_time": int(last_bar["t"]),
            "entry_price": round(open_trade["entry_price"], 6),
            "exit_price": round(exit_price, 6),
            "stop_price": round(open_trade["stop_price"], 6),
            "target_price": round(open_trade["target_price"], 6),
            "qty": open_trade["qty"],
            "pnl": round(pnl, 2),
            "pnl_pct": round((pnl / open_trade["equity_before"]), 6) if open_trade["equity_before"] > 0 else 0.0,
            "win": pnl >= 0,
            "reason": "END",
            "equity_before": round(open_trade["equity_before"], 2),
            "equity_after": round(equity, 2),
            "atr": round(float(open_trade["atr"]), 6) if open_trade["atr"] is not None else None,
            "win_streak": win_streak,
            "loss_streak": loss_streak,
        })

    total_trades = len(trade_markers)
    winning_trades = sum(1 for trade in trade_markers if trade.get("win"))
    winning_pnls = [float(trade.get("pnl", 0.0)) for trade in trade_markers if trade.get("win")]
    win_rate = (winning_trades / total_trades) if total_trades else 0.0
    total_return = ((equity - starting_equity) / starting_equity) if starting_equity > 0 else 0.0
    max_drawdown = _cem_bt_drawdown_ratio(equity_curve)
    sharpe = _cem_bt_sharpe(equity_curve, bars)
    avg_win = (sum(winning_pnls) / len(winning_pnls)) if winning_pnls else 0.0
    results = _cem_bt_results_series(bars, equity_curve)
    years_of_data = ((int(bars[-1]["t"]) - int(bars[0]["t"])) / 31557600.0) if len(bars) > 1 else 0.0
    replay_start_index = min(len(bars) - 1, max(1, warmup_bars))

    summary = {
        "total_trades": total_trades,
        "win_rate": round(win_rate, 6),
        "total_return": round(total_return, 6),
        "sharpe_ratio": round(sharpe, 6),
        "max_drawdown": round(max_drawdown, 6),
        "avg_win": round(avg_win, 2),
    }
    statistics = {
        "TotalTrades": total_trades,
        "WinningTrades": winning_trades,
        "WinRate": round(win_rate * 100.0, 4),
        "TotalReturn": round(total_return * 100.0, 4),
        "MaxDrawdown": round(max_drawdown * 100.0, 4),
        "SharpeRatio": round(sharpe, 6),
        "AvgWin": round(avg_win, 2),
    }

    parameters = dict(body)
    parameters.update({
        "symbol": symbol,
        "ticker": history_symbol,
        "timeframe": timeframe,
        "date_range": str(body.get("date_range") or "").strip() or "1Y",
        "ema_fast": ema_fast_period,
        "ema_slow": ema_slow_period,
        "ema_trend": ema_trend_period,
        "rsi_period": rsi_period,
        "rsi_ob": round(rsi_ob, 6),
        "rsi_os": round(rsi_os, 6),
        "macd_fast": macd_fast_period,
        "macd_slow": macd_slow_period,
        "macd_signal": macd_signal_period,
        "atr_period": atr_period,
        "bb_period": bb_period,
        "stop_loss": round(stop_loss_pct, 6),
        "take_profit": round(take_profit_pct, 6),
        "position_size": round(position_size_pct * 100.0, 6),
        "account_size": round(starting_equity, 2),
    })

    return {
        "status": "success",
        "strategy": f"{symbol} replay backtest",
        "symbol": symbol,
        "requested_timeframe": timeframe,
        "applied_interval": request_interval,
        "applied_range": request_range,
        "asset": symbol,
        "source": f"Yahoo Finance ({pack['yahoo']})",
        "bars_used": len(bars),
        "years_of_data": round(years_of_data, 3),
        "bars": bars,
        "ohlcv": bars,
        "count": len(bars),
        "parameters": parameters,
        "starting_equity": round(starting_equity, 2),
        "warmup_bars": warmup_bars,
        "replay_start_index": replay_start_index,
        "replay_end_index": len(bars) - 1,
        "equity_curve": equity_curve,
        "trade_markers": trade_markers,
        "summary": summary,
        "statistics": statistics,
        "metrics": summary,
        "return_pct": round(total_return, 6),
        "win_rate": round(win_rate, 6),
        "sharpe": round(sharpe, 6),
        "max_drawdown": round(max_drawdown, 6),
        "total_trades": total_trades,
        "avg_win": round(avg_win, 2),
        "results": results,
        "db": "not configured",
    }
# === CEM_BACKTEST_REPLAY_INJECT_END ===
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
    for index, line in enumerate(lines[start:end], start=start + 1):
        log(f"  {index}: {line}")
    sys.exit(1)

try:
    open(TARGET, "w", encoding="utf-8").write(patched)
    log(f"INJECT OK - wrote {len(patched)} bytes")
except Exception as exc:
    log(f"WRITE FAILED: {exc}")
    sys.exit(1)

log("=== DONE ===")
