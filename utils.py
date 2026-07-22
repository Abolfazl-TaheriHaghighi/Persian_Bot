import asyncio
import re
from aiogram import types
from aiogram.fsm.context import FSMContext
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


async def generate_client_email(user_id: int | None = None) -> str:
    """
    ساخت ایمیل یکتای کلاینت برای پنل VPN.
    ترتیب اولویت: پیشوند اختصاصی همکار (اگه user_id مربوط به همکاری با نام‌گذاری
    خودش باشه) > پیشوند سراسری (تنظیم‌شده توسط ادمین) > فرمت قدیمی (timestamp).
    این تابع تنها نقطه‌ی ساخت email است — همه‌ی مسیرهای ساخت اکانت (خرید عادی،
    تست رایگان، پلن دلخواه) باید از همین استفاده کنن تا شمارنده‌ها یکپارچه بمونن.
    """
    from db import get_next_client_email
    return await run_db(get_next_client_email, user_id)


async def prepare_new_client(user_id: int) -> tuple[str, str]:
    """
    یک‌جا هرچی برای ساخت کلاینت جدید لازمه رو آماده می‌کنه: (email, group).
    email بر اساس نام‌گذاری اختصاصی همکار (اگه تنظیم شده باشه) یا سراسری ساخته می‌شه.
    group بر اساس نوع کاربر تعیین می‌شه:
      - ادمین → "Admin"
      - همکار با برچسب اختصاصی → همون برچسب
      - بقیه → گروه پیش‌فرض تنظیم‌شده توسط ادمین (یا رشته‌ی خالی اگه هنوز تنظیم نشده)
    """
    from db import get_client_group_for_user
    email = await generate_client_email(user_id)
    group = await run_db(get_client_group_for_user, user_id)
    return email, group


# ================== MESSAGE CHUNKING (سقف ۴۰۹۶ کاراکتری تلگرام) ==================

def chunk_blocks(header: str, blocks: list, footer: str = "", max_len: int = 3500) -> list:
    """
    بلوک‌های متنی (هرکدوم مثلاً معرف یک سرویس یا یک خرید) رو در چند پیام (chunk)
    با طول کمتر از max_len ترکیب می‌کنه، بدون این‌که وسط هیچ بلوکی بریده بشه —
    این خیلی مهمه چون اگه وسط یک تگ HTML (مثلاً <code> یا <a>) بریده بشه، پیام با
    خطای entity parsing کرش می‌کنه. حاشیه‌ی امن (max_len=3500 به‌جای ۴۰۹۶) برای
    جا دادن header/footer در همون chunk در نظر گرفته شده.
    """
    chunks = []
    current = header
    for block in blocks:
        if len(current) + len(block) > max_len and current != header:
            chunks.append(current)
            current = ""
        current += block
    if current:
        chunks.append(current)

    if footer:
        if chunks and len(chunks[-1]) + len(footer) <= max_len:
            chunks[-1] += footer
        else:
            chunks.append(footer)

    return chunks


async def send_chunks(message, chunks: list, parse_mode: str | None = None):
    """ارسال چند chunk پشت‌سرهم با فاصله‌ی کوتاه، برای جلوگیری از خوردن به Flood Limit تلگرام"""
    for chunk in chunks:
        await message.answer(chunk, parse_mode=parse_mode)
        if len(chunks) > 1:
            await asyncio.sleep(0.05)


# ================== SAFE TEMPLATE FORMATTING (متن‌های سفارشی ادمین) ==================

def _safe_format(template: str, **kwargs) -> str:
    """
    .format() امن برای قالب‌های متنی سفارشی (خوش‌آمدگویی/صفحه‌ی خانه) که ادمین
    از پنل وارد می‌کنه. اگه ادمین توی متنش از یک placeholder نامعتبر استفاده
    کرده باشه (مثلاً {foo} که تعریف نشده) یا آکولاد تنها گذاشته باشه، به‌جای
    کرش کردن /start یا صفحه‌ی خانه برای *همه‌ی* کاربرها، همون متن خام (بدون
    جایگزینی placeholder ها) برگردونده می‌شه.
    """
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return template


# ================== HOME SCREEN (منوی شیشه‌ای اصلی) ==================

