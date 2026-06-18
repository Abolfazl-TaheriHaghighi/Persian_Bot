import asyncio

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove
)

from config import BOT_TOKEN, ADMIN_ID
from db import (
    init_db, add_user, get_user, get_balance, deduct_balance, set_balance, add_balance,
    create_transaction, approve_transaction, reject_transaction,
    get_all_users, get_pending_transactions,
    get_all_categories, get_category, add_category, toggle_category, delete_category,
    get_services_by_category, get_all_services, get_service,
    add_service, delete_service, toggle_service,
    create_purchase, get_user_purchases, get_all_purchases,
    create_discount_code, get_discount_code, use_discount_code,
    get_all_discount_codes, delete_discount_code,
    hard_delete_service, update_service,
    set_user_phone, get_referral_count, get_referrals,
    # Free trial
    get_trial_config, update_trial_config,
    get_trial_use_count, get_phone_max_uses, set_phone_max_uses,
    delete_phone_override, get_all_phone_overrides,
    record_trial_use, get_all_trial_uses,
    # Referral
    get_referral_config, update_referral_config,
    get_referral_stats, give_referral_reward, get_referral_rewards_history
)

dp = Dispatcher(storage=MemoryStorage())


# ================================================================
# HELPERS
# ================================================================

def format_data(gb) -> str:
    if float(gb) == 0:
        return "♾ نامحدود"
    gb = float(gb)
    if gb < 1:
        mb = round(gb * 1024)
        return f"📶 {mb} مگابایت"
    if gb == int(gb):
        return f"📶 {int(gb)} گیگابایت"
    return f"📶 {gb:g} گیگابایت"

def data_label_short(gb) -> str:
    gb = float(gb)
    if gb == 0:
        return "∞"
    if gb < 1:
        return f"{round(gb*1024)}MB"
    return f"{gb:g}GB"

def normalize_phone(phone: str) -> str:
    """نرمال‌سازی شماره تلفن به فرمت 09xxxxxxxxx"""
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("+98"):
        phone = "0" + phone[3:]
    elif phone.startswith("98") and len(phone) == 12:
        phone = "0" + phone[2:]
    return phone


# ================================================================
# STATES
# ================================================================

class DepositStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_receipt = State()

class RejectReason(StatesGroup):
    waiting_for_reason = State()

class AdminAddCategory(StatesGroup):
    name = State()
    emoji = State()

class AdminAddService(StatesGroup):
    category = State()
    name = State()
    description = State()
    price = State()
    duration = State()
    data_limit = State()

class AdminEditService(StatesGroup):
    choosing_field = State()
    entering_value = State()

class AdminEditBalance(StatesGroup):
    user_id = State()
    amount = State()

class AdminDiscountCode(StatesGroup):
    code = State()
    discount_type = State()
    discount_value = State()
    max_uses = State()

class ApplyDiscount(StatesGroup):
    waiting_for_code = State()

# ---- Free Trial States ----
class FreeTrial(StatesGroup):
    waiting_phone = State()

class AdminTrialConfig(StatesGroup):
    choosing_field = State()
    entering_value = State()

class AdminPhoneOverride(StatesGroup):
    phone = State()
    max_uses = State()

# ---- Referral Admin States ----
class AdminReferralConfig(StatesGroup):
    choosing_field = State()
    entering_value = State()


# ================================================================
# KEYBOARDS
# ================================================================

def get_kb(user_id):
    base = [
        [KeyboardButton(text="🏠 خانه")],
        [KeyboardButton(text="💰 موجودی من"), KeyboardButton(text="📋 خریدهای من")],
        [KeyboardButton(text="➕ شارژ حساب"), KeyboardButton(text="🛒 خرید سرویس")],
        [KeyboardButton(text="🎁 تست رایگان"), KeyboardButton(text="👥 رفرال من")],
    ]
    if user_id == ADMIN_ID:
        base.append([KeyboardButton(text="🛠 پنل ادمین")])
    return ReplyKeyboardMarkup(keyboard=base, resize_keyboard=True)

def back_kb(cb: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 برگشت", callback_data=cb)]
    ])

def admin_panel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 لیست کاربران",          callback_data="admin:users")],
        [InlineKeyboardButton(text="🗂 مدیریت دسته‌بندی‌ها",   callback_data="admin:categories")],
        [InlineKeyboardButton(text="📦 مدیریت سرویس‌ها",       callback_data="admin:services")],
        [InlineKeyboardButton(text="🎁 کدهای تخفیف",           callback_data="admin:discounts")],
        [InlineKeyboardButton(text="💳 تراکنش‌های در انتظار",  callback_data="admin:pending")],
        [InlineKeyboardButton(text="🛍 تاریخچه خریدها",        callback_data="admin:purchases")],
        [InlineKeyboardButton(text="➕ افزودن دسته‌بندی",      callback_data="admin:add_category")],
        [InlineKeyboardButton(text="➕ افزودن سرویس",          callback_data="admin:add_service")],
        [InlineKeyboardButton(text="💸 تنظیم موجودی کاربر",   callback_data="admin:edit_balance")],
        [InlineKeyboardButton(text="🧪 مدیریت تست رایگان",    callback_data="admin:trial_menu")],
        [InlineKeyboardButton(text="🔗 تنظیمات رفرال",         callback_data="admin:referral_menu")],
    ])

