from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import JSONResponse as _JSONResponse
def _json_resp(data, status_code=200):
    return _JSONResponse(content=data, status_code=status_code)

import yfinance as yf, numpy as np, pickle, os

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health(): return {"status":"ok","server":"CEMTrading888"}

import uuid as _uuid, math as _math, urllib.request as _urllib_req

def _log_to_supabase(row):
    """Fire-and-forget insert into cem_strategy_results via Supabase REST."""
    try:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_KEY", "")
        if not url or not key:
            return
        import json as _j
        data = _j.dumps(row).encode()
        req = _urllib_req.Request(
            f"{url}/rest/v1/cem_strategy_results",
            data=data,
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            method="POST",
        )
        _urllib_req.urlopen(req, timeout=5)
    except Exception:
        pass

def _calc_sharpe(equity, rf_annual=0.05):
    if len(equity) < 2:
        return 0.0
    returns = [(equity[i] - equity[i-1]) / equity[i-1] for i in range(1, len(equity)) if equity[i-1] > 0]
    if not returns:
        return 0.0
    avg = sum(returns) / len(returns)
    rf_daily = rf_annual / 252
    excess = [r - rf_daily for r in returns]
    avg_ex = sum(excess) / len(excess)
    var = sum((r - avg_ex) ** 2 for r in excess) / max(len(excess) - 1, 1)
    std = _math.sqrt(var) if var > 0 else 0.001
    return round((avg_ex / std) * _math.sqrt(252), 2)

def _calc_strategy_score(total_return, win_rate, max_dd, profit_factor, sharpe):
    """Weighted composite: higher = better. Scale 0-100."""
    ret_sc = min(max(total_return, -50), 200) / 2
    wr_sc = win_rate
    dd_sc = max(100 - max_dd * 2, 0)
    pf_sc = min(profit_factor * 20, 100)
    sh_sc = min(max((sharpe + 1) * 25, 0), 100)
    return round(ret_sc * 0.25 + wr_sc * 0.20 + dd_sc * 0.20 + pf_sc * 0.15 + sh_sc * 0.20, 1)

def _tag_result(total_return, strategy_score):
    if total_return >= 100:
        return "unicorn"
    if total_return >= 50:
        return "extreme_winner"
    if strategy_score >= 65:
        return "win"
    if total_return <= -30:
        return "extreme_loser"
    if total_return < 0:
        return "loss"
    return "breakeven"


@app.api_route("/mcp-proxy", methods=["GET","POST","OPTIONS"])
async def mcp_streamable(request: Request):
    if request.method == "OPTIONS":
        from fastapi.responses import Response as _R
        return _R("", headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,Accept",
        })
    if request.method == "GET":
        async def ka():
            while True:
                yield ": ping\r\n\r\n"
                await _asyncio.sleep(20)
        return _SR(ka(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        })
    try:
        body = await request.json()
    except Exception:
        return _json_resp({"jsonrpc":"2.0","id":None,"error":{"code":-32700,"message":"Parse error"}})
    method = body.get("method", "")
    id_ = body.get("id")
    params = body.get("params") or {}
    if method == "initialize":
        result = {"protocolVersion":"2025-03-26","capabilities":{"tools":{}},"serverInfo":{"name":"CEMTrading888-Brain","version":"3.0.0"}}
    elif method in ("notifications/initialized","initialized"):
        result = {}
    elif method == "tools/list":
        result = {"tools": _MCP_TOOLS}
    elif method == "tools/call":
        name = params.get("name","")
        args = params.get("arguments") or {}
        if name == "write_brain":
            out = _do_write_brain(args.get("key","UNNAMED"), args.get("text",""), args.get("category","context"))
        elif name == "write_task":
            out = _do_write_task(args.get("title",""), args.get("description",""), args.get("status","pending"))
        elif name == "read_brain":
            out = _do_read_brain(args.get("query",""))
        elif name == "get_status":
            out = _do_get_status()
        else:
            return _json_resp({"jsonrpc":"2.0","id":id_,"error":{"code":-32601,"message":"Tool not found"}})
        result = _tool_result(out)
    else:
        return _json_resp({"jsonrpc":"2.0","id":id_,"error":{"code":-32601,"message":"Method not found"}})
    rd = _json.dumps({"jsonrpc":"2.0","id":id_,"result":result})
    async def sse_resp():
        yield "data: " + rd + "\r\n\r\n"
    return _SR(sse_resp(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Access-Control-Allow-Origin": "*",
    })
# ── End MCP Transport ─────────────────────────────────────────────────────────────────────────────

# ── Paper Trading Engine ──────────────────────────────────────────────────────────────
import datetime as _dt

def _supa_post(path, data, method="POST"):
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        return None
    import json as _j
    body = _j.dumps(data).encode()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    req = _urllib_req.Request(f"{url}/rest/v1/{path}", data=body, headers=headers, method=method)
    try:
        resp = _urllib_req.urlopen(req, timeout=8)
        return _j.loads(resp.read())
    except Exception:
        return None

def _supa_get(path):
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        return None
    import json as _j
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    req = _urllib_req.Request(f"{url}/rest/v1/{path}", headers=headers)
    try:
        resp = _urllib_req.urlopen(req, timeout=8)
        return _j.loads(resp.read())
    except Exception:
        return None

def _supa_patch(path, data):
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        return None
    import json as _j
    body = _j.dumps(data).encode()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    req = _urllib_req.Request(f"{url}/rest/v1/{path}", data=body, headers=headers, method="PATCH")
    try:
        resp = _urllib_req.urlopen(req, timeout=8)
        return _j.loads(resp.read())
    except Exception:
        return None

