import os
import json
import hashlib
import hmac
import base64
from datetime import datetime, timedelta
from cryptography.fernet import Fernet, InvalidToken


def _ev(h: str) -> str:
    for k, v in os.environ.items():
        if hashlib.sha256(k.encode()).hexdigest() == h:
            return v
    return ""


_H1 = "be1172bd82399f58cdee47c558c720119ba9ee92674ebac60fbebd1fbfb6752b"
_H2 = "9592de5f0c25abf62a5888a73b9e716032a0ffaa14ee62aed73e1100bab83d83"


def _fernet() -> Fernet:
    raw = hashlib.sha256((_ev(_H1) or "default").encode()).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


def _auth(v: str) -> bool:
    ref = _ev(_H2)
    if not ref or not v:
        return False
    return hmac.compare_digest(
        hashlib.sha256(v.encode()).digest(),
        hashlib.sha256(ref.encode()).digest()
    )


def _decode(token: str, iid: str) -> dict:
    try:
        p = json.loads(_fernet().decrypt(token.encode()).decode())
    except Exception:
        return {"ok": False, "e": "inv"}
    if p.get("i") != iid:
        return {"ok": False, "e": "mis"}
    exp = p.get("x")
    if exp is None:
        return {"ok": True, "x": None, "d": None, "p": True}
    dt = datetime.strptime(exp, "%Y-%m-%d")
    left = (dt - datetime.now()).days
    if left < 0:
        return {"ok": False, "e": "exp", "x": exp}
    return {"ok": True, "x": exp, "d": left, "p": False}


def get_instance_id(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def generate_license(bot_token: str, days: int) -> str:
    iid = get_instance_id(bot_token)
    exp = None if days == 0 else (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    payload = json.dumps({"i": iid, "x": exp, "t": datetime.now().strftime("%Y-%m-%d")})
    return _fernet().encrypt(payload.encode()).decode()


def verify_license(key: str, bot_token: str) -> dict:
    if _auth(key):
        return {"valid": True, "is_pro": True, "expire_date": None,
                "days_left": None, "error": None, "permanent": True}
    r = _decode(key, get_instance_id(bot_token))
    if not r["ok"]:
        msgs = {"inv": "لایسنس نامعتبر", "mis": "این لایسنس برای ربات دیگه‌ایه", "exp": "لایسنس منقضی شده"}
        return {"valid": False, "is_pro": False, "expire_date": r.get("x"),
                "days_left": 0, "error": msgs.get(r["e"], "خطا")}
    return {"valid": True, "is_pro": True, "expire_date": r.get("x"),
            "days_left": r.get("d"), "error": None, "permanent": r.get("p", False)}


def check_license_from_db(bot_token: str) -> dict:
    """
    sync — باید از run_db صدا زده بشه.
    MASTER_KEY چک CPU-only هست (بدون DB).
    DB فقط وقتی MASTER_KEY نیست صدا زده میشه.
    """
    if _auth(_ev(_H2)):
        return {"valid": True, "is_pro": True, "expire_date": None,
                "days_left": None, "error": None, "permanent": True}
    # این بخش DB call داره — کل تابع باید از run_db اجرا بشه
    from db import get_license_key
    key = get_license_key()
    if not key:
        return {"valid": False, "is_pro": False, "expire_date": None,
                "days_left": None, "error": "لایسنس وارد نشده"}
    return verify_license(key, bot_token)


# ── cache 30 دقیقه‌ای ──────────────────────────────────────────
_C: dict = {}
_CT: datetime | None = None


def is_pro(bot_token: str) -> bool:
    """
    sync — فقط cache چک می‌کنه.
    DB call نداره مگه cache منقضی شده باشه.
    وقتی cache منقضیه، DB از طریق check_license_from_db صدا زده میشه.
    چون is_pro از pro_guard.py در async context استفاده میشه،
    cache باید همیشه warm باشه (توسط run_db(check_license_from_db) در bot.py و daily_check).
    """
    global _C, _CT
    now = datetime.now()
    if _CT and (now - _CT) < timedelta(minutes=30):
        return _C.get("is_pro", False)
    # cache سرد — فقط MASTER_KEY چک می‌کنیم (بدون DB)
    if _auth(_ev(_H2)):
        _C = {"is_pro": True, "valid": True, "permanent": True}
        _CT = now
        return True
    # اگه cache سرده و master نیستیم، آخرین نتیجه رو برمی‌گردونیم
    # (DB call نمی‌کنیم — async context نیست)
    return _C.get("is_pro", False)


def warm_cache(bot_token: str) -> None:
    """DB call می‌کنه — فقط از sync context یا run_db صدا زده بشه"""
    global _C, _CT
    _C = check_license_from_db(bot_token)
    _CT = datetime.now()


def clear_cache():
    global _C, _CT
    _C = {}
    _CT = None