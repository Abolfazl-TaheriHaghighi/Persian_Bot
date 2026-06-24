from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)

from config import ADMIN_ID, is_admin
from db_final import (
    is_partner, has_pending_request, create_partner_request,
    get_partner, add_partner, update_partner_request_status,
    get_partner_request
)
from keyboards import get_kb
from states import PartnerRequest, AdminPartnerApprove, AdminPartnerReject
from utils import normalize_phone

router = Router()


# ================================================================
# USER: درخواست همکاری
# ================================================================

@router.message(F.text == "🤝 درخواست همکاری")
async def partner_request_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    if is_partner(user_id):
        await message.answer("✅ شما در حال حاضر همکار فعال هستید.")
        return

    if has_pending_request(user_id):
        await message.answer("⏳ درخواست همکاری شما در حال بررسی است.\nمنتظر تایید ادمین باش.")
        return

    await state.set_state(PartnerRequest.waiting_phone)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 اشتراک‌گذاری شماره", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer(
        "🤝 درخواست همکاری\n\n"
        "ابتدا شماره موبایلت رو تایید کن:",
        reply_markup=kb
    )


@router.message(PartnerRequest.waiting_phone, F.contact)
async def partner_phone_contact(message: types.Message, state: FSMContext):
    phone = normalize_phone(message.contact.phone_number)
    await state.update_data(phone=phone)
    await state.set_state(PartnerRequest.waiting_description)
    await message.answer(
        f"📱 شماره: {phone}\n\n"
        "📝 حالا یه توضیح کوتاه درباره خودت و هدفت از همکاری بنویس:",
        reply_markup=types.ReplyKeyboardRemove()
    )


@router.message(PartnerRequest.waiting_phone, F.text)
async def partner_phone_text(message: types.Message, state: FSMContext):
    phone = normalize_phone(message.text)
    if not phone.startswith("09") or len(phone) != 11:
        await message.answer("❌ شماره نامعتبر. مثلاً: 09123456789")
        return
    await state.update_data(phone=phone)
    await state.set_state(PartnerRequest.waiting_description)
    await message.answer(
        f"📱 شماره: {phone}\n\n"
        "📝 یه توضیح کوتاه درباره خودت و هدفت از همکاری بنویس:",
        reply_markup=types.ReplyKeyboardRemove()
    )


@router.message(PartnerRequest.waiting_description)
async def partner_description(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    phone = data["phone"]
    description = message.text.strip()
    user_id = message.from_user.id

    create_partner_request(user_id, phone, description)
    await state.clear()

    await message.answer(
        "✅ درخواست همکاری شما ثبت شد!\n"
        "⏳ منتظر بررسی و تایید ادمین باش.",
        reply_markup=get_kb(user_id)
    )

    username = message.from_user.username or "ندارد"
    await bot.send_message(
        ADMIN_ID,
        f"🤝 درخواست همکاری جدید!\n"
        f"{'─'*22}\n"
        f"👤 User ID: {user_id}\n"
        f"🔖 Username: @{username}\n"
        f"📱 شماره: {phone}\n"
        f"📝 توضیحات:\n{description}\n"
        f"{'─'*22}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تایید", callback_data=f"partner:approve:{user_id}:{phone}"),
                InlineKeyboardButton(text="❌ رد",    callback_data=f"partner:reject:{user_id}"),
            ]
        ])
    )


# ================================================================
# ADMIN: تایید/رد درخواست
# ================================================================

@router.callback_query(F.data.startswith("partner:approve:"))
async def partner_approve_start(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    parts = call.data.split(":")
    target_user_id = int(parts[2])
    phone = parts[3]
    await state.set_state(AdminPartnerApprove.waiting_message)
    await state.update_data(target_user_id=target_user_id, phone=phone)
    await call.message.answer(
        f"✅ در حال تایید کاربر {target_user_id}\n\n"
        "پیامی برای کاربر بنویس (یا /skip برای پیام پیش‌فرض):"
    )
    await call.answer()


@router.message(AdminPartnerApprove.waiting_message)
async def partner_approve_confirm(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    target_user_id = data["target_user_id"]
    phone = data["phone"]

    custom_msg = None if message.text == "/skip" else message.text.strip()
    add_partner(target_user_id, phone)

    user_text = custom_msg or (
        "🎉 تبریک! درخواست همکاری شما تایید شد.\n"
        "✅ حالا به دسته‌بندی‌های ویژه همکاران دسترسی داری."
    )
    await state.clear()

    try:
        await bot.send_message(target_user_id, user_text)
    except Exception:
        pass

    await message.answer(
        f"✅ کاربر {target_user_id} به عنوان همکار تایید شد.",
        reply_markup=get_kb(message.from_user.id)
    )


@router.callback_query(F.data.startswith("partner:reject:"))
async def partner_reject_start(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    target_user_id = int(call.data.split(":")[2])
    await state.set_state(AdminPartnerReject.waiting_message)
    await state.update_data(target_user_id=target_user_id)
    await call.message.answer(
        f"❌ در حال رد کاربر {target_user_id}\n\n"
        "پیامی برای کاربر بنویس (یا /skip برای پیام پیش‌فرض):"
    )
    await call.answer()


@router.message(AdminPartnerReject.waiting_message)
async def partner_reject_confirm(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    target_user_id = data["target_user_id"]

    custom_msg = None if message.text == "/skip" else message.text.strip()
    user_text = custom_msg or "❌ متأسفانه درخواست همکاری شما در این مرحله تایید نشد."

    await state.clear()

    try:
        await bot.send_message(target_user_id, user_text)
    except Exception:
        pass

    await message.answer(
        f"✅ رد درخواست کاربر {target_user_id} انجام شد.",
        reply_markup=get_kb(message.from_user.id)
    )