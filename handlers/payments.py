from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_ID, is_admin
from db import (
    create_transaction, approve_transaction, reject_transaction, get_balance
)
from keyboards import home_button_kb, cancel_kb
from states import DepositStates, RejectReason
from utils import run_db, notify_admins

router = Router()


@router.callback_query(F.data == "menu:deposit")
async def deposit(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(DepositStates.waiting_for_amount)
    await call.message.edit_text(
        "💰 مبلغ واریزی رو فقط به عدد وارد کن (تومان):",
        reply_markup=cancel_kb()
    )
    await call.answer()


@router.message(DepositStates.waiting_for_amount)
async def handle_amount(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ لطفاً فقط عدد وارد کن:", reply_markup=cancel_kb())
        return
    amount = int(message.text)
    if amount <= 0:
        await message.answer("❌ مبلغ باید بیشتر از صفر باشه:", reply_markup=cancel_kb())
        return
    await state.update_data(amount=amount)
    await state.set_state(DepositStates.waiting_for_receipt)
    await message.answer(
        f"💰 مبلغ: {amount:,} تومان\n\n📸 حالا تصویر فیش واریزی رو ارسال کن:",
        reply_markup=cancel_kb()
    )


@router.message(DepositStates.waiting_for_receipt, F.photo)
async def handle_receipt(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    amount = data.get("amount")
    user_id = message.from_user.id
    tx_id = await run_db(create_transaction, user_id, amount)
    username = message.from_user.username or "ندارد"
    caption = (
        f"💳 درخواست شارژ جدید\n"
        f"👤 User ID: {user_id}\n"
        f"🔖 Username: @{username}\n"
        f"💰 مبلغ: {amount:,} تومان\n"
        f"🔑 TX_ID: {tx_id}"
    )
    from config import ADMIN_IDS
    for _aid in ADMIN_IDS:
        try:
            await bot.send_photo(
                _aid,
                photo=message.photo[-1].file_id,
                caption=caption,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="✅ تایید", callback_data=f"approve:{tx_id}:{user_id}:{amount}"),
                    InlineKeyboardButton(text="❌ رد",    callback_data=f"reject:{tx_id}:{user_id}:{amount}")
                ]])
            )
        except Exception:
            pass
    await state.clear()
    await message.answer("📤 فیش ارسال شد، منتظر تایید ادمین باش.", reply_markup=home_button_kb())


@router.message(DepositStates.waiting_for_receipt)
async def handle_receipt_wrong(message: types.Message):
    await message.answer("❌ لطفاً تصویر فیش رو ارسال کن (نه متن یا فایل دیگه):", reply_markup=cancel_kb())


@router.callback_query(F.data.startswith("approve:"))
async def approve(call: types.CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        await call.answer("❌ دسترسی ندارید", show_alert=True)
        return
    _, tx_id, user_id, amount = call.data.split(":")
    tx_id, user_id, amount = int(tx_id), int(user_id), int(amount)
    await run_db(approve_transaction, tx_id, user_id, amount)
    new_bal = await run_db(get_balance, user_id)
    await bot.send_message(user_id,
        f"✅ شارژ تایید شد\n💰 +{amount:,} تومان اضافه شد\n👛 موجودی: {new_bal:,} تومان",
        reply_markup=home_button_kb())
    await call.message.edit_caption(call.message.caption + "\n\n✅ تایید شد")
    await call.answer("✅ تایید شد")


@router.callback_query(F.data.startswith("reject:"))
async def reject(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌ دسترسی ندارید", show_alert=True)
        return
    _, tx_id, user_id, amount = call.data.split(":")
    await state.set_state(RejectReason.waiting_for_reason)
    await state.update_data(
        tx_id=int(tx_id), user_id=int(user_id), amount=int(amount),
        msg_id=call.message.message_id, orig_caption=call.message.caption or ""
    )
    await call.message.answer(
        f"✏️ دلیل رد کردن شارژ {int(amount):,} تومان (کاربر {user_id}) رو بنویس:\n"
        f"(یا /skip برای ارسال بدون دلیل)"
    )
    await call.answer()


@router.message(RejectReason.waiting_for_reason)
async def reject_with_reason(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    reason = None if message.text == "/skip" else message.text.strip()
    await run_db(reject_transaction, data["tx_id"])
    user_msg = f"❌ درخواست شارژ شما رد شد\n💰 مبلغ: {data['amount']:,} تومان"
    if reason:
        user_msg += f"\n\n📝 دلیل: {reason}"
    await bot.send_message(data["user_id"], user_msg, reply_markup=home_button_kb())
    try:
        new_cap = data["orig_caption"] + "\n\n❌ رد شد"
        if reason:
            new_cap += f"\n📝 دلیل: {reason}"
        await bot.edit_message_caption(chat_id=ADMIN_ID, message_id=data["msg_id"], caption=new_cap)
    except Exception:
        pass
    await state.clear()
    await message.answer("✅ رد شد و به کاربر اطلاع داده شد.", reply_markup=home_button_kb())