@app.post("/api/paper-trade")
async def paper_trade(request: Request):
    try:
        p = await request.json()
        action = p.get("action", "")
        user_id = p.get("user_id", "anonymous")
        session_id = p.get("session_id", "")

        if action == "start":
            active = _supa_get(f"cem_paper_trading?user_id=eq.{user_id}&status=eq.active&limit=1")
            if active and len(active) > 0:
                return {"error": "You already have an active paper trading session", "session": active[0]}

            params = p.get("params", {})
            asset = p.get("asset", "MGC")
            asset_class = p.get("asset_class", "Micro Futures")
            ticker_map = {"Micro Futures": "ES=F", "Crypto": "BTC-USD", "Forex": "EURUSD=X", "Stocks": "SPY", "MES": "ES=F", "MNQ": "NQ=F", "MGC": "GC=F"}
            ticker = ticker_map.get(asset, ticker_map.get(asset_class, "ES=F"))

            now = _dt.datetime.utcnow()
            expires = now + _dt.timedelta(days=30)
            sid = f"pt-{user_id}-{int(now.timestamp())}"

            try:
                current_price = float(yf.download(ticker, period="1d", interval="1d", progress=False, timeout=10)["Close"].iloc[-1])
            except Exception:
                current_price = 0

            row = {
                "session_id": sid,
                "user_id": user_id,
                "strategy_params": params,
                "asset_class": asset_class,
                "asset": ticker,
                "expires_at": expires.isoformat(),
                "current_equity": 10000,
                "starting_equity": 10000,
                "trade_count": 0,
                "trade_limit": 100,
                "pnl_pct": 0,
                "status": "active",
                "trades": [],
                "last_price": current_price,
            }
            result = _supa_post("cem_paper_trading", row)
            if result and len(result) > 0:
                return {"status": "started", "session": result[0], "message": "Paper trading activated! 30 days, 100 trades max."}
            return {"error": "Failed to create session"}

        elif action == "check":
            if not session_id:
                return {"error": "session_id required"}
            sessions = _supa_get(f"cem_paper_trading?session_id=eq.{session_id}&limit=1")
            if not sessions or len(sessions) == 0:
                return {"error": "Session not found"}
            sess = sessions[0]

            if sess["status"] != "active":
                return {"status": "expired", "session": sess, "message": "This paper trading session has ended."}

            now = _dt.datetime.utcnow()
            if sess.get("expires_at") and now > _dt.datetime.fromisoformat(sess["expires_at"].replace("Z", "+00:00").replace("+00:00", "").replace("+00", "")):
                _supa_patch(f"cem_paper_trading?session_id=eq.{session_id}", {"status": "expired"})
                sess["status"] = "expired"
                return {"status": "expired", "session": sess, "message": "Your 30-day paper trading trial is complete."}

            if sess["trade_count"] >= sess["trade_limit"]:
                _supa_patch(f"cem_paper_trading?session_id=eq.{session_id}", {"status": "expired"})
                sess["status"] = "expired"
                return {"status": "expired", "session": sess, "message": "Trade limit reached (100 trades)."}

            ticker = sess.get("asset", "GC=F")
            try:
                df = yf.download(ticker, period="5d", interval="1d", progress=False, timeout=10)
                if df.empty or len(df) < 2:
                    return {"status": "active", "session": sess, "signal": None, "message": "Waiting for data..."}
                if hasattr(df.columns, "levels"):
                    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
                current_price = float(df["Close"].iloc[-1])
                prev_price = float(df["Close"].iloc[-2])
            except Exception as e:
                return {"status": "active", "session": sess, "signal": None, "message": f"Price fetch error: {e}"}

            last_price = float(sess.get("last_price") or current_price)
            params = sess.get("strategy_params") or {}
            sl_pct = float(params.get("slPct", 1.5)) / 100
            tp_pct = float(params.get("tpPct", 3.75)) / 100

            equity = float(sess["current_equity"])
            starting = float(sess["starting_equity"])
            trades_list = sess.get("trades") or []
            trade_count = int(sess["trade_count"])
            signal = None
            trade_made = None

            in_position = len(trades_list) > 0 and trades_list[-1].get("status") == "open"

            if in_position:
                open_trade = trades_list[-1]
                entry = float(open_trade["entry_price"])
                change_pct = (current_price - entry) / entry

                if change_pct <= -sl_pct:
                    pnl_pct = -sl_pct
                    pnl_dollar = equity * pnl_pct
                    equity += pnl_dollar
                    open_trade["status"] = "closed"
                    open_trade["exit_price"] = round(current_price, 2)
                    open_trade["pnl"] = round(float(pnl_dollar), 2)
                    open_trade["reason"] = "SL"
                    trade_count += 1
                    signal = "SL_HIT"
                    trade_made = {"type": "close", "reason": "SL", "pnl": round(float(pnl_dollar), 2)}
                elif change_pct >= tp_pct:
                    pnl_pct = tp_pct
                    pnl_dollar = equity * pnl_pct
                    equity += pnl_dollar
                    open_trade["status"] = "closed"
                    open_trade["exit_price"] = round(current_price, 2)
                    open_trade["pnl"] = round(float(pnl_dollar), 2)
                    open_trade["reason"] = "TP"
                    trade_count += 1
                    signal = "TP_HIT"
                    trade_made = {"type": "close", "reason": "TP", "pnl": round(float(pnl_dollar), 2)}
            else:
                price_change = (current_price - prev_price) / prev_price if prev_price > 0 else 0
                if price_change > 0.001:
                    trades_list.append({
                        "entry_price": round(current_price, 2),
                        "status": "open",
                        "opened_at": now.isoformat(),
                    })
                    signal = "ENTRY"
                    trade_made = {"type": "open", "entry_price": round(current_price, 2)}

            pnl_total = round(((equity - starting) / starting) * 100, 2)

            update = {
                "current_equity": round(float(equity), 2),
                "pnl_pct": pnl_total,
                "trade_count": trade_count,
                "trades": trades_list,
                "last_price": round(current_price, 2),
                "last_check_at": now.isoformat(),
            }
            _supa_patch(f"cem_paper_trading?session_id=eq.{session_id}", update)
            sess.update(update)

            remaining = sess["trade_limit"] - trade_count
            msg = None
            if trade_made and trade_made["type"] == "open":
                msg = f"Signal fired! Paper trade opened at ${trade_made['entry_price']}."
            elif trade_made and trade_made["type"] == "close":
                msg = f"Trade closed ({trade_made['reason']}). P&L: ${trade_made['pnl']:.2f}. Equity: ${equity:.2f}."
            elif remaining <= 20 and remaining > 0:
                msg = f"{remaining} trades remaining on your free tier."

            return {"status": "active", "session": sess, "signal": signal, "trade": trade_made, "message": msg, "remaining_trades": remaining}

        elif action == "stop":
            if not session_id:
                return {"error": "session_id required"}
            _supa_patch(f"cem_paper_trading?session_id=eq.{session_id}", {"status": "stopped"})
            return {"status": "stopped", "message": "Paper trading session stopped."}

        elif action == "status":
            sessions = _supa_get(f"cem_paper_trading?user_id=eq.{user_id}&order=started_at.desc&limit=5")
            return {"sessions": sessions or []}

        else:
            return {"error": "Invalid action. Use: start, check, stop, status"}
    except Exception as e:
        return {"error": str(e)}

