import time
import threading
import ccxt
import telebot

TOKEN = "8634056973:AAF2eMhsePo5ndZbbj8ndqvIdYKBRKCt2k4"
bot = telebot.TeleBot(TOKEN)

# Підключення до біржі для отримання реальних цін
exchange = ccxt.binance({'enableRateLimit': True})

# Віртуальний капітал та статистика
virtual_balance = 100.0
total_profit = 0.0
total_loss = 0.0
user_chat_id = None  # Сюди автоматично запишеться твій ID


@bot.message_handler(commands=['start'])
def send_welcome(message):
    global user_chat_id
    user_chat_id = message.chat.id
    bot.reply_to(
        message,
        "🤖 Симулятор трикутників активовано!\nЯ стежу за ринком і надсилатиму"
        " звіти про кожну угоду сюди.",
    )
    print(f"✅ Збережено Chat ID користувача: {user_chat_id}")


def simulate_triangle_trading():
  global virtual_balance, total_profit, total_loss

  # Чекаємо, поки користувач напише /start у бота
  print("⏳ Чекаю команду /start у Telegram від тебе...")
  while user_chat_id is None:
    time.sleep(1)

  bot.send_message(
      user_chat_id, "🚀 Симулятор угод запущено! Початковий банк: $100.00"
  )

  while True:
    try:
      # Завантажуємо реальні ціни для трикутника
      tickers = exchange.fetch_tickers(["BTC/USDT", "ETH/BTC", "ETH/USDT"])

      price_btc_usdt = tickers["BTC/USDT"]["ask"]
      price_eth_btc = tickers["ETH/BTC"]["ask"]
      price_eth_usdt = tickers["ETH/USDT"]["bid"]

      # Розрахунок результату кола на $100
      start_amount = 100.0
      step1 = start_amount / price_btc_usdt  # Купили BTC
      step2 = step1 / price_eth_btc  # Купили ETH за BTC
      end_amount = step2 * price_eth_usdt  # Продали ETH за USDT

      # Віднімаємо торгову комісію біржі (~0.3% за 3 кроки)
      fee = end_amount * 0.003
      net_result = end_amount - fee
      profit_loss = net_result - start_amount

      # Визначаємо статус угоди
      if profit_loss > 0:
        trade_type = "🟢 ТЕЙК (ПРИБУТОК)"
        total_profit += profit_loss
      else:
        trade_type = "🔴 МІНУС (ЗБИТОК)"
        total_loss += abs(profit_loss)

      virtual_balance += profit_loss

      # Формуємо звіт для Telegram
      msg = (
          f"🔄 <b>Угоду закрито!</b>\n\n"
          f"📊 Статус: {trade_type}\n"
          f"💵 Результат угоди: <code>{round(profit_loss, 2)} $</code>\n"
          f"💰 Загальний баланс: <code>{round(virtual_balance, 2)} $</code>\n"
          f"📈 Загальний прибуток: +{round(total_profit, 2)} $\n"
          f"📉 Загальний мінус: -{round(total_loss, 2)} $\n"
      )

      bot.send_message(user_chat_id, msg, parse_mode="HTML")

      # Пауза між симуляціями угод (наприклад, 60 секунд)
      time.sleep(60)

    except Exception as e:
      print(f"Помилка в симуляторі: {e}")
      time.sleep(10)


if __name__ == "__main__":
  # Запускаємо симулятор в окремому фоновому потоці
  t = threading.Thread(target=simulate_triangle_trading, daemon=True)
  t.start()

  # Запуск самого Telegram бота
  bot.infinity_polling()
