import telebot
import os
import time
import psycopg2
from psycopg2 import pool
import threading
from telebot import types
from flask import Flask
from threading import Thread

# --- НАЛАШТУВАННЯ ---
TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_ID = 8309122402

bot = telebot.TeleBot(TOKEN)
app = Flask('')

# Сховища станів
admin_states = {}
banned_users = set()

# --- 1. ПУЛ З'ЄДНАНЬ (Оптимізація БД) ---
try:
    db_pool = psycopg2.pool.ThreadedConnectionPool(1, 20, dsn=DATABASE_URL)
    print("✅ Пул з'єднань успішно створено")
except Exception as e:
    print(f"❌ Помилка БД: {e}")
    exit(1)

def get_db_connection():
    return db_pool.getconn()

def release_db_connection(conn):
    db_pool.putconn(conn)

# --- 2. ПОКРАЩЕНЕ АВТОВИДАЛЕННЯ ---
def delete_after(chat_id, message_id, delay=120):
    def delayed_delete():
        try:
            time.sleep(delay)
            bot.delete_message(chat_id, message_id)
        except:
            pass # Ігноруємо, якщо повідомлення вже видалене або немає прав
    threading.Thread(target=delayed_delete, daemon=True).start()

# --- РОБОТА З БД ---
def update_data(user, chat, is_six=False):
    if user.id in banned_users: return
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        u_name = user.username if user.username else user.first_name
        c_name = chat.title if chat.title else "Особисті"
        cur.execute("""
            INSERT INTO group_stats (user_id, chat_id, chat_name, username, sixes_count, last_roll)
            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, chat_id) DO UPDATE SET 
                last_roll = CURRENT_TIMESTAMP, username = EXCLUDED.username,
                chat_name = EXCLUDED.chat_name, 
                sixes_count = group_stats.sixes_count + EXCLUDED.sixes_count;
        """, (user.id, chat.id, c_name, u_name, 1 if is_six else 0))
        conn.commit()
        cur.close()
    except Exception as e:
        print(f"DB Error: {e}")
    finally:
        if conn: release_db_connection(conn)

# --- ФОНОВА РОЗСИЛКА ---
def run_broadcast(text, chat_ids):
    success = 0
    for cid in chat_ids:
        try:
            bot.send_message(cid[0], f"📢 **ОГОЛОШЕННЯ:**\n\n{text}", parse_mode="Markdown")
            success += 1
            time.sleep(0.05)
        except:
            continue
    try: bot.send_message(ADMIN_ID, f"✅ Розсилку завершено! Доставлено: {success}")
    except: pass

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

# --- КОМАНДИ ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    update_data(message.from_user, message.chat)
    bot.send_message(
        message.chat.id, 
        "🎰 Бот готовий! Використовуй кнопки нижче для гри:", 
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@bot.callback_query_handler(func=lambda call: True)
def admin_calls(call):
    if call.from_user.id != ADMIN_ID: return
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        if call.data == "adm_stats":
            cur.execute("SELECT COUNT(DISTINCT user_id), SUM(sixes_count) FROM group_stats")
            u, s = cur.fetchone()
            bot.send_message(call.message.chat.id, f"🌐 **ГЛОБАЛЬНО:**\n👤 Гравців: `{u}`\n🔥 Шісток: `{s}`", parse_mode="Markdown")
        elif call.data == "adm_groups":
            cur.execute("SELECT chat_name, COUNT(user_id) FROM group_stats GROUP BY chat_name")
            groups = cur.fetchall()
            text = "🏘 **ГРУПИ:**\n\n" + "\n".join([f"• {g[0]} — `{g[1]}` гравців" for g in groups])
            bot.send_message(call.message.chat.id, text)
        elif call.data == "adm_gift":
            cur.execute("UPDATE group_stats SET sixes_count = sixes_count + 5")
            conn.commit()
            bot.answer_callback_query(call.id, "🎁 +5 шісток усім!", show_alert=True)
        elif call.data == "adm_bc":
            admin_states[call.from_user.id] = "waiting_bc"
            bot.send_message(call.message.chat.id, "📢 Введіть текст для розсилки:")
        elif call.data == "adm_ban":
            admin_states[call.from_user.id] = "waiting_ban"
            bot.send_message(call.message.chat.id, "🚫 ID для бану:")
        elif call.data == "adm_reset":
            cur.execute("UPDATE group_stats SET sixes_count = 0")
            conn.commit()
            bot.edit_message_text("✅ Статистику скинуто.", call.message.chat.id, call.message.message_id)
        cur.close()
    except Exception as e: print(f"DB Error: {e}")
    finally:
        if conn: release_db_connection(conn)

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    uid, cid, text = message.from_user.id, message.chat.id, message.text
    if uid in banned_users: return

    # Адмін-логіка
    if uid == ADMIN_ID and uid in admin_states:
        state = admin_states.pop(uid)
        if state == "waiting_bc":
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT DISTINCT chat_id FROM group_stats"); chats = cur.fetchall()
            cur.close(); release_db_connection(conn)
            threading.Thread(target=run_broadcast, args=(text, chats), daemon=True).start()
            bot.send_message(cid, "🚀 Розсилка почалася...")
        elif state == "waiting_ban":
            try: banned_users.add(int(text)); bot.send_message(cid, f"✅ `{text}` забанений.")
            except: bot.send_message(cid, "❌ Тільки цифри!")
        return

    # Кнопки гравців
    if text == "🎲 Кинути кубик":
        delete_after(cid, message.message_id, delay=0)
        dice_msg = bot.send_dice(cid)
        delete_after(cid, dice_msg.message_id, delay=120)
        
        update_data(message.from_user, message.chat, is_six=(dice_msg.dice.value == 6))
        
        time.sleep(3.5)
        res_msg = bot.send_message(cid, f"🎯 {message.from_user.first_name}, випало: {dice_msg.dice.value}!")
        delete_after(cid, res_msg.message_id, delay=120)

    elif "ТОП" in text:
        delete_after(cid, message.message_id, delay=0)
        conn = None
        try:
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT username, sixes_count FROM group_stats WHERE chat_id = %s AND sixes_count > 0 ORDER BY sixes_count DESC LIMIT 10", (cid,))
            rows = cur.fetchall(); cur.close()
            if not rows: bot.send_message(cid, "🏆 Поки порожньо.")
            else:
                out = "🏆 **ТОП ГРУПИ:**\n\n" + "\n".join([f"{i+1}. {r[0]} — 🔥 `{r[1]}`" for i, r in enumerate(rows)])
                res = bot.send_message(cid, out, parse_mode="Markdown")
                delete_after(cid, res.message_id, delay=120)
        finally:
            if conn: release_db_connection(conn)

    elif "Статистика" in text:
        delete_after(cid, message.message_id, delay=0)
        conn = None
        try:
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM group_stats WHERE chat_id = %s", (cid,))
            total = cur.fetchone()[0]
            cur.close()
            res = bot.send_message(cid, f"📊 У цій групі: `{total}` гравців.", parse_mode="Markdown")
            delete_after(cid, res.message_id, delay=120)
        except: pass
        finally:
            if conn: release_db_connection(conn)

    elif text == "⚙️ АДМІН-МЕНЮ" and uid == ADMIN_ID:
        bot.send_message(cid, "🛠 Адмін-панель:", reply_markup=get_admin_inline_menu())

@app.route('/')
def home(): return "Бот працює!"

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))), daemon=True).start()
    print("🤖 Бот запущений!")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
