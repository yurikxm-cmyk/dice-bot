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
banned_users = set()

# --- ФУНКЦІЯ АВТОВИДАЛЕННЯ ---
def delete_after(chat_id, message_id, delay=120):
    def delayed_delete():
        time.sleep(delay)
        try: bot.delete_message(chat_id, message_id)
        except: pass
    threading.Thread(target=delayed_delete).start()

# --- РОБОТА З БАЗОЮ ДАНИХ ---
def update_data(user, chat, is_six=False):
    if user.id in banned_users: return
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
        types.InlineKeyboardButton("🏘 Список всіх груп", callback_data="adm_groups"),
        types.InlineKeyboardButton("📢 Розсилка у всі чати", callback_data="adm_bc"),
        types.InlineKeyboardButton("🎁 Роздати +5 шісток усім", callback_data="adm_gift"),
        types.InlineKeyboardButton("🚫 Забанити гравця (ID)", callback_data="adm_ban"),
        types.InlineKeyboardButton("♻️ Скинути місяць", callback_data="adm_reset")
    )
    return markup

# --- 1. ПРІОРИТЕТНА КОМАНДА START ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    update_data(message.from_user, message.chat)
    bot.send_message(
        message.chat.id, 
        "🎰 Бот готовий! Використовуй кнопки нижче для гри:", 
        reply_markup=get_main_keyboard(message.from_user.id)
    )

# --- 2. ОБРОБНИК CALLBACK (АДМІН-МЕНЮ) ---
@bot.callback_query_handler(func=lambda call: True)
def admin_calls(call):
    if call.from_user.id != ADMIN_ID: return
    try:
        conn = psycopg2.connect(dsn=DATABASE_URL)
        cur = conn.cursor()

        if call.data == "adm_stats":
            cur.execute("SELECT COUNT(DISTINCT user_id), SUM(sixes_count) FROM group_stats")
            u, s = cur.fetchone()
            bot.send_message(call.message.chat.id, f"🌐 **ГЛОБАЛЬНО:**\n👤 Гравців: `{u}`\n🔥 Шісток: `{s}`", parse_mode="Markdown")

        elif call.data == "adm_groups":
            cur.execute("SELECT chat_name, COUNT(user_id) FROM group_stats GROUP BY chat_name")
            groups = cur.fetchall()
            text = "🏘 **ГРУПИ ТА АКТИВНІСТЬ:**\n\n" + "\n".join([f"• {g[0]} — `{g[1]}` гравців" for g in groups])
            bot.send_message(call.message.chat.id, text)

        elif call.data == "adm_gift":
            cur.execute("UPDATE group_stats SET sixes_count = sixes_count + 5")
            conn.commit()
            bot.answer_callback_query(call.id, "🎁 +5 шісток нараховано кожному!", show_alert=True)

        elif call.data == "adm_bc":
            admin_states[call.from_user.id] = "waiting_bc"
            bot.send_message(call.message.chat.id, "📢 Введіть текст для розсилки:")

        elif call.data == "adm_ban":
            admin_states[call.from_user.id] = "waiting_ban"
            bot.send_message(call.message.chat.id, "🚫 Введіть ID гравця для бану:")

        elif call.data == "adm_reset":
            cur.execute("UPDATE group_stats SET sixes_count = 0")
            conn.commit()
            bot.edit_message_text("✅ Статистику місяця скинуто.", call.message.chat.id, call.message.message_id)

        cur.close(); conn.close()
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Помилка БД: {e}")

# --- 3. ОБРОБНИК ТЕКСТУ ТА КНОПОК ---
@bot.message_handler(func=lambda m: True)
def handle_all(message):
    uid, cid, text = message.from_user.id, message.chat.id, message.text
    if uid in banned_users: return

    # Логіка очікування тексту від адміна
    if uid == ADMIN_ID and uid in admin_states:
        state = admin_states.pop(uid)
        if state == "waiting_bc":
            try:
                conn = psycopg2.connect(dsn=DATABASE_URL); cur = conn.cursor()
                cur.execute("SELECT DISTINCT chat_id FROM group_stats"); chats = cur.fetchall()
                cur.close(); conn.close()
                for c in chats:
                    try: bot.send_message(c[0], f"📢 **ОГОЛОШЕННЯ:**\n\n{text}", parse_mode="Markdown")
                    except: pass
                bot.send_message(cid, "✅ Розсилку завершено.")
            except: bot.send_message(cid, "❌ Помилка бази при розсилці.")
        elif state == "waiting_ban":
            try: 
                banned_users.add(int(text))
                bot.send_message(cid, f"✅ Юзер `{text}` забанений (до перезапуску).")
            except: bot.send_message(cid, "❌ Помилка: введіть лише цифри ID.")
        return

    # Кнопки гравців
    if text == "🎲 Кинути кубик":
        delete_after(cid, message.message_id)
        d = bot.send_dice(cid)
        delete_after(cid, d.message_id)
        update_data(message.from_user, message.chat, is_six=(d.dice.value == 6))
        time.sleep(3.5)
        res = bot.send_message(cid, f"🎯 {message.from_user.first_name}, випало: {d.dice.value}!")
        delete_after(cid, res.message_id)

    elif "ТОП" in text:
        delete_after(cid, message.message_id)
        try:
            conn = psycopg2.connect(dsn=DATABASE_URL); cur = conn.cursor()
            cur.execute("SELECT username, sixes_count FROM group_stats WHERE chat_id = %s AND sixes_count > 0 ORDER BY sixes_count DESC LIMIT 10", (cid,))
            rows = cur.fetchall(); cur.close(); conn.close()
            if not rows: bot.send_message(cid, "🏆 Поки порожньо.")
            else:
                out = "🏆 **ТОП ГРУПИ:**\n\n" + "\n".join([f"{i+1}. {r[0]} — 🔥 `{r[1]}`" for i, r in enumerate(rows)])
                bot.send_message(cid, out, parse_mode="Markdown")
        except: bot.send_message(cid, "❌ Помилка при отриманні ТОПу.")

    elif "Статистика" in text:
        delete_after(cid, message.message_id)
        try:
            conn = psycopg2.connect(dsn=DATABASE_URL); cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM group_stats WHERE chat_id = %s", (cid,))
            total = cur.fetchone()[0]
            bot.send_message(cid, f"📊 У цій групі: `{total}` гравців.", parse_mode="Markdown")
            cur.close(); conn.close()
        except: pass

    elif text == "⚙️ АДМІН-МЕНЮ" and uid == ADMIN_ID:
        bot.send_message(cid, "🛠 **Адмін-центр керування:**", reply_markup=get_admin_inline_menu(), parse_mode="Markdown")

@app.route('/')
def home(): return "OK"

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))).start()
    bot.infinity_polling()
