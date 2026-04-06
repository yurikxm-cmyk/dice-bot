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

# Функція для кнопок (Inline + Клавіатурна)
def get_keyboards():
    # Кнопка під повідомленням
    inline = types.InlineKeyboardMarkup()
    inline.add(types.InlineKeyboardButton("🎲 Кинути кубик", callback_data="roll_dice"))
    
    # Кнопка внизу (клавіатурна)
    reply = types.ReplyKeyboardMarkup(resize_keyboard=True)
    reply.add(types.KeyboardButton("🎲 Кинути кубик"))
    
    return inline, reply

@bot.message_handler(commands=['start', 'roll'])
def welcome(message):
    inline, reply = get_keyboards()
    bot.send_message(message.chat.id, "Натисніть кнопку:", reply_markup=reply)
    bot.send_message(message.chat.id, "Або цю:", reply_markup=inline)

# Обробка натискання на кнопку ПІД повідомленням
@bot.callback_query_handler(func=lambda call: call.data == "roll_dice")
def callback_roll(call):
    process_roll(call.message, call.from_user.first_name)
    bot.answer_callback_query(call.id)

# Обробка натискання на кнопку ВНИЗУ (текстова)
@bot.message_handler(func=lambda message: message.text == "🎲 Кинути кубик")
def text_roll(message):
    process_roll(message, message.from_user.first_name)

# Спільна логіка кидка
def process_roll(message, name):
    inline, _ = get_keyboards()
    dice_msg = bot.send_dice(message.chat.id)
    time.sleep(3.5)
    result = dice_msg.dice.value
    bot.send_message(message.chat.id, f"🎯 {name}, випало: {result}", reply_markup=inline)

if __name__ == "__main__":
    Thread(target=run_web_server).start()
    bot.infinity_polling()
