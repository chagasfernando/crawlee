from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import yfinance as yf
from datetime import datetime, timedelta
import pandas as pd

app = FastAPI()

class ScrapeRequest(BaseModel):
    symbol: str
    tradingview_url: Optional[str] = None
    config: Optional[dict] = None

class Candle(BaseModel):
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
    candles: List[Candle]
    timestamp: str
    source: str

# Mapeamento de símbolos TradingView -> Yahoo Finance
# Yahoo Finance NÃO suporta futuros brasileiros, usamos índices como proxy
SYMBOL_MAP = {
    "WINZ25": "^BVSP",      # Mini Índice -> Ibovespa Index
    "WINZ2025": "^BVSP",
    "WIN1!": "^BVSP",
    "WDOG25": "BRL=X",      # Mini Dólar -> USD/BRL
    "PETR4": "PETR4.SA",
    "VALE3": "VALE3.SA",
    "ITUB4": "ITUB4.SA",
    "BBDC4": "BBDC4.SA",
    "IBOV": "^BVSP",
}

def get_yahoo_symbol(tv_symbol: str) -> str:
    """Converte símbolo TradingView para Yahoo Finance"""
    clean = tv_symbol.replace("BMFBOVESPA-", "").replace("BMFBOVESPA:", "").upper()
    if clean in SYMBOL_MAP:
        return SYMBOL_MAP[clean]
    # Tenta adicionar .SA para ações brasileiras
    if not clean.endswith(".SA") and not clean.startswith("^"):
        return f"{clean}.SA"
    return clean

def classify_candle(open_price: float, high: float, low: float, close: float) -> str:
    """Classifica o tipo de candle baseado em padrões"""
    body = abs(close - open_price)
    total_range = high - low
    
    if total_range == 0:
        return "doji"
    
    body_ratio = body / total_range
    
    if body_ratio < 0.1:
        return "doji"
    elif close > open_price:
        if body_ratio > 0.7:
            return "strong_buyer"
        else:
            return "weak_buyer"
    else:
        if body_ratio > 0.7:
            return "strong_seller"
        else:
            return "weak_seller"

@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_tradingview(request: ScrapeRequest):
    try:
        yahoo_symbol = get_yahoo_symbol(request.symbol)
        print(f"Fetching {yahoo_symbol} from Yahoo Finance (original: {request.symbol})")
        
        # Configurar período e intervalo
        period = "5d"
        interval = "2m"
        
        if request.config:
            tf = request.config.get("timeframe", "2m")
            # Yahoo só permite 2m para últimos 60 dias
            if tf in ["1m", "2m", "5m", "15m", "30m", "60m", "1h"]:
                interval = tf
            else:
                interval = "2m"
        
        # Buscar dados
        ticker = yf.Ticker(yahoo_symbol)
        df = ticker.history(period=period, interval=interval)
        
        if df.empty:
            # Fallback: tentar período maior com intervalo diário
            print(f"No intraday data for {yahoo_symbol}, trying daily data")
            df = ticker.history(period="1mo", interval="1d")
        
        if df.empty:
            raise HTTPException(status_code=404, detail=f"Nenhum dado encontrado para {yahoo_symbol}")
        
        candles = []
        for idx, row in df.iterrows():
            if pd.isna(row["Open"]) or pd.isna(row["Close"]):
                continue
            candle_type = classify_candle(row["Open"], row["High"], row["Low"], row["Close"])
            candles.append(Candle(
                timestamp=idx.isoformat(),
                open=round(float(row["Open"]), 2),
                high=round(float(row["High"]), 2),
                low=round(float(row["Low"]), 2),
                close=round(float(row["Close"]), 2),
                volume=int(row["Volume"]) if not pd.isna(row["Volume"]) else 0,
                candle_type=candle_type
            ))
        
        # Limitar a 100 candles mais recentes
        candles = candles[-100:]
        
        print(f"Returning {len(candles)} candles for {yahoo_symbol}")
        
        return ScrapeResponse(
            success=True,
            symbol=request.symbol,
            candles=candles,
            timestamp=datetime.now().isoformat(),
            source="yahoo_finance"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "healthy", "source": "yahoo_finance"}
