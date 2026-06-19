from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from config import ADMIN_ID
from db import get_trial_config, get_referral_config


def get_kb(user_id):
    base = [
        [KeyboardButton(text="🏠 خانه"), KeyboardButton(text="📊 وضعیت سرویس‌ها")],
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
    from utils import data_label_short
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
    from utils import data_label_short
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
    from utils import data_label_short
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
    is_enabled, reward_join, first_purchase_reward, reward_purchase, reward_pct = cfg
    status = "✅ فعال" if is_enabled else "❌ غیرفعال"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"وضعیت: {status}", callback_data="admin:ref_toggle")],
        [InlineKeyboardButton(text=f"🎁 پاداش ثبت‌نام: {reward_join:,} تومان", callback_data="admin:ref_set:reward_on_join")],
        [InlineKeyboardButton(text=f"🥇 پاداش اولین خرید: {first_purchase_reward:,} تومان", callback_data="admin:ref_set:first_purchase_reward")],
        [InlineKeyboardButton(text=f"🛍 پاداش خریدهای بعدی (ثابت): {reward_purchase:,} تومان", callback_data="admin:ref_set:reward_on_purchase")],
        [InlineKeyboardButton(text=f"📊 پاداش خریدهای بعدی (درصد): {reward_pct}%", callback_data="admin:ref_set:reward_purchase_percent")],
        [InlineKeyboardButton(text="📋 تاریخچه پاداش‌ها", callback_data="admin:ref_history")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:back")],
    ])