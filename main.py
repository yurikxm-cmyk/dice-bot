import telebot
import os
import time
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

@bot.message_handler(commands=['roll', 'dice'])
def send_dice(message):
    user_name = message.from_user.first_name
    
    # 1. Повідомляємо, хто кидає
    bot.send_message(message.chat.id, f"🎲 {user_name} кидає кубик...")
    
    # 2. Відправляємо кубик і зберігаємо інформацію про нього
    dice_msg = bot.send_dice(message.chat.id)
    
    # 3. Чекаємо 3-4 секунди, поки закінчиться анімація кубика
    time.sleep(3.5)
    
    # 4. Пишемо результат числом
    result = dice_msg.dice.value
    bot.send_message(message.chat.id, f"🎯 У {user_name} випало: {result}")

if __name__ == "__main__":
    Thread(target=run_web_server).start()
    bot.infinity_polling()
