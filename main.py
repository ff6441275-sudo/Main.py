import asyncio
import html
import logging
import os
import random
import string
import tempfile
from datetime import datetime, timedelta
import aiosqlite

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    ChatJoinRequest,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    TelegramObject,
)

try:
    from aiogram.enums import ButtonStyle  # type: ignore
except ImportError:
    ButtonStyle = None  # type: ignore


def reply_btn(text: str, style_name: str | None = None) -> KeyboardButton:
    if ButtonStyle is not None and style_name and hasattr(ButtonStyle, style_name):
        return KeyboardButton(text=text, style=getattr(ButtonStyle, style_name))
    return KeyboardButton(text=text)


def inline_btn(text: str, callback_data: str, style_name: str | None = None) -> InlineKeyboardButton:
    if ButtonStyle is not None and style_name and hasattr(ButtonStyle, style_name):
        return InlineKeyboardButton(text=text, callback_data=callback_data, style=getattr(ButtonStyle, style_name))
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def url_btn(text: str, url: str, style_name: str | None = None) -> InlineKeyboardButton:
    if ButtonStyle is not None and style_name and hasattr(ButtonStyle, style_name):
        return InlineKeyboardButton(text=text, url=url, style=getattr(ButtonStyle, style_name))
    return InlineKeyboardButton(text=text, url=url)


# ================= CONFIG =================
BOT_TOKEN = "9197328598:AAFUSx1eYR-N4S5fyQbpvyhAEFpo9sxFPxI"
OWNER_ID = 8682912888
OWNER_USERNAME = "@tcxsu"
DB_PATH = "filestore.db"
FILES_PER_PAGE = 5
PREMIUM_COST = 2000
PREMIUM_DAYS = 7

logging.basicConfig(level=logging.INFO)
router = Router()


# ================= FSM STATES =================
class AdminStates(StatesGroup):
    waiting_file_title = State()
    waiting_file_price = State()
    waiting_file_rarity = State()
    waiting_file_doc = State()
    waiting_add_coin_user = State()
    waiting_add_coin_amount = State()
    waiting_add_gem_user = State()
    waiting_add_gem_amount = State()
    waiting_broadcast = State()
    waiting_redeem_code = State()
    waiting_redeem_coins = State()
    waiting_redeem_uses = State()
    waiting_del_file_id = State()
    waiting_welcome_video = State()
    waiting_profile_photo = State()
    waiting_fsub_add = State()
    waiting_fsub_del = State()
    waiting_add_admin = State()
    waiting_del_admin = State()


class UserStates(StatesGroup):
    waiting_gift_coins = State()
    waiting_redeem_input = State()


