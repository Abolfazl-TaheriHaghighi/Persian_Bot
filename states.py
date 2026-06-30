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