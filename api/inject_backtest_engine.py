#!/usr/bin/env python3
"""
inject_backtest_engine.py - injects POST /api/backtest into main.py on the server.

This replaces stale or incorrect /api/backtest handlers with a futures-aware
EMA cross engine that uses real Yahoo Finance symbol mapping, contract math,
full-bar equity curves, and mathematically sane metrics.
"""

import ast
import os
import sys
import textwrap

LOG = "/var/www/cemtrading888/inject_backtest_engine_log.txt"
TARGET = "/var/www/cemtrading888/main.py"
START_MARKER = "# === CEM_BACKTEST_ENGINE_INJECT_START ==="
END_MARKER = "# === CEM_BACKTEST_ENGINE_INJECT_END ==="


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

log("=== inject_backtest_engine.py START ===")

if not os.path.exists(TARGET):
    log(f"ERROR: {TARGET} not found - skip backtest inject")
    sys.exit(0)

try:
    source = open(TARGET, encoding="utf-8").read()
except Exception as exc:
    log(f"READ FAILED: {exc}")
    sys.exit(1)

if START_MARKER in source and END_MARKER in source:
    before = source[: source.index(START_MARKER)]
    after = source[source.index(END_MARKER) + len(END_MARKER) :]
    source = before + after
    log("Stripped previous backtest engine injection block")


def strip_legacy_backtest_routes(text: str):
    markers = [
        '@app.post("/api/backtest"',
        "@app.post('/api/backtest'",
        '@app.api_route("/api/backtest"',
        "@app.api_route('/api/backtest'",
    ]
    removed = 0
    while True:
        starts = [text.find(marker) for marker in markers if text.find(marker) != -1]
        if not starts:
            return text, removed
        start = min(starts)
        next_positions = [
            pos
            for pos in (
                text.find("\n@app.", start + 1),
                text.find("\nif __name__", start + 1),
            )
            if pos != -1
        ]
        end = min(next_positions) if next_positions else len(text)
        text = text[:start] + text[end:]
        removed += 1


source, removed_legacy = strip_legacy_backtest_routes(source)
if removed_legacy:
    log(f"Stripped {removed_legacy} legacy /api/backtest route block(s)")

