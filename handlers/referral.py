from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)

from config import ADMIN_ID
from db import (
    get_referral_config, get_referral_stats, get_referral_rewards_history,
    get_referrals,
    get_trial_config, get_trial_use_count, get_phone_max_uses,
    get_referral_count, get_user,
    set_user_phone, record_trial_use,
    save_vpn_account
)
from keyboards import home_button_kb, back_kb
from states import FreeTrial
from utils import format_data, data_label_short, normalize_phone, run_db, notify_admins, prepare_new_client

router = Router()


# ================================================================
# FREE TRIAL
# ================================================================

@router.callback_query(F.data == "menu:trial")
async def free_trial_start(call: types.CallbackQuery, state: FSMContext):
    cfg = await run_db(get_trial_config)
    is_enabled, duration_days, data_limit_gb, require_referral, min_referrals, default_max_uses, panel_id, panel_group_ids = cfg

    if not is_enabled:
        await call.message.edit_text("❌ در حال حاضر تست رایگان فعال نیست.", reply_markup=home_button_kb())
        await call.answer()
        return

    user_id = call.from_user.id

    if require_referral and min_referrals > 0:
        ref_count = await run_db(get_referral_count, user_id)
        if ref_count < min_referrals:
            await call.message.edit_text(
                f"❌ برای دریافت تست رایگان باید حداقل {min_referrals} نفر رو دعوت کرده باشی.\n"
                f"👥 تعداد زیرمجموعه فعلی: {ref_count}",
                reply_markup=home_button_kb()
            )
            await call.answer()
            return

    user = await run_db(get_user, user_id)
    if user and user[3]:
        phone = user[3]
        use_count = await run_db(get_trial_use_count, phone)
        max_uses = await run_db(get_phone_max_uses, phone)
        if use_count >= max_uses:
            await call.message.edit_text(
                f"❌ شماره {phone} قبلاً از تست رایگان استفاده کرده.\n"
                f"(استفاده‌های انجام‌شده: {use_count}/{max_uses})",
                reply_markup=home_button_kb()
            )
            await call.answer()
            return
        await call.message.edit_text("⏳ در حال فعال‌سازی تست رایگان...")
        await call.answer()
        await _give_free_trial(call.message, user_id, call.from_user.username or "ندارد", phone, cfg)
    else:
        await state.set_state(FreeTrial.waiting_phone)
        await call.message.edit_text("📱 برای دریافت تست رایگان، شماره موبایلت رو تایید کن:")
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 اشتراک‌گذاری شماره", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await call.message.answer(
            "روی دکمه زیر کلیک کن یا شماره‌ات رو بفرست:",
            reply_markup=kb
        )
        await call.answer()


@router.message(FreeTrial.waiting_phone, F.contact)
async def trial_phone_contact(message: types.Message, state: FSMContext):
    phone = normalize_phone(message.contact.phone_number)
    await state.clear()
    cfg = await run_db(get_trial_config)
    await _process_trial_phone(message, phone, cfg)


@router.message(FreeTrial.waiting_phone, F.text)
async def trial_phone_text(message: types.Message, state: FSMContext):
    phone = normalize_phone(message.text)
    if not phone.startswith("09") or len(phone) != 11:
        await message.answer("❌ شماره نامعتبر. مثلاً: 09123456789")
        return
    await state.clear()
    cfg = await run_db(get_trial_config)
    await _process_trial_phone(message, phone, cfg)


async def _process_trial_phone(message: types.Message, phone: str, cfg):
    user_id = message.from_user.id
    username = message.from_user.username or "ندارد"
    use_count = await run_db(get_trial_use_count, phone)
    max_uses = await run_db(get_phone_max_uses, phone)

    if use_count >= max_uses:
        await message.answer(
            f"❌ شماره {phone} قبلاً از تست رایگان استفاده کرده.\n"
            f"(استفاده‌های انجام‌شده: {use_count}/{max_uses})",
            reply_markup=home_button_kb()
        )
        return

    await run_db(set_user_phone, user_id, phone)
    await _give_free_trial(message, user_id, username, phone, cfg)


