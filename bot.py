import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, ADMIN_ID
from db_final import init_db, update_license_checked
from license import check_license_from_db, clear_cache

from handlers import user, payments, services, referral, admin, partner, broadcast
from handlers import license_handler

logging.basicConfig(level=logging.INFO)


async def daily_license_check(bot: Bot):
    """چک روزانه لایسنس + هشدار انقضا"""
    while True:
        await asyncio.sleep(86400)  # هر ۲۴ ساعت
        try:
            result = check_license_from_db(BOT_TOKEN)
            update_license_checked()
            clear_cache()

            if result.get("permanent"):
                continue

            days_left = result.get("days_left")

            if not result["valid"]:
                if result["error"] == "لایسنس منقضی شده":
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
    init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(user.router)
    dp.include_router(payments.router)
    dp.include_router(services.router)
    dp.include_router(referral.router)
    dp.include_router(partner.router)
    dp.include_router(broadcast.router)
    dp.include_router(license_handler.router)
    dp.include_router(admin.router)

    # چک لایسنس موقع استارت
    result = check_license_from_db(BOT_TOKEN)
    if result["valid"]:
        if result.get("permanent"):
            logging.info("✅ License: Permanent/Master")
        else:
            logging.info(f"✅ License: PRO — {result['days_left']} days left")
    else:
        logging.warning(f"⚠️ License: FREE — {result['error']}")

    # شروع چک روزانه
    asyncio.create_task(daily_license_check(bot))

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())