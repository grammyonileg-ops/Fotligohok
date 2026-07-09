import telebot
import requests
import time
import re
import threading
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "8842792581:AAG1FOE3kPN3ZQpMc6C-uuKZLKXizbRtDjs"  # замени на свой, если другой
bot = telebot.TeleBot(TOKEN)

# === ХРАНИЛИЩА ===
PROXY_LIST = []
user_data = {}
active_orders = {}

REASONS = {
    "spam": "📩 Спам",
    "violence": "🔪 Насилие",
    "harassment": "🚫 Домогательства",
    "self_harm": "⚠️ Опасный контент",
    "illegal": "⚖️ Незаконный контент",
    "misinformation": "❌ Недостоверная инфа",
    "fraud": "💀 Мошенничество и обман"
}

ROTATION_REASONS = ["spam", "fraud", "misinformation", "illegal", "harassment", "violence", "self_harm"]

# === МЕНЮ ===
def main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎯 Новая цель", callback_data="new_target"),
        InlineKeyboardButton("📛 Причина", callback_data="reason"),
        InlineKeyboardButton("🔄 Ротация", callback_data="toggle_rotation"),
        InlineKeyboardButton("⏱ Интервал", callback_data="interval"),
        InlineKeyboardButton("⏳ Длительность", callback_data="duration"),
        InlineKeyboardButton("🌐 Прокси", callback_data="proxy_menu"),
        InlineKeyboardButton("📋 Заказы", callback_data="orders_menu"),
        InlineKeyboardButton("🚀 Атака", callback_data="start_attack"),
        InlineKeyboardButton("🛑 Стоп", callback_data="stop")
    )
    return markup

def proxy_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ Добавить", callback_data="add_proxy"),
        InlineKeyboardButton("🗑 Удалить все", callback_data="delete_all_proxies"),
        InlineKeyboardButton("📋 Список", callback_data="list_proxies"),
        InlineKeyboardButton("🔍 Проверить", callback_data="check_proxies"),
        InlineKeyboardButton("🔙 Назад", callback_data="back")
    )
    return markup

def reason_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    for key, label in REASONS.items():
        markup.add(InlineKeyboardButton(label, callback_data=f"set_reason_{key}"))
    markup.add(InlineKeyboardButton("🔙 Назад", callback_data="back"))
    return markup

# === КОМАНДЫ ===
@bot.message_handler(commands=['start', 'menu'])
def start(message):
    if str(message.chat.id) != "8934060669":
        bot.reply_to(message, "❌ Доступ запрещён")
        return
    user_data[message.chat.id] = {
        "video_id": "",
        "reason": "spam",
        "interval": 5,
        "duration": 60,
        "rotation": False
    }
    bot.send_message(message.chat.id, "🔥 Бот для жалоб на видео", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    data = call.data

    if data == "new_target":
        bot.send_message(chat_id, "Пришли ссылку на видео")
        bot.register_next_step_handler(call.message, save_video)
    elif data == "reason":
        bot.edit_message_text("Выбери причину:", chat_id, msg_id, reply_markup=reason_menu())
    elif data.startswith("set_reason_"):
        key = data.replace("set_reason_", "")
        user_data[chat_id]["reason"] = key
        bot.answer_callback_query(call.id, f"Причина: {REASONS[key]}")
        bot.edit_message_text(f"✅ Причина: {REASONS[key]}", chat_id, msg_id, reply_markup=main_menu())
    elif data == "toggle_rotation":
        user_data[chat_id]["rotation"] = not user_data[chat_id].get("rotation", False)
        status = "включена" if user_data[chat_id]["rotation"] else "выключена"
        bot.answer_callback_query(call.id, f"Ротация {status}")
        bot.edit_message_text(f"✅ Ротация {status}", chat_id, msg_id, reply_markup=main_menu())
    elif data == "interval":
        bot.send_message(chat_id, "Введи интервал (сек):")
        bot.register_next_step_handler(call.message, save_interval)
    elif data == "duration":
        bot.send_message(chat_id, "Введи длительность (минуты):")
        bot.register_next_step_handler(call.message, save_duration)
    elif data == "proxy_menu":
        bot.edit_message_text("🌐 Управление прокси:", chat_id, msg_id, reply_markup=proxy_menu())
    elif data == "add_proxy":
        bot.send_message(chat_id, "Введи прокси (http://user:pass@ip:port)")
        bot.register_next_step_handler(call.message, add_proxy_step)
    elif data == "delete_all_proxies":
        PROXY_LIST.clear()
        bot.answer_callback_query(call.id, "Все прокси удалены")
        bot.edit_message_text("✅ Все прокси удалены", chat_id, msg_id, reply_markup=proxy_menu())
    elif data == "list_proxies":
        if not PROXY_LIST:
            bot.answer_callback_query(call.id, "Список пуст", show_alert=True)
            return
        text = "🌐 Прокси:\n" + "\n".join(PROXY_LIST[:20])
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=proxy_menu())
    elif data == "check_proxies":
        bot.edit_message_text("🔍 Проверяю...", chat_id, msg_id)
        check_proxies(chat_id)
    elif data == "orders_menu":
        order = active_orders.get(chat_id)
        if order and order.get("active"):
            text = (f"📋 Активный заказ:\n"
                    f"🎯 Видео: {order['video_id']}\n"
                    f"📛 Причина: {REASONS.get(order['reason'], order['reason'])}\n"
                    f"⏱ Интервал: {order['interval']} сек\n"
                    f"⏳ Длительность: {order['duration']//60} мин")
            bot.edit_message_text(text, chat_id, msg_id, reply_markup=main_menu())
        else:
            bot.edit_message_text("❌ Нет активных заказов.", chat_id, msg_id, reply_markup=main_menu())
    elif data == "start_attack":
        if not user_data[chat_id].get("video_id"):
            bot.send_message(chat_id, "❌ Сначала задай видео")
            return
        if not PROXY_LIST:
            bot.send_message(chat_id, "❌ Нет прокси")
            return
        bot.edit_message_text("🚀 Запускаю...", chat_id, msg_id)
        start_attack(chat_id)
    elif data == "stop":
        bot.send_message(chat_id, "🛑 Остановлено")
        raise SystemExit
    elif data == "back":
        bot.edit_message_text("Главное меню", chat_id, msg_id, reply_markup=main_menu())