async def _give_free_trial(message, user_id: int, username: str, phone: str, cfg):
    import io
    import qrcode as qrcode_lib
    from aiogram.types import BufferedInputFile
    from panel import create_vpn_account

    is_enabled, duration_days, data_limit_gb, require_referral, min_referrals, default_max_uses, panel_id, panel_group_ids = cfg
    panel_id = panel_id or 1

    # گروه‌های PasarGuard انتخاب‌شده برای تست رایگان — برای 3x-ui خالی و
    # بی‌اثره؛ برای PasarGuard اگه اینجا خالی باشه، اکانت تست بدون هیچ
    # Group ای ساخته می‌شه و کانفیگ/پروکسی واقعی نخواهد داشت.
    group_ids = [x.strip() for x in (panel_group_ids or "").split(",") if x.strip().isdigit()]

    await run_db(record_trial_use, phone, user_id)

    sep = "─" * 22
    await message.answer(
        f"✅ تست رایگان فعال شد!\n{sep}\n"
        f"📱 شماره: {phone}\n"
        f"⏳ مدت: {duration_days} روز\n"
        f"{format_data(data_limit_gb)}\n{sep}\n"
        f"⏳ در حال ساخت اکانت VPN...",
        reply_markup=home_button_kb()
    )

    await notify_admins(
        message.bot,
        f"🧪 تست رایگان جدید!\n"
        f"👤 User: {user_id} (@{username})\n"
        f"📱 شماره: {phone}\n"
        f"⏳ {duration_days} روز | {data_label_short(data_limit_gb)}"
    )

    # ایمیل و گروه پنل با تابع مرکزی آماده می‌شن (همون منطقی که برای خرید عادی و
    # پلن دلخواه هم استفاده می‌شه، تا شمارنده‌ی برند و گروه‌بندی یکپارچه بمونه)
    email, group = await prepare_new_client(user_id)
    result = await create_vpn_account(
        user_id, email, duration_days, float(data_limit_gb),
        group=group, panel_id=panel_id, inbound_ids=group_ids or None
    )

    if result:
        await run_db(save_vpn_account,
            user_id=user_id,
            email=result["email"],
            uuid=None,
            inbound_id=None,
            expire_time=result["expire_time"],
            data_limit=result["data_limit"],
            is_trial=True,
            sub_id=result.get("sub_id"),
            sub_url=result.get("sub_url"),
            panel_id=panel_id
        )
        import datetime
        import html
        expire_date = datetime.datetime.fromtimestamp(result["expire_time"] / 1000).strftime('%Y-%m-%d')
        # HTML به‌جای Markdown استفاده می‌شه چون اگه sub_path/دامنه‌ی پنل حاوی
        # کاراکتری مثل _ باشه، Markdown نسخه‌ی قدیمی با خطای "can't find end of
        # the entity" کل پیام رو رد می‌کنه (مشابه باگی که در وضعیت سرویس‌ها بود)
        safe_sub_url = html.escape(result["sub_url"])
        caption = (
            f"✅ اکانت تست VPN آماده شد!\n{sep}\n"
            f"🔗 لینک سابسکریپشن:\n"
            f"<code>{safe_sub_url}</code>\n"
            f"{sep}\n"
            f"📅 انقضا: {expire_date}\n"
            f"{format_data(data_limit_gb)}\n{sep}\n"
            f"⚙️ این لینک رو داخل نرم‌افزار VPN خودت وارد کن."
        )
        qr = qrcode_lib.QRCode(box_size=10, border=4)
        qr.add_data(result["sub_url"])
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        await message.bot.send_photo(
            user_id,
            photo=BufferedInputFile(buf.read(), filename="vpn_qr.png"),
            caption=caption,
            parse_mode="HTML",
            reply_markup=home_button_kb()
        )
    else:
        await message.bot.send_message(
            user_id,
            "⚠️ تست رایگان ثبت شد ولی ساخت اکانت VPN با مشکل مواجه شد.\n"
            "ادمین به زودی اکانتت رو می‌سازه.",
            reply_markup=home_button_kb()
        )


# ================================================================
# REFERRAL PANEL
# ================================================================

@router.callback_query(F.data == "menu:referral")
async def referral_panel(call: types.CallbackQuery):
    await _render_referral_panel(call)


async def _render_referral_panel(call: types.CallbackQuery):
    user_id = call.from_user.id
    ref_cfg = await run_db(get_referral_config)
    is_enabled, reward_join, first_purchase_reward, reward_purchase, reward_pct = ref_cfg

    ref_count, total_reward = await run_db(get_referral_stats, user_id)
    bot_info = await call.bot.get_me()
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
        if first_purchase_reward > 0:
            text += f"  • اولین خرید: {first_purchase_reward:,} تومان\n"
        if reward_purchase > 0:
            text += f"  • خریدهای بعدی (ثابت): {reward_purchase:,} تومان\n"
        if reward_pct > 0:
            text += f"  • خریدهای بعدی (درصدی): {reward_pct}% مبلغ خرید\n"
        if reward_join == 0 and first_purchase_reward == 0 and reward_purchase == 0 and reward_pct == 0:
            text += "  • در حال حاضر پاداشی تنظیم نشده.\n"
    else:
        text += "⚠️ سیستم رفرال فعلاً غیرفعاله."

    buttons = [
        [InlineKeyboardButton(text="📋 تاریخچه پاداش‌ها", callback_data="ref:history")],
        [InlineKeyboardButton(text="👥 لیست زیرمجموعه‌ها", callback_data="ref:list")],
        [InlineKeyboardButton(text="🏠 بازگشت به خانه", callback_data="menu:home")],
    ]
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await call.answer()


@router.callback_query(F.data == "ref:history")
async def ref_history(call: types.CallbackQuery):
    rewards = await run_db(get_referral_rewards_history, call.from_user.id)
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
    refs = await run_db(get_referrals, call.from_user.id)
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
    await _render_referral_panel(call)