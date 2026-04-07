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

# Сховище станів для адміна (щоб бот знав, що ми пишемо текст розсилки)
admin_states = {}

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
        types.InlineKeyboardButton("🌐 Глобальна статистика", callback_data="admin_global_stats"),
        types.InlineKeyboardButton("🏘 Список всіх груп", callback_data="admin_list_groups"),
        types.InlineKeyboardButton("📢 Розсилка у всі групи", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("♻️ Скинути статистику (Місяць)", callback_data="reset_month_confirm")
    )
    return markup

# --- КОМАНДИ ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    update_data(message.from_user, message.chat)
    bot.send_message(message.chat.id, "🎰 Бот готовий!", reply_markup=get_main_keyboard(message.from_user.id))

# --- ОБРОБНИК CALLBACK (Адмін-меню) ---
@bot.callback_query_handler(func=lambda call: True)
def handle_admin_callbacks(call):
    if call.from_user.id != ADMIN_ID: return
    
    conn = psycopg2.connect(dsn=DATABASE_URL)
    cur = conn.cursor()

    if call.data == "admin_global_stats":
        cur.execute("SELECT COUNT(DISTINCT user_id), SUM(sixes_count) FROM group_stats")
        data = cur.fetchone()
        bot.send_message(call.message.chat.id, f"🌐 **ГЛОБАЛЬНА СТАТИСТИКА:**\n\n👤 Гравців: `{data[0]}`\n🔥 Всього шісток: `{data[1]}`", parse_mode="Markdown")

    elif call.data == "admin_list_groups":
        cur.execute("SELECT DISTINCT chat_name FROM group_stats")
        groups = cur.fetchall()
        text = "🏘 **Групи, де є бот:**\n\n" + "\n".join([f"• {g[0]}" for g in groups])
        bot.send_message(call.message.chat.id, text)

    elif call.data == "admin_broadcast":
        admin_states[call.from_user.id] = "waiting_for_broadcast_text"
        bot.send_message(call.message.chat.id, "📢 **Надішли текст для розсилки:**\n(Це повідомлення отримають усі групи)")

    elif call.data == "reset_month_confirm":
        cur.execute("UPDATE group_stats SET sixes_count = 0;")
        conn.commit()
        bot.answer_callback_query(call.id, "Статистику обнулено!", show_alert=True)
        bot.edit_message_text("✅ Результати місяця успішно скинуто.", call.message.chat.id, call.message.message_id)

    cur.close(); conn.close()

# --- ЗАГАЛЬНИЙ ОБРОБНИК ТЕКСТУ ---
@bot.message_handler(func=lambda m: True)
def handle_text(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text

    # ПЕРЕВІРКА: ЧИ ЦЕ ТЕКСТ РОЗСИЛКИ?
    if user_id in admin_states and admin_states[user_id] == "waiting_for_broadcast_text":
        del admin_states[user_id] # Скидаємо стан
        try:
            conn = psycopg2.connect(dsn=DATABASE_URL)
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT chat_id FROM group_stats")
            chats = cur.fetchall()
            cur.close(); conn.close()
            
            success_count = 0
            for chat in chats:
                try:
                    bot.send_message(chat[0], f"📢 **ОГОЛОШЕННЯ ВІД АДМІНІСТРАЦІЇ:**\n\n{text}", parse_mode="Markdown")
                    success_count += 1
                except: continue
            
            bot.send_message(chat_id, f"✅ Розсилку завершено! Отримали: `{success_count}` чатів.")
        except Exception as e:
            bot.send_message(chat_id, f"❌ Помилка розсилки: {e}")
        return

    # ЗВИЧАЙНІ КНОПКИ
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
                res_t = "🏆 **ТОП ГРУПИ (шістки):**\n\n"
                for i, r in enumerate(rows):
                    res_t += f"{i+1}. {r[0]} — 🔥 `{r[1]}`\n"
                bot.send_message(chat_id, res_t, parse_mode="Markdown")
        except: pass

    elif "Статистика групи" in text:
        delete_after(chat_id, message.message_id)
        try:
            conn = psycopg2.connect(dsn=DATABASE_URL)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM group_stats WHERE chat_id = %s", (chat_id,))
            total = cur.fetchone()
            cur.close(); conn.close()
            bot.send_message(chat_id, f"📊 **У цій групі:** `{total[0]}` гравців.", parse_mode="Markdown")
        except: pass

    elif "АДМІН-МЕНЮ" in text and user_id == ADMIN_ID:
        bot.send_message(chat_id, "⚙️ **Адмін-центр керування:**", reply_markup=get_admin_inline_menu(), parse_mode="Markdown")

@app.route('/')
def home(): return "OK"

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))).start()
    bot.infinity_polling()
