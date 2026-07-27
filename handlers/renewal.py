import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import is_admin
from db import (
    get_renewal_info,
    apply_renewal_after_panel_success,
    get_balance,
    log_manual_renewal,
    is_partner,
    get_categories_for_user,
)
from utils import run_db, data_label_short, notify_admins
from panel import renew_vpn_account
from keyboards import renew_confirm_kb, home_button_kb, cancel_kb, admin_panel_kb, categories_kb
from states import AdminRenewClient

router = Router()


async def _redirect_to_shop_with_explanation(call: CallbackQuery, reason: str):
    partner = await run_db(is_partner, call.from_user.id)
    categories = await run_db(get_categories_for_user, partner, call.from_user.id)

    if not categories:
        await call.message.edit_text(
            f"⚠️ {reason}\n\n"
            f"در حال حاضر دسته‌بندی‌ای هم برای خرید سرویس جدید موجود نیست.",
            reply_markup=home_button_kb(),
        )
        return

    bal = await run_db(get_balance, call.from_user.id)
    await call.message.edit_text(
        f"⚠️ {reason}\n"
        f"می‌تونی به‌جاش یه سرویس جدید بخری 👇\n\n"
        f"🛒 فروشگاه\n💰 موجودی شما: {bal:,} تومان\n\nیه دسته‌بندی انتخاب کن:",
        reply_markup=categories_kb(categories),
    )


# ================== مسیر کاربر/همکار (از صفحه‌ی وضعیت سرویس) ==================

@router.callback_query(F.data.startswith("renew:"))
async def renew_prompt(call: CallbackQuery):
    purchase_id = int(call.data.split(":")[1])
    info = await run_db(get_renewal_info, purchase_id, call.from_user.id)
    if not info:
        await call.answer(
            "این سرویس امکان تمدید خودکار نداره (یا مال شما نیست).",
            show_alert=True,
        )
        await _redirect_to_shop_with_explanation(
            call, "این سرویس امکان تمدید خودکار نداره (یا مال شما نیست)."
        )
        return

    # آپدیت: 8 فیلد برمی‌گردد
    email, service_id, service_name, price, duration_days, data_limit_gb, owner_id, panel_id = info
    dl = data_label_short(data_limit_gb)
    text = (
        f"🔄 تمدید اشتراک «{service_name}»\n"
        f"─────────────────\n"
        f"⏳ افزایش مدت: {duration_days} روز\n"
        f"📶 افزایش حجم: {dl}\n"
        f"💰 هزینه (قیمت فعلی): {price:,} تومان\n"
        f"─────────────────\n"
        f"با تایید، مبلغ از موجودی‌ات کسر و اشتراک تمدید می‌شه."
    )
    await call.message.answer(text, reply_markup=renew_confirm_kb(purchase_id))
    await call.answer()


@router.callback_query(F.data.startswith("renew_confirm:"))
async def renew_confirm(call: CallbackQuery):
    purchase_id = int(call.data.split(":")[1])
    user_id = call.from_user.id

    info = await run_db(get_renewal_info, purchase_id, user_id)
    if not info:
        await call.answer("این سرویس پیدا نشد یا مال شما نیست.", show_alert=True)
        await _redirect_to_shop_with_explanation(call, "این سرویس پیدا نشد یا مال شما نیست.")
        return
        
    email, service_id, service_name, price, duration_days, data_limit_gb, owner_id, panel_id = info

    balance = await run_db(get_balance, user_id)
    if balance < price:
        await call.answer("موجودی کافی نیست.", show_alert=True)
        return

    add_bytes = int(data_limit_gb * 1024 ** 3) if data_limit_gb and data_limit_gb > 0 else 0

    # مرحله‌ی ۱: اول پنل — اتصال به پنل درست
    ok = await renew_vpn_account(email, add_days=duration_days, add_bytes=add_bytes, panel_id=panel_id or 1)
    if not ok:
        await call.message.edit_text(
            "❌ تمدید روی پنل ناموفق بود. هیچ مبلغی از حساب شما کم نشد.\n"
            "لطفاً دوباره تلاش کن یا با پشتیبانی تماس بگیر.",
            reply_markup=home_button_kb(),
        )
        await call.answer()
        return

    # مرحله‌ی ۲: پنل موفق بود → حالا کسر پول + آپدیت محلی، اتمیک
    saved = await run_db(
        apply_renewal_after_panel_success, user_id, purchase_id, price, duration_days, add_bytes
    )
    if not saved:
        logging.error(
            f"Renewal: panel succeeded but local balance deduction failed — "
            f"user={user_id} purchase={purchase_id} amount={price}"
        )
        await call.message.edit_text(
            "⚠️ اشتراک روی پنل تمدید شد ولی موجودی‌ات به‌موقع کسر نشد "
            "(تراکنش هم‌زمان دیگه‌ای در جریان بود). این مورد به ادمین گزارش شد.",
            reply_markup=home_button_kb(),
        )
        await call.answer()
        return

    await call.message.edit_text(
        f"✅ اشتراک «{service_name}» با موفقیت تمدید شد.\n"
        f"⏳ +{duration_days} روز | 📶 +{data_label_short(data_limit_gb)}\n"
        f"💰 {price:,} تومان از موجودی کسر شد.",
        reply_markup=home_button_kb(),
    )
    await call.answer()

    username = call.from_user.username or "ندارد"
    await notify_admins(
        call.bot,
        f"🔄 تمدید اشتراک!\n"
        f"👤 User: {user_id} (@{username})\n"
        f"📦 سرویس: {service_name}\n"
        f"⏳ +{duration_days} روز | 📶 +{data_label_short(data_limit_gb)}\n"
        f"💰 مبلغ: {price:,} تومان\n"
        f"🔑 سفارش: #{purchase_id}"
    )


