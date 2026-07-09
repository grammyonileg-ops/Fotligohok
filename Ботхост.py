import telebot
import requests
import time
import re
import threading
import socket
import random
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "8842792581:AAG1FOE3kPN3ZQpMc6C-uuKZLKXizbRtDjs"
bot = telebot.TeleBot(TOKEN)

# === ДАННЫЕ ===
PROXY_LIST = []
orders = {}
order_counter = 0
user_temp = {}

REASONS = {
    "1": "СПАМ",
    "2": "НАСИЛИЕ",
    "3": "ДОМОГАТЕЛЬСТВА",
    "4": "ОПАСНЫЙ КОНТЕНТ",
    "5": "НЕЗАКОННЫЙ КОНТЕНТ",
    "6": "НЕДОСТОВЕРНАЯ ИНФА",
    "7": "МОШЕННИЧЕСТВО"
}
REASON_KEYS = ["1", "2", "3", "4", "5", "6", "7"]
ROTATION_REASONS = ["spam", "fraud", "misinformation", "illegal", "harassment", "violence", "self_harm"]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.163 Mobile Safari/537.36"
]

# === МЕНЮ ===
def main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🆕 Новый заказ", callback_data="new_order"),
        InlineKeyboardButton("📋 Мои заказы", callback_data="list_orders"),
        InlineKeyboardButton("🌐 Прокси", callback_data="proxy_menu"),
        InlineKeyboardButton("🛑 Стоп", callback_data="stop")
    )
    return markup

def proxy_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ Добавить", callback_data="add_proxy"),
        InlineKeyboardButton("📥 Вставить список", callback_data="add_proxy_bulk"),
        InlineKeyboardButton("🗑 Удалить все", callback_data="delete_all_proxies"),
        InlineKeyboardButton("📋 Список", callback_data="list_proxies"),
        InlineKeyboardButton("🔍 Проверить", callback_data="check_proxies"),
        InlineKeyboardButton("🔙 Назад", callback_data="back")
    )
    return markup

def orders_list_markup(chat_id):
    markup = InlineKeyboardMarkup(row_width=2)
    user_orders = [o for o in orders.values() if o["chat_id"] == chat_id]
    if not user_orders:
        markup.add(InlineKeyboardButton("🔙 Назад", callback_data="back"))
        return markup, "📋 У вас нет заказов."

    text = "📋 **Ваши заказы:**\n\n"
    for o in user_orders:
        status_icon = "🟢" if o["status"] == "active" else "⏳" if o["status"] == "draft" else "🔴"
        text += f"{status_icon} #{o['id']} | {o['name'][:20]} | {o['status']}\n"
        markup.add(InlineKeyboardButton(f"#{o['id']} {o['name'][:15]}", callback_data=f"view_{o['id']}"))
    markup.add(InlineKeyboardButton("🔙 Назад", callback_data="back"))
    return markup, text

def order_actions_markup(order_id):
    markup = InlineKeyboardMarkup(row_width=2)
    o = orders.get(order_id)
    if not o:
        return markup, "❌ Заказ не найден."
    markup.add(
        InlineKeyboardButton("▶️ Активировать" if o["status"] == "draft" else "⏸ Приостановить", callback_data=f"toggle_{order_id}"),
        InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_{order_id}"),
        InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_{order_id}"),
        InlineKeyboardButton("🔙 Назад", callback_data="list_orders")
    )
    status_icon = "🟢" if o["status"] == "active" else "⏳" if o["status"] == "draft" else "🔴"
    text = (f"📦 **Заказ #{o['id']}**\n"
            f"📛 Название: {o['name']}\n"
            f"🎯 Видео ID: {o['video_id']}\n"
            f"📛 Причины: {', '.join([REASONS[r] for r in o['reasons']])}\n"
            f"🔄 Ротация: {'✅' if o['rotation'] else '❌'}\n"
            f"⏱ Интервал: {o['interval']} сек\n"
            f"⏳ Длительность: {o['duration']//60} мин\n"
            f"📊 Статус: {status_icon} {o['status']}")
    return markup, text