def categories_kb(categories):
    buttons = [
        [InlineKeyboardButton(text=f"{c[2]} {c[1]}", callback_data=f"cat:{c[0]}")]
        for c in categories
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def services_kb(services, cat_id):
    buttons = []
    for s in services:
        sid, name, desc, price, days, data_gb = s
        dl = data_label_short(data_gb)
        buttons.append([
            InlineKeyboardButton(
                text=f"{name} | {price:,}T | {days}روز | {dl}",
                callback_data=f"buy:{sid}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 برگشت به دسته‌ها", callback_data="shop:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def invoice_kb(service_id, cat_id, has_discount=False):
    buttons = []
    if not has_discount:
        buttons.append([InlineKeyboardButton(text="🎁 استفاده از کد تخفیف", callback_data=f"discount:{service_id}:{cat_id}")])
    buttons.append([InlineKeyboardButton(text="✅ تایید و پرداخت", callback_data=f"confirm_buy:{service_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 برگشت به سرویس‌ها", callback_data=f"cat:{cat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_categories_kb(categories):
    buttons = []
    for c in categories:
        cid, name, emoji, is_active, sort_order = c
        st = "✅" if is_active else "❌"
        buttons.append([
            InlineKeyboardButton(text=f"{st} {emoji} {name}", callback_data=f"admin:toggle_cat:{cid}"),
            InlineKeyboardButton(text="🗑",                    callback_data=f"admin:del_cat:{cid}"),
        ])
    buttons.append([InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_services_kb(services):
    buttons = []
    for s in services:
        sid, name, desc, price, days, data_gb, is_active, cat_name, cat_id = s
        st = "✅" if is_active else "❌"
        dl = data_label_short(data_gb)
        buttons.append([
            InlineKeyboardButton(text=f"{st} {name} | {price:,} | {dl}", callback_data=f"admin:svc_detail:{sid}"),
        ])
    buttons.append([InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_svc_detail_kb(sid, is_active):
    toggle_text = "❌ غیرفعال کردن" if is_active else "✅ فعال کردن"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ ویرایش سرویس",    callback_data=f"admin:edit_svc:{sid}")],
        [InlineKeyboardButton(text=toggle_text,            callback_data=f"admin:toggle:{sid}")],
        [InlineKeyboardButton(text="🗑 حذف کامل",         callback_data=f"admin:hard_del:{sid}")],
        [InlineKeyboardButton(text="🔙 برگشت به لیست",   callback_data="admin:services")],
    ])

def admin_edit_svc_fields_kb(sid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 نام",          callback_data=f"admin:editfield:{sid}:name")],
        [InlineKeyboardButton(text="📝 توضیحات",     callback_data=f"admin:editfield:{sid}:description")],
        [InlineKeyboardButton(text="💰 قیمت",         callback_data=f"admin:editfield:{sid}:price")],
        [InlineKeyboardButton(text="⏳ مدت (روز)",   callback_data=f"admin:editfield:{sid}:duration")],
        [InlineKeyboardButton(text="📶 حجم (GB)",    callback_data=f"admin:editfield:{sid}:data_limit")],
        [InlineKeyboardButton(text="🗂 دسته‌بندی",   callback_data=f"admin:editfield:{sid}:category")],
        [InlineKeyboardButton(text="🔙 برگشت",       callback_data=f"admin:svc_detail:{sid}")],
    ])

def admin_discounts_kb(codes):
    buttons = []
    for c in codes:
        cid, code, dtype, dval, max_uses, used = c
        type_label = "%" if dtype == "percent" else "T"
        buttons.append([
            InlineKeyboardButton(
                text=f"🎁 {code} | {dval}{type_label} | {used}/{max_uses if max_uses else '∞'}",
                callback_data=f"admin:del_discount:{cid}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="➕ کد جدید",  callback_data="admin:add_discount")])
    buttons.append([InlineKeyboardButton(text="🔙 برگشت",    callback_data="admin:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_trial_menu_kb():
    cfg = get_trial_config()
    is_enabled, duration_days, data_limit_gb, require_referral, min_referrals, default_max_uses = cfg
    status = "✅ فعال" if is_enabled else "❌ غیرفعال"
    ref_req = "✅ بله" if require_referral else "❌ خیر"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"وضعیت: {status}", callback_data="admin:trial_toggle")],
        [InlineKeyboardButton(text=f"⏳ مدت: {duration_days} روز", callback_data="admin:trial_set:duration_days")],
        [InlineKeyboardButton(text=f"📶 حجم: {data_label_short(data_limit_gb)}", callback_data="admin:trial_set:data_limit_gb")],
        [InlineKeyboardButton(text=f"🔗 نیاز رفرال: {ref_req}", callback_data="admin:trial_toggle_ref")],
        [InlineKeyboardButton(text=f"👥 حداقل رفرال: {min_referrals}", callback_data="admin:trial_set:min_referrals")],
        [InlineKeyboardButton(text=f"🔢 تست پیش‌فرض: {default_max_uses} بار", callback_data="admin:trial_set:default_max_uses")],
        [InlineKeyboardButton(text="📱 مدیریت شماره‌ها", callback_data="admin:trial_phones")],
        [InlineKeyboardButton(text="📋 لیست تست‌های گرفته‌شده", callback_data="admin:trial_uses")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:back")],
    ])

def admin_referral_menu_kb():
    cfg = get_referral_config()
    is_enabled, reward_join, reward_purchase, reward_pct = cfg
    status = "✅ فعال" if is_enabled else "❌ غیرفعال"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"وضعیت: {status}", callback_data="admin:ref_toggle")],
        [InlineKeyboardButton(text=f"🎁 پاداش ثبت‌نام: {reward_join:,} تومان", callback_data="admin:ref_set:reward_on_join")],
        [InlineKeyboardButton(text=f"🛍 پاداش خرید (ثابت): {reward_purchase:,} تومان", callback_data="admin:ref_set:reward_on_purchase")],
        [InlineKeyboardButton(text=f"📊 پاداش خرید (درصد): {reward_pct}%", callback_data="admin:ref_set:reward_purchase_percent")],
        [InlineKeyboardButton(text="📋 تاریخچه پاداش‌ها", callback_data="admin:ref_history")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:back")],
    ])


# ================================================================
# START / HOME
# ================================================================

@dp.message(Command("start"))
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

    # ثبت کاربر
    add_user(message.from_user.id, referred_by)

    # اگه رفرال داشت و رفرال فعاله → پاداش ثبت‌نام
    if referred_by:
        user_data = None
        try:
            from db import connect as db_connect
            conn = db_connect()
            cur = conn.cursor()
            cur.execute("SELECT referred_by FROM users WHERE telegram_id=%s", (message.from_user.id,))
            row = cur.fetchone()
            conn.close()
            # فقط اگه این کاربر جدیدیه (referred_by همین لحظه ست شده) پاداش بده
            # بررسی می‌کنیم آیا قبلاً پاداش ثبت‌نام داده شده
            from db import connect as db_connect2
            conn2 = db_connect2()
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
            if ref_cfg and ref_cfg[0] and ref_cfg[1] > 0:  # is_enabled و reward_on_join
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

@dp.message(F.text == "🏠 خانه")
async def home(message: types.Message, state: FSMContext):
    await state.clear()
    bal = get_balance(message.from_user.id)
    await message.answer(
        f"🏠 صفحه اصلی\n\n💰 موجودی: {bal:,} تومان",
        reply_markup=get_kb(message.from_user.id)
    )


# ================================================================
# BALANCE
# ================================================================

@dp.message(F.text == "💰 موجودی من")
async def balance(message: types.Message):
    bal = get_balance(message.from_user.id)
    await message.answer(f"💰 موجودی شما: {bal:,} تومان")


# ================================================================
# DEPOSIT
# ================================================================

@dp.message(F.text == "➕ شارژ حساب")
async def deposit(message: types.Message, state: FSMContext):
    await state.set_state(DepositStates.waiting_for_amount)
    await message.answer("💰 مبلغ واریزی رو فقط به عدد وارد کن (تومان):")

@dp.message(DepositStates.waiting_for_amount)
async def handle_amount(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ لطفاً فقط عدد وارد کن:")
        return
    amount = int(message.text)
    if amount <= 0:
        await message.answer("❌ مبلغ باید بیشتر از صفر باشه:")
        return
    await state.update_data(amount=amount)
    await state.set_state(DepositStates.waiting_for_receipt)
    await message.answer(f"💰 مبلغ: {amount:,} تومان\n\n📸 حالا تصویر فیش واریزی رو ارسال کن:")

@dp.message(DepositStates.waiting_for_receipt, F.photo)
async def handle_receipt(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    amount = data.get("amount")
    user_id = message.from_user.id
    tx_id = create_transaction(user_id, amount)
    username = message.from_user.username or "ندارد"
    caption = (
        f"💳 درخواست شارژ جدید\n"
        f"👤 User ID: {user_id}\n"
        f"🔖 Username: @{username}\n"
        f"💰 مبلغ: {amount:,} تومان\n"
        f"🔑 TX_ID: {tx_id}"
    )
    await bot.send_photo(
        ADMIN_ID,
        photo=message.photo[-1].file_id,
        caption=caption,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ تایید", callback_data=f"approve:{tx_id}:{user_id}:{amount}"),
            InlineKeyboardButton(text="❌ رد",    callback_data=f"reject:{tx_id}:{user_id}:{amount}")
        ]])
    )
    await state.clear()
    await message.answer("📤 فیش ارسال شد، منتظر تایید ادمین باش.", reply_markup=get_kb(user_id))

@dp.message(DepositStates.waiting_for_receipt)
async def handle_receipt_wrong(message: types.Message):
    await message.answer("❌ لطفاً تصویر فیش رو ارسال کن (نه متن یا فایل دیگه):")


# ================================================================
# FREE TRIAL
# ================================================================

@dp.message(F.text == "🎁 تست رایگان")
async def free_trial_start(message: types.Message, state: FSMContext):
    cfg = get_trial_config()
    is_enabled, duration_days, data_limit_gb, require_referral, min_referrals, default_max_uses = cfg

    if not is_enabled:
        await message.answer("❌ در حال حاضر تست رایگان فعال نیست.")
        return

    user_id = message.from_user.id

    # بررسی شرط رفرال
    if require_referral and min_referrals > 0:
        ref_count = get_referral_count(user_id)
        if ref_count < min_referrals:
            await message.answer(
                f"❌ برای دریافت تست رایگان باید حداقل {min_referrals} نفر رو دعوت کرده باشی.\n"
                f"👥 تعداد زیرمجموعه فعلی: {ref_count}"
            )
            return

    # بررسی شماره ثبت‌شده
    user = get_user(user_id)
    if user and user[3]:  # phone موجوده
        phone = user[3]
        use_count = get_trial_use_count(phone)
        max_uses = get_phone_max_uses(phone)
        if use_count >= max_uses:
            await message.answer(
                f"❌ شماره {phone} قبلاً از تست رایگان استفاده کرده.\n"
                f"(استفاده‌های انجام‌شده: {use_count}/{max_uses})"
            )
            return
        # شماره داره و هنوز می‌تونه تست بگیره
        await _give_free_trial(message, phone, cfg)
    else:
        # باید شماره بده
        await state.set_state(FreeTrial.waiting_phone)
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 اشتراک‌گذاری شماره", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.answer(
            "📱 برای دریافت تست رایگان، شماره موبایلت رو تایید کن:\n\n"
            "روی دکمه زیر کلیک کن یا شماره‌ات رو بفرست:",
            reply_markup=kb
        )

@dp.message(FreeTrial.waiting_phone, F.contact)
async def trial_phone_contact(message: types.Message, state: FSMContext):
    phone = normalize_phone(message.contact.phone_number)
    await state.clear()
    cfg = get_trial_config()
    await _process_trial_phone(message, phone, cfg)

@dp.message(FreeTrial.waiting_phone, F.text)
async def trial_phone_text(message: types.Message, state: FSMContext):
    phone = normalize_phone(message.text)
    if not phone.startswith("09") or len(phone) != 11:
        await message.answer("❌ شماره نامعتبر. مثلاً: 09123456789")
        return
    await state.clear()
    cfg = get_trial_config()
    await _process_trial_phone(message, phone, cfg)

async def _process_trial_phone(message: types.Message, phone: str, cfg):
    user_id = message.from_user.id
    use_count = get_trial_use_count(phone)
    max_uses = get_phone_max_uses(phone)

    if use_count >= max_uses:
        await message.answer(
            f"❌ شماره {phone} قبلاً از تست رایگان استفاده کرده.\n"
            f"(استفاده‌های انجام‌شده: {use_count}/{max_uses})",
            reply_markup=get_kb(user_id)
        )
        return

    # ذخیره شماره در پروفایل کاربر
    set_user_phone(user_id, phone)
    await _give_free_trial(message, phone, cfg)

async def _give_free_trial(message: types.Message, phone: str, cfg):
    user_id = message.from_user.id
    is_enabled, duration_days, data_limit_gb, require_referral, min_referrals, default_max_uses = cfg

    record_trial_use(phone, user_id)

    sep = "─" * 22
    await message.answer(
        f"✅ تست رایگان فعال شد!\n{sep}\n"
        f"📱 شماره: {phone}\n"
        f"⏳ مدت: {duration_days} روز\n"
        f"{format_data(data_limit_gb)}\n{sep}\n"
        f"📩 اطلاعات اتصال به زودی ارسال می‌شه.",
        reply_markup=get_kb(user_id)
    )

    username = message.from_user.username or "ندارد"
    await message.bot.send_message(
        ADMIN_ID,
        f"🧪 تست رایگان جدید!\n"
        f"👤 User: {user_id} (@{username})\n"
        f"📱 شماره: {phone}\n"
        f"⏳ {duration_days} روز | {data_label_short(data_limit_gb)}"
    )


# ================================================================
# REFERRAL
# ================================================================

@dp.message(F.text == "👥 رفرال من")
async def referral_panel(message: types.Message):
    user_id = message.from_user.id
    ref_cfg = get_referral_config()
    is_enabled, reward_join, reward_purchase, reward_pct = ref_cfg

    ref_count, total_reward = get_referral_stats(user_id)
    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

    sep = "─" * 22
    text = (
        f"👥 پنل رفرال شما\n{sep}\n"
        f"🔗 لینک دعوت:\n{ref_link}\n{sep}\n"
        f"👤 تعداد زیرمجموعه: {ref_count} نفر\n"
        f"💰 مجموع پاداش دریافتی: {total_reward:,} تومان\n{sep}\n"
    )

    if is_enabled:
        text += "🎁 پاداش‌های فعلی:\n"
        if reward_join > 0:
            text += f"  • ثبت‌نام هر نفر: {reward_join:,} تومان\n"
        if reward_purchase > 0:
            text += f"  • خرید هر نفر (ثابت): {reward_purchase:,} تومان\n"
        if reward_pct > 0:
            text += f"  • خرید هر نفر (درصدی): {reward_pct}% مبلغ خرید\n"
        if reward_join == 0 and reward_purchase == 0 and reward_pct == 0:
            text += "  • در حال حاضر پاداشی تنظیم نشده.\n"
    else:
        text += "⚠️ سیستم رفرال فعلاً غیرفعاله."

    buttons = [
        [InlineKeyboardButton(text="📋 تاریخچه پاداش‌ها", callback_data="ref:history")],
        [InlineKeyboardButton(text="👥 لیست زیرمجموعه‌ها", callback_data="ref:list")],
    ]
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "ref:history")
async def ref_history(call: types.CallbackQuery):
    rewards = get_referral_rewards_history(call.from_user.id)
    if not rewards:
        await call.message.edit_text("📋 هنوز پاداشی دریافت نکردی.", reply_markup=back_kb("ref:back"))
        await call.answer()
        return
    text = "📋 تاریخچه پاداش‌های رفرال:\n\n"
    for r in rewards:
        referred_id, rtype, amount, created_at = r
        type_label = "ثبت‌نام" if rtype == "join" else "خرید"
        text += f"👤 {referred_id} | {type_label} | +{amount:,} تومان | {created_at.strftime('%Y-%m-%d')}\n"
    await call.message.edit_text(text, reply_markup=back_kb("ref:back"))
    await call.answer()

@dp.callback_query(F.data == "ref:list")
async def ref_list(call: types.CallbackQuery):
    refs = get_referrals(call.from_user.id)
    if not refs:
        await call.message.edit_text("👥 هنوز زیرمجموعه‌ای نداری.", reply_markup=back_kb("ref:back"))
        await call.answer()
        return
    text = f"👥 زیرمجموعه‌های شما ({len(refs)} نفر):\n\n"
    for r in refs:
        uid, bal, joined = r
        text += f"🆔 {uid} | {joined.strftime('%Y-%m-%d')}\n"
    await call.message.edit_text(text, reply_markup=back_kb("ref:back"))
    await call.answer()

@dp.callback_query(F.data == "ref:back")
async def ref_back(call: types.CallbackQuery):
    await call.message.delete()
    await call.answer()


# ================================================================
# SHOP
# ================================================================

@dp.message(F.text == "🛒 خرید سرویس")
async def shop_start(message: types.Message):
    categories = get_all_categories(active_only=True)
    if not categories:
        await message.answer("❌ در حال حاضر دسته‌بندی‌ای وجود نداره.")
        return
    bal = get_balance(message.from_user.id)
    await message.answer(
        f"🛒 فروشگاه\n💰 موجودی شما: {bal:,} تومان\n\nیه دسته‌بندی انتخاب کن:",
        reply_markup=categories_kb(categories)
    )

@dp.callback_query(F.data == "shop:back")
async def shop_back_to_categories(call: types.CallbackQuery):
    categories = get_all_categories(active_only=True)
    bal = get_balance(call.from_user.id)
    await call.message.edit_text(
        f"🛒 فروشگاه\n💰 موجودی شما: {bal:,} تومان\n\nیه دسته‌بندی انتخاب کن:",
        reply_markup=categories_kb(categories)
    )
    await call.answer()

@dp.callback_query(F.data.startswith("cat:"))
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

@dp.callback_query(F.data.startswith("buy:"))
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
    from db import connect as db_connect
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

@dp.callback_query(F.data.startswith("discount:"))
async def ask_discount_code(call: types.CallbackQuery, state: FSMContext):
    _, service_id, cat_id = call.data.split(":")
    await state.set_state(ApplyDiscount.waiting_for_code)
    await state.update_data(service_id=int(service_id), cat_id=int(cat_id))
    await call.message.answer("🎁 کد تخفیف خودت رو وارد کن:")
    await call.answer()

@dp.message(ApplyDiscount.waiting_for_code)
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

@dp.callback_query(F.data.startswith("confirm_discounted:"))
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

    # پاداش رفرال برای خرید
    await _handle_purchase_referral_reward(bot, user_id, final_price)

    sep = "─" * 22
    await call.message.edit_text(
        f"✅ خرید موفق!\n{sep}\n"
        f"📦 سرویس:        {name}\n"
        f"⏳ مدت:            {days} روز\n"
        f"{format_data(data_gb)}\n{sep}\n"
        f"💰 پرداخت شد:  {final_price:,} تومان\n"
        f"👛 موجودی:       {new_bal:,} تومان\n{sep}\n"
        f"🔑 شماره سفارش: #{purchase_id}"
    )
    username = call.from_user.username or "ندارد"
    await bot.send_message(
        ADMIN_ID,
        f"🛍 خرید جدید (با تخفیف)!\n"
        f"👤 User: {user_id} (@{username})\n"
        f"📦 سرویس: {name}\n"
        f"💰 مبلغ پرداختی: {final_price:,} تومان\n"
        f"🔑 سفارش: #{purchase_id}"
    )
    await call.answer("✅ خرید موفق!")

@dp.callback_query(F.data.startswith("confirm_buy:"))
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

    # پاداش رفرال برای خرید
    await _handle_purchase_referral_reward(bot, user_id, price)

    sep = "─" * 22
    await call.message.edit_text(
        f"✅ خرید موفق!\n{sep}\n"
        f"📦 سرویس:        {name}\n"
        f"⏳ مدت:            {days} روز\n"
        f"{format_data(data_gb)}\n{sep}\n"
        f"💰 پرداخت شد:  {price:,} تومان\n"
        f"👛 موجودی:       {new_bal:,} تومان\n{sep}\n"
        f"🔑 شماره سفارش: #{purchase_id}"
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
    await call.answer("✅ خرید موفق!")

async def _handle_purchase_referral_reward(bot: Bot, buyer_id: int, amount_paid: int):
    """اگه خریدار زیرمجموعه کسیه، به دعوت‌کننده پاداش بده"""
    ref_cfg = get_referral_config()
    if not ref_cfg or not ref_cfg[0]:  # is_enabled
        return

    user = get_user(buyer_id)
    if not user or not user[2]:  # referred_by
        return

    referrer_id = user[2]
    is_enabled, reward_join, reward_purchase, reward_pct = ref_cfg

    reward = 0
    if reward_purchase > 0:
        reward += reward_purchase
    if reward_pct > 0:
        reward += int(amount_paid * float(reward_pct) / 100)

    if reward > 0:
        give_referral_reward(referrer_id, buyer_id, "purchase", reward)
        try:
            await bot.send_message(
                referrer_id,
                f"🎉 یکی از زیرمجموعه‌هات خرید کرد!\n"
                f"💚 +{reward:,} تومان پاداش به حسابت اضافه شد."
            )
        except Exception:
            pass


# ================================================================
# PURCHASE HISTORY
# ================================================================

@dp.message(F.text == "📋 خریدهای من")
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


# ================================================================
# APPROVE / REJECT DEPOSIT
# ================================================================

@dp.callback_query(F.data.startswith("approve:"))
async def approve(call: types.CallbackQuery, bot: Bot):
    if call.from_user.id != ADMIN_ID:
        await call.answer("❌ دسترسی ندارید", show_alert=True)
        return
    _, tx_id, user_id, amount = call.data.split(":")
    tx_id, user_id, amount = int(tx_id), int(user_id), int(amount)
    approve_transaction(tx_id, user_id, amount)
    new_bal = get_balance(user_id)
    await bot.send_message(user_id,
        f"✅ شارژ تایید شد\n💰 +{amount:,} تومان اضافه شد\n👛 موجودی: {new_bal:,} تومان")
    await call.message.edit_caption(call.message.caption + "\n\n✅ تایید شد")
    await call.answer("✅ تایید شد")

@dp.callback_query(F.data.startswith("reject:"))
async def reject(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer("❌ دسترسی ندارید", show_alert=True)
        return
    _, tx_id, user_id, amount = call.data.split(":")
    await state.set_state(RejectReason.waiting_for_reason)
    await state.update_data(
        tx_id=int(tx_id), user_id=int(user_id), amount=int(amount),
        msg_id=call.message.message_id, orig_caption=call.message.caption or ""
    )
    await call.message.answer(
        f"✏️ دلیل رد کردن شارژ {int(amount):,} تومان (کاربر {user_id}) رو بنویس:\n"
        f"(یا /skip برای ارسال بدون دلیل)"
    )
    await call.answer()

@dp.message(RejectReason.waiting_for_reason)
async def reject_with_reason(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    reason = None if message.text == "/skip" else message.text.strip()
    reject_transaction(data["tx_id"])
    user_msg = f"❌ درخواست شارژ شما رد شد\n💰 مبلغ: {data['amount']:,} تومان"
    if reason:
        user_msg += f"\n\n📝 دلیل: {reason}"
    await bot.send_message(data["user_id"], user_msg)
    try:
        new_cap = data["orig_caption"] + "\n\n❌ رد شد"
        if reason:
            new_cap += f"\n📝 دلیل: {reason}"
        await bot.edit_message_caption(chat_id=ADMIN_ID, message_id=data["msg_id"], caption=new_cap)
    except Exception:
        pass
    await state.clear()
    await message.answer("✅ رد شد و به کاربر اطلاع داده شد.", reply_markup=get_kb(message.from_user.id))


# ================================================================
# ADMIN PANEL
# ================================================================

@dp.message(F.text == "🛠 پنل ادمین")
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("🛠 پنل مدیریت:", reply_markup=admin_panel_kb())

@dp.callback_query(F.data == "admin:back")
async def admin_back(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text("🛠 پنل مدیریت:", reply_markup=admin_panel_kb())
    await call.answer()

@dp.callback_query(F.data == "admin:users")
async def admin_users(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    users = get_all_users()
    text = f"👥 تعداد کاربران: {len(users)}\n\n"
    for u in users:
        text += f"🆔 {u[0]} | 💰 {u[1]:,} تومان\n"
    await call.message.edit_text(text, reply_markup=back_kb("admin:back"))
    await call.answer()

@dp.callback_query(F.data == "admin:pending")
async def admin_pending(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
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

@dp.callback_query(F.data == "admin:purchases")
async def admin_purchases(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
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

# ---- دسته‌بندی‌ها ----
@dp.callback_query(F.data == "admin:categories")
async def admin_categories(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
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

@dp.callback_query(F.data.startswith("admin:toggle_cat:"))
async def admin_toggle_cat(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    cat_id = int(call.data.split(":")[2])
    new_status = toggle_category(cat_id)
    await call.answer("✅ فعال شد" if new_status else "❌ غیرفعال شد", show_alert=True)
    cats = get_all_categories(active_only=False)
    await call.message.edit_text("🗂 دسته‌بندی‌ها:\n✅=فعال | ❌=غیرفعال", reply_markup=admin_categories_kb(cats))

@dp.callback_query(F.data.startswith("admin:del_cat:"))
async def admin_del_cat(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    cat_id = int(call.data.split(":")[2])
    delete_category(cat_id)
    await call.answer("🗑 دسته غیرفعال شد", show_alert=True)
    cats = get_all_categories(active_only=False)
    if cats:
        await call.message.edit_text("🗂 دسته‌بندی‌ها:", reply_markup=admin_categories_kb(cats))
    else:
        await call.message.edit_text("🗂 هیچ دسته‌ای باقی نمونده.", reply_markup=back_kb("admin:back"))

@dp.callback_query(F.data == "admin:add_category")
async def admin_add_cat_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminAddCategory.name)
    await call.message.answer("🗂 نام دسته‌بندی رو وارد کن:")
    await call.answer()

@dp.message(AdminAddCategory.name)
async def admin_add_cat_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminAddCategory.emoji)
    await message.answer("😀 ایموجی دسته رو بفرست (مثلاً 🌍 یا 🔥)\nیا /skip برای پیش‌فرض 📦:")

@dp.message(AdminAddCategory.emoji)
async def admin_add_cat_emoji(message: types.Message, state: FSMContext):
    emoji = "📦" if message.text == "/skip" else message.text.strip()
    data = await state.get_data()
    cid = add_category(data["name"], emoji)
    await state.clear()
    await message.answer(
        f"✅ دسته‌بندی اضافه شد!\n{emoji} {data['name']}\n🔑 ID: {cid}",
        reply_markup=get_kb(message.from_user.id)
    )

# ---- مدیریت سرویس‌ها ----
@dp.callback_query(F.data == "admin:services")
async def admin_services_list(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    services = get_all_services(active_only=False)
    if not services:
        await call.message.edit_text("📦 هیچ سرویسی ثبت نشده.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ افزودن سرویس", callback_data="admin:add_service")],
            [InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:back")]
        ]))
    else:
        await call.message.edit_text("📦 سرویس‌ها (برای ویرایش/حذف کلیک کن):\n✅=فعال | ❌=غیرفعال", reply_markup=admin_services_kb(services))
    await call.answer()

@dp.callback_query(F.data.startswith("admin:svc_detail:"))
async def admin_svc_detail(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
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

@dp.callback_query(F.data.startswith("admin:toggle:"))
async def admin_toggle_service(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
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

@dp.callback_query(F.data.startswith("admin:hard_del:"))
async def admin_hard_del_service(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
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
@dp.callback_query(F.data.startswith("admin:edit_svc:"))
async def admin_edit_svc(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    sid = int(call.data.split(":")[2])
    await state.set_state(AdminEditService.choosing_field)
    await state.update_data(editing_sid=sid)
    await call.message.edit_text("✏️ کدوم فیلد رو می‌خوای ویرایش کنی؟", reply_markup=admin_edit_svc_fields_kb(sid))
    await call.answer()

@dp.callback_query(F.data.startswith("admin:editfield:"), AdminEditService.choosing_field)
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

@dp.message(AdminEditService.entering_value)
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
    await message.answer(f"✅ سرویس آپدیت شد!", reply_markup=get_kb(message.from_user.id))

# ---- افزودن سرویس ----
@dp.callback_query(F.data == "admin:add_service")
async def admin_add_service_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    cats = get_all_categories(active_only=True)
    buttons = [[InlineKeyboardButton(text=f"{c[2]} {c[1]}", callback_data=f"admin:svc_cat:{c[0]}")] for c in cats]
    buttons.append([InlineKeyboardButton(text="بدون دسته", callback_data="admin:svc_cat:0")])
    await state.set_state(AdminAddService.category)
    await call.message.answer("🗂 دسته‌بندی سرویس رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await call.answer()

@dp.callback_query(F.data.startswith("admin:svc_cat:"), AdminAddService.category)
async def admin_add_svc_cat(call: types.CallbackQuery, state: FSMContext):
    cat_id = call.data.split(":")[2]
    await state.update_data(category_id=int(cat_id) if cat_id != "0" else None)
    await state.set_state(AdminAddService.name)
    await call.message.answer("📦 نام سرویس رو وارد کن:")
    await call.answer()

@dp.message(AdminAddService.name)
async def admin_add_svc_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminAddService.description)
    await message.answer("📝 توضیحات رو وارد کن (یا /skip):")

@dp.message(AdminAddService.description)
async def admin_add_svc_desc(message: types.Message, state: FSMContext):
    desc = "" if message.text == "/skip" else message.text.strip()
    await state.update_data(description=desc)
    await state.set_state(AdminAddService.price)
    await message.answer("💰 قیمت رو به تومان وارد کن:")

@dp.message(AdminAddService.price)
async def admin_add_svc_price(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ فقط عدد:")
        return
    await state.update_data(price=int(message.text))
    await state.set_state(AdminAddService.duration)
    await message.answer("⏳ مدت رو به روز وارد کن:")

@dp.message(AdminAddService.duration)
async def admin_add_svc_duration(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ فقط عدد:")
        return
    await state.update_data(duration=int(message.text))
    await state.set_state(AdminAddService.data_limit)
    await message.answer("📶 حجم رو به گیگابایت وارد کن:\n• 0 = نامحدود\n• مثال: 30 یا 30.5 یا 0.1")

@dp.message(AdminAddService.data_limit)
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

# ---- کدهای تخفیف ----
@dp.callback_query(F.data == "admin:discounts")
async def admin_discounts(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    codes = get_all_discount_codes()
    text = "🎁 کدهای تخفیف:\n(برای حذف روی کد کلیک کن)\n\n"
    if not codes:
        text += "هیچ کدی ثبت نشده."
    await call.message.edit_text(text, reply_markup=admin_discounts_kb(codes))
    await call.answer()

@dp.callback_query(F.data == "admin:add_discount")
async def admin_add_discount_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminDiscountCode.code)
    await call.message.answer("🎁 کد تخفیف رو وارد کن (مثلاً GIFT20):")
    await call.answer()

@dp.message(AdminDiscountCode.code)
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

@dp.callback_query(F.data.startswith("dtype:"), AdminDiscountCode.discount_type)
async def admin_discount_type(call: types.CallbackQuery, state: FSMContext):
    dtype = call.data.split(":")[1]
    await state.update_data(discount_type=dtype)
    await state.set_state(AdminDiscountCode.discount_value)
    if dtype == "percent":
        await call.message.answer("📊 مقدار تخفیف رو به درصد وارد کن (مثلاً 20 برای 20%):")
    else:
        await call.message.answer("💰 مقدار تخفیف رو به تومان وارد کن:")
    await call.answer()

@dp.message(AdminDiscountCode.discount_value)
async def admin_discount_value(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ فقط عدد:")
        return
    await state.update_data(discount_value=int(message.text))
    await state.set_state(AdminDiscountCode.max_uses)
    await message.answer("🔢 حداکثر تعداد استفاده رو وارد کن:\n(0 برای نامحدود)")

@dp.message(AdminDiscountCode.max_uses)
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

@dp.callback_query(F.data.startswith("admin:del_discount:"))
async def admin_del_discount(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    dc_id = int(call.data.split(":")[2])
    delete_discount_code(dc_id)
    await call.answer("🗑 کد حذف شد", show_alert=True)
    codes = get_all_discount_codes()
    text = "🎁 کدهای تخفیف:\n(برای حذف روی کد کلیک کن)\n\n"
    if not codes:
        text += "هیچ کدی ثبت نشده."
    await call.message.edit_text(text, reply_markup=admin_discounts_kb(codes))

# ---- تنظیم موجودی ----
@dp.callback_query(F.data == "admin:edit_balance")
async def admin_edit_balance_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminEditBalance.user_id)
    await call.message.answer("👤 آی‌دی کاربر رو وارد کن:")
    await call.answer()

@dp.message(AdminEditBalance.user_id)
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

@dp.message(AdminEditBalance.amount)
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
# ADMIN: FREE TRIAL MANAGEMENT
# ================================================================

@dp.callback_query(F.data == "admin:trial_menu")
async def admin_trial_menu(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text("🧪 مدیریت تست رایگان:", reply_markup=admin_trial_menu_kb())
    await call.answer()

@dp.callback_query(F.data == "admin:trial_toggle")
async def admin_trial_toggle(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    cfg = get_trial_config()
    new_val = not cfg[0]
    update_trial_config(is_enabled=new_val)
    await call.answer("✅ فعال شد" if new_val else "❌ غیرفعال شد", show_alert=True)
    await call.message.edit_text("🧪 مدیریت تست رایگان:", reply_markup=admin_trial_menu_kb())

@dp.callback_query(F.data == "admin:trial_toggle_ref")
async def admin_trial_toggle_ref(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    cfg = get_trial_config()
    new_val = not cfg[3]
    update_trial_config(require_referral=new_val)
    await call.answer("✅ نیاز به رفرال فعال شد" if new_val else "❌ نیاز به رفرال حذف شد", show_alert=True)
    await call.message.edit_text("🧪 مدیریت تست رایگان:", reply_markup=admin_trial_menu_kb())

@dp.callback_query(F.data.startswith("admin:trial_set:"))
async def admin_trial_set_field(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
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

@dp.message(AdminTrialConfig.entering_value)
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

# ---- مدیریت شماره‌ها ----
@dp.callback_query(F.data == "admin:trial_phones")
async def admin_trial_phones(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
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

@dp.callback_query(F.data == "admin:trial_add_phone")
async def admin_trial_add_phone_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminPhoneOverride.phone)
    await call.message.answer("📱 شماره تلفن رو وارد کن (مثلاً 09123456789):")
    await call.answer()

@dp.message(AdminPhoneOverride.phone)
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
    await message.answer(
        f"🔢 حداکثر تعداد تست برای {phone} رو وارد کن:"
    )

@dp.message(AdminPhoneOverride.max_uses)
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

@dp.callback_query(F.data == "admin:trial_del_phone")
async def admin_trial_del_phone_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminPhoneOverride.phone)
    await state.update_data(override_mode="delete")
    await call.message.answer("📱 شماره‌ای که می‌خوای override ش رو حذف کنی وارد کن:")
    await call.answer()

@dp.callback_query(F.data == "admin:trial_uses")
async def admin_trial_uses(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
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
# ADMIN: REFERRAL MANAGEMENT
# ================================================================

@dp.callback_query(F.data == "admin:referral_menu")
async def admin_referral_menu(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text("🔗 تنظیمات سیستم رفرال:", reply_markup=admin_referral_menu_kb())
    await call.answer()

@dp.callback_query(F.data == "admin:ref_toggle")
async def admin_ref_toggle(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    cfg = get_referral_config()
    new_val = not cfg[0]
    update_referral_config(is_enabled=new_val)
    await call.answer("✅ رفرال فعال شد" if new_val else "❌ رفرال غیرفعال شد", show_alert=True)
    await call.message.edit_text("🔗 تنظیمات سیستم رفرال:", reply_markup=admin_referral_menu_kb())

@dp.callback_query(F.data.startswith("admin:ref_set:"))
async def admin_ref_set_field(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    field = call.data.split(":")[2]
    await state.set_state(AdminReferralConfig.entering_value)
    await state.update_data(ref_field=field)
    prompts = {
        "reward_on_join":          "🎁 پاداش ثبت‌نام رو به تومان وارد کن (0 = بدون پاداش):",
        "reward_on_purchase":      "🛍 پاداش ثابت خرید رو به تومان وارد کن (0 = بدون پاداش):",
        "reward_purchase_percent": "📊 درصد پاداش خرید رو وارد کن (0 = بدون پاداش، مثلاً 5 برای 5%):",
    }
    await call.message.answer(prompts.get(field, "مقدار جدید رو وارد کن:"))
    await call.answer()

@dp.message(AdminReferralConfig.entering_value)
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

@dp.callback_query(F.data == "admin:ref_history")
async def admin_ref_history(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    from db import connect as db_connect
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
# MAIN
# ================================================================

async def main():
    init_db()
    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())