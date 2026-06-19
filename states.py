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