# === КОМАНДЫ ===
@bot.message_handler(commands=['start', 'menu'])
def start(message):
    if str(message.chat.id) != "8934060669":
        bot.reply_to(message, "❌ Доступ запрещён")
        return
    bot.send_message(message.chat.id, "🔥 Бот для жалоб на видео", reply_markup=main_menu())

# === ОБРАБОТЧИК ВСЕХ КНОПОК ===
@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    global order_counter
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    data = call.data

    if data == "new_order":
        user_temp[chat_id] = {"step": "video", "reasons": [], "rotation": False}
        bot.edit_message_text("📎 Шаг 1: Пришли ссылку на видео", chat_id, msg_id, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Назад", callback_data="back")))
        bot.register_next_step_handler(call.message, step_video)

    elif data == "list_orders":
        markup, text = orders_list_markup(chat_id)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("view_"):
        oid = int(data.split("_")[1])
        markup, text = order_actions_markup(oid)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("toggle_"):
        oid = int(data.split("_")[1])
        o = orders.get(oid)
        if o and o["chat_id"] == chat_id:
            if o["status"] == "draft":
                o["status"] = "active"
                bot.answer_callback_query(call.id, "✅ Заказ активирован!")
                start_attack(oid)
            elif o["status"] == "active":
                o["status"] = "draft"
                bot.answer_callback_query(call.id, "⏸ Заказ приостановлен")
        markup, text = order_actions_markup(oid)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("delete_"):
        oid = int(data.split("_")[1])
        if oid in orders and orders[oid]["chat_id"] == chat_id:
            del orders[oid]
            bot.answer_callback_query(call.id, "🗑 Заказ удалён")
        bot.edit_message_text("✅ Заказ удалён.", chat_id, msg_id, reply_markup=main_menu())

    elif data.startswith("edit_"):
        oid = int(data.split("_")[1])
        o = orders.get(oid)
        if o:
            user_temp[chat_id] = {"edit_id": oid}
            bot.send_message(chat_id, f"✏️ Введи новый интервал (сейчас {o['interval']} сек):")
            bot.register_next_step_handler(call.message, edit_interval)

    elif data == "proxy_menu":
        bot.edit_message_text("🌐 Управление прокси:", chat_id, msg_id, reply_markup=proxy_menu())

    elif data == "add_proxy":
        bot.send_message(chat_id, "Введи прокси (http://user:pass@ip:port или socks5://user:pass@ip:port)")
        bot.register_next_step_handler(call.message, add_proxy)

    elif data == "add_proxy_bulk":
        bot.send_message(chat_id, "Отправь список прокси (каждый с новой строки или через запятую):")
        bot.register_next_step_handler(call.message, add_proxy_bulk)

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

    elif data == "back":
        bot.edit_message_text("Главное меню", chat_id, msg_id, reply_markup=main_menu())

    elif data == "stop":
        bot.send_message(chat_id, "🛑 Остановлено")
        raise SystemExit

# === ШАГИ СОЗДАНИЯ ЗАКАЗА ===
def step_video(message):
    chat_id = message.chat.id
    url = message.text.strip()
    match = re.search(r'/video/(\d+)', url)
    if not match:
        bot.reply_to(message, "❌ Неверная ссылка. Попробуй ещё раз.")
        bot.register_next_step_handler(message, step_video)
        return
    user_temp[chat_id]["video_id"] = match.group(1)
    show_reason_menu(chat_id)

def show_reason_menu(chat_id):
    reasons = user_temp.get(chat_id, {}).get("reasons", [])
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ Добавить ещё", callback_data="add_reason"),
        InlineKeyboardButton("✅ Готово", callback_data="reason_done"),
        InlineKeyboardButton("🔙 Назад", callback_data="back")
    )
    text = "📛 **Шаг 2: Выбери причины (пришли боту цифру причины, можно несколько):**\n\n"
    for key, label in REASONS.items():
        text += f"{label} - {key}\n"
    text += "\n📌 **Твои выбранные причины:**\n"
    if reasons:
        text += ", ".join([REASONS[r] for r in reasons])
    else:
        text += "❌ (пока ничего не выбрано)"
    text += "\n\nℹ️ Нажми 'Добавить ещё' и введи номер причины (1-7)."
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "add_reason")
def add_reason_callback(call):
    bot.answer_callback_query(call.id, "ℹ️ Введи номер причины в чат.")
    bot.send_message(call.message.chat.id, "ℹ️ Введи номер причины (1-7):")
    bot.register_next_step_handler(call.message, process_reason_input)

