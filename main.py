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

# Кнопка під повідомленням
def get_inline_keyboard():
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("🎲 Кинути ще раз", callback_data="roll_dice")
    markup.add(btn)
    return markup

@bot.message_handler(commands=['start', 'roll'])
def welcome(message):
    bot.send_message(
        message.chat.id, 
        "Привіт! Натискай кнопку нижче, щоб випробувати удачу:", 
        reply_markup=get_inline_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data == "roll_dice")
def callback_roll(call):
    user_name = call.from_user.first_name
    
    # 1. Ефект "Бот друкує..." (поки крутиться кубик)
    bot.send_chat_action(call.message.chat.id, 'typing')
    
    # 2. Кидаємо кубик
    dice_msg = bot.send_dice(call.message.chat.id)
    
    # Прибираємо годинник на кнопці
    bot.answer_callback_query(call.id)
    
    # 3. Пауза на анімацію (3.5 сек)
    time.sleep(3.5)
    
    # 4. Пишемо результат і додаємо кнопку "Кинути ще раз"
    result = dice_msg.dice.value
    bot.send_message(
        call.message.chat.id, 
        f"🎯 {user_name}, випало: {result}", 
        reply_markup=get_inline_keyboard()
    )

if __name__ == "__main__":
    Thread(target=run_web_server).start()
    bot.infinity_polling()