# ================== مسیر ادمین (تمدید دستی با ایمیل/آیدی کلاینت) ==================

@router.callback_query(F.data == "admin:renew_manual")
async def admin_renew_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return
    await state.set_state(AdminRenewClient.waiting_email)
    await call.message.edit_text(
        "📧 ایمیل یا آیدی کلاینت روی پنل (email) رو وارد کن:",
        reply_markup=cancel_kb(),
    )
    await call.answer()


@router.message(AdminRenewClient.waiting_email)
async def admin_renew_email(message: Message, state: FSMContext):
    email = (message.text or "").strip()
    if not email:
        await message.answer("ایمیل نامعتبره. دوباره وارد کن:")
        return
    await state.update_data(email=email)
    await state.set_state(AdminRenewClient.waiting_days)
    await message.answer("⏳ چند روز اضافه بشه؟ (اگه نمی‌خوای روز اضافه بشه، عدد 0 بفرست)")


@router.message(AdminRenewClient.waiting_days)
async def admin_renew_days(message: Message, state: FSMContext):
    try:
        days = int((message.text or "").strip())
        if days < 0:
            raise ValueError
    except ValueError:
        await message.answer("یک عدد صحیح و غیرمنفی وارد کن:")
        return
    await state.update_data(days=days)
    await state.set_state(AdminRenewClient.waiting_gb)
    await message.answer("📶 چند گیگابایت اضافه بشه؟ (برای بدون تغییر حجم، عدد 0 بفرست)")


@router.message(AdminRenewClient.waiting_gb)
async def admin_renew_gb(message: Message, state: FSMContext):
    try:
        gb = float((message.text or "").strip())
        if gb < 0:
            raise ValueError
    except ValueError:
        await message.answer("یک عدد معتبر وارد کن:")
        return

    data = await state.get_data()
    email = data["email"]
    days = data["days"]
    add_bytes = int(gb * 1024 ** 3) if gb > 0 else 0

    if days == 0 and add_bytes == 0:
        await state.clear()
        await message.answer("هیچ مقداری برای افزایش وارد نشد — عملیات لغو شد.", reply_markup=admin_panel_kb())
        return

    def _get_panel_id_by_email(email_addr):
        from db import connect as _conn
        conn = _conn()
        cur = conn.cursor()
        cur.execute("SELECT panel_id FROM vpn_accounts WHERE email=%s LIMIT 1", (email_addr,))
        r = cur.fetchone()
        conn.close()
        return r[0] if r and r[0] else 1

    panel_id = await run_db(_get_panel_id_by_email, email)
    ok = await renew_vpn_account(email, add_days=days, add_bytes=add_bytes, panel_id=panel_id)
    
    await state.clear()

    if not ok:
        await message.answer(
            f"❌ تمدید ایمیل «{email}» روی پنل ناموفق بود. مطمئن شو ایمیل درسته.",
            reply_markup=admin_panel_kb(),
        )
        return

    await run_db(log_manual_renewal, email, days, add_bytes, message.from_user.id)
    await message.answer(
        f"✅ تمدید انجام شد.\n📧 {email}\n⏳ +{days} روز | 📶 +{gb:g}GB",
        reply_markup=admin_panel_kb(),
    )

    admin_username = message.from_user.username or "ندارد"
    await notify_admins(
        message.bot,
        f"🔄 تمدید دستی (توسط ادمین)!\n"
        f"👮 انجام‌دهنده: {message.from_user.id} (@{admin_username})\n"
        f"📧 ایمیل: {email}\n"
        f"⏳ +{days} روز | 📶 +{gb:g}GB"
    )