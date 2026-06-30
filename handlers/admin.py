from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_ID, is_admin
from db import (
    get_all_users, get_pending_transactions, get_all_purchases,
    get_all_categories, get_category, add_category, toggle_category, delete_category,
    get_all_services, get_service, add_service, toggle_service, hard_delete_service, update_service,
    get_all_discount_codes, create_discount_code, delete_discount_code,
    get_balance, set_balance, add_balance,
    get_trial_config, update_trial_config,
    get_all_phone_overrides, set_phone_max_uses, delete_phone_override, get_all_trial_uses,
    get_referral_config, update_referral_config,
    get_all_channels, add_channel, delete_channel, toggle_channel,
    get_all_partners, get_partner, add_partner, remove_partner,
    get_user_purchases,
    connect as db_connect
)
from keyboards import (
    get_kb, back_kb, admin_panel_kb,
    admin_categories_kb, admin_services_kb, admin_svc_detail_kb,
    admin_edit_svc_fields_kb, admin_discounts_kb,
    admin_trial_menu_kb, admin_referral_menu_kb
)
from states import (
    AdminAddCategory, AdminAddService, AdminEditService,
    AdminEditBalance, AdminDiscountCode,
    AdminTrialConfig, AdminPhoneOverride, AdminReferralConfig,
    AdminAddChannel, AdminAddPartnerManual
)
from pro_guard import (
    require_pro, check_free_category_limit, check_free_service_limit
)
from utils import format_data, data_label_short, normalize_phone, run_db

router = Router()


# ================================================================
# ADMIN PANEL
# ================================================================

@router.message(F.text == "🛠 پنل ادمین")
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("🛠 پنل مدیریت:", reply_markup=admin_panel_kb())