# === ШАГИ ===
def save_video(message):
    url = message.text.strip()
    match = re.search(r'/video/(\d+)', url)
    if match:
        user_data[message.chat.id]["video_id"] = match.group(1)
        bot.reply_to(message, f"✅ Видео найдено! ID: {match.group(1)}")
    else:
        bot.reply_to(message, "❌ Не удалось найти ID видео")

def save_interval(message):
    try:
        val = int(message.text)
        user_data[message.chat.id]["interval"] = val
        bot.reply_to(message, f"✅ Интервал: {val} сек")
    except:
        bot.reply_to(message, "❌ Введи число")

def save_duration(message):
    try:
        val = int(message.text) * 60
        user_data[message.chat.id]["duration"] = val
        bot.reply_to(message, f"✅ Длительность: {val//60} мин")
    except:
        bot.reply_to(message, "❌ Введи число")

def add_proxy_step(message):
    PROXY_LIST.append(message.text.strip())
    bot.reply_to(message, f"✅ Прокси добавлен: {message.text}")

def check_proxies(chat_id):
    if not PROXY_LIST:
        bot.send_message(chat_id, "❌ Нет прокси")
        return
    alive = 0
    for p in PROXY_LIST[:10]:
        try:
            requests.get("https://api.ipify.org", proxies={"http": p, "https": p}, timeout=5)
            alive += 1
        except:
            pass
    bot.send_message(chat_id, f"✅ Живых: {alive} из {len(PROXY_LIST[:10])}", reply_markup=proxy_menu())

# === АТАКА ===
def start_attack(chat_id):
    data = user_data[chat_id]
    video_id = data["video_id"]
    interval = data["interval"]
    duration = data["duration"]
    rotation = data.get("rotation", False)
    reason = data["reason"]

    active_orders[chat_id] = {
        "video_id": video_id,
        "reason": reason,
        "interval": interval,
        "duration": duration,
        "active": True,
        "rotation": rotation,
        "rotation_index": 0
    }

    def run():
        order = active_orders[chat_id]
        start_time = time.time()
        sent = 0
        success = 0
        failed = 0
        proxy_index = 0

        bot.send_message(chat_id, f"🔥 Атака на видео {video_id} началась!")

        while order["active"] and time.time() - start_time < duration:
            if rotation:
                reason_key = ROTATION_REASONS[order["rotation_index"] % len(ROTATION_REASONS)]
                order["rotation_index"] += 1
            else:
                reason_key = reason

            proxy = PROXY_LIST[proxy_index % len(PROXY_LIST)]
            try:
                resp = requests.post(
                    "https://www.tiktok.com/api/video/report/",
                    data={"video_id": video_id, "reason": reason_key},
                    proxies={"http": proxy, "https": proxy},
                    timeout=5
                )
                sent += 1
                if resp.status_code == 200:
                    success += 1
                    status = "✅ УСПЕШНО"
                else:
                    failed += 1
                    status = f"⚠️ ОШИБКА {resp.status_code}"
            except:
                sent += 1
                failed += 1
                status = "❌ СБОЙ"

            bot.send_message(chat_id, f"📊 Жалоба #{sent} | {status} | Причина: {REASONS.get(reason_key, reason_key)}")
            proxy_index += 1
            time.sleep(interval)

        bot.send_message(chat_id, f"🏁 Атака завершена! Успешно: {success}, Ошибок: {failed}", reply_markup=main_menu())
        if chat_id in active_orders:
            del active_orders[chat_id]

    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()

# === ЗАПУСК ===
bot.remove_webhook()
bot.polling(none_stop=True)
