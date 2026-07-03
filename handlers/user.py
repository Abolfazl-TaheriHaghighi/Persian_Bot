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
# نکته‌ی مهم: این بخش دیگه به پنل زنده وصل نمی‌شه (get_client_status حذف شد).
# چون اتصال زنده به پنل کند/ناپایدار بود و باعث تاخیر و timeout می‌شد، الان فقط
# از اطلاعات ذخیره‌شده در دیتابیس خودِ ربات (سریع و همیشه در دسترس) استفاده می‌کنیم
# و کاربر رو برای وضعیت لحظه‌ای (حجم مصرفی زنده) به اپلیکیشن VPN خودش با لینک ساب
# هدایت می‌کنیم — چون خودِ اپ‌های VPN معمولاً وضعیت مصرف رو از سرور می‌خونن.

def _fmt_total_bytes(b) -> str:
    if not b or b <= 0:
        return "♾ نامحدود"
    b = float(b)
    if b >= 1024 ** 3:
        return f"{b / 1024 ** 3:.2f} GB"
    if b >= 1024 ** 2:
        return f"{b / 1024 ** 2:.0f} MB"
    return f"{b / 1024:.0f} KB"


def _fmt_time_left(target_dt) -> str:
    import datetime
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


# تلگرام حداکثر ۴۰۹۶ کاراکتر برای هر پیام قبول می‌کنه. مقدار پایین‌تر برای
# حاشیه‌ی امن در نظر گرفته شده (چون header/footer هم به هر chunk اضافه می‌شن)
_MAX_MESSAGE_LEN = 3500


@router.message(F.text == "📊 وضعیت سرویس‌ها")
async def service_status(message: types.Message):
    import html
    from db import get_user_vpn_accounts

    accounts = await run_db(get_user_vpn_accounts, message.from_user.id)
    if not accounts:
        await message.answer("📊 هنوز سرویس فعالی نداری.")
        return

    sep = "─" * 22
    header = f"📊 وضعیت سرویس‌های شما\n{sep}\n"
    footer = (
        "\nℹ️ برای دیدن وضعیت لحظه‌ای (حجم مصرفی/باقی‌مانده)، لینک سابسکریپشن بالا رو "
        "داخل اپلیکیشن VPN خودت وارد کن و از همون‌جا وضعیت سرویست رو ببین."
    )

    # هر سرویس به‌صورت یک بلوک کامل و جدا ساخته می‌شه، تا موقع تقسیم پیام هیچ‌وقت
    # وسط یک <code> یا یک سرویس بریده نشه (که باعث خطای HTML entity می‌شد)
    blocks = []
    for acc in accounts:
        (email, uuid, sub_url, inbound_id, expire_time_db, data_limit_db,
         created_at, is_trial, service_name, category_name, purchase_id) = acc

        label = "🧪 تست رایگان" if is_trial else "💎 سرویس"

        # نکته‌ی امنیتی: ایمیل، نام سرویس، دسته‌بندی و لینک ساب همگی مقادیر
        # داینامیک هستن (بعضی‌شون از قبل با فرمت قدیمی دارای _ ساخته شدن) و اگه
        # با parse_mode="Markdown" (نسخه‌ی قدیمی و شکننده) فرستاده بشن، یک _ یا *
        # جفت‌نشده باعث خطای "can't find end of the entity" و کرش کل پیام می‌شه.
        # برای همین از HTML استفاده می‌کنیم و همه‌ی مقادیر داینامیک رو escape می‌کنیم.
        safe_service_name = html.escape(service_name or "")
        safe_category_name = html.escape(category_name or "")
        safe_email = html.escape(email or "")

        block = f"{label}\n"
        if purchase_id:
            block += f"🔑 شماره سفارش: #{purchase_id}\n"
        block += f"📦 نام: {safe_service_name}\n"
        if not is_trial:
            block += f"🗂 دسته‌بندی: {safe_category_name}\n"
        block += f"📧 ایمیل کلاینت: {safe_email}\n"

        block += f"📶 حجم کل: {_fmt_total_bytes(data_limit_db)}\n"

        if sub_url:
            safe_sub_url = html.escape(sub_url)
            block += f"🔗 لینک سابسکریپشن:\n<code>{safe_sub_url}</code>\n"

            # طبق داکیومنت پنل، همین لینک ساب با ?html=1 یک صفحه‌ی وضعیت زنده
            # (ترافیک مصرفی/باقی‌مانده، انقضا) رو مستقیماً از خودِ پنل رندر می‌کنه —
            # پس نیازی به تماس ربات با API پنل نیست. اینجا به‌جای <code> از <a> استفاده
            # می‌شه تا با یک تپ داخل مرورگر باز بشه.
            separator = "&" if "?" in sub_url else "?"
            live_status_url = f"{sub_url}{separator}html=1"
            safe_live_status_url = html.escape(live_status_url, quote=True)
            block += (
                f"📡 دیدن لحظه‌ای وضعیت سرویس و حجم باقی‌مانده:\n"
                f"<a href=\"{safe_live_status_url}\">مشاهده وضعیت زنده</a>\n"
                f"⚠️ اگه صفحه‌ی وضعیت چیزی نشون نداد، اول فیلترشکن (VPN) گوشی یا سیستمت رو "
                f"خاموش کن و دوباره امتحان کن. اگه بازم چیزی نمایش داده نشد، یعنی این سرویس "
                f"به‌خاطر اتمام حجم یا پایان مدت اشتراک از روی پنل حذف شده.\n"
            )

        block += f"{sep}\n"
        blocks.append(block)

    # بلوک‌ها رو در چند پیام (chunk) جمع می‌کنیم، بدون شکستن وسط یک سرویس
    chunks = []
    current = header
    for block in blocks:
        if len(current) + len(block) > _MAX_MESSAGE_LEN and current != header:
            chunks.append(current)
            current = ""
        current += block
    if current:
        chunks.append(current)

    if chunks and len(chunks[-1]) + len(footer) <= _MAX_MESSAGE_LEN:
        chunks[-1] += footer
    else:
        chunks.append(footer)

    for chunk in chunks:
        await message.answer(chunk, parse_mode="HTML")
        if len(chunks) > 1:
            import asyncio
            await asyncio.sleep(0.05)


# ================================================================
# PURCHASE HISTORY
# ================================================================

@router.message(F.text == "📋 خریدهای من")
async def my_purchases(message: types.Message):
    purchases = await run_db(get_user_purchases, message.from_user.id)
    if not purchases:
        await message.answer("📋 هنوز خریدی نداشتی.")
        return

    sep = "─" * 22
    text = f"📋 تاریخچه خریدهای شما\n{sep}\n"
    for p in purchases:
        pid, sname, amt, pat, category_name = p
        text += (
            f"📦 نام: {sname}\n"
            f"🔑 شماره سفارش: #{pid}\n"
            f"🗂 دسته‌بندی: {category_name}\n"
            f"💰 مبلغ: {amt:,} تومان\n"
            f"📅 تاریخ: {pat.strftime('%Y-%m-%d %H:%M')}\n"
            f"{sep}\n"
        )

    # نکته: get_user_purchases با LIMIT 10 محدود شده، پس طول این پیام هیچ‌وقت
    # به سقف ۴۰۹۶ کاراکتری تلگرام نمی‌رسه و نیازی به chunk کردن نداره
    # (برخلاف وضعیت سرویس‌ها که تعداد سرویس‌ها می‌تونه نامحدود باشه)
    await message.answer(text)