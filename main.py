import os
import json
import asyncio
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import wikipedia
import requests
from bs4 import BeautifulSoup
import logging
import re
from shazamio import Shazam
import urllib.parse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

app = Client("wikipedia_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

DB_FILE = "database.json"

IMAGE_APIS = [
    {"name": "Pollinations Enhanced", "url": lambda p: f"https://image.pollinations.ai/prompt/{p}?width=1024&height=1024&nologo=true&enhance=true"},
    {"name": "Pollinations Alt", "url": lambda p: f"https://pollinations.ai/p/{p}?width=1024&height=1024&nologo=true"},
    {"name": "Pollinations Standard", "url": lambda p: f"https://image.pollinations.ai/prompt/{p}?width=1024&height=1024"}
]

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "users": {},
        "channels": [],
        "searches": {},
        "ads": [],
        "user_language": {},
        "admin_state": {}
    }

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

db = load_db()

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

def language_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇺🇿 O'zbek", callback_data="lang_uz")],
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")]
    ])

def admin_panel_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📊 Statistika"), KeyboardButton("📢 Kanallar")],
        [KeyboardButton("📣 Reklama"), KeyboardButton("🔍 Top qidiruvlar")],
        [KeyboardButton("❌ Panelni yopish")]
    ], resize_keyboard=True)

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

def get_user_language(user_id):
    return db.get("user_language", {}).get(str(user_id), "uz")

def set_user_language(user_id, lang):
    if "user_language" not in db:
        db["user_language"] = {}
    db["user_language"][str(user_id)] = lang
    save_db(db)

def get_admin_state(user_id):
    return db.get("admin_state", {}).get(str(user_id), None)

def set_admin_state(user_id, state):
    if "admin_state" not in db:
        db["admin_state"] = {}
    db["admin_state"][str(user_id)] = state
    save_db(db)

async def ai_analyze_and_answer(query, collected_info, language="uz"):
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        
        lang_instruction = {
            "uz": "O'zbek tilida javob ber",
            "ru": "Ответь на русском языке",
            "en": "Answer in English"
        }
        
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        system_prompt = f"""Siz professional ma'lumot tahlilchisisiz. Foydalanuvchi savoliga to'liq, aniq va tushunarli javob bering.

Qoidalar:
1. {lang_instruction.get(language, 'O\'zbek tilida javob ber')}
2. Ma'lumotni tartibli va ravon tarzda yozing
3. Muhim faktlarni ajratib ko'rsating
4. Agar ma'lumot yetarli bo'lmasa, mavjud ma'lumot asosida javob bering
5. Javobni 2000 belgidan oshmasin
6. Emoji va formatlardan foydalaning
7. Har doim to'liq javob qaytaring, "ma'lumot topilmadi" deb javob bermang"""

        user_prompt = f"""Savol: {query}

Yig'ilgan ma'lumotlar:
{collected_info}

Ushbu savol va ma'lumotlar asosida to'liq, aniq va foydali javob tayyorlang."""

        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 2000
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            return None
    except Exception as e:
        logger.error(f"AI Error: {e}")
        return None

async def generate_image(prompt, message):
    try:
        encoded_prompt = urllib.parse.quote(prompt)
        
        for api in IMAGE_APIS:
            try:
                image_url = api["url"](encoded_prompt)
                await message.reply_photo(
                    image_url,
                    caption=f"🎨 **Rasm yaratildi!**\n\n📝 Prompt: {prompt}\n🔧 API: {api['name']}"
                )
                return True
            except Exception as e:
                logger.error(f"{api['name']} error: {e}")
                continue
        
        return False
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        return False

async def recognize_music(file_path):
    try:
        shazam = Shazam()
        result = await shazam.recognize_song(file_path)
        
        if result and 'track' in result:
            track = result['track']
            title = track.get('title', 'Noma\'lum')
            artist = track.get('subtitle', 'Noma\'lum')
            cover = track.get('images', {}).get('coverart', '')
            
            sections = track.get('sections', [])
            youtube_link = None
            
            for section in sections:
                if section.get('type') == 'VIDEO':
                    items = section.get('youtubeids', {}).get('actions', [])
                    if items:
                        youtube_id = items[0].get('id')
                        if youtube_id:
                            youtube_link = f"https://www.youtube.com/watch?v={youtube_id}"
                            break
            
            return {
                "title": title,
                "artist": artist,
                "cover": cover,
                "youtube": youtube_link
            }
        
        return None
    except Exception as e:
        logger.error(f"Shazam error: {e}")
        return None

