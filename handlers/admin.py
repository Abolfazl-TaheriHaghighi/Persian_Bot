from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_ID, is_admin
from db_final import (
    get_all_users, get_pending_transactions, get_all_purchases,
    get_all_categories, get_category, add_category, toggle_category, delete_category,
    get_all_services, get_service, add_service, toggle_service, hard_delete_service, update_service,
    get_all_discount_codes, create_discount_code, delete_discount_code,
    get_balance, set_balance, add_balance,
    get_trial_config, update_trial_config,
    get_all_phone_overrides, set_phone_max_uses, delete_phone_override, get_all_trial_uses,
    get_referral_config, update_referral_config,
    get_all_channels, add_channel, delete_channel, toggle_channel,
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
    AdminAddChannel
)
from pro_guard import (
    require_pro, check_free_category_limit, check_free_service_limit
)

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
    users = get_all_users()
    text = f"👥 تعداد کاربران: {len(users)}\n\n"
    for u in users:
        text += f"🆔 {u[0]} | 💰 {u[1]:,} تومان\n"
    await call.message.edit_text(text, reply_markup=back_kb("admin:back"))
    await call.answer()


@router.callback_query(F.data == "admin:pending")
async def admin_pending(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    txs = get_pending_transactions()
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
    purchases = get_all_purchases()
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
    cats = get_all_categories(active_only=False)
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
    new_status = toggle_category(cat_id)
    await call.answer("✅ فعال شد" if new_status else "❌ غیرفعال شد", show_alert=True)
    cats = get_all_categories(active_only=False)
    await call.message.edit_text("🗂 دسته‌بندی‌ها:\n✅=فعال | ❌=غیرفعال", reply_markup=admin_categories_kb(cats))


@router.callback_query(F.data.startswith("admin:del_cat:"))
async def admin_del_cat(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cat_id = int(call.data.split(":")[2])
    delete_category(cat_id)
    await call.answer("🗑 دسته غیرفعال شد", show_alert=True)
    cats = get_all_categories(active_only=False)
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
    cid = add_category(data["name"], emoji)
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
    services = get_all_services(active_only=False)
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
    service = get_service(sid)
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
    new_status = toggle_service(sid)
    await call.answer("✅ فعال شد" if new_status else "❌ غیرفعال شد", show_alert=True)
    service = get_service(sid)
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
    hard_delete_service(sid)
    await call.answer("🗑 سرویس کاملاً حذف شد", show_alert=True)
    services = get_all_services(active_only=False)
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

    update_service(sid, field, value)
    await state.clear()
    await message.answer("✅ سرویس آپدیت شد!", reply_markup=get_kb(message.from_user.id))


# ---- افزودن سرویس ----

@router.callback_query(F.data == "admin:add_service")
async def admin_add_service_start(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    if not await check_free_service_limit(call):
        return
    cats = get_all_categories(active_only=True)
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
    sid = add_service(data["name"], data.get("description", ""), data["price"], data["duration"], data_gb, data.get("category_id"))
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
    codes = get_all_discount_codes()
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
    cid = create_discount_code(
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
    delete_discount_code(dc_id)
    await call.answer("🗑 کد حذف شد", show_alert=True)
    codes = get_all_discount_codes()
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
    old_bal = get_balance(uid)

    if text.startswith("="):
        val = text[1:]
        if not val.isdigit():
            await message.answer("❌ فرمت اشتباه:")
            return
        new_val = int(val)
        set_balance(uid, new_val)
        action = f"ست شد به {new_val:,} تومان"
        user_msg = (f"🔔 موجودی حساب شما توسط ادمین تغییر کرد\n"
                    f"💰 موجودی قبلی: {old_bal:,} تومان\n"
                    f"💰 موجودی جدید: {new_val:,} تومان")
    elif text.lstrip("-").isdigit():
        val = int(text)
        add_balance(uid, val)
        if val > 0:
            action = f"+{val:,} تومان اضافه شد"
            user_msg = (f"🔔 موجودی حساب شما توسط ادمین افزایش یافت\n"
                        f"💚 +{val:,} تومان اضافه شد\n"
                        f"💰 موجودی جدید: {get_balance(uid):,} تومان")
        else:
            action = f"{val:,} تومان کسر شد"
            user_msg = (f"🔔 موجودی حساب شما توسط ادمین کاهش یافت\n"
                        f"🔴 {val:,} تومان کسر شد\n"
                        f"💰 موجودی جدید: {get_balance(uid):,} تومان")
    else:
        await message.answer("❌ فرمت اشتباه:")
        return

    new_bal = get_balance(uid)
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
    await call.message.edit_text("🧪 مدیریت تست رایگان:", reply_markup=admin_trial_menu_kb())
    await call.answer()


@router.callback_query(F.data == "admin:trial_toggle")
async def admin_trial_toggle(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cfg = get_trial_config()
    new_val = not cfg[0]
    update_trial_config(is_enabled=new_val)
    await call.answer("✅ فعال شد" if new_val else "❌ غیرفعال شد", show_alert=True)
    await call.message.edit_text("🧪 مدیریت تست رایگان:", reply_markup=admin_trial_menu_kb())


@router.callback_query(F.data == "admin:trial_toggle_ref")
async def admin_trial_toggle_ref(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cfg = get_trial_config()
    new_val = not cfg[3]
    update_trial_config(require_referral=new_val)
    await call.answer("✅ نیاز به رفرال فعال شد" if new_val else "❌ نیاز به رفرال حذف شد", show_alert=True)
    await call.message.edit_text("🧪 مدیریت تست رایگان:", reply_markup=admin_trial_menu_kb())


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

    update_trial_config(**{field: value})
    await state.clear()
    await message.answer("✅ تنظیمات تست ذخیره شد.", reply_markup=get_kb(message.from_user.id))


@router.callback_query(F.data == "admin:trial_phones")
async def admin_trial_phones(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    overrides = get_all_phone_overrides()
    cfg = get_trial_config()
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
        [InlineKeyboardButton(text="➕ تنظیم شماره اختصاصی", callback_data="admin:trial_add_phone")],
        [InlineKeyboardButton(text="🗑 حذف override شماره",   callback_data="admin:trial_del_phone")],
        [InlineKeyboardButton(text="📋 لیست کامل تست‌ها",    callback_data="admin:trial_uses")],
        [InlineKeyboardButton(text="🔙 برگشت",                callback_data="admin:trial_menu")],
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
    if data.get("override_mode") == "delete":
        delete_phone_override(phone)
        await state.clear()
        await message.answer(
            f"✅ Override شماره {phone} حذف شد.",
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
    set_phone_max_uses(phone, max_uses)
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


@router.callback_query(F.data == "admin:trial_uses")
async def admin_trial_uses(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    uses = get_all_trial_uses()
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
    await call.message.edit_text("🔗 تنظیمات سیستم رفرال:", reply_markup=admin_referral_menu_kb())
    await call.answer()


@router.callback_query(F.data == "admin:ref_toggle")
async def admin_ref_toggle(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cfg = get_referral_config()
    new_val = not cfg[0]
    update_referral_config(is_enabled=new_val)
    await call.answer("✅ رفرال فعال شد" if new_val else "❌ رفرال غیرفعال شد", show_alert=True)
    await call.message.edit_text("🔗 تنظیمات سیستم رفرال:", reply_markup=admin_referral_menu_kb())


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

    update_referral_config(**{field: value})
    await state.clear()
    await message.answer("✅ تنظیمات رفرال ذخیره شد.", reply_markup=get_kb(message.from_user.id))


@router.callback_query(F.data == "admin:ref_history")
async def admin_ref_history(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT referrer_id, referred_id, reward_type, amount, created_at
        FROM referral_rewards ORDER BY created_at DESC LIMIT 50
    """)
    rows = cur.fetchall()
    conn.close()

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
    channels = get_all_channels()
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
    new_status = toggle_channel(ch_id)
    await call.answer("✅ فعال شد" if new_status else "❌ غیرفعال شد", show_alert=True)
    channels = get_all_channels()
    await call.message.edit_text(
        "📢 کانال‌های اجباری:\n✅=فعال | ❌=غیرفعال\n\n",
        reply_markup=channels_kb(channels)
    )


@router.callback_query(F.data.startswith("admin:ch_del:"))
async def admin_ch_del(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    ch_id = int(call.data.split(":")[2])
    delete_channel(ch_id)
    await call.answer("🗑 کانال حذف شد", show_alert=True)
    channels = get_all_channels()
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
    cid = add_channel(
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


def panel_config_kb():
    cfg = get_panel_config()
    url, auth_type, username, password, api_key, inbound_id, panel_path = cfg or (None,)*7
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
        [InlineKeyboardButton(text="📋 لیست Inbound ها", callback_data="admin:panel_inbounds")],
        [InlineKeyboardButton(text="🔌 تست اتصال", callback_data="admin:panel_test")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:back")],
    ])


@router.callback_query(F.data == "admin:panel_config")
async def admin_panel_config(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("⚙️ تنظیمات پنل VPN:", reply_markup=panel_config_kb())
    await call.answer()


@router.callback_query(F.data == "admin:panel_toggle_auth")
async def admin_panel_toggle_auth(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cfg = get_panel_config()
    new_auth = "apikey" if cfg[1] == "userpass" else "userpass"
    if new_auth == "apikey" and not await require_pro(call, "اتصال با API Key"):
        return
    update_panel_config(auth_type=new_auth)
    await call.answer("🔑 API Key" if new_auth == "apikey" else "👤 یوزر/پس", show_alert=True)
    await call.message.edit_text("⚙️ تنظیمات پنل VPN:", reply_markup=panel_config_kb())


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
    elif field == "panel_url":
        value = raw.rstrip("/")
    else:
        value = raw

    update_panel_config(**{field: value})
    await state.clear()
    await message.answer("✅ ذخیره شد.", reply_markup=get_kb(message.from_user.id))


@router.callback_query(F.data == "admin:panel_test")
async def admin_panel_test(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("🔌 در حال تست اتصال...")
    ok, msg = await test_panel_connection()
    await call.message.edit_text(
        f"{'✅' if ok else '❌'} {msg}",
        reply_markup=panel_config_kb()
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
        [InlineKeyboardButton(text="🔙 برگشت به لیست", callback_data="admin:partners")],
    ])


@router.callback_query(F.data == "admin:partners")
async def admin_partners(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    if not await require_pro(call, "همکاران"):
        return
    partners = get_all_partners()
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
    p = get_partner(user_id)
    if not p:
        await call.answer("❌ یافت نشد", show_alert=True)
        return
    pid, uid, phone, desc, status, added_at = p
    sep = "─" * 22
    text = (
        f"🤝 جزئیات همکار\n{sep}\n"
        f"🆔 User ID: {uid}\n"
        f"📱 شماره: {phone or '—'}\n"
        f"📝 توضیحات: {desc or '—'}\n"
        f"🔘 وضعیت: {'✅ فعال' if status == 'active' else '❌ غیرفعال'}\n"
        f"📅 تاریخ: {added_at.strftime('%Y-%m-%d')}\n"
    )
    await call.message.edit_text(text, reply_markup=partner_detail_kb(uid, status == "active"))
    await call.answer()


@router.callback_query(F.data.startswith("admin:partner_toggle:"))
async def admin_partner_toggle(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    user_id = int(call.data.split(":")[2])
    p = get_partner(user_id)
    if not p:
        await call.answer("❌ یافت نشد", show_alert=True)
        return
    if p[4] == "active":
        remove_partner(user_id)
        await call.answer("❌ غیرفعال شد", show_alert=True)
    else:
        add_partner(user_id, p[2], p[3])
        await call.answer("✅ فعال شد", show_alert=True)
    p = get_partner(user_id)
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
    add_partner(uid, phone)
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

def category_visibility_kb(categories):
    buttons = []
    for c in categories:
        cid, name, emoji, is_active, sort_order, visibility = c
        vis_label = "👥 همه" if visibility in ("all", None) else "🤝 فقط همکاران"
        buttons.append([
            InlineKeyboardButton(
                text=f"{emoji} {name} | {vis_label}",
                callback_data=f"admin:cat_vis:{cid}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "admin:cat_visibility")
async def admin_cat_visibility(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT id, name, emoji, is_active, sort_order, visibility FROM categories ORDER BY sort_order, id")
    cats = cur.fetchall()
    conn.close()
    await call.message.edit_text(
        "👁 دسترسی دسته‌بندی‌ها:\n👥 همه = همه کاربران | 🤝 فقط همکاران\n\n"
        "برای تغییر کلیک کن:",
        reply_markup=category_visibility_kb(cats)
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin:cat_vis:"))
async def admin_toggle_cat_visibility(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cat_id = int(call.data.split(":")[2])
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT visibility FROM categories WHERE id=%s", (cat_id,))
    r = cur.fetchone()
    conn.close()
    current = r[0] if r else "all"
    new_vis = "partners" if current in ("all", None) else "all"
    set_category_visibility(cat_id, new_vis)
    await call.answer("🤝 فقط همکاران" if new_vis == "partners" else "👥 همه", show_alert=True)

    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT id, name, emoji, is_active, sort_order, visibility FROM categories ORDER BY sort_order, id")
    cats = cur.fetchall()
    conn.close()
    await call.message.edit_text(
        "👁 دسترسی دسته‌بندی‌ها:\n👥 همه = همه کاربران | 🤝 فقط همکاران\n\nبرای تغییر کلیک کن:",
        reply_markup=category_visibility_kb(cats)
    )