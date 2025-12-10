from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import asyncio
from datetime import datetime, timedelta

# Use tvdatafeed for reliable TradingView data extraction
from tvDatafeed import TvDatafeed, Interval

app = FastAPI(title="TradingView Scraper Service")

# CORS for Supabase Edge Functions
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScrapeRequest(BaseModel):
    url: str
    symbol: str
    timeframe: str = "2m"
    limit: int = 100
    historical_days: int = 7

class CandleData(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    candle_type: str

class ScrapeResponse(BaseModel):
    success: bool
    symbol: str
    candles: List[CandleData]
    message: Optional[str] = None

# Map timeframe strings to tvdatafeed intervals
INTERVAL_MAP = {
    "1m": Interval.in_1_minute,
    "2m": Interval.in_1_minute,  # tvdatafeed doesn't have 2m, use 1m
    "5m": Interval.in_5_minute,
    "15m": Interval.in_15_minute,
    "30m": Interval.in_30_minute,
    "1h": Interval.in_1_hour,
    "4h": Interval.in_4_hour,
    "1d": Interval.in_daily,
}

def classify_candle(open_price: float, high: float, low: float, close: float) -> str:
    """Classify candle type based on body size and direction"""
    body_size = abs(close - open_price)
    total_range = high - low
    
    if total_range == 0:
        return "exhaustion"
    
    body_ratio = body_size / total_range
    is_bullish = close > open_price
    
    if body_ratio > 0.7:
        return "bull-strong" if is_bullish else "bear-strong"
    elif body_ratio > 0.4:
        return "bull-weak" if is_bullish else "bear-weak"
    elif body_ratio < 0.2:
        return "exhaustion"
    else:
        return "reversal"

@app.get("/")
async def root():
    return {"status": "ok", "service": "TradingView Scraper", "version": "2.0"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/scrape", response_model=ScrapeResponse)
async def scrape(request: ScrapeRequest):
    try:
        # Initialize tvdatafeed (no login for basic data)
        tv = TvDatafeed()
        
        # Parse symbol for B3 (Brazilian exchange)
        # WINZ25 -> WIN (continuous contract symbol)
        symbol = request.symbol.upper()
        
        # Map B3 mini-index symbols
        exchange = "BMFBOVESPA"
        
        # For futures contracts like WINZ25, extract base symbol
        if symbol.startswith("WIN"):
            tv_symbol = "WIN1!"  # Continuous mini-index contract
        elif symbol.startswith("WDO"):
            tv_symbol = "WDO1!"  # Continuous mini-dollar contract
        else:
            tv_symbol = symbol
        
        # Get interval
        interval = INTERVAL_MAP.get(request.timeframe, Interval.in_1_minute)
        
        # Calculate number of bars needed
        # For 2-minute timeframe with 7 days: ~7 * 4.5 hours * 30 candles/hour = ~945 candles
        bars_per_day = 270  # ~9 hours trading session / 2 min
        n_bars = min(request.historical_days * bars_per_day, 5000)
        
        print(f"Fetching {n_bars} bars for {tv_symbol} on {exchange}")
        
        # Fetch historical data
        df = tv.get_hist(
            symbol=tv_symbol,
            exchange=exchange,
            interval=interval,
            n_bars=n_bars,
            fut_contract=1  # Use front month contract
        )
        
        if df is None or df.empty:
            return ScrapeResponse(
                success=False,
                symbol=request.symbol,
                candles=[],
                message="No data returned from TradingView"
            )
        
        # Convert DataFrame to candle list
        candles = []
        for idx, row in df.iterrows():
            timestamp = idx if isinstance(idx, datetime) else datetime.fromisoformat(str(idx))
            
            candle = CandleData(
                timestamp=timestamp.isoformat(),
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=int(row['volume']) if 'volume' in row else 0,
                candle_type=classify_candle(
                    float(row['open']),
                    float(row['high']),
                    float(row['low']),
                    float(row['close'])
                )
            )
            candles.append(candle)
        
        print(f"Successfully extracted {len(candles)} candles")
        
        return ScrapeResponse(
            success=True,
            symbol=request.symbol,
            candles=candles,
            message=f"Extracted {len(candles)} candles from TradingView"
        )
        
    except Exception as e:
        print(f"Error scraping: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return ScrapeResponse(
            success=False,
            symbol=request.symbol,
            candles=[],
            message=f"Error: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
