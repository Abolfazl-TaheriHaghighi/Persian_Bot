import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonCommands

from config import BOT_TOKEN, ADMIN_ID
from db import init_db, update_license_checked
from license import check_license_from_db, warm_cache, clear_cache
from utils import run_db
from backup import auto_backup_loop
from handlers import user, payments, services, referral, admin, partner, broadcast
from handlers import license_handler, renewal

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


async def daily_license_check(bot: Bot):
    """چک روزانه لایسنس + گرم کردن cache + هشدار انقضا"""
    while True:
        await asyncio.sleep(86400)
        try:
            # warm_cache داخلش DB call داره — از run_db
            await run_db(warm_cache, BOT_TOKEN)
            await run_db(update_license_checked)

            from license import _C as result
            if result.get("permanent"):
                continue

            days_left = result.get("days_left")
            if not result.get("valid"):
                if result.get("error") == "لایسنس منقضی شده":
                    await bot.send_message(
                        ADMIN_ID,
                        "⛔️ لایسنس پرو منقضی شد!\n\n"
                        "قابلیت‌های پرو غیرفعال شدن.\n"
                        "برای تمدید، لایسنس جدید از پنل ادمین وارد کن."
                    )
            elif days_left is not None and 0 < days_left <= 7:
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ لایسنس پرو در حال انقضاست!\n\n"
                    f"⏳ {days_left} روز دیگه منقضی میشه\n"
                    f"📅 تاریخ انقضا: {result['expire_date']}\n\n"
                    f"برای تمدید اقدام کن."
                )
        except Exception as e:
            logging.error(f"License check error: {e}")


async def main():
    # init_db قبل از polling — یه‌بار blocking قابل قبوله
    await asyncio.to_thread(init_db)

    # گرم کردن cache لایسنس — از run_db
    await run_db(warm_cache, BOT_TOKEN)
    from license import _C as lic_result
    if lic_result.get("valid"):
        if lic_result.get("permanent"):
            logging.info("✅ License: Permanent/Master")
        else:
            logging.info(f"✅ License: PRO — {lic_result.get('days_left')} days left")
    else:
        logging.warning(f"⚠️ License: FREE — {lic_result.get('error')}")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    await setup_bot_menu(bot)

    dp.include_router(user.router)
    dp.include_router(payments.router)
    dp.include_router(services.router)
    dp.include_router(referral.router)
    dp.include_router(partner.router)
    dp.include_router(broadcast.router)
    dp.include_router(license_handler.router)
    dp.include_router(renewal.router)
    dp.include_router(admin.router)

    asyncio.create_task(daily_license_check(bot))
    # حلقه‌ی بکاپ خودکار دیتابیس — هر ساعت چک می‌کنه که آیا طبق تنظیمات ادمین
    # (از پنل ادمین → پشتیبان‌گیری) وقتشه بکاپ بگیره یا نه
    asyncio.create_task(auto_backup_loop())

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())