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
ADMIN_ID = 8309122402  # Твій ID

bot = telebot.TeleBot(TOKEN)
app = Flask('')

# Сховища станів
admin_states = {}
banned_users = set()

# --- 1. ПУЛ З'ЄДНАНЬ ТА ОНОВЛЕННЯ СТРУКТУРИ БД ---
try:
    db_pool = psycopg2.pool.ThreadedConnectionPool(1, 20, dsn=DATABASE_URL)
    conn = db_pool.getconn()
    cur = conn.cursor()
    
    # ⚠️ УВАГА: Цей рядок видалить стару таблицю ОДИН РАЗ, щоб створити нову з XP та цифрами 1-6
    # Це виправить помилку, через яку ти не бачив статистику.
    cur.execute("DROP TABLE IF EXISTS group_stats CASCADE;")
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS group_stats (
            user_id BIGINT,
            chat_id BIGINT,
            chat_name TEXT,
            username TEXT,
            count_1 INTEGER DEFAULT 0,
            count_2 INTEGER DEFAULT 0,
            count_3 INTEGER DEFAULT 0,
            count_4 INTEGER DEFAULT 0,
            count_5 INTEGER DEFAULT 0,
            count_6 INTEGER DEFAULT 0,
            xp INTEGER DEFAULT 0,
            last_roll TIMESTAMP,
            PRIMARY KEY (user_id, chat_id)
        );
    """)
    conn.commit()
    cur.close()
    db_pool.putconn(conn)
    print("✅ Базу даних успішно оновлено! Тепер XP та цифри 1-6 доступні.")
except Exception as e:
    print(f"❌ Помилка БД: {e}")

def get_db_connection(): return db_pool.getconn()
def release_db_connection(conn): db_pool.putconn(conn)

# --- 2. СИСТЕМА РАНГІВ ---
def get_rank(xp):
    if xp < 100: return "🌱 Новачок"
    if xp < 300: return "🎲 Гравець"
    if xp < 700: return "🔥 Азартний"
    if xp < 1500: return "🏆 Майстер"
    if xp < 3000: return "💎 Еліта"
    return "👑 Легенда казино"

# --- 3. ПОКРАЩЕНЕ АВТОВИДАЛЕННЯ ---
def delete_after(chat_id, message_id, delay=120):
    def delayed_delete():
        try:
            time.sleep(delay)
            bot.delete_message(chat_id, message_id)
        except: pass
    threading.Thread(target=delayed_delete, daemon=True).start()

# --- 4. ЛОГІКА ЗАПИСУ ДАНИХ ---
def update_data(user, chat, dice_value):
    if user.id in banned_users: return
    conn = None
    try:
        conn = get_db_connection(); cur = conn.cursor()
        u_name = user.username if user.username else user.first_name
        c_name = chat.title if chat.title else "Особисті"
        
        xp_gain = 15 if dice_value == 6 else 5
        col_name = f"count_{dice_value}"

        cur.execute(f"""
            INSERT INTO group_stats (user_id, chat_id, chat_name, username, {col_name}, xp, last_roll)
            VALUES (%s, %s, %s, %s, 1, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, chat_id) DO UPDATE SET 
                {col_name} = group_stats.{col_name} + 1,
                xp = group_stats.xp + EXCLUDED.xp,
                username = EXCLUDED.username,
                chat_name = EXCLUDED.chat_name,
                last_roll = CURRENT_TIMESTAMP;
        """, (user.id, chat.id, c_name, u_name, xp_gain))
        conn.commit(); cur.close()
    except Exception as e: print(f"DB Error: {e}")
    finally:
        if conn: release_db_connection(conn)

# --- ФОНОВА РОЗСИЛКА ---
def run_broadcast(text, chat_ids):
    success = 0
    for cid in chat_ids:
        try:
            bot.send_message(cid, f"📢 **ОГОЛОШЕННЯ:**\n\n{text}", parse_mode="Markdown")
            success += 1
            time.sleep(0.05)
        except: continue
    try: bot.send_message(ADMIN_ID, f"✅ Розсилку завершено! Отримали: {success}")
    except: pass

# --- КЛАВІАТУРИ ---
def get_main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("🎲 Кинути кубик", "🏆 ТОП цієї групи", "📊 Моя статистика")
    if int(user_id) == ADMIN_ID:
        markup.add("⚙️ АДМІН-МЕНЮ")
    return markup

# --- ОБРОБНИК ПОВІДОМЛЕНЬ ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    update_data(message.from_user, message.chat, 0) # Ініціалізація
    bot.send_message(
        message.chat.id, 
        "🎰 Бот готовий до гри!", 
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@bot.callback_query_handler(func=lambda call: True)
def admin_calls(call):
    if call.from_user.id != ADMIN_ID: return
    conn = None
    try:
        conn = get_db_connection(); cur = conn.cursor()
        if call.data == "adm_bc":
            admin_states[call.from_user.id] = "waiting_bc"
            bot.send_message(call.message.chat.id, "📢 Введіть текст для розсилки:")
        elif call.data == "adm_reset":
            cur.execute("DELETE FROM group_stats")
            conn.commit()
            bot.send_message(call.message.chat.id, "✅ Статистику повністю очищено.")
        cur.close()
    except: pass
    finally:
        if conn: release_db_connection(conn)

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    uid, cid, text = message.from_user.id, message.chat.id, message.text
    if uid in banned_users: return

    # Адмін-панель
    if text == "⚙️ АДМІН-МЕНЮ":
        if uid == ADMIN_ID:
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(types.InlineKeyboardButton("📢 Розсилка", callback_data="adm_bc"),
                       types.InlineKeyboardButton("♻️ Скинути все", callback_data="adm_reset"))
            bot.send_message(cid, "🛠 Адмін-панель:", reply_markup=markup)
        else:
            bot.send_message(cid, "❌ Немає прав.", reply_markup=get_main_keyboard(uid))
        return

    if uid == ADMIN_ID and uid in admin_states:
        state = admin_states.pop(uid)
        if state == "waiting_bc":
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT DISTINCT chat_id FROM group_stats"); chats = cur.fetchall()
            cur.close(); release_db_connection(conn)
            threading.Thread(target=run_broadcast, args=(text, [c[0] for c in chats]), daemon=True).start()
            bot.send_message(cid, "🚀 Розсилка почалася...")
        return

    # Кнопки
    if text == "🎲 Кинути кубик":
        delete_after(cid, message.message_id, delay=0)
        d = bot.send_dice(cid)
        update_data(message.from_user, message.chat, d.dice.value)
        delete_after(cid, d.message_id, delay=120)
        time.sleep(3.5)
        res = bot.send_message(cid, f"🎯 {message.from_user.first_name}, випало: {d.dice.value}!")
        delete_after(cid, res.message_id, delay=120)

    elif "Моя статистика" in text:
        delete_after(cid, message.message_id, delay=0)
        conn = None
        try:
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT count_1, count_2, count_3, count_4, count_5, count_6, xp FROM group_stats WHERE user_id = %s AND chat_id = %s", (uid, cid))
            res = cur.fetchone()
            if res:
                c1, c2, c3, c4, c5, c6, xp = res
                rank = get_rank(xp)
                msg = bot.send_message(cid, f"👤 **Профіль:** {message.from_user.first_name}\n🎖 Ранг: `{rank}`\n⭐ Досвід: `{xp} XP`\n\n📊 **Цифри:**\n1️⃣ — `{c1}` | 2️⃣ — `{c2}` | 3️⃣ — `{c3}`\n4️⃣ — `{c4}` | 5️⃣ — `{c5}` | 6️⃣ — `{c6}` 🔥", parse_mode="Markdown")
                delete_after(cid, msg.message_id, delay=120)
            cur.close()
        finally:
            if conn: release_db_connection(conn)

    elif "ТОП" in text:
        delete_after(cid, message.message_id, delay=0)
        conn = None
        try:
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT username, xp, count_6 FROM group_stats WHERE chat_id = %s ORDER BY xp DESC LIMIT 10", (cid,))
            rows = cur.fetchall()
            if rows:
                out = "🏆 **ТОП ГРАВЦІВ ГРУПИ (за XP):**\n\n"
                for i, r in enumerate(rows):
                    out += f"{i+1}. {r[0]} — `{r[1]}` XP (🔥 {r[2]} шісток)\n"
                m = bot.send_message(cid, out, parse_mode="Markdown")
                delete_after(cid, m.message_id, delay=120)
            cur.close()
        finally:
            if conn: release_db_connection(conn)

# --- ЗАПУСК ---
@app.route('/')
def home(): return "OK"

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))), daemon=True).start()
    bot.infinity_polling()
