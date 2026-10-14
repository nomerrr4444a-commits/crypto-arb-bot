import os
import time
import threading
from flask import Flask, render_template_string, jsonify
import ccxt
import telebot
from telebot import types

app = Flask(__name__)

# ================= НАЛАШТУВАННЯ =================
TOKEN = "8634056973:AAF2eMhsePo5ndZbbjBndqvIdYkBRKcT2k4"  # <--- Встав сюди свій токен від @BotFather
# ===============================================

bot = telebot.TeleBot(TOKEN)
latest_signals = []

EXCHANGES = {
    'binance': ccxt.binance({'enableRateLimit': True}),
    'bybit': ccxt.bybit({'enableRateLimit': True}),
    'kucoin': ccxt.kucoin({'enableRateLimit': True}),
    'whitebit': ccxt.whitebit({'enableRateLimit': True}),
    'bitget': ccxt.bitget({'enableRateLimit': True}),
    'htx': ccxt.htx({'enableRateLimit': True}),
    'woo': ccxt.woo({'enableRateLimit': True})
}

SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT', 'NEAR/USDT', 'AVAX/USDT']

def background_scanner():
    global latest_signals
    print("🔄 Фоновий багатобіржовий сканер запущено у хмарі...")
    while True:
        found_signals = []
        target_capital = 1000.0

        for symbol in SYMBOLS:
            order_books = {}
            for ex_name, ex_client in EXCHANGES.items():
                try:
                    book = ex_client.fetch_order_book(symbol, limit=5)
                    if book['asks'] and book['bids']:
                        order_books[ex_name] = {
                            'ask': book['asks'][0][0],
                            'bid': book['bids'][0][0]
                        }
                except Exception:
                    continue

            ex_names = list(order_books.keys())
            for i in range(len(ex_names)):
                for j in range(len(ex_names)):
                    if i == j: continue
                    buy_ex = ex_names[i]
                    sell_ex = ex_names[j]
                    buy_price = order_books[buy_ex]['ask']
                    sell_price = order_books[sell_ex]['bid']
                    
                    if sell_price > buy_price:
                        bought_amount = target_capital / buy_price
                        revenue = bought_amount * sell_price
                        fees = (target_capital * 0.002) + 1.0
                        net_profit = revenue - target_capital - fees
                        spread_pct = ((sell_price - buy_price) / buy_price) * 100

                        if net_profit > 15.0:
                            found_signals.append({
                                'symbol': symbol.replace('/', '-'),
                                'buy_ex': buy_ex.upper(),
                                'sell_ex': sell_ex.upper(),
                                'buy_price': round(buy_price, 4),
                                'sell_price': round(sell_price, 4),
                                'spread_pct': round(spread_pct, 2),
                                'net_profit': round(net_profit, 2),
                                'time': '3-5 хв.'
                            })

        found_signals.sort(key=lambda x: x['net_profit'], reverse=True)
        latest_signals = found_signals
        time.sleep(45)

MINI_APP_HTML = """
<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CryptoArb Pro</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #ffffff; margin: 0; padding: 16px; color: #222; }
        .header-btn { background-color: #ffffff; color: #2481cc; border: 2px solid #2481cc; padding: 12px; border-radius: 14px; font-size: 15px; font-weight: 600; width: 100%; cursor: pointer; box-shadow: 0 2px 8px rgba(0,0,0,0.03); }
        .no-signals { text-align: center; color: #999999; font-size: 13px; margin-top: 50px; }
        .signal-card { background: #ffffff; border-radius: 16px; padding: 16px; margin-top: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.06); border: 1px solid #eaeaea; cursor: pointer; }
        .signal-header { display: flex; justify-content: space-between; align-items: center; font-weight: 700; font-size: 18px; }
        .spread-badge { color: #2e7d32; background: #e8f5e9; padding: 4px 10px; border-radius: 8px; font-size: 14px; }
        .signal-row { display: flex; justify-content: space-between; margin-top: 10px; font-size: 14px; color: #555; }
        .divider { height: 1px; background: #eee; margin: 12px 0; }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.4); justify-content: center; align-items: center; padding: 20px; box-sizing: border-box; }
        .modal-content { background: #fff; padding: 20px; border-radius: 16px; width: 100%; max-width: 320px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); }
        .btn { background-color: #2481cc; color: white; border: none; padding: 12px 20px; border-radius: 12px; font-size: 15px; font-weight: 600; width: 100%; cursor: pointer; margin-top: 15px; }
    </style>
</head>
<body>
    <button class="header-btn" onclick="loadSignals()">🔄 Оновити список</button>
    <div id="signal-container"><div class="no-signals">Завантаження актуальних зв'язок...</div></div>
    <div id="modal" class="modal" onclick="closeModal(event)"><div class="modal-content" onclick="event.stopPropagation()"><h3>📖 Алгоритм виконання</h3><p id="modal-text" style="font-size: 14px; color: #444; line-height: 1.5;"></p><button class="btn" onclick="document.getElementById('modal').style.display='none'">Закрити</button></div></div>
    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        let currentSignalsList = [];
        async function loadSignals() {
            const container = document.getElementById('signal-container');
            container.innerHTML = '<div class="no-signals">Скануємо топ-біржі...</div>';
            try {
                const response = await fetch('/api/get_signals');
                const data = await response.json();
                if (data.status === 'success' && data.signals.length > 0) {
                    currentSignalsList = data.signals;
                    let html = '';
                    data.signals.forEach((sig, index) => {
                        html += `
                            <div class="signal-card" onclick="openModal(${index})">
                                <div class="signal-header"><span>🪙 ${sig.symbol}</span><span class="spread-badge">+${sig.spread_pct}% (+$${sig.net_profit})</span></div>
                                <div class="divider"></div>
                                <div class="signal-row"><span>🟢 Купівля: <b>${sig.buy_ex}</b></span><span>Ціна: <b>${sig.buy_price}</b></span></div>
                                <div class="signal-row"><span>🔴 Продаж: <b>${sig.sell_ex}</b></span><span>Ціна: <b>${sig.sell_price}</b></span></div>
                                <div class="divider"></div>
                                <div class="signal-row" style="font-size: 12px; color: #888;"><span>Капітал: $1,000</span><span>Час виводу: ~${sig.time}</span></div>
                            </div>`;
                    });
                    container.innerHTML = html;
                } else { container.innerHTML = '<div class="no-signals">немає сигналів (чекаємо спред)</div>'; }
            } catch (e) { container.innerHTML = '<div class="no-signals">Помилка зв\'язку з сервером</div>'; }
        }
        function openModal(index) {
            const s = currentSignalsList[index];
            if (!s) return;
            document.getElementById('modal-text').innerHTML = `1. Переведіть $1,000 на <b>${s.buy_ex}</b>.<br><br>2. Придбайте <b>${s.symbol}</b> по <code>${s.buy_price}</code>.<br><br>3. Здійсніть вивід на <b>${s.sell_ex}</b>.<br><br>4. Продайте по <code>${s.sell_price}</code>. Чистий прибуток: ~<b>+$${s.net_profit}</b>!`;
            document.getElementById('modal').style.display = 'flex';
        }
        function closeModal(e) { document.getElementById('modal').style.display = 'none'; }
        loadSignals();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(MINI_APP_HTML)

@app.route('/api/get_signals')
def get_signals_api():
    return jsonify({'status': 'success', 'signals': latest_signals})

if __name__ == '__main__':
    threading.Thread(target=background_scanner, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
