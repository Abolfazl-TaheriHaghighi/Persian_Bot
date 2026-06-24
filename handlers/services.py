from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from db_final import (
    get_all_categories, get_category, get_services_by_category, get_service,
    get_balance, deduct_balance, create_purchase,
    get_discount_code, use_discount_code,
    get_user, get_referral_config, give_referral_reward,
    has_previous_purchase, save_vpn_account,
    is_partner, get_categories_for_user,
    connect as db_connect
)
from panel import create_vpn_account
from keyboards import get_kb, categories_kb, services_kb, invoice_kb, back_kb
from states import ApplyDiscount
from utils import format_data

router = Router()


# ================================================================
# SHOP
# ================================================================

@router.message(F.text == "🛒 خرید سرویس")
async def shop_start(message: types.Message):
    partner = is_partner(message.from_user.id)
    categories = get_categories_for_user(partner)
    if not categories:
        await message.answer("❌ در حال حاضر دسته‌بندی‌ای وجود نداره.")
        return
    bal = get_balance(message.from_user.id)
    await message.answer(
        f"🛒 فروشگاه\n💰 موجودی شما: {bal:,} تومان\n\nیه دسته‌بندی انتخاب کن:",
        reply_markup=categories_kb(categories)
    )


@router.callback_query(F.data == "shop:back")
async def shop_back_to_categories(call: types.CallbackQuery):
    partner = is_partner(call.from_user.id)
    categories = get_categories_for_user(partner)
    bal = get_balance(call.from_user.id)
    await call.message.edit_text(
        f"🛒 فروشگاه\n💰 موجودی شما: {bal:,} تومان\n\nیه دسته‌بندی انتخاب کن:",
        reply_markup=categories_kb(categories)
    )
    await call.answer()


@router.callback_query(F.data.startswith("cat:"))
async def show_category_services(call: types.CallbackQuery):
    cat_id = int(call.data.split(":")[1])
    cat = get_category(cat_id)
    if not cat:
        await call.answer("❌ دسته پیدا نشد", show_alert=True)
        return
    services = get_services_by_category(cat_id)
    bal = get_balance(call.from_user.id)
    cid, cname, cemoji, _ = cat

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
        text += (
            f"📦 {name}\n"
            f"  💰 {price:,} تومان  |  ⏳ {days} روز  |  {format_data(data_gb)}\n"
        )
        if desc:
            text += f"  📝 {desc}\n"
        text += f"{sep}\n"
    text += "\n👇 روی سرویس مورد نظر کلیک کن:"

    await call.message.edit_text(text, reply_markup=services_kb(services, cat_id))
    await call.answer()


@router.callback_query(F.data.startswith("buy:"))
async def show_invoice(call: types.CallbackQuery):
    service_id = int(call.data.split(":")[1])
    service = get_service(service_id)
    if not service:
        await call.answer("❌ سرویس پیدا نشد", show_alert=True)
        return
    sid, name, desc, price, days, data_gb, is_active, cat_name = service
    if not is_active:
        await call.answer("❌ این سرویس فعلاً در دسترس نیست", show_alert=True)
        return

    bal = get_balance(call.from_user.id)
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT category_id FROM services WHERE id=%s", (service_id,))
    row = cur.fetchone()
    conn.close()
    cat_id = row[0] if row and row[0] else 0

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
        await call.message.edit_text(invoice_text, reply_markup=back_kb(f"cat:{cat_id}"))
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

    discount = get_discount_code(code)
    if not discount:
        await message.answer("❌ کد تخفیف نامعتبر یا منقضی شده.")
        await state.clear()
        return

    dc_id, dc_code, dc_type, dc_value, max_uses, used_count = discount
    if max_uses is not None and used_count >= max_uses:
        await message.answer("❌ این کد به حداکثر استفاده رسیده.")
        await state.clear()
        return

    service = get_service(service_id)
    sid, name, desc, price, days, data_gb, is_active, cat_name = service

    if dc_type == "percent":
        discount_amount = int(price * dc_value / 100)
    else:
        discount_amount = int(dc_value)

    final_price = max(0, price - discount_amount)
    bal = get_balance(message.from_user.id)

    sep = "─" * 22
    invoice_text = (
        f"🧾 فاکتور خرید (با تخفیف)\n{sep}\n"
        f"📦 سرویس:       {name}\n"
        f"{sep}\n"
        f"⏳ مدت:          {days} روز\n"
        f"{format_data(data_gb)}\n"
        f"{sep}\n"
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

    service = get_service(service_id)
    if not service:
        await call.answer("❌ سرویس پیدا نشد", show_alert=True)
        return

    sid, name, desc, price, days, data_gb, is_active, cat_name = service
    user_id = call.from_user.id

    success = deduct_balance(user_id, final_price)
    if not success:
        await call.answer("❌ موجودی کافی نیست!", show_alert=True)
        return

    use_discount_code(dc_id)
    purchase_id = create_purchase(user_id, sid, name, final_price)
    new_bal = get_balance(user_id)

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
        f"⏳ در حال ساخت اکانت VPN..."
    )
    from config import ADMIN_ID
    username = call.from_user.username or "ندارد"
    await bot.send_message(
        ADMIN_ID,
        f"🛍 خرید جدید (با تخفیف)!\n"
        f"👤 User: {user_id} (@{username})\n"
        f"📦 سرویس: {name}\n"
        f"💰 مبلغ پرداختی: {final_price:,} تومان\n"
        f"🔑 سفارش: #{purchase_id}"
    )
    await _create_and_send_vpn(bot, user_id, purchase_id, service)
    await call.answer("✅ خرید موفق!")


