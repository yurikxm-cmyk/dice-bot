import telebot
import os
import time
import psycopg2
import threading
from telebot import types
from flask import Flask
from threading import Thread

# --- НАЛАШТУВАННЯ ---
TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_ID = 8309122402  # Твій актуальний ID

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
    except Exception as e: print(f"DB Update Error: {e}")

# --- КОМАНДИ ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    update_data(message.from_user, message.chat)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("🎲 Кинути кубик", "🏆 ТОП цієї групи", "📊 Статистика групи")
    
    bot.send_message(message.chat.id, "🎰 Бот готовий! Грай кнопками знизу:", reply_markup=markup)
    
    # ПЕРЕВІРКА НА АДМІНА
    if message.from_user.id == ADMIN_ID:
        admin_markup = types.InlineKeyboardMarkup()
        admin_markup.add(types.InlineKeyboardButton("♻️ Скинути статистику (Місяць)", callback_data="reset_month_confirm"))
        bot.send_message(message.chat.id, "⚙️ **АДМІН-ПАНЕЛЬ АКТИВНА**", reply_markup=admin_markup, parse_mode="Markdown")

@bot.message_handler(commands=['my_id'])
def my_id_cmd(message):
    bot.reply_to(message, f"Твій ID: `{message.from_user.id}`")

# --- ОБРОБКА КНОПКИ СКИНУТИ (АДМІН) ---
@bot.callback_query_handler(func=lambda call: call.data == "reset_month_confirm")
def admin_callback(call):
    if call.from_user.id == ADMIN_ID:
        try:
            conn = psycopg2.connect(dsn=DATABASE_URL)
            cur = conn.cursor()
            cur.execute("UPDATE group_stats SET sixes_count = 0;")
            conn.commit()
            cur.close(); conn.close()
            bot.answer_callback_query(call.id, "Статистику обнулено!", show_alert=True)
            bot.edit_message_text("✅ Всі результати успішно скинуто на новий місяць.", call.message.chat.id, call.message.message_id)
        except Exception as e:
            bot.answer_callback_query(call.id, f"Помилка: {e}")
    else:
        bot.answer_callback_query(call.id, "У вас немає прав!", show_alert=True)

# --- ОБРОБНИК ТЕКСТОВИХ КНОПОК ---
@bot.message_handler(func=lambda m: True)
def handle_all_text(message):
    chat_id = message.chat.id
    text = message.text if message.text else ""

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

@app.route('/')
def home(): return "OK"

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))).start()
    bot.infinity_polling()
