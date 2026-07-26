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

    commands = [
        BotCommand(command="start", description="🏠 راه‌اندازی مجدد / بازگشت به خانه"),
    ]
    await bot.set_my_commands(commands)
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def main():
    
    await asyncio.to_thread(init_db)

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

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

    asyncio.create_task(auto_backup_loop())

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())