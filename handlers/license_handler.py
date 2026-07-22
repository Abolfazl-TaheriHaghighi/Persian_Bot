import os
import html
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_ID, BOT_TOKEN, MASTER_KEY, is_admin
from db import save_license_key, get_license_key
from license import verify_license, check_license_from_db, warm_cache, clear_cache, generate_license, get_instance_id
from keyboards import home_button_kb
from utils import run_db

router = Router()


def is_super_admin() -> bool:
    return bool(MASTER_KEY)


class LicenseInput(StatesGroup):
    waiting_key = State()


class LicenseCreate(StatesGroup):
    waiting_token = State()
    waiting_days = State()


# ================================================================
# وضعیت لایسنس (برای همه ادمین‌ها)
# ================================================================

def license_status_kb():
    buttons = [
        [InlineKeyboardButton(text="🔑 وارد کردن لایسنس", callback_data="license:input")],
    ]
    if is_super_admin():
        buttons.append([InlineKeyboardButton(text="🛠 ساخت لایسنس جدید", callback_data="license:create")])
    buttons.append([InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "admin:license")
async def admin_license_menu(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    result = await run_db(check_license_from_db, BOT_TOKEN)
    sep = "─" * 22

    if result.get("permanent"):
        text = (
            f"🔑 وضعیت لایسنس\n{sep}\n"
            f"✅ لایسنس دائمی فعاله\n"
            f"👑 همه قابلیت‌های پرو فعال"
        )
    elif result["valid"]:
        text = (
            f"🔑 وضعیت لایسنس\n{sep}\n"
            f"✅ پرو — فعال\n"
            f"📅 انقضا: {result['expire_date']}\n"
            f"⏳ {result['days_left']} روز مونده"
        )
    elif result["error"] == "لایسنس منقضی شده":
        text = (
            f"🔑 وضعیت لایسنس\n{sep}\n"
            f"❌ لایسنس منقضی شده\n"
            f"📅 تاریخ انقضا: {result['expire_date']}\n\n"
            f"برای تمدید، لایسنس جدید وارد کن."
        )
    else:
        text = (
            f"🔑 وضعیت لایسنس\n{sep}\n"
            f"⚠️ {result['error'] or 'لایسنس وارد نشده'}\n\n"
            f"در حالت رایگان:\n"
            f"• حداکثر ۱ دسته‌بندی و ۲ سرویس\n"
            f"• بدون رفرال، جوین اجباری، همکاران و..."
        )

    await call.message.edit_text(text, reply_markup=license_status_kb())
    await call.answer()


# ================================================================
# وارد کردن لایسنس (برای همه ادمین‌ها)
# ================================================================

@router.callback_query(F.data == "license:input")
async def license_input_start(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(LicenseInput.waiting_key)
    await call.message.answer("🔑 لایسنس کی رو وارد کن:")
    await call.answer()


@router.message(LicenseInput.waiting_key)
async def license_input_save(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    key = message.text.strip()
    result = verify_license(key, BOT_TOKEN)

    if not result["valid"]:
        await state.clear()
        await message.answer(
            f"❌ لایسنس نامعتبر\n{result['error']}",
            reply_markup=home_button_kb()
        )
        return

    await run_db(save_license_key, key)
    await run_db(warm_cache, BOT_TOKEN)  # cache رو با DB جدید گرم کن
    await state.clear()

    sep = "─" * 22
    if result.get("permanent"):
        text = f"✅ لایسنس دائمی فعال شد!\n{sep}\n👑 همه قابلیت‌های پرو فعال شدن."
    else:
        text = (
            f"✅ لایسنس فعال شد!\n{sep}\n"
            f"📅 انقضا: {result['expire_date']}\n"
            f"⏳ {result['days_left']} روز اعتبار\n"
            f"👑 همه قابلیت‌های پرو فعال شدن."
        )

    await message.answer(text, reply_markup=home_button_kb())


# ================================================================
# ساخت لایسنس — فقط برای صاحب اصلی (MASTER_KEY)
# ================================================================

@router.callback_query(F.data == "license:create")
async def license_create_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID or not is_super_admin():
        await call.answer("❌ دسترسی ندارید", show_alert=True)
        return
    await state.set_state(LicenseCreate.waiting_token)
    await call.message.answer(
        "🛠 ساخت لایسنس جدید\n\n"
        "BOT_TOKEN ربات مشتری رو وارد کن:"
    )
    await call.answer()


@router.message(LicenseCreate.waiting_token)
async def license_create_token(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID or not is_super_admin():
        return
    token = message.text.strip()
    if ":" not in token or len(token) < 30:
        await message.answer("❌ توکن نامعتبر به نظر میرسه. دوباره وارد کن:")
        return
    await state.update_data(target_token=token)
    await state.set_state(LicenseCreate.waiting_days)
    instance_id = get_instance_id(token)
    # نکته: instance_id یک هگزادسیمال ساده است (فقط 0-9a-f) و با Markdown مشکلی نداره،
    # ولی برای یکدست بودن سبک با بقیه‌ی پیام‌های این فایل، همینجا هم HTML استفاده می‌شه.
    await message.answer(
        f"✅ توکن ثبت شد\n"
        f"🆔 Instance ID: <code>{html.escape(instance_id)}</code>\n\n"
        f"⏳ تعداد روز اعتبار رو وارد کن:\n"
        f"(0 = نامحدود)",
        parse_mode="HTML"
    )


@router.message(LicenseCreate.waiting_days)
async def license_create_days(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID or not is_super_admin():
        return
    if not message.text.isdigit():
        await message.answer("❌ فقط عدد:")
        return
    days = int(message.text)
    data = await state.get_data()
    token = data["target_token"]

    license_key = generate_license(token, days)
    await state.clear()

    sep = "─" * 22
    if days == 0:
        expire_text = "نامحدود"
    else:
        from datetime import datetime, timedelta
        expire_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        expire_text = f"{days} روز (تا {expire_date})"

    # نکته‌ی امنیتی مهم: license_key خروجی Fernet.encrypt است که base64 urlsafe
    # است و می‌تونه کاراکترهای _ و - داشته باشه. با parse_mode="Markdown" قدیمی،
    # یک _ جفت‌نشده باعث خطای "can't find end of the entity" و کرش کل پیام می‌شه
    # (دقیقاً همون کلاس باگی که در وضعیت سرویس‌ها هم رخ داد). برای همین HTML +
    # escape استفاده می‌شه تا این ریسک برای همیشه از بین بره.
    safe_license_key = html.escape(license_key)
    await message.answer(
        f"✅ لایسنس ساخته شد!\n{sep}\n"
        f"⏳ اعتبار: {expire_text}\n{sep}\n"
        f"🔑 لایسنس:\n<code>{safe_license_key}</code>\n{sep}\n"
        f"این لایسنس رو به مشتری بده تا از پنل ادمین وارد کنه.",
        parse_mode="HTML",
        reply_markup=home_button_kb()
    )