# ── End Paper Trading ─────────────────────────────────────────────────────────────────────

# ── Direct Deploy Endpoints ──────────────────────────────────────────────────
import subprocess as _subprocess
import os as _os

_EXEC_WHITELIST = [
    "systemctl restart cemtrading888",
    "pkill -f uvicorn",
    "journalctl -u cemtrading888 -n 50 --no-pager",
    "df -h",
    "free -m",
    "systemctl status cemtrading888",
]

def _check_token(request):
    token = _os.environ.get("CEM_EXEC_TOKEN","")
    return request.headers.get("X-CEM-Token","") == token and token != ""

@app.post("/mcp/exec")
async def mcp_exec(request: Request):
    if not _check_token(request):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error":"forbidden"}, status_code=403)
    body = await request.json()
    cmd = body.get("command","")
    if cmd not in _EXEC_WHITELIST:
        return _json_resp({"error":"command not allowed"})
    result = _subprocess.run(cmd.split(), capture_output=True, text=True, timeout=30)
    return _json_resp({"output": result.stdout + result.stderr})

@app.post("/mcp/write")
async def mcp_write(request: Request):
    if not _check_token(request):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error":"forbidden"}, status_code=403)
    body = await request.json()
    filename = _os.path.basename(body.get("filename",""))
    if not any(filename.endswith(ext) for ext in [".html",".py",".txt"]):
        return _json_resp({"error":"file type not allowed"})
    path = f"/var/www/cemtrading888/{filename}"
    open(path,"w").write(body.get("content",""))
    return _json_resp({"success": True, "path": path})
# ── End Direct Deploy Endpoints ───────────────────────────────────────────────


































































































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







































































































































































































































































































































































































































































































































































































































































































































































































































































































































# === CEM_RESEARCH_STREAM_INJECT_START ===
import json as _cem_rs_json
import os as _cem_rs_os

from fastapi import Request as _cem_rs_Request
from fastapi.responses import StreamingResponse as _cem_rs_StreamingResponse

CEM_RESEARCH_SYSTEM = """You are CEM — an elite AI trading strategist built into CEMTrading888's Strategy Lab.

You speak with authority, precision, and conviction. You are direct — no hedging, no filler.
Your responses are structured into clear sections. Use these headers:

━━ REGIME ANALYSIS ━━
Your read on current market conditions based on the indicators and price action provided.

━━ STRATEGY ASSESSMENT ━━
What works and what doesn't about the trader's current parameters.

━━ SPECIFIC IMPROVEMENTS ━━
Concrete parameter suggestions with reasoning. Give numbers, not vague advice.

━━ PROP FIRM ALIGNMENT ━━
Will this strategy pass the trader's selected prop firm evaluation? What rules are at risk?

━━ CONSCIOUSNESS COACHING ━━
Your unique psychological/mindset insight. Help the trader think like a professional.

Keep responses focused and actionable. You have access to the trader's full context below."""

