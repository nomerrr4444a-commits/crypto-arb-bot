import os
import time
import logging
import threading
from typing import Any
from functools import wraps
import ccxt
import requests
from flask import Flask, request, render_template_string, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

# ------------------------------ Logging ------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("crypto-arb")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

# ------------------------------ Security / Password ------------------------------
PASSWORD_FILE = "scanner_password.txt"

def load_or_init_password() -> str:
    env_pass = os.environ.get("SCANNER_PASSWORD")
    if env_pass:
        return generate_password_hash(env_pass)
    if os.path.exists(PASSWORD_FILE):
        with open(PASSWORD_FILE, "r", encoding="utf-8") as f:
            h = f.read().strip()
            if h:
                return h
    default_pass = "admin123456"
    h = generate_password_hash(default_pass)
    with open(PASSWORD_FILE, "w", encoding="utf-8") as f:
        f.write(h)
    return h

app_password_hash = load_or_init_password()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

LOGIN_HTML = r"""<!doctype html><html lang="uk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Вхід · Safe Crypto Arbitrage</title>
<style>
:root{color-scheme:dark;--bg:#0b1220;--card:#121e30;--line:#26354a;--green:#48e0ae}body{margin:0;background:var(--bg);color:#e6edf7;font-family:Segoe UI,Arial,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;padding:20px}
.box{width:100%;max-width:380px;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:24px}
h1{font-size:20px;margin:0 0 8px}.sub{color:#9badc4;font-size:13px;margin-bottom:20px}
input{width:100%;background:#0b1422;border:1px solid #2a3b51;color:#fff;padding:12px;border-radius:10px;margin-bottom:14px;font-size:15px}
button{width:100%;background:var(--green);color:#0b1220;border:0;padding:12px;border-radius:10px;font-weight:700;cursor:pointer;font-size:15px}
.err{color:#ff8f9a;font-size:13px;margin-bottom:12px}
</style></head><body><main class="box"><h1>Вхід у систему</h1><div class="sub">Введіть пароль для доступу до сканера</div>
{% if error %}<div class="err">{{ error }}</div>{% endif %}
<form method="post"><input type="password" name="password" placeholder="Пароль" required autofocus><button type="submit">Увійти</button></form></main></body></html>"""

@app.route("/login", methods=["GET", "POST"])
def login():
    global app_password_hash
    error = None
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if check_password_hash(app_password_hash, pwd):
            session.clear()
            session["authenticated"] = True
            return redirect(url_for("index"))
        error = "Невірний пароль"
    return render_template_string(LOGIN_HTML, error=error)

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))

# ------------------------------ Scanner Core Config ------------------------------
EXCHANGE_IDS = [
    "binance", "okx", "bybit", "gate", "kucoin", 
    "mexc", "htx", "bitget", "bingx", "coinex", 
    "kraken", "whitebit", "bitfinex", "phemex"
]

TEST_AMOUNTS_USD = [39.0, 152.0]
MAX_ACCEPTABLE_BOOK_IMPACT_PCT = 0.5
MIN_NET_SPREAD_PCT = 1.0
SCAN_INTERVAL_SECONDS = 30

exchanges: dict[str, Any] = {}
for ex_id in EXCHANGE_IDS:
    try:
        ex_class = getattr(ccxt, ex_id)
        ex = ex_class({"enableRateLimit": True, "timeout": 10000})
        ex.load_markets()
        exchanges[ex_id] = ex
    except Exception as exc:
        log.warning("Не вдалося ініціалізувати біржу %s: %s", ex_id, exc)

latest_signals: list[dict[str, Any]] = []
scanner_status: dict[str, Any] = {"running": False, "message": "Ініціалізація..."}
state_lock = threading.Lock()

