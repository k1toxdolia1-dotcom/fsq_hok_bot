
    
import sqlite3
import random
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
import logging

# --- НАСТРОЙКИ ---
TOKEN = "8359158895:AAHcqKGvgV-12NB-y3C1b2jDxONb5DFYmgs"
COOLDOWN_MINUTES = 120  # 2 часа
DB_NAME = "cards.db"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            rarity TEXT DEFAULT 'Common',
            image_name TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            user_id INTEGER NOT NULL,
            card_id INTEGER NOT NULL,
            obtained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, card_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cooldowns (
            user_id INTEGER PRIMARY KEY,
            last_card_time TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER PRIMARY KEY,
            card_id INTEGER NOT NULL
        )
    ''')
    
    cursor.execute("SELECT COUNT(*) FROM cards")
    if cursor.fetchone()[0] == 0:
        sample = [
            ("Долия", "Лучшая роум-мурчалка", "Legendary", "dolia.jpg"),
            ("Ли Синь", "Легендарный мечник тьмы", "Legendary", "li_xin.jpg"),
            ("Микаса", "Верный страж свободы", "Epic", "mikasa.jpg"),
            ("Май Ширануи", "Королева вееров", "Epic", "mai.jpg"),
            ("Да Цяо", "Хранительница порталов", "Rare", "da_qiao.jpg"),
            ("Кайто", "Властелин ночного неона", "Common", "kaito.jpg"),
            ("Соня", "Маленькая принцесса Hello Kitty", "Rare", "sonya.jpg"),
            ("Джамбич", "Легенда бесплатного доната", "Legendary", "jambich.jpg")
        ]
        cursor.executemany("INSERT INTO cards (name, description, rarity, image_name) VALUES (?, ?, ?, ?)", sample)
        conn.commit()
    conn.close()

# --- ФУНКЦИИ БАЗЫ ДАННЫХ ---
def get_missing_cards(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, description, rarity, image_name
        FROM cards
        WHERE id NOT IN (SELECT card_id FROM inventory WHERE user_id = ?)
    ''', (user_id,))
    result = cursor.fetchall()
    conn.close()
    return result

def get_user_inventory(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.id, c.name, c.description, c.rarity, c.image_name
        FROM inventory i
        JOIN cards c ON i.card_id = c.id
        WHERE i.user_id = ?
    ''', (user_id,))
    result = cursor.fetchall()
    conn.close()
    return result

def add_card_to_inventory(user_id, card_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO inventory (user_id, card_id) VALUES (?, ?)", (user_id, card_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

# --- ИЗБРАННАЯ КАРТА ---
def set_favorite_card(user_id, card_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO favorites (user_id, card_id) VALUES (?, ?)", (user_id, card_id))
    conn.commit()
    conn.close()

def get_favorite_card(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT card_id FROM favorites WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

# --- КУЛДАУН ---
def get_cooldown(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT last_card_time FROM cooldowns WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def set_cooldown(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO cooldowns (user_id, last_card_time) VALUES (?, ?)", (user_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def is_cooldown_expired(user_id):
    last_time = get_cooldown(user_id)
    if not last_time: 
        return True
    return datetime.now() - datetime.fromisoformat(last_time) > timedelta(minutes=COOLDOWN_MINUTES)

def get_remaining_cooldown(user_id):
    last_time = get_cooldown(user_id)
    if not last_time: 
        return 0
    elapsed = (datetime.now() - datetime.fromisoformat(last_time)).total_seconds()
    remaining = COOLDOWN_MINUTES * 60 - elapsed
    return max(0, int(remaining))

# --- КОМАНДЫ БОТА ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Добро пожаловать в HoK Collection!\n\n"
        "🎴 /card - Получить новую карту (уникальную)\n"
        "📦 /inventory - Посмотреть коллекцию\n"
        "⭐ /setfav - Выбрать любимую карту\n"
        "💖 /profile - Показать профиль с любимой картой"
    )

async def card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_cooldown_expired(user_id):
        remaining = get_remaining_cooldown(user_id)
        m, s = divmod(remaining, 60)
        await update.message.reply_text(f"⏳ Новая карта через {m} мин {s} сек!")
        return
    
    missing = get_missing_cards(user_id)
    
    if not missing:
        await update.message.reply_text("🎉 Ты собрал абсолютно ВСЕ карты! Ты — легенда коллекции!")
        return
    
    card_data = random.choice(missing)
    card_id, name, desc, rarity, image = card_data
    
    add_card_to_inventory(user_id, card_id)
    emoji = {"Legendary": "⭐", "Epic": "🔶", "Rare": "🔷", "Common": "⚪"}.get(rarity, "⬜")
    
    try:
        with open(f"cards/{image}", 'rb') as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=f"{emoji} {name}\n📝 {desc}\n🏷 {rarity}\n🆕 Уникальная коллекция!"
            )
    except FileNotFoundError:
        await update.message.reply_text(f"{emoji} {name}\n📝 {desc}\n🏷 {rarity}\n(Фото {image} не найдено)")
    
    set_cooldown(user_id)

async def inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    inv = get_user_inventory(user_id)
    
    if not inv:
        await update.message.reply_text("📭 У тебя пока нет карт. Используй /card!")
        return
    
    msg = "📦 Твоя коллекция:\n\n"
    for c in inv:
        msg += f"• {c[3]} {c[1]}\n"
    msg += f"\n📊 Всего: {len(inv)} карт"
    await update.message.reply_text(msg)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    fav_id = get_favorite_card(user_id)
    
    if fav_id is None:
        await update.message.reply_text("💔 У тебя пока нет любимой карты. Используй /setfav чтобы выбрать!")
        return
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name, description, rarity, image_name FROM cards WHERE id = ?", (fav_id,))
    card = cursor.fetchone()
    conn.close()
    
    if not card:
        await update.message.reply_text("❌ Ошибка: карта не найдена в базе.")
        return
    
    name, desc, rarity, image = card
    emoji = {"Legendary": "⭐", "Epic": "🔶", "Rare": "🔷", "Common": "⚪"}.get(rarity, "⬜")
    
    try:
        with open(f"cards/{image}", 'rb') as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=f"💖 Твоя любимая карта:\n\n{emoji} {name}\n📝 {desc}\n🏷 {rarity}"
            )
    except FileNotFoundError:
        await update.message.reply_text(f"💖 Твоя любимая карта: {emoji} {name}")

async def setfav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    inv = get_user_inventory(user_id)
    
    if not inv:
        await update.message.reply_text("📭 Сначала собери хоть одну карту через /card!")
        return
    
    keyboard = []
    for card in inv:
        card_id, name, desc, rarity, image = card
        emoji = {"Legendary": "⭐", "Epic": "🔶", "Rare": "🔷", "Common": "⚪"}.get(rarity, "⬜")
        keyboard.append([InlineKeyboardButton(f"{emoji} {name}", callback_data=f"fav_{card_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("⭐ Выбери свою любимую карту:", reply_markup=reply_markup)

async def fav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    card_id = int(query.data.split("_")[1])
    
    set_favorite_card(user_id, card_id)
    await query.edit_message_text("✅ Любимая карта обновлена! Используй /profile чтобы посмотреть.")

# --- ЗАПУСК БОТА ---
def main():
    init_db()
    os.makedirs("cards", exist_ok=True)
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("card", card))
    app.add_handler(CommandHandler("inventory", inventory))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("setfav", setfav))
    app.add_handler(CallbackQueryHandler(fav_callback, pattern="fav_"))
    
    print("✅ Бот запущен (без повторов, есть избранная карта!)")
    app.run_polling()

if __name__ == "__main__":
    main()
