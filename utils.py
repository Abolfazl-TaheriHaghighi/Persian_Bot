def format_data(gb) -> str:
    if float(gb) == 0:
        return "♾ نامحدود"
    gb = float(gb)
    if gb < 1:
        mb = round(gb * 1024)
        return f"📶 {mb} مگابایت"
    if gb == int(gb):
        return f"📶 {int(gb)} گیگابایت"
    return f"📶 {gb:g} گیگابایت"


def data_label_short(gb) -> str:
    gb = float(gb)
    if gb == 0:
        return "∞"
    if gb < 1:
        return f"{round(gb*1024)}MB"
    return f"{gb:g}GB"


def normalize_phone(phone: str) -> str:
    """نرمال‌سازی شماره تلفن به فرمت 09xxxxxxxxx"""
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("+98"):
        phone = "0" + phone[3:]
    elif phone.startswith("98") and len(phone) == 12:
        phone = "0" + phone[2:]
    return phone