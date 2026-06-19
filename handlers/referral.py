from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from db import (
    get_referral_config, get_referral_stats, get_referral_rewards_history,
    get_referrals,
    get_trial_config, get_trial_use_count, get_phone_max_uses,
    get_referral_count, get_user,
    set_user_phone, record_trial_use
)
from keyboards import get_kb, back_kb
from states import FreeTrial
from utils import format_data, data_label_short, normalize_phone

router = Router()


# ================================================================
# FREE TRIAL
# ================================================================

@router.message(F.text == "🎁 تست رایگان")
async def free_trial_start(message: types.Message, state: FSMContext):
    cfg = get_trial_config()
    is_enabled, duration_days, data_limit_gb, require_referral, min_referrals, default_max_uses = cfg

    if not is_enabled:
        await message.answer("❌ در حال حاضر تست رایگان فعال نیست.")
        return

    user_id = message.from_user.id

    if require_referral and min_referrals > 0:
        ref_count = get_referral_count(user_id)
        if ref_count < min_referrals:
            await message.answer(
                f"❌ برای دریافت تست رایگان باید حداقل {min_referrals} نفر رو دعوت کرده باشی.\n"
                f"👥 تعداد زیرمجموعه فعلی: {ref_count}"
            )
            return

    user = get_user(user_id)
    if user and user[3]:  # phone موجوده
        phone = user[3]
        use_count = get_trial_use_count(phone)
        max_uses = get_phone_max_uses(phone)
        if use_count >= max_uses:
            await message.answer(
                f"❌ شماره {phone} قبلاً از تست رایگان استفاده کرده.\n"
                f"(استفاده‌های انجام‌شده: {use_count}/{max_uses})"
            )
            return
        await _give_free_trial(message, phone, cfg)
    else:
        await state.set_state(FreeTrial.waiting_phone)
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 اشتراک‌گذاری شماره", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.answer(
            "📱 برای دریافت تست رایگان، شماره موبایلت رو تایید کن:\n\n"
            "روی دکمه زیر کلیک کن یا شماره‌ات رو بفرست:",
            reply_markup=kb
        )


@router.message(FreeTrial.waiting_phone, F.contact)
async def trial_phone_contact(message: types.Message, state: FSMContext):
    phone = normalize_phone(message.contact.phone_number)
    await state.clear()
    cfg = get_trial_config()
    await _process_trial_phone(message, phone, cfg)


@router.message(FreeTrial.waiting_phone, F.text)
async def trial_phone_text(message: types.Message, state: FSMContext):
    phone = normalize_phone(message.text)
    if not phone.startswith("09") or len(phone) != 11:
        await message.answer("❌ شماره نامعتبر. مثلاً: 09123456789")
        return
    await state.clear()
    cfg = get_trial_config()
    await _process_trial_phone(message, phone, cfg)


async def _process_trial_phone(message: types.Message, phone: str, cfg):
    user_id = message.from_user.id
    use_count = get_trial_use_count(phone)
    max_uses = get_phone_max_uses(phone)

    if use_count >= max_uses:
        await message.answer(
            f"❌ شماره {phone} قبلاً از تست رایگان استفاده کرده.\n"
            f"(استفاده‌های انجام‌شده: {use_count}/{max_uses})",
            reply_markup=get_kb(user_id)
        )
        return

    set_user_phone(user_id, phone)
    await _give_free_trial(message, phone, cfg)