def process_reason_input(message):
    chat_id = message.chat.id
    text = message.text.strip()
    if text in REASON_KEYS:
        reasons = user_temp.get(chat_id, {}).get("reasons", [])
        if text not in reasons:
            reasons.append(text)
            user_temp[chat_id]["reasons"] = reasons
            bot.reply_to(message, f"✅ Добавлена причина: {REASONS[text]}")
        else:
            bot.reply_to(message, f"⚠️ Причина {REASONS[text]} уже выбрана.")
    else:
        bot.reply_to(message, "❌ Введи номер от 1 до 7.")
    show_reason_menu(chat_id)

@bot.callback_query_handler(func=lambda call: call.data == "reason_done")
def reason_done_callback(call):
    chat_id = call.message.chat.id
    reasons = user_temp.get(chat_id, {}).get("reasons", [])
    if not reasons:
        bot.answer_callback_query(call.id, "❌ Выбери хотя бы одну причину!", show_alert=True)
        return
    bot.answer_callback_query(call.id, "✅ Причины выбраны!")
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🔄 Включить ротацию", callback_data="rotation_on"),
        InlineKeyboardButton("🔒 Без ротации", callback_data="rotation_off"),
        InlineKeyboardButton("🔙 Назад", callback_data="back")
    )
    bot.edit_message_text("🔄 Шаг 3: Включить ротацию?", chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["rotation_on", "rotation_off"])
def rotation_callback(call):
    chat_id = call.message.chat.id
    user_temp[chat_id]["rotation"] = (call.data == "rotation_on")
    bot.answer_callback_query(call.id, f"✅ Ротация {'включена' if call.data == 'rotation_on' else 'выключена'}")
    bot.send_message(chat_id, "⏱ Шаг 4: Введи интервал между жалобами (сек):")
    bot.register_next_step_handler(call.message, step_interval)

def step_interval(message):
    chat_id = message.chat.id
    try:
        interval = int(message.text)
        if interval < 1:
            bot.reply_to(message, "❌ Интервал должен быть больше 0!")
            bot.register_next_step_handler(message, step_interval)
            return
        user_temp[chat_id]["interval"] = interval
        bot.reply_to(message, "⏳ Шаг 5: Введи длительность атаки (минуты):")
        bot.register_next_step_handler(message, step_duration)
    except:
        bot.reply_to(message, "❌ Введи число!")
        bot.register_next_step_handler(message, step_interval)

def step_duration(message):
    global order_counter
    chat_id = message.chat.id
    try:
        duration = int(message.text) * 60
        temp = user_temp.get(chat_id, {})
        if not temp.get("video_id") or not temp.get("reasons"):
            bot.reply_to(message, "❌ Ошибка! Начни заново /start")
            return
        order_counter += 1
        oid = order_counter
        orders[oid] = {
            "id": oid,
            "chat_id": chat_id,
            "name": f"Заказ #{oid}",
            "video_id": temp["video_id"],
            "reasons": temp["reasons"],
            "rotation": temp.get("rotation", False),
            "interval": temp.get("interval", 5),
            "duration": duration,
            "status": "draft"
        }
        del user_temp[chat_id]
        bot.reply_to(message, f"✅ **Заказ #{oid} создан!**\nСтатус: ⏳ Черновик\n\nИспользуй '📋 Мои заказы' для управления.", parse_mode="Markdown", reply_markup=main_menu())
    except:
        bot.reply_to(message, "❌ Ошибка! Начни заново /start")

