import asyncio
import html
import time
from datetime import datetime

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
from keyboards import home_menu_kb, home_button_kb, service_status_renew_kb
from utils import run_db, chunk_blocks, send_chunks, render_home, build_welcome_text

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
        await render_home(call, call.from_user.id)


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

    # اگه از قبل کیبورد ثابت (نسخه‌ی قدیمی ربات) روی گوشی کاربر مونده باشه، این
    # پیام موقت اونو حذف می‌کنه — از این به بعد فقط دکمه‌های شیشه‌ای استفاده می‌شن
    await message.answer("👋", reply_markup=types.ReplyKeyboardRemove())

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

    from db import get_brand_name
    from keyboards import home_menu_kb

    brand_name = await run_db(get_brand_name)
    welcome_text = await build_welcome_text(message.from_user.first_name, brand_name)
    await message.answer(welcome_text, reply_markup=home_menu_kb(message.from_user.id))


@router.callback_query(F.data == "menu:home")
async def menu_home(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    not_joined = await check_membership(call.bot, call.from_user.id)
    if not_joined:
        await call.message.edit_text("⛔️ برای استفاده از ربات باید عضو کانال‌های زیر بشی:")
        await send_join_message(call.message, not_joined)
        await call.answer()
        return
    await render_home(call, call.from_user.id)


@router.callback_query(F.data == "cancel:fsm")
async def cancel_fsm(call: types.CallbackQuery, state: FSMContext):
    """
    دکمه‌ی انصراف عمومی — برای وسط هر فلوی چندمرحله‌ای (FSM) که کاربر بخواد
    بی‌خیال بشه (مثلاً وسط شارژ حساب). state رو پاک می‌کنه و برمی‌گرده خانه.
    """
    await state.clear()
    await render_home(call, call.from_user.id)


# ================================================================
# BALANCE
# ================================================================

@router.callback_query(F.data == "menu:balance")
async def menu_balance(call: types.CallbackQuery):
    bal = await run_db(get_balance, call.from_user.id)
    await call.message.edit_text(
        f"💰 موجودی شما: {bal:,} تومان",
        reply_markup=home_button_kb()
    )
    await call.answer()


# ================================================================
# SERVICE STATUS
# ================================================================
# این بخش برخلاف قبل، برای هر سرویس با get_client_status وضعیت لحظه‌ای رو
# مستقیم از پنل می‌گیره (حجم مصرفی/کل، تاریخ انقضا، فعال/غیرفعال بودن روی
# پنل). همه‌ی درخواست‌ها موازی (asyncio.gather) زده می‌شن تا با چند سرویس هم
# صفحه کند نشه. اگه پنل جواب نداد (قطعی/تایم‌اوت)، به‌جای کرش، همون سرویس با
# آخرین اطلاعات ذخیره‌شده در دیتابیس + یک هشدار کوچیک نمایش داده می‌شه.
#
# نکته: sub_url همیشه از دیتابیس خودمون میاد چون endpoint ترافیک پنل اصلاً
# subId رو برنمی‌گردونه (حتی خودِ پنل هم اونو جایی ذخیره نمی‌کنه، فقط لحظه‌ی
# ساخت اکانت تولید می‌شه) — این تنها منبع ممکن برای لینک ساب‌ه.
#
# دکمه‌ی تمدید فقط وقتی نشون داده می‌شه که purchase_id داشته باشیم (نه تست
# رایگان) — تمدید پلن‌های دلخواه (بدون service_id ثابت) فعلاً پشتیبانی نمی‌شه.

def _fmt_bytes(b) -> str:
    if b is None:
        return "—"
    b = float(b)
    if b <= 0:
        return "0 B"
    if b >= 1024 ** 3:
        return f"{b / 1024 ** 3:.2f} GB"
    if b >= 1024 ** 2:
        return f"{b / 1024 ** 2:.0f} MB"
    if b >= 1024:
        return f"{b / 1024:.0f} KB"
    return f"{b:.0f} B"


def _progress_bar(used: float, total: float, width: int = 10) -> str:
    if not total or total <= 0:
        return ""
    pct = min(max(used / total, 0.0), 1.0)
    filled = round(pct * width)
    return "🟩" * filled + "⬜️" * (width - filled) + f"  {pct * 100:.0f}%"


def _status_label(enable: bool, expire_ms: int, total: int, used: int) -> str:
    now_ms = time.time() * 1000
    if not enable:
        return "🔴 غیرفعال (روی پنل خاموش شده)"
    if expire_ms and expire_ms > 0 and now_ms > expire_ms:
        return "⏰ منقضی شده"
    if total and total > 0 and used >= total:
        return "📛 اتمام حجم"
    return "🟢 فعال"


@router.callback_query(F.data == "menu:status")
async def menu_status(call: types.CallbackQuery):
    from db import get_user_vpn_accounts
    from panel import get_client_status

    accounts = await run_db(get_user_vpn_accounts, call.from_user.id)
    if not accounts:
        await call.message.edit_text("📊 هنوز سرویس فعالی نداری.", reply_markup=home_button_kb())
        await call.answer()
        return

    await call.message.edit_text(
        f"📊 وضعیت سرویس‌های شما ({len(accounts)} مورد)\n⏳ در حال دریافت اطلاعات لحظه‌ای از پنل..."
    )

    # همه‌ی درخواست‌های پنل رو موازی می‌زنیم — با N سرویس، به‌جای N برابر
    # تایم‌اوت (حداکثر ۱۰ ثانیه هرکدوم طبق panel.py)، کل کار حداکثر یک تایم‌اوت طول می‌کشه
    live_results = await asyncio.gather(
        *[get_client_status(acc[0]) for acc in accounts],  # acc[0] == email
        return_exceptions=True,
    )

    sep = "─" * 22

    for acc, live in zip(accounts, live_results):
        (email, uuid, sub_url, inbound_id, expire_time_db, data_limit_db,
         created_at, is_trial, service_name, category_name, purchase_id) = acc

        live = live if isinstance(live, dict) else None
        is_live = live is not None

        if is_live:
            used = (live.get("up") or 0) + (live.get("down") or 0)
            total = live.get("total") or 0
            expire_ms = live.get("expiryTime") or 0
            enable = live.get("enable", True)
        else:
            used = None
            total = data_limit_db or 0
            expire_ms = expire_time_db or 0
            enable = True  # نمی‌دونیم؛ خوش‌بینانه فرض می‌کنیم فعاله

        status = _status_label(enable, expire_ms, total, used or 0)

        label = "🧪 تست رایگان" if is_trial else "💎 سرویس"
        safe_service_name = html.escape(service_name or "")
        safe_category_name = html.escape(category_name or "")
        safe_email = html.escape(email or "")

        lines = [label]
        if purchase_id:
            lines.append(f"🔑 شماره سفارش: #{purchase_id}")
        lines.append(f"📦 نام: {safe_service_name}")
        if not is_trial:
            lines.append(f"🗂 دسته‌بندی: {safe_category_name}")
        lines.append(f"📧 ایمیل کلاینت: {safe_email}")
        lines.append(f"وضعیت: {status}")

        if expire_ms and expire_ms > 0:
            expire_dt = datetime.fromtimestamp(expire_ms / 1000)
            days_left = (expire_dt - datetime.now()).days
            days_txt = f"({days_left} روز مانده)" if days_left >= 0 else "(منقضی شده)"
            lines.append(f"📅 انقضا: {expire_dt.strftime('%Y-%m-%d')} {days_txt}")
        else:
            lines.append("📅 انقضا: نامحدود")

        if total and total > 0:
            used_v = used or 0
            remaining = max(total - used_v, 0)
            lines.append(f"📊 حجم: {_fmt_bytes(used_v)} از {_fmt_bytes(total)} مصرف شده")
            bar = _progress_bar(used_v, total)
            if bar:
                lines.append(bar)
            lines.append(f"📶 باقی‌مانده: {_fmt_bytes(remaining)}")
        elif used is not None:
            lines.append(f"📊 حجم مصرفی: {_fmt_bytes(used)} (سقف: ♾ نامحدود)")
        else:
            lines.append("📶 حجم: ♾ نامحدود")

        if not is_live:
            lines.append("⚠️ اتصال لحظه‌ای به پنل برقرار نشد — آخرین اطلاعات ذخیره‌شده نمایش داده شد.")

        if sub_url:
            safe_sub_url = html.escape(sub_url)
            lines.append(f"🔗 لینک سابسکریپشن:\n<code>{safe_sub_url}</code>")

        block = "\n".join(lines) + "\n" + sep

        kb = service_status_renew_kb(purchase_id) if (purchase_id and not is_trial) else None
        await call.message.answer(block, parse_mode="HTML", reply_markup=kb)

        if len(accounts) > 1:
            await asyncio.sleep(0.05)  # جلوگیری از خوردن به Flood Limit تلگرام

    await call.message.answer(
        "ℹ️ برای اتصال، لینک سابسکریپشن بالا رو داخل اپلیکیشن VPN خودت وارد کن.",
        reply_markup=home_button_kb(),
    )
    await call.answer()



# ================================================================
# PURCHASE HISTORY
# ================================================================

@router.callback_query(F.data == "menu:purchases")
async def menu_purchases(call: types.CallbackQuery):
    purchases = await run_db(get_user_purchases, call.from_user.id)
    if not purchases:
        await call.message.edit_text("📋 هنوز خریدی نداشتی.", reply_markup=home_button_kb())
        await call.answer()
        return

    sep = "─" * 22
    header = f"📋 تاریخچه خریدهای شما\n{sep}\n"

    blocks = []
    for p in purchases:
        pid, sname, amt, pat, category_name, email = p
        blocks.append(
            f"📦 نام: {sname}\n"
            f"🔑 شماره سفارش: #{pid}\n"
            f"🗂 دسته‌بندی: {category_name}\n"
            f"📧 ایمیل کلاینت: {email or '—'}\n"
            f"💰 مبلغ: {amt:,} تومان\n"
            f"📅 تاریخ: {pat.strftime('%Y-%m-%d %H:%M')}\n"
            f"{sep}\n"
        )

    chunks = chunk_blocks(header, blocks)
    await call.message.edit_text(chunks[0])
    if len(chunks) > 1:
        await send_chunks(call.message, chunks[1:])
    await call.message.answer("👇", reply_markup=home_button_kb())
    await call.answer()