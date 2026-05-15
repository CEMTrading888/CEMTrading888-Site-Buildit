import yfinance as yf
import pandas as pd

def run(params):
    ticker_map = {
        "Micro Futures": "ES=F", "Crypto": "BTC-USD",
        "Forex": "EURUSD=X", "Stocks": "SPY", "Options": "SPY"
    }
    ticker = ticker_map.get(params.get("trade","Micro Futures"),"ES=F")
    df = yf.download(ticker, period="60d", interval="5m", timeout=8, progress=False)
    if df.empty: return {"error":"No data"}
    df.columns = [c[0] if isinstance(c,tuple) else c for c in df.columns]
    close = df["Close"].dropna()
    ema9 = close.ewm(span=9).mean()
    ema21 = close.ewm(span=21).mean()
    eq=init=100000.0; pos=None; trades=[]; equity=[init]; maxDD=0
    for i in range(21, len(close)):
        price = float(close.iloc[i])
        cross_up = float(ema9.iloc[i]) > float(ema21.iloc[i]) and float(ema9.iloc[i-1]) <= float(ema21.iloc[i-1])
        cross_dn = float(ema9.iloc[i]) < float(ema21.iloc[i]) and float(ema9.iloc[i-1]) >= float(ema21.iloc[i-1])
        if cross_up and pos is None:
            pos = price
        elif cross_dn and pos is not None:
            pnl = (price - pos) / pos * eq
            eq += pnl
            trades.append({"pnl":round(pnl,2),"win":pnl>0})
            pos = None
        dd = (max(equity[-1],eq) - eq) / max(equity[-1],eq) * 100 if equity else 0
        if dd > maxDD: maxDD = dd
        equity.append(round(eq,2))
    tt=len(trades); wt=sum(1 for t in trades if t["win"])
    return {
        "status":"Completed","source":f"Yahoo Finance ({ticker})","bars_used":len(close),
        "asset":params.get("trade","MES"),
        "statistics":{
            "TotalTrades":tt,"WinningTrades":wt,
            "WinRate":round(wt/tt*100,1) if tt else 0,
            "TotalReturn":round((eq-init)/init*100,2),
            "NetProfit":round(eq-init,2),
            "MaxDrawdown":round(maxDD,2)
        },
        "equity_curve":equity[-100:]
    }
