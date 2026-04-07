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
ADMIN_ID = 8309122402  # Твій ID

bot = telebot.TeleBot(TOKEN)
app = Flask('')

# Сховища станів
admin_states = {}
banned_users = set() # Можна розширити до БД, але поки в пам'яті

def delete_after(chat_id, message_id, delay=120):
    def delayed_delete():
        time.sleep(delay)
        try: bot.delete_message(chat_id, message_id)
        except: pass
    threading.Thread(target=delayed_delete).start()

# --- РОБОТА З БД ---
def update_data(user, chat, is_six=False):
    if user.id in banned_users: return # Ігноруємо забанених
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

# --- КЛАВІАТУРИ ---
def get_main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("🎲 Кинути кубик", "🏆 ТОП цієї групи", "📊 Статистика групи")
    if user_id == ADMIN_ID:
        markup.add("⚙️ АДМІН-МЕНЮ")
    return markup

def get_admin_inline_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🌐 Глобальна статистика", callback_data="adm_stats"),
        types.InlineKeyboardButton("🎁 Роздати +5 шісток усім", callback_data="adm_gift"),
        types.InlineKeyboardButton("🚫 Забанити гравця (ID)", callback_data="adm_ban"),
        types.InlineKeyboardButton("🏘 Список груп", callback_data="adm_groups"),
        types.InlineKeyboardButton("📢 Розсилка", callback_data="adm_bc"),
        types.InlineKeyboardButton("ℹ️ Інфо про цей чат", callback_data="adm_chat_info"),
        types.InlineKeyboardButton("♻️ Скинути місяць", callback_data="adm_reset")
    )
    return markup

# --- ОБРОБНИКИ АДМІН-КНОПОК ---
@bot.callback_query_handler(func=lambda call: True)
def admin_calls(call):
    if call.from_user.id != ADMIN_ID: return
    
    conn = psycopg2.connect(dsn=DATABASE_URL)
    cur = conn.cursor()

    if call.data == "adm_stats":
        cur.execute("SELECT COUNT(DISTINCT user_id), SUM(sixes_count) FROM group_stats")
        u, s = cur.fetchone()
        bot.send_message(call.message.chat.id, f"🌐 **Глобально:**\n👤 Юзерів: `{u}`\n🔥 Шісток: `{s}`", parse_mode="Markdown")

    elif call.data == "adm_gift":
        cur.execute("UPDATE group_stats SET sixes_count = sixes_count + 5")
        conn.commit()
        bot.answer_callback_query(call.id, "🎁 Подаровано +5 шісток усім гравцям!", show_alert=True)

    elif call.data == "adm_ban":
        admin_states[call.from_user.id] = "waiting_for_ban_id"
        bot.send_message(call.message.chat.id, "🚫 Введіть ID користувача для бану:")

    elif call.data == "adm_chat_info":
        info = f"📍 **Чат:** {call.message.chat.title}\n🆔 **ID:** `{call.message.chat.id}`"
        bot.send_message(call.message.chat.id, info, parse_mode="Markdown")

    elif call.data == "adm_bc":
        admin_states[call.from_user.id] = "waiting_bc"
        bot.send_message(call.message.chat.id, "📢 Введіть текст розсилки:")

    elif call.data == "adm_reset":
        cur.execute("UPDATE group_stats SET sixes_count = 0")
        conn.commit()
        bot.edit_message_text("✅ Статистику оновлено на новий місяць.", call.message.chat.id, call.message.message_id)

    cur.close(); conn.close()

# --- ГОЛОВНИЙ ОБРОБНИК ---
@bot.message_handler(func=lambda m: True)
def handle_all(message):
    uid = message.from_user.id
    cid = message.chat.id
    if uid in banned_users: return

    # Логіка станів адміна
    if uid == ADMIN_ID and uid in admin_states:
        state = admin_states[uid]
        del admin_states[uid]
        
        if state == "waiting_for_ban_id":
            try:
                target = int(message.text)
                banned_users.add(target)
                bot.send_message(cid, f"✅ Користувача `{target}` забанено.")
            except: bot.send_message(cid, "❌ Невірний ID.")
        
        elif state == "waiting_bc":
            # Тут логіка розсилки, яку ми писали раніше
            bot.send_message(cid, "🚀 Розсилку запущено...")
        return

    # Кнопки меню
    if message.text == "🎲 Кинути кубик":
        delete_after(cid, message.message_id)
        d = bot.send_dice(cid)
        delete_after(cid, d.message_id)
        update_data(message.from_user, message.chat, is_six=(d.dice.value == 6))
        time.sleep(3.5)
        res = bot.send_message(cid, f"🎯 {message.from_user.first_name}, випало: {d.dice.value}!")
        delete_after(cid, res.message_id)

    elif "ТОП" in message.text:
        delete_after(cid, message.message_id)
        # ... логіка ТОПу ...
        pass

    elif "АДМІН-МЕНЮ" in message.text and uid == ADMIN_ID:
        bot.send_message(cid, "🛠 **Панель керування:**", reply_markup=get_admin_inline_menu(), parse_mode="Markdown")

# Лог додавання в нову групу
@bot.my_chat_member_handler()
def on_join(message):
    if message.new_chat_member.status == "member":
        bot.send_message(ADMIN_ID, f"🆕 **Бота додано в групу:**\n🏘 {message.chat.title}\n🆔 `{message.chat.id}`")

@app.route('/')
def home(): return "OK"

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))).start()
    bot.infinity_polling()
