from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)

from config import ADMIN_ID, is_admin
from db import (
    is_partner, has_pending_request, create_partner_request,
    get_partner, add_partner, remove_partner,
    get_all_partners
)
from keyboards import get_kb
from states import PartnerRequest, AdminPartnerApprove, AdminPartnerReject
from utils import normalize_phone, run_db

router = Router()


# ================================================================
# USER: درخواست همکاری
# ================================================================

@router.message(F.text == "🤝 درخواست همکاری")
async def partner_request_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    if await run_db(is_partner, user_id):
        await message.answer("✅ شما در حال حاضر همکار فعال هستید.")
        return

    if await run_db(has_pending_request, user_id):
        await message.answer("⏳ درخواست همکاری شما در حال بررسی است.\nمنتظر تایید ادمین باش.")
        return

    await state.set_state(PartnerRequest.waiting_phone)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 اشتراک‌گذاری شماره", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer(
        "🤝 درخواست همکاری\n\nابتدا شماره موبایلت رو تایید کن:",
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


# هر نوع محتوایی رو به عنوان توضیحات قبول کن (متن، عکس، ویس و...)
@router.message(PartnerRequest.waiting_description)
async def partner_description(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    phone = data["phone"]
    user_id = message.from_user.id

    # خلاصه توضیحات برای دیتابیس
    if message.text:
        description = message.text.strip()
    elif message.photo:
        description = f"[عکس] {message.caption or ''}"
    elif message.voice:
        description = "[ویس]"
    elif message.video:
        description = f"[ویدیو] {message.caption or ''}"
    else:
        description = "[فایل]"

    await run_db(create_partner_request, user_id, phone, description)
    await state.clear()

    await message.answer(
        "✅ درخواست همکاری شما ثبت شد!\n"
        "⏳ منتظر بررسی و تایید ادمین باش.",
        reply_markup=get_kb(user_id)
    )

    # فوروارد پیام کاربر به ادمین
    username = message.from_user.username or "ندارد"
    header = (
        f"🤝 درخواست همکاری جدید!\n"
        f"{'─'*22}\n"
        f"👤 User ID: {user_id}\n"
        f"🔖 Username: @{username}\n"
        f"📱 شماره: {phone}\n"
        f"{'─'*22}\n"
        f"📝 توضیحات:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تایید", callback_data=f"partner:approve:{user_id}:{phone}"),
            InlineKeyboardButton(text="❌ رد",    callback_data=f"partner:reject:{user_id}"),
        ]
    ])

    from config import ADMIN_IDS
    for _aid in ADMIN_IDS:
        try:
            await bot.send_message(_aid, header)
            await bot.forward_message(chat_id=_aid, from_chat_id=message.chat.id, message_id=message.message_id)
            await bot.send_message(_aid, "انتخاب کن:", reply_markup=kb)
        except Exception:
            pass


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
    await run_db(add_partner, target_user_id, phone)
    await state.clear()

    # پیام پایه همیشه میره
    base_text = "🎉 تبریک! درخواست همکاری شما تایید شد.\n✅ حالا به دسته‌بندی‌های ویژه همکاران دسترسی داری."
    # اگه پیام اضافه داشت، زیرش میاد
    full_text = base_text + (f"\n\n💬 پیام ادمین:\n{custom_msg}" if custom_msg else "")

    try:
        await bot.send_message(target_user_id, full_text)
        notif = "✅ پیام به کاربر ارسال شد"
    except Exception:
        notif = "⚠️ کاربر ربات رو بلاک کرده"

    await message.answer(
        f"✅ کاربر {target_user_id} به عنوان همکار تایید شد.\n{notif}",
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

    # پاک کردن درخواست از دیتابیس
    from db import connect as _conn
    def _delete_request(uid):
        conn = _conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM partner_requests WHERE user_id=%s", (uid,))
        conn.commit()
        conn.close()
    await run_db(_delete_request, target_user_id)

    await state.clear()

    try:
        await bot.send_message(target_user_id, user_text)
        notif = "✅ پیام به کاربر ارسال شد"
    except Exception:
        notif = "⚠️ کاربر ربات رو بلاک کرده"

    await message.answer(
        f"✅ رد درخواست کاربر {target_user_id} انجام شد.\n{notif}",
        reply_markup=get_kb(message.from_user.id)
    )