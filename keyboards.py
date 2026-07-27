from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import ADMIN_ID, is_admin
from utils import data_label_short


def home_menu_kb(user_id) -> InlineKeyboardMarkup:
    """
    منوی اصلی شیشه‌ای — جایگزین کیبورد ثابت پایین صفحه (get_kb قدیمی).
    همه‌ی گزینه‌ها inline هستن تا چت شلوغ نشه و همه‌چیز با edit_text پیش بره.
    """
    buttons = [
        [InlineKeyboardButton(text="🛒 خرید سرویس", callback_data="menu:shop")],
        [InlineKeyboardButton(text="🎛 مدیریت سرویس‌ها", callback_data="menu:status"),
         InlineKeyboardButton(text="➕ شارژ حساب", callback_data="menu:deposit")],
        [InlineKeyboardButton(text="👤 پروفایل من", callback_data="menu:profile")],
        [InlineKeyboardButton(text="💰 کسب درآمد", callback_data="menu:referral"),
         InlineKeyboardButton(text="🎁 تست رایگان", callback_data="menu:trial")],
        [InlineKeyboardButton(text="🤝 درخواست همکاری", callback_data="menu:partner"),
         InlineKeyboardButton(text="📞 پشتیبانی", callback_data="menu:support")],
    ]
    if is_admin(user_id):
        buttons.append([InlineKeyboardButton(text="🛠 پنل ادمین", callback_data="menu:admin")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def home_button_kb() -> InlineKeyboardMarkup:
    """
    دکمه‌ی تکی «بازگشت به خانه» — جایگزین عمومی get_kb() قدیمی، برای پایان هر
    عملیات (خرید، شارژ، تست رایگان و...). با تپ روی این، render_home() صدا زده
    می‌شه و همون پیام به صفحه‌ی خانه‌ی کامل تبدیل می‌شه.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 بازگشت به خانه", callback_data="menu:home")]
    ])


def cancel_kb() -> InlineKeyboardMarkup:
    """
    دکمه‌ی «انصراف» برای وسط فلوهای چندمرحله‌ای (FSM) مثل شارژ حساب — کاربر
    هر لحظه که خواست می‌تونه بی‌خیال بشه، بدون نیاز به تایپ دستی /start.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ انصراف و بازگشت به خانه", callback_data="cancel:fsm")]
    ])


def back_kb(cb: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 برگشت", callback_data=cb)]
    ])


def admin_panel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 لیست کاربران", callback_data="admin:users"),
         InlineKeyboardButton(text="🗂 مدیریت دسته‌بندی‌ها", callback_data="admin:categories")],
        [InlineKeyboardButton(text="📦 مدیریت سرویس‌ها", callback_data="admin:services"),
         InlineKeyboardButton(text="🎁 کدهای تخفیف", callback_data="admin:discounts")],
        [InlineKeyboardButton(text="⏳ تراکنش‌های در انتظار تایید", callback_data="admin:pending"),
         InlineKeyboardButton(text="🛍 تاریخچه خریدها", callback_data="admin:purchases")],
        [InlineKeyboardButton(text="➕ افزودن دسته‌بندی", callback_data="admin:add_category"),
         InlineKeyboardButton(text="➕ افزودن سرویس", callback_data="admin:add_service")],
        [InlineKeyboardButton(text="💸 تنظیم موجودی کاربر", callback_data="admin:edit_balance"),
         InlineKeyboardButton(text="🧪 مدیریت تست رایگان", callback_data="admin:trial_menu")],
        [InlineKeyboardButton(text="🔗 تنظیمات رفرال", callback_data="admin:referral_menu"),
         InlineKeyboardButton(text="📢 کانال‌های اجباری", callback_data="admin:channels")],
        [InlineKeyboardButton(text="⚙️ تنظیمات پنل VPN", callback_data="admin:panel_config"),
         InlineKeyboardButton(text="🤝 مدیریت همکاران", callback_data="admin:partners")],
        [InlineKeyboardButton(text="👁 دسترسی دسته‌بندی‌ها", callback_data="admin:cat_visibility"),
         InlineKeyboardButton(text="📣 ارسال پیام گروهی", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="🎛 پلن‌های دلخواه", callback_data="admin:custom_plans"),
         InlineKeyboardButton(text="🏷 نام‌گذاری کلاینت‌ها", callback_data="admin:naming")],
        [InlineKeyboardButton(text="💾 پشتیبان‌گیری از دیتابیس", callback_data="admin:backup"),
         InlineKeyboardButton(text="💳 مدیریت روش‌های پرداخت", callback_data="admin:payment_methods")],
        [InlineKeyboardButton(text="🎨 شخصی‌سازی متن‌ها", callback_data="admin:brand")],
        [InlineKeyboardButton(text="🔄 تمدید دستی کلاینت", callback_data="admin:renew_manual"),
         InlineKeyboardButton(text="📞 مدیریت پشتیبانی", callback_data="admin:support")],
        [InlineKeyboardButton(text="🏠 بازگشت به خانه", callback_data="menu:home")],
    ])


