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

# Розширений список монет, включаючи AI-токені та трендові пари
SYMBOLS = [
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT', 
    'NEAR/USDT', 'AVAX/USDT', 'ADA/USDT', 'DOT/USDT', 'LINK/USDT', 
    'SUI/USDT', 'ARB/USDT', 'OP/USDT', 'PEPE/USDT', 'RENDER/USDT',
    'MNT/USDT', 'TON/USDT', 'TIA/USDT', 'INJ/USDT', 'SEI/USDT',
    'APT/USDT', 'FET/USDT', 'WLD/USDT', 'STRK/USDT', 'AI/USDT', 
    'TAO/USDT', 'GRT/USDT', 'OCEAN/USDT', 'AGIX/USDT', 'PNUT/USDT', 'NEIRO/USDT'
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
    print("🚀 Розширений сканер AI та арбітражу запущено у хмарі...")
    
    while True:
        raw_signals = []
        prices_data = {}

        # Паралельне опитування всіх 10 бірж
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
                            if bid and ask and float(bid) > 0 and float(ask) > 0:
                                if symbol not in prices_data:
                                    prices_data[symbol] = {}
                                prices_data[symbol][ex_name] = {'bid': float(bid), 'ask': float(ask)}
                except Exception:
                    continue

        # Пошук арбітражних можливостей
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

                    # Розширюємо межі до 40% для відлову унікальних AI/волатильних спредів
                    if 0.3 <= spread <= 40.0:
                        # Формуємо поради щодо переказу та комісій
                        fee_advice = "Використовуйте мережу з найнижчою комісією (наприклад, BSC, TRC20 для стейблкоїнів або нативну мережу монети). Торгові комісії бірж зазвичай становлять 0.1%."
                        if "USDT" in symbol:
                            fee_advice = "Для виведення/переказу USDT обирайте мережу TRC20 (~$1) або Arbitrum/Polygon (~$0.1), якщо вона підтримується обома біржами."

                        raw_signals.append({
                            'symbol': symbol,
                            'buy_exchange': ex_buy,
                            'sell_exchange': ex_sell,
                            'buy_price': ask_price,
                            'sell_price': bid_price,
                            'spread': round(spread, 2),
                            'advice': fee_advice
                        })

        # Фільтрація: залишаємо ТІЛЬКИ найкращий сигнал для кожної монети
        best_per_coin = {}
        for sig in raw_signals:
            sym = sig['symbol']
            if sym not in best_per_coin or sig['spread'] > best_per_coin[sym]['spread']:
                best_per_coin[sym] = sig

        found_signals = list(best_per_coin.values())
        found_signals = sorted(found_signals, key=lambda x: x['spread'], reverse=True)
        
        latest_signals = found_signals[:35]
        time.sleep(3)

# HTML/JS Інтерфейс Telegram Mini App з інтерактивними модалками
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
            --modal-bg: #1e293b;
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
            margin: 6px 0;
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
        <h1>⚡ AI & Crypto Scanner</h1>
        <div class="status-badge" id="status">LIVE 🟢</div>
    </div>

    <div id="signals" class="signals-container">
        <div class="loader"></div>
        <div class="no-signals">Скануємо ринок та AI-монети...</div>
    </div>

    <!-- Модальне вікно деталей -->
    <div id="signalModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <span class="modal-title" id="modalCoin">BTC/USDT</span>
                <button class="close-btn" onclick="closeModal()">✕</button>
            </div>
            <div class="modal-body" id="modalBody">
                <!-- Контент заповнюється динамічно -->
            </div>
            <button class="action-btn" onclick="closeModal()">Зрозуміло</button>
        </div>
    </div>

    <script>
        let tg = window.Telegram.WebApp;
        tg.expand();
        let currentSignals = [];

        async function fetchSignals() {
            try {
                let response = await fetch('/api/signals');
                let data = await response.json();
                currentSignals = data;
                let container = document.getElementById('signals');
                
                if (data.length === 0) {
                    container.innerHTML = '<div class="no-signals">Шукаємо вигідні спреди по AI та топ-монетах...</div>';
                    return;
                }

                let html = '';
                data.forEach((sig, index) => {
                    html += `
                        <div class="signal-card" onclick="openModal(${index})">
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
                            <div class="tap-hint">Натисніть для перегляду комісій та інструкції 👆</div>
                        </div>
                    `;
                });
                container.innerHTML = html;
            } catch (e) {
                console.error('Помилка завантаження:', e);
            }
        }

        function openModal(index) {
            let sig = currentSignals[index];
            if (!sig) return;

            document.getElementById('modalCoin').innerText = `${sig.symbol} (Спред: +${sig.spread}%)`;
            
            let bodyHtml = `
                <p>🛒 <strong>Купити на біржі:</strong> ${sig.buy_exchange.toUpperCase()} по ціні <code>${sig.buy_price}</code></p>
                <p>💰 <strong>Продати на біржі:</strong> ${sig.sell_exchange.toUpperCase()} по ціні <code>${sig.sell_price}</code></p>
                <hr style="border: 0; border-top: 1px solid var(--border-color); margin: 10px 0;">
                <p>⚙️ <strong>Комісії та переказ:</strong></p>
                <p>${sig.advice}</p>
                <p style="color: #38bdf8; margin-top: 8px;">💡 <em>Порада: Завжди перевіряйте відкриті мережі для введення/виведення на обох біржах перед здійсненням арбітражу!</em></p>
            `;
            
            document.getElementById('modalBody').innerHTML = bodyHtml;
            document.getElementById('signalModal').style.display = 'flex';
        }

        function closeModal() {
            document.getElementById('signalModal').style.display = 'none';
        }

        setInterval(fetchSignals, 4000);
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