async def search_wikipedia(query, language="uz"):
    results = []
    try:
        wiki_lang = {"uz": "uz", "ru": "ru", "en": "en"}
        wikipedia.set_lang(wiki_lang.get(language, "uz"))
        
        search_results = wikipedia.search(query, results=3)
        
        for result in search_results:
            try:
                page = wikipedia.page(result)
                results.append({
                    "source": "Wikipedia",
                    "title": page.title,
                    "content": page.summary[:1500],
                    "url": page.url,
                    "images": page.images[:3] if page.images else []
                })
            except:
                continue
    except:
        pass
    
    return results

async def search_google(query):
    results = []
    try:
        search_url = f"https://www.google.com/search?q={query}&num=5"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(search_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for g in soup.find_all('div', class_='g'):
            try:
                title = g.find('h3')
                description = g.find('div', class_='VwiC3b')
                link = g.find('a')
                
                if title and description and link:
                    results.append({
                        "source": "Google",
                        "title": title.get_text(),
                        "content": description.get_text(),
                        "url": link.get('href', '')
                    })
            except:
                continue
                
        if not results:
            divs = soup.find_all('div', class_='BNeawe')
            for i, div in enumerate(divs[:5]):
                results.append({
                    "source": "Google",
                    "title": f"Natija {i+1}",
                    "content": div.get_text()
                })
    except:
        pass
    
    return results

async def search_duckduckgo(query):
    results = []
    try:
        url = f"https://api.duckduckgo.com/?q={query}&format=json"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get('Abstract'):
            results.append({
                "source": "DuckDuckGo",
                "title": data.get('Heading', 'Abstract'),
                "content": data.get('Abstract'),
                "url": data.get('AbstractURL', '')
            })
        
        for topic in data.get('RelatedTopics', [])[:3]:
            if isinstance(topic, dict) and 'Text' in topic:
                results.append({
                    "source": "DuckDuckGo",
                    "title": topic.get('Text', '')[:100],
                    "content": topic.get('Text', ''),
                    "url": topic.get('FirstURL', '')
                })
    except:
        pass
    
    return results

async def search_bing(query):
    results = []
    try:
        search_url = f"https://www.bing.com/search?q={query}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(search_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for result in soup.find_all('li', class_='b_algo')[:3]:
            try:
                title = result.find('h2')
                desc = result.find('p')
                link = result.find('a')
                
                if title and desc:
                    results.append({
                        "source": "Bing",
                        "title": title.get_text(),
                        "content": desc.get_text(),
                        "url": link.get('href', '') if link else ''
                    })
            except:
                continue
    except:
        pass
    
    return results

@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "No username"
    first_name = message.from_user.first_name or "User"
    add_user(user_id, username, first_name)
    
    if user_id == ADMIN_ID:
        await message.reply_text(
            "👨‍💼 **Admin Panel**\n\nQuyidagi tugmalardan foydalaning:",
            reply_markup=admin_panel_keyboard()
        )
        return
    
    if not await check_subscription(user_id):
        await message.reply_text("❗️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=subscription_keyboard())
        return
    
    lang = get_user_language(user_id)
    
    messages = {
        "uz": f"👋 Salom {first_name}!\n\n🤖 Men AI bilan ishlaydigan ko'p funksiyali botman!\n\n📚 **Qidiruv:**\nIstalgan savolni yuboring\n\n🎨 **Rasm yaratish:**\n/image [tavsif]\nMisol: /image kosmosdagi mushuk\n\n🎵 **Musiqa tanish:**\nAudio yuborib \"musiqa\" deb yozing\n\n🌍 Tilni tanlash: /language",
        "ru": f"👋 Привет {first_name}!\n\n🤖 Я многофункциональный AI бот!\n\n📚 **Поиск:**\nОтправьте любой вопрос\n\n🎨 **Создание изображений:**\n/image [описание]\nПример: /image кот в космосе\n\n🎵 **Распознавание музыки:**\nОтправьте аудио и напишите \"музыка\"\n\n🌍 Язык: /language",
        "en": f"👋 Hello {first_name}!\n\n🤖 I'm a multi-functional AI bot!\n\n📚 **Search:**\nSend any question\n\n🎨 **Image generation:**\n/image [description]\nExample: /image cat in space\n\n🎵 **Music recognition:**\nSend audio and write \"music\"\n\n🌍 Language: /language"
    }
    
    await message.reply_text(messages.get(lang, messages["uz"]))

@app.on_message(filters.command("image"))
async def image_command(client, message: Message):
    user_id = message.from_user.id
    
    if not await check_subscription(user_id):
        await message.reply_text("❗️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=subscription_keyboard())
        return
    
    if len(message.command) < 2:
        lang = get_user_language(user_id)
        texts = {
            "uz": "❌ Format: /image [tavsif]\n\nMisol:\n/image go'zal tog'lar\n/image kosmosdagi mushuk",
            "ru": "❌ Формат: /image [описание]\n\nПример:\n/image красивые горы\n/image кот в космосе",
            "en": "❌ Format: /image [description]\n\nExample:\n/image beautiful mountains\n/image cat in space"
        }
        await message.reply_text(texts.get(lang, texts["uz"]))
        return
    
    prompt = message.text.split(None, 1)[1]
    processing = await message.reply_text("🎨 Rasm yaratyapman...")
    
    success = await generate_image(prompt, message)
    
    if success:
        await processing.delete()
    else:
        await processing.edit_text("❌ Rasm yaratishda xatolik. Qaytadan urinib ko'ring.")

@app.on_message(filters.command("language"))
async def language_command(client, message: Message):
    lang = get_user_language(message.from_user.id)
    
    texts = {
        "uz": "🌍 Tilni tanlang:",
        "ru": "🌍 Выберите язык:",
        "en": "🌍 Choose language:"
    }
    
    await message.reply_text(texts.get(lang, texts["uz"]), reply_markup=language_keyboard())

@app.on_message(filters.audio | filters.voice)
async def audio_handler(client, message: Message):
    user_id = message.from_user.id
    
    if not await check_subscription(user_id):
        await message.reply_text("❗️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=subscription_keyboard())
        return
    
    lang = get_user_language(user_id)
    
    processing_texts = {
        "uz": "🎵 Musiqa tanilmoqda...",
        "ru": "🎵 Распознаю музыку...",
        "en": "🎵 Recognizing music..."
    }
    
    processing = await message.reply_text(processing_texts.get(lang, processing_texts["uz"]))
    
    try:
        file = await client.download_media(message)
        
        result = await recognize_music(file)
        
        if result:
            response = f"🎵 **Musiqa topildi!**\n\n"
            response += f"🎤 Qo'shiq: {result['title']}\n"
            response += f"👤 Ijrochi: {result['artist']}\n"
            
            if result['youtube']:
                response += f"🔗 YouTube: {result['youtube']}"
            
            if result['cover']:
                try:
                    await message.reply_photo(result['cover'], caption=response)
                    await processing.delete()
                except:
                    await processing.edit_text(response)
            else:
                await processing.edit_text(response)
        else:
            error_texts = {
                "uz": "❌ Musiqa tanilmadi. Boshqa audio yuboring.",
                "ru": "❌ Музыка не распознана. Отправьте другое аудио.",
                "en": "❌ Music not recognized. Send another audio."
            }
            await processing.edit_text(error_texts.get(lang, error_texts["uz"]))
        
        if os.path.exists(file):
            os.remove(file)
    
    except Exception as e:
        logger.error(f"Audio error: {e}")
        await processing.edit_text("❌ Xatolik yuz berdi.")

@app.on_callback_query()
async def callback_handler(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    if data.startswith("lang_"):
        lang = data.split("_")[1]
        set_user_language(user_id, lang)
        
        messages = {
            "uz": "✅ Til o'zgartirildi: O'zbek",
            "ru": "✅ Язык изменен: Русский",
            "en": "✅ Language changed: English"
        }
        
        await callback_query.answer(messages.get(lang, messages["uz"]), show_alert=True)
        await callback_query.message.delete()
        return
    
    if data == "check_sub":
        if await check_subscription(user_id):
            await callback_query.message.delete()
            
            lang = get_user_language(user_id)
            texts = {
                "uz": "✅ Obuna tasdiqlandi!\n\n🔍 Endi menga istalgan savolingizni yuboring.",
                "ru": "✅ Подписка подтверждена!\n\n🔍 Теперь задайте мне любой вопрос.",
                "en": "✅ Subscription confirmed!\n\n🔍 Now ask me anything."
            }
            
            await callback_query.message.reply_text(texts.get(lang, texts["uz"]))
        else:
            lang = get_user_language(user_id)
            texts = {
                "uz": "❌ Siz hali obuna bo'lmagansiz!",
                "ru": "❌ Вы еще не подписались!",
                "en": "❌ You haven't subscribed yet!"
            }
            await callback_query.answer(texts.get(lang, texts["uz"]), show_alert=True)
        return

@app.on_message(filters.text & filters.user(ADMIN_ID) & ~filters.command("start"))
async def admin_message_handler(client, message: Message):
    text = message.text
    state = get_admin_state(ADMIN_ID)
    
    if text == "❌ Panelni yopish":
        set_admin_state(ADMIN_ID, None)
        await message.reply_text("✅ Admin panel yopildi", reply_markup=ReplyKeyboardRemove())
        return
    
    if text == "📊 Statistika":
        total_users = len(db["users"])
        total_searches = sum(db["searches"].values())
        stats_text = f"📊 **Statistika**\n\n👥 Foydalanuvchilar: {total_users}\n🔍 Qidiruvlar: {total_searches}"
        await message.reply_text(stats_text)
        return
    
    if text == "📢 Kanallar":
        channels_text = "📢 **Majburiy kanallar:**\n\n"
        if db["channels"]:
            for i, ch in enumerate(db["channels"], 1):
                channels_text += f"{i}. {ch}\n"
        else:
            channels_text += "Hozircha kanallar yo'q.\n"
        channels_text += "\n💡 Kanal qo'shish: /addchannel @kanal\n💡 Kanalni o'chirish: /removechannel @kanal"
        await message.reply_text(channels_text)
        return
    
    if text == "📣 Reklama":
        set_admin_state(ADMIN_ID, "broadcast")
        await message.reply_text("📣 Yubormoqchi bo'lgan xabaringizni yuboring:")
        return
    
    if text == "🔍 Top qidiruvlar":
        top = sorted(db["searches"].items(), key=lambda x: x[1], reverse=True)[:10]
        top_text = "🔍 **Eng ko'p qidirilgan 10 ta so'rov:**\n\n"
        for i, (query, count) in enumerate(top, 1):
            top_text += f"{i}. {query} - {count} marta\n"
        await message.reply_text(top_text)
        return
    
    if state == "broadcast":
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
        set_admin_state(ADMIN_ID, None)
        return

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

@app.on_message(filters.text & filters.private & ~filters.user(ADMIN_ID))
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
    
    lang = get_user_language(user_id)
    
    status_texts = {
        "uz": "🔍 Qidiryapman...",
        "ru": "🔍 Ищу...",
        "en": "🔍 Searching..."
    }
    
    processing = await message.reply_text(status_texts.get(lang, status_texts["uz"]))
    
    try:
        all_results = []
        images = []
        
        wiki_results = await search_wikipedia(query, lang)
        all_results.extend(wiki_results)
        
        for result in wiki_results:
            if result.get("images"):
                images.extend(result["images"])
        
        google_results = await search_google(query)
        all_results.extend(google_results)
        
        ddg_results = await search_duckduckgo(query)
        all_results.extend(ddg_results)
        
        bing_results = await search_bing(query)
        all_results.extend(bing_results)
        
        if all_results:
            collected_info = ""
            for i, result in enumerate(all_results[:10], 1):
                collected_info += f"\n\n--- Manba {i} ({result['source']}) ---\n"
                collected_info += f"Sarlavha: {result.get('title', 'N/A')}\n"
                collected_info += f"Ma'lumot: {result.get('content', 'N/A')[:500]}\n"
                if result.get('url'):
                    collected_info += f"Havola: {result['url']}\n"
            
            await processing.edit_text(status_texts.get(lang, "🤖 AI tahlil qilyapti...").replace("Qidiryapman", "AI tahlil qilyapti").replace("Ищу", "AI анализирует").replace("Searching", "AI analyzing"))
            
            ai_response = await ai_analyze_and_answer(query, collected_info, lang)
            
            if ai_response:
                if images and len(images) > 0:
                    try:
                        await message.reply_photo(
                            images[0],
                            caption=f"🤖 **AI Javob:**\n\n{ai_response[:900]}"
                        )
                        await processing.delete()
                        return
                    except:
                        pass
                
                await processing.edit_text(f"🤖 **AI Javob:**\n\n{ai_response}")
            else:
                simple_response = f"📚 **{all_results[0]['title']}**\n\n{all_results[0]['content'][:1000]}"
                if all_results[0].get('url'):
                    simple_response += f"\n\n🔗 [Batafsil]({all_results[0]['url']})"
                
                await processing.edit_text(simple_response, disable_web_page_preview=False)
        else:
            fallback_texts = {
                "uz": "🔍 Keling, boshqa usulda qidiramiz...",
                "ru": "🔍 Давайте попробуем другой способ...",
                "en": "🔍 Let me try another way..."
            }
            
            await processing.edit_text(fallback_texts.get(lang, fallback_texts["uz"]))
            
            ai_response = await ai_analyze_and_answer(
                query, 
                f"Foydalanuvchi '{query}' haqida so'radi. Umumiy bilimlaringiz asosida javob bering.",
                lang
            )
            
            if ai_response:
                await message.reply_text(f"🤖 **AI Javob:**\n\n{ai_response}")
            else:
                error_texts = {
                    "uz": "❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.",
                    "ru": "❌ Произошла ошибка. Попробуйте снова.",
                    "en": "❌ An error occurred. Please try again."
                }
                await processing.edit_text(error_texts.get(lang, error_texts["uz"]))
    
    except Exception as e:
        logger.error(f"Error: {e}")
        error_texts = {
            "uz": "❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.",
            "ru": "❌ Произошла ошибка. Попробуйте снова.",
            "en": "❌ An error occurred. Please try again."
        }
        await processing.edit_text(error_texts.get(lang, error_texts["uz"]))

if __name__ == "__main__":
    print("🚀 Bot ishga tushdi...")
    app.run()
