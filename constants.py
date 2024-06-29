import os
import telebot
from dotenv import load_dotenv

load_dotenv('/etc/env/tg.env')

admin_tg = os.getenv('admin_tg')
bot_tools = telebot.TeleBot(os.getenv('tg_token_tools'))

supl_path = 'c:/Quad Solutions/files/2_ price'


def send_message(message):
    bot_tools.send_message(admin_tg, message)