def edit_interval(message):
    chat_id = message.chat.id
    edit_id = user_temp.get(chat_id, {}).get("edit_id")
    if not edit_id or edit_id not in orders:
        bot.reply_to(message, "❌ Заказ не найден.")
        return
    try:
        interval = int(message.text)
        orders[edit_id]["interval"] = interval
        bot.reply_to(message, f"✅ Интервал обновлён на {interval} сек.")
        markup, text = order_actions_markup(edit_id)
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
        del user_temp[chat_id]
    except:
        bot.reply_to(message, "❌ Введи число!")

# === ПРОКСИ ===
def add_proxy(message):
    text = message.text.strip()
    proxies = re.split(r'[\n,]+', text)
    count = 0
    for p in proxies:
        p = p.strip()
        if p:
            PROXY_LIST.append(p)
            count += 1
    bot.reply_to(message, f"✅ Добавлено прокси: {count} шт.")

def add_proxy_bulk(message):
    text = message.text.strip()
    proxies = re.split(r'[\n,]+', text)
    count = 0
    for p in proxies:
        p = p.strip()
        if p:
            PROXY_LIST.append(p)
            count += 1
    bot.reply_to(message, f"✅ Добавлено прокси: {count} шт.")

def check_proxies(chat_id):
    if not PROXY_LIST:
        bot.send_message(chat_id, "❌ Нет прокси")
        return
    alive = 0
    for p in PROXY_LIST[:10]:
        try:
            if p.startswith("socks5://"):
                parts = p.replace("socks5://", "").split("@")
                if len(parts) == 2:
                    _, ip_port = parts
                    ip, port = ip_port.split(":")
                    port = int(port)
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(5)
                    s.connect((ip, port))
                    s.close()
                    alive += 1
            else:
                requests.get("https://api.ipify.org", proxies={"http": p, "https": p}, timeout=5)
                alive += 1
        except:
            pass
    bot.send_message(chat_id, f"✅ Живых: {alive} из {len(PROXY_LIST[:10])}", reply_markup=proxy_menu())

# === АТАКА ===
def start_attack(order_id):
    order = orders.get(order_id)
    if not order or order["status"] != "active":
        return
    chat_id = order["chat_id"]
    video_id = order["video_id"]
    interval = order["interval"]
    duration = order["duration"]
    rotation = order["rotation"]
    reasons = order["reasons"]

    def run():
        start_time = time.time()
        sent = 0
        success = 0
        failed = 0
        proxy_index = 0
        reason_index = 0

        bot.send_message(chat_id, f"🔥 Атака по заказу #{order_id} на видео {video_id} началась!")

        while time.time() - start_time < duration and order["status"] == "active":
            if rotation:
                reason_key = ROTATION_REASONS[reason_index % len(ROTATION_REASONS)]
                reason_index += 1
            else:
                r_key = reasons[reason_index % len(reasons)]
                reason_key = list(REASONS.keys())[list(REASONS.values()).index(REASONS[r_key])]

            proxy = PROXY_LIST[proxy_index % len(PROXY_LIST)] if PROXY_LIST else None
            if not proxy:
                bot.send_message(chat_id, "❌ Нет прокси! Атака остановлена.")
                break

            headers = {"User-Agent": random.choice(USER_AGENTS)}
            try:
                resp = requests.post(
                    "https://www.tiktok.com/api/video/report/",
                    data={"video_id": video_id, "reason": reason_key},
                    headers=headers,
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

            bot.send_message(chat_id, f"📊 Заказ #{order_id} | Жалоба #{sent} | {status} | Причина: {REASONS.get(reason_key, reason_key)} | Прокси: {proxy[:30]}")
            proxy_index += 1
            time.sleep(interval)

        order["status"] = "completed"
        bot.send_message(chat_id, f"🏁 Заказ #{order_id} завершён! Успешно: {success}, Ошибок: {failed}", reply_markup=main_menu())

    threading.Thread(target=run, daemon=True).start()

# === ЗАПУСК ===
try:
    bot.remove_webhook()
except:
    pass

print("✅ Бот запущен и готов к работе!")
bot.polling(none_stop=True)