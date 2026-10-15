    exchange_id, data, errors = future.result()
    books[exchange_id] = data
    if errors:
               exchange_errors.append(f"{exchange_id}: стакан недоступний для {len(errors)} пар")
                except Exception as exc:
                    exchange_errors.append(f"book worker: {type(exc).__name__}")

    signals: list[dict[str, Any]] = []
    for route in candidates:
        symbol = route["symbol"]
        buy_book = books.get(route["buy_exchange"], {}).get(symbol)
        sell_book = books.get(route["sell_exchange"], {}).get(symbol)
        sizes: dict[str, Any] = {}
        for amount in TEST_AMOUNTS_USD:
            sizes[str(int(amount))] = evaluate_size(route, buy_book, sell_book, amount)
        # Keep all checked opportunities visible so the user can see why a route failed.
        liquidity = "Висока" if all(
            r["buy_full"] and r["sell_full"] and r["max_impact_pct"] is not None and r["max_impact_pct"] <= MAX_ACCEPTABLE_BOOK_IMPACT_PCT
            for r in sizes.values()
        ) else "Потребує перевірки"
        signals.append({
            "symbol": symbol,
            "buy_exchange": route["buy_exchange"],
            "sell_exchange": route["sell_exchange"],
            "buy_price": route["buy_price"],
            "sell_price": route["sell_price"],
            "gross_spread_pct": route["gross_spread"],
            "preliminary_net_pct": route["preliminary_net"],
            "buy_volume_24h": route["buy_volume_24h"],
            "sell_volume_24h": route["sell_volume_24h"],
            "buy_fee_pct": route["buy_fee"] * 100,
            "sell_fee_pct": route["sell_fee"] * 100,
            "fee_estimated": route["buy_fee_estimated"] or route["sell_fee_estimated"],
            "liquidity": liquidity,
            "sizes": sizes,
            "transfer_costs_checked": False,
        })

    signals.sort(
        key=lambda sig: max(
            (sig["sizes"][str(int(amount))].get("net_spread_pct") or -999 for amount in TEST_AMOUNTS_USD),
            default=-999,
        ),
        reverse=True,
    )
    status = {
        "running": True,
        "last_scan": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "exchange_count": fetched_count,
        "configured_exchange_count": len(EXCHANGES),
        "market_count": loaded_market_count,
        "shared_symbols": len(ticker_data),
        "candidate_count": len(signals),
        "error_exchanges": exchange_errors[:15],
        "duration_seconds": round(time.time() - started_at, 1),
        "message": "Сканування завершено" if signals else "Підходящих маршрутів поки не знайдено",
    }
    return signals, status


def background_scanner() -> None:
    log.info("Приватний сканер працює. Торги й перекази не виконуються.")
    while True:
        try:
            with state_lock:
                scanner_status["running"] = True
                scanner_status["message"] = "Оновлюємо котирування і стакани…"
            signals, status = scan_once()
            with state_lock:
                latest_signals[:] = signals
                scanner_status.clear()
                scanner_status.update(status)
            log.info("Сканування: %d маршрутів, %d бірж, %.1f c", len(signals), status["exchange_count"], status["duration_seconds"])
        except Exception as exc:
            log.exception("Помилка циклу сканера")
            with state_lock:
                scanner_status["running"] = False
                scanner_status["message"] = f"Помилка сканера: {type(exc).__name__}"
                scanner_status["error_exchanges"] = [str(exc)[:200]]
        time.sleep(SCAN_INTERVAL_SECONDS)