import io
import qrcode


def _make_qr(data: str) -> io.BytesIO:
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


async def _create_and_send_vpn(bot, user_id: int, purchase_id: int, service: tuple, is_trial: bool = False):
    """ساخت اکانت VPN و ارسال لینک سابسکریپشن + QR Code به کاربر"""
    sid, name, desc, price, days, data_gb, is_active, cat_name = service
    import time
    email = f"user{user_id}_{int(time.time())}"

    result = await create_vpn_account(user_id, email, days, float(data_gb))

    if result:
        save_vpn_account(
            user_id=user_id,
            email=result["email"],
            uuid=result["uuid"],
            inbound_id=result["inbound_id"],
            expire_time=result["expire_time"],
            data_limit=result["data_limit"],
            purchase_id=purchase_id,
            is_trial=is_trial,
            sub_id=result.get("sub_id"),
            sub_url=result.get("sub_url")
        )
        import datetime
        expire_date = datetime.datetime.fromtimestamp(result["expire_time"] / 1000).strftime('%Y-%m-%d')
        sep = "─" * 22
        caption = (
            f"✅ اکانت VPN شما آماده شد!\n{sep}\n"
            f"🔗 لینک سابسکریپشن:\n"
            f"`{result['sub_url']}`\n"
            f"{sep}\n"
            f"📅 انقضا: {expire_date}\n"
            f"{format_data(data_gb)}\n{sep}\n"
            f"⚙️ این لینک رو داخل نرم‌افزار VPN خودت وارد کن."
        )
        qr_buf = _make_qr(result["sub_url"])
        from aiogram.types import BufferedInputFile
        await bot.send_photo(
            user_id,
            photo=BufferedInputFile(qr_buf.read(), filename="vpn_qr.png"),
            caption=caption,
            parse_mode="Markdown"
        )
    else:
        await bot.send_message(
            user_id,
            "⚠️ خریدت ثبت شد ولی ساخت اکانت VPN با مشکل مواجه شد.\n"
            "ادمین به زودی اکانتت رو می‌سازه."
        )


@router.callback_query(F.data.startswith("confirm_buy:"))
async def confirm_buy(call: types.CallbackQuery, bot: Bot):
    service_id = int(call.data.split(":")[1])
    service = get_service(service_id)
    if not service:
        await call.answer("❌ سرویس پیدا نشد", show_alert=True)
        return
    sid, name, desc, price, days, data_gb, is_active, cat_name = service
    user_id = call.from_user.id
    success = deduct_balance(user_id, price)
    if not success:
        await call.answer("❌ موجودی کافی نیست!", show_alert=True)
        return
    purchase_id = create_purchase(user_id, sid, name, price)
    new_bal = get_balance(user_id)

    await _handle_purchase_referral_reward(bot, user_id, price)

    sep = "─" * 22
    from config import ADMIN_ID
    await call.message.edit_text(
        f"✅ خرید موفق!\n{sep}\n"
        f"📦 سرویس:        {name}\n"
        f"⏳ مدت:            {days} روز\n"
        f"{format_data(data_gb)}\n{sep}\n"
        f"💰 پرداخت شد:  {price:,} تومان\n"
        f"👛 موجودی:       {new_bal:,} تومان\n{sep}\n"
        f"🔑 شماره سفارش: #{purchase_id}\n\n"
        f"⏳ در حال ساخت اکانت VPN..."
    )
    username = call.from_user.username or "ندارد"
    await bot.send_message(
        ADMIN_ID,
        f"🛍 خرید جدید!\n"
        f"👤 User: {user_id} (@{username})\n"
        f"📦 سرویس: {name}\n"
        f"💰 مبلغ: {price:,} تومان\n"
        f"🔑 سفارش: #{purchase_id}"
    )
    await _create_and_send_vpn(bot, user_id, purchase_id, service)
    await call.answer("✅ خرید موفق!")


async def _handle_purchase_referral_reward(bot: Bot, buyer_id: int, amount_paid: int):
    """اگه خریدار زیرمجموعه کسیه، به دعوت‌کننده پاداش بده"""
    ref_cfg = get_referral_config()
    if not ref_cfg or not ref_cfg[0]:
        return

    user = get_user(buyer_id)
    if not user or not user[2]:
        return

    referrer_id = user[2]
    is_enabled, reward_join, first_purchase_reward, reward_purchase, reward_pct = ref_cfg

    # چک کن اولین خریده یا نه (موقع صدا زدن این تابع، خرید ثبت شده پس count >= 1)
    is_first = not has_previous_purchase(buyer_id)

    reward = 0
    if is_first and first_purchase_reward > 0:
        # اولین خرید → پاداش ثابت اول
        reward = first_purchase_reward
    else:
        # خریدهای بعدی → ثابت + درصدی
        if reward_purchase > 0:
            reward += reward_purchase
        if reward_pct > 0:
            reward += int(amount_paid * float(reward_pct) / 100)

    if reward > 0:
        give_referral_reward(referrer_id, buyer_id, "purchase", reward)
        label = "اولین خرید" if is_first and first_purchase_reward > 0 else "خرید"
        try:
            await bot.send_message(
                referrer_id,
                f"🎉 یکی از زیرمجموعه‌هات {label} کرد!\n"
                f"💚 +{reward:,} تومان پاداش به حسابت اضافه شد."
            )
        except Exception:
            pass