# ================= DATABASE =================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                coins INTEGER DEFAULT 0,
                gems INTEGER DEFAULT 0,
                referrals INTEGER DEFAULT 0,
                referred_by INTEGER,
                streak INTEGER DEFAULT 0,
                last_bonus TEXT,
                premium_until TEXT,
                joined_at TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                added_at TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                price INTEGER NOT NULL,
                rarity TEXT DEFAULT 'NORMAL',
                file_id TEXT NOT NULL,
                file_type TEXT DEFAULT 'document',
                purchases INTEGER DEFAULT 0
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_files (
                user_id INTEGER,
                file_id INTEGER,
                bought_at TEXT,
                PRIMARY KEY (user_id, file_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS redeem_codes (
                code TEXT PRIMARY KEY,
                coins INTEGER NOT NULL,
                max_uses INTEGER NOT NULL,
                used_count INTEGER DEFAULT 0
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS redeemed_users (
                code TEXT,
                user_id INTEGER,
                PRIMARY KEY (code, user_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS force_channels (
                chat_id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                invite_link TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS join_requests (
                chat_id INTEGER,
                user_id INTEGER,
                PRIMARY KEY (chat_id, user_id)
            )
            """
        )
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('maintenance', 'off')"
        )
        await db.execute(
            "INSERT OR IGNORE INTO admins (user_id, added_by, added_at) VALUES (?, ?, ?)",
            (OWNER_ID, OWNER_ID, datetime.now().strftime("%Y-%m-%d %H:%M")),
        )
        await db.commit()


async def get_setting(key: str) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        await db.commit()


async def is_maintenance_on() -> bool:
    val = await get_setting("maintenance")
    return (val or "off").strip().lower() == "on"


def is_owner(user_id: int) -> bool:
    return int(user_id) == int(OWNER_ID)


async def is_admin(user_id: int) -> bool:
    if is_owner(user_id):
        return True
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM admins WHERE user_id = ?", (int(user_id),)) as cur:
            return await cur.fetchone() is not None


async def get_all_admin_ids() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM admins ORDER BY user_id ASC") as cur:
            rows = [int(r[0]) for r in await cur.fetchall()]
    if int(OWNER_ID) not in rows:
        rows.insert(0, int(OWNER_ID))
    return rows


def rarity_emoji(rarity: str) -> str:
    r = (rarity or "").upper()
    if r == "PREMIUM":
        return "👑"
    if r == "RARE":
        return "💠"
    return "✨"


# ================= FORCE SUBSCRIBE + JOIN REQUEST =================
@router.chat_join_request()
async def on_chat_join_request(req: ChatJoinRequest):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO join_requests (chat_id, user_id) VALUES (?, ?)",
            (req.chat.id, req.from_user.id),
        )
        await db.commit()


async def get_unjoined_channels(bot: Bot, user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM force_channels ORDER BY chat_id ASC") as cur:
            channels = [dict(r) for r in await cur.fetchall()]
        async with db.execute("SELECT chat_id FROM join_requests WHERE user_id = ?", (user_id,)) as cur2:
            requested_ids = {int(r["chat_id"]) for r in await cur2.fetchall()}

    missing = []
    for ch in channels:
        cid = int(ch["chat_id"])
        if cid in requested_ids:
            continue
        try:
            member = await bot.get_chat_member(cid, user_id)
            if member.status in {
                ChatMemberStatus.CREATOR,
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.MEMBER,
            }:
                continue
        except Exception:
            pass
        missing.append(ch)
    return missing


def build_fsub_keyboard(missing_channels: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for ch in missing_channels:
        rows.append([url_btn(f"📢 {ch['title']}", ch["invite_link"], "PRIMARY")])
    rows.append([inline_btn("✅ VERIFY", "fsub_verify", "SUCCESS")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_access_restricted(target_msg: Message, missing_channels: list[dict], edit: bool = False):
    text = (
        "🔒 <b>ACCESS RESTRICTED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "To Use This Bot, Please Join All Required Channels Below, Then Tap ✅ <b>VERIFY</b>.\n\n"
        "For Private Channels, Sending a Join Request is Enough — The Bot Does Not Approve or Cancel Your Request. "
        "If a Private Button is Missing, The Bot Needs Admin Permission To Create Its Invite Link."
    )
    kb = build_fsub_keyboard(missing_channels)
    if edit:
        try:
            await target_msg.edit_text(text, reply_markup=kb)
            return
        except Exception:
            pass
    await target_msg.answer(text, reply_markup=kb)


# ================= USER & PREMIUM HELPERS =================
async def ensure_user(user_id: int, username: str | None, full_name: str, ref_id: int | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            valid_ref = ref_id if (ref_id and ref_id != user_id) else None
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            await db.execute(
                """
                INSERT INTO users (user_id, username, full_name, coins, referred_by, joined_at)
                VALUES (?, ?, ?, 0, ?, ?)
                """,
                (user_id, username or "", full_name, valid_ref, now_str),
            )
            if valid_ref:
                await db.execute(
                    "UPDATE users SET referrals = referrals + 1, coins = coins + 50 WHERE user_id = ?",
                    (valid_ref,),
                )
            await db.commit()
        else:
            await db.execute(
                "UPDATE users SET username = ?, full_name = ? WHERE user_id = ?",
                (username or "", full_name, user_id),
            )
            await db.commit()


async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


def is_premium_active(user_dict: dict) -> bool:
    prem = user_dict.get("premium_until")
    if not prem:
        return False
    try:
        return datetime.fromisoformat(prem) > datetime.now()
    except ValueError:
        return False


def _extract_user(event: TelegramObject):
    if isinstance(event, Message):
        return event.from_user
    if isinstance(event, CallbackQuery):
        return event.from_user
    if hasattr(event, "message") and getattr(event, "message") is not None:
        return getattr(event.message, "from_user", None)
    if hasattr(event, "callback_query") and getattr(event, "callback_query") is not None:
        return getattr(event.callback_query, "from_user", None)
    return None


# ================= OUTER ACCESS MIDDLEWARE (MAINTENANCE + FORCE SUB) =================
class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = _extract_user(event)
        msg = event.message if isinstance(event, Message) else (
            event.message if isinstance(event, CallbackQuery) else getattr(event, "message", None)
        )
        cb = event.callback_query if hasattr(event, "callback_query") and getattr(event, "callback_query") else (
            event if isinstance(event, CallbackQuery) else None
        )

        if not user or await is_admin(user.id):
            return await handler(event, data)

        if await is_maintenance_on():
            notice = (
                "🛠️ <b>MAINTENANCE MODE ACTIVE</b> ✨\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "⚙️ Bot abhi maintenance mein hai.\n"
                "💫 Thodi der baad dubara try karein!"
            )
            if cb:
                await cb.answer("🛠️ Bot abhi maintenance mein hai!", show_alert=True)
            elif msg:
                await msg.answer(notice)
            return

        if cb and cb.data == "fsub_verify":
            return await handler(event, data)

        bot: Bot = data["bot"]
        missing = await get_unjoined_channels(bot, user.id)
        if missing:
            if cb and cb.message:
                await cb.answer("⚠️ Pehle required channels join karein!", show_alert=True)
                await send_access_restricted(cb.message, missing, edit=False)
            elif msg:
                await send_access_restricted(msg, missing, edit=False)
            return

        return await handler(event, data)


# ================= KEYBOARDS =================
def main_reply_kb(has_admin_access: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [reply_btn("BUY FILES", "SUCCESS")],
        [
            reply_btn("DAILY BONUS", "PRIMARY"),
            reply_btn("MYSTERY BOX", "SUCCESS"),
        ],
        [
            reply_btn("REFER & EARN", "PRIMARY"),
            reply_btn("REDEEM CODE", "DANGER"),
        ],
        [
            reply_btn("MY STATS", "PRIMARY"),
            reply_btn("LEADERBOARD", "PRIMARY"),
        ],
        [
            reply_btn("MY WALLET", "PRIMARY"),
            reply_btn("SUPPORT", "PRIMARY"),
        ],
    ]
    if has_admin_access:
        rows.append([reply_btn("ADMIN PANEL", "DANGER")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_panel_kb(maint_on: bool = False, owner_view: bool = True) -> InlineKeyboardMarkup:
    maint_text = "🛠️ Maint: ON 🔴" if maint_on else "🛠️ Maint: OFF 🟢"
    rows = [
        [
            inline_btn("🎬 Set Video", "adm_set_video", "SUCCESS"),
            inline_btn("🖼️ Set Photo", "adm_set_photo", "PRIMARY"),
        ],
        [
            inline_btn("➕ Add File", "adm_add_file", "SUCCESS"),
            inline_btn("🗑️ Delete File", "adm_del_file", "DANGER"),
        ],
        [
            inline_btn("🪙 Add Coins", "adm_add_coins", "SUCCESS"),
            inline_btn("💎 Add Gems", "adm_add_gems", "PRIMARY"),
        ],
        [
            inline_btn("📢 Add FSub Channel", "adm_fsub_add", "SUCCESS"),
            inline_btn("🚫 Del FSub Channel", "adm_fsub_del", "DANGER"),
        ],
        [
            inline_btn("🎟️ Create Code", "adm_create_code", "PRIMARY"),
            inline_btn("📣 Broadcast", "adm_broadcast", "PRIMARY"),
        ],
        [
            inline_btn(maint_text, "adm_toggle_maint", "DANGER" if maint_on else "SUCCESS"),
            inline_btn("📈 Bot Status", "adm_status", "SUCCESS"),
        ],
        [
            inline_btn("📂 List All Files", "adm_list_files", "PRIMARY"),
            inline_btn("👮 List Admins", "adm_list_admins", "SUCCESS"),
        ],
    ]
    if owner_view:
        rows.append(
            [
                inline_btn("👤 Add Admin", "adm_add_admin", "SUCCESS"),
                inline_btn("❌ Del Admin", "adm_del_admin", "DANGER"),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ================= STORE (SEPARATE NORMAL / RARE / PREMIUM + 5 PER PAGE) =================
def store_category_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [inline_btn("✨ NORMAL FILES", "store_cat:NORMAL:0", "PRIMARY")],
            [inline_btn("💠 RARE FILES", "store_cat:RARE:0", "SUCCESS")],
            [inline_btn("👑 PREMIUM FILES", "store_cat:PREMIUM:0", "DANGER")],
        ]
    )


async def render_store_rarity_page(message: Message, rarity: str, page: int = 0, edit: bool = False):
    rarity = rarity.upper()
    if rarity not in {"NORMAL", "RARE", "PREMIUM"}:
        rarity = "NORMAL"

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM files WHERE rarity = ? ORDER BY id DESC", (rarity,)
        ) as cur:
            all_files = [dict(r) for r in await cur.fetchall()]

    em = rarity_emoji(rarity)
    if not all_files:
        text = (
            f"{em} <b>{rarity} FILES STORE</b> ✨\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📭 Is category (<b>{rarity}</b>) mein abhi koi file nahi hai."
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[inline_btn("◀️ BACK TO CATEGORIES", "store_categories", "SUCCESS")]]
        )
        if edit:
            await message.edit_text(text, reply_markup=kb)
        else:
            await message.answer(text, reply_markup=kb)
        return

    total_pages = max(1, (len(all_files) + FILES_PER_PAGE - 1) // FILES_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    start = page * FILES_PER_PAGE
    end = start + FILES_PER_PAGE
    page_files = all_files[start:end]

    kb_rows = []
    for f in page_files:
        kb_rows.append(
            [
                inline_btn(
                    f"{em} {f['title']} • 🪙 {f['price']} Coins",
                    f"buy_file:{f['id']}:{rarity}:{page}",
                    "PRIMARY",
                )
            ]
        )

    nav_row = []
    if page > 0:
        nav_row.append(inline_btn("◀️ PREV", f"store_cat:{rarity}:{page - 1}", "SUCCESS"))
    nav_row.append(inline_btn(f"📄 {page + 1}/{total_pages}", "noop"))
    if page < total_pages - 1:
        nav_row.append(inline_btn("NEXT ▶️", f"store_cat:{rarity}:{page + 1}", "SUCCESS"))
    kb_rows.append(nav_row)
    kb_rows.append([inline_btn("📂 ALL CATEGORIES", "store_categories", "DANGER")])

    text = (
        f"{em} <b>{rarity} FILES STORE</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🛍️ Ek baar mein <b>5 files</b> show ho rahi hain.\n"
        "⚡ Kisi bhi file par tap karke purchase karein!"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


# ================= WELCOME CARD SENDER =================
async def send_welcome_card(message: Message, user_id: int, first_name: str, username: str | None = None, ref_id: int | None = None):
    safe_name = html.escape(first_name or "User")
    await ensure_user(user_id, username, first_name, ref_id)
    u_data = await get_user(user_id)

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM files") as c1:
            total_files = (await c1.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM user_files") as c2:
            total_purchases = (await c2.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM user_files WHERE user_id = ?", (user_id,)) as c3:
            owned_files = (await c3.fetchone())[0]

    prem_status = "Active ✨" if is_premium_active(u_data) else "Not Active 💫"
    welcome_video_id = await get_setting("welcome_video")
    kb = main_reply_kb(has_admin_access=await is_admin(user_id))

    caption = (
        "💎 <b>Welcome To File Store Bot !!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌸 Hey <b>{safe_name}</b> 👑\n\n"
        f"🪙 <b>Wallet :</b> <code>{u_data['coins']}</code> Coins\n"
        f"💎 <b>Gems :</b> <code>{u_data['gems']}</code> Gems\n"
        f"📁 <b>Files Owned :</b> <code>{owned_files}</code>\n"
        f"👥 <b>Referrals :</b> <code>{u_data['referrals']}</code>\n"
        f"⭐ <b>Premium :</b> <code>{prem_status}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>TOTAL FILE :</b> <code>{total_files}</code>\n"
        f"👑 <b>TOTAL PURCHASES :</b> <code>{total_purchases}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ <b>OWNER :</b> {html.escape(OWNER_USERNAME)} 💖"
    )

    if welcome_video_id:
        await message.answer_video(
            video=welcome_video_id,
            caption=caption,
            reply_markup=kb,
        )
    else:
        await message.answer(
            caption,
            reply_markup=kb,
        )


# ================= START & VERIFY HANDLERS =================
@router.message(CommandStart())
async def cmd_start(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    ref_id = None
    if len(parts) > 1 and parts[1].startswith("ref_"):
        try:
            ref_id = int(parts[1].replace("ref_", ""))
        except ValueError:
            ref_id = None

    user = message.from_user
    await send_welcome_card(message, user.id, user.first_name or "User", user.username, ref_id)


@router.callback_query(F.data == "fsub_verify")
async def cb_fsub_verify(call: CallbackQuery, bot: Bot):
    uid = call.from_user.id
    missing = await get_unjoined_channels(bot, uid)
    if missing:
        await call.answer("❌ Abhi saare channels join/request nahi hue hain!", show_alert=True)
        await send_access_restricted(call.message, missing, edit=True)
        return

    await call.answer("✅ Verification Successful!", show_alert=False)
    try:
        await call.message.delete()
    except Exception:
        pass
    await send_welcome_card(call.message, uid, call.from_user.first_name or "User", call.from_user.username)


@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery):
    await call.answer()


# ================= STORE & PURCHASE =================
@router.message(F.text == "BUY FILES")
async def btn_buy_files(message: Message):
    await message.answer(
        "🛒 <b>SELECT FILE CATEGORY</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "✨ <b>NORMAL FILES</b> — Regular files\n"
        "💠 <b>RARE FILES</b> — Special rare files\n"
        "👑 <b>PREMIUM FILES</b> — VIP / Premium files",
        reply_markup=store_category_kb(),
    )


@router.callback_query(F.data == "store_categories")
async def cb_store_categories(call: CallbackQuery):
    await call.message.edit_text(
        "🛒 <b>SELECT FILE CATEGORY</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "✨ <b>NORMAL FILES</b> — Regular files\n"
        "💠 <b>RARE FILES</b> — Special rare files\n"
        "👑 <b>PREMIUM FILES</b> — VIP / Premium files",
        reply_markup=store_category_kb(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("store_cat:"))
async def cb_store_cat(call: CallbackQuery):
    _, rarity, page_str = call.data.split(":")
    await render_store_rarity_page(call.message, rarity=rarity, page=int(page_str), edit=True)
    await call.answer()


@router.callback_query(F.data.startswith("buy_file:"))
async def cb_buy_file(call: CallbackQuery, bot: Bot):
    _, file_id_str, rarity, _ = call.data.split(":")
    file_id = int(file_id_str)
    uid = call.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM files WHERE id = ?", (file_id,)) as cur:
            f_row = await cur.fetchone()
        if not f_row:
            await call.answer("❌ File nahi mili!", show_alert=True)
            return
        file_data = dict(f_row)

        u_data = await get_user(uid)
        async with db.execute(
            "SELECT 1 FROM user_files WHERE user_id = ? AND file_id = ?", (uid, file_id)
        ) as cur2:
            already_owned = await cur2.fetchone() is not None

        if not already_owned:
            if u_data["coins"] < file_data["price"]:
                await call.answer(
                    f"🪙 Coins kam hain! Need {file_data['price']}, aapke paas {u_data['coins']} hain.",
                    show_alert=True,
                )
                return
            await db.execute(
                "UPDATE users SET coins = coins - ? WHERE user_id = ?",
                (file_data["price"], uid),
            )
            await db.execute(
                "UPDATE files SET purchases = purchases + 1 WHERE id = ?",
                (file_id,),
            )
            await db.execute(
                "INSERT INTO user_files (user_id, file_id, bought_at) VALUES (?, ?, ?)",
                (uid, file_id, datetime.now().strftime("%Y-%m-%d %H:%M")),
            )
            await db.commit()

    await call.answer("🚀 File bhej raha hoon!", show_alert=False)
    safe_title = html.escape(file_data["title"])
    safe_rarity = html.escape(file_data["rarity"])
    em = rarity_emoji(file_data["rarity"])
    caption = (
        f"{em} <b>{safe_title}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 <b>Category:</b> <code>{safe_rarity}</code>\n"
        "✅ <b>Status:</b> <code>Unlocked!</code>"
    )
    if file_data["file_type"] == "video":
        await bot.send_video(uid, file_data["file_id"], caption=caption)
    elif file_data["file_type"] == "photo":
        await bot.send_photo(uid, file_data["file_id"], caption=caption)
    else:
        await bot.send_document(uid, file_data["file_id"], caption=caption)


# ================= DAILY BONUS =================
@router.message(F.text == "DAILY BONUS")
async def btn_daily_bonus(message: Message):
    uid = message.from_user.id
    u_data = await get_user(uid)
    now = datetime.now()

    if u_data.get("last_bonus"):
        last_dt = datetime.fromisoformat(u_data["last_bonus"])
        if now - last_dt < timedelta(hours=24):
            rem = timedelta(hours=24) - (now - last_dt)
            hrs = int(rem.total_seconds() // 3600)
            mins = int((rem.total_seconds() % 3600) // 60)
            await message.answer(
                f"⏳ <b>Daily Bonus Locked!</b>\n"
                f"✨ Next bonus <b>{hrs}h {mins}m</b> baad milega."
            )
            return

    new_streak = (u_data.get("streak") or 0) + 1
    bonus = 25 + (10 if is_premium_active(u_data) else 0) + min(new_streak * 2, 30)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET coins = coins + ?, streak = ?, last_bonus = ? WHERE user_id = ?",
            (bonus, new_streak, now.isoformat(), uid),
        )
        await db.commit()

    await message.answer(
        "🎉 <b>DAILY BONUS CLAIMED!</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 <b>Received:</b> <code>+{bonus}</code> Coins\n"
        f"💰 <b>New Balance:</b> <code>{u_data['coins'] + bonus}</code> Coins\n"
        f"🔥 <b>Login Streak:</b> <code>{new_streak}</code> Day(s)"
    )


# ================= MYSTERY BOX =================
@router.message(F.text == "MYSTERY BOX")
async def btn_mystery_box(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [inline_btn("✨ Normal Box • 100 Coins", "mbox:100:NORMAL", "PRIMARY")],
            [inline_btn("💠 Rare Box • 500 Coins", "mbox:500:RARE", "SUCCESS")],
            [inline_btn("👑 Premium Box • 1000 Coins", "mbox:1000:PREMIUM", "DANGER")],
        ]
    )
    await message.answer(
        "🎁 <b>MYSTERY BOX</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔮 Apni pasand ka box open karein!\n"
        "♻️ Agar wo file aapke paas pehle se hai to coins safe rahenge.",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("mbox:"))
async def cb_mystery_box(call: CallbackQuery, bot: Bot):
    _, cost_str, rarity = call.data.split(":")
    cost = int(cost_str)
    uid = call.from_user.id
    u_data = await get_user(uid)

    if u_data["coins"] < cost:
        await call.answer(f"🪙 Insufficient coins! Need {cost} coins.", show_alert=True)
        return

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM files WHERE rarity = ?", (rarity,)) as cur:
            pool = [dict(r) for r in await cur.fetchall()]
        if not pool:
            await call.answer(f"📭 {rarity} category mein abhi koi file nahi hai!", show_alert=True)
            return

        chosen = random.choice(pool)
        async with db.execute(
            "SELECT 1 FROM user_files WHERE user_id = ? AND file_id = ?", (uid, chosen["id"])
        ) as cur3:
            already = await cur3.fetchone() is not None

        if already:
            await call.answer(
                f"♻️ '{chosen['title']}' pehle se unlocked hai! Koi coin nahi kata.",
                show_alert=True,
            )
            return

        await db.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (cost, uid))
        await db.execute("UPDATE files SET purchases = purchases + 1 WHERE id = ?", (chosen["id"],))
        await db.execute(
            "INSERT INTO user_files (user_id, file_id, bought_at) VALUES (?, ?, ?)",
            (uid, chosen["id"], datetime.now().strftime("%Y-%m-%d %H:%M")),
        )
        await db.commit()

    await call.answer("🎁 Box unlocked!", show_alert=False)
    safe_title = html.escape(chosen["title"])
    await bot.send_document(uid, chosen["file_id"], caption=f"🎁 <b>Mystery Box Reward:</b> {safe_title} ✨")


# ================= REFER & EARN =================
@router.message(F.text == "REFER & EARN")
async def btn_refer(message: Message, bot: Bot):
    me = await bot.get_me()
    u_data = await get_user(message.from_user.id)
    ref_link = f"https://t.me/{me.username}?start=ref_{message.from_user.id}"
    await message.answer(
        "👥 <b>REFER & EARN</b> 💖\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌟 <b>Your Referrals:</b> <code>{u_data['referrals']}</code>\n"
        "🪙 <b>Reward:</b> <code>+50</code> Coins per referral\n\n"
        f"🔗 <b>Your Referral Link:</b>\n<code>{html.escape(ref_link)}</code>"
    )


# ================= REDEEM CODE =================
@router.message(F.text == "REDEEM CODE")
async def btn_redeem(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_btn("🔑 Redeem Code", "user_redeem_enter", "SUCCESS"),
                inline_btn("🎁 Create Gift", "user_create_gift", "PRIMARY"),
            ]
        ]
    )
    await message.answer(
        "🎟️ <b>REDEEM CENTER</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔑 <b>Redeem Code:</b> Code daal kar instant coins paayein.\n"
        "🎁 <b>Create Gift:</b> Apne coins se shareable gift code banayein.",
        reply_markup=kb,
    )


@router.callback_query(F.data == "user_redeem_enter")
async def cb_user_redeem_enter(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_redeem_input)
    await call.message.answer("🔑 Apna <b>Redeem Code</b> bhejein:")
    await call.answer()


@router.message(UserStates.waiting_redeem_input)
async def process_user_redeem(message: Message, state: FSMContext):
    code = (message.text or "").strip().upper()
    uid = message.from_user.id
    await state.clear()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM redeem_codes WHERE code = ?", (code,)) as cur:
            row = await cur.fetchone()
        if not row:
            await message.answer("❌ Invalid code!")
            return
        c_data = dict(row)
        if c_data["used_count"] >= c_data["max_uses"]:
            await message.answer("⚠️ Is code ki usage limit khatam ho chuki hai!")
            return
        async with db.execute(
            "SELECT 1 FROM redeemed_users WHERE code = ? AND user_id = ?", (code, uid)
        ) as cur2:
            if await cur2.fetchone():
                await message.answer("💫 Aap yeh code pehle hi redeem kar chuke hain!")
                return

        await db.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (c_data["coins"], uid))
        await db.execute("UPDATE redeem_codes SET used_count = used_count + 1 WHERE code = ?", (code,))
        await db.execute("INSERT INTO redeemed_users (code, user_id) VALUES (?, ?)", (code, uid))
        await db.commit()

    await message.answer(f"🎉 Code <code>{html.escape(code)}</code> redeemed! Aapko <code>+{c_data['coins']}</code> Coins mile! 🪙")


@router.callback_query(F.data == "user_create_gift")
async def cb_user_create_gift(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_gift_coins)
    await call.message.answer("🎁 Kitne coins ka gift code banana chahte hain? (Number bhejein)")
    await call.answer()


@router.message(UserStates.waiting_gift_coins)
async def process_user_gift(message: Message, state: FSMContext):
    await state.clear()
    try:
        amt = int((message.text or "").strip())
        if amt <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("❌ Valid positive number bhejein.")
        return

    uid = message.from_user.id
    u_data = await get_user(uid)
    if u_data["coins"] < amt:
        await message.answer("🪙 Aapke paas itne coins nahi hain.")
        return

    code = "GIFT-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (amt, uid))
        await db.execute(
            "INSERT INTO redeem_codes (code, coins, max_uses, used_count) VALUES (?, ?, 1, 0)",
            (code, amt),
        )
        await db.commit()

    await message.answer(
        "🎁 <b>GIFT CODE CREATED!</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎟️ <b>Code:</b> <code>{code}</code>\n"
        f"🪙 <b>Value:</b> <code>{amt}</code> Coins (1 use)"
    )


# ================= STATS, WALLET, LEADERBOARD, SUPPORT =================
@router.message(F.text == "MY STATS")
async def btn_my_stats(message: Message):
    uid = message.from_user.id
    u_data = await get_user(uid)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM user_files WHERE user_id = ?", (uid,)) as cur:
            owned = (await cur.fetchone())[0]

    await message.answer(
        "📊 <b>YOUR STATS</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>User ID:</b> <code>{uid}</code>\n"
        f"🪙 <b>Coins:</b> <code>{u_data['coins']}</code>\n"
        f"💎 <b>Gems:</b> <code>{u_data['gems']}</code>\n"
        f"📁 <b>Files Owned:</b> <code>{owned}</code>\n"
        f"👥 <b>Referrals:</b> <code>{u_data['referrals']}</code>\n"
        f"🔥 <b>Streak:</b> <code>{u_data['streak']}</code> Day(s)"
    )


@router.message(F.text == "MY WALLET")
async def btn_my_wallet(message: Message):
    u_data = await get_user(message.from_user.id)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_btn("🛒 Buy Files", "store_categories", "SUCCESS"),
                inline_btn(f"👑 Buy Premium ({PREMIUM_COST} Coins • {PREMIUM_DAYS}d)", "buy_prem_coins", "PRIMARY"),
            ]
        ]
    )
    prem_txt = "Active ✨" if is_premium_active(u_data) else "Not Active 💫"
    await message.answer(
        "👛 <b>MY WALLET</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 <b>Coins:</b> <code>{u_data['coins']}</code>\n"
        f"💎 <b>Gems:</b> <code>{u_data['gems']}</code>\n"
        f"👑 <b>Premium:</b> <code>{prem_txt}</code>",
        reply_markup=kb,
    )


@router.callback_query(F.data == "buy_prem_coins")
async def cb_buy_prem_coins(call: CallbackQuery):
    uid = call.from_user.id
    u_data = await get_user(uid)
    if u_data["coins"] < PREMIUM_COST:
        await call.answer(
            f"🪙 {PREMIUM_COST} Coins chahiye {PREMIUM_DAYS} Days Premium ke liye!",
            show_alert=True,
        )
        return

    new_until = (datetime.now() + timedelta(days=PREMIUM_DAYS)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET coins = coins - ?, premium_until = ? WHERE user_id = ?",
            (PREMIUM_COST, new_until, uid),
        )
        await db.commit()
    await call.answer(f"👑 {PREMIUM_DAYS} Days Premium Activated!", show_alert=True)


@router.message(F.text == "LEADERBOARD")
async def btn_leaderboard(message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT full_name, coins, gems, referrals FROM users ORDER BY coins DESC LIMIT 10"
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = ["🏆 <b>TOP 10 COINS LEADERBOARD</b> ✨", "━━━━━━━━━━━━━━━━━━━━━━"]
    for idx, r in enumerate(rows, start=1):
        uname = html.escape(r["full_name"] or "User")
        badge = medals.get(idx, "✨")
        lines.append(
            f"{badge} <b>{idx}.</b> {uname} — 🪙 <code>{r['coins']}</code> | 💎 <code>{r['gems']}</code> | 👥 <code>{r['referrals']}</code>"
        )
    await message.answer("\n".join(lines))


@router.message(F.text == "SUPPORT")
async def btn_support(message: Message):
    await message.answer(
        "💬 <b>SUPPORT CENTER</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 <b>Owner / Support:</b> {html.escape(OWNER_USERNAME)}\n"
        "🕒 <b>Hours:</b> 10:00 AM - 10:00 PM (IST)\n"
        "💖 Koi bhi issue ho to directly message karein!"
    )


# ================= ADMIN PANEL & COMMANDS =================
@router.message(Command("admin"))
@router.message(F.text == "ADMIN PANEL")
async def cmd_admin(message: Message):
    uid = message.from_user.id
    if not await is_admin(uid):
        await message.answer("⛔ Ye command sirf Admins ke liye hai.")
        return
    has_vid = "Set ✅" if await get_setting("welcome_video") else "Not Set ❌"
    maint_on = await is_maintenance_on()
    maint_status = "ON 🔴" if maint_on else "OFF 🟢"
    owner_view = is_owner(uid)

    async with aiosqlite.connect(DB_PATH) as db:
        fsub_cnt = (await (await db.execute("SELECT COUNT(*) FROM force_channels")).fetchone())[0]
        n_cnt = (await (await db.execute("SELECT COUNT(*) FROM files WHERE rarity='NORMAL'")).fetchone())[0]
        r_cnt = (await (await db.execute("SELECT COUNT(*) FROM files WHERE rarity='RARE'")).fetchone())[0]
        p_cnt = (await (await db.execute("SELECT COUNT(*) FROM files WHERE rarity='PREMIUM'")).fetchone())[0]
    adm_cnt = len(await get_all_admin_ids())

    await message.answer(
        "⚙️ <b>ADMIN CONTROL PANEL</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎬 <b>Welcome Video:</b> <code>{has_vid}</code>\n"
        f"🛠️ <b>Maintenance:</b> <code>{maint_status}</code>\n"
        f"📢 <b>Force Channels:</b> <code>{fsub_cnt}</code>\n"
        f"👮 <b>Total Admins:</b> <code>{adm_cnt}</code>\n"
        f"📦 <b>Files:</b> ✨<code>{n_cnt}</code> Normal | 💠<code>{r_cnt}</code> Rare | 👑<code>{p_cnt}</code> Premium",
        reply_markup=admin_panel_kb(maint_on=maint_on, owner_view=owner_view),
    )


# --- Add / Delete / List Admins (Owner Only for Add/Del) ---
@router.message(Command("addadmin"))
@router.callback_query(F.data == "adm_add_admin")
async def adm_add_admin_start(event: Message | CallbackQuery, state: FSMContext):
    if not is_owner(event.from_user.id):
        if isinstance(event, CallbackQuery):
            await event.answer("⛔ Sirf Owner naya admin add kar sakta hai!", show_alert=True)
        else:
            await event.answer("⛔ Sirf Owner naya admin add kar sakta hai.")
        return
    await state.set_state(AdminStates.waiting_add_admin)
    target = event.message if isinstance(event, CallbackQuery) else event
    await target.answer("👤 Jis user ko full Admin banana hai uski <b>User ID</b> bhejein:")
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.message(AdminStates.waiting_add_admin)
async def adm_add_admin_save(message: Message, state: FSMContext, bot: Bot):
    if not is_owner(message.from_user.id):
        await state.clear()
        return
    await state.clear()
    try:
        new_adm_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Valid numeric User ID bhejein.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO admins (user_id, added_by, added_at) VALUES (?, ?, ?)",
            (new_adm_id, message.from_user.id, datetime.now().strftime("%Y-%m-%d %H:%M")),
        )
        await db.commit()

    await message.answer(
        f"✅ <b>New Admin Added!</b>\n"
        f"👤 <b>User ID:</b> <code>{new_adm_id}</code>\n"
        "⚙️ Ab is user ke paas full admin access hai."
    )
    try:
        await bot.send_message(
            new_adm_id,
            "🎉 <b>ADMIN ACCESS GRANTED!</b> ✨\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Aapko bot ka full admin access diya gaya hai.\n"
            "Use <code>/start</code> ya <code>/admin</code> to open <b>ADMIN PANEL</b>.",
        )
    except Exception:
        pass


@router.message(Command("deladmin"))
@router.callback_query(F.data == "adm_del_admin")
async def adm_del_admin_start(event: Message | CallbackQuery, state: FSMContext):
    if not is_owner(event.from_user.id):
        if isinstance(event, CallbackQuery):
            await event.answer("⛔ Sirf Owner admin remove kar sakta hai!", show_alert=True)
        else:
            await event.answer("⛔ Sirf Owner admin remove kar sakta hai.")
        return
    admins = [aid for aid in await get_all_admin_ids() if not is_owner(aid)]
    await state.set_state(AdminStates.waiting_del_admin)
    target = event.message if isinstance(event, CallbackQuery) else event
    if not admins:
        await target.answer("📭 Remove karne ke liye koi extra admin nahi hai.")
    else:
        lines = ["❌ <b>Remove Admin — User ID bhejein:</b>"]
        for aid in admins:
            lines.append(f"• <code>{aid}</code>")
        await target.answer("\n".join(lines))
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.message(AdminStates.waiting_del_admin)
async def adm_del_admin_done(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        await state.clear()
        return
    await state.clear()
    try:
        target_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Valid numeric User ID bhejein.")
        return
    if is_owner(target_id):
        await message.answer("⛔ Main Owner ID remove nahi ho sakti.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM admins WHERE user_id = ?", (target_id,))
        await db.commit()
    await message.answer(f"✅ Admin <code>{target_id}</code> remove ho gaya.")


@router.callback_query(F.data == "adm_list_admins")
async def adm_list_admins(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        return
    admins = await get_all_admin_ids()
    lines = ["👮 <b>BOT ADMINS LIST</b> ✨", "━━━━━━━━━━━━━━━━━━━━━━"]
    for aid in admins:
        role = "👑 Owner" if is_owner(aid) else "🛡️ Admin"
        lines.append(f"{role} — <code>{aid}</code>")
    await call.message.answer("\n".join(lines))
    await call.answer()


# --- Force Subscribe Channel Add / Delete ---
@router.callback_query(F.data == "adm_fsub_add")
async def adm_fsub_add_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_fsub_add)
    await call.message.answer(
        "📢 <b>Force Subscribe Channel Add</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Format bhejein:\n"
        "<code>-1001234567890 | Channel Name | https://t.me/+InviteLink</code>\n\n"
        "<i>Note: Bot channel mein Admin hona chahiye.</i>"
    )
    await call.answer()


@router.message(AdminStates.waiting_fsub_add)
async def adm_fsub_add_save(message: Message, state: FSMContext):
    await state.clear()
    raw = (message.text or "").strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) < 3:
        await message.answer("❌ Format galat hai. Use: <code>chat_id | Title | Invite_Link</code>")
        return
    try:
        chat_id = int(parts[0])
    except ValueError:
        await message.answer("❌ Chat ID number (jaise <code>-1001234567890</code>) hona chahiye.")
        return

    title = parts[1]
    link = parts[2]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO force_channels (chat_id, title, invite_link) VALUES (?, ?, ?)",
            (chat_id, title, link),
        )
        await db.commit()
    await message.answer(f"✅ <b>Force Channel Added!</b>\n📢 <b>{html.escape(title)}</b> (<code>{chat_id}</code>)")


@router.callback_query(F.data == "adm_fsub_del")
async def adm_fsub_del_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM force_channels") as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    await state.set_state(AdminStates.waiting_fsub_del)
    if not rows:
        await call.message.answer("📭 Koi force channel add nahi hai.")
    else:
        lines = ["🚫 <b>Remove Channel — Chat ID bhejein:</b>"]
        for r in rows:
            lines.append(f"• <code>{r['chat_id']}</code> — {html.escape(r['title'])}")
        await call.message.answer("\n".join(lines))
    await call.answer()


@router.message(AdminStates.waiting_fsub_del)
async def adm_fsub_del_done(message: Message, state: FSMContext):
    await state.clear()
    try:
        cid = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Valid Chat ID bhejein.")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM force_channels WHERE chat_id = ?", (cid,))
        await db.commit()
    await message.answer(f"✅ Channel <code>{cid}</code> remove ho gaya.")


# --- Toggle Maintenance Mode ---
@router.message(Command("maintenance"))
@router.callback_query(F.data == "adm_toggle_maint")
async def adm_toggle_maint(event: Message | CallbackQuery):
    uid = event.from_user.id
    if not await is_admin(uid):
        return
    current_on = await is_maintenance_on()
    new_val = "off" if current_on else "on"
    await set_setting("maintenance", new_val)
    now_on = new_val == "on"
    status_txt = "ON 🔴" if now_on else "OFF 🟢"

    if isinstance(event, CallbackQuery):
        await event.answer(f"🛠️ Maintenance Mode {status_txt}", show_alert=True)
        await event.message.edit_reply_markup(
            reply_markup=admin_panel_kb(maint_on=now_on, owner_view=is_owner(uid))
        )
    else:
        await event.answer(f"🛠️ <b>Maintenance Mode:</b> <code>{status_txt}</code>")


# --- Set Welcome Video ---
@router.message(Command("setvideo"))
@router.callback_query(F.data == "adm_set_video")
async def adm_set_video_start(event: Message | CallbackQuery, state: FSMContext):
    if not await is_admin(event.from_user.id):
        return
    await state.set_state(AdminStates.waiting_welcome_video)
    target = event.message if isinstance(event, CallbackQuery) else event
    await target.answer("🎬 Ab <b>Welcome Video</b> bhejein:")
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.message(AdminStates.waiting_welcome_video)
async def adm_set_video_save(message: Message, state: FSMContext):
    if not message.video:
        await message.answer("❌ Kripya ek valid video bhejein.")
        return
    await state.clear()
    await set_setting("welcome_video", message.video.file_id)
    await message.answer("✅ <b>Welcome Video Set!</b> 🎬")


# --- Set Bot Profile Photo ---
@router.callback_query(F.data == "adm_set_photo")
async def adm_set_photo_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_profile_photo)
    await call.message.answer("🖼️ Bot ki nayi <b>Profile Photo</b> bhejein:")
    await call.answer()


@router.message(AdminStates.waiting_profile_photo)
async def adm_set_photo_save(message: Message, state: FSMContext, bot: Bot):
    if not message.photo:
        await message.answer("❌ Kripya ek valid photo bhejein.")
        return
    await state.clear()
    photo = message.photo[-1]
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
        await bot.download(photo, destination=tmp_path)
        with open(tmp_path, "rb") as f:
            await bot.set_my_profile_photo(photo=BufferedInputFile(f.read(), filename="avatar.jpg"))
        await message.answer("✅ <b>Bot Profile Photo Updated!</b> 🖼️")
    except Exception as e:
        await message.answer(f"❌ Profile photo update nahi ho saki: <code>{html.escape(str(e))}</code>")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


# --- Add File Flow (Normal / Rare / Premium) ---
@router.message(Command("addfile"))
@router.callback_query(F.data == "adm_add_file")
async def adm_add_file_start(event: Message | CallbackQuery, state: FSMContext):
    if not await is_admin(event.from_user.id):
        return
    await state.set_state(AdminStates.waiting_file_title)
    target = event.message if isinstance(event, CallbackQuery) else event
    await target.answer("📝 <b>File Title</b> bhejein:")
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.message(AdminStates.waiting_file_title)
async def adm_file_title(message: Message, state: FSMContext):
    await state.update_data(title=(message.text or "").strip())
    await state.set_state(AdminStates.waiting_file_price)
    await message.answer("🪙 File ka <b>Price (Coins)</b> mein bhejein:")


@router.message(AdminStates.waiting_file_price)
async def adm_file_price(message: Message, state: FSMContext):
    try:
        price = int((message.text or "").strip())
        if price < 0:
            raise ValueError()
    except ValueError:
        await message.answer("❌ Valid price number bhejein.")
        return
    await state.update_data(price=price)
    await state.set_state(AdminStates.waiting_file_rarity)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_btn("✨ NORMAL", "pick_rarity:NORMAL", "PRIMARY"),
                inline_btn("💠 RARE", "pick_rarity:RARE", "SUCCESS"),
                inline_btn("👑 PREMIUM", "pick_rarity:PREMIUM", "DANGER"),
            ]
        ]
    )
    await message.answer("💎 File Category / Rarity chunein (ya type karein <code>NORMAL</code> / <code>RARE</code> / <code>PREMIUM</code>):", reply_markup=kb)


@router.callback_query(F.data.startswith("pick_rarity:"))
async def cb_pick_rarity(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    rarity = call.data.split(":")[1]
    await state.update_data(rarity=rarity)
    await state.set_state(AdminStates.waiting_file_doc)
    await call.message.answer(f"📎 Category <b>{rarity}</b> selected! Ab <b>File / Document / Video / Photo</b> bhejein:")
    await call.answer()


@router.message(AdminStates.waiting_file_rarity)
async def adm_file_rarity(message: Message, state: FSMContext):
    rarity = (message.text or "").strip().upper()
    if rarity not in {"NORMAL", "RARE", "PREMIUM"}:
        rarity = "NORMAL"
    await state.update_data(rarity=rarity)
    await state.set_state(AdminStates.waiting_file_doc)
    await message.answer(f"📎 Category <b>{rarity}</b> selected! Ab <b>File / Document / Video / Photo</b> bhejein:")


@router.message(AdminStates.waiting_file_doc)
async def adm_file_doc(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    file_id = None
    file_type = "document"
    if message.document:
        file_id = message.document.file_id
        file_type = "document"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    else:
        await message.answer("❌ Kripya valid file/document/video/photo bhejein.")
        return

    rarity = data.get("rarity", "NORMAL")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO files (title, price, rarity, file_id, file_type) VALUES (?, ?, ?, ?, ?)",
            (data["title"], data["price"], rarity, file_id, file_type),
        )
        new_id = cur.lastrowid
        await db.commit()

    await message.answer(
        "✅ <b>FILE ADDED!</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>ID:</b> <code>{new_id}</code>\n"
        f"📄 <b>Title:</b> <code>{html.escape(data['title'])}</code>\n"
        f"🪙 <b>Price:</b> <code>{data['price']}</code> Coins\n"
        f"{rarity_emoji(rarity)} <b>Category:</b> <code>{rarity}</code>"
    )


# --- Delete File ---
@router.callback_query(F.data == "adm_del_file")
async def adm_del_file_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_del_file_id)
    await call.message.answer("🗑️ Jis file ko delete karna hai uski <b>File ID</b> bhejein:")
    await call.answer()


@router.message(AdminStates.waiting_del_file_id)
async def adm_del_file_done(message: Message, state: FSMContext):
    await state.clear()
    try:
        fid = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Valid ID bhejein.")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM files WHERE id = ?", (fid,))
        await db.commit()
    await message.answer(f"🗑️ File ID <code>{fid}</code> delete ho gayi.")


# --- Add Coins ---
@router.message(Command("addcoin"))
@router.callback_query(F.data == "adm_add_coins")
async def adm_add_coins_start(event: Message | CallbackQuery, state: FSMContext):
    if not await is_admin(event.from_user.id):
        return
    await state.set_state(AdminStates.waiting_add_coin_user)
    target = event.message if isinstance(event, CallbackQuery) else event
    await target.answer("👤 User ID bhejein jise coins dene hain:")
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.message(AdminStates.waiting_add_coin_user)
async def adm_add_coin_user(message: Message, state: FSMContext):
    try:
        target_uid = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Valid numeric User ID bhejein.")
        return
    await state.update_data(target_uid=target_uid)
    await state.set_state(AdminStates.waiting_add_coin_amount)
    await message.answer("🪙 Kitne coins add karne hain?")


@router.message(AdminStates.waiting_add_coin_amount)
async def adm_add_coin_amount(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    try:
        amt = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Valid number bhejein.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amt, data["target_uid"]))
        await db.commit()
    await message.answer(f"🪙 User <code>{data['target_uid']}</code> ke coins <code>{amt:+d}</code> update ho gaye!")


# --- Add Gems ---
@router.message(Command("addgem"))
@router.callback_query(F.data == "adm_add_gems")
async def adm_add_gems_start(event: Message | CallbackQuery, state: FSMContext):
    if not await is_admin(event.from_user.id):
        return
    await state.set_state(AdminStates.waiting_add_gem_user)
    target = event.message if isinstance(event, CallbackQuery) else event
    await target.answer("👤 User ID bhejein jise gems dene hain:")
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.message(AdminStates.waiting_add_gem_user)
async def adm_add_gem_user(message: Message, state: FSMContext):
    try:
        target_uid = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Valid numeric User ID bhejein.")
        return
    await state.update_data(target_uid=target_uid)
    await state.set_state(AdminStates.waiting_add_gem_amount)
    await message.answer("💎 Kitne gems add karne hain?")


@router.message(AdminStates.waiting_add_gem_amount)
async def adm_add_gem_amount(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    try:
        amt = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Valid number bhejein.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET gems = gems + ? WHERE user_id = ?", (amt, data["target_uid"]))
        await db.commit()
    await message.answer(f"💎 User <code>{data['target_uid']}</code> ke gems <code>{amt:+d}</code> update ho gaye!")


# --- Create Redeem Code ---
@router.callback_query(F.data == "adm_create_code")
async def adm_create_code_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_redeem_code)
    await call.message.answer("🎟️ Redeem Code ka naam bhejein:")
    await call.answer()


@router.message(AdminStates.waiting_redeem_code)
async def adm_redeem_code_name(message: Message, state: FSMContext):
    await state.update_data(code=(message.text or "").strip().upper())
    await state.set_state(AdminStates.waiting_redeem_coins)
    await message.answer("🪙 Is code par kitne coins milenge?")


@router.message(AdminStates.waiting_redeem_coins)
async def adm_redeem_code_coins(message: Message, state: FSMContext):
    try:
        coins = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Valid number bhejein.")
        return
    await state.update_data(coins=coins)
    await state.set_state(AdminStates.waiting_redeem_uses)
    await message.answer("🔢 Maximum kitne users is code ko use kar sakte hain?")


@router.message(AdminStates.waiting_redeem_uses)
async def adm_redeem_code_uses(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    try:
        uses = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Valid number bhejein.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO redeem_codes (code, coins, max_uses, used_count) VALUES (?, ?, ?, 0)",
            (data["code"], data["coins"], uses),
        )
        await db.commit()

    await message.answer(
        "🎟️ <b>REDEEM CODE CREATED!</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 <b>Code:</b> <code>{html.escape(data['code'])}</code>\n"
        f"🪙 <b>Coins:</b> <code>{data['coins']}</code>\n"
        f"👥 <b>Max Uses:</b> <code>{uses}</code>"
    )


# --- Broadcast ---
@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_broadcast)
    await call.message.answer("📢 Jo message sabhi users ko bhejna hai wo likhein:")
    await call.answer()


@router.message(AdminStates.waiting_broadcast)
async def adm_broadcast_send(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cur:
            users = [r[0] for r in await cur.fetchall()]

    sent = 0
    safe_msg = html.escape(message.text or "")
    for uid in users:
        try:
            await bot.send_message(uid, f"📢 <b>ANNOUNCEMENT</b> ✨\n━━━━━━━━━━━━━━━━━━━━━━\n\n{safe_msg}")
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await message.answer(f"✅ Broadcast complete! <code>{sent}/{len(users)}</code> users ko message gaya.")


# --- Status & List Files ---
@router.message(Command("status"))
@router.callback_query(F.data == "adm_status")
async def adm_status(event: Message | CallbackQuery):
    if not await is_admin(event.from_user.id):
        return
    async with aiosqlite.connect(DB_PATH) as db:
        u_cnt = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
        f_cnt = (await (await db.execute("SELECT COUNT(*) FROM files")).fetchone())[0]
        p_cnt = (await (await db.execute("SELECT COUNT(*) FROM user_files")).fetchone())[0]
        c_sum = (await (await db.execute("SELECT COALESCE(SUM(coins), 0) FROM users")).fetchone())[0]
        g_sum = (await (await db.execute("SELECT COALESCE(SUM(gems), 0) FROM users")).fetchone())[0]

    maint_txt = "ON 🔴" if await is_maintenance_on() else "OFF 🟢"
    text = (
        "📈 <b>BOT STATUS</b> ✨\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Total Users:</b> <code>{u_cnt}</code>\n"
        f"📦 <b>Total Files:</b> <code>{f_cnt}</code>\n"
        f"🛍️ <b>Total Purchases:</b> <code>{p_cnt}</code>\n"
        f"🪙 <b>Total Coins:</b> <code>{c_sum}</code>\n"
        f"💎 <b>Total Gems:</b> <code>{g_sum}</code>\n"
        f"🛠️ <b>Maintenance:</b> <code>{maint_txt}</code>\n"
        "🟢 <b>Bot Status:</b> <code>Online & Running</code>"
    )
    if isinstance(event, CallbackQuery):
        await event.message.answer(text)
        await event.answer()
    else:
        await event.answer(text)


@router.callback_query(F.data == "adm_list_files")
async def adm_list_files(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        return
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, title, price, rarity, purchases FROM files ORDER BY id DESC") as cur:
            rows = [dict(r) for r in await cur.fetchall()]

    if not rows:
        await call.message.answer("📭 Koi file nahi hai.")
    else:
        lines = ["📂 <b>ALL FILES</b> ✨", "━━━━━━━━━━━━━━━━━━━━━━"]
        for r in rows:
            em = rarity_emoji(r["rarity"])
            lines.append(
                f"{em} <code>#{r['id']}</code> | <b>{html.escape(r['title'])}</b> — "
                f"🪙 <code>{r['price']}</code> | <code>{r['rarity']}</code> | 🛍️ <code>{r['purchases']}</code>"
            )
        await call.message.answer("\n".join(lines))
    await call.answer()


# ================= RUN BOT =================
async def main():
    await init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.update.outer_middleware(AccessMiddleware())
    dp.include_router(router)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
