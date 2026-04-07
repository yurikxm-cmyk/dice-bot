import telebot
import os
import time
import psycopg2
import threading
from telebot import types
from flask import Flask
from threading import Thread

# Налаштування (Render бере їх з Environment Variables)
TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_ID = 8765742454 

bot = telebot.TeleBot(TOKEN)
app = Flask('')

# --- ФУНКЦІЯ АВТОВИДАЛЕННЯ ---
def delete_after(chat_id, message_id, delay=120):
    def delayed_delete():
        time.sleep(delay)
        try:
            bot.delete_message(chat_id, message_id)
        except: pass
    threading.Thread(target=delayed_delete).start()

# --- ЛОГІКА БАЗИ ДАНИХ (СПІЛЬНА) ---
def get_db_connection():
    return psycopg2.connect(dsn=DATABASE_URL)

def get_top_text(chat_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT username, sixes_count FROM group_stats WHERE chat_id = %s AND sixes_count > 0 ORDER BY sixes_count DESC LIMIT 10", (chat_id,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        if not rows: return "Поки пусто."
        return "🏆 **ТОП ГРУПИ:**\n\n" + "\n".join([f"{i+1}. {r[0]} — {r[1]}" for i, r in enumerate(rows)])
    except Exception as e: return f"Помилка БД: {e}"

def get_stats_text(chat_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM group_stats WHERE chat_id = %s", (chat_id,))
        total = cur.fetchone()[0]
        cur.close(); conn.close()
        return f"📊 **У цій групі:** `{total}` гравців."
    except Exception as e: return f"Помилка БД: {e}"

# --- КЛАВІАТУРА ---
def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("🎲 Кинути кубик"), 
               types.KeyboardButton("🏆 ТОП цієї групи"), 
               types.KeyboardButton("📊 Статистика групи"))
    return markup

# --- ОБРОБНИК ТЕКСТОВИХ КНОПОК (НИЖНЯ ПАНЕЛЬ) ---
@bot.message_handler(func=lambda m: m.text in ["🎲 Кинути кубик", "🏆 ТОП цієї групи", "📊 Статистика групи"])
def handle_menu_text(message):
    chat_id = message.chat.id
    delete_after(chat_id, message.message_id) # Видаляємо команду юзера

    if message.text == "🎲 Кинути кубик":
        dice = bot.send_dice(chat_id)
        delete_after(chat_id, dice.message_id)
        # Оновлення даних (is_six = True якщо випало 6)
        from update_logic import update_data # Припускаємо, що update_data у тебе є
        update_data(message.from_user, message.chat, is_six=(dice.dice.value == 6))
        
        time.sleep(3.5)
        res = bot.send_message(chat_id, f"🎯 {message.from_user.first_name}, випало: {dice.dice.value}!")
        delete_after(chat_id, res.message_id)

    elif message.text == "🏆 ТОП цієї групи":
        msg = bot.send_message(chat_id, get_top_text(chat_id), parse_mode="Markdown")
        delete_after(chat_id, msg.message_id)

    elif message.text == "📊 Статистика групи":
        msg = bot.send_message(chat_id, get_stats_text(chat_id), parse_mode="Markdown")
        delete_after(chat_id, msg.message_id)

# --- ОБРОБНИК СТАРИХ INLINE-КНОПОК (ЩОБ ВОНИ ЗАПРАЦЮВАЛИ) ---
@bot.callback_query_handler(func=lambda call: True)
def handle_old_buttons(call):
    chat_id = call.message.chat.id
    if call.data == "view_top":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat_id, get_top_text(chat_id), parse_mode="Markdown")
        delete_after(chat_id, msg.message_id)
    elif call.data == "group_stats":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat_id, get_stats_text(chat_id), parse_mode="Markdown")
        delete_after(chat_id, msg.message_id)
    elif call.data == "roll_dice":
        bot.answer_callback_query(call.id)
        # Логіка кубика аналогічна текстовій
        dice = bot.send_dice(chat_id)
        delete_after(chat_id, dice.message_id)

# --- СТАРТ ---
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "🎰 Клавіатуру оновлено! Грай кнопками нижче.", reply_markup=get_main_keyboard())

# Веб-сервер для Render
@app.route('/')
def home(): return "Bot is running"

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))).start()
    bot.infinity_polling()
