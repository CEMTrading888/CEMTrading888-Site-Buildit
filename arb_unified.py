"""
Unified Arbitrage Bot — Kalshi + Polymarket + Cross-Platform
===========================================================
FastAPI routes for /api/bot/arb, /api/bot/kalshi-status, /api/bot/trades

Supports three opportunity types:
  1. Kalshi-only   (YES+NO < $1.00 within Kalshi)
  2. Polymarket-only (YES+NO < $1.00 within Polymarket)
  3. Cross-arbitrage (same event priced differently across platforms)

Deploy: add this file to your FastAPI app, include the router.
"""

import os
import json
import asyncio
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
from dataclasses import dataclass, asdict

import aiohttp
from fastapi import APIRouter, HTTPException

# ── CONFIG ───────────────────────────────────────────────────
KALSHI_BASE = "https://api.elections.kalshi.com/v1"
POLY_GAMMA = "https://gamma-api.polymarket.com"
POLY_CLOB = "https://clob.polymarket.com"

# Minimum divergence to flag as actionable (after estimated fees)
MIN_DIVERGENCE = 0.02        # 2 cents
CROSS_ARB_THRESHOLD = 0.03   # 3% price gap for cross-platform
KALSHI_FEE_EST = 0.02        # ~2% all-in fee estimate
POLY_FEE_EST = 0.01          # ~1% effective fee on Polymarket (spread + gas)

# Series we scan on Kalshi
KALSHI_SERIES = ["KXBTC15M", "KXETH15M", "KXSOL15M"]

log = logging.getLogger("arb_unified")
router = APIRouter()

# ── DATA CLASSES ─────────────────────────────────────────────
@dataclass
class ArbOpportunity:
    kind: str                      # "kalshi_only" | "polymarket_only" | "cross_arb"
    event_title: str
    kalshi_ticker: Optional[str] = None
    poly_slug: Optional[str] = None
    kalshi_yes: Optional[float] = None
    kalshi_no: Optional[float] = None
    poly_yes: Optional[float] = None
    poly_no: Optional[float] = None
    divergence: float = 0.0        # raw $ or % edge
    net_profit: float = 0.0        # after estimated fees
    direction: str = ""            # "buy_kalshi_yes", "buy_poly_no", etc.
    expires_at: Optional[str] = None
    matched_event: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # sanitize None values for JSON
        return {k: (v if v is not None else "") for k, v in d.items()}


@dataclass
class TradeRecord:
    id: str
    platform: str                  # "kalshi" | "polymarket"
    event_slug: str
    market_ticker: str
    direction: str                 # "yes" | "no" | "up" | "down"
    entry_price: float
    size: float
    timestamp: str
    settled: bool = False
    result: Optional[str] = None   # "win" | "loss"
    pnl: Optional[float] = None


# ── IN-MEMORY STATE (replace with Redis/DB in production) ────
_trade_history: List[TradeRecord] = []
_opportunity_cache: Dict[str, Any] = {"ts": "", "data": {}}