def categories_kb(categories):
    buttons = []
    for c in categories:
        cid, name, emoji = c[0], c[1], c[2]
        is_custom = c[3] if len(c) > 3 else False
        cb = f"customcat:{cid}" if is_custom else f"cat:{cid}"
        buttons.append([InlineKeyboardButton(text=f"{emoji} {name}", callback_data=cb)])
    buttons.append([InlineKeyboardButton(text="🏠 بازگشت به خانه", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def custom_groups_kb(groups, cat_id):
    """لیست زیرگروه‌های پلن دلخواه"""
    buttons = [
        [InlineKeyboardButton(text=f"{g[2]} {g[1]}", callback_data=f"customgrp:{g[0]}")]
        for g in groups
    ]
    buttons.append([InlineKeyboardButton(text="🔙 برگشت به دسته‌ها", callback_data="shop:back")])
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
        cid, name, emoji, is_active, sort_order, is_custom = c
        st = "✅" if is_active else "❌"
        # به جای دکمه‌ی حذف مستقیم، کاربر را به صفحه‌ی جزئیات دسته‌بندی هدایت می‌کنیم
        buttons.append([
            InlineKeyboardButton(text=f"{st} {emoji} {name}", callback_data=f"admin:cat_detail:{cid}")
        ])
    buttons.append([InlineKeyboardButton(text="➕ افزودن دسته جدید", callback_data="admin:add_category")])
    buttons.append([InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_cat_detail_kb(cat_id, is_active):
    toggle_text = "❌ غیرفعال کردن" if is_active else "✅ فعال کردن"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ تغییر نام", callback_data=f"admin:edit_cat:{cat_id}:name"),
         InlineKeyboardButton(text="🖥 تغییر پنل", callback_data=f"admin:edit_cat:{cat_id}:panel")],
        [InlineKeyboardButton(text=toggle_text, callback_data=f"admin:toggle_cat:{cat_id}"),
         InlineKeyboardButton(text="🗑 حذف دسته", callback_data=f"admin:del_cat:{cat_id}")],
        [InlineKeyboardButton(text="🔙 برگشت به لیست دسته‌ها", callback_data="admin:categories")],
    ])


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
        [InlineKeyboardButton(text="✏️ ویرایش سرویس", callback_data=f"admin:edit_svc:{sid}")],
        [InlineKeyboardButton(text=toggle_text, callback_data=f"admin:toggle:{sid}")],
        [InlineKeyboardButton(text="🗑 حذف کامل", callback_data=f"admin:hard_del:{sid}")],
        [InlineKeyboardButton(text="🔙 برگشت به لیست", callback_data="admin:services")],
    ])


def admin_edit_svc_fields_kb(sid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 نام", callback_data=f"admin:editfield:{sid}:name")],
        [InlineKeyboardButton(text="📝 توضیحات", callback_data=f"admin:editfield:{sid}:description")],
        [InlineKeyboardButton(text="💰 قیمت", callback_data=f"admin:editfield:{sid}:price")],
        [InlineKeyboardButton(text="⏳ مدت (روز)", callback_data=f"admin:editfield:{sid}:duration")],
        [InlineKeyboardButton(text="📶 حجم (GB)", callback_data=f"admin:editfield:{sid}:data_limit")],
        [InlineKeyboardButton(text="🗂 دسته‌بندی", callback_data=f"admin:editfield:{sid}:category")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data=f"admin:svc_detail:{sid}")],
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
    buttons.append([InlineKeyboardButton(text="➕ کد جدید", callback_data="admin:add_discount")])
    buttons.append([InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_trial_menu_kb(cfg):
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


def admin_referral_menu_kb(cfg):
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


def admin_backup_kb(cfg):
    """کیبورد منوی پشتیبان‌گیری از دیتابیس"""
    bot_token, admin_id, interval_hours, last_backup_at = cfg if cfg else (None, None, 0, None)
    token_label = "✅ تنظیم شده" if bot_token else "❌ تنظیم نشده"
    admin_label = str(admin_id) if admin_id else "❌ تنظیم نشده"
    interval_label = f"هر {interval_hours} ساعت" if interval_hours and interval_hours > 0 else "❌ غیرفعال"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔑 توکن ربات بکاپ: {token_label}", callback_data="admin:backup_set_token")],
        [InlineKeyboardButton(text=f"🆔 آیدی گیرنده: {admin_label}", callback_data="admin:backup_set_admin")],
        [InlineKeyboardButton(text="⚡️ بکاپ‌گیری لحظه‌ای", callback_data="admin:backup_now")],
        [InlineKeyboardButton(text=f"⏰ بکاپ خودکار: {interval_label}", callback_data="admin:backup_set_interval")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:back")],
    ])


def admin_naming_kb(cfg):
    """
    کیبورد مدیریت نام‌گذاری خودکار کلاینت‌ها (برند + شمارنده + گروه پیش‌فرض).
    توجه: دکمه‌ی ریست شمارنده عمداً بدون تایید اضافه (مثل بقیه‌ی دکمه‌های ادمین این پروژه)
    است؛ هشدار خطرش داخل متن منو نوشته می‌شه.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ تغییر پیشوند ایمیل", callback_data="admin:naming_set_prefix")],
        [InlineKeyboardButton(text="🔄 ریست شمارنده به صفر", callback_data="admin:naming_reset")],
        [InlineKeyboardButton(text="🏷 تنظیم گروه پیش‌فرض کاربران", callback_data="admin:naming_set_group")],
        [InlineKeyboardButton(text="🔙 برگشت", callback_data="admin:back")],
    ])


def renew_confirm_kb(purchase_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تایید و تمدید", callback_data=f"renew_confirm:{purchase_id}")],
        [InlineKeyboardButton(text="❌ انصراف", callback_data="menu:status")],
    ])