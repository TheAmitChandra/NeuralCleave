SKILL_METADATA = {
    "name": "stock_quote",
    "description": "Get the current stock price and daily change for a ticker symbol.",
    "version": "1.0.0",
    "trigger": "stock price",
    "dependencies": ["httpx"],
}

import httpx


async def run(args: dict) -> str:
    ticker = args.get("ticker", "AAPL").upper()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
    r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
    result = r.json().get("chart", {}).get("result", [])
    if not result:
        return f"Could not fetch data for {ticker}"
    meta = result[0]["meta"]
    price = meta.get("regularMarketPrice", 0)
    prev = meta.get("previousClose", price)
    change = price - prev
    pct = (change / prev * 100) if prev else 0
    sign = "+" if change >= 0 else ""
    return f"{ticker}: ${price:.2f} ({sign}{change:.2f}, {sign}{pct:.2f}%)"
