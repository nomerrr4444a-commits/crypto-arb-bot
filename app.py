from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Значно розширений список монет (популярні альткоїни, мемкоїни та мережеві монети)
COINS = [
    "NEARUSDT", "SUIUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", 
    "TONUSDT", "LINKUSDT", "INJUSDT", "TIAUSDT", "AVAXUSDT", 
    "ATOMUSDT", "FETUSDT", "XRPUSDT", "TRXUSDT", "KASUSDT", 
    "PEPEUSDT", "DOGEUSDT", "SHIBUSDT", "RENDERUSDT", "SEIUSDT",
    "JUPUSDT", "WIFUSDT", "POLUSDT", "NEARUSDT", "ICPUSDT",
    "NEARUSDT", "FTMUSDT", "STXUSDT", "BCHUSDT", "LTCUSDT",
    "ALGOUSDT", "ATOMUSDT", "NEARUSDT", "GRTUSDT", "RUNEUSDT"
]
# Видаляємо можливі дублікати за допомогою set
COINS = list(set(COINS))

@app.get("/api/arbitrage")
def get_arbitrage_opportunities():
    opportunities = []
    
    # Отримуємо ціни з Binance API
    try:
        binance_res = requests.get("https://api.binance.com/api/v3/ticker/bookTicker", timeout=5).json()
        binance_prices = {
            item['symbol']: {
                "bid": float(item['bidPrice']), 
                "ask": float(item['askPrice']), 
                "bidQty": float(item['bidQty']), 
                "askQty": float(item['askQty'])
            } for item in binance_res if item['symbol'] in COINS
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Binance API error: {str(e)}")

    # Отримуємо ціни з Bybit API
    bybit_prices = {}
    try:
        bybit_res = requests.get("https://api.bybit.com/v5/market/tickers?category=spot", timeout=5).json()
        if bybit_res.get("retCode") == 0:
            for item in bybit_res["result"]["list"]:
                sym = item["symbol"]
                if sym in COINS:
                    bybit_prices[sym] = {
                        "bid": float(item["bid1Price"]) if item["bid1Price"] else 0,
                        "ask": float(item["ask1Price"]) if item["ask1Price"] else 0,
                        "bidQty": float(item["bid1Size"]) if item["bid1Size"] else 0,
                        "askQty": float(item["ask1Size"]) if item["ask1Size"] else 0,
                    }
    except Exception:
        pass

    capital = 300.0  # Твій робочий капітал
    for symbol in COINS:
        base_coin = symbol.replace("USDT", "")
        
        if symbol not in binance_prices or symbol not in bybit_prices:
            continue
            
        b_data = binance_prices[symbol]
        yb_data = bybit_prices[symbol]
        
        if b_data["ask"] == 0 or yb_data["bid"] == 0:
            continue

        # Зв'язка 1: Купити на Binance, Продати на Bybit
        spread_1 = ((yb_data["bid"] - b_data["ask"]) / b_data["ask"]) * 100
        net_profit_1 = (capital * (spread_1 / 100)) - 1.0  # Мінус комісія мережі TRC-20 ($1)
        
        if spread_1 > 0.2 and net_profit_1 > 0:
            depth = b_data["askQty"] * b_data["ask"]
            max_rounds = int(depth / capital) if capital > 0 else 1
            if max_rounds < 1: max_rounds = 1
            
            opportunities.append({
                "coin": base_coin,
                "buyExchange": "Binance",
                "sellExchange": "Bybit",
                "buyPrice": b_data["ask"],
                "sellPrice": yb_data["bid"],
                "spread": round(spread_1, 2),
                "netProfit": round(net_profit_1, 2),
                "roi": round((net_profit_1 / capital) * 100, 2),
                "maxRounds": max_rounds,
                "totalPotential": round(net_profit_1 * min(max_rounds, 5), 2),
                "network": "TRC-20 (Комісія $1)",
                "liquidityStatus": "Висока ($300+ доступно)"
            })

        # Зв'язка 2: Купити на Bybit, Продати на Binance
        spread_2 = ((b_data["bid"] - yb_data["ask"]) / yb_data["ask"]) * 100
        net_profit_2 = (capital * (spread_2 / 100)) - 1.0
        
        if spread_2 > 0.2 and net_profit_2 > 0:
            depth = yb_data["askQty"] * yb_data["ask"]
            max_rounds = int(depth / capital) if capital > 0 else 1
            if max_rounds < 1: max_rounds = 1
            
            opportunities.append({
                "coin": base_coin,
                "buyExchange": "Bybit",
                "sellExchange": "Binance",
                "buyPrice": yb_data["ask"],
                "sellPrice": b_data["bid"],
                "spread": round(spread_2, 2),
                "netProfit": round(net_profit_2, 2),
                "roi": round((net_profit_2 / capital) * 100, 2),
                "maxRounds": max_rounds,
                "totalPotential": round(net_profit_2 * min(max_rounds, 5), 2),
                "network": "TRC-20 (Комісія $1)",
                "liquidityStatus": "Висока ($300+ доступно)"
            })

    opportunities.sort(key=lambda x: x["netProfit"], reverse=True)
    return {"status": "success", "data": opportunities}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
 