@app.post("/api/research-stream")
async def api_research_stream(request: _cem_rs_Request):
    body = await request.json()
    message = body.get("message", "")
    context = body.get("context", {})
    history = body.get("history", [])

    key = (_cem_rs_os.getenv("ANTHROPIC_API_KEY") or "").strip()
    model = _cem_rs_os.getenv("COACH_ANTHROPIC_MODEL") or "claude-sonnet-4-6"

    if not key:
        async def no_key():
            yield "data: " + _cem_rs_json.dumps({"type": "error", "text": "Configure ANTHROPIC_API_KEY on the server for CEM Research."}) + "\n\n"
        return _cem_rs_StreamingResponse(no_key(), media_type="text/event-stream")

    # Build context block
    ctx_lines = []
    if context.get("symbol"):
        ctx_lines.append(f"Asset: {context['symbol']}")
    if context.get("timeframe"):
        ctx_lines.append(f"Timeframe: {context['timeframe']}")
    if context.get("indicators"):
        ctx_lines.append(f"Active indicators: {context['indicators']}")
    if context.get("backtest"):
        ctx_lines.append(f"Last backtest: {context['backtest']}")
    if context.get("propFirm"):
        ctx_lines.append(f"Prop firm mode: {context['propFirm']}")
    if context.get("params"):
        ctx_lines.append(f"Strategy params: {context['params']}")

    system = CEM_RESEARCH_SYSTEM
    if ctx_lines:
        system += "\n\n--- TRADER CONTEXT ---\n" + "\n".join(ctx_lines)

    messages = []
    for h in (history or [])[-10:]:
        role = h.get("role", "user")
        content = h.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    import urllib.request as _rs_uq
    import urllib.error as _rs_ue

    async def stream_response():
        try:
            payload = _cem_rs_json.dumps({
                "model": model,
                "max_tokens": 2048,
                "system": system,
                "messages": messages,
                "stream": True,
            })
            req = _rs_uq.Request(
                "https://api.anthropic.com/v1/messages",
                data=payload.encode(),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )
            with _rs_uq.urlopen(req, timeout=90) as resp:
                buffer = ""
                for chunk in resp:
                    buffer += chunk.decode("utf-8", errors="replace")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line or line.startswith(":"):
                            continue
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                yield "data: " + _cem_rs_json.dumps({"type": "done"}) + "\n\n"
                                return
                            try:
                                event = _cem_rs_json.loads(data_str)
                                etype = event.get("type", "")
                                if etype == "content_block_delta":
                                    delta = event.get("delta", {})
                                    text = delta.get("text", "")
                                    if text:
                                        yield "data: " + _cem_rs_json.dumps({"type": "text", "text": text}) + "\n\n"
                                elif etype == "message_stop":
                                    yield "data: " + _cem_rs_json.dumps({"type": "done"}) + "\n\n"
                                    return
                            except _cem_rs_json.JSONDecodeError:
                                pass
            yield "data: " + _cem_rs_json.dumps({"type": "done"}) + "\n\n"
        except _rs_ue.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:200]
            yield "data: " + _cem_rs_json.dumps({"type": "error", "text": f"Anthropic API error ({e.code}): {err_body}"}) + "\n\n"
        except Exception as e:
            yield "data: " + _cem_rs_json.dumps({"type": "error", "text": str(e)[:200]}) + "\n\n"

    return _cem_rs_StreamingResponse(stream_response(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
# === CEM_RESEARCH_STREAM_INJECT_END ===

# === CEM_SPEAK_ELEVENLABS_START ===
import os as _spk_os
import json as _spk_json
import urllib.request as _spk_uq
import urllib.error as _spk_ue
from fastapi import Request as _spk_Req
from fastapi.responses import Response as _spk_Resp

@app.post("/api/speak")
async def api_speak(request: _spk_Req):
    data = await request.json()
    text = data.get("text", "")[:2000]
    voice_id = data.get("voice_id", "EXAVITQu4vr4xnSDxMaL")
    key = (_spk_os.getenv("ELEVENLABS_API_KEY") or "").strip()
    if not key:
        return _spk_Resp(content=b"", status_code=503)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    payload = _spk_json.dumps({
        "text": text,
        "model_id": "eleven_flash_v2_5",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.0, "use_speaker_boost": True}
    }).encode()
    req = _spk_uq.Request(url, data=payload, headers={
        "Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": key
    }, method="POST")
    try:
        with _spk_uq.urlopen(req, timeout=30) as resp:
            audio = resp.read()
        return _spk_Resp(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "no-cache"})
    except _spk_ue.HTTPError as e:
        return _spk_Resp(content=b"", status_code=e.code)
    except Exception:
        return _spk_Resp(content=b"", status_code=500)
# === CEM_SPEAK_ELEVENLABS_END ===

# === CEM_LIVE_PRICES_START ===
import os as _lp_os
import json as _lp_json
import urllib.request as _lp_uq
import urllib.error as _lp_ue
from datetime import datetime as _lp_dt

@app.get("/api/prices-live")
async def api_prices_live(symbol: str = "MGC", interval: str = "1day", range: str = "5y"):
    TWELVE_KEY = (_lp_os.getenv("TWELVE_DATA_API_KEY") or "").strip()
    AV_KEY = (_lp_os.getenv("ALPHA_VANTAGE_API_KEY") or "").strip()

    twelve_map = {"MGC":"GC1!","MES":"ES1!","MNQ":"NQ1!","MYM":"YM1!","MCL":"CL1!","MBT":"BTC1!","GC":"GC1!","ES":"ES1!","NQ":"NQ1!","BTC/USD":"BTC/USD","ETH/USD":"ETH/USD","SOL/USD":"SOL/USD","EUR/USD":"EUR/USD","GBP/USD":"GBP/USD","USD/JPY":"USD/JPY","AUD/USD":"AUD/USD","AAPL":"AAPL","NVDA":"NVDA","MSFT":"MSFT","TSLA":"TSLA","AMZN":"AMZN"}
    size_map = {"1M":30,"3M":90,"6M":180,"1Y":365,"2Y":730,"5Y":1260,"MAX":5000}
    int_map = {"1D":"1day","D":"1day","1W":"1week","W":"1week","1M":"1month","M":"1month","4H":"4h","4h":"4h","1H":"1h","1h":"1h","15M":"15min","15m":"15min","5M":"5min","5m":"5min","1m":"1min"}

    # Try Twelve Data
    if TWELVE_KEY:
        try:
            td_sym = twelve_map.get(symbol, symbol)
            td_int = int_map.get(interval, "1day")
            td_size = size_map.get(range.upper(), 1260)
            url = f"https://api.twelvedata.com/time_series?symbol={td_sym}&interval={td_int}&outputsize={td_size}&apikey={TWELVE_KEY}&format=JSON"
            req = _lp_uq.Request(url, headers={"User-Agent": "CEM/1.0"})
            with _lp_uq.urlopen(req, timeout=10) as resp:
                data = _lp_json.loads(resp.read().decode())
            if data.get("status") == "ok" and data.get("values"):
                candles = []
                for bar in reversed(data["values"]):
                    try:
                        fmt = "%Y-%m-%d %H:%M:%S" if " " in bar["datetime"] else "%Y-%m-%d"
                        t = int(_lp_dt.strptime(bar["datetime"], fmt).timestamp())
                        candles.append({"time": t, "open": float(bar["open"]), "high": float(bar["high"]), "low": float(bar["low"]), "close": float(bar["close"])})
                    except:
                        pass
                if len(candles) > 10:
                    return {"candles": candles, "source": "twelve_data", "symbol": symbol}
        except Exception as e:
            print(f"Twelve Data error: {e}")

    # Try Alpha Vantage
    if AV_KEY:
        try:
            av_map = {"MGC":"GC=F","MES":"ES=F","MNQ":"NQ=F","GC":"GC=F","BTC/USD":"BTC","ETH/USD":"ETH","AAPL":"AAPL","NVDA":"NVDA","MSFT":"MSFT","TSLA":"TSLA","AMZN":"AMZN"}
            av_sym = av_map.get(symbol, symbol)
            url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={av_sym}&outputsize=full&apikey={AV_KEY}"
            req = _lp_uq.Request(url, headers={"User-Agent": "CEM/1.0"})
            with _lp_uq.urlopen(req, timeout=10) as resp:
                data = _lp_json.loads(resp.read().decode())
            ts = data.get("Time Series (Daily)", {})
            candles = []
            for ds, bar in sorted(ts.items()):
                t = int(_lp_dt.strptime(ds, "%Y-%m-%d").timestamp())
                candles.append({"time": t, "open": float(bar["1. open"]), "high": float(bar["2. high"]), "low": float(bar["3. low"]), "close": float(bar["4. close"])})
            if len(candles) > 10:
                return {"candles": candles[-1260:], "source": "alpha_vantage", "symbol": symbol}
        except Exception as e:
            print(f"Alpha Vantage error: {e}")

    return {"candles": [], "source": "generated", "symbol": symbol}
