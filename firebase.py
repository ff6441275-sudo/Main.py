import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
import firebase_admin
from firebase_admin import credentials, db

# Logging setup
logging.basicConfig(level=logging.INFO)

# Configuration
BOT_TOKEN = "9029198385:AAGvJ7hub3dHU-_K_D4QOda7gRyNGzQIz1w"
OWNER_ID = 8241730977
OWNER_USERNAME = "@Sakira540"

# Safe Firebase Initialization
FIREBASE_ACTIVE = False
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate("firebase_key.json")
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://your-firebase-default-rtdb.firebaseio.com/'
        })
    FIREBASE_ACTIVE = True
    print("Firebase Connected Successfully!")
except Exception as e:
    print(f"Firebase Warning/Error: {e}")
    FIREBASE_ACTIVE = False

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()

def is_admin(user_id: int) -> bool:
    return user_id == OWNER_ID

def get_config(key, default):
    if FIREBASE_ACTIVE:
        try:
            val = db.reference(f"config/{key}").get()
            return val if val else default
        except Exception:
            pass
    return default

async def check_subscription(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    channel = get_config("channel", "@TG_CHEATS_GEN")
    if not channel:
        return True
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except TelegramBadRequest:
        pass
    except Exception:
        pass
    return True  # Fallback to true if channel check fails so bot doesn't get stuck

@dp.message(Command("start"))
async def cmd_start(message: Message):
    try:
        user_id = message.from_user.id
        channel = get_config("channel", "@TG_CHEATS_GEN")
        
        # 1. Force Subscription Check
        if not await check_subscription(user_id):
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Join Channel", url=f"https://t.me/{channel.replace('@', '')}")],
                [InlineKeyboardButton(text="🔄 Try Again", callback_data="check_sub")]
            ])
            await message.answer(f"❌ <b>Access nahi hai!</b>\n\nPehle hamara channel {channel} join karein phir bot use karein:", reply_markup=kb)
            return

        # 2. Firebase User Registration
        if FIREBASE_ACTIVE:
            try:
                ref = db.reference(f"users/{user_id}")
                if not ref.get():
                    ref.set({
                        "username": message.from_user.username or "NoUsername",
                        "joined_date": message.date.strftime("%Y-%m-%d %H:%M:%S")
                    })
            except Exception:
                pass

        # 3. Main Interface
        welcome_text = (
            f"🔥 <b>WELCOME TRUSTED SELLER TO THE BOT</b> 🔥\n\n"
            f"✨ <b>Owner:</b> {OWNER_USERNAME}\n"
            f"🤖 <b>Status:</b> Online & Free Active 🚀\n\n"
            f"Neeche diye gaye buttons ka use karein:"
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Stats", callback_data="btn_stats"), InlineKeyboardButton(text="🔍 Scan / Lookup", callback_data="btn_scan")],
            [InlineKeyboardButton(text="ℹ️ Info", callback_data="btn_info"), InlineKeyboardButton(text="⚙️ Admin Panel", callback_data="admin_panel")]
        ])

        image_id = get_config("image_id", None)
        video_id = get_config("video_id", None)

        if video_id:
            await message.answer_video(video=video_id, caption=welcome_text, reply_markup=kb)
        elif image_id:
            await message.answer_photo(photo=image_id, caption=welcome_text, reply_markup=kb)
        else:
            await message.answer(welcome_text, reply_markup=kb)
            
    except Exception as e:
        print(f"Error in start handler: {e}")