async def _give_free_trial(message: types.Message, phone: str, cfg):
    user_id = message.from_user.id
    is_enabled, duration_days, data_limit_gb, require_referral, min_referrals, default_max_uses = cfg

    record_trial_use(phone, user_id)

    sep = "─" * 22
    await message.answer(
        f"✅ تست رایگان فعال شد!\n{sep}\n"
        f"📱 شماره: {phone}\n"
        f"⏳ مدت: {duration_days} روز\n"
        f"{format_data(data_limit_gb)}\n{sep}\n"
        f"📩 اطلاعات اتصال به زودی ارسال می‌شه.",
        reply_markup=get_kb(user_id)
    )

    from config import ADMIN_ID
    username = message.from_user.username or "ندارد"
    await message.bot.send_message(
        ADMIN_ID,
        f"🧪 تست رایگان جدید!\n"
        f"👤 User: {user_id} (@{username})\n"
        f"📱 شماره: {phone}\n"
        f"⏳ {duration_days} روز | {data_label_short(data_limit_gb)}"
    )


# ================================================================
# REFERRAL PANEL
# ================================================================

@router.message(F.text == "👥 رفرال من")
async def referral_panel(message: types.Message):
    user_id = message.from_user.id
    ref_cfg = get_referral_config()
    is_enabled, reward_join, reward_purchase, reward_pct = ref_cfg

    ref_count, total_reward = get_referral_stats(user_id)
    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

    sep = "─" * 22
    text = (
        f"👥 پنل رفرال شما\n{sep}\n"
        f"🔗 لینک دعوت:\n{ref_link}\n{sep}\n"
        f"👤 تعداد زیرمجموعه: {ref_count} نفر\n"
        f"💰 مجموع پاداش دریافتی: {total_reward:,} تومان\n{sep}\n"
    )

    if is_enabled:
        text += "🎁 پاداش‌های فعلی:\n"
        if reward_join > 0:
            text += f"  • ثبت‌نام هر نفر: {reward_join:,} تومان\n"
        if reward_purchase > 0:
            text += f"  • خرید هر نفر (ثابت): {reward_purchase:,} تومان\n"
        if reward_pct > 0:
            text += f"  • خرید هر نفر (درصدی): {reward_pct}% مبلغ خرید\n"
        if reward_join == 0 and reward_purchase == 0 and reward_pct == 0:
            text += "  • در حال حاضر پاداشی تنظیم نشده.\n"
    else:
        text += "⚠️ سیستم رفرال فعلاً غیرفعاله."

    buttons = [
        [InlineKeyboardButton(text="📋 تاریخچه پاداش‌ها", callback_data="ref:history")],
        [InlineKeyboardButton(text="👥 لیست زیرمجموعه‌ها", callback_data="ref:list")],
    ]
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data == "ref:history")
async def ref_history(call: types.CallbackQuery):
    rewards = get_referral_rewards_history(call.from_user.id)
    if not rewards:
        await call.message.edit_text("📋 هنوز پاداشی دریافت نکردی.", reply_markup=back_kb("ref:back"))
        await call.answer()
        return
    text = "📋 تاریخچه پاداش‌های رفرال:\n\n"
    for r in rewards:
        referred_id, rtype, amount, created_at = r
        type_label = "ثبت‌نام" if rtype == "join" else "خرید"
        text += f"👤 {referred_id} | {type_label} | +{amount:,} تومان | {created_at.strftime('%Y-%m-%d')}\n"
    await call.message.edit_text(text, reply_markup=back_kb("ref:back"))
    await call.answer()


@router.callback_query(F.data == "ref:list")
async def ref_list(call: types.CallbackQuery):
    refs = get_referrals(call.from_user.id)
    if not refs:
        await call.message.edit_text("👥 هنوز زیرمجموعه‌ای نداری.", reply_markup=back_kb("ref:back"))
        await call.answer()
        return
    text = f"👥 زیرمجموعه‌های شما ({len(refs)} نفر):\n\n"
    for r in refs:
        uid, bal, joined = r
        text += f"🆔 {uid} | {joined.strftime('%Y-%m-%d')}\n"
    await call.message.edit_text(text, reply_markup=back_kb("ref:back"))
    await call.answer()


@router.callback_query(F.data == "ref:back")
async def ref_back(call: types.CallbackQuery):
    await call.message.delete()
    await call.answer()