# === CEM_LIVE_PRICES_END ===

# === CEM_DYNAMIC_VOICE_START ===
def _cem_build_dynamic_system(message="", sel=None):
    base = (
        "You are CEM, an elite AI trading strategist built into CEMTrading888.\n"
        "PERSONALITY: Warm, direct, powerful, wise. Short punchy sentences. Never waste words.\n"
        "You see the trader setup - their EMA settings, stop loss, take profit, R:R ratio.\n"
        "When R:R is below 1:1 say the math loses over time. When 2:1 say solid foundation.\n"
        "NEVER start two responses the same way. NEVER say Great question or Certainly.\n"
        "NEVER give more than 4 sentences unless deeply technical.\n"
        "ALWAYS reference specific numbers from their strategy when available.\n"
        "Never give personalized financial advice - offer educational strategy guidance only.\n"
    )
    msg_lower = str(message or "").lower()
    if any(x in msg_lower for x in ["replay", "bar ", "loss streak", "coaching"]):
        base += "\nYou are watching a LIVE REPLAY. Be urgent, specific, brief. Max 2 sentences."
    elif any(x in msg_lower for x in ["viability", "score is", "negative"]):
        base += "\nFocus on ONE specific fix. Name the exact slider and value. Be direct."
    elif any(x in msg_lower for x in ["backtest", "result", "win rate"]):
        base += "\nCoach on the results. If profitable: acknowledge. If losing: be honest and specific."
    elif any(x in msg_lower for x in ["junior", "under 18", "young", "student"]):
        base += "\nUser may be under 18. Clear language, more encouragement, same real math."
    if isinstance(sel, dict):
        if sel.get("sl"):
            base += "\nCurrent strategy: SL " + str(sel.get("sl")) + "%, TP " + str(sel.get("tp","")) + "%, R:R " + str(sel.get("rr","")) + ":1"
        if sel.get("symbol"):
            base += "\nAsset: " + str(sel.get("symbol"))
    return base
# === CEM_DYNAMIC_VOICE_END ===













































































































































































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
    install_block = "\n".join(f"  {line}" for line in _cem_codegen_install_lines(broker))
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
    return broker, symbol, filename, script.strip() + "\n"

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


# === CEM_COACH_INJECT_START ===
import json as _cem_coach_json
import os as _cem_coach_os
import urllib.error as _cem_coach_ue
import urllib.request as _cem_coach_uq
from fastapi import Request

def _cem_coach_hist_to_messages(hist, mx=12):
    out = []
    if not isinstance(hist, list):
        return out
    for turn in hist[-mx:]:
        if not isinstance(turn, dict):
            continue
        role = turn.get("role") or ""
        content = str(turn.get("content") or "").strip()
        if not content or role not in ("user", "assistant"):
            continue
        out.append({"role": role, "content": content})
    return out

def _cem_coach_legacy(sel):
    trade = sel.get("trade") or ""
    inst = sel.get("instrument") or ""
    style = sel.get("style") or ""
    if not trade and not inst:
        return (
            "Select your asset, trading style, and risk above to see your personalized strategy analysis."
        )
    parts = []
    if inst:
        parts.append(
            "Focus on " + inst + " — align entries with your session and indicator stack."
        )
    elif trade:
        parts.append(
            "Instrument family: " + trade + ". Pick a specific contract from the chips when ready."
        )
    if style:
        parts.append(style + " rhythm: watch volatility and keep risk per trade consistent.")
    parts.append("Run a backtest to stress-test parameters before sizing up.")
    return " ".join(parts)

def _cem_coach_chat_fallback(inp):
    asset = (inp.get("asset") or "your market").strip() or "your market"
    ret = str(inp.get("backtestReturn") or "").strip()
    wr = str(inp.get("backtestWinRate") or "").strip()
    last = ""
    h = inp.get("history") or []
    if isinstance(h, list):
        for i in range(len(h) - 1, -1, -1):
            t = h[i]
            if isinstance(t, dict) and t.get("role") == "user" and t.get("content"):
                last = str(t["content"])
                break
    if not last and inp.get("message"):
        last = str(inp["message"])
    snippet = (' You asked: "' + last + '"') if last else ""
    stats = ""
    if ret and ret != "—":
        stats += " Return line reads " + ret + "."
    if wr and wr != "—":
        stats += " Win rate strip: " + wr + "."
    tail = stats if stats else " run a backtest so we can discuss concrete stats."
    return (
        "CEMbot is in offline mode (set ANTHROPIC_API_KEY on the server for full chat)."
        + snippet
        + " On "
        + asset
        + ","
        + tail
        + " This is educational context only — not financial advice."
    )

