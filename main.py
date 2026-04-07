import telebot
import os
import time
import psycopg2
from psycopg2 import pool
import threading
from telebot import types
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta

# --- НАЛАШТУВАННЯ ---
TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_ID = 8309122402  # Твій ID

bot = telebot.TeleBot(TOKEN)
app = Flask('')

@app.route('/')
def home():
    return "Бот працює та онлайн!"

admin_states = {}

# --- 1. ПУЛ З'ЄДНАНЬ ТА БЕЗПЕЧНЕ ОНОВЛЕННЯ БД ---
try:
    db_pool = psycopg2.pool.ThreadedConnectionPool(1, 20, dsn=DATABASE_URL)
    conn = db_pool.getconn()
    cur = conn.cursor()
    
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
            last_bonus TIMESTAMP DEFAULT '1970-01-01 00:00:00',
            PRIMARY KEY (user_id, chat_id)
        );
    """)
    
    # Додавання нових колонок, якщо їх немає
    columns = [
        ("count_1", "INTEGER DEFAULT 0"), ("count_2", "INTEGER DEFAULT 0"),
        ("count_3", "INTEGER DEFAULT 0"), ("count_4", "INTEGER DEFAULT 0"),
        ("count_5", "INTEGER DEFAULT 0"), ("count_6", "INTEGER DEFAULT 0"),
        ("xp", "INTEGER DEFAULT 0"), ("last_bonus", "TIMESTAMP DEFAULT '1970-01-01 00:00:00'")
    ]
    for col_name, col_type in columns:
        try:
            cur.execute(f"ALTER TABLE group_stats ADD COLUMN {col_name} {col_type};")
            conn.commit()
        except:
            conn.rollback()

    cur.close()
    db_pool.putconn(conn)
    print("✅ База даних оновлена.")
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

# --- 3. АВТОВИДАЛЕННЯ ---
def delete_after(chat_id, message_id, delay=60):
    def delayed_delete():
        try:
            time.sleep(delay)
            bot.delete_message(chat_id, message_id)
        except: pass
    threading.Thread(target=delayed_delete, daemon=True).start()

# --- 4. ЛОГІКА ЗАПИСУ ---
def update_data(user, chat, dice_value):
    conn = None
    try:
        conn = get_db_connection(); cur = conn.cursor()
        u_name = user.username if user.username else user.first_name
        c_name = chat.title if chat.title else "Особисті"
        
        xp_gain = 15 if dice_value == 6 else (5 if dice_value > 0 else 0)
        col_name = f"count_{dice_value}" if dice_value > 0 else "count_1"

        if dice_value > 0:
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
        else:
            cur.execute("""
                INSERT INTO group_stats (user_id, chat_id, chat_name, username)
                VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING;
            """, (user.id, chat.id, c_name, u_name))
            
        conn.commit(); cur.close()
    except Exception as e: print(f"DB Error: {e}")
    finally:
        if conn: release_db_connection(conn)

# --- КЛАВІАТУРИ ---
def get_main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("🎲 Кинути кубик", "🎁 Бонус", "🏆 ТОП", "📊 Статистика")
    if int(user_id) == ADMIN_ID:
        markup.add("⚙️ АДМІН-МЕНЮ")
    return markup

# --- ОБРОБНИКИ ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    update_data(message.from_user, message.chat, 0)
    bot.send_message(
        message.chat.id, 
        "🎰 Привіт! Кидай кубик та заробляй XP!", 
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@bot.callback_query_handler(func=lambda call: True)
def admin_calls(call):
    if call.from_user.id != ADMIN_ID: return
    conn = get_db_connection(); cur = conn.cursor()
    
    if call.data == "adm_stats":
        cur.execute("SELECT COUNT(DISTINCT user_id), COUNT(DISTINCT chat_id), SUM(xp) FROM group_stats")
        u, c, x = cur.fetchone()
        bot.send_message(call.message.chat.id, f"📈 **Статистика:**\n👤 Юзерів: {u}\n👥 Чати: {c}\n⭐ XP: {x}")
    elif call.data == "adm_bc":
        admin_states[call.from_user.id] = "waiting_bc"
        bot.send_message(call.message.chat.id, "📢 Введіть текст розсилки:")
    elif call.data == "adm_give_xp":
        admin_states[call.from_user.id] = "waiting_xp"
        bot.send_message(call.message.chat.id, "🎁 Формат: `ID XP`")
    
    cur.close(); release_db_connection(conn)

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    uid, cid, text = message.from_user.id, message.chat.id, message.text

    # Захист адмін-панелі
    if text == "⚙️ АДМІН-МЕНЮ":
        if uid == ADMIN_ID:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📊 Статистика", callback_data="adm_stats"),
                       types.InlineKeyboardButton("📢 Розсилка", callback_data="adm_bc"),
                       types.InlineKeyboardButton("🎁 Дати XP", callback_data="adm_give_xp"))
            bot.send_message(cid, "🛠 Адмін-панель:", reply_markup=markup)
        else:
            bot.delete_message(cid, message.message_id) # Видалити спробу входу
        return

    # Логіка бонусів
    if text == "🎁 Бонус":
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT last_bonus FROM group_stats WHERE user_id = %s AND chat_id = %s", (uid, cid))
        res = cur.fetchone()
        
        if res and (datetime.now() - res[0]) < timedelta(hours=24):
            rem = timedelta(hours=24) - (datetime.now() - res[0])
            bot.send_message(cid, f"⏳ Зачекай ще {rem.seconds // 3600} год. { (rem.seconds // 60) % 60} хв.")
        else:
            import random
            bonus_xp = random.randint(20, 100)
            cur.execute("UPDATE group_stats SET xp = xp + %s, last_bonus = CURRENT_TIMESTAMP WHERE user_id = %s AND chat_id = %s", (bonus_xp, uid, cid))
            conn.commit()
            bot.send_message(cid, f"🎁 Твій щоденний бонус: +{bonus_xp} XP!")
        
        cur.close(); release_db_connection(conn)
        return

    # Гра
    if text == "🎲 Кинути кубик":
        d = bot.send_dice(cid)
        update_data(message.from_user, message.chat, d.dice.value)
        time.sleep(3.5)
        bot.send_message(cid, f"🎯 {message.from_user.first_name}, випало {d.dice.value}!")
        return

    # Статистика
    if "Статистика" in text:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT xp FROM group_stats WHERE user_id = %s AND chat_id = %s", (uid, cid))
        res = cur.fetchone()
        if res:
            bot.send_message(cid, f"👤 {message.from_user.first_name}\n🎖 Ранг: {get_rank(res[0])}\n⭐ XP: {res[0]}")
        cur.close(); release_db_connection(conn)
        return

    # Адмін-стани
    if uid == ADMIN_ID and uid in admin_states:
        state = admin_states.pop(uid)
        if state == "waiting_bc":
            bot.send_message(cid, "🚀 Розсилка запущена...")
            # Тут код розсилки...
        if state == "waiting_xp":
            try:
                t_id, amt = text.split()
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("UPDATE group_stats SET xp = xp + %s WHERE user_id = %s", (int(amt), int(t_id)))
                conn.commit(); cur.close(); release_db_connection(conn)
                bot.send_message(cid, "✅ Успішно!")
            except: bot.send_message(cid, "❌ Помилка")

# --- ЗАПУСК ---
if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))).start()
    bot.infinity_polling()