def fetch_tickers_and_books() -> tuple[int, int, dict[str, dict[str, Any]]]:
    tickers: dict[str, dict[str, Any]] = {}
    fetched_count = 0
    loaded_market_count = 0

    for ex_id, ex in exchanges.items():
        try:
            t = ex.fetch_tickers()
            fetched_count += 1
            for symbol, data in t.items():
                if not symbol.endswith("/USDT"):
                    continue
                loaded_market_count += 1
                ask = data.get("ask")
                bid = data.get("bid")
                base_volume = data.get("quoteVolume") or data.get("baseVolume")
                if not ask or not bid or ask <= 0 or bid <= 0:
                    continue
                if symbol not in tickers:
                    tickers[symbol] = {}
                tickers[symbol][ex_id] = {
                    "ask": float(ask),
                    "bid": float(bid),
                    "volume": float(base_volume) if base_volume else 0.0,
                    "fee": ex.fees.get("trading", {}).get("taker", 0.001)
                }
        except Exception as exc:
            log.warning("Помилка отримання тікерів з %s: %s", ex_id, exc)

    return fetched_count, loaded_market_count, tickers

def evaluate_size(route: dict[str, Any], buy_book: dict[str, Any], sell_book: dict[str, Any], amount_usd: float) -> dict[str, Any]:
    if not buy_book or not sell_book:
        return {"good": False, "status": "Стакан недоступний", "profit_usd": None, "net_spread_pct": None}
    
    try:
        asks = buy_book.get("asks", [])
        bids = sell_book.get("bids", [])
        if not asks or not bids:
            return {"good": False, "status": "Порожній стакан", "profit_usd": None, "net_spread_pct": None}

        remaining = amount_usd
        bought_base = 0.0
        cost_usd = 0.0
        for price, volume in asks:
            p, v = float(price), float(volume)
            chunk_cost = p * v
            if remaining >= chunk_cost:
                remaining -= chunk_cost
                cost_usd += chunk_cost
                bought_base += v
            else:
                fraction = remaining / p
                bought_base += fraction
                cost_usd += remaining
                remaining = 0.0
                break

        buy_full = (remaining <= 0.001)
        avg_buy_price = cost_usd / bought_base if bought_base > 0 else route["buy_price"]
        buy_impact = abs(avg_buy_price - route["buy_price"]) / route["buy_price"] * 100

        remaining_base = bought_base
        revenue_usd = 0.0
        sold_base = 0.0
        for price, volume in bids:
            p, v = float(price), float(volume)
            if remaining_base >= v:
                remaining_base -= v
                revenue_usd += p * v
                sold_base += v
            else:
                revenue_usd += p * remaining_base
                sold_base += remaining_base
                remaining_base = 0.0
                break

        sell_full = (remaining_base <= 0.0001)
        avg_sell_price = revenue_usd / sold_base if sold_base > 0 else route["sell_price"]
        sell_impact = abs(avg_sell_price - route["sell_price"]) / route["sell_price"] * 100

        buy_fee = route["buy_fee"] * cost_usd
        sell_fee = route["sell_fee"] * revenue_usd
        net_revenue = revenue_usd - buy_fee - sell_fee
        profit = net_revenue - cost_usd
        net_spread_pct = (profit / cost_usd) * 100 if cost_usd > 0 else -999

        max_impact = max(buy_impact, sell_impact)
        good = buy_full and sell_full and (net_spread_pct >= MIN_NET_SPREAD_PCT) and (max_impact <= MAX_ACCEPTABLE_BOOK_IMPACT_PCT)

        return {
            "good": good,
            "status": "Ліквідність підтверджена" if good else "Недостатня глибина",
            "profit_usd": round(profit, 2),
            "net_spread_pct": round(net_spread_pct, 2),
            "buy_full": buy_full,
            "sell_full": sell_full,
            "max_impact_pct": round(max_impact, 3),
            "buy_fee_pct": route["buy_fee"] * 100,
            "sell_fee_pct": route["sell_fee"] * 100,
        }
    except Exception as exc:
        return {"good": False, "status": f"Помилка: {type(exc).__name__}", "profit_usd": None, "net_spread_pct": None}