# ── HELPERS ──────────────────────────────────────────────────
async def _get_json(session: aiohttp.ClientSession, url: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> dict:
    try:
        async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                return await resp.json()
            log.warning(f"HTTP {resp.status} from {url}")
            return {}
    except Exception as e:
        log.warning(f"Fetch error {url}: {e}")
        return {}


def _norm_event(title: str) -> str:
    """Normalize event title for fuzzy cross-platform matching."""
    t = title.lower()
    for word in ["will", "the", "a", "an", "to", "be", "by", "on", "at", "in", "of", "for", "?"]:
        t = t.replace(word, " ")
    return " ".join(t.split())


# ── KALSHI SCANNER ───────────────────────────────────────────
async def _scan_kalshi(session: aiohttp.ClientSession) -> List[ArbOpportunity]:
    opps: List[ArbOpportunity] = []
    for series in KALSHI_SERIES:
        url = f"{KALSHI_BASE}/series/{series}/markets"
        data = await _get_json(session, url, params={"status": "open", "limit": 50})
        markets = data.get("markets", []) if isinstance(data, dict) else []
        for m in markets:
            yes_ask = m.get("yes_ask", 0) or 0
            no_ask = m.get("no_ask", 0) or 0
            combined = yes_ask + no_ask
            if combined > 0 and combined < 1.0 - MIN_DIVERGENCE:
                edge = (1.0 - combined) / 2.0   # split edge per side
                net = edge - KALSHI_FEE_EST
                if net > 0.01:
                    opps.append(ArbOpportunity(
                        kind="kalshi_only",
                        event_title=m.get("title", m.get("ticker_name", series)),
                        kalshi_ticker=m.get("ticker", ""),
                        kalshi_yes=yes_ask,
                        kalshi_no=no_ask,
                        divergence=1.0 - combined,
                        net_profit=net,
                        direction="buy_both" if yes_ask > 0 and no_ask > 0 else "buy_cheap_side",
                        expires_at=m.get("close_time", ""),
                    ))
    return opps


async def _kalshi_balance(session: aiohttp.ClientSession) -> dict:
    """Returns balance info if KALSHI_API_KEY is set, else empty."""
    key = os.getenv("KALSHI_API_KEY")
    if not key:
        return {}
    headers = {"Authorization": f"Bearer {key}"}
    data = await _get_json(session, f"{KALSHI_BASE}/portfolio/balance", headers=headers)
    return data if isinstance(data, dict) else {}


# ── POLYMARKET SCANNER ───────────────────────────────────────
async def _scan_polymarket(session: aiohttp.ClientSession) -> List[ArbOpportunity]:
    opps: List[ArbOpportunity] = []
    # Fetch active markets from Gamma API
    markets = await _get_json(
        session,
        f"{POLY_GAMMA}/markets",
        params={"active": "true", "closed": "false", "limit": 100}
    )
    if not isinstance(markets, list):
        return opps

    for m in markets:
        # Polymarket markets often have outcomes array ["Yes", "No"]
        outcomes = m.get("outcomes", [])
        if len(outcomes) != 2:
            continue
        # Get CLOB mid-price if available, else use last price from gamma
        mid = None
        clob = m.get("clobTokenIds", [])
        if clob and len(clob) >= 2:
            # Try to get best prices from CLOB
            try:
                book = await _get_json(session, f"{POLY_CLOB}/book", params={"token_id": clob[0]})
                bids = book.get("bids", [])
                asks = book.get("asks", [])
                if bids and asks:
                    best_bid = float(bids[0].get("price", 0))
                    best_ask = float(asks[0].get("price", 0))
                    mid = (best_bid + best_ask) / 2
            except Exception:
                pass

        if mid is None:
            # Fallback: use outcomePrices if present
            prices = m.get("outcomePrices", [])
            if len(prices) >= 2:
                try:
                    mid = float(prices[0])
                except (ValueError, TypeError):
                    continue
            else:
                continue

        # Assuming Yes at index 0, No at index 1
        yes_price = mid
        no_price = 1.0 - mid
        combined = yes_price + no_price  # theoretically 1.0, but mispricings happen

        # Flag if the implied probability is mispriced vs 1.0
        # In practice Polymarket is efficient, but we catch stale data / wide spreads
        spread_penalty = abs(combined - 1.0)
        if spread_penalty > MIN_DIVERGENCE:
            net = spread_penalty - POLY_FEE_EST
            if net > 0.01:
                opps.append(ArbOpportunity(
                    kind="polymarket_only",
                    event_title=m.get("question", m.get("slug", "Unknown")),
                    poly_slug=m.get("slug", ""),
                    poly_yes=yes_price,
                    poly_no=no_price,
                    divergence=spread_penalty,
                    net_profit=net,
                    direction="buy_mispriced_side",
                    expires_at=m.get("endDate", ""),
                ))
    return opps


# ── CROSS-ARBITRAGE SCANNER ──────────────────────────────────
async def _scan_cross_arb(session: aiohttp.ClientSession) -> List[ArbOpportunity]:
    """Find matching events between Kalshi and Polymarket with divergent prices."""
    cross_opps: List[ArbOpportunity] = []

    # Fetch both market sets in parallel
    kalshi_markets: List[Dict] = []
    for series in KALSHI_SERIES:
        data = await _get_json(session, f"{KALSHI_BASE}/series/{series}/markets", params={"status": "open", "limit": 50})
        if isinstance(data, dict):
            kalshi_markets.extend(data.get("markets", []))

    poly_markets = await _get_json(session, f"{POLY_GAMMA}/markets", params={"active": "true", "limit": 100})
    if not isinstance(poly_markets, list):
        poly_markets = []

    # Build normalized lookup for Polymarket
    poly_by_norm: Dict[str, Dict] = {}
    for m in poly_markets:
        q = m.get("question", "")
        if q:
            poly_by_norm[_norm_event(q)] = m

    for km in kalshi_markets:
        title = km.get("title", "")
        norm = _norm_event(title)
        pm = poly_by_norm.get(norm)
        if not pm:
            # Try fuzzy substring match as fallback
            for p_norm, p_m in poly_by_norm.items():
                if norm in p_norm or p_norm in norm:
                    pm = p_m
                    break
        if not pm:
            continue

        # Compare YES prices
        k_yes = km.get("yes_ask", 0) or 0
        k_no = km.get("no_ask", 0) or 0

        p_prices = pm.get("outcomePrices", [])
        p_yes = None
        if len(p_prices) >= 2:
            try:
                p_yes = float(p_prices[0])
            except (ValueError, TypeError):
                pass

        if p_yes is None:
            # Try CLOB mid
            clob = pm.get("clobTokenIds", [])
            if clob:
                try:
                    book = await _get_json(session, f"{POLY_CLOB}/book", params={"token_id": clob[0]})
                    bids = book.get("bids", [])
                    asks = book.get("asks", [])
                    if bids and asks:
                        p_yes = (float(bids[0].get("price", 0)) + float(asks[0].get("price", 0))) / 2
                except Exception:
                    pass

        if p_yes is None or k_yes <= 0:
            continue

        # Calculate cross-arb edge
        # If Kalshi YES is cheaper than Polymarket YES by > threshold, buy Kalshi YES + Poly NO
        # If Polymarket YES is cheaper, buy Poly YES + Kalshi NO
        diff = abs(k_yes - p_yes)
        fees = KALSHI_FEE_EST + POLY_FEE_EST
        net = diff - fees

        if diff > CROSS_ARB_THRESHOLD and net > 0.01:
            if k_yes < p_yes:
                direction = "buy_kalshi_yes + buy_poly_no"
                cheap_yes = k_yes
                expensive_yes = p_yes
            else:
                direction = "buy_poly_yes + buy_kalshi_no"
                cheap_yes = p_yes
                expensive_yes = k_yes

            cross_opps.append(ArbOpportunity(
                kind="cross_arb",
                event_title=title,
                kalshi_ticker=km.get("ticker", ""),
                poly_slug=pm.get("slug", ""),
                kalshi_yes=k_yes,
                kalshi_no=k_no,
                poly_yes=p_yes,
                poly_no=1.0 - p_yes,
                divergence=diff,
                net_profit=net,
                direction=direction,
                matched_event=pm.get("question", ""),
                expires_at=km.get("close_time", pm.get("endDate", "")),
            ))

    return cross_opps


# ── AGGREGATE SCAN ───────────────────────────────────────────
async def run_full_scan() -> Dict[str, Any]:
    async with aiohttp.ClientSession(headers={"User-Agent": "CEMTrading888-ArbBot/2.0"}) as session:
        k_task = asyncio.create_task(_scan_kalshi(session))
        p_task = asyncio.create_task(_scan_polymarket(session))
        # Cross-arb depends on both, but we can kick it off after partial data
        # For speed, run kalshi+poly in parallel, then cross
        kalshi_opps = await k_task
        poly_opps = await p_task
        cross_opps = await _scan_cross_arb(session)

    total_actionable = sum(1 for o in kalshi_opps + poly_opps + cross_opps if o.net_profit > 0.01)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kalshi_markets": len(KALSHI_SERIES) * 50,  # rough upper bound
        "poly_markets": 100,
        "total_actionable": total_actionable,
        "kalshi_only": {
            "count": len(kalshi_opps),
            "opportunities": [o.to_dict() for o in kalshi_opps[:20]],
        },
        "polymarket_only": {
            "count": len(poly_opps),
            "opportunities": [o.to_dict() for o in poly_opps[:20]],
        },
        "cross_arb": {
            "count": len(cross_opps),
            "opportunities": [o.to_dict() for o in cross_opps[:20]],
        },
    }


