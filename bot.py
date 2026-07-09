import telebot
import requests
import time
import re
import threading
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "883ZQpMc6C-uuKZLKXizbRtDjs"
bot = telebot.TeleBot(TOKEN)

# === ОСТАЛЬНОЙ КОД (весь, что был ранее) ===
# ... (вставь сюда весь остальной код, который я дал в прошлом сообщении)

bot.remove_webhook()
bot.polling(none_stop=True)