@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(callback: CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.edit_text("✅ <b>Verification Successful!</b> Ab bot use karne ke liye `/start` bhejein.")
    else:
        await callback.answer("❌ Aapne abhi tak channel join nahi kiya hai!", show_alert=True)

@dp.callback_query(F.data == "btn_scan")
async def cb_scan(callback: CallbackQuery):
    await callback.message.answer("🔍 <b>Free Scan / Lookup Mode Active:</b>\n\nKripya query ya data bhejein.")
    await callback.answer()

@dp.callback_query(F.data == "btn_stats")
async def cb_stats(callback: CallbackQuery):
    total = 0
    if FIREBASE_ACTIVE:
        try:
            users_data = db.reference("users").get()
            if users_data:
                total = len(users_data)
        except Exception:
            pass
    await callback.message.answer(f"📊 <b>Bot Info:</b>\n• Total Users: {total}\n• Status: Free & Unlimited ✅")
    await callback.answer()

@dp.callback_query(F.data == "btn_info")
async def cb_info(callback: CallbackQuery):
    channel = get_config("channel", "@TG_CHEATS_GEN")
    await callback.message.answer(f"ℹ️ <b>Bot Details:</b>\n\n• Owner: {OWNER_USERNAME}\n• Required Channel: {channel}\n• Mode: Free Access")
    await callback.answer()

# --- ADMIN PANEL ---
@dp.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⚠️ Ye sirf Owner ke liye hai!", show_alert=True)
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="adm_bc_info")],
        [InlineKeyboardButton(text="📢 Set Channel", callback_data="adm_ch_info")],
        [InlineKeyboardButton(text="🖼️ Set/Remove Media", callback_data="adm_media_info")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="back_start")]
    ])
    await callback.message.edit_text("👑 <b>Admin Control Panel (Free Mode)</b>\n\nCommands list:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "adm_bc_info")
async def cb_bc_info(callback: CallbackQuery):
    await callback.answer("Use: Kisi message ko reply karke /broadcast likhein.", show_alert=True)

@dp.callback_query(F.data == "adm_ch_info")
async def cb_ch_info(callback: CallbackQuery):
    await callback.answer("Use: /setchannel @channelname", show_alert=True)

@dp.callback_query(F.data == "adm_media_info")
async def cb_media_info(callback: CallbackQuery):
    await callback.answer("Use: Photo/Video par reply karke /setimage ya /setvideo likhein. Remove ke liye /removemedia", show_alert=True)

@dp.callback_query(F.data == "back_start")
async def cb_back(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Stats", callback_data="btn_stats"), InlineKeyboardButton(text="🔍 Scan / Lookup", callback_data="btn_scan")],
        [InlineKeyboardButton(text="ℹ️ Info", callback_data="btn_info"), InlineKeyboardButton(text="⚙️ Admin Panel", callback_data="admin_panel")]
    ])
    await callback.message.edit_text(f"🔥 <b>WELCOME TRUSTED SELLER TO THE BOT</b> 🔥\n\n✨ <b>Owner:</b> {OWNER_USERNAME}", reply_markup=kb)
    await callback.answer()

# --- ADMIN COMMANDS ---
@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if not is_admin(message.from_user.id):
        return
    if not message.reply_to_message:
        await message.reply("⚠️ Kisi message ko reply karke `/broadcast` likhein.")
        return
    
    success = 0
    if FIREBASE_ACTIVE:
        try:
            users = db.reference("users").get()
            if users:
                for uid in users.keys():
                    try:
                        await message.reply_to_message.copy(chat_id=int(uid))
                        success += 1
                    except Exception:
                        pass
        except Exception:
            pass
    await message.reply(f"🚀 Broadcast sent to {success} users successfully!")

@dp.message(Command("setchannel"))
async def cmd_setchannel(message: Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        await message.reply("⚠️ Format: `/setchannel @channelusername`")
        return
    new_ch = args[1]
    if FIREBASE_ACTIVE:
        db.reference("config/channel").set(new_ch)
        await message.reply(f"✅ Force subscription channel successfully updated to: <code>{new_ch}</code>")

@dp.message(Command("setimage"))
async def cmd_setimage(message: Message):
    if not is_admin(message.from_user.id):
        return
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply("⚠️ Kisi photo par reply karke `/setimage` likhein.")
        return
    photo_id = message.reply_to_message.photo[-1].file_id
    if FIREBASE_ACTIVE:
        db.reference("config/image_id").set(photo_id)
        db.reference("config/video_id").delete()
        await message.reply("✅ Welcome image successfully set!")

@dp.message(Command("setvideo"))
async def cmd_setvideo(message: Message):
    if not is_admin(message.from_user.id):
        return
    if not message.reply_to_message or not message.reply_to_message.video:
        await message.reply("⚠️ Kisi video par reply karke `/setvideo` likhein.")
        return
    video_id = message.reply_to_message.video.file_id
    if FIREBASE_ACTIVE:
        db.reference("config/video_id").set(video_id)
        db.reference("config/image_id").delete()
        await message.reply("✅ Welcome video successfully set!")

@dp.message(Command("removemedia"))
async def cmd_removemedia(message: Message):
    if not is_admin(message.from_user.id):
        return
    if FIREBASE_ACTIVE:
        db.reference("config/image_id").delete()
        db.reference("config/video_id").delete()
        await message.reply("✅ Welcome image and video successfully removed!")

async def main():
    print("Bot is polling and ready...")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
