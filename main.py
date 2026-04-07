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

# --- РОБОТА З БАЗОЮ ДАНИХ ---
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
                last_roll = CURRENT_TIMESTAMP, 
                username = EXCLUDED.username,
                chat_name = EXCLUDED.chat_name,
                sixes_count = group_stats.sixes_count + EXCLUDED.sixes_count;
        """, (user.id, chat.id, c_name, u_name, 1 if is_six else 0))
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        print(f"Помилка оновлення БД: {e}")

def get_top_text(chat_id):
    try:
        conn = psycopg2.connect(dsn=DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT username, sixes_count FROM group_stats WHERE chat_id = %s AND sixes_count > 0 ORDER BY sixes_count DESC LIMIT 10", (chat_id,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        
        if not rows:
            return "🏆 **ТОП ГРУПИ:**\n\nПоки що ніхто не вибив 6! 🎲"
        
        text = "🏆 **ТОП ГРУПИ (шістки):**\n\n"
        for i, row in enumerate(rows):
            text += f"{i+1}. {row[0]} — 🔥 `{row[1]}`\n"
        return text
    except Exception as e:
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

# --- ОБРОБНИКИ ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    update_data(message.from_user, message.chat)
    msg = bot.send_message(message.chat.id, "🎰 Бот активовано! Грай кнопками знизу:", reply_markup=get_main_keyboard())
    delete_after(message.chat.id, message.message_id)
    delete_after(message.chat.id, msg.message_id)

@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    chat_id = message.chat.id
    text = message.text

    if text == "🎲 Кинути кубик":
        delete_after(chat_id, message.message_id)
        dice_msg = bot.send_dice(chat_id)
        delete_after(chat_id, dice_msg.message_id)
        
        # Оновлюємо статистику
        update_data(message.from_user, message.chat, is_six=(dice_msg.dice.value == 6))
        
        time.sleep(3.5)
        res_text = f"🎯 {message.from_user.first_name}, випало: {dice_msg.dice.value}!"
        res_msg = bot.send_message(chat_id, res_text)
        delete_after(chat_id, res_msg.message_id)

    elif text == "🏆 ТОП цієї групи":
        delete_after(chat_id, message.message_id)
        msg = bot.send_message(chat_id, get_top_text(chat_id), parse_mode="Markdown")
        delete_after(chat_id, msg.message_id)

    elif text == "📊 Статистика групи":
        delete_after(chat_id, message.message_id)
        try:
            conn = psycopg2.connect(dsn=DATABASE_URL)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM group_stats WHERE chat_id = %s", (chat_id,))
            total = cur.fetchone()[0]
            cur.close(); conn.close()
            msg = bot.send_message(chat_id, f"📊 **У цій групі:** `{total}` гравців.", parse_mode="Markdown")
            delete_after(chat_id, msg.message_id)
        except: pass

@app.route('/')
def home(): return "OK"

if __name__ == "__main__":
    # Ініціалізація БД (на всяк випадок)
    try:
        c = psycopg2.connect(dsn=DATABASE_URL)
        cur = c.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS group_stats (user_id BIGINT, chat_id BIGINT, chat_name TEXT, username TEXT, sixes_count INTEGER DEFAULT 0, last_roll TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (user_id, chat_id));")
        c.commit(); cur.close(); c.close()
    except: pass
    
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))).start()
    bot.infinity_polling()
