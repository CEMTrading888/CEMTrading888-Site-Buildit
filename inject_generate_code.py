#!/usr/bin/env python3
"""
inject_generate_code.py - injects POST /api/generate_code into main.py on the server.

On the droplet (after push to main), path must be api/ on GitHub:
  curl -s https://raw.githubusercontent.com/CEMTrading888/cem-bot-builder/main/api/inject_generate_code.py | python3
"""
import ast
import os
import sys
import textwrap

LOG = "/var/www/cemtrading888/inject_generate_code_log.txt"
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

log("=== inject_generate_code.py START ===")

if not os.path.exists(TARGET):
    log(f"ERROR: {TARGET} not found - skip generate_code inject")
    sys.exit(0)

try:
    src = open(TARGET, encoding="utf-8").read()
except Exception as e:
    log(f"READ FAILED: {e}")
    sys.exit(1)

START_MARKER = "# === CEM_GENERATE_CODE_INJECT_START ==="
END_MARKER = "# === CEM_GENERATE_CODE_INJECT_END ==="
if START_MARKER in src and END_MARKER in src:
    before = src[: src.index(START_MARKER)]
    after = src[src.index(END_MARKER) + len(END_MARKER) :]
    src = before + after
    log("Stripped previous generate_code injection block")

NEW_ROUTE = textwrap.dedent(
    """

# === CEM_GENERATE_CODE_INJECT_START ===
from fastapi import HTTPException
from string import Template as _cem_codegen_Template
import textwrap as _cem_codegen_tw

_CEM_CODEGEN_ALLOWED = [
    "IBKR",
    "Tradovate",
    "Rithmic",
    "Alpaca",
    "TradeStation",
    "OANDA",
    "TopstepX",
    "Apex",
    "MFF",
    "E2T",
    "TFD",
]

def _cem_codegen_clean_broker(value):
    raw = str(value or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="broker is required")
    aliases = {
        "IBKR": "IBKR",
        "INTERACTIVEBROKERS": "IBKR",
        "TRADOVATE": "Tradovate",
        "RITHMIC": "Rithmic",
        "ALPACA": "Alpaca",
        "TRADESTATION": "TradeStation",
        "OANDA": "OANDA",
        "TOPSTEPX": "TopstepX",
        "TOPSTEP": "TopstepX",
        "APEX": "Apex",
        "APEXTRADER": "Apex",
        "MFF": "MFF",
        "MYFUNDEDFUTURES": "MFF",
        "E2T": "E2T",
        "EARN2TRADE": "E2T",
        "TFD": "TFD",
        "THEFUTURESDESK": "TFD",
    }
    key = "".join(ch for ch in raw.upper() if ch.isalnum())
    broker = aliases.get(key)
    if not broker:
        raise HTTPException(status_code=400, detail=f"Unsupported broker: {raw}")
    return broker

def _cem_codegen_clean_symbol(value):
    raw = "".join(ch for ch in str(value or "MGC").upper() if ch.isalnum() or ch in "/=._-")
    return raw or "MGC"

def _cem_codegen_slug(value):
    out = []
    prev_sep = False
    for ch in str(value or "").strip().lower():
        if ch.isalnum():
            out.append(ch)
            prev_sep = False
        elif not prev_sep:
            out.append("_")
            prev_sep = True
    return "".join(out).strip("_") or "strategy"

def _cem_codegen_int(body, key, default, minimum=0):
    try:
        val = int(float(body.get(key, default)))
    except Exception:
        val = default
    return max(val, minimum)

def _cem_codegen_float(body, key, default, minimum=0.0):
    try:
        val = float(body.get(key, default))
    except Exception:
        val = default
    return max(val, minimum)

def _cem_codegen_sample_prices(symbol):
    base = {
        "MGC": 2740.0,
        "GC": 2748.0,
        "MES": 5610.0,
        "MNQ": 19840.0,
        "ES": 5618.0,
        "NQ": 19876.0,
        "CL": 78.5,
        "BTC/USD": 67420.0,
        "ETH/USD": 3241.0,
        "SPY": 562.0,
        "QQQ": 483.0,
        "EUR/USD": 1.0824,
    }.get(symbol, 100.0)
    prices = []
    for idx in range(48):
        drift = idx * (base * 0.00045)
        wobble = ((idx % 6) - 2.5) * max(base * 0.00028, 0.12)
        prices.append(round(base + drift + wobble, 4))
    prices[-2] = round(prices[-3] - max(base * 0.0010, 0.75), 4)
    prices[-1] = round(prices[-2] + max(base * 0.0024, 1.65), 4)
    return prices

def _cem_codegen_install_lines(broker):
    if broker == "IBKR":
        return ["pip install ibapi"]
    if broker in ("Tradovate", "TopstepX", "TFD"):
        return ["pip install requests websocket-client"]
    if broker in ("Rithmic", "Apex", "MFF", "E2T"):
        return ["pip install async_rithmic"]
    if broker == "Alpaca":
        return ["pip install alpaca-py"]
    if broker == "TradeStation":
        return ["pip install tradestation-api-python"]
    if broker == "OANDA":
        return ["pip install oandapyV20"]
    return ["pip install requests"]

def _cem_codegen_backend_note(broker):
    notes = {
        "IBKR": "Interactive Brokers TWS / IB Gateway via ibapi.",
        "Tradovate": "Tradovate REST + WebSocket futures wrapper scaffold.",
        "Rithmic": "Rithmic futures scaffold using async_rithmic.",
        "Alpaca": "Alpaca bracket-order scaffold using alpaca-py.",
        "TradeStation": "TradeStation REST scaffold using the official Python wrapper.",
        "OANDA": "OANDA v20 scaffold with attached stop-loss / take-profit details.",
        "TopstepX": "TopstepX futures scaffold using a Tradovate-style wrapper by default.",
        "Apex": "Apex prop-firm scaffold using a Rithmic-style wrapper.",
        "MFF": "MyFundedFutures scaffold using a Rithmic-style wrapper.",
        "E2T": "Earn2Trade scaffold using a Rithmic-style wrapper.",
        "TFD": "The Futures Desk scaffold using a Tradovate-style wrapper.",
    }
    return notes.get(broker, "Generated broker scaffold.")

def _cem_codegen_import_block(broker):
    if broker == "IBKR":
        return _cem_codegen_tw.dedent('''
            try:
                from ibapi.client import EClient
                from ibapi.wrapper import EWrapper
                from ibapi.contract import Contract
                from ibapi.order import Order
            except ImportError as exc:
                raise SystemExit("Install dependency first: pip install ibapi") from exc
        ''').strip()
    if broker in ("Tradovate", "TopstepX", "TFD"):
        return _cem_codegen_tw.dedent('''
            try:
                import requests
                import websocket
            except ImportError as exc:
                raise SystemExit("Install dependencies first: pip install requests websocket-client") from exc
        ''').strip()
    if broker in ("Rithmic", "Apex", "MFF", "E2T"):
        return _cem_codegen_tw.dedent('''
            try:
                from async_rithmic import RithmicClient
            except ImportError as exc:
                raise SystemExit("Install dependency first: pip install async_rithmic") from exc
        ''').strip()
    if broker == "Alpaca":
        return _cem_codegen_tw.dedent('''
            try:
                from alpaca.trading.client import TradingClient
                from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
                from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
            except ImportError as exc:
                raise SystemExit("Install dependency first: pip install alpaca-py") from exc
        ''').strip()
    if broker == "TradeStation":
        return _cem_codegen_tw.dedent('''
            try:
                from tradestation import TradeStationClient
            except ImportError as exc:
                raise SystemExit("Install dependency first: pip install tradestation-api-python") from exc
        ''').strip()
    if broker == "OANDA":
        return _cem_codegen_tw.dedent('''
            try:
                from oandapyV20 import API
                import oandapyV20.endpoints.orders as orders
                from oandapyV20.contrib.requests import MarketOrderRequest, StopLossDetails, TakeProfitDetails
            except ImportError as exc:
                raise SystemExit("Install dependency first: pip install oandapyV20") from exc
        ''').strip()
    return "pass"

def _cem_codegen_runner_block(broker):
    if broker == "IBKR":
        return _cem_codegen_tw.dedent('''
            class IBKRApp(EWrapper, EClient):
                def __init__(self) -> None:
                    EClient.__init__(self, self)

            def _ibkr_order(action: str, order_type: str, qty: int, price: float | None = None) -> Order:
                order = Order()
                order.action = action
                order.orderType = order_type
                order.totalQuantity = qty
                if price is not None:
                    if order_type == "LMT":
                        order.lmtPrice = round(price, 4)
                    elif order_type == "STP":
                        order.auxPrice = round(price, 4)
                return order

            def submit_live_order(signal: Signal, qty: float) -> None:
                contract = Contract()
                contract.symbol = SYMBOL
                contract.secType = os.getenv("IBKR_SEC_TYPE", "FUT")
                contract.exchange = os.getenv("IBKR_EXCHANGE", "GLOBEX")
                contract.currency = os.getenv("IBKR_CURRENCY", "USD")
                contract.lastTradeDateOrContractMonth = os.getenv("IBKR_CONTRACT_MONTH", "")
                action = "BUY" if signal.side == "buy" else "SELL"
                exit_action = "SELL" if action == "BUY" else "BUY"
                order_qty = max(int(round(qty)), 1)
                entry = _ibkr_order(action, "MKT", order_qty)
                stop_order = _ibkr_order(exit_action, "STP", order_qty, signal.stop_price)
                target_order = _ibkr_order(exit_action, "LMT", order_qty, signal.take_price)
                print("IBKR contract and bracket orders prepared. Connect to TWS / IB Gateway to submit them:")
                print(json.dumps({
                    "host": os.getenv("IBKR_HOST", "127.0.0.1"),
                    "port": int(os.getenv("IBKR_PORT", "7497")),
                    "client_id": int(os.getenv("IBKR_CLIENT_ID", "7")),
                    "contract": {
                        "symbol": contract.symbol,
                        "secType": contract.secType,
                        "exchange": contract.exchange,
                        "currency": contract.currency,
                        "contractMonth": contract.lastTradeDateOrContractMonth,
                    },
                    "entry": {"action": entry.action, "type": entry.orderType, "qty": entry.totalQuantity},
                    "stop": {"action": stop_order.action, "type": stop_order.orderType, "qty": stop_order.totalQuantity, "auxPrice": round(signal.stop_price, 4)},
                    "target": {"action": target_order.action, "type": target_order.orderType, "qty": target_order.totalQuantity, "limitPrice": round(signal.take_price, 4)},
                }, indent=2))
                _ = IBKRApp
        ''').strip()
    if broker in ("Tradovate", "TopstepX", "TFD"):
        env_prefix = {"Tradovate": "TRADOVATE", "TopstepX": "TOPSTEPX", "TFD": "TFD"}[broker]
        note = {
            "Tradovate": "Use your Tradovate access token and account spec below.",
            "TopstepX": "TopstepX accounts frequently sit on Tradovate or Rithmic. This scaffold defaults to Tradovate-style REST/WebSocket flows.",
            "TFD": "The Futures Desk uses a Tradovate-style wrapper in this generated scaffold.",
        }[broker]
        return _cem_codegen_tw.dedent(f'''
            def submit_live_order(signal: Signal, qty: float) -> None:
                base_url = os.getenv("{env_prefix}_BASE_URL", os.getenv("TRADOVATE_BASE_URL", "https://demo.tradovateapi.com/v1"))
                access_token = os.getenv("{env_prefix}_ACCESS_TOKEN", os.getenv("TRADOVATE_ACCESS_TOKEN", ""))
                account_id = os.getenv("{env_prefix}_ACCOUNT_ID", os.getenv("TRADOVATE_ACCOUNT_ID", "SIM101"))
                order_side = "Buy" if signal.side == "buy" else "Sell"
                exit_side = "Sell" if signal.side == "buy" else "Buy"
                order_qty = max(int(round(qty)), 1)
                payload = {{
                    "entry": {{
                        "accountId": account_id,
                        "symbol": SYMBOL,
                        "action": order_side,
                        "orderType": "Market",
                        "qty": order_qty,
                    }},
                    "stop_loss": {{
                        "accountId": account_id,
                        "symbol": SYMBOL,
                        "action": exit_side,
                        "orderType": "Stop",
                        "price": round(signal.stop_price, 4),
                        "qty": order_qty,
                    }},
                    "take_profit": {{
                        "accountId": account_id,
                        "symbol": SYMBOL,
                        "action": exit_side,
                        "orderType": "Limit",
                        "price": round(signal.take_price, 4),
                        "qty": order_qty,
                    }},
                }}
                print("{note}")
                print(json.dumps(payload, indent=2))
                if access_token:
                    print("POST entry to:", base_url + "/order/placeorder")
                    print("Use your websocket session for live order / fill management.")
                else:
                    print("Set {env_prefix}_ACCESS_TOKEN (or TRADOVATE_ACCESS_TOKEN) before posting these payloads.")
                _ = requests, websocket
        ''').strip()
    if broker in ("Rithmic", "Apex", "MFF", "E2T"):
        env_prefix = {"Rithmic": "RITHMIC", "Apex": "APEX", "MFF": "MFF", "E2T": "E2T"}[broker]
        note = {
            "Rithmic": "Use your direct Rithmic credentials and gateway URL below.",
            "Apex": "Apex accounts generally route through Rithmic. Use the Apex-provided Rithmic credentials.",
            "MFF": "MyFundedFutures accounts generally route through Rithmic. Use the funded-account credentials here.",
            "E2T": "Earn2Trade accounts generally route through Rithmic. Use the evaluation or funded credentials here.",
        }[broker]
        return _cem_codegen_tw.dedent(f'''
            def submit_live_order(signal: Signal, qty: float) -> None:
                order_qty = max(int(round(qty)), 1)
                payload = {{
                    "connection": {{
                        "user": os.getenv("{env_prefix}_USER", os.getenv("RITHMIC_USER", "")),
                        "password": os.getenv("{env_prefix}_PASSWORD", os.getenv("RITHMIC_PASSWORD", "")),
                        "system_name": os.getenv("{env_prefix}_SYSTEM_NAME", os.getenv("RITHMIC_SYSTEM_NAME", "Rithmic Paper Trading")),
                        "app_name": os.getenv("{env_prefix}_APP_NAME", os.getenv("RITHMIC_APP_NAME", "CEMbot")),
                        "app_version": os.getenv("{env_prefix}_APP_VERSION", os.getenv("RITHMIC_APP_VERSION", "1.0")),
                        "url": os.getenv("{env_prefix}_URL", os.getenv("RITHMIC_URL", "rituz00100.rithmic.com:443")),
                    }},
                    "entry": {{"symbol": SYMBOL, "side": signal.side, "qty": order_qty, "type": "market"}},
                    "stop_loss": {{"qty": order_qty, "price": round(signal.stop_price, 4)}},
                    "take_profit": {{"qty": order_qty, "price": round(signal.take_price, 4)}},
                }}
                print("{note}")
                print(json.dumps(payload, indent=2))
                print("Use async_rithmic to connect, submit the market entry, then attach server-side OCO exits.")
                _ = RithmicClient
        ''').strip()
    if broker == "Alpaca":
        return _cem_codegen_tw.dedent('''
            def submit_live_order(signal: Signal, qty: float) -> None:
                api_key = os.getenv("ALPACA_API_KEY", "")
                api_secret = os.getenv("ALPACA_API_SECRET", "")
                paper = os.getenv("ALPACA_PAPER", "true").lower() != "false"
                side = OrderSide.BUY if signal.side == "buy" else OrderSide.SELL
                order_data = MarketOrderRequest(
                    symbol=SYMBOL,
                    qty=max(round(qty, 4), 1),
                    side=side,
                    time_in_force=TimeInForce.DAY,
                    order_class=OrderClass.BRACKET,
                    take_profit=TakeProfitRequest(limit_price=round(signal.take_price, 4)),
                    stop_loss=StopLossRequest(stop_price=round(signal.stop_price, 4)),
                )
                print("Alpaca bracket order prepared:")
                print(order_data)
                if api_key and api_secret:
                    trading_client = TradingClient(api_key, api_secret, paper=paper)
                    print("Submit with: trading_client.submit_order(order_data=order_data)")
                    _ = trading_client
                else:
                    print("Set ALPACA_API_KEY and ALPACA_API_SECRET to send the bracket order.")
        ''').strip()
    if broker == "TradeStation":
        return _cem_codegen_tw.dedent('''
            def submit_live_order(signal: Signal, qty: float) -> None:
                order_qty = max(int(round(qty)), 1)
                payload = {
                    "Symbol": SYMBOL,
                    "OrderType": "Market",
                    "TradeAction": "BUY" if signal.side == "buy" else "SELLSHORT",
                    "Quantity": order_qty,
                    "Route": os.getenv("TRADESTATION_ROUTE", "Intelligent"),
                    "TimeInForce": {"Duration": "DAY"},
                    "AdvancedOptions": {
                        "BracketType": "OCO",
                        "ProfitTarget": round(signal.take_price, 4),
                        "StopLoss": round(signal.stop_price, 4),
                    },
                }
                print("TradeStation order payload prepared:")
                print(json.dumps(payload, indent=2))
                if os.getenv("TRADESTATION_CLIENT_ID") and os.getenv("TRADESTATION_REFRESH_TOKEN"):
                    print("Instantiate TradeStationClient with your OAuth credentials, then submit the payload above.")
                    _ = TradeStationClient
                else:
                    print("Set TRADESTATION_CLIENT_ID, TRADESTATION_CLIENT_SECRET, and TRADESTATION_REFRESH_TOKEN first.")
        ''').strip()
    if broker == "OANDA":
        return _cem_codegen_tw.dedent('''
            def submit_live_order(signal: Signal, qty: float) -> None:
                instrument = SYMBOL.replace("/", "_")
                units = max(int(round(qty)), 1)
                signed_units = units if signal.side == "buy" else -units
                order_data = MarketOrderRequest(
                    instrument=instrument,
                    units=signed_units,
                    takeProfitOnFill=TakeProfitDetails(price=round(signal.take_price, 4)).data,
                    stopLossOnFill=StopLossDetails(price=round(signal.stop_price, 4)).data,
                )
                print("OANDA market order with attached exits prepared:")
                print(json.dumps(order_data.data, indent=2))
                access_token = os.getenv("OANDA_ACCESS_TOKEN", "")
                account_id = os.getenv("OANDA_ACCOUNT_ID", "")
                if access_token and account_id:
                    client = API(access_token=access_token)
                    request_obj = orders.OrderCreate(account_id, data=order_data.data)
                    print("Submit with: client.request(request_obj)")
                    _ = client, request_obj
                else:
                    print("Set OANDA_ACCESS_TOKEN and OANDA_ACCOUNT_ID to submit this order.")
        ''').strip()
    return _cem_codegen_tw.dedent('''
        def submit_live_order(signal: Signal, qty: float) -> None:
            print("Broker integration placeholder:")
            print(json.dumps({"symbol": SYMBOL, "side": signal.side, "qty": qty}, indent=2))
    ''').strip()

def _cem_codegen_render_script(body):
    broker = _cem_codegen_clean_broker(body.get("broker"))
    symbol = _cem_codegen_clean_symbol(body.get("symbol"))
    ema_fast = _cem_codegen_int(body, "ema_fast", 9, 1)
    ema_slow = _cem_codegen_int(body, "ema_slow", 21, max(ema_fast + 1, 2))
    rsi_period = _cem_codegen_int(body, "rsi_period", 14, 1)
    stop_loss = _cem_codegen_float(body, "stop_loss", 1.5, 0.01)
    take_profit = _cem_codegen_float(body, "take_profit", 3.0, 0.01)
    position_size = _cem_codegen_float(body, "position_size", 10.0, 0.01)
    broker_slug = _cem_codegen_slug(broker)
    symbol_slug = _cem_codegen_slug(symbol)
    filename = f"cembot_{broker_slug}_{symbol_slug}.py"
    install_block = "\\n".join(f"  {line}" for line in _cem_codegen_install_lines(broker))
    template = _cem_codegen_Template(_cem_codegen_tw.dedent('''
        #!/usr/bin/env python3
        # CEMTrading888 generated Python strategy scaffold.
        # Broker: $broker
        # Symbol: $symbol
        # Backend note: $backend_note
        #
        # Install:
        $install_block
        #
        # Run:
        #   python $filename
        #
        # This scaffold mirrors the cockpit parameters, uses an EMA crossover with RSI confirmation,
        # and calculates stop loss / take profit exits before creating broker-specific order payloads.

        from __future__ import annotations

        import json
        import os
        from dataclasses import dataclass
        from typing import Optional

        $import_block

        BROKER = "$broker"
        SYMBOL = "$symbol"
        EMA_FAST = $ema_fast
        EMA_SLOW = $ema_slow
        RSI_PERIOD = $rsi_period
        STOP_LOSS_PCT = $stop_loss
        TAKE_PROFIT_PCT = $take_profit
        POSITION_SIZE_PCT = $position_size

        SAMPLE_CLOSES = $sample_prices

        @dataclass
        class Signal:
            side: str
            entry_price: float
            stop_price: float
            take_price: float

        def ema(prices: list[float], period: int) -> list[float]:
            period = max(period, 1)
            alpha = 2.0 / (period + 1.0)
            out: list[float] = []
            current: Optional[float] = None
            for price in prices:
                current = price if current is None else (price * alpha) + (current * (1.0 - alpha))
                out.append(round(current, 6))
            return out

        def rsi(prices: list[float], period: int) -> list[float]:
            period = max(period, 1)
            if len(prices) < 2:
                return [50.0 for _ in prices]
            gains = [0.0]
            losses = [0.0]
            for prev, curr in zip(prices, prices[1:]):
                change = curr - prev
                gains.append(max(change, 0.0))
                losses.append(abs(min(change, 0.0)))
            out: list[float] = []
            avg_gain = 0.0
            avg_loss = 0.0
            for idx in range(len(prices)):
                avg_gain = ((avg_gain * (period - 1)) + gains[idx]) / period
                avg_loss = ((avg_loss * (period - 1)) + losses[idx]) / period
                if avg_loss == 0:
                    out.append(100.0 if avg_gain else 50.0)
                    continue
                rs = avg_gain / avg_loss
                out.append(round(100.0 - (100.0 / (1.0 + rs)), 4))
            return out

        def build_signal(prices: list[float]) -> Optional[Signal]:
            need = max(EMA_SLOW, RSI_PERIOD) + 2
            if len(prices) < need:
                return None
            fast = ema(prices, EMA_FAST)
            slow = ema(prices, EMA_SLOW)
            momentum = rsi(prices, RSI_PERIOD)
            prev_fast, curr_fast = fast[-2], fast[-1]
            prev_slow, curr_slow = slow[-2], slow[-1]
            current_price = prices[-1]
            current_rsi = momentum[-1]
            if prev_fast <= prev_slow and curr_fast > curr_slow and current_rsi >= 50.0:
                return Signal(
                    side="buy",
                    entry_price=current_price,
                    stop_price=round(current_price * (1.0 - STOP_LOSS_PCT / 100.0), 4),
                    take_price=round(current_price * (1.0 + TAKE_PROFIT_PCT / 100.0), 4),
                )
            if prev_fast >= prev_slow and curr_fast < curr_slow and current_rsi <= 50.0:
                return Signal(
                    side="sell",
                    entry_price=current_price,
                    stop_price=round(current_price * (1.0 + STOP_LOSS_PCT / 100.0), 4),
                    take_price=round(current_price * (1.0 - TAKE_PROFIT_PCT / 100.0), 4),
                )
            return None

        def calc_position_units(entry_price: float, account_equity: float = 10000.0) -> float:
            allocation = max(account_equity * (POSITION_SIZE_PCT / 100.0), 1.0)
            return round(max(allocation / max(entry_price, 0.0001), 1.0), 4)

        $runner_block

        def main() -> None:
            signal = build_signal(SAMPLE_CLOSES)
            print(f"{BROKER} strategy scaffold for {SYMBOL}")
            print(f"EMA {EMA_FAST}/{EMA_SLOW} | RSI {RSI_PERIOD} | SL {STOP_LOSS_PCT}% | TP {TAKE_PROFIT_PCT}% | Size {POSITION_SIZE_PCT}%")
            if signal is None:
                print("No fresh EMA crossover signal in SAMPLE_CLOSES. Replace the sample series with live market data.")
                return
            qty = calc_position_units(signal.entry_price)
            print(json.dumps({
                "side": signal.side,
                "entry_price": round(signal.entry_price, 4),
                "stop_price": round(signal.stop_price, 4),
                "take_price": round(signal.take_price, 4),
                "position_units": qty,
            }, indent=2))
            submit_live_order(signal, qty)

        if __name__ == "__main__":
            main()
    ''').strip())
    script = template.substitute(
        broker=broker,
        symbol=symbol,
        backend_note=_cem_codegen_backend_note(broker),
        install_block=install_block,
        filename=filename,
        import_block=_cem_codegen_import_block(broker),
        ema_fast=str(ema_fast),
        ema_slow=str(ema_slow),
        rsi_period=str(rsi_period),
        stop_loss=str(round(stop_loss, 4)),
        take_profit=str(round(take_profit, 4)),
        position_size=str(round(position_size, 4)),
        sample_prices=repr(_cem_codegen_sample_prices(symbol)),
        runner_block=_cem_codegen_runner_block(broker),
    )
    return broker, symbol, filename, script.strip() + "\\n"

@app.post("/api/generate_code")
async def api_generate_code(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    broker, symbol, filename, code = _cem_codegen_render_script(body)
    return {
        "broker": broker,
        "symbol": symbol,
        "filename": filename,
        "code": code,
    }
# === CEM_GENERATE_CODE_INJECT_END ===
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