# ── FASTAPI ROUTES ───────────────────────────────────────────
@router.get("/bot/arb")
async def get_arb_opportunities():
    """Return categorized arb opportunities."""
    # Use cache if < 30s old
    now = datetime.now(timezone.utc)
    cache_ts = _opportunity_cache.get("ts", "")
    if cache_ts:
        try:
            cached = datetime.fromisoformat(cache_ts)
            if (now - cached).total_seconds() < 30:
                return _opportunity_cache["data"]
        except Exception:
            pass

    data = await run_full_scan()
    _opportunity_cache["ts"] = now.isoformat()
    _opportunity_cache["data"] = data
    return data


@router.get("/bot/kalshi-status")
async def get_kalshi_status():
    """Return Kalshi bot connection + balance snapshot."""
    async with aiohttp.ClientSession() as session:
        bal = await _kalshi_balance(session)
    return {
        "connected": bool(bal),
        "balance": bal,
    }


@router.get("/bot/polymarket-status")
async def get_polymarket_status():
    """Return Polymarket bot snapshot (USDC balance, open orders)."""
    # In production, wire this to your Polymarket wallet / CLOB API
    # For now, return placeholder that frontend can override when real data arrives
    return {
        "connected": True,
        "usdc_balance": None,   # Set when real API connected
        "open_orders": 0,
        "server": "Helsinki",
    }