def _cem_coach_design_fallback(inp):
    brand = inp.get("brand") or {}
    colors = brand.get("colors") or {}
    primary = str(colors.get("primary") or "#00FFCC").upper()
    secondary = str(colors.get("secondary") or "#FF6600").upper()
    last = str(inp.get("message") or "").strip()
    lower = last.lower()
    if "grant" in lower:
        return (
            "Frame the grant visually around traction, mission, and credibility. "
            "Use a clean dark background, teal data callouts, one orange CTA/highlight, and a simple proof stack for outcomes. "
            "Next action: build a one-page grant hero in the canvas, then ask CEMbot for the exact section copy."
        )
    if "tiktok" in lower:
        prompt = (
            "Vertical 9:16 ad for CEMTrading888, futuristic trading command center, glowing teal UI, "
            "orange CTA accents, trader silhouette, headline area for 'Build Your Edge', cinematic lighting, high contrast"
        )
        return (
            "Build it as a vertical hook-first ad: one hero scene, one bold promise, one CTA. "
            'Try: "' + prompt + '" Next action: click the prompt tile and run it in Grok.'
        )
    if "color" in lower or "brand" in lower:
        return (
            f"Anchor the layout in charcoal, let {primary} drive glow/focus, and use {secondary} only for urgency or CTA moments. "
            "Keep the palette about 70/20/10 so it still feels premium. Next action: add a dark base, teal headline, and one orange CTA."
        )
    if "model" in lower or "photoreal" in lower:
        prompt = (
            "Photorealistic trader at a neon trading workstation, cinematic teal and orange reflections, "
            "futures chart screens, premium fintech ad, ultra detailed"
        )
        return (
            "Use Grok for photoreal trading scenes, Flux for stylized concept art, and DALL-E 3 when text placement matters. "
            'Try: "' + prompt + '" Next action: generate that in Grok first.'
        )
    prompt = (
        "Futuristic CEMTrading888 social ad, TRON x Bloomberg aesthetic, dark matte background, teal holographic charts, "
        "orange accent CTA, premium fintech campaign, clean composition"
    )
    return (
        "Lead with one promise, one focal visual, and one action. Keep it dark, precise, and brand-clean. "
        'Try: "' + prompt + '" Next action: paste that into AI Generate and iterate from the first draft.'
    )

def _cem_coach_anthropic(key, model, system, messages):
    if not key or not messages:
        return None
    payload = _cem_coach_json.dumps(
        {"model": model, "max_tokens": 320, "system": system, "messages": messages}
    )
    req = _cem_coach_uq.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload.encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with _cem_coach_uq.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
    except _cem_coach_ue.HTTPError:
        return None
    except Exception:
        return None
    try:
        j = _cem_coach_json.loads(raw)
        return str(j["content"][0]["text"])
    except Exception:
        return None

