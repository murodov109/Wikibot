import os
import json
import asyncio
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
import wikipedia
import requests
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

app = Client("wikipedia_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

DB_FILE = "database.json"

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "users": {},
        "channels": [],
        "searches": {},
        "ads": []
    }

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

db = load_db()

wikipedia.set_lang("uz")

async def check_subscription(user_id):
    if not db["channels"]:
        return True
    for channel in db["channels"]:
        try:
            member = await app.get_chat_member(channel, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            continue
    return True

def subscription_keyboard():
    buttons = []
    for channel in db["channels"]:
        buttons.append([InlineKeyboardButton("📢 Kanalga obuna bo'lish", url=f"https://t.me/{channel.replace('@', '')}")])
    buttons.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(buttons)

def admin_panel_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Kanallar", callback_data="admin_channels")],
        [InlineKeyboardButton("📣 Reklama yuborish", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔍 Eng ko'p qidirilganlar", callback_data="admin_top_searches")],
        [InlineKeyboardButton("❌ Yopish", callback_data="admin_close")]
    ])

def add_user(user_id, username, first_name):
    if str(user_id) not in db["users"]:
        db["users"][str(user_id)] = {
            "username": username,
            "first_name": first_name,
            "joined_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "search_count": 0
        }
        save_db(db)

def add_search(query):
    query_lower = query.lower()
    if query_lower in db["searches"]:
        db["searches"][query_lower] += 1
    else:
        db["searches"][query_lower] = 1
    save_db(db)

@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "No username"
    first_name = message.from_user.first_name or "User"
    add_user(user_id, username, first_name)
    if user_id == ADMIN_ID:
        await message.reply_text("👨‍💼 **Admin Panel**\n\nQuyidagi tugmalardan birini tanlang:", reply_markup=admin_panel_keyboard())
        return
    if not await check_subscription(user_id):
        await message.reply_text("❗️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=subscription_keyboard())
        return
    await message.reply_text(f"👋 Salom {first_name}!\n\n🔍 Men Wikipedia va internetdan ma'lumot qidiradigan botman.\n\n📝 Menga istalgan savolingizni yozing va men sizga:\n• Matn\n• Rasm\n• GIF\n• Video\n\n...kabi formatda javob beraman!\n\n💡 Misol: 'O'zbekiston tarixi' yoki 'Albert Einstein'")

@app.on_callback_query()
async def callback_handler(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data
    if data == "check_sub":
        if await check_subscription(user_id):
            await callback_query.message.delete()
            await callback_query.message.reply_text("✅ Obuna tasdiqlandi!\n\n🔍 Endi menga istalgan savolingizni yuboring.")
        else:
            await callback_query.answer("❌ Siz hali obuna bo'lmagansiz!", show_alert=True)
        return
    if user_id != ADMIN_ID:
        await callback_query.answer("⛔️ Sizda ruxsat yo'q!", show_alert=True)
        return
    if data == "admin_stats":
        total_users = len(db["users"])
        total_searches = sum(db["searches"].values())
        text = f"📊 **Statistika**\n\n👥 Foydalanuvchilar: {total_users}\n🔍 Qidiruvlar: {total_searches}"
        await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]]))
    elif data == "admin_channels":
        channels_text = "📢 **Majburiy kanallar:**\n\n"
        if db["channels"]:
            for i, ch in enumerate(db["channels"], 1):
                channels_text += f"{i}. {ch}\n"
        else:
            channels_text += "Hozircha kanallar yo'q.\n"
        channels_text += "\n💡 Kanal qo'shish: /addchannel @kanal\n💡 Kanalni o'chirish: /removechannel @kanal"
        await callback_query.message.edit_text(channels_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]]))
    elif data == "admin_broadcast":
        await callback_query.message.edit_text("📣 **Reklama yuborish**\n\nYubormoqchi bo'lgan xabaringizni yuboring.\nFormat: /broadcast [xabar]", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]]))
    elif data == "admin_top_searches":
        top = sorted(db["searches"].items(), key=lambda x: x[1], reverse=True)[:10]
        text = "🔍 **Eng ko'p qidirilgan 10 ta so'rov:**\n\n"
        for i, (query, count) in enumerate(top, 1):
            text += f"{i}. {query} - {count} marta\n"
        await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]]))
    elif data == "admin_back":
        await callback_query.message.edit_text("👨‍💼 **Admin Panel**\n\nQuyidagi tugmalardan birini tanlang:", reply_markup=admin_panel_keyboard())
    elif data == "admin_close":
        await callback_query.message.delete()

@app.on_message(filters.command("addchannel") & filters.user(ADMIN_ID))
async def add_channel(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("❌ Format: /addchannel @kanal")
        return
    channel = message.command[1]
    if channel not in db["channels"]:
        db["channels"].append(channel)
        save_db(db)
        await message.reply_text(f"✅ {channel} qo'shildi!")
    else:
        await message.reply_text("❌ Bu kanal allaqachon qo'shilgan!")

@app.on_message(filters.command("removechannel") & filters.user(ADMIN_ID))
async def remove_channel(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("❌ Format: /removechannel @kanal")
        return
    channel = message.command[1]
    if channel in db["channels"]:
        db["channels"].remove(channel)
        save_db(db)
        await message.reply_text(f"✅ {channel} o'chirildi!")
    else:
        await message.reply_text("❌ Bu kanal ro'yxatda yo'q!")

@app.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("❌ Format: /broadcast [xabar]")
        return
    text = message.text.split(None, 1)[1]
    success = 0
    failed = 0
    status_msg = await message.reply_text("📤 Yuborilmoqda...")
    for user_id in db["users"]:
        try:
            await client.send_message(int(user_id), text)
            success += 1
        except:
            failed += 1
        await asyncio.sleep(0.05)
    await status_msg.edit_text(f"✅ Yuborildi: {success}\n❌ Xato: {failed}")

@app.on_message(filters.text & filters.private)
async def search_handler(client, message: Message):
    user_id = message.from_user.id
    if message.text.startswith('/'):
        return
    if not await check_subscription(user_id):
        await message.reply_text("❗️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=subscription_keyboard())
        return
    query = message.text
    add_search(query)
    if str(user_id) in db["users"]:
        db["users"][str(user_id)]["search_count"] += 1
        save_db(db)
    processing = await message.reply_text("🔍 Qidiryapman...")
    try:
        results = wikipedia.search(query, results=5)
        if results:
            try:
                page = wikipedia.page(results[0])
                summary = page.summary[:1000] + "..." if len(page.summary) > 1000 else page.summary
                response = f"📖 **{page.title}**\n\n{summary}\n\n🔗 [Batafsil o'qish]({page.url})"
                if page.images:
                    try:
                        await message.reply_photo(page.images[0], caption=response)
                        await processing.delete()
                        return
                    except:
                        pass
                await processing.edit_text(response, disable_web_page_preview=False)
                return
            except:
                pass
        search_url = f"https://www.google.com/search?q={query}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(search_url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        search_results = soup.find_all('div', class_='BNeawe')
        if search_results:
            result_text = f"🌐 **Google natijasi:** {query}\n\n"
            result_text += search_results[0].get_text()[:500] + "..."
            await processing.edit_text(result_text)
        else:
            await processing.edit_text("❌ Afsuski, ma'lumot topilmadi. Boshqa so'rov kiriting.")
    except Exception as e:
        logger.error(f"Error: {e}")
        await processing.edit_text("❌ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.")

if __name__ == "__main__":
    print("🚀 Bot ishga tushdi...")
    app.run()
