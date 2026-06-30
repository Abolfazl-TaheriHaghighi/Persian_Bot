import asyncio
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_ID, is_admin
from db import get_all_user_ids, get_partner_user_ids
from keyboards import get_kb
from states import AdminBroadcast
from utils import run_db

router = Router()


def broadcast_target_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 همه کاربران",     callback_data="broadcast:all")],
        [InlineKeyboardButton(text="🤝 فقط همکاران",     callback_data="broadcast:partners")],
        [InlineKeyboardButton(text="🎯 کاربران خاص",     callback_data="broadcast:custom")],
        [InlineKeyboardButton(text="🔙 برگشت",           callback_data="admin:back")],
    ])


@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast_start(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    from pro_guard import require_pro
    if not await require_pro(call, "ارسال پیام همگانی"):
        return
    await call.message.edit_text("📣 ارسال پیام گروهی\n\nمخاطبان رو انتخاب کن:", reply_markup=broadcast_target_kb())
    await call.answer()


@router.callback_query(F.data.startswith("broadcast:"))
async def broadcast_choose_target(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    target = call.data.split(":")[1]

    if target == "custom":
        await state.set_state(AdminBroadcast.waiting_custom_ids)
        await call.message.answer(
            "🎯 آی‌دی کاربران رو وارد کن (هر خط یه آی‌دی):\n"
            "مثال:\n123456789\n987654321"
        )
        await call.answer()
        return

    await state.set_state(AdminBroadcast.waiting_message)
    await state.update_data(target=target, custom_ids=None)

    target_label = "همه کاربران" if target == "all" else "همکاران"
    await call.message.answer(f"📝 پیامت رو برای {target_label} بنویس:")
    await call.answer()


@router.message(AdminBroadcast.waiting_custom_ids)
async def broadcast_custom_ids(message: types.Message, state: FSMContext):
    lines = message.text.strip().splitlines()
    ids = []
    for line in lines:
        line = line.strip()
        if line.isdigit():
            ids.append(int(line))

    if not ids:
        await message.answer("❌ هیچ آی‌دی معتبری پیدا نشد. دوباره وارد کن:")
        return

    await state.update_data(target="custom", custom_ids=ids)
    await state.set_state(AdminBroadcast.waiting_message)
    await message.answer(f"✅ {len(ids)} کاربر انتخاب شد.\n\n📝 حالا پیامت رو بنویس:")


@router.message(AdminBroadcast.waiting_message)
async def broadcast_send(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    target = data["target"]
    custom_ids = data.get("custom_ids")
    await state.clear()

    # گرفتن لیست آی‌دی‌ها
    if target == "all":
        user_ids = await run_db(get_all_user_ids)
    elif target == "partners":
        user_ids = await run_db(get_partner_user_ids)
    else:
        user_ids = custom_ids or []

    if not user_ids:
        await message.answer("❌ هیچ کاربری پیدا نشد.")
        return

    await message.answer(f"📤 در حال ارسال به {len(user_ids)} نفر...")

    success = 0
    failed = 0
    for uid in user_ids:
        if uid == ADMIN_ID:
            continue
        try:
            await bot.copy_message(
                chat_id=uid,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # جلوگیری از flood

    await message.answer(
        f"✅ ارسال تموم شد!\n"
        f"✔️ موفق: {success}\n"
        f"❌ ناموفق: {failed}",
        reply_markup=get_kb(message.from_user.id)
    )