"""
helper برای چک کردن دسترسی پرو
استفاده:
    from pro_guard import require_pro, check_free_limits
"""
from aiogram import types
from config import BOT_TOKEN
from license import is_pro as _is_pro
from db import get_category_count, get_service_count

# حدود رایگان
FREE_MAX_CATEGORIES = 1
FREE_MAX_SERVICES = 2


def is_pro() -> bool:
    return _is_pro(BOT_TOKEN)


async def require_pro(message_or_call, feature_name: str = "") -> bool:
    """
    اگه پرو نبود پیام بده و False برگردون
    استفاده:
        if not await require_pro(call, "رفرال"):
            return
    """
    if is_pro():
        return True

    text = (
        f"🔒 این قابلیت فقط در نسخه پرو در دسترسه.\n"
        f"{'(' + feature_name + ')' if feature_name else ''}\n\n"
        f"برای فعال‌سازی لایسنس پرو، از پنل ادمین اقدام کن."
    )

    if isinstance(message_or_call, types.CallbackQuery):
        await message_or_call.answer(text, show_alert=True)
    else:
        await message_or_call.answer(text)
    return False


async def check_free_category_limit(message_or_call) -> bool:
    """چک حد رایگان دسته‌بندی"""
    if is_pro():
        return True
    count = get_category_count()
    if count >= FREE_MAX_CATEGORIES:
        text = (
            f"🔒 در نسخه رایگان فقط {FREE_MAX_CATEGORIES} دسته‌بندی مجازه.\n"
            f"برای افزودن بیشتر، لایسنس پرو فعال کن."
        )
        if isinstance(message_or_call, types.CallbackQuery):
            await message_or_call.answer(text, show_alert=True)
        else:
            await message_or_call.answer(text)
        return False
    return True


async def check_free_service_limit(message_or_call) -> bool:
    """چک حد رایگان سرویس"""
    if is_pro():
        return True
    count = get_service_count()
    if count >= FREE_MAX_SERVICES:
        text = (
            f"🔒 در نسخه رایگان فقط {FREE_MAX_SERVICES} سرویس مجازه.\n"
            f"برای افزودن بیشتر، لایسنس پرو فعال کن."
        )
        if isinstance(message_or_call, types.CallbackQuery):
            await message_or_call.answer(text, show_alert=True)
        else:
            await message_or_call.answer(text)
        return False
    return True