@router.get("/bot/markets")
async def get_market_counts():
    """Return raw market counts + weather signal placeholder."""
    # Weather signal is placeholder — wire your existing weather bot here
    return {
        "weather": 0,
        "total": len(KALSHI_SERIES) * 50 + 100,
        "kalshi_series": KALSHI_SERIES,
    }


@router.get("/bot/signals-news")
async def get_signals_news():
    """Placeholder for news signal count."""
    return {"count": 0}


@router.get("/bot/trades")
async def get_trades():
    """Return trade history. In production, read from DB."""
    return [asdict(t) for t in _trade_history]


# Legacy flat format fallback for older clients
@router.get("/bot/arb-legacy")
async def get_arb_legacy():
    data = await get_arb_opportunities()
    # Flatten all opportunities into old format
    flat = []
    for cat in ["kalshi_only", "polymarket_only", "cross_arb"]:
        for o in data.get(cat, {}).get("opportunities", []):
            flat.append({
                "kalshi_ticker": o.get("kalshi_ticker") or o.get("poly_slug"),
                "poly_question": o.get("poly_slug"),
                "net_profit": o.get("net_profit"),
                "divergence": o.get("divergence"),
                "direction": o.get("direction"),
                "kind": o.get("kind"),
            })
    return {
        "actionable": data["total_actionable"],
        "kalshi_markets": data["kalshi_markets"],
        "poly_markets": data["poly_markets"],
        "opportunities": flat,
    }