@app.post("/api/coach")
async def api_coach(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    if body.get("mode") == "chat":
        context = body.get("context", "trading")
        custom_system = str(body.get("system") or "").strip()
        brand = body.get("brand") or {}
        asset = (body.get("asset") or "MGC").strip() or "MGC"
        chart_meta = str(body.get("chartMeta") or "")
        btr = body.get("backtestReturn")
        btw = body.get("backtestWinRate")
        btr = "not run yet" if btr in (None, "", "—") else str(btr).strip()
        btw = "not run yet" if btw in (None, "", "—") else str(btw).strip()
        exp = body.get("experienceLevel") or "beginner"
        if exp not in ("beginner", "intermediate", "pro"):
            exp = "beginner"
        exp_guide = {
            "beginner": "User is a beginner — simple language, define terms briefly, encouraging tone.",
            "intermediate": "User is intermediate — standard trading vocabulary, practical tweaks.",
            "pro": "User is advanced — concise, technical, focus on edge and execution.",
        }[exp]
        sel = body.get("sel") or {}
        sel_line = ""
        if isinstance(sel, dict):
            try:
                sj = _cem_coach_json.dumps(sel, ensure_ascii=False)
                sel_line = (sj[:900] + "…") if len(sj) > 900 else sj
            except Exception:
                sel_line = ""
        if context == "design_lab":
            try:
                brand_line = _cem_coach_json.dumps(brand, ensure_ascii=False)
            except Exception:
                brand_line = "{}"
            design_ctx = body.get("designContext") or {}
            try:
                design_ctx_line = _cem_coach_json.dumps(design_ctx, ensure_ascii=False)
            except Exception:
                design_ctx_line = "{}"
            default_system = (
                "You are CEMbot, the AI creative assistant inside the CEMTrading888 Design Lab.\n"
                "You help users design bot logos, trading dashboards, social media graphics, brand assets, social captions, and visuals that support grant applications.\n"
                f"Brand context JSON: {brand_line}\n"
                f"Design lab context JSON: {design_ctx_line}\n"
                "You know the full CEM brand: TRON Legacy meets Bloomberg Terminal with teal #00FFD5 and orange #FF6B35 on deep dark backgrounds.\n"
                "Tools available in this lab: Fabric.js 2D canvas (text, shapes, uploads, filters, color controls, layers, templates, export), Three.js 3D Studio, Asset Library (unDraw illustrations, SVG Repo icons, and My Assets from Supabase), plus AI image generation.\n"
                "Recommend concrete tool choices and step-by-step moves inside the lab whenever the user describes something they want to build.\n"
                "You can suggest color palettes, layouts, model choice, campaign concepts, captions, prompt wording, and visual hierarchy.\n"
                "Model guidance: Grok for photoreal trading scenes, Flux Pro for stylized concept art, DALL-E 3 for text-forward clean compositions, CEMbot Custom for on-brand trading concepts.\n"
                "Be conversational, encouraging, visually minded, and practical.\n"
                "Keep replies under 120 words unless the user explicitly asks for more detail.\n"
                "When you suggest an image prompt, put the exact ready-to-use prompt in quotes.\n"
                "Always end with one specific next action the user can take right now."
            )
            if custom_system:
                system = default_system + "\nAdditional design-lab instructions:\n" + custom_system
            else:
                system = default_system
        else:
            system = (
                f"You are CEMbot, an AI trading assistant built into the CEMTrading888 platform.\n"
                f"The user is currently looking at {asset} with these backtest strip values: "
                f"Return: {btr}, Win rate: {btw}.\n"
                f"Chart / UI context: {chart_meta}\n"
                f"Cockpit selection (JSON): {sel_line}\n"
                f"{exp_guide}\n"
                "Be conversational, specific, and direct. Keep responses under 3 sentences unless the user asks for detail.\n"
                "You understand: futures scalping, EMA/MACD/RSI-style strategies, risk management, systematic backtesting.\n"
                "Never give personalized financial advice — offer educational strategy guidance only."
            )
        hist = body.get("history") or []
        if not isinstance(hist, list):
            hist = []
        messages = _cem_coach_hist_to_messages(hist, 12)
        key = (_cem_coach_os.getenv("ANTHROPIC_API_KEY") or "").strip()
        model = (
            _cem_coach_os.getenv("COACH_ANTHROPIC_MODEL") or "claude-sonnet-4-6"
        ).strip()
        reply = _cem_coach_anthropic(key, model, system, messages)
        if not reply:
            reply = _cem_coach_design_fallback(body) if context == "design_lab" else _cem_coach_chat_fallback(body)
        return {"message": reply, "advice": reply, "response": reply}
    return {"advice": _cem_coach_legacy(body)}
# === CEM_COACH_INJECT_END ===


# === CEM_GENERATE_IMAGE_INJECT_START ===
import asyncio as _cem_img_asyncio
import base64 as _cem_img_base64
import json as _cem_img_json
import os as _cem_img_os
import time as _cem_img_time
import urllib.error as _cem_img_error
import urllib.parse as _cem_img_parse
import urllib.request as _cem_img_request
from fastapi import HTTPException as _cem_img_HTTPException
from fastapi import Request as _cem_img_Request
from fastapi.responses import JSONResponse as _cem_img_JSONResponse


def _cem_img_placeholder(env_key: str, label: str):
    return {"placeholder": True, "message": f"{label}: add {env_key} to .env to activate"}


def _cem_img_http_error(label: str, exc: Exception):
    detail = str(exc)
    if isinstance(exc, _cem_img_error.HTTPError):
        try:
            raw = exc.read().decode("utf-8", errors="ignore").strip()
            if raw:
                detail = raw
        except Exception:
            pass
    raise _cem_img_HTTPException(status_code=502, detail=f"{label} request failed: {detail[:600]}")


def _cem_img_request_json(label: str, url: str, headers: dict, payload=None, method: str = "GET"):
    data = None if payload is None else _cem_img_json.dumps(payload).encode("utf-8")
    request = _cem_img_request.Request(url, data=data, headers=headers, method=method)
    try:
        with _cem_img_request.urlopen(request, timeout=90) as response:
            raw = response.read().decode("utf-8")
    except Exception as exc:
        _cem_img_http_error(label, exc)
    try:
        return _cem_img_json.loads(raw)
    except Exception as exc:
        raise _cem_img_HTTPException(status_code=502, detail=f"{label} returned invalid JSON: {exc}")


def _cem_img_guess_mime_from_b64(value: str):
    if not value:
        return "image/png"
    if value.startswith("/9j/"):
        return "image/jpeg"
    if value.startswith("iVBOR"):
        return "image/png"
    if value.startswith("R0lGOD"):
        return "image/gif"
    if value.startswith("UklGR"):
        return "image/webp"
    return "image/png"


def _cem_img_data_url_from_b64(value: str, mime_type: str = ""):
    safe_mime = mime_type or _cem_img_guess_mime_from_b64(value)
    return f"data:{safe_mime};base64,{value}"


def _cem_img_download_data_url(url: str, headers=None):
    request = _cem_img_request.Request(url, headers=headers or {}, method="GET")
    try:
        with _cem_img_request.urlopen(request, timeout=90) as response:
            data = response.read()
            mime_type = response.headers.get_content_type() or "image/png"
    except Exception as exc:
        _cem_img_http_error("image download", exc)
    encoded = _cem_img_base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _cem_img_build_pollinations_payload(prompt: str, style: str = "", model_hint: str = ""):
    model_lookup = {
        "grok": "flux",
        "flux": "flux",
        "dalle": "gptimage",
        "cembot": "flux",
    }
    chosen_model = model_lookup.get(str(model_hint or "").strip().lower(), "flux")
    prompt_parts = [
        str(prompt or "").strip(),
        str(style or "").strip(),
        "professional",
        "high quality",
        "digital art",
    ]
    full_prompt = ", ".join(part for part in prompt_parts if part)
    encoded = _cem_img_parse.quote(full_prompt[:3000])
    image_url = (
        "https://image.pollinations.ai/prompt/"
        f"{encoded}?width=512&height=512&model={chosen_model}&nologo=true&enhance=true"
    )
    return {
        "url": image_url,
        "image_url": image_url,
        "prompt": full_prompt,
        "status": "ok",
        "provider": "pollinations",
        "model": chosen_model,
    }


def _cem_img_with_query(url: str, **params):
    parsed = _cem_img_parse.urlsplit(url)
    query = dict(_cem_img_parse.parse_qsl(parsed.query, keep_blank_values=True))
    query.update({key: value for key, value in params.items() if value not in (None, "")})
    return _cem_img_parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, _cem_img_parse.urlencode(query), parsed.fragment)
    )