def scan_once() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started_at = time.time()
    fetched_count, loaded_market_count, tickers = fetch_tickers_and_books()
    
    candidates = []
    for symbol, ex_data in tickers.items():
        if len(ex_data) < 2:
            continue
        sorted_exs = sorted(ex_data.items(), key=lambda x: x[1]["ask"])
        best_buy_ex, best_buy_info = sorted_exs[0]
        
        sorted_sell = sorted(ex_data.items(), key=lambda x: x[1]["bid"], reverse=True)
        best_sell_ex, best_sell_info = sorted_sell[0]
        
        if best_buy_ex == best_sell_ex:
            continue
            
        buy_price = best_buy_info["ask"]
        sell_price = best_sell_info["bid"]
        
        if buy_price <= 0:
            continue
            
        gross_spread = ((sell_price - buy_price) / buy_price) * 100
        if gross_spread <= 0.3:
            continue
            
        candidates.append({
            "symbol": symbol,
            "buy_exchange": best_buy_ex,
            "sell_exchange": best_sell_ex,
            "buy_price": buy_price,
            "sell_price": sell_price,
            "gross_spread": gross_spread,
            "buy_fee": best_buy_info["fee"],
            "sell_fee": best_sell_info["fee"],
        })

    books: dict[str, dict[str, Any]] = {}
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = {}
        for route in candidates[:25]:
            sym = route["symbol"]
            for ex_id in (route["buy_exchange"], route["sell_exchange"]):
                if ex_id not in books and ex_id not in futures:
                    futures[ex_id] = executor.submit(exchanges[ex_id].fetch_order_book, sym, 20)
        
        for ex_id, fut in futures.items():
            try:
                books[ex_id] = {candidates[0]["symbol"]: fut.result()}
            except Exception:
                pass

    signals: list[dict[str, Any]] = []
    for route in candidates[:25]:
        symbol = route["symbol"]
        buy_book = books.get(route["buy_exchange"], {}).get(symbol)
        sell_book = books.get(route["sell_exchange"], {}).get(symbol)
        
        sizes = {}
        for amount in TEST_AMOUNTS_USD:
            sizes[str(int(amount))] = evaluate_size(route, buy_book, sell_book, amount)
            
        signals.append({
            "symbol": symbol,
            "buy_exchange": route["buy_exchange"],
            "sell_exchange": route["sell_exchange"],
            "buy_price": route["buy_price"],
            "sell_price": route["sell_price"],
            "gross_spread_pct": route["gross_spread"],
            "sizes": sizes,
        })

    signals.sort(key=lambda s: max((s["sizes"][str(int(amt))].get("net_spread_pct") or -999 for amt in TEST_AMOUNTS_USD)), reverse=True)
    
    status = {
        "running": True,
        "last_scan": time.strftime("%H:%M:%S", time.localtime()),
        "exchange_count": fetched_count,
        "shared_symbols": len(tickers),
        "duration_seconds": round(time.time() - started_at, 1),
    }
    return signals, status

def background_scanner() -> None:
    while True:
        try:
            with state_lock:
                scanner_status["running"] = True
            signals, status = scan_once()
            with state_lock:
                latest_signals[:] = signals
                scanner_status.clear()
                scanner_status.update(status)
        except Exception as exc:
            log.exception("Помилка сканера")
        time.sleep(SCAN_INTERVAL_SECONDS)

