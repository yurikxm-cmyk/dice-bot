import telebot
import os
import time
import psycopg2
from telebot import types
from flask import Flask
from threading import Thread

# Отримуємо змінні оточення з Render
TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_ID = 12345678  # ЗАМІНІТЬ на ваш реальний Telegram ID (числом)

bot = telebot.TeleBot(TOKEN)
app = Flask('')

# --- Робота з Базою Даних ---
def init_db():
    try:
        # Важливо: використовуємо dsn= для коректного підключення
        conn = psycopg2.connect(dsn=DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                last_roll TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("База даних успішно ініціалізована")
    except Exception as e:
        print(f"Помилка ініціалізації БД: {e}")

def log_user(user):
    try:
        conn = psycopg2.connect(dsn=DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (user_id, username, last_roll)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id) DO UPDATE SET 
                last_roll = CURRENT_TIMESTAMP, 
                username = EXCLUDED.username;
        """, (user.id, user.username))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Помилка запису в БД: {e}")

# --- Веб-сервер для Render ---
@app.route('/')
def home():
    return "Бот працює і база даних підключена!"

def run_web_server():
    # Render динамічно призначає порт, тому беремо його зі змінних
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- Логіка Бота ---
def get_inline_keyboard():
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("🎲 Кинути ще раз", callback_data="roll_dice")
    markup.add(btn)
    return markup

@bot.message_handler(commands=['start', 'roll'])
def welcome(message):
    log_user(message.from_user)
    bot.send_message(
        message.chat.id, 
        "Привіт! Натискай кнопку нижче, щоб випробувати удачу:", 
        reply_markup=get_inline_keyboard()
    )

@bot.message_handler(commands=['stats'])
def show_stats(message):
    # Перевірка, чи це пише адмін
    if message.from_user.id == ADMIN_ID:
        try:
            conn = psycopg2.connect(dsn=DATABASE_URL)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users")
            count = cur.fetchone()[0]
            cur.close()
            conn.close()
            bot.reply_to(message, f"📊 Унікальних користувачів: {count}")
        except Exception as e:
            bot.reply_to(message, "Помилка отримання статистики.")
            print(e)

@bot.callback_query_handler(func=lambda call: call.data == "roll_dice")
def callback_roll(call):
    log_user(call.from_user)
    bot.answer_callback_query(call.id)
    bot.send_chat_action(call.message.chat.id, 'typing')
    
    dice_msg = bot.send_dice(call.message.chat.id)
    time.sleep(3.5)
    
    result = dice_msg.dice.value
    bot.send_message(
        call.message.chat.id, 
        f"🎯 {call.from_user.first_name}, випало: {result}", 
        reply_markup=get_inline_keyboard()
    )

if __name__ == "__main__":
    init_db()
    # Запускаємо веб-сервер в окремому потоці
    Thread(target=run_web_server).start()
    # Запускаємо бота
    print("Бот запускається...")
    bot.infinity_polling()
