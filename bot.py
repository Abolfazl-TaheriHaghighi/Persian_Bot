import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonCommands

from config import BOT_TOKEN
from db import init_db
from utils import run_db
from backup import auto_backup_loop
from handlers import user, payments, services, referral, admin, partner, broadcast
from handlers import renewal
from middlewares import MembershipAndPhoneMiddleware

logging.basicConfig(level=logging.INFO)


async def setup_bot_menu(bot: Bot):
    """
    ثبت منوی دستورات تلگرام (همون آیکون ☰ کنار دکمه‌ی آپلود فایل).
    برخلاف دکمه‌های شیشه‌ای، این منو هیچ‌وقت با اسکرول چت گم نمی‌شه — همیشه
    از پایین صفحه در دسترسه، حتی اگه کاربر وسط یه فلوی دیگه گیر کرده باشه.
    """
    commands = [
        BotCommand(command="start", description="🏠 راه‌اندازی مجدد / بازگشت به خانه"),
    ]
    await bot.set_my_commands(commands)
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def main():
    # init_db قبل از polling — یه‌بار blocking قابل قبوله
    await asyncio.to_thread(init_db)

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # میدل‌ور سراسری: قبل از هر دکمه (callback query) چک می‌کنه کاربر عضو
    # کانال‌های اجباری هست و شماره‌ش ثبت شده — روی dp.callback_query یعنی
    # پیام‌های متنی/دستورات اصلاً از این مسیر رد نمی‌شن، فقط دکمه‌ها.
    dp.callback_query.middleware(MembershipAndPhoneMiddleware())

    await setup_bot_menu(bot)

    dp.include_router(user.router)
    dp.include_router(payments.router)
    dp.include_router(services.router)
    dp.include_router(referral.router)
    dp.include_router(partner.router)
    dp.include_router(broadcast.router)
    dp.include_router(renewal.router)
    dp.include_router(admin.router)

    # حلقه‌ی بکاپ خودکار دیتابیس — هر ساعت چک می‌کنه که آیا طبق تنظیمات ادمین
    # (از پنل ادمین → پشتیبان‌گیری) وقتشه بکاپ بگیره یا نه
    asyncio.create_task(auto_backup_loop())

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())