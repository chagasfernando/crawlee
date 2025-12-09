from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import asyncio
from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext

app = FastAPI()

class ScrapeRequest(BaseModel):
    url: str
    timeframe: str = "2m"

class Candle(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    type: str

class ScrapeResponse(BaseModel):
    success: bool
    candles: List[Candle]
    error: Optional[str] = None

def classify_candle(o, h, l, c):
    body = abs(c - o)
    total = h - l
    if total == 0: return "doji"
    ratio = body / total
    if c > o:
        return "bull-strong" if ratio > 0.6 else "bull-weak"
    elif c < o:
        return "bear-strong" if ratio > 0.6 else "bear-weak"
    return "doji"

@app.post("/scrape", response_model=ScrapeResponse)
async def scrape(request: ScrapeRequest):
    candles = []
    
    async def handler(context: PlaywrightCrawlingContext):
        page = context.page
        await page.wait_for_timeout(5000)
        # Extract OHLC data from TradingView chart
        data = await page.evaluate('''() => {
            const chart = document.querySelector('[class*="chart"]');
            return chart ? chart.innerText : null;
        }''')
        # Parse and populate candles here
    
    try:
        crawler = PlaywrightCrawler(
            headless=True,
            max_requests_per_crawl=1
        )
        crawler.router.default_handler(handler)
        await crawler.run([request.url])
        return ScrapeResponse(success=True, candles=candles)
    except Exception as e:
        return ScrapeResponse(success=False, candles=[], error=str(e))

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
