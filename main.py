import telebot
import os
import time
import psycopg2
import threading
from telebot import types
from flask import Flask
from threading import Thread

# Налаштування
TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_ID = 8765742454 

bot = telebot.TeleBot(TOKEN)
app = Flask('')

def delete_after(chat_id, message_id, delay=120):
    def delayed_delete():
        time.sleep(delay)
        try:
            bot.delete_message(chat_id, message_id)
        except: pass
    threading.Thread(target=delayed_delete).start()

# --- ФУНКЦІЇ РОБОТИ З БД ---
def get_top_text(chat_id):
    conn = None
    try:
        conn = psycopg2.connect(dsn=DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT username, sixes_count FROM group_stats WHERE chat_id = %s AND sixes_count > 0 ORDER BY sixes_count DESC LIMIT 10", (chat_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        if not rows:
            return "🏆 **ТОП ГРУПИ:**\n\nПоки що ніхто не вибив 6! Будь першим! 🎲"
        
        text = "🏆 **ТОП ГРУПИ (найбільше шісток):**\n\n"
        for i, row in enumerate(rows):
            text += f"{i+1}. {row[0]} — 🔥 `{row[1]}`\n"
        return text
    except Exception as e:
        if conn: conn.close()
        return f"❌ Помилка БД: {e}"

def get_stats_text(chat_id):
    conn = None
    try:
        conn = psycopg2.connect(dsn=DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM group_stats WHERE chat_id = %s", (chat_id,))
        total = cur.fetchone()[0]
        cur.close()
        conn.close()
        return f"📊 **Статистика чату:**\n\nВсього гравців у базі: `{total}`"
    except Exception as e:
        if conn: conn.close()
        return f"❌ Помилка БД: {e}"

# --- КЛАВІАТУРА ---
def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("🎲 Кинути кубик"),
        types.KeyboardButton("🏆 ТОП цієї групи"),
        types.KeyboardButton("📊 Статистика групи")
    )
    return markup

# --- ОБРОБКА ПОВІДОМЛЕНЬ ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    msg = bot.send_message(
        message.chat.id, 
        "🎰 Бот активовано!\nВикористовуй кнопки на панелі знизу 👇", 
        reply_markup=get_main_keyboard()
    )
    delete_after(message.chat.id, message.message_id)
    delete_after(message.chat.id, msg.message_id)

@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    chat_id = message.chat.id
    text = message.text.strip() # Очищаємо від зайвих пробілів

    if text == "🎲 Кинути кубик":
        delete_after(chat_id, message.message_id)
        dice_msg = bot.send_dice(chat_id)
        delete_after(chat_id, dice_msg.message_id)
        
        # Тут має бути твоя функція оновлення даних update_data(...)
        # update_data(message.from_user, message.chat, is_six=(dice_msg.dice.value == 6))
        
        time.sleep(3.5)
        res_msg = bot.send_message(chat_id, f"🎯 {message.from_user.first_name}, випало: {dice_msg.dice.value}!")
        delete_after(chat_id, res_msg.message_id)

    elif text == "🏆 ТОП цієї групи":
        delete_after(chat_id, message.message_id)
        msg = bot.send_message(chat_id, get_top_text(chat_id), parse_mode="Markdown")
        delete_after(chat_id, msg.message_id)

    elif text == "📊 Статистика групи":
        delete_after(chat_id, message.message_id)
        msg = bot.send_message(chat_id, get_stats_text(chat_id), parse_mode="Markdown")
        delete_after(chat_id, msg.message_id)

# Веб-сервер для Render
@app.route('/')
def home(): return "Бот працює!"

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))).start()
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
