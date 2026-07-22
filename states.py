from aiogram.fsm.state import State, StatesGroup


class DepositStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_receipt = State()


class RejectReason(StatesGroup):
    waiting_for_reason = State()


class AdminAddCategory(StatesGroup):
    name = State()
    emoji = State()


class AdminAddService(StatesGroup):
    category = State()
    name = State()
    description = State()
    price = State()
    duration = State()
    data_limit = State()


class AdminEditService(StatesGroup):
    choosing_field = State()
    entering_value = State()


class AdminEditBalance(StatesGroup):
    user_id = State()
    amount = State()


class AdminDiscountCode(StatesGroup):
    code = State()
    discount_type = State()
    discount_value = State()
    max_uses = State()


class ApplyDiscount(StatesGroup):
    waiting_for_code = State()


class FreeTrial(StatesGroup):
    waiting_phone = State()


class AdminTrialConfig(StatesGroup):
    choosing_field = State()
    entering_value = State()


class AdminPhoneOverride(StatesGroup):
    phone = State()
    max_uses = State()


class AdminReferralConfig(StatesGroup):
    choosing_field = State()
    entering_value = State()


class AdminAddChannel(StatesGroup):
    channel_id = State()
    title = State()
    invite_link = State()


class AdminPanelConfig(StatesGroup):
    choosing_field = State()
    entering_value = State()


class PartnerRequest(StatesGroup):
    waiting_phone = State()
    waiting_description = State()


class AdminPartnerApprove(StatesGroup):
    waiting_message = State()


class AdminPartnerReject(StatesGroup):
    waiting_message = State()


class AdminAddPartnerManual(StatesGroup):
    waiting_user_id = State()
    waiting_phone = State()


class AdminBroadcast(StatesGroup):
    choosing_target = State()
    waiting_message = State()
    waiting_custom_ids = State()


# ---- پلن دلخواه: کاربر ----
class CustomPlanOrder(StatesGroup):
    waiting_gb = State()
    waiting_days = State()
    waiting_discount = State()


# ---- پلن دلخواه: ادمین ----
class AdminCustomCategory(StatesGroup):
    name = State()


class AdminAddCustomGroup(StatesGroup):
    name = State()
    emoji = State()


class AdminEditCustomGroup(StatesGroup):
    choosing_field = State()
    entering_value = State()


class AdminCustomAccessAdd(StatesGroup):
    waiting_input = State()


class AdminCustomAccessRemove(StatesGroup):
    waiting_input = State()


# ---- نام‌گذاری خودکار کلاینت‌ها (برند + شمارنده) ----
class AdminClientNaming(StatesGroup):
    waiting_prefix = State()
    waiting_default_group = State()


# ---- برچسب گروه اختصاصی هر همکار ----
class AdminPartnerGroupLabel(StatesGroup):
    waiting_label = State()


# ---- تنظیمات پشتیبان‌گیری از دیتابیس ----
class AdminBackupConfig(StatesGroup):
    waiting_bot_token = State()
    waiting_admin_id = State()
    waiting_interval = State()


# ---- نام‌گذاری اختصاصی ایمیل هر همکار (پیشوند + ایموجی + شمارنده‌ی خودش) ----
class AdminPartnerEmailNaming(StatesGroup):
    waiting_emoji = State()
    waiting_prefix = State()


# ---- مسدودسازی یک دسته‌بندی برای کاربر خاص (deny-list) ----
class AdminCategoryBlockAdd(StatesGroup):
    waiting_input = State()


# ---- مدیریت روش‌های پرداخت شارژ حساب ----
class AdminPaymentMethod(StatesGroup):
    waiting_title = State()
    waiting_instructions = State()


class AdminEditPaymentMethod(StatesGroup):
    entering_value = State()


class AdminPaymentCard(StatesGroup):
    waiting_card_number = State()
    waiting_holder_name = State()


class AdminEditPaymentCard(StatesGroup):
    entering_value = State()


# ---- نام برند ربات (شخصی‌سازی متن‌های کاربری) ----
class AdminBrandName(StatesGroup):
    waiting_name = State()


# ---- تمدید دستی اشتراک توسط ادمین (با ایمیل/آیدی کلاینت) ----
class AdminRenewClient(StatesGroup):
    waiting_email = State()
    waiting_days = State()
    waiting_gb = State()


# ---- متن خوش‌آمدگویی سفارشی (/start) ----
class AdminWelcomeText(StatesGroup):
    waiting_text = State()


# ---- متن سفارشی صفحه‌ی «خانه» ----
class AdminHomeText(StatesGroup):
    waiting_text = State()