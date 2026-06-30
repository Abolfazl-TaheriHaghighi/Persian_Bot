from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_ID, is_admin
from db import (
    add_user, get_balance, get_user_purchases,
    get_referral_config, give_referral_reward,
    get_active_channels,
    connect as db_connect
)
from keyboards import get_kb
from utils import run_db

router = Router()


# ================================================================
# MEMBERSHIP CHECK
# ================================================================

async def check_membership(bot: Bot, user_id: int) -> list:
    channels = await run_db(get_active_channels)
    not_joined = []
    for ch in channels:
        ch_id, channel_id, username, title, invite_link = ch
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status in ("left", "kicked", "banned"):
                not_joined.append((ch_id, channel_id, username, title, invite_link))
        except Exception:
            not_joined.append((ch_id, channel_id, username, title, invite_link))
    return not_joined


async def send_join_message(message: types.Message, not_joined: list):
    text = "⛔️ برای استفاده از ربات باید عضو کانال‌های زیر بشی:\n\n"
    buttons = []
    for ch_id, channel_id, username, title, invite_link in not_joined:
        link = invite_link or (f"https://t.me/{username.lstrip('@')}" if username else None)
        if link:
            buttons.append([InlineKeyboardButton(text=f"📢 {title}", url=link)])
    buttons.append([InlineKeyboardButton(text="✅ عضو شدم، بررسی کن", callback_data="check_membership")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data == "check_membership")
async def recheck_membership(call: types.CallbackQuery):
    not_joined = await check_membership(call.bot, call.from_user.id)
    if not_joined:
        await call.answer("❌ هنوز عضو همه کانال‌ها نشدی!", show_alert=True)
    else:
        await call.message.delete()
        bal = await run_db(get_balance, call.from_user.id)
        await call.message.answer(
            f"✅ عضویت تایید شد!\n\n💰 موجودی: {bal:,} تومان",
            reply_markup=get_kb(call.from_user.id)
        )
        await call.answer()


# ================================================================
# START / HOME
# ================================================================

@router.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await state.clear()

    args = message.text.split()
    referred_by = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referred_by = int(args[1][4:])
            if referred_by == message.from_user.id:
                referred_by = None
        except ValueError:
            referred_by = None

    await run_db(add_user, message.from_user.id, referred_by)

    not_joined = await check_membership(message.bot, message.from_user.id)
    if not_joined:
        await send_join_message(message, not_joined)
        return

    if referred_by:
        try:
            def _check_join_reward(referrer, referred):
                from db import connect as _conn
                conn = _conn()
                cur = conn.cursor()
                cur.execute("""
                    SELECT COUNT(*) FROM referral_rewards
                    WHERE referrer_id=%s AND referred_id=%s AND reward_type='join'
                """, (referrer, referred))
                result = cur.fetchone()[0] > 0
                conn.close()
                return result
            already_rewarded = await run_db(_check_join_reward, referred_by, message.from_user.id)
        except Exception:
            already_rewarded = True

        if not already_rewarded:
            ref_cfg = await run_db(get_referral_config)
            if ref_cfg and ref_cfg[0] and ref_cfg[1] > 0:
                await run_db(give_referral_reward, referred_by, message.from_user.id, "join", ref_cfg[1])
                try:
                    await message.bot.send_message(
                        referred_by,
                        f"🎉 یه نفر با لینک رفرال شما عضو شد!\n"
                        f"💚 +{ref_cfg[1]:,} تومان به حسابت اضافه شد."
                    )
                except Exception:
                    pass

    bal = await run_db(get_balance, message.from_user.id)
    await message.answer(
        f"👋 خوش اومدی به ربات VPN!\n\n💰 موجودی: {bal:,} تومان",
        reply_markup=get_kb(message.from_user.id)
    )


@router.message(F.text == "🏠 خانه")
async def home(message: types.Message, state: FSMContext):
    await state.clear()
    not_joined = await check_membership(message.bot, message.from_user.id)
    if not_joined:
        await send_join_message(message, not_joined)
        return
    bal = await run_db(get_balance, message.from_user.id)
    await message.answer(
        f"🏠 صفحه اصلی\n\n💰 موجودی: {bal:,} تومان",
        reply_markup=get_kb(message.from_user.id)
    )


# ================================================================
# BALANCE
# ================================================================

@router.message(F.text == "💰 موجودی من")
async def balance(message: types.Message):
    bal = await run_db(get_balance, message.from_user.id)
    await message.answer(f"💰 موجودی شما: {bal:,} تومان")


# ================================================================
# SERVICE STATUS
# ================================================================

@router.message(F.text == "📊 وضعیت سرویس‌ها")
async def service_status(message: types.Message):
    from db import get_user_vpn_accounts
    from panel import get_client_status
    import datetime

    accounts = await run_db(get_user_vpn_accounts, message.from_user.id)
    if not accounts:
        await message.answer("📊 هنوز سرویس فعالی نداری.")
        return

    def _fmt_bytes(b):
        if b is None:
            return "—"
        b = float(b)
        if b >= 1024 ** 3:
            return f"{b / 1024 ** 3:.2f} GB"
        if b >= 1024 ** 2:
            return f"{b / 1024 ** 2:.0f} MB"
        return f"{b / 1024:.0f} KB"

    def _fmt_time_left(target_dt: datetime.datetime) -> str:
        now = datetime.datetime.now()
        diff = target_dt - now
        if diff.total_seconds() <= 0:
            return "⛔️ منقضی شده"
        days = diff.days
        hours = diff.seconds // 3600
        if days > 0:
            return f"⏳ {days} روز و {hours} ساعت مونده"
        minutes = (diff.seconds % 3600) // 60
        if hours > 0:
            return f"⏳ {hours} ساعت و {minutes} دقیقه مونده"
        return f"⏳ {minutes} دقیقه مونده"

    sep = "─" * 22
    text = f"📊 وضعیت سرویس‌های شما\n{sep}\n"

    for acc in accounts:
        (email, uuid, sub_url, inbound_id, expire_time_db, data_limit_db,
         created_at, is_trial, service_name, category_name) = acc

        label = "🧪 تست رایگان" if is_trial else "💎 سرویس"

        text += f"{label}\n"
        text += f"📦 نام: {service_name}\n"
        if not is_trial:
            text += f"🗂 دسته‌بندی: {category_name}\n"

        # اطلاعات زنده از پنل — اولویت با پنل، fallback به DB
        stat = await get_client_status(email)

        expiry_ms = None
        total_bytes = None
        used_bytes = None
        enable = True

        if stat:
            expiry_ms = stat.get("expiryTime") or expire_time_db
            total_bytes = stat.get("total") if stat.get("total") not in (None, 0) else data_limit_db
            up = stat.get("up", 0) or 0
            down = stat.get("down", 0) or 0
            used_bytes = up + down
            enable = stat.get("enable", True)
        else:
            expiry_ms = expire_time_db
            total_bytes = data_limit_db
            used_bytes = None

        # زمان باقیمونده
        if expiry_ms:
            exp_dt = datetime.datetime.fromtimestamp(expiry_ms / 1000)
            text += f"{_fmt_time_left(exp_dt)}\n"
            text += f"📅 تاریخ انقضا: {exp_dt.strftime('%Y-%m-%d %H:%M')}\n"
        else:
            text += "📅 بدون محدودیت زمانی\n"

        # حجم
        if total_bytes and total_bytes > 0:
            remaining_bytes = max(0, total_bytes - (used_bytes or 0))
            text += f"📶 حجم کل: {_fmt_bytes(total_bytes)}\n"
            text += f"📥 حجم مصرفی: {_fmt_bytes(used_bytes or 0)}\n"
            text += f"📤 حجم باقی‌مانده: {_fmt_bytes(remaining_bytes)}\n"
        else:
            text += f"📶 حجم: نامحدود"
            if used_bytes is not None:
                text += f" | مصرفی: {_fmt_bytes(used_bytes)}"
            text += "\n"

        text += f"🔘 وضعیت: {'✅ فعال' if enable else '❌ غیرفعال'}\n"

        if sub_url:
            text += f"🔗 لینک سابسکریپشن:\n`{sub_url}`\n"

        if not stat:
            text += "⚠️ اطلاعات زنده از پنل دریافت نشد (نمایش از کش)\n"

        text += f"{sep}\n"

    await message.answer(text, parse_mode="Markdown")


# ================================================================
# PURCHASE HISTORY
# ================================================================

@router.message(F.text == "📋 خریدهای من")
async def my_purchases(message: types.Message):
    purchases = await run_db(get_user_purchases, message.from_user.id)
    if not purchases:
        await message.answer("📋 هنوز خریدی نداشتی.")
        return
    text = "📋 تاریخچه خریدهای شما:\n\n"
    for p in purchases:
        sname, amt, pat = p
        text += f"📦 {sname} | {amt:,} تومان | {pat.strftime('%Y-%m-%d %H:%M')}\n"
    await message.answer(text)