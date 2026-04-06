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

# Функція для створення звичайної клавіатури (не Reply на кубик)
def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    btn = types.KeyboardButton("🎲 Кинути кубик")
    markup.add(btn)
    return markup

@bot.message_handler(commands=['start'])
def welcome(message):
    # Надсилаємо кнопку окремим повідомленням один раз
    bot.send_message(message.chat.id, "Кнопка активована! Натискай її нижче 👇", reply_markup=main_keyboard())

@bot.message_handler(func=lambda message: message.text == "🎲 Кинути кубик" or message.text == "/roll")
def send_dice(message):
    user_name = message.from_user.first_name
    
    # 1. Відправляємо кубик БЕЗ передачі reply_markup у цьому ж повідомленні
    dice_msg = bot.send_dice(message.chat.id)
    
    # 2. Пауза на анімацію
    time.sleep(3.5)
    
    # 3. Виводимо результат
    result = dice_msg.dice.value
    bot.send_message(message.chat.id, f"🎯 {user_name}, випало: {result}")

if __name__ == "__main__":
    Thread(target=run_web_server).start()
    bot.infinity_polling()
    # 2. Чекаємо 3.5 секунди
    time.sleep(3.5)
    
    # 3. Пишемо підсумок: хто кинув і що випало
    result = dice_msg.dice.value
    bot.send_message(message.chat.id, f"🎯 {user_name}, випало: {result}")

if __name__ == "__main__":
    Thread(target=run_web_server).start()
    bot.infinity_polling()
    # Відправляємо кубик
    dice_msg = bot.send_dice(message.chat.id)
    
    # Чекаємо завершення анімації
    time.sleep(3.5)
    
    # Пишемо результат
    result = dice_msg.dice.value
    bot.send_message(message.chat.id, f"🎯 У {user_name} випало: {result}")

if __name__ == "__main__":
    Thread(target=run_web_server).start()
    bot.infinity_polling()
    bot.infinity_polling()
