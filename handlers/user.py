import asyncio
import html
import time
from datetime import datetime

from aiogram import Router, types, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_ID, is_admin
from db import (
    add_user, get_balance, get_user_purchases,
    get_referral_config, give_referral_reward,
    get_active_channels,
    connect as db_connect
)
from keyboards import home_menu_kb, home_button_kb
from utils import run_db, chunk_blocks, send_chunks, render_home, build_welcome_text, normalize_phone
from states import ServiceNote

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
# PROFILE (ترکیب موجودی + خریدها + اطلاعات کاربر در یک صفحه)
# ================================================================
# این هندلر جایگزین «💰 موجودی من» و «📋 خریدهای من» روی صفحه‌ی خانه شده.
# «📋 خریدهای من» از دکمه‌ی داخل همین صفحه (menu:purchases) در دسترسه.

@router.callback_query(F.data == "menu:profile")
async def menu_profile(call: types.CallbackQuery):
    from db import get_user_stats

    user_id = call.from_user.id
    bal = await run_db(get_balance, user_id)
    total_purchases, active_services = await run_db(get_user_stats, user_id)

    username = f"@{call.from_user.username}" if call.from_user.username else "ثبت نشده"
    full_name = call.from_user.full_name or "—"

    sep = "─" * 22
    text = (
        f"👤 پروفایل من\n{sep}\n"
        f"🆔 آیدی عددی: <code>{user_id}</code>\n"
        f"🔖 آیدی تلگرام: {username}\n"
        f"📛 نام: {html.escape(full_name)}\n{sep}\n"
        f"💰 موجودی: {bal:,} تومان\n"
        f"🛍 تعداد کل خریدها: {total_purchases}\n"
        f"📡 سرویس‌های فعال: {active_services}\n{sep}\n"
    )
    buttons = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 تاریخچه‌ی کامل خریدها", callback_data="menu:purchases")],
        [InlineKeyboardButton(text="➕ شارژ حساب", callback_data="menu:deposit")],
        [InlineKeyboardButton(text="🏠 بازگشت به خانه", callback_data="menu:home")],
    ])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=buttons)
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


def _status_dot(enable: bool, expire_ms: int, total: int, used: int) -> str:
    """فقط ایموجی وضعیت (بدون متن) — برای دکمه‌های لیست سرویس‌ها که جا کمتری دارن"""
    now_ms = time.time() * 1000
    if not enable:
        return "🔴"
    if expire_ms and expire_ms > 0 and now_ms > expire_ms:
        return "⏰"
    if total and total > 0 and used >= total:
        return "📛"
    return "🟢"


