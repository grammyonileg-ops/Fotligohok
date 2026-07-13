import mysql.connector
import requests
import time
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ==================== НАСТРОЙКИ ====================
"

DB_CONFIG = {
    "host": "localhost",
    "user": "your_user",
    "password": "your_password",
    "database": "your_db"
}

ANTISPAM_ENABLED = True
ANTISPAM_INTERVAL = 1
ANTISPAM_BAN_TIME = 3

START_TEXT = "Привет 👋"

last_message_time = {}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

def init_db():
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_activity DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cells (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id BIGINT,
            action TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_bans (
            user_id BIGINT PRIMARY KEY,
            banned_until DATETIME
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            id INT AUTO_INCREMENT PRIMARY KEY,
            event_type TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def log_action(user_id, action):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("INSERT INTO logs (user_id, action) VALUES (%s, %s)", (user_id, action))
        cur.execute("INSERT INTO stats (event_type) VALUES (%s)", (action,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Log error: {e}")

def get_stats(hours=None):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        if hours:
            since = datetime.now() - timedelta(hours=hours)
            cur.execute("SELECT COUNT(*) FROM stats WHERE timestamp >= %s", (since,))
        else:
            cur.execute("SELECT COUNT(*) FROM stats")
        count = cur.fetchone()[0]
        conn.close()
        return count
    except:
        return 0

def check_ban(user_id):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT banned_until FROM user_bans WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        conn.close()
        if row and row[0] and row[0] > datetime.now():
            return row[0]
        return None
    except:
        return None

def ban_user(user_id, seconds):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        until = datetime.now() + timedelta(seconds=seconds)
        cur.execute("REPLACE INTO user_bans (user_id, banned_until) VALUES (%s, %s)", (user_id, until))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ban error: {e}")

def get_sponsors():
    url = "https://api.subgram.org/api/v1/public/get-sponsors"
    headers = {"Authorization": f"Bearer {SUBGRAM_API_KEY}"}
    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            data = r.json()
            return data.get("sponsors", [])
    except Exception as e:
        logger.error(f"SubGram sponsors error: {e}")
    return []

def check_subgram_subscription(user_id, channel_username):
    url = "https://api.subgram.org/api/v1/advanced/orders"
    headers = {"Authorization": f"Bearer {SUBGRAM_API_KEY}"}
    params = {"user_id": user_id, "sponsor": channel_username}
    try:
        r = requests.get(url, headers=headers, params=params)
        if r.status_code == 200:
            data = r.json()
            return data.get("subscribed", False)
    except Exception as e:
        logger.error(f"SubGram check error: {e}")
    return False

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("📂 Каталог", callback_data="admin_catalog")],
        [InlineKeyboardButton("✏️ Сменить приветствие", callback_data="admin_change_start")],
        [InlineKeyboardButton("🔑 Обновить SubGram", callback_data="admin_subgram_key")],
        [InlineKeyboardButton("🛡 Антиспам", callback_data="admin_antispam")]
    ])

def catalog_keyboard(cells):
    keyboard = []
    for cell in cells:
        keyboard.append([InlineKeyboardButton(cell[1], callback_data=f"cell_{cell[0]}")])
    keyboard.append([InlineKeyboardButton("➕ Создать ячейку", callback_data="admin_create_cell")])
    keyboard.append([InlineKeyboardButton("🔙 Закрыть", callback_data="admin_close")])
    return InlineKeyboardMarkup(keyboard)

def cell_owner_keyboard(cell_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Поделиться", switch_inline_query=f"start=script_{cell_id}")],
        [InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_cell_{cell_id}")],
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_cell_{cell_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_catalog")]
    ])

def cell_user_keyboard(cell_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Поделиться", switch_inline_query=f"start=script_{cell_id}")]
    ])

def check_antispam(user_id):
    global ANTISPAM_ENABLED, ANTISPAM_INTERVAL, ANTISPAM_BAN_TIME
    if not ANTISPAM_ENABLED:
        return True
    now = time.time()
    if user_id in last_message_time:
        diff = now - last_message_time[user_id]
        if diff < ANTISPAM_INTERVAL:
            ban_user(user_id, ANTISPAM_BAN_TIME)
            return False
    last_message_time[user_id] = now
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    if not check_antispam(user.id):
        ban = check_ban(user.id)
        await update.message.reply_text(f"Антиспам. Вы забанены до {ban.strftime('%H:%M:%S')}")
        return

    await log_action(user.id, "start")

    ban = check_ban(user.id)
    if ban:
        await update.message.reply_text(f"Вы забанены до {ban.strftime('%H:%M:%S')}")
        return

    if args and args[0].startswith("script_"):
        try:
            cell_id = int(args[0].split("_")[1])
        except:
            await update.message.reply_text("Неверная ссылка")
            return

        if user.id == OWNER_ID:
            try:
                conn = mysql.connector.connect(**DB_CONFIG)
                cur = conn.cursor()
                cur.execute("SELECT name, description FROM cells WHERE id = %s", (cell_id,))
                cell = cur.fetchone()
                conn.close()
                if cell:
                    await update.message.reply_text(f"{cell[0]}\n\n{cell[1]}", reply_markup=cell_owner_keyboard(cell_id))
                else:
                    await update.message.reply_text("Ячейка не найдена")
            except Exception as e:
                await update.message.reply_text("Ошибка базы данных")
                logger.error(f"DB error: {e}")
            return

        sponsors = get_sponsors()
        if not sponsors:
            try:
                conn = mysql.connector.connect(**DB_CONFIG)
                cur = conn.cursor()
                cur.execute("SELECT name, description FROM cells WHERE id = %s", (cell_id,))
                cell = cur.fetchone()
                conn.close()
                if cell:
                    await update.message.reply_text(f"{cell[0]}\n\n{cell[1]}", reply_markup=cell_user_keyboard(cell_id))
                else:
                    await update.message.reply_text("Ячейка не найдена")
            except:
                await update.message.reply_text("Ошибка")
            return

        not_subscribed = []
        for sp in sponsors:
            username = sp.get("username") or sp.get("chat_id")
            if username and not check_subgram_subscription(user.id, username):
                not_subscribed.append(sp)

        if not_subscribed:
            keyboard = []
            for sp in not_subscribed:
                label = sp.get("username") or sp.get("title") or "Канал"
                link = sp.get("username") or sp.get("chat_id")
                url = f"https://t.me/{link}" if not str(link).startswith("http") else link
                keyboard.append([InlineKeyboardButton(f"📢 {label}", url=url)])
            keyboard.append([InlineKeyboardButton("✅ Я подписался", callback_data=f"check_sub_{cell_id}")])
            await update.message.reply_text("Для доступа подпишитесь на каналы:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            try:
                conn = mysql.connector.connect(**DB_CONFIG)
                cur = conn.cursor()
                cur.execute("SELECT name, description FROM cells WHERE id = %s", (cell_id,))
                cell = cur.fetchone()
                conn.close()
                if cell:
                    await update.message.reply_text(f"{cell[0]}\n\n{cell[1]}", reply_markup=cell_user_keyboard(cell_id))
                else:
                    await update.message.reply_text("Ячейка не найдена")
            except:
                await update.message.reply_text("Ошибка")
        return

    if user.id == OWNER_ID:
        await update.message.reply_text("Админ-панель", reply_markup=admin_keyboard())
    else:
        await update.message.reply_text(START_TEXT)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    if not check_antispam(user.id):
        ban = check_ban(user.id)
        await update.message.reply_text(f"Антиспам. Бан до {ban.strftime('%H:%M:%S')}")
        return

    if user.id != OWNER_ID:
        return

    if context.user_data.get("awaiting_start"):
        global START_TEXT
        START_TEXT = text
        context.user_data["awaiting_start"] = False
        await update.message.reply_text(f"Приветствие обновлено:\n\n{text}", reply_markup=admin_keyboard())
        return

    if context.user_data.get("awaiting_subgram"):
        global SUBGRAM_API_KEY
        SUBGRAM_API_KEY = text
        context.user_data["awaiting_subgram"] = False
        await update.message.reply_text("SubGram API ключ обновлён", reply_markup=admin_keyboard())
        return

    if context.user_data.get("awaiting_cell_name"):
        name = text
        context.user_data["new_cell_name"] = name
        context.user_data["awaiting_cell_name"] = False
        context.user_data["awaiting_cell_desc"] = True
        await update.message.reply_text("Введите описание ячейки:")
        return

    if context.user_data.get("awaiting_cell_desc"):
        name = context.user_data.get("new_cell_name")
        desc = text
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor()
            cur.execute("INSERT INTO cells (name, description) VALUES (%s, %s)", (name, desc))
            conn.commit()
            conn.close()
            await update.message.reply_text(f"Ячейка «{name}» создана", reply_markup=admin_keyboard())
        except Exception as e:
            await update.message.reply_text("Ошибка создания")
            logger.error(f"Create cell error: {e}")
        context.user_data["awaiting_cell_desc"] = False
        return

    if context.user_data.get("awaiting_edit_cell"):
        cell_id = context.user_data.get("edit_cell_id")
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor()
            cur.execute("UPDATE cells SET description = %s WHERE id = %s", (text, cell_id))
            conn.commit()
            conn.close()
            await update.message.reply_text("Описание обновлено", reply_markup=admin_keyboard())
        except:
            await update.message.reply_text("Ошибка")
        context.user_data["awaiting_edit_cell"] = False
        return

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data

    if data.startswith("check_sub_"):
        cell_id = int(data.split("_")[2])
        sponsors = get_sponsors()
        not_subscribed = []
        for sp in sponsors:
            username = sp.get("username") or sp.get("chat_id")
            if username and not check_subgram_subscription(user.id, username):
                not_subscribed.append(sp)

        if not_subscribed:
            await query.answer("Вы подписались не на все каналы", show_alert=True)
        else:
            try:
                conn = mysql.connector.connect(**DB_CONFIG)
                cur = conn.cursor()
                cur.execute("SELECT name, description FROM cells WHERE id = %s", (cell_id,))
                cell = cur.fetchone()
                conn.close()
                if cell:
                    await query.edit_message_text(f"{cell[0]}\n\n{cell[1]}", reply_markup=cell_user_keyboard(cell_id))
                else:
                    await query.edit_message_text("Ячейка не найдена")
            except:
                await query.edit_message_text("Ошибка")
        return

    if user.id != OWNER_ID:
        await query.edit_message_text("Доступ запрещён")
        return

    if data == "admin_stats":
        total = get_stats()
        day = get_stats(24)
        await query.edit_message_text(f"📊 Статистика\n\nЗа всё время: {total}\nЗа 24 часа: {day}", reply_markup=admin_keyboard())

    elif data == "admin_catalog":
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor()
            cur.execute("SELECT id, name FROM cells")
            cells = cur.fetchall()
            conn.close()
            await query.edit_message_text("📂 Каталог ячеек:", reply_markup=catalog_keyboard(cells))
        except:
            await query.edit_message_text("Ошибка загрузки", reply_markup=admin_keyboard())

    elif data == "admin_close":
        await query.edit_message_text("Админ-панель", reply_markup=admin_keyboard())

    elif data == "admin_back":
        await query.edit_message_text("Админ-панель", reply_markup=admin_keyboard())

    elif data == "admin_change_start":
        context.user_data["awaiting_start"] = True
        await query.edit_message_text("Введите новый текст приветствия:")

    elif data == "admin_subgram_key":
        context.user_data["awaiting_subgram"] = True
        await query.edit_message_text("Введите новый SubGram API ключ:")

    elif data == "admin_antispam":
        await query.edit_message_text(
            f"🛡 Антиспам\n\nСтатус: {'ВКЛ' if ANTISPAM_ENABLED else 'ВЫКЛ'}\nИнтервал: {ANTISPAM_INTERVAL}с\nВремя бана: {ANTISPAM_BAN_TIME}с",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("ВКЛ/ВЫКЛ", callback_data="toggle_antispam")],
                [InlineKeyboardButton("Интервал 1с", callback_data="interval_1"),
                 InlineKeyboardButton("2с", callback_data="interval_2")],
                [InlineKeyboardButton("Интервал 3с", callback_data="interval_3"),
                 InlineKeyboardButton("5с", callback_data="interval_5")],
                [InlineKeyboardButton("Бан 1с", callback_data="ban_1"),
                 InlineKeyboardButton("3с", callback_data="ban_3")],
                [InlineKeyboardButton("Бан 5с", callback_data="ban_5"),
                 InlineKeyboardButton("10с", callback_data="ban_10")],
                [InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]
            ])
        )

    elif data == "toggle_antispam":
        global ANTISPAM_ENABLED
        ANTISPAM_ENABLED = not ANTISPAM_ENABLED
        await query.edit_message_text(f"Антиспам {'включен' if ANTISPAM_ENABLED else 'выключен'}", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_antispam")]
        ]))

    elif data.startswith("interval_"):
        global ANTISPAM_INTERVAL
        ANTISPAM_INTERVAL = int(data.split("_")[1])
        await query.edit_message_text(f"Интервал: {ANTISPAM_INTERVAL}с", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_antispam")]
        ]))

    elif data.startswith("ban_"):
        global ANTISPAM_BAN_TIME
        ANTISPAM_BAN_TIME = int(data.split("_")[1])
        await query.edit_message_text(f"Время бана: {ANTISPAM_BAN_TIME}с", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_antispam")]
        ]))

    elif data == "admin_create_cell":
        context.user_data["awaiting_cell_name"] = True
        await query.edit_message_text("Введите название ячейки:")

    elif data.startswith("cell_"):
        cell_id = int(data.split("_")[1])
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor()
            cur.execute("SELECT name, description FROM cells WHERE id = %s", (cell_id,))
            cell = cur.fetchone()
            conn.close()
            if cell:
                await query.edit_message_text(f"{cell[0]}\n\n{cell[1]}", reply_markup=cell_owner_keyboard(cell_id))
            else:
                await query.edit_message_text("Ячейка не найдена", reply_markup=admin_keyboard())
        except:
            await query.edit_message_text("Ошибка", reply_markup=admin_keyboard())

    elif data.startswith("edit_cell_"):
        cell_id = int(data.split("_")[2])
        context.user_data["awaiting_edit_cell"] = True
        context.user_data["edit_cell_id"] = cell_id
        await query.edit_message_text("Введите новое описание:")

    elif data.startswith("delete_cell_"):
        cell_id = int(data.split("_")[2])
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor()
            cur.execute("DELETE FROM cells WHERE id = %s", (cell_id,))
            conn.commit()
            conn.close()
            await query.edit_message_text("Ячейка удалена", reply_markup=admin_keyboard())
        except:
            await query.edit_message_text("Ошибка удаления", reply_markup=admin_keyboard())

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    error = context.error
    if "Forbidden: bot was blocked by the user" in str(error):
        logger.warning("403: Пользователь заблокировал бота")
    else:
        logger.error(f"Error: {error}")

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
