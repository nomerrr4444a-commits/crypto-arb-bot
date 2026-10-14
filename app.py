import os
import time
import threading
import concurrent.futures
from flask import Flask, render_template_string, jsonify
import ccxt
import telebot

app = Flask(__name__)

# ==================== НАЛАШТУВАННЯ ====================
TOKEN = "8634056973:AAF2eMhsePo5ndZbbj8ndqvIdYKBRKCt2k4" 
bot = telebot.TeleBot(TOKEN)
latest_signals = []

# 10 топових криптобірж
EXCHANGES = {
    'binance': ccxt.binance({'enableRateLimit': True}),
    'bybit': ccxt.bybit({'enableRateLimit': True}),
    'kucoin': ccxt.kucoin({'enableRateLimit': True}),
    'whitebit': ccxt.whitebit({'enableRateLimit': True}),
    'bitget': ccxt.bitget({'enableRateLimit': True}),
    'htx': ccxt.htx({'enableRateLimit': True}),
    'woo': ccxt.woo({'enableRateLimit': True}),
    'kraken': ccxt.kraken({'enableRateLimit': True}),
    'mexc': ccxt.mexc({'enableRateLimit': True}),
    'gate': ccxt.gate({'enableRateLimit': True})
}

# Популярні торгові пари
SYMBOLS = [
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT', 
    'NEAR/USDT', 'AVAX/USDT', 'ADA/USDT', 'DOT/USDT', 'LINK/USDT', 
    'SUI/USDT', 'ARB/USDT', 'OP/USDT', 'PEPE/USDT', 'RENDER/USDT'
]

def fetch_exchange_tickers(exchange_name, exchange_obj):
    try:
        # Миттєве завантаження всіх тикерів біржі одним запитом
        tickers = exchange_obj.fetch_tickers(SYMBOLS)
        return exchange_name, tickers
    except Exception:
        try:
            tickers = exchange_obj.fetch_tickers()
            return exchange_name, tickers
        except Exception:
            return exchange_name, {}

def background_scanner():
    global latest_signals
    print("🚀 Ультрашвидкий сканер запрацював у хмарі...")
    while True:
        found_signals = []
        prices_data = {symbol: {} for symbol in SYMBOLS}
        
        # Паралельне опитування всіх 10 біржах одночасно (займає ~1.5 сек)
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_exchange = {
                executor.submit(fetch_exchange_tickers, ex_name, ex): ex_name 
                for ex_name, ex in EXCHANGES.items()
            }
            for future in concurrent.futures.as_completed(future_to_exchange):
                ex_name, tickers = future.result()
                if not tickers:
                    continue
                for symbol in SYMBOLS:
                    if symbol in tickers:
                        t = tickers[symbol]
                        bid = t.get('bid')
                        ask = t.get('ask')
                        if bid and ask:
                            prices_data[symbol][ex_name] = {'bid': bid, 'ask': ask}

        # Пошук арбітражних можливостей
        for symbol, ex_prices in prices_data.items():
            ex_list = list(ex_prices.keys())
            for i in range(len(ex_list)):
                for j in range(len(ex_list)):
                    if i == j:
                        continue
                    ex_buy = ex_list[i]
                    ex_sell = ex_list[j]

                    ask_price = ex_prices[ex_buy]['ask']
                    bid_price = ex_prices[ex_sell]['bid']

                    if not ask_price or not bid_price or ask_price <= 0:
                        continue

                    spread = ((bid_price - ask_price) / ask_price) * 100

                    # Фільтр реалістичного спреду
                    if 0.2 <= spread <= 25.0:
                        found_signals.append({
                            'symbol': symbol,
                            'buy_exchange': ex_buy,
                            'sell_exchange': ex_sell,
                            'buy_price': ask_price,
                            'sell_price': bid_price,
                            'spread': round(spread, 2)
                        })

        found_signals = sorted(found_signals, key=lambda x: x['spread'], reverse=True)
        latest_signals = found_signals[:40]
        time.sleep(2)  # оновлення кожні 2 секунди