# ------------------------------ Mini App Dashboard HTML ------------------------------
DASHBOARD_HTML = r"""<!doctype html><html lang="uk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Safe Crypto Arbitrage</title>
<style>
:root{--bg:#0f172a;--card:#1e293b;--line:#334155;--green:#10b981;--text:#f8fafc;--muted:#94a3b8}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;padding:12px}
.wrap{max-width:480px;margin:auto}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}
.brand{font-size:18px;font-weight:700;display:flex;align-items:center;gap:6px}.pill{background:#064e3b;color:var(--green);border-radius:20px;padding:4px 10px;font-size:11px;font-weight:600}
.signal{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin-bottom:12px;cursor:pointer;transition:border .2s}
.signal:hover{border-color:var(--green)}
.head{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.coin{font-weight:800;font-size:16px}.spread{background:#064e3b;color:var(--green);font-weight:800;font-size:13px;padding:4px 8px;border-radius:8px}
.route-box{display:grid;grid-template-columns:1fr auto 1fr;gap:8px;align-items:center;background:#0f172a;border:1px solid var(--line);border-radius:10px;padding:10px;text-align:center}
.ex-label{font-size:10px;color:var(--muted);text-transform:uppercase;margin-bottom:2px}
.ex-name{font-weight:700;font-size:13px}.ex-price{font-family:monospace;font-size:12px;color:var(--green);margin-top:2px}
.arrow{color:var(--muted);font-size:16px}
.hint{text-align:center;color:var(--muted);font-size:11px;margin-top:8px}
.empty{text-align:center;padding:40px;color:var(--muted)}
.modal{display:none;position:fixed;inset:0;background:#000bd9;background:rgba(0,0,0,0.7);z-index:9;align-items:center;justify-content:center;padding:16px}
.modalbox{width:100%;max-width:420px;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;max-height:85vh;overflow:auto}
.modalhead{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}.modalhead h3{margin:0;font-size:16px}
.close{background:var(--line);border:0;color:#fff;padding:6px 10px;border-radius:8px;cursor:pointer}
.det-row{background:#0f172a;border:1px solid var(--line);border-radius:10px;padding:10px;margin-bottom:8px;font-size:13px}
.det-row b{color:var(--green)}
</style></head><body><main class="wrap"><header class="top"><div class="brand">⚡ Safe Crypto Arbitrage</div><span class="pill" id="statuspill">LIVE ●</span></header>
<section id="signals"><div class="empty">Сканування ринку...</div></section></main>
<div id="modal" class="modal" onclick="if(event.target===this)closeModal()"><div class="modalbox"><div class="modalhead"><h3 id="mtitle">Деталі</h3><button class="close" onclick="closeModal()">✕</button></div><div id="mbody"></div></div></div>
<script>
let allSignals=[];
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function pct(x){return x==null||!Number.isFinite(Number(x))?'—':(Number(x)>=0?'+':'')+Number(x).toFixed(2)+'%'}
function card(sig,i){
return `<article class="signal" onclick="openModal(${i})">
<div class="head"><div class="coin">${esc(sig.symbol)}</div><div class="spread">${esc(pct(sig.gross_spread_pct))}</div></div>
<div class="route-box">
<div><div class="ex-label">Купити</div><div class="ex-name">${esc(sig.buy_exchange.toUpperCase())}</div><div class="ex-price">${esc(sig.buy_price)}</div></div>
<div class="arrow">→</div>
<div><div class="ex-label">Продати</div><div class="ex-name">${esc(sig.sell_exchange.toUpperCase())}</div><div class="ex-price">${esc(sig.sell_price)}</div></div>
</div><div class="hint">Натисніть для деталей ліквідності та сум ($39 / $152) 👆</div></article>`;
}
function render(){
let el=document.getElementById('signals');
el.innerHTML=allSignals.length?allSignals.map((s,i)=>card(s,i)).join(''):'<div class="empty">Пошук вигідних маршрутів...</div>';
}
function openModal(i){
let s=allSignals[i];if(!s)return;
document.getElementById('mtitle').textContent=s.symbol+' ('+s.buy_exchange.toUpperCase()+' → '+s.sell_exchange.toUpperCase()+')';
let b39=s.sizes['39']||{};let b152=s.sizes['152']||{};
document.getElementById('mbody').innerHTML=`
<div class="det-row"><b>Сума $39:</b><br>Статус: ${esc(b39.status)}<br>Прибуток: <b>$${b39.profit_usd??'—'}</b><br>Чистий спред: <b>${pct(b39.net_spread_pct)}</b></div>
<div class="det-row"><b>Сума $152:</b><br>Статус: ${esc(b152.status)}<br>Прибуток: <b>$${b152.profit_usd??'—'}</b><br>Чистий спред: <b>${pct(b152.net_spread_pct)}</b></div>
`;
document.getElementById('modal').style.display='flex';
}
function closeModal(){document.getElementById('modal').style.display='none'}
async function refresh(){
try{let res=await fetch('/api/signals',{cache:'no-store'});if(res.status===401){location.href='/login';return;}allSignals=await res.json();render();}catch(e){}
}
refresh();setInterval(refresh,10000);
</script></body></html>"""

@app.route("/")
@login_required
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route("/api/signals")
@login_required
def api_signals():
    with state_lock:
        return jsonify(latest_signals)

if __name__ == "__main__":
    scanner_thread = threading.Thread(target=background_scanner, daemon=True, name="market-scanner")
    scanner_thread.start()
    port = int(os.environ.get("PORT", "5000"))
    host = os.getenv("HOST", "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    if os.environ.get("PORT"):
        from waitress import serve
        serve(app, host=host, port=port, threads=8)
    else:
        app.run(host=host, port=port, debug=False, threaded=True, use_reloader=False)