@router.callback_query(F.data == "menu:status")
async def menu_status(call: types.CallbackQuery):
    """
    به‌جای دامپ کامل هر سرویس، یه لیست دکمه‌ای می‌سازه — هر دکمه ایمیل یه
    سرویسه (پیام کاربر: «روی سرویس ایمیل کاربر نوشته شده باشه»)، با تپ روی
    هرکدوم وارد صفحه‌ی جزئیات/مدیریت همون سرویس می‌شه.
    سرویس‌هایی که دیگه روی پنل اصلی پیدا نشن (حذف شده) اصلاً توی این لیست
    نشون داده نمی‌شن — طبق درخواست کاربر.
    """
    from db import get_user_vpn_accounts
    from panel import get_client_status

    accounts = await run_db(get_user_vpn_accounts, call.from_user.id)
    if not accounts:
        await call.message.edit_text("📊 هنوز سرویس فعالی نداری.", reply_markup=home_button_kb())
        await call.answer()
        return

    await call.message.edit_text("⏳ در حال بررسی سرویس‌های شما روی سرور...")

    live_results = await asyncio.gather(
        *[get_client_status(acc[1]) for acc in accounts],  # acc[1] == email
        return_exceptions=True,
    )

    buttons = []
    for acc, live in zip(accounts, live_results):
        (account_id, email, uuid, sub_url, inbound_id, expire_time_db, data_limit_db,
         created_at, is_trial, service_name, category_name, purchase_id, note) = acc

        live = live if isinstance(live, dict) else None
        if live is None:
            # روی سرور اصلی پیدا نشد (حذف شده) — طبق درخواست کاربر، نشونش نمی‌دیم
            continue

        enable = live.get("enable", True)
        total = live.get("total") or 0
        used = (live.get("up") or 0) + (live.get("down") or 0)
        expire_ms = live.get("expiryTime") or 0
        dot = _status_dot(enable, expire_ms, total, used)

        buttons.append([InlineKeyboardButton(text=f"{dot} {email}", callback_data=f"svcdetail:{account_id}")])

    if not buttons:
        await call.message.edit_text(
            "📊 هیچ سرویس فعالی روی سرور برات پیدا نشد.\n"
            "(ممکنه سرویس‌هات از روی سرور اصلی حذف شده باشن)",
            reply_markup=home_button_kb(),
        )
        await call.answer()
        return

    buttons.append([InlineKeyboardButton(text="🏠 بازگشت به خانه", callback_data="menu:home")])

    await call.message.edit_text(
        "یکی از سرویس های خود را انتخاب کنید تا وارد پنل تنظیمات و مدیریت سرویس خود شوید .",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await call.answer()


async def _render_service_detail(call: types.CallbackQuery, account_id: int) -> bool:
    """
    رندر صفحه‌ی جزئیات/مدیریت یک سرویس (وضعیت، حجم، انقضا، یادداشت + دکمه‌های
    تمدید/روشن‌خاموش/یادداشت/لینک). هم از svcdetail و هم بعد از svctoggle صدا
    زده می‌شه تا صفحه با آخرین وضعیت رندر شه. True برمی‌گردونه اگه موفق بود.
    """
    from db import get_vpn_account
    from panel import get_client_status

    acc = await run_db(get_vpn_account, account_id, call.from_user.id)
    if not acc:
        await call.message.edit_text("این سرویس پیدا نشد یا مال شما نیست.", reply_markup=home_button_kb())
        return False

    (account_id, email, uuid, sub_url, inbound_id, expire_time_db, data_limit_db,
     created_at, is_trial, service_name, category_name, purchase_id, note, owner_id) = acc

    live = await get_client_status(email)
    if live is None:
        await call.message.edit_text(
            "⚠️ این سرویس دیگه روی سرور اصلی پیدا نشد (احتمالاً حذف شده).",
            reply_markup=home_button_kb(),
        )
        return False

    enable = live.get("enable", True)
    total = live.get("total") or 0
    used = (live.get("up") or 0) + (live.get("down") or 0)
    expire_ms = live.get("expiryTime") or 0
    status = _status_label(enable, expire_ms, total, used)

    sep = "─" * 22
    lines = [f"وضعیت سرویس : {status}", sep]
    lines.append(f"🗂 نام سرویس : {html.escape(service_name or '')}")
    code = purchase_id if purchase_id else account_id
    lines.append(f"🔑 کد سرویس: {code}")
    lines.append(f"📧 ایمیل: {html.escape(email or '')}")
    lines.append(sep)
    lines.append(f"🏷 یادداشت شما: {html.escape(note) if note else 'تنظیم نشده...'}")
    lines.append(sep)

    if total and total > 0:
        used_v = used or 0
        remaining = max(total - used_v, 0)
        lines.append(f"📥 حجم مصرف شده : {_fmt_bytes(used_v)}")
        lines.append(f"♾ حجم سرویس : {_fmt_bytes(total)}")
        bar = _progress_bar(used_v, total)
        if bar:
            lines.append(bar)
        lines.append(f"📶 باقی‌مانده: {_fmt_bytes(remaining)}")
    else:
        lines.append(f"📥 حجم مصرف شده : {_fmt_bytes(used or 0)}")
        lines.append("♾ حجم سرویس : نامحدود")

    if expire_ms and expire_ms > 0:
        expire_dt = datetime.fromtimestamp(expire_ms / 1000)
        delta = expire_dt - datetime.now()
        days_left = delta.days
        hours_left = delta.seconds // 3600
        if days_left >= 0:
            days_txt = f"( {days_left} روز و {hours_left} ساعت دیگر )"
        else:
            days_txt = "( منقضی شده )"
        lines.append(f"📅 فعال تا تاریخ : {expire_dt.strftime('%Y/%m/%d %H:%M')} {days_txt}")
    else:
        lines.append("📅 فعال تا تاریخ : نامحدود")

    text = "\n".join(lines)

    toggle_label = "🔴 خاموش کردن" if enable else "🟢 روشن کردن"
    kb_rows = [
        [InlineKeyboardButton(text="🏷 تنظیم یادداشت", callback_data=f"svcnote:{account_id}"),
         InlineKeyboardButton(text=toggle_label, callback_data=f"svctoggle:{account_id}:{0 if enable else 1}")],
    ]
    if purchase_id and not is_trial:
        kb_rows.append([
            InlineKeyboardButton(text="🔄 تمدید سرویس", callback_data=f"renew:{purchase_id}"),
            InlineKeyboardButton(text="🔗 دریافت لینک", callback_data=f"svclink:{account_id}"),
        ])
    else:
        kb_rows.append([InlineKeyboardButton(text="🔗 دریافت لینک", callback_data=f"svclink:{account_id}")])
    kb_rows.append([InlineKeyboardButton(text="🔙 برگشت به لیست سرویس‌ها", callback_data="menu:status")])

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    return True


@router.callback_query(F.data.startswith("svcdetail:"))
async def svc_detail(call: types.CallbackQuery):
    account_id = int(call.data.split(":")[1])
    await _render_service_detail(call, account_id)
    await call.answer()


@router.callback_query(F.data.startswith("svctoggle:"))
async def svc_toggle(call: types.CallbackQuery):
    """
    روشن/خاموش کردن واقعی کلاینت روی سرور اصلی (نه فقط توی دیتابیس خودمون).
    توضیح کامل نحوه‌ی کار و ریسک‌هاش توی panel.py (PanelClient.set_client_enable) هست.
    """
    from db import get_vpn_account
    from panel import set_client_enable

    parts = call.data.split(":")
    account_id = int(parts[1])
    new_enable = bool(int(parts[2]))

    acc = await run_db(get_vpn_account, account_id, call.from_user.id)
    if not acc:
        await call.answer("این سرویس پیدا نشد یا مال شما نیست.", show_alert=True)
        return
    email = acc[1]

    ok = await set_client_enable(email, new_enable)
    if not ok:
        await call.answer("❌ تغییر وضعیت روی سرور ناموفق بود. دوباره تلاش کن.", show_alert=True)
        return

    await _render_service_detail(call, account_id)
    await call.answer("✅ وضعیت سرویس تغییر کرد.")


@router.callback_query(F.data.startswith("svclink:"))
async def svc_link(call: types.CallbackQuery):
    from db import get_vpn_account

    account_id = int(call.data.split(":")[1])
    acc = await run_db(get_vpn_account, account_id, call.from_user.id)
    if not acc:
        await call.answer("این سرویس پیدا نشد یا مال شما نیست.", show_alert=True)
        return

    sub_url = acc[3]
    if not sub_url:
        await call.answer("لینکی برای این سرویس ثبت نشده.", show_alert=True)
        return

    safe_sub_url = html.escape(sub_url)
    await call.message.answer(
        f"🔗 لینک سابسکریپشن سرویس شما:\n<code>{safe_sub_url}</code>",
        parse_mode="HTML",
    )
    await call.answer()


@router.callback_query(F.data.startswith("svcnote:"))
async def svc_note_start(call: types.CallbackQuery, state: FSMContext):
    from db import get_vpn_account

    account_id = int(call.data.split(":")[1])
    acc = await run_db(get_vpn_account, account_id, call.from_user.id)
    if not acc:
        await call.answer("این سرویس پیدا نشد یا مال شما نیست.", show_alert=True)
        return

    await state.set_state(ServiceNote.waiting_text)
    await state.update_data(account_id=account_id)
    await call.message.answer(
        "🏷 یادداشت جدید برای این سرویس رو بفرست:\n"
        "(برای حذف یادداشت فعلی، فقط یک خط تیره «-» بفرست)"
    )
    await call.answer()


@router.message(ServiceNote.waiting_text)
async def svc_note_save(message: types.Message, state: FSMContext):
    from db import set_vpn_account_note

    data = await state.get_data()
    account_id = data.get("account_id")
    await state.clear()

    text = (message.text or "").strip()
    note = None if text == "-" else text[:200]

    await run_db(set_vpn_account_note, account_id, note)
    await message.answer("✅ یادداشت ذخیره شد.", reply_markup=home_button_kb())



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


# ================================================================
# SUPPORT (اطلاعات پشتیبانی — قابل مدیریت از پنل ادمین)
# ================================================================

@router.callback_query(F.data == "menu:support")
async def menu_support(call: types.CallbackQuery):
    from db import get_support_username, get_support_phone

    username = await run_db(get_support_username)
    phone = await run_db(get_support_phone)

    sep = "─" * 22
    lines = ["📞 پشتیبانی", sep]
    if username:
        lines.append(f"🆔 آیدی تلگرام: @{username.lstrip('@')}")
    if phone:
        lines.append(f"📱 شماره تماس: {phone}")
    if not username and not phone:
        lines.append("اطلاعات پشتیبانی هنوز توسط ادمین تنظیم نشده.")
    text = "\n".join(lines)

    buttons = []
    if username:
        buttons.append([InlineKeyboardButton(
            text="💬 گفتگو با پشتیبانی",
            url=f"https://t.me/{username.lstrip('@')}",
        )])
    buttons.append([InlineKeyboardButton(text="🏠 بازگشت به خانه", callback_data="menu:home")])

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await call.answer()


# ================================================================
# GLOBAL PHONE COLLECTION
# ================================================================
# میدل‌ور سراسری (middlewares.py) وقتی کاربری بدون شماره‌ی ثبت‌شده روی هر
# دکمه‌ای بزنه، ازش شماره می‌خواد. این هندلر اون شماره رو می‌گیره و ذخیره
# می‌کنه. عمداً StateFilter(None) داره تا با فلوهای دیگه‌ای که خودشون منتظر
# F.contact هستن (مثل تست رایگان یا درخواست همکاری، که state اختصاصی خودشون
# رو دارن) تداخل نکنه — این فقط وقتی اجرا می‌شه که کاربر توی هیچ FSM دیگه‌ای نباشه.

@router.message(StateFilter(None), F.contact)
async def collect_phone_globally(message: types.Message):
    from db import set_user_phone

    phone = normalize_phone(message.contact.phone_number)
    await run_db(set_user_phone, message.from_user.id, phone)
    await message.answer(
        "✅ شماره‌ت ثبت شد.\nحالا می‌تونی دوباره روی همون دکمه‌ای که می‌خواستی بزنی.",
        reply_markup=types.ReplyKeyboardRemove(),
    )