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

router = Router()


# ================================================================
# MEMBERSHIP CHECK
# ================================================================

async def check_membership(bot: Bot, user_id: int) -> list:
    """لیست کانال‌هایی که کاربر عضوشون نیست رو برمی‌گردونه"""
    channels = get_active_channels()
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
    """پیام جوین اجباری با دکمه‌های چنل‌ها"""
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
        bal = get_balance(call.from_user.id)
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

    # پردازش لینک رفرال
    args = message.text.split()
    referred_by = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referred_by = int(args[1][4:])
            if referred_by == message.from_user.id:
                referred_by = None
        except ValueError:
            referred_by = None

    add_user(message.from_user.id, referred_by)

    # چک عضویت
    not_joined = await check_membership(message.bot, message.from_user.id)
    if not_joined:
        await send_join_message(message, not_joined)
        return

    # اگه رفرال داشت → پاداش ثبت‌نام
    if referred_by:
        try:
            conn2 = db_connect()
            cur2 = conn2.cursor()
            cur2.execute("""
                SELECT COUNT(*) FROM referral_rewards
                WHERE referrer_id=%s AND referred_id=%s AND reward_type='join'
            """, (referred_by, message.from_user.id))
            already_rewarded = cur2.fetchone()[0] > 0
            conn2.close()
        except Exception:
            already_rewarded = True

        if not already_rewarded:
            ref_cfg = get_referral_config()
            if ref_cfg and ref_cfg[0] and ref_cfg[1] > 0:
                give_referral_reward(referred_by, message.from_user.id, "join", ref_cfg[1])
                try:
                    await message.bot.send_message(
                        referred_by,
                        f"🎉 یه نفر با لینک رفرال شما عضو شد!\n"
                        f"💚 +{ref_cfg[1]:,} تومان به حسابت اضافه شد."
                    )
                except Exception:
                    pass

    bal = get_balance(message.from_user.id)
    await message.answer(
        f"👋 خوش اومدی به ربات VPN!\n\n💰 موجودی: {bal:,} تومان",
        reply_markup=get_kb(message.from_user.id)
    )


@router.message(F.text == "🏠 خانه")
async def home(message: types.Message, state: FSMContext):
    await state.clear()

    # چک عضویت
    not_joined = await check_membership(message.bot, message.from_user.id)
    if not_joined:
        await send_join_message(message, not_joined)
        return

    bal = get_balance(message.from_user.id)
    await message.answer(
        f"🏠 صفحه اصلی\n\n💰 موجودی: {bal:,} تومان",
        reply_markup=get_kb(message.from_user.id)
    )


# ================================================================
# BALANCE
# ================================================================

@router.message(F.text == "💰 موجودی من")
async def balance(message: types.Message):
    bal = get_balance(message.from_user.id)
    await message.answer(f"💰 موجودی شما: {bal:,} تومان")


# ================================================================
# SERVICE STATUS
# ================================================================

@router.message(F.text == "📊 وضعیت سرویس‌ها")
async def service_status(message: types.Message):
    from db import get_user_vpn_accounts
    from panel import get_client_status
    import datetime

    accounts = get_user_vpn_accounts(message.from_user.id)
    if not accounts:
        await message.answer("📊 هنوز سرویس فعالی نداری.")
        return

    sep = "─" * 22
    text = f"📊 وضعیت سرویس‌های شما\n{sep}\n"

    for acc in accounts:
        email, uuid, sub_url, inbound_id, expire_time, data_limit, created_at, is_trial = acc
        label = "🧪 تست" if is_trial else "💎 سرویس"

        if expire_time:
            exp_dt = datetime.datetime.fromtimestamp(expire_time / 1000)
            remaining = (exp_dt - datetime.datetime.now()).days
            exp_str = exp_dt.strftime('%Y-%m-%d')
            if remaining > 0:
                time_str = f"📅 انقضا: {exp_str} ({remaining} روز مونده)"
            else:
                time_str = "⛔️ منقضی شده"
        else:
            time_str = "📅 بدون انقضا"

        text += f"{label}\n{time_str}\n"

        if sub_url:
            text += f"🔗 لینک سابسکریپشن:\n`{sub_url}`\n"

        stat = await get_client_status(email)
        if stat:
            up = stat.get("up", 0)
            down = stat.get("down", 0)
            total = stat.get("total", 0)
            used = up + down
            enable = stat.get("enable", True)

            def _fmt(b):
                if b >= 1024 ** 3:
                    return f"{b / 1024 ** 3:.1f} GB"
                return f"{b / 1024 ** 2:.0f} MB"

            text += f"📶 مصرف: {_fmt(used)}"
            if total > 0:
                text += f" از {_fmt(total)} ({_fmt(total - used)} مونده)"
            text += f"\n🔘 وضعیت: {'✅ فعال' if enable else '❌ غیرفعال'}\n"
        else:
            text += "⚠️ اطلاعات از پنل دریافت نشد\n"

        text += f"{sep}\n"

    await message.answer(text, parse_mode="Markdown")


# ================================================================
# PURCHASE HISTORY
# ================================================================

@router.message(F.text == "📋 خریدهای من")
async def my_purchases(message: types.Message):
    purchases = get_user_purchases(message.from_user.id)
    if not purchases:
        await message.answer("📋 هنوز خریدی نداشتی.")
        return
    text = "📋 تاریخچه خریدهای شما:\n\n"
    for p in purchases:
        sname, amt, pat = p
        text += f"📦 {sname} | {amt:,} تومان | {pat.strftime('%Y-%m-%d %H:%M')}\n"
    await message.answer(text)