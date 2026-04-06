import telebot
import os
import time
from telebot import types
from flask import Flask
from threading import Thread

TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

app = Flask('')
@app.route('/')
def home():
    return "Бот працює!"

def run_web_server():
    app.run(host='0.0.0.0', port=8080)

# Створюємо INLINE кнопку (вона не викликає авто-відповідь)
def inline_keyboard():
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("🎲 Кинути кубик", callback_data="roll_dice")
    markup.add(btn)
    return markup

@bot.message_handler(commands=['start', 'roll'])
def welcome(message):
    bot.send_message(message.chat.id, "Натисніть кнопку, щоб кинути кубик:", reply_markup=inline_keyboard())

# Обробка натискання на Inline кнопку
@bot.callback_query_handler(func=lambda call: call.data == "roll_dice")
def callback_query(call):
    user_name = call.from_user.first_name
    
    # 1. Відразу кидаємо кубик
    dice_msg = bot.send_dice(call.message.chat.id)
    
    # 2. Пауза
    time.sleep(3.5)
    
    # 3. Результат і нова кнопка
    result = dice_msg.dice.value
    bot.send_message(call.message.chat.id, f"🎯 {user_name}, випало: {result}", reply_markup=inline_keyboard())
    
    # Прибираємо "годинник" на кнопці
    bot.answer_callback_query(call.id)

if __name__ == "__main__":
    Thread(target=run_web_server).start()
    bot.infinity_polling()