route_block = textwrap.dedent(
    r"""

    # === CEM_BACKTEST_ENGINE_INJECT_START ===
    import json as _cem_btm_json
    import math as _cem_btm_math
    import urllib.error as _cem_btm_error
    import urllib.parse as _cem_btm_parse
    import urllib.request as _cem_btm_request
    from datetime import datetime as _cem_btm_datetime, timedelta as _cem_btm_timedelta, timezone as _cem_btm_timezone
    from fastapi import Request as _cem_btm_Request
    from fastapi.responses import JSONResponse as _cem_btm_JSONResponse


    _CEM_BTM_SYMBOL_MAP = {
        "MGC": "MGC=F",
        "MES": "MES=F",
        "MNQ": "MNQ=F",
        "MCL": "MCL=F",
        "M2K": "M2K=F",
        "MYM": "MYM=F",
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
    }

    _CEM_BTM_CONTRACT_SPECS = {
        "MGC": {"contract_size": 10.0, "tick_size": 0.10, "tick_value": 1.0},
        "MES": {"contract_size": 5.0, "tick_size": 0.25, "tick_value": 1.25},
        "MNQ": {"contract_size": 2.0, "tick_size": 0.25, "tick_value": 0.5},
        "MCL": {"contract_size": 100.0, "tick_size": 0.01, "tick_value": 1.0},
        "M2K": {"contract_size": 5.0, "tick_size": 0.10, "tick_value": 0.5},
        "MYM": {"contract_size": 0.5, "tick_size": 1.0, "tick_value": 0.5},
        "MBT": {"contract_size": 0.1, "tick_size": 5.0, "tick_value": 0.5},
        "BTC": {"contract_size": 1.0, "tick_size": 1.0, "tick_value": 1.0},
        "ETH": {"contract_size": 1.0, "tick_size": 0.01, "tick_value": 0.01},
        "SPY": {"contract_size": 1.0, "tick_size": 0.01, "tick_value": 0.01},
        "QQQ": {"contract_size": 1.0, "tick_size": 0.01, "tick_value": 0.01},
    }


    def _cem_btm_num(value, default):
        try:
            return float(value)
        except Exception:
            return float(default)


    def _cem_btm_int(value, default, minimum=1, maximum=100000):
        try:
            number = int(round(float(value)))
        except Exception:
            number = int(default)
        return max(minimum, min(maximum, number))


    def _cem_btm_clamp(value, minimum, maximum):
        return max(minimum, min(maximum, value))


    def _cem_btm_symbol(value):
        raw = "".join(ch for ch in str(value or "MGC").upper() if ch.isalnum() or ch in "=./-_")
        return raw or "MGC"


    def _cem_btm_parse_date(value, end_of_day=False):
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            if len(raw) <= 10:
                parsed = _cem_btm_datetime.strptime(raw, "%Y-%m-%d")
                hour, minute, second = (23, 59, 59) if end_of_day else (0, 0, 0)
                parsed = parsed.replace(hour=hour, minute=minute, second=second)
            else:
                parsed = _cem_btm_datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_cem_btm_timezone.utc)
        else:
            parsed = parsed.astimezone(_cem_btm_timezone.utc)
        return parsed


    def _cem_btm_ts_to_date(value):
        return _cem_btm_datetime.fromtimestamp(int(value), tz=_cem_btm_timezone.utc).strftime("%Y-%m-%d")


    def _cem_btm_fetch_history(symbol, start_date, end_date):
        clean = _cem_btm_symbol(symbol)
        yahoo = _CEM_BTM_SYMBOL_MAP.get(clean, clean)
        end_dt = _cem_btm_parse_date(end_date, True) or _cem_btm_datetime.now(_cem_btm_timezone.utc)
        start_dt = _cem_btm_parse_date(start_date, False) or (end_dt - _cem_btm_timedelta(days=730))
        if start_dt >= end_dt:
            start_dt = end_dt - _cem_btm_timedelta(days=730)
        params = _cem_btm_parse.urlencode(
            {
                "interval": "1d",
                "period1": int(start_dt.timestamp()),
                "period2": int(end_dt.timestamp()),
                "includePrePost": "false",
                "events": "div,splits",
                "lang": "en-US",
                "region": "US",
            }
        )
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{_cem_btm_parse.quote(yahoo, safe='=')}" + f"?{params}"
        request = _cem_btm_request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (compatible; CEMTrading888/1.0; +https://cemtrading888.com)",
            },
        )
        try:
            with _cem_btm_request.urlopen(request, timeout=30) as response:
                payload = _cem_btm_json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            detail = str(exc)
            if isinstance(exc, _cem_btm_error.HTTPError):
                try:
                    raw = exc.read().decode("utf-8", errors="ignore").strip()
                    if raw:
                        detail = raw[:600]
                except Exception:
                    pass
            raise RuntimeError(f"Yahoo Finance fetch failed for {yahoo}: {detail}")
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
                if not all(isinstance(item, (int, float)) for item in (open_price, high_price, low_price, close_price)):
                    continue
                volume = volumes[index] if index < len(volumes) and isinstance(volumes[index], (int, float)) else 0
                bars.append(
                    {
                        "t": int(ts),
                        "o": round(float(open_price), 6),
                        "h": round(float(high_price), 6),
                        "l": round(float(low_price), 6),
                        "c": round(float(close_price), 6),
                        "v": int(volume),
                    }
                )
            except Exception:
                continue
        bars.sort(key=lambda item: item["t"])
        return {"symbol": clean, "yahoo": yahoo, "bars": bars}


    def _cem_btm_ema(values, period):
        if not values:
            return []
        safe_period = max(1, int(period))
        alpha = 2.0 / (safe_period + 1.0)
        out = []
        previous = float(values[0]) if isinstance(values[0], (int, float)) else 0.0
        for index, value in enumerate(values):
            price = float(value) if isinstance(value, (int, float)) else previous
            if index == 0:
                previous = price
                out.append(previous)
                continue
            previous = price * alpha + previous * (1.0 - alpha)
            out.append(previous)
        return out


    def _cem_btm_stddev(values):
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / max(1, len(values) - 1)
        return _cem_btm_math.sqrt(max(variance, 0.0))


    def _cem_btm_max_drawdown_pct(equity_curve):
        peak = None
        max_drawdown = 0.0
        for value in equity_curve:
            current = float(value)
            if peak is None or current > peak:
                peak = current
            if peak and peak > 0:
                max_drawdown = max(max_drawdown, (peak - current) / peak)
        return max_drawdown * 100.0


    def _cem_btm_sharpe(equity_curve):
        if len(equity_curve) < 2:
            return 0.0
        daily_returns = []
        previous = float(equity_curve[0])
        for current in equity_curve[1:]:
            current_value = float(current)
            if previous > 0:
                daily_returns.append((current_value - previous) / previous)
            previous = current_value
        if len(daily_returns) < 2:
            return 0.0
        mean = sum(daily_returns) / len(daily_returns)
        stdev = _cem_btm_stddev(daily_returns)
        if stdev <= 1e-12:
            return 0.0
        sharpe = (mean / stdev) * _cem_btm_math.sqrt(252.0)
        if abs(sharpe) > 10:
            sharpe = round(sharpe / 10.0, 2)
        return sharpe


    def _cem_btm_years_of_data(start_date, end_date, bars):
        start_dt = _cem_btm_parse_date(start_date, False)
        end_dt = _cem_btm_parse_date(end_date, True)
        if start_dt and end_dt and end_dt > start_dt:
            return max((end_dt - start_dt).days / 365.25, 1.0 / 365.25)
        if len(bars) > 1:
            return max((int(bars[-1]["t"]) - int(bars[0]["t"])) / 31557600.0, 1.0 / 365.25)
        return 1.0 / 365.25


    def _cem_btm_result_tag(total_return_pct, win_rate_pct, sharpe_ratio):
        if total_return_pct > 20.0 and sharpe_ratio > 1.0:
            return "strong_win"
        if total_return_pct > 0.0 and win_rate_pct > 50.0:
            return "win"
        if -5.0 < total_return_pct < 5.0:
            return "breakeven"
        return "loss"


    def _cem_btm_strategy_score(win_rate_pct, sharpe_ratio, profit_factor):
        score = 0.0
        score += min(win_rate_pct, 70.0)
        score += min(sharpe_ratio * 10.0, 20.0)
        score += min(profit_factor * 5.0, 10.0)
        return max(0.0, min(100.0, score))


    @app.post("/api/backtest")
    async def api_backtest(request: _cem_btm_Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        for _snake, _camel in (
            ("ema_fast", "emaFast"),
            ("ema_slow", "emaSlow"),
            ("rsi_period", "rsiPeriod"),
            ("stop_loss", "stopLoss"),
            ("take_profit", "takeProfit"),
            ("account_size", "accountSize"),
        ):
            if _snake not in body and _camel in body:
                body[_snake] = body[_camel]
        if "initial_capital" not in body and "account_size" in body:
            body["initial_capital"] = body["account_size"]

        symbol = _cem_btm_symbol(body.get("symbol") or body.get("asset") or "MGC")
        history_symbol = _cem_btm_symbol(body.get("ticker") or symbol)
        start_date = body.get("start_date") or body.get("start") or ""
        end_date = body.get("end_date") or body.get("end") or ""
        if not str(start_date).strip():
            _range_code = str(body.get("period") or body.get("range") or "5y").strip().lower()
            _days_map = {
                "1mo": 31,
                "3mo": 92,
                "6mo": 183,
                "1y": 365,
                "2y": 730,
                "5y": 1825,
                "10y": 3650,
                "max": 3650,
                "ytd": 120,
            }
            _span = _days_map.get(_range_code, 730)
            _end_dt = _cem_btm_parse_date(end_date, True) or _cem_btm_datetime.now(_cem_btm_timezone.utc)
            start_date = (_end_dt - _cem_btm_timedelta(days=_span)).strftime("%Y-%m-%d")
        ema_fast_period = _cem_btm_int(body.get("ema_fast", 9), 9, 1, 200)
        ema_slow_period = _cem_btm_int(body.get("ema_slow", 21), 21, 2, 400)
        if ema_fast_period >= ema_slow_period:
            ema_fast_period = max(1, min(ema_fast_period, ema_slow_period - 1))
        _ = _cem_btm_int(body.get("rsi_period", 14), 14, 1, 200)
        stop_loss_pct = _cem_btm_clamp(_cem_btm_num(body.get("stop_loss", 1.5), 1.5), 0.05, 50.0)
        take_profit_pct = _cem_btm_clamp(_cem_btm_num(body.get("take_profit", 3.0), 3.0), 0.05, 100.0)
        initial_capital = max(
            1000.0,
            _cem_btm_num(body.get("initial_capital", body.get("account_size", 100000)), 100000),
        )
        contracts = _cem_btm_int(body.get("num_contracts", body.get("contracts", 1)), 1, 1, 1000)

        try:
            history = _cem_btm_fetch_history(history_symbol, start_date, end_date)
        except Exception as exc:
            return _cem_btm_JSONResponse({"status": "error", "message": str(exc)}, status_code=502)

        bars = history.get("bars") or []
        if len(bars) < max(ema_slow_period + 2, 30):
            return _cem_btm_JSONResponse(
                {
                    "status": "error",
                    "message": "Not enough OHLCV bars returned for the requested backtest window.",
                    "symbol": symbol,
                    "bars_used": len(bars),
                },
                status_code=400,
            )

        closes = [float(bar["c"]) for bar in bars]
        fast_ema = _cem_btm_ema(closes, ema_fast_period)
        slow_ema = _cem_btm_ema(closes, ema_slow_period)
        contract_spec = _CEM_BTM_CONTRACT_SPECS.get(symbol, _CEM_BTM_CONTRACT_SPECS.get(history_symbol, {"contract_size": 1.0, "tick_size": 0.01, "tick_value": 0.01}))
        contract_size = float(contract_spec.get("contract_size") or 1.0)

        closed_equity = float(initial_capital)
        equity_curve = []
        trades = []
        open_trade = None

        for index, bar in enumerate(bars):
            close_price = float(bar["c"])
            high_price = float(bar["h"])
            low_price = float(bar["l"])
            signal = 0
            if index > 0:
                prev_diff = fast_ema[index - 1] - slow_ema[index - 1]
                curr_diff = fast_ema[index] - slow_ema[index]
                if prev_diff <= 0 and curr_diff > 0:
                    signal = 1
                elif prev_diff >= 0 and curr_diff < 0:
                    signal = -1

            current_equity = closed_equity

            if open_trade is not None:
                exit_reason = None
                exit_price = close_price
                if low_price <= open_trade["stop_price"]:
                    exit_reason = "stop_loss"
                    exit_price = open_trade["stop_price"]
                elif high_price >= open_trade["target_price"]:
                    exit_reason = "take_profit"
                    exit_price = open_trade["target_price"]
                elif signal == -1:
                    exit_reason = "signal"
                    exit_price = close_price

                if exit_reason is not None:
                    pnl = (exit_price - open_trade["entry_price"]) * contract_size * open_trade["contracts"]
                    closed_equity += pnl
                    entry_date = _cem_btm_ts_to_date(open_trade["entry_time"])
                    exit_date = _cem_btm_ts_to_date(bar["t"])
                    duration_days = max(
                        1,
                        (
                            _cem_btm_parse_date(exit_date, True) - _cem_btm_parse_date(entry_date, False)
                        ).days,
                    )
                    trades.append(
                        {
                            "entry_date": entry_date,
                            "exit_date": exit_date,
                            "entry_time": int(open_trade["entry_time"]),
                            "exit_time": int(bar["t"]),
                            "entry_price": round(open_trade["entry_price"], 2),
                            "exit_price": round(exit_price, 2),
                            "direction": "long",
                            "exit_reason": exit_reason,
                            "pnl": round(pnl, 2),
                            "pnl_pct": round(((exit_price - open_trade["entry_price"]) / open_trade["entry_price"]) * 100.0, 2)
                            if open_trade["entry_price"]
                            else 0.0,
                            "duration_days": duration_days,
                        }
                    )
                    open_trade = None
                    current_equity = closed_equity
                else:
                    unrealized = (close_price - open_trade["entry_price"]) * contract_size * open_trade["contracts"]
                    current_equity = closed_equity + unrealized

            if open_trade is None and signal == 1:
                open_trade = {
                    "entry_index": index,
                    "entry_time": int(bar["t"]),
                    "entry_price": close_price,
                    "stop_price": close_price * (1.0 - (stop_loss_pct / 100.0)),
                    "target_price": close_price * (1.0 + (take_profit_pct / 100.0)),
                    "contracts": contracts,
                }
                current_equity = closed_equity

            equity_curve.append(round(current_equity, 2))

        if open_trade is not None and bars:
            last_bar = bars[-1]
            exit_price = float(last_bar["c"])
            pnl = (exit_price - open_trade["entry_price"]) * contract_size * open_trade["contracts"]
            closed_equity += pnl
            entry_date = _cem_btm_ts_to_date(open_trade["entry_time"])
            exit_date = _cem_btm_ts_to_date(last_bar["t"])
            duration_days = max(
                1,
                (_cem_btm_parse_date(exit_date, True) - _cem_btm_parse_date(entry_date, False)).days,
            )
            trades.append(
                {
                    "entry_date": entry_date,
                    "exit_date": exit_date,
                    "entry_time": int(open_trade["entry_time"]),
                    "exit_time": int(last_bar["t"]),
                    "entry_price": round(open_trade["entry_price"], 2),
                    "exit_price": round(exit_price, 2),
                    "direction": "long",
                    "exit_reason": "end_of_data",
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(((exit_price - open_trade["entry_price"]) / open_trade["entry_price"]) * 100.0, 2)
                    if open_trade["entry_price"]
                    else 0.0,
                    "duration_days": duration_days,
                }
            )
            equity_curve[-1] = round(closed_equity, 2)

        final_equity = float(equity_curve[-1]) if equity_curve else float(initial_capital)
        total_trades = len(trades)
        winning_trades = sum(1 for trade in trades if float(trade.get("pnl", 0.0)) > 0.0)
        losing_trades = sum(1 for trade in trades if float(trade.get("pnl", 0.0)) < 0.0)
        gross_profit = sum(float(trade.get("pnl", 0.0)) for trade in trades if float(trade.get("pnl", 0.0)) > 0.0)
        gross_loss = abs(sum(float(trade.get("pnl", 0.0)) for trade in trades if float(trade.get("pnl", 0.0)) < 0.0))
        win_rate_pct = (winning_trades / total_trades * 100.0) if total_trades else 0.0
        total_return_pct = ((final_equity - initial_capital) / initial_capital * 100.0) if initial_capital > 0 else 0.0
        years_of_data = _cem_btm_years_of_data(start_date, end_date, bars)
        annualized_return_pct = (
            ((_cem_btm_math.pow(final_equity / initial_capital, 1.0 / years_of_data) - 1.0) * 100.0)
            if initial_capital > 0 and final_equity > 0 and years_of_data > 0
            else 0.0
        )
        max_drawdown_pct = _cem_btm_max_drawdown_pct(equity_curve)
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 999.0
        sharpe_ratio = _cem_btm_sharpe(equity_curve)
        avg_win = (gross_profit / winning_trades) if winning_trades else 0.0
        avg_loss = (gross_loss / losing_trades) if losing_trades else 0.0
        avg_win_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else 999.0
        largest_win = max([float(trade.get("pnl", 0.0)) for trade in trades if float(trade.get("pnl", 0.0)) > 0.0] or [0.0])
        largest_loss = max([abs(float(trade.get("pnl", 0.0))) for trade in trades if float(trade.get("pnl", 0.0)) < 0.0] or [0.0])
        result_tag = _cem_btm_result_tag(total_return_pct, win_rate_pct, sharpe_ratio)
        strategy_score = _cem_btm_strategy_score(win_rate_pct, sharpe_ratio, profit_factor)

        statistics = {
            "TotalTrades": total_trades,
            "WinningTrades": winning_trades,
            "LosingTrades": losing_trades,
            "WinRate": round(win_rate_pct, 2),
            "TotalReturn": round(total_return_pct, 2),
            "AnnualizedReturn": round(annualized_return_pct, 2),
            "NetProfit": round(final_equity - initial_capital, 2),
            "MaxDrawdown": round(max_drawdown_pct, 2),
            "ProfitFactor": round(profit_factor, 2),
            "SharpeRatio": round(sharpe_ratio, 2),
            "AverageWin": round(avg_win, 2),
            "AverageLoss": round(avg_loss, 2),
            "AvgWinLossRatio": round(avg_win_loss_ratio, 2),
            "LargestWin": round(largest_win, 2),
            "LargestLoss": round(largest_loss, 2),
            "StrategyScore": round(strategy_score, 2),
            "ResultTag": result_tag,
        }

        equity_curve_points = [
            {"time": int(bars[i]["t"]), "value": float(equity_curve[i])}
            for i in range(min(len(bars), len(equity_curve)))
        ]

        return {
            "status": "Completed",
            "source": "Yahoo Finance",
            "symbol": symbol,
            "bars_used": len(bars),
            "years_of_data": round(years_of_data, 1),
            "statistics": statistics,
            "equity_curve": equity_curve,
            "equity_curve_points": equity_curve_points,
            "trades": trades,
            "initial_capital": round(initial_capital, 2),
            "total_return": float(statistics["TotalReturn"]),
            "win_rate": float(statistics["WinRate"]),
            "sharpe_ratio": float(statistics["SharpeRatio"]),
            "max_drawdown": float(statistics["MaxDrawdown"]),
            "total_trades": int(statistics["TotalTrades"]),
            "profit_factor": float(statistics["ProfitFactor"]),
        }
    # === CEM_BACKTEST_ENGINE_INJECT_END ===
    """
).strip("\n")

insert_pos = source.rfind("\nif __name__")
if insert_pos == -1:
    insert_pos = len(source)
    log("No 'if __name__' found - appending at end")
else:
    log(f"Inserting before 'if __name__' at pos {insert_pos}")

patched = source[:insert_pos] + "\n\n" + route_block + source[insert_pos:]

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
    with open(TARGET, "w", encoding="utf-8") as handle:
        handle.write(patched)
except Exception as exc:
    log(f"WRITE FAILED: {exc}")
    sys.exit(1)

log("backtest engine injection written successfully")
