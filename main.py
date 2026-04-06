import telebot
import os
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
    bot.send_dice(message.chat.id)

if __name__ == "__main__":
    Thread(target=run_web_server).start()
    bot.infinity_polling()
