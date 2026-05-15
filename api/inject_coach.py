#!/usr/bin/env python3
"""
inject_coach.py — injects POST /api/coach into main.py on the server (FastAPI / uvicorn).
Strips and re-applies a marked block so deploys are idempotent. Logs to inject_coach_log.txt.

On the droplet (after push to main), path must be api/ on GitHub:
  curl -s https://raw.githubusercontent.com/CEMTrading888/cem-bot-builder/main/api/inject_coach.py | python3
"""
import os
import sys
import ast
import textwrap

LOG = "/var/www/cemtrading888/inject_coach_log.txt"
TARGET = "/var/www/cemtrading888/main.py"


def log(msg: str) -> None:
    print(msg)
    try:
        with open(LOG, "a") as f:
            f.write(msg + "\n")
    except Exception:
        pass


try:
    open(LOG, "w").close()
except Exception:
    pass

log("=== inject_coach.py START ===")

if not os.path.exists(TARGET):
    log(f"ERROR: {TARGET} not found — skip coach inject")
    sys.exit(0)

try:
    src = open(TARGET, encoding="utf-8").read()
except Exception as e:
    log(f"READ FAILED: {e}")
    sys.exit(1)

START_MARKER = "# === CEM_COACH_INJECT_START ==="
END_MARKER = "# === CEM_COACH_INJECT_END ==="
if START_MARKER in src and END_MARKER in src:
    before = src[: src.index(START_MARKER)]
    after = src[src.index(END_MARKER) + len(END_MARKER) :]
    src = before + after
    log("Stripped previous coach injection block")


def strip_legacy_coach_routes(text: str) -> tuple[str, int]:
    markers = ['@app.post("/api/coach")', "@app.post('/api/coach')"]
    removed = 0
    while True:
        starts = [text.find(marker) for marker in markers if text.find(marker) != -1]
        if not starts:
            return text, removed
        start = min(starts)
        next_positions = [
            pos for pos in (text.find("\n@app.", start + 1), text.find("\nif __name__", start + 1)) if pos != -1
        ]
        end = min(next_positions) if next_positions else len(text)
        text = text[:start] + text[end:]
        removed += 1


src, removed_legacy = strip_legacy_coach_routes(src)
if removed_legacy:
    log(f"Stripped {removed_legacy} legacy /api/coach route block(s)")

NEW_ROUTE = textwrap.dedent(
    r"""

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
"""
)

insert_pos = src.rfind("\nif __name__")
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
    lines = patched.split("\n")
    start = max(0, (e.lineno or 1) - 3)
    end = min(len(lines), (e.lineno or 1) + 3)
    for i, ln in enumerate(lines[start:end], start=start + 1):
        log(f"  {i}: {ln}")
    sys.exit(1)

try:
    open(TARGET, "w", encoding="utf-8").write(patched)
    log(f"INJECT OK — wrote {len(patched)} bytes")
except Exception as e:
    log(f"WRITE FAILED: {e}")
    sys.exit(1)

log("=== DONE ===")