# HTML/JS Інтерфейс Telegram Mini App
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Crypto Arbitrage Scanner</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-color: #f8fafc;
            --accent-color: #10b981;
            --secondary-text: #94a3b8;
            --border-color: #334155;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 12px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 14px;
            padding: 0 4px;
        }
        h1 {
            font-size: 18px;
            margin: 0;
            font-weight: 700;
        }
        .status-badge {
            font-size: 11px;
            background: rgba(16, 185, 129, 0.15);
            color: var(--accent-color);
            padding: 4px 8px;
            border-radius: 12px;
            font-weight: 600;
        }
        .signals-container {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .signal-card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 12px 14px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }
        .signal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }
        .coin-name {
            font-size: 15px;
            font-weight: 700;
            color: #ffffff;
        }
        .spread-badge {
            background: #10b981;
            color: #0f172a;
            font-weight: 800;
            font-size: 13px;
            padding: 3px 8px;
            border-radius: 6px;
        }
        .route-box {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(15, 23, 42, 0.5);
            padding: 8px 10px;
            border-radius: 8px;
            font-size: 13px;
        }
        .exchange-col {
            display: flex;
            flex-direction: column;
        }
        .ex-title {
            font-size: 10px;
            color: var(--secondary-text);
            text-transform: uppercase;
        }
        .ex-name {
            font-weight: 600;
            color: #e2e8f0;
            text-transform: uppercase;
        }
        .ex-price {
            font-family: monospace;
            color: #38bdf8;
            font-size: 12px;
        }
        .arrow {
            color: var(--secondary-text);
            font-weight: bold;
            font-size: 16px;
        }
        .no-signals {
            text-align: center;
            padding: 40px 20px;
            color: var(--secondary-text);
            font-size: 14px;
        }
        .loader {
            border: 3px solid var(--border-color);
            border-top: 3px solid var(--accent-color);
            border-radius: 50%;
            width: 24px;
            height: 24px;
            animation: spin 1s linear infinite;
            margin: 20px auto;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>⚡ Crypto Scanner</h1>
        <div class="status-badge" id="status">LIVE 🟢</div>
    </div>

    <div id="signals" class="signals-container">
        <div class="loader"></div>
        <div class="no-signals">Миттєве сканування ринку...</div>
    </div>

    <script>
        let tg = window.Telegram.WebApp;
        tg.expand();

        async function fetchSignals() {
            try {
                let response = await fetch('/api/signals');
                let data = await response.json();
                let container = document.getElementById('signals');
                
                if (data.length === 0) {
                    container.innerHTML = '<div class="no-signals">Аналізуємо біржі, чекаємо перші зв\'язки...</div>';
                    return;
                }

                let html = '';
                data.forEach(sig => {
                    html += `
                        <div class="signal-card">
                            <div class="signal-header">
                                <span class="coin-name">${sig.symbol}</span>
                                <span class="spread-badge">+${sig.spread}%</span>
                            </div>
                            <div class="route-box">
                                <div class="exchange-col">
                                    <span class="ex-title">Купити на</span>
                                    <span class="ex-name">${sig.buy_exchange}</span>
                                    <span class="ex-price">${sig.buy_price}</span>
                                </div>
                                <div class="arrow">➔</div>
                                <div class="exchange-col" style="text-align: right;">
                                    <span class="ex-title">Продати на</span>
                                    <span class="ex-name">${sig.sell_exchange}</span>
                                    <span class="ex-price">${sig.sell_price}</span>
                                </div>
                            </div>
                        </div>
                    `;
                });
                container.innerHTML = html;
            } повний catch (e) {
                console.error('Помилка:', e);
            }
        }

        setInterval(fetchSignals, 3000);
        fetchSignals();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/signals')
def get_signals():
    return jsonify(latest_signals)

if __name__ == '__main__':
    scanner_thread = threading.Thread(target=background_scanner, daemon=True)
    scanner_thread.start()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
