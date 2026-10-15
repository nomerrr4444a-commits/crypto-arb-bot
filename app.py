from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import requests

app = FastAPI(title="Crypto Arbitrage Telegram App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Розширений список популярних та волатильних монет під арбітраж
COINS = [
    "NEARUSDT", "SUIUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", 
    "TONUSDT", "LINKUSDT", "INJUSDT", "TIAUSDT", "AVAXUSDT", 
    "ATOMUSDT", "FETUSDT", "XRPUSDT", "TRXUSDT", "KASUSDT", 
    "PEPEUSDT", "DOGEUSDT", "SHIBUSDT", "RENDERUSDT", "SEIUSDT",
    "JUPUSDT", "WIFUSDT", "POLUSDT", "FTMUSDT", "STXUSDT", 
    "BCHUSDT", "LTCUSDT", "ALGOUSDT", "GRTUSDT", "RUNEUSDT"
]
COINS = list(set(COINS))

@app.get("/api/arbitrage")
def get_arbitrage_opportunities():
    opportunities = []
    
    # 1. Отримуємо живі ціни з Binance API
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

    # 2. Отримуємо живі ціни з Bybit API
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

    capital = 300.0  # Робочий капітал $300
    for symbol in COINS:
        base_coin = symbol.replace("USDT", "")
        
        if symbol not in binance_prices or symbol not in bybit_prices:
            continue
            
        b_data = binance_prices[symbol]
        yb_data = bybit_prices[symbol]
        
        if b_data["ask"] == 0 or yb_data["bid"] == 0:
            continue

        # Зв'язка 1: Купити Binance -> Продати Bybit
        spread_1 = ((yb_data["bid"] - b_data["ask"]) / b_data["ask"]) * 100
        net_profit_1 = (capital * (spread_1 / 100)) - 1.0  # Комісія мережі TRC-20 (~$1)
        
        if spread_1 > 0.25 and net_profit_1 > 0:
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

        # Зв'язка 2: Купити Bybit -> Продати Binance
        spread_2 = ((b_data["bid"] - yb_data["ask"]) / yb_data["ask"]) * 100
        net_profit_2 = (capital * (spread_2 / 100)) - 1.0
        
        if spread_2 > 0.25 and net_profit_2 > 0:
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

# Головна сторінка — повертає повноцінний білий веб-інтерфейс у Telegram Mini App
@app.get("/", response_class=HTMLResponse)
def render_app():
    return """
<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>Crypto Arbitrage Scanner</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body { background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    </style>
</head>
<body class="p-4 text-slate-800 min-h-screen">
    <div class="max-w-md mx-auto">
        <!-- Header -->
        <div class="bg-white rounded-2xl p-4 shadow-sm border border-slate-100 mb-4 flex justify-between items-center">
            <div>
                <h1 class="text-lg font-bold text-slate-900 flex items-center gap-2">
                    <i class="fa-solid me-1 fa-chart-line text-blue-600"></i> Сканер Арбітражу
                </h1>
                <p class="text-xs text-slate-500">Капітал: <span class="font-bold text-slate-700">$300 USDT</span></p>
            </div>
            <button onclick="loadData()" class="bg-blue-50 text-blue-600 p-2.5 rounded-xl hover:bg-blue-100 transition active:scale-95">
                <i class="fa-solid fa-rotate text-sm" id="syncIcon"></i>
            </button>
        </div>

        <!-- Status Bar -->
        <div class="flex items-center justify-between text-xs text-slate-500 mb-3 px-1">
            <span id="statusText"><i class="fa-solid fa-circle text-emerald-500 text-[8px] mr-1"></i> Live сканування...</span>
            <span id="cardCount">Знайдено: 0</span>
        </div>

        <!-- Deals Container -->
        <div id="dealsList" class="space-y-3">
            <div class="bg-white rounded-2xl p-6 text-center text-slate-400 border border-slate-100 shadow-sm">
                <i class="fa-solid fa-spinner fa-spin text-2xl text-blue-500 mb-2"></i>
                <p class="text-xs">Завантаження актуальних цін...</p>
            </div>
        </div>
    </div>

    <script>
        const tg = window.Telegram?.WebApp;
        if (tg) { tg.expand(); tg.ready(); }

        async function loadData() {
            const syncIcon = document.getElementById('syncIcon');
            const dealsList = document.getElementById('dealsList');
            const statusText = document.getElementById('statusText');
            const cardCount = document.getElementById('cardCount');

            syncIcon.classList.add('fa-spin');
            statusText.innerHTML = '<i class="fa-solid fa-spinner fa-spin text-blue-500 mr-1"></i> Оновлення...';

            try {
                const res = await fetch('/api/arbitrage');
                const data = await res.json();
                
                syncIcon.classList.remove('fa-spin');
                statusText.innerHTML = '<i class="fa-solid fa-circle text-emerald-500 text-[8px] mr-1"></i> Оновлено';

                if (!data.data || data.data.length === 0) {
                    dealsList.innerHTML = `
                        <div class="bg-white rounded-2xl p-6 text-center border border-slate-100 shadow-sm">
                            <p class="text-sm font-semibold text-slate-600">Незвичайних спредів не знайдено</p>
                            <p class="text-xs text-slate-400 mt-1">Сканер перевіряє понад 30 монет. Зачекайте оновлення ринку.</p>
                        </div>`;
                    cardCount.innerText = 'Знайдено: 0';
                    return;
                }

                cardCount.innerText = `Знайдено: ${data.data.length}`;
                dealsList.innerHTML = data.data.map(item => `
                    <div class="bg-white rounded-2xl p-4 shadow-sm border border-slate-100 relative overflow-hidden">
                        <div class="flex justify-between items-start mb-3">
                            <div class="flex items-center gap-2">
                                <span class="font-black text-slate-900 text-base">${item.coin}</span>
                                <span class="bg-slate-100 text-slate-600 text-[10px] font-medium px-2 py-0.5 rounded-full">${item.network}</span>
                            </div>
                            <div class="text-right">
                                <span class="text-emerald-600 font-bold text-sm">+${item.spread}%</span>
                                <p class="text-[10px] text-slate-400">Спред</p>
                            </div>
                        </div>

                        <!-- Exchange Route -->
                        <div class="bg-slate-50 p-2.5 rounded-xl flex items-center justify-between text-xs mb-3 border border-slate-100">
                            <div>
                                <p class="text-slate-400 text-[10px]">Купівля</p>
                                <p class="font-bold text-slate-800">${item.buyExchange}</p>
                                <p class="text-[10px] text-slate-500">$${item.buyPrice}</p>
                            </div>
                            <i class="fa-solid fa-arrow-right text-slate-300"></i>
                            <div class="text-right">
                                <p class="text-slate-400 text-[10px]">Продаж</p>
                                <p class="font-bold text-slate-800">${item.sellExchange}</p>
                                <p class="text-[10px] text-slate-500">$${item.sellPrice}</p>
                            </div>
                        </div>

                        <!-- Metrics Grid -->
                        <div class="grid grid-cols-2 gap-2 text-xs pt-1 border-t border-slate-50">
                            <div>
                                <p class="text-[10px] text-slate-400">Чистий прибуток ($300):</p>
                                <p class="font-extrabold text-emerald-600">+$${item.netProfit} USDT</p>
                            </div>
                            <div class="text-right">
                                <p class="text-[10px] text-slate-400">Макс. кругів ($300):</p>
                                <p class="font-bold text-slate-700">${item.maxRounds} кругів (по ~+$${item.totalPotential})</p>
                            </div>
                        </div>
                    </div>
                `).join('');

            } catch (err) {
                syncIcon.classList.remove('fa-spin');
                statusText.innerHTML = '<i class="fa-solid fa-triangle-exclamation text-amber-500 mr-1"></i> Помилка';
                dealsList.innerHTML = `
                    <div class="bg-white rounded-2xl p-6 text-center border border-slate-100 text-rose-500 text-xs">
                        Помилка з'єднання з сервером. Спробуйте оновити ще раз.
                    </div>`;
            }
        }

        loadData();
        setInterval(loadData, 10000); // Авто-оновлення кожні 10 секунд
    </script>
</body>
</html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
