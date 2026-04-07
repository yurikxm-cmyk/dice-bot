import telebot
import os
import time
import psycopg2
import threading
from telebot import types
from flask import Flask
from threading import Thread

TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_ID = 8765742454 

bot = telebot.TeleBot(TOKEN)
app = Flask('')

def delete_after(chat_id, message_id, delay=120):
    def delayed_delete():
        time.sleep(delay)
        try: bot.delete_message(chat_id, message_id)
        except: pass
    threading.Thread(target=delayed_delete).start()

def update_data(user, chat, is_six=False):
    try:
        conn = psycopg2.connect(dsn=DATABASE_URL)
        cur = conn.cursor()
        u_name = user.username if user.username else user.first_name
        c_name = chat.title if chat.title else "Особисті повідомлення"
        cur.execute("""
            INSERT INTO group_stats (user_id, chat_id, chat_name, username, sixes_count, last_roll)
            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, chat_id) DO UPDATE SET 
                last_roll = CURRENT_TIMESTAMP, username = EXCLUDED.username,
                chat_name = EXCLUDED.chat_name, sixes_count = group_stats.sixes_count + EXCLUDED.sixes_count;
        """, (user.id, chat.id, c_name, u_name, 1 if is_six else 0))
        conn.commit()
        cur.close(); conn.close()
    except Exception as e: print(f"DB Error: {e}")

# --- ГОЛОВНА ЛОГІКА ---
@bot.message_handler(func=lambda m: True)
def handle_all(message):
    chat_id = message.chat.id
    text = message.text if message.text else ""

    # Перевірка через "in", щоб обійти цитування
    if "Кинути кубик" in text:
        delete_after(chat_id, message.message_id)
        dice = bot.send_dice(chat_id)
        delete_after(chat_id, dice.message_id)
        update_data(message.from_user, message.chat, is_six=(dice.dice.value == 6))
        time.sleep(3.5)
        res = bot.send_message(chat_id, f"🎯 {message.from_user.first_name}, випало: {dice.dice.value}!")
        delete_after(chat_id, res.message_id)

    elif "ТОП" in text:
        delete_after(chat_id, message.message_id)
        try:
            conn = psycopg2.connect(dsn=DATABASE_URL)
            cur = conn.cursor()
            cur.execute("SELECT username, sixes_count FROM group_stats WHERE chat_id = %s AND sixes_count > 0 ORDER BY sixes_count DESC LIMIT 10", (chat_id,))
            rows = cur.fetchall()
            cur.close(); conn.close()
            
            if not rows:
                bot.send_message(chat_id, "🏆 **ТОП ГРУПИ:**\n\nПоки порожньо.")
            else:
                res_text = "🏆 **ТОП ГРУПИ (шістки):**\n\n"
                for i, r in enumerate(rows):
                    res_text += f"{i+1}. {r[0]} — 🔥 `{r[1]}`\n"
                bot.send_message(chat_id, res_text, parse_mode="Markdown")
        except Exception as e: bot.send_message(chat_id, f"Помилка БД: {e}")

    elif "Статистика" in text:
        delete_after(chat_id, message.message_id)
        try:
            conn = psycopg2.connect(dsn=DATABASE_URL)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM group_stats WHERE chat_id = %s", (chat_id,))
            total = cur.fetchone()[0]
            cur.close(); conn.close()
            bot.send_message(chat_id, f"📊 **У цій групі:** `{total}` гравців.", parse_mode="Markdown")
        except: pass

@bot.message_handler(commands=['start'])
def start_cmd(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🎲 Кинути кубик", "🏆 ТОП цієї групи", "📊 Статистика групи")
    bot.send_message(message.chat.id, "🎰 Бот оновлений!", reply_markup=markup)

@app.route('/')
def home(): return "OK"

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))).start()
    bot.infinity_polling()