@router.callback_query(F.data == "admin:back")
async def admin_back(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("🛠 پنل مدیریت:", reply_markup=admin_panel_kb())
    await call.answer()


@router.callback_query(F.data == "admin:users")
async def admin_users(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    users = await run_db(get_all_users)
    text = f"👥 تعداد کاربران: {len(users)}\n\n"
    for u in users:
        text += f"🆔 {u[0]} | 💰 {u[1]:,} تومان\n"
    await call.message.edit_text(text, reply_markup=back_kb("admin:back"))
    await call.answer()


@router.callback_query(F.data == "admin:pending")
async def admin_pending(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    txs = await run_db(get_pending_transactions)
    if not txs:
        text = "✅ تراکنش در انتظاری وجود نداره."
    else:
        text = f"💳 تراکنش‌های در انتظار ({len(txs)}):\n\n"
        for tx in txs:
            tid, uid, amt, cat = tx
            text += f"🔑 #{tid} | 👤 {uid} | 💰 {amt:,} تومان\n"
    await call.message.edit_text(text, reply_markup=back_kb("admin:back"))
    await call.answer()


@router.callback_query(F.data == "admin:purchases")
async def admin_purchases(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    purchases = await run_db(get_all_purchases)
    if not purchases:
        text = "📋 هنوز خریدی انجام نشده."
    else:
        text = f"🛍 آخرین خریدها ({len(purchases)}):\n\n"
        for p in purchases:
            pid, uid, sname, amt, pat = p
            text += f"#{pid} | 👤{uid} | {sname} | {amt:,}T | {pat.strftime('%m-%d %H:%M')}\n"
    await call.message.edit_text(text, reply_markup=back_kb("admin:back"))
    await call.answer()


# ================================================================
# CATEGORIES
# ================================================================

@router.callback_query(F.data == "admin:categories")
async def admin_categories(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cats = await run_db(get_all_categories, active_only=False)
    if not cats:
        await call.message.edit_text("🗂 هیچ دسته‌ای ثبت نشده.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ افزودن دسته", callback_data="admin:add_category")],
            [InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:back")]
        ]))
    else:
        await call.message.edit_text("🗂 دسته‌بندی‌ها:\n✅=فعال | ❌=غیرفعال", reply_markup=admin_categories_kb(cats))
    await call.answer()


@router.callback_query(F.data.startswith("admin:toggle_cat:"))
async def admin_toggle_cat(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cat_id = int(call.data.split(":")[2])
    new_status = await run_db(toggle_category, cat_id)
    await call.answer("✅ فعال شد" if new_status else "❌ غیرفعال شد", show_alert=True)
    cats = await run_db(get_all_categories, active_only=False)
    await call.message.edit_text("🗂 دسته‌بندی‌ها:\n✅=فعال | ❌=غیرفعال", reply_markup=admin_categories_kb(cats))


@router.callback_query(F.data.startswith("admin:del_cat:"))
async def admin_del_cat(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cat_id = int(call.data.split(":")[2])
    await run_db(delete_category, cat_id)
    await call.answer("🗑 دسته غیرفعال شد", show_alert=True)
    cats = await run_db(get_all_categories, active_only=False)
    if cats:
        await call.message.edit_text("🗂 دسته‌بندی‌ها:", reply_markup=admin_categories_kb(cats))
    else:
        await call.message.edit_text("🗂 هیچ دسته‌ای باقی نمونده.", reply_markup=back_kb("admin:back"))


@router.callback_query(F.data == "admin:add_category")
async def admin_add_cat_start(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    if not await check_free_category_limit(call):
        return
    await state.set_state(AdminAddCategory.name)
    await call.message.answer("🗂 نام دسته‌بندی رو وارد کن:")
    await call.answer()


@router.message(AdminAddCategory.name)
async def admin_add_cat_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminAddCategory.emoji)
    await message.answer("😀 ایموجی دسته رو بفرست (مثلاً 🌍 یا 🔥)\nیا /skip برای پیش‌فرض 📦:")


@router.message(AdminAddCategory.emoji)
async def admin_add_cat_emoji(message: types.Message, state: FSMContext):
    emoji = "📦" if message.text == "/skip" else message.text.strip()
    data = await state.get_data()
    cid = await run_db(add_category, data["name"], emoji)
    await state.clear()
    await message.answer(
        f"✅ دسته‌بندی اضافه شد!\n{emoji} {data['name']}\n🔑 ID: {cid}",
        reply_markup=get_kb(message.from_user.id)
    )


# ================================================================
# SERVICES
# ================================================================

@router.callback_query(F.data == "admin:services")
async def admin_services_list(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    services = await run_db(get_all_services, active_only=False)
    if not services:
        await call.message.edit_text("📦 هیچ سرویسی ثبت نشده.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ افزودن سرویس", callback_data="admin:add_service")],
            [InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:back")]
        ]))
    else:
        await call.message.edit_text("📦 سرویس‌ها:\n✅=فعال | ❌=غیرفعال", reply_markup=admin_services_kb(services))
    await call.answer()


@router.callback_query(F.data.startswith("admin:svc_detail:"))
async def admin_svc_detail(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    sid = int(call.data.split(":")[2])
    service = await run_db(get_service, sid)
    if not service:
        await call.answer("❌ سرویس پیدا نشد", show_alert=True)
        return
    s_id, name, desc, price, days, data_gb, is_active, cat_name = service
    sep = "─" * 22
    text = (
        f"📦 جزئیات سرویس\n{sep}\n"
        f"نام: {name}\n"
        f"دسته: {cat_name or '—'}\n"
        f"توضیحات: {desc or '—'}\n"
        f"قیمت: {price:,} تومان\n"
        f"مدت: {days} روز\n"
        f"حجم: {format_data(data_gb)}\n"
        f"وضعیت: {'✅ فعال' if is_active else '❌ غیرفعال'}\n"
    )
    await call.message.edit_text(text, reply_markup=admin_svc_detail_kb(sid, is_active))
    await call.answer()


@router.callback_query(F.data.startswith("admin:toggle:"))
async def admin_toggle_service(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    sid = int(call.data.split(":")[2])
    new_status = await run_db(toggle_service, sid)
    await call.answer("✅ فعال شد" if new_status else "❌ غیرفعال شد", show_alert=True)
    service = await run_db(get_service, sid)
    if service:
        s_id, name, desc, price, days, data_gb, is_active, cat_name = service
        sep = "─" * 22
        text = (
            f"📦 جزئیات سرویس\n{sep}\n"
            f"نام: {name}\nدسته: {cat_name or '—'}\nتوضیحات: {desc or '—'}\n"
            f"قیمت: {price:,} تومان\nمدت: {days} روز\nحجم: {format_data(data_gb)}\n"
            f"وضعیت: {'✅ فعال' if is_active else '❌ غیرفعال'}\n"
        )
        await call.message.edit_text(text, reply_markup=admin_svc_detail_kb(sid, is_active))


@router.callback_query(F.data.startswith("admin:hard_del:"))
async def admin_hard_del_service(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    sid = int(call.data.split(":")[2])
    await run_db(hard_delete_service, sid)
    await call.answer("🗑 سرویس کاملاً حذف شد", show_alert=True)
    services = await run_db(get_all_services, active_only=False)
    if services:
        await call.message.edit_text("📦 سرویس‌ها:", reply_markup=admin_services_kb(services))
    else:
        await call.message.edit_text("📦 هیچ سرویسی باقی نمونده.", reply_markup=back_kb("admin:back"))


# ---- ویرایش سرویس ----

@router.callback_query(F.data.startswith("admin:edit_svc:"))
async def admin_edit_svc(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    sid = int(call.data.split(":")[2])
    await state.set_state(AdminEditService.choosing_field)
    await state.update_data(editing_sid=sid)
    await call.message.edit_text("✏️ کدوم فیلد رو می‌خوای ویرایش کنی؟", reply_markup=admin_edit_svc_fields_kb(sid))
    await call.answer()


@router.callback_query(F.data.startswith("admin:editfield:"), AdminEditService.choosing_field)
async def admin_editfield(call: types.CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    sid = int(parts[2])
    field = parts[3]
    await state.update_data(editing_field=field)
    await state.set_state(AdminEditService.entering_value)
    prompts = {
        "name":        "📦 نام جدید سرویس رو وارد کن:",
        "description": "📝 توضیحات جدید رو وارد کن (یا /skip برای خالی):",
        "price":       "💰 قیمت جدید رو به تومان وارد کن:",
        "duration":    "⏳ مدت جدید رو به روز وارد کن:",
        "data_limit":  "📶 حجم جدید رو به GB وارد کن (0=نامحدود، مثلاً 30 یا 0.5):",
        "category":    "🗂 آی‌دی دسته جدید رو وارد کن (0=بدون دسته):",
    }
    await call.message.answer(prompts.get(field, "مقدار جدید رو وارد کن:"))
    await call.answer()


@router.message(AdminEditService.entering_value)
async def admin_save_edit(message: types.Message, state: FSMContext):
    data = await state.get_data()
    sid = data["editing_sid"]
    field = data["editing_field"]
    raw = message.text.strip()

    if field in ("price", "duration"):
        if not raw.isdigit():
            await message.answer("❌ فقط عدد صحیح:")
            return
        value = int(raw)
    elif field == "data_limit":
        try:
            value = float(raw.replace(",", "."))
            if value < 0:
                raise ValueError
        except ValueError:
            await message.answer("❌ عدد معتبر وارد کن:")
            return
    elif field == "category":
        if not raw.isdigit():
            await message.answer("❌ آی‌دی باید عدد باشه:")
            return
        value = int(raw) if int(raw) != 0 else None
    elif field == "description":
        value = "" if raw == "/skip" else raw
    else:
        value = raw

    await run_db(update_service, sid, field, value)
    await state.clear()
    await message.answer("✅ سرویس آپدیت شد!", reply_markup=get_kb(message.from_user.id))


# ---- افزودن سرویس ----

@router.callback_query(F.data == "admin:add_service")
async def admin_add_service_start(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    if not await check_free_service_limit(call):
        return
    cats = await run_db(get_all_categories, active_only=True)
    buttons = [[InlineKeyboardButton(text=f"{c[2]} {c[1]}", callback_data=f"admin:svc_cat:{c[0]}")] for c in cats]
    buttons.append([InlineKeyboardButton(text="بدون دسته", callback_data="admin:svc_cat:0")])
    await state.set_state(AdminAddService.category)
    await call.message.answer("🗂 دسته‌بندی سرویس رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await call.answer()


@router.callback_query(F.data.startswith("admin:svc_cat:"), AdminAddService.category)
async def admin_add_svc_cat(call: types.CallbackQuery, state: FSMContext):
    cat_id = call.data.split(":")[2]
    await state.update_data(category_id=int(cat_id) if cat_id != "0" else None)
    await state.set_state(AdminAddService.name)
    await call.message.answer("📦 نام سرویس رو وارد کن:")
    await call.answer()


@router.message(AdminAddService.name)
async def admin_add_svc_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminAddService.description)
    await message.answer("📝 توضیحات رو وارد کن (یا /skip):")


@router.message(AdminAddService.description)
async def admin_add_svc_desc(message: types.Message, state: FSMContext):
    desc = "" if message.text == "/skip" else message.text.strip()
    await state.update_data(description=desc)
    await state.set_state(AdminAddService.price)
    await message.answer("💰 قیمت رو به تومان وارد کن:")


@router.message(AdminAddService.price)
async def admin_add_svc_price(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ فقط عدد:")
        return
    await state.update_data(price=int(message.text))
    await state.set_state(AdminAddService.duration)
    await message.answer("⏳ مدت رو به روز وارد کن:")


@router.message(AdminAddService.duration)
async def admin_add_svc_duration(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ فقط عدد:")
        return
    await state.update_data(duration=int(message.text))
    await state.set_state(AdminAddService.data_limit)
    await message.answer("📶 حجم رو به گیگابایت وارد کن:\n• 0 = نامحدود\n• مثال: 30 یا 30.5 یا 0.1")


@router.message(AdminAddService.data_limit)
async def admin_add_svc_data(message: types.Message, state: FSMContext):
    raw = message.text.strip().replace(",", ".")
    try:
        data_gb = float(raw)
        if data_gb < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ عدد معتبر وارد کن:")
        return
    data = await state.get_data()
    sid = await run_db(add_service, data["name"], data.get("description", ""), data["price"], data["duration"], data_gb, data.get("category_id"))
    await state.clear()
    await message.answer(
        f"✅ سرویس اضافه شد!\n\n📦 {data['name']}\n"
        f"💰 {data['price']:,} تومان | ⏳ {data['duration']} روز | {format_data(data_gb)}\n🔑 ID: {sid}",
        reply_markup=get_kb(message.from_user.id)
    )


# ================================================================
# DISCOUNT CODES
# ================================================================

@router.callback_query(F.data == "admin:discounts")
async def admin_discounts(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    if not await require_pro(call, "کد تخفیف"):
        return
    codes = await run_db(get_all_discount_codes)
    text = "🎁 کدهای تخفیف:\n(برای حذف روی کد کلیک کن)\n\n"
    if not codes:
        text += "هیچ کدی ثبت نشده."
    await call.message.edit_text(text, reply_markup=admin_discounts_kb(codes))
    await call.answer()


@router.callback_query(F.data == "admin:add_discount")
async def admin_add_discount_start(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AdminDiscountCode.code)
    await call.message.answer("🎁 کد تخفیف رو وارد کن (مثلاً GIFT20):")
    await call.answer()


@router.message(AdminDiscountCode.code)
async def admin_discount_code_handler(message: types.Message, state: FSMContext):
    await state.update_data(code=message.text.strip().upper())
    await state.set_state(AdminDiscountCode.discount_type)
    await message.answer(
        "نوع تخفیف رو انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 درصدی (%)", callback_data="dtype:percent")],
            [InlineKeyboardButton(text="💰 تومانی (T)", callback_data="dtype:amount")],
        ])
    )


@router.callback_query(F.data.startswith("dtype:"), AdminDiscountCode.discount_type)
async def admin_discount_type(call: types.CallbackQuery, state: FSMContext):
    dtype = call.data.split(":")[1]
    await state.update_data(discount_type=dtype)
    await state.set_state(AdminDiscountCode.discount_value)
    if dtype == "percent":
        await call.message.answer("📊 مقدار تخفیف رو به درصد وارد کن (مثلاً 20 برای 20%):")
    else:
        await call.message.answer("💰 مقدار تخفیف رو به تومان وارد کن:")
    await call.answer()


@router.message(AdminDiscountCode.discount_value)
async def admin_discount_value(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ فقط عدد:")
        return
    await state.update_data(discount_value=int(message.text))
    await state.set_state(AdminDiscountCode.max_uses)
    await message.answer("🔢 حداکثر تعداد استفاده رو وارد کن:\n(0 برای نامحدود)")


@router.message(AdminDiscountCode.max_uses)
async def admin_discount_max_uses(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ فقط عدد:")
        return
    max_uses = int(message.text)
    data = await state.get_data()
    cid = await run_db(create_discount_code, 
        data["code"],
        data["discount_type"],
        data["discount_value"],
        None if max_uses == 0 else max_uses
    )
    await state.clear()
    type_label = "درصد" if data["discount_type"] == "percent" else "تومان"
    await message.answer(
        f"✅ کد تخفیف ساخته شد!\n\n"
        f"🎁 کد: {data['code']}\n"
        f"💸 مقدار: {data['discount_value']} {type_label}\n"
        f"🔢 حداکثر استفاده: {'نامحدود' if max_uses == 0 else max_uses}\n"
        f"🔑 ID: {cid}",
        reply_markup=get_kb(message.from_user.id)
    )


@router.callback_query(F.data.startswith("admin:del_discount:"))
async def admin_del_discount(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    dc_id = int(call.data.split(":")[2])
    await run_db(delete_discount_code, dc_id)
    await call.answer("🗑 کد حذف شد", show_alert=True)
    codes = await run_db(get_all_discount_codes)
    text = "🎁 کدهای تخفیف:\n(برای حذف روی کد کلیک کن)\n\n"
    if not codes:
        text += "هیچ کدی ثبت نشده."
    await call.message.edit_text(text, reply_markup=admin_discounts_kb(codes))


# ================================================================
# EDIT BALANCE
# ================================================================

@router.callback_query(F.data == "admin:edit_balance")
async def admin_edit_balance_start(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AdminEditBalance.user_id)
    await call.message.answer("👤 آی‌دی کاربر رو وارد کن:")
    await call.answer()


@router.message(AdminEditBalance.user_id)
async def admin_edit_balance_uid(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ آی‌دی باید عدد باشه:")
        return
    await state.update_data(target_user_id=int(message.text))
    await state.set_state(AdminEditBalance.amount)
    await message.answer(
        "💰 مبلغ رو وارد کن:\n"
        "• عدد مثبت → اضافه (مثلاً: 50000)\n"
        "• عدد منفی → کسر (مثلاً: -20000)\n"
        "• =عدد → ست مستقیم (مثلاً: =100000)"
    )


@router.message(AdminEditBalance.amount)
async def admin_edit_balance_amount(message: types.Message, state: FSMContext, bot: Bot):
    text = message.text.strip()
    data = await state.get_data()
    uid = data["target_user_id"]
    old_bal = await run_db(get_balance, uid)

    if text.startswith("="):
        val = text[1:]
        if not val.isdigit():
            await message.answer("❌ فرمت اشتباه:")
            return
        new_val = int(val)
        await run_db(set_balance, uid, new_val)
        action = f"ست شد به {new_val:,} تومان"
        user_msg = (f"🔔 موجودی حساب شما توسط ادمین تغییر کرد\n"
                    f"💰 موجودی قبلی: {old_bal:,} تومان\n"
                    f"💰 موجودی جدید: {new_val:,} تومان")
    elif text.lstrip("-").isdigit():
        val = int(text)
        await run_db(add_balance, uid, val)
        if val > 0:
            action = f"+{val:,} تومان اضافه شد"
            user_msg = (f"🔔 موجودی حساب شما توسط ادمین افزایش یافت\n"
                        f"💚 +{val:,} تومان اضافه شد\n"
                        f"💰 موجودی جدید: {await run_db(get_balance, uid):,} تومان")
        else:
            action = f"{val:,} تومان کسر شد"
            user_msg = (f"🔔 موجودی حساب شما توسط ادمین کاهش یافت\n"
                        f"🔴 {val:,} تومان کسر شد\n"
                        f"💰 موجودی جدید: {await run_db(get_balance, uid):,} تومان")
    else:
        await message.answer("❌ فرمت اشتباه:")
        return

    new_bal = await run_db(get_balance, uid)
    await state.clear()
    try:
        await bot.send_message(uid, user_msg)
        notif = "✅ پیام به کاربر ارسال شد"
    except Exception:
        notif = "⚠️ کاربر ربات رو بلاک کرده"
    await message.answer(
        f"✅ موجودی کاربر {uid} {action}\n💰 موجودی جدید: {new_bal:,} تومان\n{notif}",
        reply_markup=get_kb(message.from_user.id)
    )


# ================================================================
# FREE TRIAL MANAGEMENT
# ================================================================

@router.callback_query(F.data == "admin:trial_menu")
async def admin_trial_menu(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cfg = await run_db(get_trial_config)
    await call.message.edit_text("🧪 مدیریت تست رایگان:", reply_markup=admin_trial_menu_kb(cfg))
    await call.answer()


@router.callback_query(F.data == "admin:trial_toggle")
async def admin_trial_toggle(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cfg = await run_db(get_trial_config)
    new_val = not cfg[0]
    await run_db(update_trial_config, is_enabled=new_val)
    await call.answer("✅ فعال شد" if new_val else "❌ غیرفعال شد", show_alert=True)
    cfg = await run_db(get_trial_config)
    await call.message.edit_text("🧪 مدیریت تست رایگان:", reply_markup=admin_trial_menu_kb(cfg))


@router.callback_query(F.data == "admin:trial_toggle_ref")
async def admin_trial_toggle_ref(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cfg = await run_db(get_trial_config)
    new_val = not cfg[3]
    await run_db(update_trial_config, require_referral=new_val)
    await call.answer("✅ نیاز به رفرال فعال شد" if new_val else "❌ نیاز به رفرال حذف شد", show_alert=True)
    cfg = await run_db(get_trial_config)
    await call.message.edit_text("🧪 مدیریت تست رایگان:", reply_markup=admin_trial_menu_kb(cfg))


@router.callback_query(F.data.startswith("admin:trial_set:"))
async def admin_trial_set_field(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    field = call.data.split(":")[2]
    await state.set_state(AdminTrialConfig.entering_value)
    await state.update_data(trial_field=field)
    prompts = {
        "duration_days":    "⏳ مدت جدید تست رو به روز وارد کن:",
        "data_limit_gb":    "📶 حجم جدید تست رو به GB وارد کن (مثلاً 5 یا 0.5):",
        "min_referrals":    "👥 حداقل تعداد رفرال لازم رو وارد کن (0 = بدون محدودیت):",
        "default_max_uses": "🔢 تعداد پیش‌فرض تست برای هر شماره رو وارد کن:",
    }
    await call.message.answer(prompts.get(field, "مقدار جدید رو وارد کن:"))
    await call.answer()


@router.message(AdminTrialConfig.entering_value)
async def admin_trial_save_field(message: types.Message, state: FSMContext):
    data = await state.get_data()
    field = data["trial_field"]
    raw = message.text.strip()

    if field == "data_limit_gb":
        try:
            value = float(raw.replace(",", "."))
        except ValueError:
            await message.answer("❌ عدد معتبر:")
            return
    else:
        if not raw.isdigit():
            await message.answer("❌ فقط عدد صحیح:")
            return
        value = int(raw)

    await run_db(update_trial_config, **{field: value})
    await state.clear()
    await message.answer("✅ تنظیمات تست ذخیره شد.", reply_markup=get_kb(message.from_user.id))


@router.callback_query(F.data == "admin:trial_phones")
async def admin_trial_phones(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    overrides = await run_db(get_all_phone_overrides)
    cfg = await run_db(get_trial_config)
    default_max = cfg[5]
    sep = "─" * 22
    text = f"📱 مدیریت شماره‌ها\n{sep}\n🔢 تعداد پیش‌فرض: {default_max} بار\n{sep}\n"
    if overrides:
        text += "شماره‌های با تعداد اختصاصی:\n"
        for phone, max_uses in overrides:
            text += f"📱 {phone}: {max_uses} بار\n"
    else:
        text += "هیچ override ای ثبت نشده.\n"
    buttons = [
        [InlineKeyboardButton(text="➕ تنظیم شماره اختصاصی",   callback_data="admin:trial_add_phone")],
        [InlineKeyboardButton(text="🗑 حذف override شماره",     callback_data="admin:trial_del_phone")],
        [InlineKeyboardButton(text="🔄 ریست تاریخچه تست شماره", callback_data="admin:trial_clear_uses")],
        [InlineKeyboardButton(text="📋 لیست کامل تست‌ها",      callback_data="admin:trial_uses")],
        [InlineKeyboardButton(text="🔙 برگشت",                  callback_data="admin:trial_menu")],
    ]
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await call.answer()


@router.callback_query(F.data == "admin:trial_add_phone")
async def admin_trial_add_phone_start(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AdminPhoneOverride.phone)
    await call.message.answer("📱 شماره تلفن رو وارد کن (مثلاً 09123456789):")
    await call.answer()


@router.message(AdminPhoneOverride.phone)
async def admin_trial_phone_input(message: types.Message, state: FSMContext):
    phone = normalize_phone(message.text)
    if not phone.startswith("09") or len(phone) != 11:
        await message.answer("❌ شماره نامعتبر:")
        return

    data = await state.get_data()
    mode = data.get("override_mode")

    if mode == "delete":
        await run_db(delete_phone_override, phone)
        await state.clear()
        await message.answer(
            f"✅ Override شماره {phone} حذف شد.",
            reply_markup=get_kb(message.from_user.id)
        )
        return

    if mode == "clear_uses":
        from db import clear_trial_uses
        await run_db(clear_trial_uses, phone)
        await state.clear()
        await message.answer(
            f"✅ تاریخچه تست شماره {phone} ریست شد.\n"
            f"این شماره می‌تونه دوباره تست بگیره.",
            reply_markup=get_kb(message.from_user.id)
        )
        return

    await state.update_data(override_phone=phone)
    await state.set_state(AdminPhoneOverride.max_uses)
    await message.answer(f"🔢 حداکثر تعداد تست برای {phone} رو وارد کن:")


@router.message(AdminPhoneOverride.max_uses)
async def admin_trial_phone_max_uses(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ فقط عدد:")
        return
    data = await state.get_data()
    phone = data["override_phone"]
    max_uses = int(message.text)
    await run_db(set_phone_max_uses, phone, max_uses)
    await state.clear()
    await message.answer(
        f"✅ تنظیم شد!\n📱 {phone}: حداکثر {max_uses} بار تست",
        reply_markup=get_kb(message.from_user.id)
    )


@router.callback_query(F.data == "admin:trial_del_phone")
async def admin_trial_del_phone_start(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AdminPhoneOverride.phone)
    await state.update_data(override_mode="delete")
    await call.message.answer("📱 شماره‌ای که می‌خوای override ش رو حذف کنی وارد کن:")
    await call.answer()


@router.callback_query(F.data == "admin:trial_clear_uses")
async def admin_trial_clear_uses_start(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AdminPhoneOverride.phone)
    await state.update_data(override_mode="clear_uses")
    await call.message.answer(
        "🔄 شماره‌ای که می‌خوای تاریخچه تستش رو ریست کنی وارد کن:\n"
        "(بعد از ریست، اون شماره می‌تونه دوباره تست بگیره)"
    )
    await call.answer()


@router.callback_query(F.data == "admin:trial_uses")
async def admin_trial_uses(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    uses = await run_db(get_all_trial_uses)
    if not uses:
        text = "📋 هنوز هیچ تستی گرفته نشده."
    else:
        text = f"📋 آخرین تست‌های گرفته‌شده ({len(uses)}):\n\n"
        for phone, tid, used_at in uses:
            text += f"📱 {phone} | 👤 {tid} | {used_at.strftime('%m-%d %H:%M')}\n"
    await call.message.edit_text(text, reply_markup=back_kb("admin:trial_phones"))
    await call.answer()


# ================================================================
# REFERRAL MANAGEMENT
# ================================================================

@router.callback_query(F.data == "admin:referral_menu")
async def admin_referral_menu(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    if not await require_pro(call, "رفرال"):
        return
    cfg = await run_db(get_referral_config)
    await call.message.edit_text("🔗 تنظیمات سیستم رفرال:", reply_markup=admin_referral_menu_kb(cfg))
    await call.answer()


@router.callback_query(F.data == "admin:ref_toggle")
async def admin_ref_toggle(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cfg = await run_db(get_referral_config)
    new_val = not cfg[0]
    await run_db(update_referral_config, is_enabled=new_val)
    await call.answer("✅ رفرال فعال شد" if new_val else "❌ رفرال غیرفعال شد", show_alert=True)
    cfg = await run_db(get_referral_config)
    await call.message.edit_text("🔗 تنظیمات سیستم رفرال:", reply_markup=admin_referral_menu_kb(cfg))


@router.callback_query(F.data.startswith("admin:ref_set:"))
async def admin_ref_set_field(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    field = call.data.split(":")[2]
    await state.set_state(AdminReferralConfig.entering_value)
    await state.update_data(ref_field=field)
    prompts = {
        "reward_on_join":          "🎁 پاداش ثبت‌نام رو به تومان وارد کن (0 = بدون پاداش):",
        "first_purchase_reward":   "🥇 پاداش اولین خرید زیرمجموعه رو به تومان وارد کن (0 = بدون پاداش):",
        "reward_on_purchase":      "🛍 پاداش ثابت خریدهای بعدی رو به تومان وارد کن (0 = بدون پاداش):",
        "reward_purchase_percent": "📊 درصد پاداش خریدهای بعدی رو وارد کن (0 = بدون پاداش، مثلاً 5 برای 5%):",
    }
    await call.message.answer(prompts.get(field, "مقدار جدید رو وارد کن:"))
    await call.answer()


@router.message(AdminReferralConfig.entering_value)
async def admin_ref_save_field(message: types.Message, state: FSMContext):
    data = await state.get_data()
    field = data["ref_field"]
    raw = message.text.strip()

    if field == "reward_purchase_percent":
        try:
            value = float(raw.replace(",", "."))
            if value < 0 or value > 100:
                raise ValueError
        except ValueError:
            await message.answer("❌ عدد بین 0 تا 100 وارد کن:")
            return
    else:
        if not raw.isdigit():
            await message.answer("❌ فقط عدد صحیح:")
            return
        value = int(raw)

    await run_db(update_referral_config, **{field: value})
    await state.clear()
    await message.answer("✅ تنظیمات رفرال ذخیره شد.", reply_markup=get_kb(message.from_user.id))


@router.callback_query(F.data == "admin:ref_history")
async def admin_ref_history(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    def _get_ref_rewards():
        from db import connect as _conn
        conn = _conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT referrer_id, referred_id, reward_type, amount, created_at
            FROM referral_rewards ORDER BY created_at DESC LIMIT 50
        """)
        rows = cur.fetchall()
        conn.close()
        return rows

    rows = await run_db(_get_ref_rewards)

    if not rows:
        text = "📋 هنوز هیچ پاداش رفرالی ثبت نشده."
    else:
        text = f"📋 تاریخچه پاداش‌های رفرال ({len(rows)}):\n\n"
        for referrer, referred, rtype, amount, created_at in rows:
            type_label = "ثبت‌نام" if rtype == "join" else "خرید"
            text += f"👤{referrer}→{referred} | {type_label} | +{amount:,}T | {created_at.strftime('%m-%d %H:%M')}\n"
    await call.message.edit_text(text, reply_markup=back_kb("admin:referral_menu"))
    await call.answer()


# ================================================================
# CHANNEL MANAGEMENT
# ================================================================

def channels_kb(channels):
    buttons = []
    for ch in channels:
        ch_id, channel_id, username, title, invite_link, is_active = ch
        st = "✅" if is_active else "❌"
        buttons.append([
            InlineKeyboardButton(text=f"{st} {title}", callback_data=f"admin:ch_toggle:{ch_id}"),
            InlineKeyboardButton(text="🗑", callback_data=f"admin:ch_del:{ch_id}"),
        ])
    buttons.append([InlineKeyboardButton(text="➕ افزودن کانال", callback_data="admin:ch_add")])
    buttons.append([InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "admin:channels")
async def admin_channels(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    if not await require_pro(call, "جوین اجباری"):
        return
    channels = await run_db(get_all_channels)
    text = "📢 کانال‌های اجباری:\n✅=فعال | ❌=غیرفعال\n\n"
    if not channels:
        text += "هیچ کانالی ثبت نشده."
    await call.message.edit_text(text, reply_markup=channels_kb(channels))
    await call.answer()


@router.callback_query(F.data.startswith("admin:ch_toggle:"))
async def admin_ch_toggle(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    ch_id = int(call.data.split(":")[2])
    new_status = await run_db(toggle_channel, ch_id)
    await call.answer("✅ فعال شد" if new_status else "❌ غیرفعال شد", show_alert=True)
    channels = await run_db(get_all_channels)
    await call.message.edit_text(
        "📢 کانال‌های اجباری:\n✅=فعال | ❌=غیرفعال\n\n",
        reply_markup=channels_kb(channels)
    )


@router.callback_query(F.data.startswith("admin:ch_del:"))
async def admin_ch_del(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    ch_id = int(call.data.split(":")[2])
    await run_db(delete_channel, ch_id)
    await call.answer("🗑 کانال حذف شد", show_alert=True)
    channels = await run_db(get_all_channels)
    text = "📢 کانال‌های اجباری:\n✅=فعال | ❌=غیرفعال\n\n"
    if not channels:
        text += "هیچ کانالی ثبت نشده."
    await call.message.edit_text(text, reply_markup=channels_kb(channels))


@router.callback_query(F.data == "admin:ch_add")
async def admin_ch_add_start(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AdminAddChannel.channel_id)
    await call.message.answer(
        "📢 آی‌دی یا یوزرنیم کانال رو وارد کن:\n\n"
        "مثال: @mychannel یا -1001234567890\n\n"
        "⚠️ ربات باید ادمین کانال باشه!"
    )
    await call.answer()


@router.message(AdminAddChannel.channel_id)
async def admin_ch_id_input(message: types.Message, state: FSMContext):
    raw = message.text.strip()
    await state.update_data(channel_id=raw)

    # سعی می‌کنیم اطلاعات کانال رو از تلگرام بگیریم
    try:
        chat = await message.bot.get_chat(raw)
        await state.update_data(
            channel_username=chat.username or "",
            channel_title=chat.title or raw
        )
        await state.set_state(AdminAddChannel.invite_link)
        await message.answer(
            f"✅ کانال پیدا شد: {chat.title}\n\n"
            f"لینک دعوت رو وارد کن (اختیاری، برای کانال‌های پرایوت):\n"
            f"یا /skip اگه کانال پابلیکه:"
        )
    except Exception:
        await message.answer(
            "⚠️ نتونستم اطلاعات کانال رو بگیرم (ربات ادمین نیست؟)\n\n"
            "عنوان کانال رو دستی وارد کن:"
        )
        await state.set_state(AdminAddChannel.title)


@router.message(AdminAddChannel.title)
async def admin_ch_title_input(message: types.Message, state: FSMContext):
    await state.update_data(channel_title=message.text.strip(), channel_username="")
    await state.set_state(AdminAddChannel.invite_link)
    await message.answer(
        "لینک دعوت رو وارد کن:\n"
        "یا /skip اگه نداری:"
    )


@router.message(AdminAddChannel.invite_link)
async def admin_ch_invite_input(message: types.Message, state: FSMContext):
    invite = None if message.text.strip() == "/skip" else message.text.strip()
    data = await state.get_data()
    cid = await run_db(add_channel, 
        data["channel_id"],
        data.get("channel_username", ""),
        data.get("channel_title", data["channel_id"]),
        invite
    )
    await state.clear()
    await message.answer(
        f"✅ کانال اضافه شد!\n"
        f"📢 {data.get('channel_title', data['channel_id'])}\n"
        f"🔑 ID: {cid}",
        reply_markup=get_kb(message.from_user.id)
    )


# ================================================================
# PANEL CONFIG MANAGEMENT
# ================================================================

from states import AdminPanelConfig
from db import get_panel_config, update_panel_config
from panel import test_panel_connection, get_inbound_list


def panel_config_kb(cfg):
    if not cfg:
        url, auth_type, username, password, api_key, inbound_id, panel_path, sub_port, sub_path = (None,)*9
    elif len(cfg) >= 9:
        url, auth_type, username, password, api_key, inbound_id, panel_path, sub_port, sub_path = cfg
    else:
        url, auth_type, username, password, api_key, inbound_id, panel_path = cfg[:7]
        sub_port, sub_path = None, "sub"
    auth_label = "👤 یوزر/پس" if auth_type == "userpass" else "🔑 API Key"
    connected = "✅" if url else "❌"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{connected} آدرس پنل: {url or 'تنظیم نشده'}", callback_data="admin:panel_set:panel_url")],
        [InlineKeyboardButton(text=f"🔐 روش اتصال: {auth_label}", callback_data="admin:panel_toggle_auth")],
        [InlineKeyboardButton(text=f"👤 یوزرنیم: {username or '—'}", callback_data="admin:panel_set:username")],
        [InlineKeyboardButton(text=f"🔒 پسورد: {'✅ ست شده' if password else '—'}", callback_data="admin:panel_set:password")],
        [InlineKeyboardButton(text=f"🔑 API Key: {'✅ ست شده' if api_key else '—'}", callback_data="admin:panel_set:api_key")],
        [InlineKeyboardButton(text=f"📡 Inbound ID: {inbound_id or '—'}", callback_data="admin:panel_set:inbound_id")],
        [InlineKeyboardButton(text=f"📂 Panel Path: {panel_path or '/'}", callback_data="admin:panel_set:panel_path")],
        [InlineKeyboardButton(text=f"🔌 پورت لینک Sub: {sub_port or 'همان پنل'}", callback_data="admin:panel_set:sub_port")],
        [InlineKeyboardButton(text=f"📎 Sub Path: /{sub_path or 'sub'}", callback_data="admin:panel_set:sub_path")],
        [InlineKeyboardButton(text="📋 لیست Inbound ها", callback_data="admin:panel_inbounds")],
        [InlineKeyboardButton(text="🔌 تست اتصال", callback_data="admin:panel_test")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:back")],
    ])


@router.callback_query(F.data == "admin:panel_config")
async def admin_panel_config(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cfg = await run_db(get_panel_config)
    await call.message.edit_text("⚙️ تنظیمات پنل VPN:", reply_markup=panel_config_kb(cfg))
    await call.answer()


@router.callback_query(F.data == "admin:panel_toggle_auth")
async def admin_panel_toggle_auth(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cfg = await run_db(get_panel_config)
    new_auth = "apikey" if cfg[1] == "userpass" else "userpass"
    if new_auth == "apikey" and not await require_pro(call, "اتصال با API Key"):
        return
    await run_db(update_panel_config, auth_type=new_auth)
    from panel import invalidate_panel_cache
    invalidate_panel_cache()
    await call.answer("🔑 API Key" if new_auth == "apikey" else "👤 یوزر/پس", show_alert=True)
    cfg = await run_db(get_panel_config)
    await call.message.edit_text("⚙️ تنظیمات پنل VPN:", reply_markup=panel_config_kb(cfg))


@router.callback_query(F.data.startswith("admin:panel_set:"))
async def admin_panel_set_field(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    field = call.data.split(":")[2]
    await state.set_state(AdminPanelConfig.entering_value)
    await state.update_data(panel_field=field)
    prompts = {
        "panel_url":   "🌐 آدرس پنل رو وارد کن:\nمثال: https://1.2.3.4:2053",
        "username":    "👤 یوزرنیم پنل رو وارد کن:",
        "password":    "🔒 پسورد پنل رو وارد کن:",
        "api_key":     "🔑 API Key پنل رو وارد کن:",
        "inbound_id":  "📡 شماره Inbound ID رو وارد کن (عدد):",
        "panel_path":  "📂 Panel Path رو وارد کن (پیش‌فرض خالی):\nمثال: /panel یا /skip برای خالی:",
        "sub_port":    "🔌 پورت لینک Sub رو وارد کن:\nمثال: 2096 (یا /skip اگه همون پورت پنله):",
        "sub_path":    "📎 Sub Path رو وارد کن (پیش‌فرض: sub):\nمثال: sub یا subscription:",
    }
    await call.message.answer(prompts.get(field, "مقدار جدید رو وارد کن:"))
    await call.answer()


@router.message(AdminPanelConfig.entering_value)
async def admin_panel_save_field(message: types.Message, state: FSMContext):
    data = await state.get_data()
    field = data["panel_field"]
    raw = message.text.strip()

    if field == "inbound_id":
        if not raw.isdigit():
            await message.answer("❌ فقط عدد:")
            return
        value = int(raw)
    elif field == "panel_path":
        value = "" if raw == "/skip" else raw
    elif field == "sub_port":
        if raw == "/skip":
            value = None
        elif raw.isdigit():
            value = int(raw)
        else:
            await message.answer("❌ فقط عدد یا /skip:")
            return
    elif field == "sub_path":
        value = "sub" if raw == "/skip" else raw.strip("/")
    elif field == "panel_url":
        # اگه URL شامل path بود (مثلاً https://domain:2083/abcXYZ) خودکار جدا کن
        from urllib.parse import urlparse
        parsed = urlparse(raw.rstrip("/"))
        # base: scheme + host + port
        base = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path.rstrip("/")
        value = base
        # اگه path داشت، panel_path رو هم آپدیت کن
        if path:
            await run_db(update_panel_config, panel_path=path)
            await message.answer(
                f"✅ آدرس ذخیره شد.\n"
                f"🌐 Base URL: {base}\n"
                f"📂 Panel Path: {path}\n"
                f"(panel_path هم خودکار تنظیم شد)"
            )
            from panel import invalidate_panel_cache
            invalidate_panel_cache()
            await state.clear()
            return
    else:
        value = raw

    await run_db(update_panel_config, **{field: value})
    from panel import invalidate_panel_cache
    invalidate_panel_cache()
    await state.clear()
    await message.answer("✅ ذخیره شد.", reply_markup=get_kb(message.from_user.id))


@router.callback_query(F.data == "admin:panel_test")
async def admin_panel_test(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("🔌 در حال تست اتصال...")
    ok, msg = await test_panel_connection()
    cfg = await run_db(get_panel_config)
    await call.message.edit_text(
        f"{'✅' if ok else '❌'} {msg}",
        reply_markup=panel_config_kb(cfg)
    )
    await call.answer()


@router.callback_query(F.data == "admin:panel_inbounds")
async def admin_panel_inbounds(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("📋 در حال دریافت لیست...")
    inbounds = await get_inbound_list()
    if not inbounds:
        await call.message.edit_text(
            "❌ نتونستم inbound ها رو بگیرم.\nاتصال پنل رو چک کن.",
            reply_markup=back_kb("admin:panel_config")
        )
        await call.answer()
        return

    text = "📋 لیست Inbound ها:\n\n"
    for ib in inbounds:
        text += f"🔹 ID: {ib.get('id')} | {ib.get('remark','—')} | {ib.get('protocol','—')} | پورت: {ib.get('port','—')}\n"
    text += "\nاز این IDها برای تنظیم Inbound ID استفاده کن."
    await call.message.edit_text(text, reply_markup=back_kb("admin:panel_config"))
    await call.answer()


# ================================================================
# PARTNER MANAGEMENT
# ================================================================

from db import (
    get_all_partners, get_partner, add_partner, remove_partner,
    get_all_categories, set_category_visibility
)
from states import AdminAddPartnerManual


def partners_kb(partners):
    buttons = []
    for p in partners:
        pid, user_id, phone, desc, status, added_at = p
        st = "✅" if status == "active" else "❌"
        buttons.append([
            InlineKeyboardButton(text=f"{st} {user_id} | {phone or '—'}", callback_data=f"admin:partner_detail:{user_id}"),
        ])
    buttons.append([InlineKeyboardButton(text="➕ افزودن دستی", callback_data="admin:partner_add")])
    buttons.append([InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def partner_detail_kb(user_id, is_active):
    toggle_text = "❌ غیرفعال کردن" if is_active else "✅ فعال کردن"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data=f"admin:partner_toggle:{user_id}")],
        [InlineKeyboardButton(text="🛍 آمار خرید", callback_data=f"admin:partner_purchases:{user_id}")],
        [InlineKeyboardButton(text="🗑 حذف همکار", callback_data=f"admin:partner_delete:{user_id}")],
        [InlineKeyboardButton(text="🔙 برگشت به لیست", callback_data="admin:partners")],
    ])


@router.callback_query(F.data == "admin:partners")
async def admin_partners(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    if not await require_pro(call, "همکاران"):
        return
    partners = await run_db(get_all_partners)
    active = sum(1 for p in partners if p[4] == "active")
    text = f"🤝 همکاران ({active} فعال از {len(partners)}):\n✅=فعال | ❌=غیرفعال\n\n"
    if not partners:
        text += "هیچ همکاری ثبت نشده."
    await call.message.edit_text(text, reply_markup=partners_kb(partners))
    await call.answer()


@router.callback_query(F.data.startswith("admin:partner_detail:"))
async def admin_partner_detail(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    user_id = int(call.data.split(":")[2])
    p = await run_db(get_partner, user_id)
    if not p:
        await call.answer("❌ یافت نشد", show_alert=True)
        return
    pid, uid, phone, desc, status, added_at = p
    bal = await run_db(get_balance, uid)
    purchases = await run_db(get_user_purchases, uid)
    sep = "─" * 22
    text = (
        f"🤝 جزئیات همکار\n{sep}\n"
        f"🆔 User ID: {uid}\n"
        f"📱 شماره: {phone or '—'}\n"
        f"📝 توضیحات: {desc or '—'}\n"
        f"🔘 وضعیت: {'✅ فعال' if status == 'active' else '❌ غیرفعال'}\n"
        f"💰 موجودی: {bal:,} تومان\n"
        f"🛍 تعداد خرید: {len(purchases)}\n"
        f"📅 تاریخ عضویت: {added_at.strftime('%Y-%m-%d')}\n"
    )
    await call.message.edit_text(text, reply_markup=partner_detail_kb(uid, status == "active"))
    await call.answer()


@router.callback_query(F.data.startswith("admin:partner_purchases:"))
async def admin_partner_purchases(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    user_id = int(call.data.split(":")[2])
    purchases = await run_db(get_user_purchases, user_id)
    if not purchases:
        await call.answer("هنوز خریدی نداشته", show_alert=True)
        return
    sep = "─" * 22
    text = f"🛍 خریدهای همکار {user_id}\n{sep}\n"
    total = 0
    for p in purchases:
        sname, amt, pat = p
        text += f"📦 {sname} | {amt:,}T | {pat.strftime('%Y-%m-%d')}\n"
        total += amt
    text += f"{sep}\n💰 مجموع: {total:,} تومان"
    await call.message.edit_text(text, reply_markup=back_kb(f"admin:partner_detail:{user_id}"))
    await call.answer()


@router.callback_query(F.data.startswith("admin:partner_delete:"))
async def admin_partner_delete(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    user_id = int(call.data.split(":")[2])

    def _delete_partner(uid):
        from db import connect as _conn
        conn = _conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM partners WHERE user_id=%s", (uid,))
        cur.execute("DELETE FROM partner_requests WHERE user_id=%s", (uid,))
        conn.commit()
        conn.close()

    await run_db(_delete_partner, user_id)
    await call.answer("🗑 همکار حذف شد", show_alert=True)
    partners = await run_db(get_all_partners)
    active = sum(1 for p in partners if p[4] == "active")
    text = f"🤝 همکاران ({active} فعال از {len(partners)}):\n\n"
    if not partners:
        text += "هیچ همکاری ثبت نشده."
    await call.message.edit_text(text, reply_markup=partners_kb(partners))


@router.callback_query(F.data.startswith("admin:partner_toggle:"))
async def admin_partner_toggle(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    user_id = int(call.data.split(":")[2])
    p = await run_db(get_partner, user_id)
    if not p:
        await call.answer("❌ یافت نشد", show_alert=True)
        return
    if p[4] == "active":
        await run_db(remove_partner, user_id)
        await call.answer("❌ غیرفعال شد", show_alert=True)
    else:
        await run_db(add_partner, user_id, p[2], p[3])
        await call.answer("✅ فعال شد", show_alert=True)
    p = await run_db(get_partner, user_id)
    pid, uid, phone, desc, status, added_at = p
    sep = "─" * 22
    text = (
        f"🤝 جزئیات همکار\n{sep}\n"
        f"🆔 User ID: {uid}\n"
        f"📱 شماره: {phone or '—'}\n"
        f"📝 توضیحات: {desc or '—'}\n"
        f"🔘 وضعیت: {'✅ فعال' if status == 'active' else '❌ غیرفعال'}\n"
    )
    await call.message.edit_text(text, reply_markup=partner_detail_kb(uid, status == "active"))


@router.callback_query(F.data == "admin:partner_add")
async def admin_partner_add_start(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AdminAddPartnerManual.waiting_user_id)
    await call.message.answer("👤 آی‌دی عددی کاربر رو وارد کن:")
    await call.answer()


@router.message(AdminAddPartnerManual.waiting_user_id)
async def admin_partner_add_uid(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ فقط عدد:")
        return
    await state.update_data(target_uid=int(message.text))
    await state.set_state(AdminAddPartnerManual.waiting_phone)
    await message.answer("📱 شماره موبایل همکار (یا /skip):")


@router.message(AdminAddPartnerManual.waiting_phone)
async def admin_partner_add_phone(message: types.Message, state: FSMContext, bot: Bot):
    from utils import normalize_phone
    phone = None if message.text == "/skip" else normalize_phone(message.text)
    data = await state.get_data()
    uid = data["target_uid"]
    await run_db(add_partner, uid, phone)
    await state.clear()
    try:
        await bot.send_message(
            uid,
            "🎉 شما به عنوان همکار اضافه شدید!\n"
            "✅ حالا به دسته‌بندی‌های ویژه همکاران دسترسی داری."
        )
    except Exception:
        pass
    await message.answer(
        f"✅ کاربر {uid} به عنوان همکار اضافه شد.",
        reply_markup=get_kb(message.from_user.id)
    )


# ================================================================
# CATEGORY VISIBILITY
# ================================================================

def _vis_label(v):
    if v == "partners":
        return "🤝 همکاران"
    if v == "users":
        return "👤 کاربران عادی"
    if v == "custom":
        return "🎯 سفارشی (لیست)"
    return "👥 همه"

def _vis_next(v):
    # چرخش: all → partners → users → custom → all
    if v in ("all", None):
        return "partners"
    if v == "partners":
        return "users"
    if v == "users":
        return "custom"
    return "all"


def category_visibility_kb(categories):
    buttons = []
    for c in categories:
        cid, name, emoji, is_active, sort_order, visibility = c
        buttons.append([
            InlineKeyboardButton(
                text=f"{emoji} {name} | {_vis_label(visibility)}",
                callback_data=f"admin:cat_vis:{cid}"
            )
        ])
        if visibility == "custom":
            buttons.append([
                InlineKeyboardButton(
                    text=f"   └ 👥 مدیریت لیست دسترسی «{name}»",
                    callback_data=f"admin:cat_custom_users:{cid}"
                )
            ])
    buttons.append([InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _get_cats_for_vis():
    """sync helper — فقط از run_db صدا زده بشه"""
    from db import connect as _conn
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, emoji, is_active, sort_order, visibility FROM categories ORDER BY sort_order, id")
    cats = cur.fetchall()
    conn.close()
    return cats


@router.callback_query(F.data == "admin:cat_visibility")
async def admin_cat_visibility(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cats = await run_db(_get_cats_for_vis)
    await call.message.edit_text(
        "👁 دسترسی دسته‌بندی‌ها:\n"
        "👥 همه | 🤝 همکاران | 👤 کاربران عادی | 🎯 سفارشی\n"
        "روی نام دسته کلیک کن تا بچرخونیش:",
        reply_markup=category_visibility_kb(cats)
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin:cat_vis:"))
async def admin_toggle_cat_visibility(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cat_id = int(call.data.split(":")[2])

    def _get_visibility(cid):
        from db import connect as _conn
        conn = _conn()
        cur = conn.cursor()
        cur.execute("SELECT visibility FROM categories WHERE id=%s", (cid,))
        r = cur.fetchone()
        conn.close()
        return r[0] if r else "all"

    current = await run_db(_get_visibility, cat_id)
    new_vis = _vis_next(current)
    from db import set_category_visibility
    await run_db(set_category_visibility, cat_id, new_vis)

    msg = _vis_label(new_vis)
    if new_vis == "custom":
        msg += "\nحالا از زیرمنوی «مدیریت لیست دسترسی» کاربرها رو اضافه کن."
    await call.answer(msg, show_alert=True)

    cats = await run_db(_get_cats_for_vis)
    await call.message.edit_text(
        "👁 دسترسی دسته‌بندی‌ها:\n"
        "👥 همه | 🤝 همکاران | 👤 کاربران عادی | 🎯 سفارشی\n"
        "روی نام دسته کلیک کن تا بچرخونیش:",
        reply_markup=category_visibility_kb(cats)
    )


# ================================================================
# مدیریت لیست دسترسی سفارشی (visibility = custom)
# ================================================================

from db import (
    add_category_custom_user, remove_category_custom_user,
    get_category_custom_users, find_user_id_by_phone,
)
from states import AdminCustomAccessAdd, AdminCustomAccessRemove


def custom_access_kb(cat_id, users):
    buttons = []
    for uid, phone in users:
        label = f"🆔 {uid}"
        if phone:
            label += f" | 📱 {phone}"
        buttons.append([
            InlineKeyboardButton(text=label, callback_data=f"admin:cat_custom_del:{cat_id}:{uid}")
        ])
    buttons.append([InlineKeyboardButton(text="➕ افزودن کاربر", callback_data=f"admin:cat_custom_add:{cat_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:cat_visibility")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data.startswith("admin:cat_custom_users:"))
async def admin_cat_custom_users(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cat_id = int(call.data.split(":")[2])
    users = await run_db(get_category_custom_users, cat_id)
    text = f"👥 لیست دسترسی سفارشی (دسته #{cat_id}):\n\n"
    if not users:
        text += "هیچ کاربری اضافه نشده.\nروی «افزودن کاربر» بزن (می‌تونی آیدی عددی یا شماره وارد کنی)."
    await call.message.edit_text(text, reply_markup=custom_access_kb(cat_id, users))
    await call.answer()


@router.callback_query(F.data.startswith("admin:cat_custom_add:"))
async def admin_cat_custom_add_start(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    cat_id = int(call.data.split(":")[2])
    await state.set_state(AdminCustomAccessAdd.waiting_input)
    await state.update_data(cat_id=cat_id)
    await call.message.answer(
        "👤 آیدی عددی یا شماره موبایل کاربر(ها) رو وارد کن:\n\n"
        "می‌تونی چند مورد رو هر خط یکی بفرستی.\n"
        "مثال:\n"
        "933988915\n"
        "09123456789\n\n"
        "⚠️ نکته: اگه شماره وارد کنی، کاربر باید قبلاً یه بار با ربات تعامل داشته و شماره‌اش ثبت شده باشه (مثلاً از تست رایگان)."
    )
    await call.answer()


@router.message(AdminCustomAccessAdd.waiting_input)
async def admin_cat_custom_add_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cat_id = data["cat_id"]
    lines = [l.strip() for l in message.text.strip().splitlines() if l.strip()]

    added = []
    not_found = []

    for line in lines:
        if line.isdigit() and len(line) >= 6 and not line.startswith("09"):
            # آیدی عددی تلگرام
            uid = int(line)
            await run_db(add_category_custom_user, cat_id, uid)
            added.append(str(uid))
        elif line.startswith("09") and len(line) == 11:
            # شماره موبایل — پیدا کردن آیدی
            uid = await run_db(find_user_id_by_phone, line)
            if uid:
                await run_db(add_category_custom_user, cat_id, uid)
                added.append(f"{line} → {uid}")
            else:
                not_found.append(line)
        else:
            not_found.append(line)

    await state.clear()

    text = ""
    if added:
        text += "✅ اضافه شدن:\n" + "\n".join(added) + "\n\n"
    if not_found:
        text += "❌ پیدا نشدن یا فرمت اشتباه:\n" + "\n".join(not_found)

    await message.answer(text or "هیچی پردازش نشد.", reply_markup=get_kb(message.from_user.id))


@router.callback_query(F.data.startswith("admin:cat_custom_del:"))
async def admin_cat_custom_del(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    parts = call.data.split(":")
    cat_id = int(parts[2])
    user_id = int(parts[3])
    await run_db(remove_category_custom_user, cat_id, user_id)
    await call.answer("🗑 حذف شد", show_alert=True)
    users = await run_db(get_category_custom_users, cat_id)
    text = f"👥 لیست دسترسی سفارشی (دسته #{cat_id}):\n\n"
    if not users:
        text += "هیچ کاربری اضافه نشده."
    await call.message.edit_text(text, reply_markup=custom_access_kb(cat_id, users))


# ================================================================
# CUSTOM PLAN MANAGEMENT (پلن دلخواه)
# ================================================================

from db import (
    add_category_custom_flag, get_custom_groups, get_custom_group,
    add_custom_group, update_custom_group, toggle_custom_group, delete_custom_group,
)
from states import AdminCustomCategory, AdminAddCustomGroup, AdminEditCustomGroup


@router.callback_query(F.data == "admin:custom_plans")
async def admin_custom_plans_menu(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    def _get_custom_cats():
        from db import connect as _conn
        conn = _conn()
        cur = conn.cursor()
        cur.execute("SELECT id, name, emoji, is_active FROM categories WHERE is_custom=TRUE ORDER BY sort_order, id")
        rows = cur.fetchall()
        conn.close()
        return rows

    cats = await run_db(_get_custom_cats)
    buttons = []
    for c in cats:
        cid, name, emoji, is_active = c
        st = "✅" if is_active else "❌"
        buttons.append([InlineKeyboardButton(text=f"{st} {emoji} {name}", callback_data=f"admin:custom_cat_detail:{cid}")])
    buttons.append([InlineKeyboardButton(text="➕ افزودن دسته‌بندی پلن دلخواه", callback_data="admin:custom_cat_add")])
    buttons.append([InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:back")])

    text = "🎛 مدیریت پلن‌های دلخواه:\n\n"
    if not cats:
        text += "هیچ دسته‌بندی پلن دلخواهی نساختی."
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await call.answer()


@router.callback_query(F.data == "admin:custom_cat_add")
async def admin_custom_cat_add_start(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    if not await check_free_category_limit(call):
        return
    await state.set_state(AdminCustomCategory.name)
    await call.message.answer(
        "🎛 نام دسته‌بندی پلن دلخواه رو وارد کن:\n"
        "(مثلاً: پلن دلخواه)"
    )
    await call.answer()


@router.message(AdminCustomCategory.name)
async def admin_custom_cat_add_save(message: types.Message, state: FSMContext):
    name = message.text.strip()
    cid = await run_db(add_category, name, "🎛", True)
    await state.clear()
    await message.answer(
        f"✅ دسته‌بندی پلن دلخواه ساخته شد!\n🎛 {name}\n🔑 ID: {cid}\n\n"
        f"حالا باید زیرگروه‌هاش رو اضافه کنی.",
        reply_markup=get_kb(message.from_user.id)
    )


def custom_cat_detail_kb(cat_id, groups):
    buttons = []
    for g in groups:
        gid, name, emoji, ppg, ppd, min_gb, max_gb, min_days, max_days, ibids, is_active = g
        st = "✅" if is_active else "❌"
        buttons.append([InlineKeyboardButton(text=f"{st} {emoji} {name}", callback_data=f"admin:custom_grp_detail:{gid}")])
    buttons.append([InlineKeyboardButton(text="➕ افزودن زیرگروه", callback_data=f"admin:custom_grp_add:{cat_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:custom_plans")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data.startswith("admin:custom_cat_detail:"))
async def admin_custom_cat_detail(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cat_id = int(call.data.split(":")[2])
    cat = await run_db(get_category, cat_id)
    if not cat:
        await call.answer("❌ پیدا نشد", show_alert=True)
        return
    groups = await run_db(get_custom_groups, cat_id, False)
    text = f"🎛 {cat[1]}\n\nزیرگروه‌ها:\n"
    if not groups:
        text += "هیچ زیرگروهی ساخته نشده."
    await call.message.edit_text(text, reply_markup=custom_cat_detail_kb(cat_id, groups))
    await call.answer()


@router.callback_query(F.data.startswith("admin:custom_grp_add:"))
async def admin_custom_grp_add_start(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    cat_id = int(call.data.split(":")[2])
    await state.set_state(AdminAddCustomGroup.name)
    await state.update_data(cat_id=cat_id)
    await call.message.answer("📝 نام زیرگروه رو وارد کن:\n(مثلاً: 🇩🇪 اروپا)")
    await call.answer()


@router.message(AdminAddCustomGroup.name)
async def admin_custom_grp_add_name(message: types.Message, state: FSMContext):
    await state.update_data(grp_name=message.text.strip())
    await state.set_state(AdminAddCustomGroup.emoji)
    await message.answer("😀 ایموجی رو وارد کن (یا /skip برای پیش‌فرض 🌍):")


@router.message(AdminAddCustomGroup.emoji)
async def admin_custom_grp_add_emoji(message: types.Message, state: FSMContext):
    emoji = "🌍" if message.text.strip() == "/skip" else message.text.strip()
    data = await state.get_data()
    gid = await run_db(add_custom_group, data["cat_id"], data["grp_name"], emoji)
    await state.clear()
    await message.answer(
        f"✅ زیرگروه ساخته شد!\n{emoji} {data['grp_name']}\n🔑 ID: {gid}\n\n"
        f"⚠️ یادت نره قیمت‌ها، حداقل/حداکثر و inbound ها رو از جزئیات زیرگروه تنظیم کنی.",
        reply_markup=get_kb(message.from_user.id)
    )


def custom_grp_detail_kb(group_id, cat_id, is_active):
    toggle_text = "❌ غیرفعال کردن" if is_active else "✅ فعال کردن"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 نام/ایموجی", callback_data=f"admin:custom_grp_edit:{group_id}:name")],
        [InlineKeyboardButton(text="💰 قیمت هر گیگ", callback_data=f"admin:custom_grp_edit:{group_id}:price_per_gb")],
        [InlineKeyboardButton(text="💰 قیمت هر روز", callback_data=f"admin:custom_grp_edit:{group_id}:price_per_day")],
        [InlineKeyboardButton(text="📶 حداقل/حداکثر گیگ", callback_data=f"admin:custom_grp_edit:{group_id}:gb_range")],
        [InlineKeyboardButton(text="⏳ حداقل/حداکثر روز", callback_data=f"admin:custom_grp_edit:{group_id}:days_range")],
        [InlineKeyboardButton(text="📡 Inbound IDs", callback_data=f"admin:custom_grp_edit:{group_id}:inbound_ids")],
        [InlineKeyboardButton(text=toggle_text, callback_data=f"admin:custom_grp_toggle:{group_id}")],
        [InlineKeyboardButton(text="🗑 حذف زیرگروه", callback_data=f"admin:custom_grp_del:{group_id}")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data=f"admin:custom_cat_detail:{cat_id}")],
    ])


def _format_group_detail(g):
    gid, cat_id, name, emoji, ppg, ppd, min_gb, max_gb, min_days, max_days, ibids, is_active = g
    sep = "─" * 22
    return (
        f"{emoji} {name}\n{sep}\n"
        f"💰 قیمت هر گیگ: {ppg:,} تومان\n"
        f"💰 قیمت هر روز: {ppd:,} تومان\n"
        f"📶 محدوده حجم: {min_gb:g} تا {max_gb:g} گیگ\n"
        f"⏳ محدوده روز: {min_days} تا {max_days} روز\n"
        f"📡 Inbound IDs: {ibids or 'همه inbound های فعال'}\n"
        f"🔘 وضعیت: {'✅ فعال' if is_active else '❌ غیرفعال'}\n"
    )


@router.callback_query(F.data.startswith("admin:custom_grp_detail:"))
async def admin_custom_grp_detail(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    group_id = int(call.data.split(":")[2])
    g = await run_db(get_custom_group, group_id)
    if not g:
        await call.answer("❌ پیدا نشد", show_alert=True)
        return
    cat_id = g[1]
    await call.message.edit_text(
        _format_group_detail(g),
        reply_markup=custom_grp_detail_kb(group_id, cat_id, g[11])
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin:custom_grp_toggle:"))
async def admin_custom_grp_toggle(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    group_id = int(call.data.split(":")[2])
    new_status = await run_db(toggle_custom_group, group_id)
    await call.answer("✅ فعال شد" if new_status else "❌ غیرفعال شد", show_alert=True)
    g = await run_db(get_custom_group, group_id)
    if g:
        await call.message.edit_text(
            _format_group_detail(g),
            reply_markup=custom_grp_detail_kb(group_id, g[1], g[11])
        )


@router.callback_query(F.data.startswith("admin:custom_grp_del:"))
async def admin_custom_grp_del(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    group_id = int(call.data.split(":")[2])
    g = await run_db(get_custom_group, group_id)
    cat_id = g[1] if g else None
    await run_db(delete_custom_group, group_id)
    await call.answer("🗑 زیرگروه حذف شد", show_alert=True)
    if cat_id:
        groups = await run_db(get_custom_groups, cat_id, False)
        cat = await run_db(get_category, cat_id)
        text = f"🎛 {cat[1] if cat else ''}\n\nزیرگروه‌ها:\n"
        if not groups:
            text += "هیچ زیرگروهی ساخته نشده."
        await call.message.edit_text(text, reply_markup=custom_cat_detail_kb(cat_id, groups))


@router.callback_query(F.data.startswith("admin:custom_grp_edit:"))
async def admin_custom_grp_edit_start(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    parts = call.data.split(":")
    group_id = int(parts[2])
    field = parts[3]
    await state.set_state(AdminEditCustomGroup.entering_value)
    await state.update_data(group_id=group_id, field=field)

    prompts = {
        "name":          "📝 نام جدید رو وارد کن:",
        "price_per_gb":  "💰 قیمت هر گیگ رو به تومان وارد کن:",
        "price_per_day": "💰 قیمت هر روز رو به تومان وارد کن:",
        "gb_range":      "📶 حداقل و حداکثر گیگ رو با خط فاصله وارد کن:\nمثال: 5-100",
        "days_range":    "⏳ حداقل و حداکثر روز رو با خط فاصله وارد کن:\nمثال: 7-90",
        "inbound_ids":   "📡 شماره Inbound ID ها رو با کاما جدا کن:\nمثال: 1,3,5\n(یا /all برای همه inbound های فعال)",
    }
    await call.message.answer(prompts.get(field, "مقدار جدید رو وارد کن:"))
    await call.answer()


@router.message(AdminEditCustomGroup.entering_value)
async def admin_custom_grp_edit_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    group_id = data["group_id"]
    field = data["field"]
    raw = message.text.strip()

    if field == "name":
        await run_db(update_custom_group, group_id, "name", raw)
        await state.clear()
        await message.answer("✅ نام آپدیت شد.", reply_markup=get_kb(message.from_user.id))
        return

    if field in ("price_per_gb", "price_per_day"):
        if not raw.isdigit():
            await message.answer("❌ فقط عدد:")
            return
        await run_db(update_custom_group, group_id, field, int(raw))
        await state.clear()
        await message.answer("✅ قیمت آپدیت شد.", reply_markup=get_kb(message.from_user.id))
        return

    if field == "gb_range":
        if "-" not in raw:
            await message.answer("❌ فرمت اشتباه. مثال: 5-100")
            return
        try:
            min_v, max_v = raw.split("-")
            min_v, max_v = float(min_v), float(max_v)
            if min_v <= 0 or max_v <= min_v:
                raise ValueError
        except ValueError:
            await message.answer("❌ اعداد معتبر وارد کن (min-max):")
            return
        await run_db(update_custom_group, group_id, "min_gb", min_v)
        await run_db(update_custom_group, group_id, "max_gb", max_v)
        await state.clear()
        await message.answer("✅ محدوده حجم آپدیت شد.", reply_markup=get_kb(message.from_user.id))
        return

    if field == "days_range":
        if "-" not in raw:
            await message.answer("❌ فرمت اشتباه. مثال: 7-90")
            return
        try:
            min_v, max_v = raw.split("-")
            min_v, max_v = int(min_v), int(max_v)
            if min_v <= 0 or max_v <= min_v:
                raise ValueError
        except ValueError:
            await message.answer("❌ اعداد صحیح معتبر وارد کن (min-max):")
            return
        await run_db(update_custom_group, group_id, "min_days", min_v)
        await run_db(update_custom_group, group_id, "max_days", max_v)
        await state.clear()
        await message.answer("✅ محدوده روز آپدیت شد.", reply_markup=get_kb(message.from_user.id))
        return

    if field == "inbound_ids":
        if raw == "/all":
            value = ""
        else:
            ids = [x.strip() for x in raw.split(",") if x.strip().isdigit()]
            if not ids:
                await message.answer("❌ فرمت اشتباه. مثال: 1,3,5 یا /all")
                return
            value = ",".join(ids)
        await run_db(update_custom_group, group_id, "inbound_ids", value)
        await state.clear()
        await message.answer("✅ Inbound IDs آپدیت شد.", reply_markup=get_kb(message.from_user.id))
        return

    await state.clear()
    await message.answer("❌ خطای ناشناخته.", reply_markup=get_kb(message.from_user.id))