async def render_home(target, user_id: int):
    """
    صفحه‌ی خانه رو می‌سازه و نمایش می‌ده — تنها نقطه‌ی ساخت صفحه‌ی خانه است تا
    همه‌ی مسیرهای «🏠 بازگشت به خانه» دقیقاً یکسان رفتار کنن (بدون کد تکراری).
    اگه target از نوع CallbackQuery باشه، همون پیام رو ویرایش می‌کنه (edit_text)
    تا چت تمیز بمونه؛ اگه از نوع Message باشه (مثلاً دستور /start)، پیام جدید می‌فرسته.

    نکته‌ی مهم: پیامی که دکمه‌ی «بازگشت به خانه» روش هست همیشه پیام متنی نیست —
    مثلاً روی عکس QR کد (با caption) هم همین دکمه هست. edit_text() فقط روی
    پیام‌های متنی خالص کار می‌کنه و روی عکس/کپشن با خطای Telegram شکست می‌خوره.
    برای همین اینجا edit_text تلاش می‌شه و اگه شکست خورد (مثلاً پیام عکسه یا
    خیلی قدیمیه)، به‌جاش یک پیام متنی جدید فرستاده می‌شه.
    """
    from aiogram.exceptions import TelegramBadRequest
    from db import get_balance, get_brand_name, get_home_text
    from keyboards import home_menu_kb

    bal = await run_db(get_balance, user_id)
    brand_name = await run_db(get_brand_name)
    template = await run_db(get_home_text)
    sep = "─" * 22
    text = _safe_format(template, brand=brand_name, balance=f"{bal:,}", sep=sep)
    kb = home_menu_kb(user_id)

    if isinstance(target, types.CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest:
            # پیام قابل ویرایش به متن نبود (مثلاً عکس با caption) — پیام جدید بفرست
            await target.message.answer(text, reply_markup=kb)
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb)


async def build_welcome_text(first_name: str, brand_name: str) -> str:
    """
    متن خوش‌آمدگویی /start — از قالب قابل‌ویرایش توسط ادمین (پنل ادمین →
    شخصی‌سازی متن‌ها) ساخته می‌شه. Placeholder های در دسترس: {name}, {brand}, {sep}
    اگه ادمین چیزی سفارشی تنظیم نکرده باشه، قالب پیش‌فرض (همون متن قبلی) استفاده می‌شه.
    """
    from db import get_welcome_text
    template = await run_db(get_welcome_text)
    safe_name = (first_name or "").strip() or "دوست عزیز"
    sep = "─" * 22
    return _safe_format(template, name=safe_name, brand=brand_name, sep=sep)


# ================== EDIT-IN-PLACE FSM PROMPTS (کاهش شلوغی چت ادمین) ==================
# popup واقعی (call.answer با show_alert) فقط وقتی ممکنه که آخرین حرکت کاربر
# «تپ روی دکمه» باشه — تلگرام هیچ API پاپ‌آپی برای پیام‌های متنی معمولی نداره.
# برای فلوهایی که ادمین باید یک مقدار تایپ کنه (نه فقط تپ بزنه)، این دو تابع
# باعث می‌شن به‌جای فرستادن یک پیام تایید *جدید*، همون پیامِ «مقدار رو وارد کن»
# با نتیجه ادیت بشه — یعنی هیچ پیام اضافه‌ای به چت اضافه نمی‌شه.

async def start_prompt(call: types.CallbackQuery, state: FSMContext, text: str, reply_markup=None):
    """
    پرامپت رو می‌فرسته (پیام جدید، چون callback نمی‌تونه هم‌زمان state بگیره و
    ادیت بمونه) و chat_id/message_id ش رو برای ادیت بعدی در state ذخیره می‌کنه.
    """
    sent = await call.message.answer(text, reply_markup=reply_markup)
    data = await state.get_data()
    data["_prompt_chat_id"] = sent.chat.id
    data["_prompt_msg_id"] = sent.message_id
    await state.update_data(**data)


async def finish_prompt(message: types.Message, state: FSMContext, text: str, reply_markup=None):
    """
    به‌جای فرستادن یک پیام تایید جدید، پیام prompt قبلی (که با start_prompt
    ذخیره شده) رو با نتیجه ادیت می‌کنه. اگه به هر دلیلی ادیت ممکن نبود (مثلاً
    پیام قبلاً پاک شده)، fallback امن به فرستادن پیام معمولی می‌زنه.
    """
    data = await state.get_data()
    chat_id = data.get("_prompt_chat_id")
    msg_id = data.get("_prompt_msg_id")
    if chat_id and msg_id:
        try:
            await message.bot.edit_message_text(
                text, chat_id=chat_id, message_id=msg_id, reply_markup=reply_markup
            )
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=reply_markup)