import telebot
import os
import time
import psycopg2  # Додано
from telebot import types
from flask import Flask
from threading import Thread

TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL') # Додайте в змінні оточення
ADMIN_ID = 12345678  # ЗАМІНІТЬ на ваш Telegram ID

bot = telebot.TeleBot(TOKEN)
app = Flask('')

# --- Робота з Базою Даних ---
def init_db():
    conn = psycopg2.connect(DATABASE_URL)
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

def log_user(user):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (user_id, username, last_roll)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id) DO UPDATE SET last_roll = CURRENT_TIMESTAMP;
        """, (user.id, user.username))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Помилка БД: {e}")

# --- Веб-сервер ---
@app.route('/')
def home():
    return "Бот працює!"

def run_web_server():
    app.run(host='0.0.0.0', port=8080)

# --- Логіка Бота ---
def get_inline_keyboard():
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("🎲 Кинути ще раз", callback_data="roll_dice")
    markup.add(btn)
    return markup

@bot.message_handler(commands=['start', 'roll'])
def welcome(message):
    log_user(message.from_user) # Логуємо юзера
    bot.send_message(
        message.chat.id, 
        "Привіт! Натискай кнопку нижче, щоб випробувати удачу:", 
        reply_markup=get_inline_keyboard()
    )

@bot.message_handler(commands=['stats'])
def show_stats(message):
    if message.from_user.id == ADMIN_ID:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        bot.reply_to(message, f"📊 Унікальних користувачів: {count}")

@bot.callback_query_handler(func=lambda call: call.data == "roll_dice")
def callback_roll(call):
    log_user(call.from_user) # Оновлюємо активність
    bot.send_chat_action(call.message.chat.id, 'typing')
    dice_msg = bot.send_dice(call.message.chat.id)
    bot.answer_callback_query(call.id)
    
    time.sleep(3.5)
    
    result = dice_msg.dice.value
    bot.send_message(
        call.message.chat.id, 
        f"🎯 {call.from_user.first_name}, випало: {result}", 
        reply_markup=get_inline_keyboard()
    )

if __name__ == "__main__":
    init_db() # Ініціалізація таблиці при старті
    Thread(target=run_web_server).start()
    bot.infinity_polling()
