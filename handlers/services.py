import io
import qrcode
import datetime
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

from config import ADMIN_ID
from db import (
    get_category, get_services_by_category, get_service,
    get_balance, deduct_balance, create_purchase,
    get_discount_code, use_discount_code,
    get_user, get_referral_config, give_referral_reward,
    has_previous_purchase, save_vpn_account,
    is_partner, get_categories_for_user,
    get_custom_groups, get_custom_group,
    get_category_panel_group_ids,
)
from panel import create_vpn_account
from keyboards import categories_kb, services_kb, invoice_kb, back_kb, custom_groups_kb, home_button_kb
from states import ApplyDiscount, CustomPlanOrder
from utils import format_data, run_db, notify_admins, prepare_new_client

router = Router()


def _make_qr(data: str) -> io.BytesIO:
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ================================================================
# SHOP
# ================================================================

@router.callback_query(F.data == "menu:shop")
async def shop_start(call: types.CallbackQuery):
    partner = await run_db(is_partner, call.from_user.id)
    categories = await run_db(get_categories_for_user, partner, call.from_user.id)
    if not categories:
        await call.message.edit_text("❌ در حال حاضر دسته‌بندی‌ای وجود نداره.", reply_markup=home_button_kb())
        await call.answer()
        return
    bal = await run_db(get_balance, call.from_user.id)
    await call.message.edit_text(
        f"🛒 فروشگاه\n💰 موجودی شما: {bal:,} تومان\n\nیه دسته‌بندی انتخاب کن:",
        reply_markup=categories_kb(categories)
    )
    await call.answer()


@router.callback_query(F.data == "shop:back")
async def shop_back_to_categories(call: types.CallbackQuery):
    partner = await run_db(is_partner, call.from_user.id)
    categories = await run_db(get_categories_for_user, partner, call.from_user.id)
    bal = await run_db(get_balance, call.from_user.id)
    await call.message.edit_text(
        f"🛒 فروشگاه\n💰 موجودی شما: {bal:,} تومان\n\nیه دسته‌بندی انتخاب کن:",
        reply_markup=categories_kb(categories)
    )
    await call.answer()


@router.callback_query(F.data.startswith("cat:"))
async def show_category_services(call: types.CallbackQuery):
    cat_id = int(call.data.split(":")[1])
    cat = await run_db(get_category, cat_id)
    if not cat:
        await call.answer("❌ دسته پیدا نشد", show_alert=True)
        return
    services = await run_db(get_services_by_category, cat_id)
    bal = await run_db(get_balance, call.from_user.id)
    cid, cname, cemoji, is_active, is_custom = cat

    if not services:
        await call.message.edit_text(
            f"{cemoji} {cname}\n\n❌ سرویسی در این دسته وجود نداره.",
            reply_markup=back_kb("shop:back")
        )
        await call.answer()
        return

    sep = "─" * 22
    text = f"{cemoji} {cname}\n💰 موجودی شما: {bal:,} تومان\n\n{sep}\n"
    for s in services:
        sid, name, desc, price, days, data_gb = s
        text += f"📦 {name}\n  💰 {price:,} تومان  |  ⏳ {days} روز  |  {format_data(data_gb)}\n"
        if desc:
            text += f"  📝 {desc}\n"
        text += f"{sep}\n"
    text += "\n👇 روی سرویس مورد نظر کلیک کن:"

    await call.message.edit_text(text, reply_markup=services_kb(services, cat_id))
    await call.answer()


