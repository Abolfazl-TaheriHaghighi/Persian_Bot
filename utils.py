import asyncio
import re
from config import ADMIN_IDS


async def run_db(fn, *args, **kwargs):
    """اجرای توابع دیتابیس در thread جداگانه تا event loop بلاک نشه"""
    return await asyncio.to_thread(fn, *args, **kwargs)


async def notify_admins(bot, text: str, **kwargs):
    """ارسال پیام به همه ادمین‌ها"""
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, **kwargs)
        except Exception:
            pass


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


# ================== CLIENT NAMING (برند + شمارنده) ==================

_MAX_PREFIX_LEN = 20


def sanitize_naming_prefix(raw: str) -> str:
    """
    فقط حروف انگلیسی، عدد، _ و - رو نگه می‌داره؛ فاصله و حروف فارسی/غیرانگلیسی حذف می‌شن
    (چون این رشته داخل email کلاینت روی پنل VPN و توی URL ساب‌اسکریپشن استفاده می‌شه)
    اگه بعد از پاکسازی چیزی باقی نمونه یا خیلی طولانی باشه، رشته‌ی خالی برمی‌گردونه (یعنی نامعتبر)
    """
    cleaned = raw.strip().replace(" ", "")
    cleaned = re.sub(r"[^A-Za-z0-9_\-]", "", cleaned)
    if not cleaned or len(cleaned) > _MAX_PREFIX_LEN:
        return ""
    return cleaned


async def generate_client_email() -> str:
    """
    ساخت ایمیل یکتای کلاینت برای پنل VPN.
    اگه ادمین از پنل ادمین یک پیشوند تنظیم کرده باشه (مثلاً PersianShield)،
    خروجی به شکل PersianShield1, PersianShield2, ... خواهد بود.
    در غیر این صورت به فرمت قدیمی (بر پایه timestamp) fallback می‌کنه.
    این تابع تنها نقطه‌ی ساخت email است — همه‌ی مسیرهای ساخت اکانت (خرید عادی،
    تست رایگان، پلن دلخواه) باید از همین استفاده کنن تا شمارنده یکپارچه بمونه.
    """
    from db import get_next_client_email
    return await run_db(get_next_client_email)