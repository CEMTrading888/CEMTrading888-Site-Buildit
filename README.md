# CEMTrading888 — AI-Powered Trading Bot Builder

## 🧠 FIRST DOCUMENTED CLAUDE + GROK LIVE MCP INTEGRATION — March 27, 2026

> **CEMTrading888 is the first publicly documented project to deploy a live MCP (Model Context Protocol) server enabling real-time shared memory between Claude (Anthropic) and Grok (xAI) — two competing AI systems working as a coordinated team on the same codebase.**
>
> Claude handles architecture, browser automation, debugging, and Railway deployment in real time.
> Grok handles local code execution inside Cursor on Mac M4.
> Both read and write to the same Supabase brain simultaneously via the live MCP server.
>
> Neither Anthropic nor xAI has publicly demonstrated this cross-AI collaboration pattern.
> **CEMTrading888 built it first.**
>
> 🟢 Live proof: https://cem-bot-builder-production.up.railway.app/health
> Returns: `{"status":"ok","server":"CEMTrading888 Shared AI Brain"}`
> Confirmed live: March 27, 2026

---

## What Is This?

CEMTrading888 is a self-serve algorithmic trading bot builder powered by AI (Claude) and real QuantConnect backtesting infrastructure. The platform interviews you about your trading style, risk tolerance, and preferred instruments — then automatically generates, validates, and delivers a working algorithmic trading bot customized to your answers.

No Python. No APIs. No coding experience required.

## Shared AI Brain — Architecture

```
Claude (Anthropic)          Grok (xAI / Cursor)
  |                              |
  |── reads/writes ──────────────|
           ↓                ↓
     CEMTrading888 MCP Server (Railway)
           ↓
       Supabase Brain
    (cem_context, cem_tasks,
     cem_messages, cem_files)
```

Both AIs share the same memory. Decisions, code, context, and session history persist across both systems in real time. Claude navigates the browser and deploys. Grok writes local code. One brain. Two agents. Zero human bottleneck.

## How It Works

1. Answer 4 questions → Trading style, asset class, risk level, account size
2. Build your strategy → Pick indicators in a visual simulator
3. Run a real backtest → Live QuantConnect results, not simulations
4. Validate automatically → Syntax check + backtest confirmation (3-step)
5. Own your bot → Download your .py file, deploy anywhere

Every bot delivered is pre-tested against real market data before purchase.

## Pricing

| Tier | Price | Details |
|------|-------|---------|
| Snapshot Bot Standard | $497 one-time | Futures/Crypto/Forex/Stocks — delivered in 60 seconds |
| Snapshot Bot Options | $997 one-time | Full Greeks, IV rank — delivered in 60 seconds |
| Living Bot Standard | $97/month | Unlimited mods and backtests — cancel anytime |
| Living Bot Options | $197/month | Options bots — reflects Greeks complexity |
| Mia AI Review | $19 add-on | Bot optimization review before purchase |
| Live Customization | $297/session | 1hr live session with Chandler (CTO) |

## Backtest Track Record

We publish wins AND losses. Transparency is the product.

| Backtest Name | Result | Notes |
|--------------|--------|-------|
| Well Dressed Yellow Chicken | -99.9% | v1 sizing error — fixed |
| Crying Magenta Fish | -14.8% | ORB, 17hr avg holds |
| Crying Fluorescent Orange Bee | -29.7% | 41% win rate signal — real edge found |
| Formal Yellow Guanaco | +17.51% | Adaptive regime, $27k — previous best |
| MGC EMA+MACD Scalper | +17.99% | Found accidentally in 5 minutes — top 10% QC worldwide |

## Tech Stack

- **Frontend**: HTML/CSS/JS (ECharts) — Namecheap + Cloudflare Pages
- **Backtests**: Python 3.11 / FastAPI services
- **Bot Gen**: Claude API — generates production Python from strategy params
- **MCP Server**: FastAPI on Railway — shared brain between Claude and Grok
- **Memory**: Supabase (cem_context, cem_tasks, cem_messages, cem_files)
- **Broker**: Interactive Brokers TWS
- **Language**: Python 3.11
- **Libraries**: ib_insync, pandas, numpy, nest_asyncio, FastAPI, uvicorn

## About CEMTrading888 LLC

**Chandler Morone — CTO.** Bot architecture, QuantConnect strategy development, Claude API engineering, live trading.

**Kayla — COO.** Business development, grants, social media, brand, partnerships.

Links: [cemtrading888.com](https://cemtrading888.com) · cem@cemtrading888.com · @CEMTrading888

---

*© 2026 CEMTrading888 LLC. All Rights Reserved. Algorithmic trading involves risk. Past backtest performance does not guarantee future results.*
