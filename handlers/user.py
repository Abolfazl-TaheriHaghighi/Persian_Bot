from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from config import ADMIN_ID
from db import (
    add_user, get_balance, get_user_purchases,
    get_referral_config, give_referral_reward,
    connect as db_connect
)
from keyboards import get_kb
from states import DepositStates

router = Router()


# ================================================================
# START / HOME
# ================================================================

@router.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await state.clear()

    # پردازش لینک رفرال
    args = message.text.split()
    referred_by = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referred_by = int(args[1][4:])
            if referred_by == message.from_user.id:
                referred_by = None
        except ValueError:
            referred_by = None

    add_user(message.from_user.id, referred_by)

    # اگه رفرال داشت → پاداش ثبت‌نام
    if referred_by:
        try:
            conn2 = db_connect()
            cur2 = conn2.cursor()
            cur2.execute("""
                SELECT COUNT(*) FROM referral_rewards
                WHERE referrer_id=%s AND referred_id=%s AND reward_type='join'
            """, (referred_by, message.from_user.id))
            already_rewarded = cur2.fetchone()[0] > 0
            conn2.close()
        except Exception:
            already_rewarded = True

        if not already_rewarded:
            ref_cfg = get_referral_config()
            if ref_cfg and ref_cfg[0] and ref_cfg[1] > 0:
                give_referral_reward(referred_by, message.from_user.id, "join", ref_cfg[1])
                try:
                    await message.bot.send_message(
                        referred_by,
                        f"🎉 یه نفر با لینک رفرال شما عضو شد!\n"
                        f"💚 +{ref_cfg[1]:,} تومان به حسابت اضافه شد."
                    )
                except Exception:
                    pass

    bal = get_balance(message.from_user.id)
    await message.answer(
        f"👋 خوش اومدی به ربات VPN!\n\n💰 موجودی: {bal:,} تومان",
        reply_markup=get_kb(message.from_user.id)
    )


@router.message(F.text == "🏠 خانه")
async def home(message: types.Message, state: FSMContext):
    await state.clear()
    bal = get_balance(message.from_user.id)
    await message.answer(
        f"🏠 صفحه اصلی\n\n💰 موجودی: {bal:,} تومان",
        reply_markup=get_kb(message.from_user.id)
    )


# ================================================================
# BALANCE
# ================================================================

@router.message(F.text == "💰 موجودی من")
async def balance(message: types.Message):
    bal = get_balance(message.from_user.id)
    await message.answer(f"💰 موجودی شما: {bal:,} تومان")


# ================================================================
# PURCHASE HISTORY
# ================================================================

@router.message(F.text == "📊 وضعیت سرویس‌ها")
async def service_status(message: types.Message):
    await message.answer("🔧 این بخش به زودی اضافه میشه.")
async def my_purchases(message: types.Message):
    purchases = get_user_purchases(message.from_user.id)
    if not purchases:
        await message.answer("📋 هنوز خریدی نداشتی.")
        return
    text = "📋 تاریخچه خریدهای شما:\n\n"
    for p in purchases:
        sname, amt, pat = p
        text += f"📦 {sname} | {amt:,} تومان | {pat.strftime('%Y-%m-%d %H:%M')}\n"
    await message.answer(text)