# ------------------------------ Dashboard ------------------------------
DASHBOARD_HTML = r"""<!doctype html><html lang="uk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Приватний криптоарбітражний сканер</title>
<style>
:root{color-scheme:dark;--bg:#0b1220;--card:#121e30;--line:#26354a;--muted:#9badc4;--green:#48e0ae;--red:#ff8f9a;--blue:#84cfff}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#e6edf7;font-family:Segoe UI,Arial,sans-serif;padding:20px}.wrap{max-width:1320px;margin:auto}.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:18px}.brand h1{font-size:22px;margin:0 0 5px}.sub{font-size:12px;color:var(--muted)}.pill{border:1px solid #245944;background:#103326;color:var(--green);border-radius:30px;padding:8px 12px;font-size:12px}.logout{border:1px solid #34445b;background:#172338;color:#e9f0f9;border-radius:9px;padding:9px 12px;cursor:pointer}.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:14px}.stat{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:14px}.stat label{display:block;color:var(--muted);font-size:12px;margin-bottom:8px}.stat b{font-size:20px}.notice{border:1px solid #5d4b27;background:#2a2417;color:#e9d39a;border-radius:12px;padding:12px 14px;line-height:1.5;font-size:12px;margin:12px 0 16px}.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:15px 0}.toolbar input{min-width:200px;flex:1;background:#101b2d;border:1px solid #2a3b51;color:#fff;padding:11px 12px;border-radius:10px}.hint{color:var(--muted);font-size:12px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.signal{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:15px;cursor:pointer;transition:border .15s}.signal:hover{border-color:#4a7893}.signalhead{display:flex;justify-content:space-between;gap:10px;align-items:start;margin-bottom:10px}.coin{font-weight:800;font-size:17px}.route{font-size:12px;color:var(--muted);margin-top:4px}.spread{border-radius:7px;background:#153629;color:var(--green);font-weight:800;font-size:12px;padding:6px 8px;white-space:nowrap}.prices{display:grid;grid-template-columns:1fr 1fr;gap:8px}.pricebox{background:#0b1422;border:1px solid #1d2c41;border-radius:9px;padding:10px}.pricebox label{display:block;color:var(--muted);font-size:11px;margin-bottom:5px}.pricebox b{font-family:Consolas,monospace;font-size:13px;overflow-wrap:anywhere}.sizerow{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:9px}.size{padding:10px;border-radius:9px;border:1px solid #26394d;background:#0d1727}.size.good{border-color:#267d5d;background:#102d26}.size.no{border-color:#5a3540}.size strong{display:block;font-size:12px;margin-bottom:5px}.size .number{font-size:16px;font-weight:800}.size small{display:block;color:var(--muted);font-size:11px;margin-top:4px;line-height:1.4}.goodtext{color:var(--green)}.badtext{color:#ffacb4}.muted{color:var(--muted)}.empty{padding:35px;text-align:center;color:var(--muted);background:var(--card);border-radius:12px;border:1px solid var(--line);grid-column:1/-1}.footer{color:#7f91a8;font-size:11px;line-height:1.6;margin-top:18px}.modal{display:none;position:fixed;inset:0;background:#000b;z-index:9;align-items:center;justify-content:center;padding:16px}.modalbox{width:min(640px,100%);max-height:90vh;overflow:auto;background:#121e30;border:1px solid #34445b;border-radius:16px;padding:18px}.modalhead{display:flex;align-items:center;justify-content:space-between;gap:10px}.modalhead h2{font-size:18px;margin:0}.close{border:0;background:#26374b;color:#fff;border-radius:8px;padding:8px 11px;cursor:pointer}.detailgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px}.detail{padding:12px;background:#0c1626;border:1px solid #26374b;border-radius:10px}.detail h3{font-size:13px;margin:0 0 8px}.detail p{font-size:12px;color:var(--muted);margin:5px 0}.danger{color:#ffb1b8}.success{color:var(--green)}@media(max-width:850px){.grid{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}}@media(max-width:480px){body{padding:12px}.brand h1{font-size:18px}.stats{gap:7px}.stat{padding:11px}.stat b{font-size:16px}.detailgrid{grid-template-columns:1fr}}
</style></head><body><main class="wrap"><header class="top"><div class="brand"><h1>⚡ Приватний арбітражний сканер</h1><div class="sub">Spot USDT · публічні API · без автоматичних угод</div></div><div style="display:flex;gap:10px;align-items:center"><span class="pill" id="statuspill">● запускається</span><form method="post" action="/logout"><button class="logout" type="submit">Вийти</button></form></div></header>
<section class="stats"><div class="stat"><label>Біржі з даними</label><b id="excount">—</b></div><div class="stat"><label>Монети / ринки</label><b id="marketcount">—</b></div><div class="stat"><label>Перевірені маршрути</label><b id="routecount">—</b></div><div class="stat"><label>Останнє сканування</label><b id="lastscan" style="font-size:13px">очікування</b></div></section>
<div class="notice"><b>Що означає «ТАК»:</b> стакан показав достатню глибину для всієї суми, чистий спред після приблизних торгових комісій не нижче <b>1,5%</b>, а розрахункове прослизання не вище <b>0,5%</b>. <b>Комісії виведення, мережа, блокування депозиту/виведення та рух ціни під час переказу не включені</b> — тому це ще не гарантія прибутку.</div>
<div class="toolbar"><input id="search" placeholder="Пошук монети або біржі, наприклад SOL…" autocomplete="off"><span class="hint" id="scanmsg">Перший цикл може зайняти трохи часу.</span></div><section id="signals" class="grid"><div class="empty">Підключаємо публічні API бірж…</div></section>
<div class="footer">Відбір: USDT spot, обсяг пари від $100 000 за 24 год, внутрішній спред біржі до 2%, актуальність котирувань і глибина до 20 рівнів стакана. Приблизні комісії, якщо біржа їх не повідомляє через CCXT, рахуються як 0,10% на кожну сторону. Спочатку вручну перевір статус депозиту/виведення і доступну мережу на обох біржах. Сканер не має API-ключів бірж і не може торгувати.</div></main>
<div id="modal" class="modal" onclick="if(event.target===this)closeModal()"><div class="modalbox"><div class="modalhead"><h2 id="modaltitle">Деталі</h2><button class="close" onclick="closeModal()">Закрити</button></div><div id="modalbody"></div></div></div>
<script>
let allSignals=[];let lastStatus={};
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function money(x){return x==null||!Number.isFinite(Number(x))?'—':'$'+Number(x).toFixed(2)}
function pct(x){return x==null||!Number.isFinite(Number(x))?'—':(Number(x)>=0?'+':'')+Number(x).toFixed(2)+'%'}
function price(x){if(x==null)return '—';return Number(x).toLocaleString('en-US',{maximumSignificantDigits:10});}
function sizeCard(amount,r){if(!r)return '';const good=!!r.good;let amountLabel='$'+amount;let value=r.profit_usd==null?'НЕ ПІДТВЕРДЖЕНО':money(r.profit_usd);let spread=r.net_spread_pct==null?'—':pct(r.net_spread_pct);return `<div class="size ${good?'good':'no'}"><strong>${amountLabel} · ${good?'<span class="goodtext">ПІДХОДИТЬ</span>':'<span class="badtext">НЕ ПІДТВЕРДЖЕНО</span>'}</strong><div class="number">${esc(value)}</div><small>Чистий спред: ${esc(spread)}<br>${esc(r.status)}<br>Прослизання: ${r.max_impact_pct==null?'—':esc(Number(r.max_impact_pct).toFixed(3)+'%')}</small></div>`;}
function card(sig,i){let sizes=sig.sizes||{};return `<article class="signal" onclick="openModal(${i})"><div class="signalhead"><div><div class="coin">${esc(sig.symbol)}</div><div class="route">${esc(sig.buy_exchange.toUpperCase())} → ${esc(sig.sell_exchange.toUpperCase())}</div></div><div class="spread">Брутто ${esc(pct(sig.gross_spread_pct))}</div></div><div class="prices"><div class="pricebox"><label>Купити (ask)</label><b>${esc(price(sig.buy_price))}</b></div><div class="pricebox"><label>Продати (bid)</label><b>${esc(price(sig.sell_price))}</b></div></div><div class="sizerow">${sizeCard(39,sizes['39'])}${sizeCard(152,sizes['152'])}</div><div class="route" style="margin-top:10px">24h volume: ${esc(money(sig.buy_volume_24h))} / ${esc(money(sig.sell_volume_24h))} · ${esc(sig.liquidity)}</div></article>`;}
function renderSignals(){let q=document.getElementById('search').value.trim().toLowerCase();let filtered=allSignals.filter(s=>`${s.symbol} ${s.buy_exchange} ${s.sell_exchange}`.toLowerCase().includes(q));let el=document.getElementById('signals');el.innerHTML=filtered.length?filtered.map(s=>card(s,allSignals.indexOf(s))).join(''):'<div class="empty">Поки немає маршрутів, що пройшли попередній відбір. Це не означає, що на ринку немає арбітражу — спробуй оновити пізніше.</div>';}
function openModal(index){let s=allSignals[index];if(!s)return;document.getElementById('modaltitle').textContent=s.symbol+' · '+s.buy_exchange.toUpperCase()+' → '+s.sell_exchange.toUpperCase();const block=(amt,r)=>{if(!r)return '';return `<div class="detail"><h3>$${amt}: ${r.good?'<span class="success">ПІДХОДИТЬ</span>':'<span class="danger">НЕ ПІДТВЕРДЖЕНО</span>'}</h3><p>Результат після торгових комісій: <b>${esc(money(r.profit_usd))}</b></p><p>Чистий спред: <b>${esc(pct(r.net_spread_pct))}</b></p><p>Купівля: ${r.buy_full?'повна':'неповна'}; продаж: ${r.sell_full?'повний':'неповний'}</p><p>Прослизання купівлі: ${r.buy_impact_pct==null?'—':esc(Number(r.buy_impact_pct).toFixed(3)+'%')}</p><p>Прослизання продажу: ${r.sell_impact_pct==null?'—':esc(Number(r.sell_impact_pct).toFixed(3)+'%')}</p><p>Комісія купівлі/продажу: ${esc(Number(r.buy_fee_pct).toFixed(3))}% / ${esc(Number(r.sell_fee_pct).toFixed(3))}%${r.fees_estimated?' (оцінка)':''}</p><p>${esc(r.status)}</p></div>`};document.getElementById('modalbody').innerHTML=`<div class="detailgrid">${block(39,s.sizes['39'])}${block(152,s.sizes['152'])}</div><div class="notice" style="margin-top:12px"><b>Важливо:</b> розрахунок передбачає, що обидва ордери можна виконати за оціненими рівнями стакана. Не враховані виведення/депозит, мережеві комісії, затримка переказу та зміна цін. Перевір на біржах, що депозит і виведення ${esc(s.symbol.split('/')[0])} активні через одну й ту саму мережу. Невідповідність токенів з однаковим тикером може зламати маршрут.</div>`;document.getElementById('modal').style.display='flex';}
function closeModal(){document.getElementById('modal').style.display='none'}
async function refresh(){try{let [sr,st]=await Promise.all([fetch('/api/signals',{cache:'no-store'}),fetch('/api/status',{cache:'no-store'})]);if(sr.status===401||st.status===401){location.href='/login';return}allSignals=await sr.json();lastStatus=await st.json();document.getElementById('excount').textContent=(lastStatus.exchange_count??'—')+' / '+(lastStatus.configured_exchange_count??'—');document.getElementById('marketcount').textContent=(lastStatus.shared_symbols??'—')+' / '+(lastStatus.market_count??'—');document.getElementById('routecount').textContent=allSignals.length;document.getElementById('lastscan').textContent=lastStatus.last_scan||'очікування';document.getElementById('scanmsg').textContent=(lastStatus.message||'')+(lastStatus.duration_seconds!=null?' · '+lastStatus.duration_seconds+' с':'');document.getElementById('statuspill').textContent=lastStatus.running?'● LIVE':'● очікування';renderSignals()}catch(e){document.getElementById('scanmsg').textContent='Зв’язок зі сканером відсутній';}}
document.getElementById('search').addEventListener('input',renderSignals);refresh();setInterval(refresh,10000);
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


@app.route("/api/status")
@login_required
def api_status():
    with state_lock:
        return jsonify(dict(scanner_status))


if __name__ == "__main__":
    if not EXCHANGES:
        raise RuntimeError("Не вдалося ініціалізувати жодну біржу. Перевстанови ccxt.")
    scanner_thread = threading.Thread(target=background_scanner, daemon=True, name="market-scanner")
    scanner_thread.start()
    port = int(os.environ.get("PORT", "5000"))
    host = os.getenv("HOST", "0.0.0.0" if os.getenv("PORT") else "127.0.0.1")
    if os.getenv("PORT"):
        # Waitress is used for hosted deployments; no Flask debug/reloader.
        from waitress import serve
        serve(app, host=host, port=port, threads=8)
    else:
        print(f"\nВідкрий у браузері: http://127.0.0.1:{port}")
        print("Пароль не зберігається у файлі. Не використовуй пароль від біржі.\n")
        app.run(host=host, port=port, debug=False, threaded=True, use_reloader=False)