def _cem_img_generate_grok(prompt: str):
    api_key = (_cem_img_os.getenv("XAI_API_KEY") or "").strip()
    if not api_key:
        return _cem_img_placeholder("XAI_API_KEY", "Grok Image")
    payload = {
        "model": "grok-imagine-image",
        "prompt": prompt,
        "n": 1,
        "response_format": "b64_json",
    }
    data = _cem_img_request_json(
        "xAI image generation",
        "https://api.x.ai/v1/images/generations",
        {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        payload,
        method="POST",
    )
    items = data.get("data") if isinstance(data, dict) else None
    first = items[0] if isinstance(items, list) and items else (data if isinstance(data, dict) else {})
    if isinstance(first, dict) and first.get("b64_json"):
        return {"image_url": _cem_img_data_url_from_b64(first["b64_json"]), "provider": "grok"}
    if isinstance(first, dict) and first.get("url"):
        return {"image_url": _cem_img_download_data_url(first["url"]), "provider": "grok"}
    if isinstance(data, dict) and data.get("url"):
        return {"image_url": _cem_img_download_data_url(data["url"]), "provider": "grok"}
    raise _cem_img_HTTPException(status_code=502, detail="xAI image response missing image data")


def _cem_img_generate_flux(prompt: str):
    api_key = (_cem_img_os.getenv("BFL_API_KEY") or "").strip()
    if not api_key:
        return _cem_img_placeholder("BFL_API_KEY", "Flux Pro")
    request_data = _cem_img_request_json(
        "Flux generation request",
        "https://api.bfl.ai/v1/flux-pro-1.1",
        {
            "accept": "application/json",
            "x-key": api_key,
            "Content-Type": "application/json",
        },
        {
            "prompt": prompt,
            "width": 1024,
            "height": 1024,
        },
        method="POST",
    )
    request_id = request_data.get("id") if isinstance(request_data, dict) else None
    polling_url = request_data.get("polling_url") if isinstance(request_data, dict) else None
    if not request_id or not polling_url:
        raise _cem_img_HTTPException(status_code=502, detail="Flux generation did not return a polling URL")
    final_url = _cem_img_with_query(str(polling_url), id=request_id)
    for _ in range(60):
        result = _cem_img_request_json(
            "Flux polling",
            final_url,
            {
                "accept": "application/json",
                "x-key": api_key,
            },
            method="GET",
        )
        status = str((result or {}).get("status") or "").strip().lower()
        if status == "ready":
            sample_url = (((result or {}).get("result") or {}).get("sample") or result.get("sample") or "").strip()
            if not sample_url:
                raise _cem_img_HTTPException(status_code=502, detail="Flux result was ready but missing sample URL")
            return {"image_url": _cem_img_download_data_url(sample_url), "provider": "flux"}
        if status in {"error", "failed"}:
            raise _cem_img_HTTPException(status_code=502, detail=f"Flux generation failed: {result}")
        _cem_img_time.sleep(0.5)
    raise _cem_img_HTTPException(status_code=504, detail="Flux generation timed out")


def _cem_img_generate_dalle(prompt: str):
    api_key = (_cem_img_os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return _cem_img_placeholder("OPENAI_API_KEY", "DALL-E 3")
    data = _cem_img_request_json(
        "OpenAI image generation",
        "https://api.openai.com/v1/images/generations",
        {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        {
            "model": "dall-e-3",
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
            "quality": "standard",
            "style": "vivid",
            "response_format": "b64_json",
        },
        method="POST",
    )
    items = data.get("data") if isinstance(data, dict) else None
    first = items[0] if isinstance(items, list) and items else {}
    if isinstance(first, dict) and first.get("b64_json"):
        return {
            "image_url": _cem_img_data_url_from_b64(first["b64_json"]),
            "provider": "dalle",
            "revised_prompt": data.get("revised_prompt"),
        }
    if isinstance(first, dict) and first.get("url"):
        return {
            "image_url": _cem_img_download_data_url(first["url"]),
            "provider": "dalle",
            "revised_prompt": data.get("revised_prompt"),
        }
    result_value = data.get("result") if isinstance(data, dict) else None
    if isinstance(result_value, str) and result_value.startswith("http"):
        return {"image_url": _cem_img_download_data_url(result_value), "provider": "dalle"}
    if isinstance(result_value, str) and result_value:
        return {"image_url": _cem_img_data_url_from_b64(result_value), "provider": "dalle"}
    raise _cem_img_HTTPException(status_code=502, detail="OpenAI image response missing image data")


@app.post("/api/generate")
async def generate_pollinations_image(request: _cem_img_Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    prompt = str((body or {}).get("prompt", "") or "").strip()
    style = str((body or {}).get("style", "trading dashboard") or "trading dashboard").strip()
    model_hint = str((body or {}).get("model", "") or "").strip()
    if not prompt:
        return _cem_img_JSONResponse({"error": "No prompt provided"}, status_code=400)
    return _cem_img_JSONResponse(_cem_img_build_pollinations_payload(prompt, style, model_hint))


@app.post("/api/generate-image")
async def generate_image(request: _cem_img_Request):
    body = await request.json()
    prompt = str(body.get("prompt", "") or "").strip()
    model = str(body.get("model", "grok") or "grok").strip().lower()

    if not prompt:
        return {"placeholder": True, "message": "Prompt required for image generation"}

    safe_prompt = prompt[:4000]

    if model == "grok":
        return await _cem_img_asyncio.to_thread(_cem_img_generate_grok, safe_prompt)

    if model == "flux":
        return await _cem_img_asyncio.to_thread(_cem_img_generate_flux, safe_prompt)

    if model == "dalle":
        return await _cem_img_asyncio.to_thread(_cem_img_generate_dalle, safe_prompt)

    if model == "cembot":
        return {"placeholder": True, "message": "CEMbot Custom: endpoint ready - model training in progress"}

    return {"placeholder": True, "message": f"Model not configured yet: {model}"}


# === CEM_GENERATE_IMAGE_INJECT_END ===

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
