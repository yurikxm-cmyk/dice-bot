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
ADMIN_ID = 8765742454  # Твій ID

bot = telebot.TeleBot(TOKEN)
app = Flask('')

# --- ФУНКЦІЯ ВИДАЛЕННЯ ---
def delete_after(chat_id, message_id, delay=120):
    def delayed_delete():
        time.sleep(delay)
        try:
            bot.delete_message(chat_id, message_id)
        except Exception:
            pass 
    threading.Thread(target=delayed_delete).start()

# --- БАЗА ДАНИХ ---
def init_db():
    try:
        conn = psycopg2.connect(dsn=DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS group_stats (
                user_id BIGINT,
                chat_id BIGINT,
                chat_name TEXT,
                username TEXT,
                sixes_count INTEGER DEFAULT 0,
                last_roll TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, chat_id)
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Помилка БД: {e}")

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
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Помилка оновлення: {e}")

# --- ВЕБ-СЕРВЕР ---
@app.route('/')
def home(): return "Бот активний!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- НИЖНЯ ПАНЕЛЬ (Reply Keyboard) ---
def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    # Кнопки текстом, які з'являться замість звичайної клавіатури
    markup.add(
        types.KeyboardButton("🎲 Кинути кубик"),
        types.KeyboardButton("🏆 ТОП цієї групи"),
        types.KeyboardButton("📊 Статистика групи")
    )
    return markup

# --- АДМІН-КНОПКА (Inline) ---
def get_admin_inline():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⚙️ АДМІН: Глобальна інфо", callback_data="admin_global"))
    return markup

# --- ОБРОБКА КОМАНДИ /START ---
@bot.message_handler(commands=['start'])
def welcome(message):
    update_data(message.from_user, message.chat)
    # Важливо: відправляємо reply_markup=get_main_keyboard(), щоб замінити інлайн-кнопки на нижню панель
    msg = bot.send_message(
        message.chat.id, 
        "🎰 Бот активовано! Тепер кнопки знаходяться внизу, де зазвичай клавіатура.", 
        reply_markup=get_main_keyboard()
    )
    delete_after(message.chat.id, message.message_id)
    delete_after(message.chat.id, msg.message_id)
    
    if message.from_user.id == ADMIN_ID:
        bot.send_message(message.chat.id, "Доступ адміна:", reply_markup=get_admin_inline())

# --- ОБРОБКА КНОПОК З НИЖНЬОЇ ПАНЕЛІ ---
@bot.message_handler(func=lambda m: m.text in ["🎲 Кинути кубик", "🏆 ТОП цієї групи", "📊 Статистика групи"])
def handle_menu(message):
    chat_id = message.chat.id
    
    # Видаляємо повідомлення юзера через 2 хв
    delete_after(chat_id, message.message_id)

    if message.text == "🎲 Кинути кубик":
        dice_msg = bot.send_dice(chat_id)
        delete_after(chat_id, dice_msg.message_id)
        
        is_six = (dice_msg.dice.value == 6)
        update_data(message.from_user, message.chat, is_six=is_six)
        
        time.sleep(3.5)
        res_text = f"🎯 {message.from_user.first_name}, випало: {dice_msg.dice.value}!"
        res_msg = bot.send_message(chat_id, res_text)
        delete_after(chat_id, res_msg.message_id)

    elif message.text == "🏆 ТОП цієї групи":
        conn = psycopg2.connect(dsn=DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT username, sixes_count FROM group_stats WHERE chat_id = %s AND sixes_count > 0 ORDER BY sixes_count DESC LIMIT 10", (chat_id,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        
        text = "🏆 **ТОП ГРУПИ:**\n\n" + "\n".join([f"{i+1}. {r[0]} — {r[1]}" for i, r in enumerate(rows)]) if rows else "Поки пусто."
        msg = bot.send_message(chat_id, text, parse_mode="Markdown")
        delete_after(chat_id, msg.message_id)

    elif message.text == "📊 Статистика групи":
        conn = psycopg2.connect(dsn=DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM group_stats WHERE chat_id = %s", (chat_id,))
        total = cur.fetchone()[0]
        cur.close(); conn.close()
        msg = bot.send_message(chat_id, f"📊 **У цій групі:** `{total}` гравців.", parse_mode="Markdown")
        delete_after(chat_id, msg.message_id)

# --- CALLBACK ДЛЯ АДМІНА ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_global")
def admin_query(call):
    if call.from_user.id == ADMIN_ID:
        conn = psycopg2.connect(dsn=DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(DISTINCT user_id) FROM group_stats")
        total_users = cur.fetchone()[0]
        cur.execute("SELECT chat_name, COUNT(user_id) FROM group_stats GROUP BY chat_name")
        groups = cur.fetchall()
        cur.close(); conn.close()
        
        text = f"🌐 **ГЛОБАЛЬНА СТАТИСТИКА**\n👤 Всього юзерів: `{total_users}`\n\n🏘 **Список груп:**\n"
        for g_name, count in groups:
            text += f"• {g_name}: `{count}` гравців\n"
        
        bot.send_message(call.message.chat.id, text, parse_mode="Markdown")
        bot.answer_callback_query(call.id)

if __name__ == "__main__":
    init_db()
    Thread(target=run_web_server).start()
    bot.infinity_polling()
