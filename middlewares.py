from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import (
    TelegramObject, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)

from db import get_active_channels, connect
from utils import run_db

# این کالبک‌ها همیشه باید رد بشن، حتی اگه کاربر عضو کانال‌ها نباشه یا شماره
# ثبت‌شده نداشته باشه — وگرنه کاربر توی یه حلقه‌ی بی‌راه‌حل گیر می‌کنه:
# - check_membership: همون دکمه‌ای که بعد از جوین شدن برای بررسی مجدد می‌زنه
# - cancel:fsm: راه فرار از وسط هر فلوی چندمرحله‌ای؛ نباید خودش هم گیت شه
_EXEMPT_CALLBACKS = {"check_membership", "cancel:fsm"}


def _user_has_phone(user_id) -> bool:
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT phone FROM users WHERE telegram_id=%s", (user_id,))
    r = cur.fetchone()
    conn.close()
    return bool(r and r[0])


async def _check_membership(bot, user_id: int) -> list:
    """
    دقیقاً همون منطق check_membership در handlers/user.py — اینجا مستقل
    تعریف شده (نه import شده) تا میدل‌ور به هیچ هندلری وابسته نباشه و در
    صورت تغییر ساختار handlers در آینده نشکنه.
    """
    channels = await run_db(get_active_channels)
    not_joined = []
    for ch in channels:
        ch_id, channel_id, username, title, invite_link = ch
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status in ("left", "kicked", "banned"):
                not_joined.append((ch_id, channel_id, username, title, invite_link))
        except Exception:
            not_joined.append((ch_id, channel_id, username, title, invite_link))
    return not_joined


async def _send_join_alert(call: CallbackQuery, not_joined: list):
    buttons = []
    for ch_id, channel_id, username, title, invite_link in not_joined:
        link = invite_link or (f"https://t.me/{username.lstrip('@')}" if username else None)
        if link:
            buttons.append([InlineKeyboardButton(text=f"📢 {title}", url=link)])
    buttons.append([InlineKeyboardButton(text="✅ عضو شدم، بررسی کن", callback_data="check_membership")])
    await call.answer("⛔️ برای استفاده از ربات باید عضو کانال‌های زیر بشی", show_alert=True)
    try:
        await call.message.answer(
            "⛔️ برای استفاده از ربات باید عضو کانال‌های زیر بشی:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
    except Exception:
        pass


async def _ask_for_phone(call: CallbackQuery):
    await call.answer("📱 لطفاً اول شماره‌ت رو ثبت کن", show_alert=True)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 اشتراک‌گذاری شماره", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    try:
        await call.message.answer(
            "📱 برای ادامه، لطفاً شماره موبایلت رو با دکمه‌ی زیر به اشتراک بذار:",
            reply_markup=kb,
        )
    except Exception:
        pass


class MembershipAndPhoneMiddleware(BaseMiddleware):
    """
    میدل‌ور سراسری روی همه‌ی callback query ها (یعنی همه‌ی دکمه‌های شیشه‌ای
    ربات، بدون استثنا مگر توی _EXEMPT_CALLBACKS). قبل از رسیدن به هندلر اصلی
    هر دکمه، دو تا چک انجام می‌ده:
        ۱) عضویت در کانال‌های اجباری (اگه کانالی تعریف شده باشه)
        ۲) وجود شماره تلفن ثبت‌شده برای کاربر
    اگه هرکدوم رد نشه، هندلر اصلی اصلاً صدا زده نمی‌شه (میدل‌ور بدون
    فراخوانی handler برمی‌گرده) و پیام مناسب (لینک جوین / درخواست شماره)
    نشون داده می‌شه.

    فقط روی CallbackQuery ثبت می‌شه (dp.callback_query.middleware) نه روی
    کل Update — یعنی پیام‌های متنی (ورودی‌های FSM ادمین، دکمه‌ی اشتراک‌گذاری
    شماره خودش، دستورات و...) اصلاً از این مسیر رد نمی‌شن و دست‌نخورده می‌مونن.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: Dict[str, Any],
    ) -> Any:
        if event.data in _EXEMPT_CALLBACKS:
            return await handler(event, data)

        bot = data.get("bot") or event.bot
        user_id = event.from_user.id

        not_joined = await _check_membership(bot, user_id)
        if not_joined:
            await _send_join_alert(event, not_joined)
            return

        has_phone = await run_db(_user_has_phone, user_id)
        if not has_phone:
            await _ask_for_phone(event)
            return

        return await handler(event, data)