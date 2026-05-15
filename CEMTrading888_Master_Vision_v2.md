CEMTrading888 Master Vision v2
Version 2 — March 27, 2026
Built by Chandler Morone (CTO)
Real trader-coded strategies with live chart reactivity, backtesting, leaderboard competition, and custom bot rewards.
1. Core Purpose & Empire Vision
CEMTrading888 is the world's first platform-agnostic self-serve algorithmic trading bot marketplace.
Users get free education + real tools that actually help them help themselves:

Free 5-step strategy builder + simulator (no email gate ever)
Real QuantConnect backtests
Submit to weekly leaderboard (social follow gate ONLY at submission)
Winner each Monday gets a fully coded, production-ready bot built around their strategy (theirs to own and deploy)

Differentiator: Most bots are either rigid subscriptions or expensive one-off customs with no ongoing support. We give both — one-time Snapshot Bot + optional Living Bot subscription that keeps evolving.
Brand Rules (Permanent)

Public website competes on merit only. No identity language (minority/LGBTQ+/women-led) on cemtrading888.com.
Use designations only in grant applications.
No email capture anywhere — ever. Social follows only.
All performance claims must be past results with proper risk disclosures. Never promise returns.

2. Business Model & Pricing (Locked March 2026)

Snapshot Bot Standard: $497 one-time (Futures/Crypto/Forex/Stocks) — automated delivery in ~60 seconds, user owns forever
Snapshot Bot Options: $997 one-time (Options strategies with Greeks/IV)
Living Bot Standard: $97/month — unlimited mods + backtests
Living Bot Options: $197/month
Live Customization Session: $297 (1hr video with Chandler)
Mia AI Review add-on: $19
Additional: Broker affiliates, social monetization, sponsorships, live trading profits

Contest Hook: Weekly winner gets free $497 Snapshot Bot + 30-day Living Bot trial.
3. Current Technical Reality

Website: Single vanilla HTML/CSS/JS file (index.html) on Namecheap shared hosting (public_html)
Charts: ECharts (live MES/MNQ/MGC prices, P&L, EMA status)
Builder: 5-step free simulator with sticky right chart + backtest results
Backtesting: Python 3.11 / FastAPI services (current bug: 0 trades on some runs)
Deployment: Currently messy (Namecheap → Cloudflare → DigitalOcean Droplet → GitHub)
Goal: Clean pipeline so git push updates live site reliably

Current Folder in Cursor: cem-bot-builder
4. Immediate Priorities

Fix deployment pipeline (Cloudflare + DigitalOcean + GitHub) so changes push cleanly
Fix QuantConnect 0-trades backtest bug
Build Stripe + bot delivery automation
Make the website feel seamless and trader-focused (free education that actually helps people)

5. Workflow Rules (For Grok + Cursor)

All deep work happens in Cursor with Grok-4 in the left panel
This Master Vision v2.md is the single source of truth — update it after every major session
Teach Chandler Cursor safely, one button/command at a time
No band-aids on infra — fix root problems (deployment, data loss, context)

Saved: March 27, 2026
Status: Active — Re-ingest / re-paste into Grok sessions as needed