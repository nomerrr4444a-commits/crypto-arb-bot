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

# Топові криптобіржі
EXCHANGES = {
    'binance': ccxt.binance({'enableRateLimit': True, 'timeout': 5000}),
    'bybit': ccxt.bybit({'enableRateLimit': True, 'timeout': 5000}),
    'kucoin': ccxt.kucoin({'enableRateLimit': True, 'timeout': 5000}),
    'whitebit': ccxt.whitebit({'enableRateLimit': True, 'timeout': 5000}),
    'bitget': ccxt.bitget({'enableRateLimit': True, 'timeout': 5000}),
    'htx': ccxt.htx({'enableRateLimit': True, 'timeout': 5000}),
    'woo': ccxt.woo({'enableRateLimit': True, 'timeout': 5000}),
    'kraken': ccxt.kraken({'enableRateLimit': True, 'timeout': 5000}),
    'mexc': ccxt.mexc({'enableRateLimit': True, 'timeout': 5000}),
    'gate': ccxt.gate({'enableRateLimit': True, 'timeout': 5000})
}

# Список стабільних і ліквідних монет
SYMBOLS = [
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'ADA/USDT', 
    'AVAX/USDT', 'DOT/USDT', 'LINK/USDT', 'NEAR/USDT', 'SUI/USDT', 
    'ARB/USDT', 'OP/USDT', 'RENDER/USDT', 'MNT/USDT', 'TON/USDT', 
    'TIA/USDT', 'INJ/USDT', 'SEI/USDT', 'APT/USDT', 'ATOM/USDT',
    'LTC/USDT', 'UNI/USDT', 'POL/USDT'
]

def fetch_exchange_data(exchange_name, exchange_obj):
    try:
        exchange_obj.load_markets()
        tickers = exchange_obj.fetch_tickers()
        return exchange_name, tickers
    except Exception:
        try:
            tickers = exchange_obj.fetch_tickers(SYMBOLS)
            return exchange_name, tickers
        except Exception:
            return exchange_name, {}

def background_scanner():
    global latest_signals
    print("🚀 Оновлений сканер ліквідності запрацював...")
    
    while True:
        raw_signals = []
        prices_data = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(fetch_exchange_data, ex_name, ex) for ex_name, ex in EXCHANGES.items()]
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    ex_name, tickers = future.result(timeout=6)
                    if not tickers:
                        continue
                    
                    for symbol in SYMBOLS:
                        ticker = None
                        if symbol in tickers:
                            ticker = tickers[symbol]
                        else:
                            alt = symbol.replace('/', '')
                            for k, v in tickers.items():
                                if symbol in k or alt in k.replace('/', ''):
                                    ticker = v
                                    break
                        
                        if ticker:
                            bid = ticker.get('bid')
                            ask = ticker.get('ask')
                            quote_volume = ticker.get('quoteVolume', 50000) # обсяги за 24г
                            if bid and ask and float(bid) > 0 and float(ask) > 0:
                                if symbol not in prices_data:
                                    prices_data[symbol] = {}
                                prices_data[symbol][ex_name] = {
                                    'bid': float(bid), 
                                    'ask': float(ask),
                                    'volume': float(quote_volume) if quote_volume else 50000
                                }
                except Exception:
                    continue

        # Пошук арбітражу
        for symbol, ex_prices in prices_data.items():
            ex_list = list(ex_prices.keys())
            if len(ex_list) < 2:
                continue
                
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

                    if 0.5 <= spread <= 8.0:
                        # Оцінка ліквідності та кількість прокрутів на $100
                        vol_buy = ex_prices[ex_buy]['volume']
                        vol_sell = ex_prices[ex_sell]['volume']
                        min_vol = min(vol_buy, vol_sell)
                        
                        if min_vol > 500000:
                            liq_status = "Висока 🟢"
                            spins = "5–10+ прокрутів"
                        elif min_vol > 100000:
                            liq_status = "Середня 🟡"
                            spins = "3–5 прокрутів"
                        else:
                            liq_status = "Помірні обсяги 🟠"
                            spins = "1–2 прокрути"

                        raw_signals.append({
                            'symbol': symbol,
                            'buy_exchange': ex_buy,
                            'sell_exchange': ex_sell,
                            'buy_price': ask_price,
                            'sell_price': bid_price,
                            'spread': round(spread, 2),
                            'liquidity': liq_status,
                            'spins_100': spins
                        })

        # Залишаємо ТІЛЬКИ найкращий сигнал для кожної монети
        best_per_coin = {}
        for sig in raw_signals:
            sym = sig['symbol']
            if sym not in best_per_coin or sig['spread'] > best_per_coin[sym]['spread']:
                best_per_coin[sym] = sig

        found_signals = list(best_per_coin.values())
        found_signals = sorted(found_signals, key=lambda x: x['spread'], reverse=True)
        
        latest_signals = found_signals[:30]
        time.sleep(3)

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
            cursor: pointer;
            transition: transform 0.1s, border-color 0.2s;
        }
        .signal-card:active {
            transform: scale(0.98);
            border-color: var(--accent-color);
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
        .tap-hint {
            font-size: 11px;
            color: var(--secondary-text);
            text-align: center;
            margin-top: 6px;
        }
        /* Modal */
        .modal {
            display: none;
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.7);
            justify-content: center;
            align-items: flex-end;
            z-index: 100;
        }
        .modal-content {
            background: var(--card-bg);
            width: 100%;
            max-width: 500px;
            border-top-left-radius: 20px;
            border-top-right-radius: 20px;
            padding: 20px;
            box-sizing: border-box;
            border-top: 1px solid var(--border-color);
            animation: slideUp 0.3s ease-out;
        }
        @keyframes slideUp {
            from { transform: translateY(100%); }
            to { transform: translateY(0); }
        }
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }
        .modal-title {
            font-size: 18px;
            font-weight: 700;
        }
        .close-btn {
            background: none;
            border: none;
            color: var(--secondary-text);
            font-size: 20px;
            cursor: pointer;
        }
        .modal-body p {
            font-size: 13px;
            color: var(--secondary-text);
            margin: 8px 0;
            line-height: 1.4;
        }
        .modal-body strong {
            color: var(--text-color);
        }
        .action-btn {
            display: block;
            width: 100%;
            background: var(--accent-color);
            color: #0f172a;
            border: none;
            padding: 12px;
            border-radius: 10px;
            font-weight: 700;
            font-size: 15px;
            text-align: center;
            margin-top: 16px;
            cursor: pointer;
        }
        .no-signals {
            text-align: center;