@router.callback_query(F.data.startswith("buy:"))
async def show_invoice(call: types.CallbackQuery):
    service_id = int(call.data.split(":")[1])
    service = await run_db(get_service, service_id)
    if not service:
        await call.answer("❌ سرویس پیدا نشد", show_alert=True)
        return

    # آپدیت: 10 فیلد برمی‌گردد (category_id در انتها اضافه شده)
    sid, name, desc, price, days, data_gb, is_active, cat_name, panel_id, category_id = service
    if not is_active:
        await call.answer("❌ این سرویس فعلاً در دسترس نیست", show_alert=True)
        return

    bal = await run_db(get_balance, call.from_user.id)

    def _get_cat_id(sid):
        from db import connect as _conn
        conn = _conn()
        cur = conn.cursor()
        cur.execute("SELECT category_id FROM services WHERE id=%s", (sid,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row and row[0] else 0

    cat_id = await run_db(_get_cat_id, service_id)

    sep = "─" * 22
    invoice_text = (
        f"🧾 فاکتور خرید\n{sep}\n"
        f"📦 سرویس:     {name}\n"
        f"🗂 دسته:       {cat_name or '—'}\n"
        f"📝 توضیحات:  {desc or '—'}\n"
        f"{sep}\n"
        f"⏳ مدت:        {days} روز\n"
        f"{format_data(data_gb)}\n"
        f"{sep}\n"
        f"💰 قیمت:       {price:,} تومان\n"
        f"👛 موجودی:   {bal:,} تومان\n"
    )
    shortage = price - bal
    if shortage > 0:
        invoice_text += f"\n❌ موجودی کافی نیست\n🔴 کمبود: {shortage:,} تومان"
        await call.message.edit_text(invoice_text, reply_markup=invoice_kb(service_id, cat_id))
    else:
        invoice_text += f"\n✅ موجودی کافیه."
        await call.message.edit_text(invoice_text, reply_markup=invoice_kb(service_id, cat_id))
    await call.answer()


# ================================================================
# DISCOUNT CODE
# ================================================================

@router.callback_query(F.data.startswith("discount:"))
async def ask_discount_code(call: types.CallbackQuery, state: FSMContext):
    _, service_id, cat_id = call.data.split(":")
    await state.set_state(ApplyDiscount.waiting_for_code)
    await state.update_data(service_id=int(service_id), cat_id=int(cat_id))
    await call.message.answer("🎁 کد تخفیف خودت رو وارد کن:")
    await call.answer()


@router.message(ApplyDiscount.waiting_for_code)
async def apply_discount_code(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    data = await state.get_data()
    service_id = data["service_id"]
    cat_id = data["cat_id"]

    discount = await run_db(get_discount_code, code)
    if not discount:
        await message.answer("❌ کد تخفیف نامعتبر یا منقضی شده.")
        await state.clear()
        return

    dc_id, dc_code, dc_type, dc_value, max_uses, used_count = discount
    if max_uses is not None and used_count >= max_uses:
        await message.answer("❌ این کد به حداکثر استفاده رسیده.")
        await state.clear()
        return

    service = await run_db(get_service, service_id)
    # آپدیت: 10 فیلد برمی‌گردد (category_id در انتها اضافه شده)
    sid, name, desc, price, days, data_gb, is_active, cat_name, panel_id, category_id = service

    if dc_type == "percent":
        discount_amount = int(price * dc_value / 100)
    else:
        discount_amount = int(dc_value)

    final_price = max(0, price - discount_amount)
    bal = await run_db(get_balance, message.from_user.id)

    sep = "─" * 22
    invoice_text = (
        f"🧾 فاکتور خرید (با تخفیف)\n{sep}\n"
        f"📦 سرویس:       {name}\n{sep}\n"
        f"⏳ مدت:          {days} روز\n"
        f"{format_data(data_gb)}\n{sep}\n"
        f"💰 قیمت اصلی:  {price:,} تومان\n"
        f"🎁 تخفیف:        {discount_amount:,} تومان\n"
        f"💵 قیمت نهایی:  {final_price:,} تومان\n"
        f"👛 موجودی:      {bal:,} تومان\n"
    )
    await state.clear()

    if bal < final_price:
        invoice_text += f"\n❌ موجودی کافی نیست\n🔴 کمبود: {final_price - bal:,} تومان"
        await message.answer(invoice_text)
    else:
        invoice_text += "\n✅ موجودی کافیه."
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ تایید و پرداخت", callback_data=f"confirm_discounted:{service_id}:{dc_id}:{final_price}")],
            [InlineKeyboardButton(text="🔙 انصراف",         callback_data=f"cat:{cat_id}")],
        ])
        await message.answer(invoice_text, reply_markup=kb)


@router.callback_query(F.data.startswith("confirm_discounted:"))
async def confirm_discounted_buy(call: types.CallbackQuery, bot: Bot):
    _, service_id, dc_id, final_price = call.data.split(":")
    service_id, dc_id, final_price = int(service_id), int(dc_id), int(final_price)

    service = await run_db(get_service, service_id)
    if not service:
        await call.answer("❌ سرویس پیدا نشد", show_alert=True)
        return

    # آپدیت: 10 فیلد برمی‌گردد (category_id در انتها اضافه شده)
    sid, name, desc, price, days, data_gb, is_active, cat_name, panel_id, category_id = service
    user_id = call.from_user.id

    success = await run_db(deduct_balance, user_id, final_price)
    if not success:
        await call.answer("❌ موجودی کافی نیست!", show_alert=True)
        return

    await run_db(use_discount_code, dc_id)
    purchase_id = await run_db(create_purchase, user_id, sid, name, final_price)
    new_bal = await run_db(get_balance, user_id)

    await _handle_purchase_referral_reward(bot, user_id, final_price)

    sep = "─" * 22
    await call.message.edit_text(
        f"✅ خرید موفق!\n{sep}\n"
        f"📦 سرویس:        {name}\n"
        f"⏳ مدت:            {days} روز\n"
        f"{format_data(data_gb)}\n{sep}\n"
        f"💰 پرداخت شد:  {final_price:,} تومان\n"
        f"👛 موجودی:       {new_bal:,} تومان\n{sep}\n"
        f"🔑 شماره سفارش: #{purchase_id}\n\n"
        f"⏳ در حال ساخت اکانت VPN...",
        reply_markup=home_button_kb()
    )
    await call.answer("✅ خرید موفق!")
    username = call.from_user.username or "ندارد"
    await notify_admins(
        bot,
        f"🛍 خرید جدید (با تخفیف)!\n"
        f"👤 User: {user_id} (@{username})\n"
        f"📦 سرویس: {name}\n"
        f"💰 مبلغ پرداختی: {final_price:,} تومان\n"
        f"🔑 سفارش: #{purchase_id}"
    )
    await _create_and_send_vpn(bot, user_id, purchase_id, service, panel_id or 1)


async def _create_and_send_vpn(bot, user_id: int, purchase_id: int, service: tuple, panel_id: int = 1, is_trial: bool = False):
    # آپدیت: 10 فیلد برمی‌گردد (category_id در انتها اضافه شده)
    sid, name, desc, price, days, data_gb, is_active, cat_name, _pid, category_id = service
    email, group = await prepare_new_client(user_id)

    # گروه‌های PasarGuard متصل به این دسته‌بندی (برای 3x-ui لیست خالی هست و
    # بی‌اثره؛ برای PasarGuard اگه دسته گروهی نداشته باشه، اکانت ساخته می‌شه
    # ولی هیچ کانفیگ/پروکسی‌ای نخواهد داشت — پس این مقدار ضروریه)
    group_ids = await run_db(get_category_panel_group_ids, category_id)

    # اتصال به پنل مورد نظر
    result = await create_vpn_account(
        user_id, email, days, float(data_gb),
        group=group, panel_id=panel_id, inbound_ids=group_ids or None
    )

    if result:
        await run_db(save_vpn_account,
            user_id=user_id,
            email=result["email"],
            uuid=None,
            inbound_id=None,
            expire_time=result["expire_time"],
            data_limit=result["data_limit"],
            purchase_id=purchase_id,
            is_trial=is_trial,
            sub_id=result.get("sub_id"),
            sub_url=result.get("sub_url"),
            panel_id=panel_id
        )
        expire_date = datetime.datetime.fromtimestamp(result["expire_time"] / 1000).strftime('%Y-%m-%d')
        sep = "─" * 22
        import html
        safe_sub_url = html.escape(result["sub_url"])
        safe_email = html.escape(result["email"])
        
        # دریافت موجودی جدید کاربر
        new_bal = await run_db(get_balance, user_id)
        
        caption = (
            f"✅ اکانت VPN شما آماده شد!\n{sep}\n"
            f"👤 نام کاربری: <code>{safe_email}</code>\n"
            f"🔗 لینک سابسکریپشن:\n"
            f"<code>{safe_sub_url}</code>\n"
            f"{sep}\n"
            f"📅 انقضا: {expire_date}\n"
            f"📶 حجم: {format_data(data_gb)}\n{sep}\n"
            f"👛 موجودی جدید: {new_bal:,} تومان\n{sep}\n"
            f"⚙️ این لینک رو داخل نرم‌افزار VPN خودت وارد کن."
        )
        qr_buf = _make_qr(result["sub_url"])
        await bot.send_photo(
            user_id,
            photo=BufferedInputFile(qr_buf.read(), filename="vpn_qr.png"),
            caption=caption,
            parse_mode="HTML",
            reply_markup=home_button_kb()
        )
    else:
        await bot.send_message(
            user_id,
            "⚠️ خریدت ثبت شد ولی ساخت اکانت VPN با مشکل مواجه شد.\n"
            "ادمین به زودی اکانتت رو می‌سازه.",
            reply_markup=home_button_kb()
        )


@router.callback_query(F.data.startswith("confirm_buy:"))
async def confirm_buy(call: types.CallbackQuery, bot: Bot):
    service_id = int(call.data.split(":")[1])
    service = await run_db(get_service, service_id)
    if not service:
        await call.answer("❌ سرویس پیدا نشد", show_alert=True)
        return
    # آپدیت: 10 فیلد برمی‌گردد (category_id در انتها اضافه شده)
    sid, name, desc, price, days, data_gb, is_active, cat_name, panel_id, category_id = service
    user_id = call.from_user.id
    success = await run_db(deduct_balance, user_id, price)
    if not success:
        await call.answer("❌ موجودی کافی نیست!", show_alert=True)
        return
    purchase_id = await run_db(create_purchase, user_id, sid, name, price)
    new_bal = await run_db(get_balance, user_id)

    await _handle_purchase_referral_reward(bot, user_id, price)

    sep = "─" * 22
    await call.message.edit_text(
        f"✅ خرید موفق!\n{sep}\n"
        f"📦 سرویس:        {name}\n"
        f"⏳ مدت:            {days} روز\n"
        f"{format_data(data_gb)}\n{sep}\n"
        f"💰 پرداخت شد:  {price:,} تومان\n"
        f"👛 موجودی:       {new_bal:,} تومان\n{sep}\n"
        f"🔑 شماره سفارش: #{purchase_id}\n\n"
        f"⏳ در حال ساخت اکانت VPN...",
        reply_markup=home_button_kb()
    )
    await call.answer("✅ خرید موفق!")
    username = call.from_user.username or "ندارد"
    await notify_admins(
        bot,
        f"🛍 خرید جدید!\n"
        f"👤 User: {user_id} (@{username})\n"
        f"📦 سرویس: {name}\n"
        f"💰 مبلغ: {price:,} تومان\n"
        f"🔑 سفارش: #{purchase_id}"
    )
    await _create_and_send_vpn(bot, user_id, purchase_id, service, panel_id or 1)


async def _handle_purchase_referral_reward(bot: Bot, buyer_id: int, amount_paid: int):
    ref_cfg = await run_db(get_referral_config)
    if not ref_cfg or not ref_cfg[0]:
        return

    user = await run_db(get_user, buyer_id)
    if not user or not user[2]:
        return

    referrer_id = user[2]
    is_enabled, reward_join, first_purchase_reward, reward_purchase, reward_pct = ref_cfg

    is_first = not await run_db(has_previous_purchase, buyer_id)

    reward = 0
    if is_first and first_purchase_reward > 0:
        reward = first_purchase_reward
    else:
        if reward_purchase > 0:
            reward += reward_purchase
        if reward_pct > 0:
            reward += int(amount_paid * float(reward_pct) / 100)

    if reward > 0:
        await run_db(give_referral_reward, referrer_id, buyer_id, "purchase", reward)
        label = "اولین خرید" if is_first and first_purchase_reward > 0 else "خرید"
        try:
            await bot.send_message(
                referrer_id,
                f"🎉 یکی از زیرمجموعه‌هات {label} کرد!\n"
                f"💚 +{reward:,} تومان پاداش به حسابت اضافه شد."
            )
        except Exception:
            pass


# ================================================================
# CUSTOM PLAN (پلن دلخواه)
# ================================================================

@router.callback_query(F.data.startswith("customcat:"))
async def show_custom_groups(call: types.CallbackQuery):
    cat_id = int(call.data.split(":")[1])
    cat = await run_db(get_category, cat_id)
    if not cat:
        await call.answer("❌ دسته پیدا نشد", show_alert=True)
        return
    cid, cname, cemoji = cat[0], cat[1], cat[2]

    groups = await run_db(get_custom_groups, cat_id)
    if not groups:
        await call.message.edit_text(
            f"{cemoji} {cname}\n\n❌ هیچ زیرگروهی برای این پلن تعریف نشده.",
            reply_markup=back_kb("shop:back")
        )
        await call.answer()
        return

    await call.message.edit_text(
        f"{cemoji} {cname}\n\n👇 یکی از گزینه‌های زیر رو انتخاب کن:",
        reply_markup=custom_groups_kb(groups, cat_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("customgrp:"))
async def show_custom_group_detail(call: types.CallbackQuery, state: FSMContext):
    group_id = int(call.data.split(":")[1])
    group = await run_db(get_custom_group, group_id)
    if not group:
        await call.answer("❌ گزینه پیدا نشد", show_alert=True)
        return

    (gid, cat_id, name, emoji, price_per_gb, price_per_day,
     min_gb, max_gb, min_days, max_days, inbound_ids, is_active) = group

    if not is_active:
        await call.answer("❌ این گزینه فعلاً در دسترس نیست", show_alert=True)
        return

    await state.update_data(custom_group_id=group_id)
    await state.set_state(CustomPlanOrder.waiting_gb)

    sep = "─" * 22
    text = (
        f"{emoji} {name}\n{sep}\n"
        f"💰 قیمت هر گیگ: {price_per_gb:,} تومان\n"
        f"💰 قیمت هر روز: {price_per_day:,} تومان\n{sep}\n"
        f"📶 حجم مجاز: {min_gb:g} تا {max_gb:g} گیگابایت\n"
        f"⏳ مدت مجاز: {min_days} تا {max_days} روز\n{sep}\n"
        f"👇 لطفاً مقدار حجم مورد نظرت رو به گیگابایت وارد کن:\n"
        f"(مثلاً: 20)"
    )
    await call.message.edit_text(text)
    await call.answer()


@router.message(CustomPlanOrder.waiting_gb)
async def custom_plan_gb_input(message: types.Message, state: FSMContext):
    raw = message.text.strip().replace(",", ".")
    try:
        gb = float(raw)
        if gb <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ عدد معتبر وارد کن:")
        return

    data = await state.get_data()
    group = await run_db(get_custom_group, data["custom_group_id"])
    if not group:
        await message.answer("❌ خطا در دریافت اطلاعات. دوباره تلاش کن.")
        await state.clear()
        return

    (gid, cat_id, name, emoji, price_per_gb, price_per_day,
     min_gb, max_gb, min_days, max_days, inbound_ids, is_active) = group

    if gb < float(min_gb) or gb > float(max_gb):
        await message.answer(
            f"❌ حجم باید بین {min_gb:g} تا {max_gb:g} گیگابایت باشه:"
        )
        return

    await state.update_data(custom_gb=gb)
    await state.set_state(CustomPlanOrder.waiting_days)
    await message.answer(
        f"📶 حجم انتخابی: {gb:g} گیگابایت\n\n"
        f"👇 حالا مدت زمان مورد نظرت رو به روز وارد کن:\n"
        f"(مثلاً: 30)"
    )


@router.message(CustomPlanOrder.waiting_days)
async def custom_plan_days_input(message: types.Message, state: FSMContext):
    raw = message.text.strip()
    if not raw.isdigit():
        await message.answer("❌ فقط عدد صحیح وارد کن:")
        return
    days = int(raw)

    data = await state.get_data()
    group = await run_db(get_custom_group, data["custom_group_id"])
    if not group:
        await message.answer("❌ خطا در دریافت اطلاعات. دوباره تلاش کن.")
        await state.clear()
        return

    (gid, cat_id, name, emoji, price_per_gb, price_per_day,
     min_gb, max_gb, min_days, max_days, inbound_ids, is_active) = group

    if days < min_days or days > max_days:
        await message.answer(f"❌ مدت باید بین {min_days} تا {max_days} روز باشه:")
        return

    gb = data["custom_gb"]
    base_price = int(gb * price_per_gb + days * price_per_day)

    await state.update_data(custom_days=days, custom_base_price=base_price)
    bal = await run_db(get_balance, message.from_user.id)

    sep = "─" * 22
    text = (
        f"🧾 فاکتور پلن دلخواه\n{sep}\n"
        f"{emoji} {name}\n"
        f"📶 حجم: {gb:g} گیگابایت\n"
        f"⏳ مدت: {days} روز\n{sep}\n"
        f"💰 محاسبه: ({gb:g} × {price_per_gb:,}) + ({days} × {price_per_day:,})\n"
        f"💵 قیمت نهایی: {base_price:,} تومان\n"
        f"👛 موجودی شما: {bal:,} تومان\n"
    )

    buttons = [
        [InlineKeyboardButton(text="🎁 استفاده از کد تخفیف", callback_data="customplan:discount")],
        [InlineKeyboardButton(text="✅ تایید و پرداخت", callback_data="customplan:confirm")],
        [InlineKeyboardButton(text="🔙 انصراف", callback_data="shop:back")],
    ]

    if bal < base_price:
        text += f"\n❌ موجودی کافی نیست\n🔴 کمبود: {base_price - bal:,} تومان"

    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data == "customplan:discount")
async def custom_plan_ask_discount(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(CustomPlanOrder.waiting_discount)
    await call.message.answer("🎁 کد تخفیف رو وارد کن:")
    await call.answer()


@router.message(CustomPlanOrder.waiting_discount)
async def custom_plan_apply_discount(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    data = await state.get_data()
    base_price = data["custom_base_price"]

    discount = await run_db(get_discount_code, code)
    if not discount:
        await message.answer("❌ کد تخفیف نامعتبر یا منقضی شده.")
        return

    dc_id, dc_code, dc_type, dc_value, max_uses, used_count = discount
    if max_uses is not None and used_count >= max_uses:
        await message.answer("❌ این کد به حداکثر استفاده رسیده.")
        return

    if dc_type == "percent":
        discount_amount = int(base_price * dc_value / 100)
    else:
        discount_amount = int(dc_value)

    final_price = max(0, base_price - discount_amount)
    await state.update_data(custom_final_price=final_price, custom_dc_id=dc_id)
    await state.set_state(None)

    bal = await run_db(get_balance, message.from_user.id)
    sep = "─" * 22
    text = (
        f"🧾 فاکتور (با تخفیف)\n{sep}\n"
        f"💰 قیمت اصلی: {base_price:,} تومان\n"
        f"🎁 تخفیف: {discount_amount:,} تومان\n"
        f"💵 قیمت نهایی: {final_price:,} تومان\n"
        f"👛 موجودی شما: {bal:,} تومان\n"
    )
    if bal < final_price:
        text += f"\n❌ موجودی کافی نیست\n🔴 کمبود: {final_price - bal:,} تومان"

    buttons = [
        [InlineKeyboardButton(text="✅ تایید و پرداخت", callback_data="customplan:confirm")],
        [InlineKeyboardButton(text="🔙 انصراف", callback_data="shop:back")],
    ]
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data == "customplan:confirm")
async def custom_plan_confirm(call: types.CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    group_id = data.get("custom_group_id")
    gb = data.get("custom_gb")
    days = data.get("custom_days")
    final_price = data.get("custom_final_price") or data.get("custom_base_price")
    dc_id = data.get("custom_dc_id")

    if not all([group_id, gb, days, final_price]):
        await call.answer("❌ اطلاعات سفارش منقضی شده، دوباره تلاش کن.", show_alert=True)
        await state.clear()
        return

    group = await run_db(get_custom_group, group_id)
    if not group:
        await call.answer("❌ این گزینه دیگه موجود نیست.", show_alert=True)
        await state.clear()
        return

    (gid, cat_id, name, emoji, price_per_gb, price_per_day,
     min_gb, max_gb, min_days, max_days, inbound_ids_str, is_active) = group

    user_id = call.from_user.id
    success = await run_db(deduct_balance, user_id, final_price)
    if not success:
        await call.answer("❌ موجودی کافی نیست!", show_alert=True)
        return

    if dc_id:
        await run_db(use_discount_code, dc_id)

    service_name = f"{name} ({gb:g}GB/{days}روز)"
    purchase_id = await run_db(create_purchase, user_id, None, service_name, final_price)
    new_bal = await run_db(get_balance, user_id)

    await state.clear()

    sep = "─" * 22
    await call.message.edit_text(
        f"✅ خرید موفق!\n{sep}\n"
        f"📦 {service_name}\n"
        f"💰 پرداخت شد: {final_price:,} تومان\n"
        f"👛 موجودی: {new_bal:,} تومان\n{sep}\n"
        f"🔑 سفارش: #{purchase_id}\n\n"
        f"⏳ در حال ساخت اکانت VPN...",
        reply_markup=home_button_kb()
    )
    await call.answer("✅ خرید موفق!")

    username = call.from_user.username or "ندارد"
    await notify_admins(
        bot,
        f"🛍 خرید پلن دلخواه!\n"
        f"👤 User: {user_id} (@{username})\n"
        f"📦 {service_name}\n"
        f"💰 مبلغ: {final_price:,} تومان\n"
        f"🔑 سفارش: #{purchase_id}"
    )

    # گرفتن Panel_id مربوط به این دسته‌بندی
    def _get_panel_id_for_group(g_id):
        from db import connect as _conn
        conn = _conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT c.panel_id FROM custom_plan_groups g
            JOIN categories c ON g.category_id = c.id
            WHERE g.id=%s
        """, (g_id,))
        r = cur.fetchone()
        conn.close()
        return r[0] if r and r[0] else 1
    
    panel_id = await run_db(_get_panel_id_for_group, group_id)

    inbound_ids = None
    if inbound_ids_str:
        try:
            inbound_ids = [int(x.strip()) for x in inbound_ids_str.split(",") if x.strip().isdigit()]
        except Exception:
            inbound_ids = None

    await _create_custom_vpn(bot, user_id, purchase_id, service_name, gb, days, inbound_ids, panel_id)


async def _create_custom_vpn(bot, user_id, purchase_id, service_name, gb, days, inbound_ids, panel_id):
    from panel import get_panel_client

    email, group = await prepare_new_client(user_id)

    client = await get_panel_client(panel_id)
    result = None
    if client:
        result = await client.add_client(email, days, gb, inbound_ids=inbound_ids)
        if result and group:
            await client.set_client_group(email, group)

    if result:
        await run_db(save_vpn_account,
            user_id=user_id,
            email=result["email"],
            uuid=None,
            inbound_id=None,
            expire_time=result["expire_time"],
            data_limit=result["data_limit"],
            purchase_id=purchase_id,
            is_trial=False,
            sub_id=result.get("sub_id"),
            sub_url=result.get("sub_url"),
            panel_id=panel_id
        )
        expire_date = datetime.datetime.fromtimestamp(result["expire_time"] / 1000).strftime('%Y-%m-%d')
        sep = "─" * 22
        import html
        safe_sub_url = html.escape(result["sub_url"])
        safe_service_name = html.escape(service_name)
        safe_email = html.escape(result["email"])
        
        # دریافت موجودی جدید کاربر
        new_bal = await run_db(get_balance, user_id)
        
        caption = (
            f"✅ اکانت VPN شما آماده شد!\n{sep}\n"
            f"📦 {safe_service_name}\n"
            f"👤 نام کاربری: <code>{safe_email}</code>\n\n"
            f"🔗 لینک سابسکریپشن:\n"
            f"<code>{safe_sub_url}</code>\n"
            f"{sep}\n"
            f"📅 انقضا: {expire_date}\n"
            f"📶 حجم: {gb:g} گیگابایت\n{sep}\n"
            f"👛 موجودی جدید: {new_bal:,} تومان\n{sep}\n"
            f"⚙️ این لینک رو داخل نرم‌افزار VPN خودت وارد کن."
        )
        qr_buf = _make_qr(result["sub_url"])
        await bot.send_photo(
            user_id,
            photo=BufferedInputFile(qr_buf.read(), filename="vpn_qr.png"),
            caption=caption,
            parse_mode="HTML",
            reply_markup=home_button_kb()
        )
    else:
        await bot.send_message(
            user_id,
            "⚠️ خریدت ثبت شد ولی ساخت اکانت VPN با مشکل مواجه شد.\n"
            "ادمین به زودی اکانتت رو می‌سازه.",
            reply_markup=home_button_kb()
        )