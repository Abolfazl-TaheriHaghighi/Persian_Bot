import asyncio
import logging
import aiohttp
import uuid as uuid_lib
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse, quote

from db import get_panel_config
from utils import run_db

logger = logging.getLogger(__name__)

_SESSION_TTL = timedelta(hours=23)

# تایم‌اوت مشخص برای همه‌ی درخواست‌های پنل — بدون این، aiohttp تا ۵ دقیقه
# منتظر می‌مونه و باعث می‌شه بات کاملاً هنگ به نظر برسه
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10, connect=5)

# طول پیش‌نمایش بدنه‌ی پاسخ در لاگ، تا پاسخ‌های بزرگ (مثل HTML کامل) لاگ رو شلوغ نکنن
_BODY_PREVIEW_LEN = 200


class PanelClient:
    def __init__(self, cfg: tuple):
        # نکته: یوزر/پس کاملاً حذف شد — این پنل همیشه با API Key وصل می‌شه.
        self.base_url = cfg[0].rstrip("/")
        self.auth_type = cfg[1]
        self.api_key = cfg[4]
        self.inbound_id = cfg[5]
        self.panel_path = cfg[6] or ""
        # sub_port و sub_path برای ساخت لینک subscription
        self.sub_port = cfg[7] if len(cfg) > 7 and cfg[7] else None
        self.sub_path = cfg[8] if len(cfg) > 8 and cfg[8] else "sub"

    def _url(self, path: str) -> str:
        return f"{self.base_url}{self.panel_path}{path}"

    def _sub_url(self, sub_id: str) -> str:
        """ساخت لینک subscription با پورت و path جداگانه"""
        parsed = urlparse(self.base_url)
        if self.sub_port:
            sub_base = f"{parsed.scheme}://{parsed.hostname}:{self.sub_port}"
        else:
            sub_base = self.base_url
        return f"{sub_base}/{self.sub_path}/{sub_id}"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }

    async def _get(self, path: str) -> dict | None:
        try:
            async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session:
                resp = await session.get(
                    self._url(path), headers=self._headers(), ssl=False
                )
                try:
                    return await resp.json()
                except aiohttp.ContentTypeError:
                    body_preview = (await resp.text())[:_BODY_PREVIEW_LEN]
                    logger.warning(
                        f"Panel GET non-JSON response on {path} "
                        f"(status={resp.status}, content-type={resp.content_type!r}): {body_preview!r}"
                    )
                    return None
        except asyncio.TimeoutError:
            logger.warning(f"Panel GET timed out: {path}")
            return None
        except aiohttp.ClientError as e:
            logger.warning(f"Panel GET connection error on {path}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Panel GET unexpected error on {path}: {e}")
            return None

    async def _post(self, path: str, payload: dict) -> dict | None:
        try:
            async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session:
                resp = await session.post(
                    self._url(path), headers=self._headers(), json=payload, ssl=False
                )
                try:
                    return await resp.json()
                except aiohttp.ContentTypeError:
                    body_preview = (await resp.text())[:_BODY_PREVIEW_LEN]
                    logger.warning(
                        f"Panel POST non-JSON response on {path} "
                        f"(status={resp.status}, content-type={resp.content_type!r}): {body_preview!r}"
                    )
                    return None
        except asyncio.TimeoutError:
            logger.warning(f"Panel POST timed out: {path}")
            return None
        except aiohttp.ClientError as e:
            logger.warning(f"Panel POST connection error on {path}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Panel POST unexpected error on {path}: {e}")
            return None

    async def get_inbounds(self) -> list:
        data = await self._get("/panel/api/inbounds/list")
        if data and data.get("success"):
            return data.get("obj", [])
        return []

    async def get_all_inbound_ids(self) -> list:
        inbounds = await self.get_inbounds()
        return [ib["id"] for ib in inbounds if ib.get("enable", True)]

    async def add_client(
        self, email: str, duration_days: int, data_limit_gb: float,
        inbound_ids: list | None = None,
    ) -> dict | None:
        # 🐛 لایه‌ی دفاعی نهایی برای یه باگ واقعی و خطرناک که رخ داده بود:
        # اگه duration_days به هر دلیلی (فرم ادمین، دیتای دستکاری‌شده، باگ
        # آینده‌ی هرجای دیگه‌ی کد) صفر یا منفی به اینجا برسه، هرگز نباید به
        # پنل فرستاده بشه — چون این پنل expiryTime=0 رو "نامحدود برای همیشه"
        # می‌سازه. برخلاف data_limit_gb=0 (که "حجم نامحدود" یه قابلیت عمدیه)،
        # duration_days=0 هیچ‌وقت یه قصد معتبر نیست. این چک مستقل از هر
        # اعتبارسنجی بالادستیه، تا این کلاس باگ دیگه از هیچ مسیری تکرار نشه.
        if duration_days <= 0:
            logger.error(
                f"add_client BLOCKED: duration_days={duration_days!r} for email={email!r} — "
                f"refusing to create a client with zero/negative duration (panel treats "
                f"expiryTime<=0 as UNLIMITED FOREVER). Check the caller for a data bug."
            )
            return None

        sub_id = uuid_lib.uuid4().hex[:16]
        expire_ms = int((time.time() + duration_days * 86400) * 1000)
        data_limit_bytes = int(data_limit_gb * 1024 ** 3) if data_limit_gb > 0 else 0

        if not inbound_ids:
            inbound_ids = await self.get_all_inbound_ids()
        if not inbound_ids and self.inbound_id:
            inbound_ids = [self.inbound_id]
        if not inbound_ids:
            return None

        payload = {
            "client": {
                "email": email,
                "totalGB": data_limit_bytes,
                "expiryTime": expire_ms,
                "tgId": 0,
                "limitIp": 0,
                "enable": True,
                "subId": sub_id,
            },
            "inboundIds": inbound_ids,
        }

        data = await self._post("/panel/api/clients/add", payload)
        if not data or not data.get("success"):
            return None

        return {
            "email": email,
            "sub_id": sub_id,
            "sub_url": self._sub_url(sub_id),
            "expire_time": expire_ms,
            "data_limit": data_limit_bytes,
            "inbound_ids": inbound_ids,
        }

    async def renew_client(self, email: str, add_days: int = 0, add_bytes: int = 0) -> dict | None:
        """
        تمدید اشتراک (افزایش مدت/حجم) از طریق endpoint اختصاصی bulkAdjust.
        برخلاف add_client/update که مقادیر رو *جایگزین* می‌کنن، این endpoint
        به مقدار فعلی expiry/حجم *اضافه* می‌کنه. طبق داکیومنت پنل، اگه فقط
        افزایش روز مدنظره نباید addBytes رو اصلاً بفرستیم (و برعکس) — برای
        همین اینجا هرکدوم صفر/خالی بود از payload حذف می‌شه، نه با مقدار 0.
        """
        payload = {"emails": [email]}
        if add_days:
            payload["addDays"] = add_days
        if add_bytes:
            payload["addBytes"] = add_bytes
        if len(payload) == 1:  # نه addDays نه addBytes
            return None

        data = await self._post("/panel/api/clients/bulkAdjust", payload)
        if not data or not data.get("success"):
            return None
        return {"success": True, "adjusted": data.get("obj")}

    async def get_client_stat(self, email: str) -> dict | None:
        # نکته: طبق داکیومنت رسمی API این پنل، مسیر ترافیک کلاینت زیر Clients است
        # نه Inbounds — مسیر قدیمی /panel/api/inbounds/getClientTraffics/{email}
        # روی این پنل اصلاً وجود نداره و ۴۰۴ (صفحه‌ی HTML) برمی‌گردونه.
        # نکته‌ی امنیتی: email می‌تونه شامل ایموجی/یونیکد باشه (نام‌گذاری اختصاصی
        # همکاران) — quote() اینو برای قرار گرفتن امن توی مسیر URL انکود می‌کنه.
        safe_email = quote(email, safe="")
        data = await self._get(f"/panel/api/clients/traffic/{safe_email}")
        if data and data.get("success"):
            return data.get("obj")
        return None

    async def set_client_group(self, email: str, group: str) -> bool:
        """
        اضافه کردن کلاینت به یک گروه در پنل (قسمت "گروه" کلاینت).
        طبق داکیومنت پنل، اگه گروه از قبل وجود نداشته باشه خودکار ساخته می‌شه.
        نکته: ساختار دقیق body این endpoint در داکیومنت مشخص نشده بود؛ اینجا بر اساس
        الگوی سایر endpoint های bulk (که آرایه‌ی "emails" می‌گیرن) حدس زده شده.
        اگه گروه روی پنل درست ست نشد، لاگ WARNING مربوط به _post دقیقاً پاسخ واقعی
        سرور رو نشون می‌ده تا فیلدها اصلاح بشن.
        """
        if not group:
            return True
        data = await self._post("/panel/api/clients/groups/bulkAdd", {
            "emails": [email],
            "group": group,
        })
        return bool(data and data.get("success"))

    async def set_client_enable(self, email: str, enable: bool) -> bool:
        """
        فعال/غیرفعال کردن یک کلاینت.

        🐛 باگ واقعی که اینجا رخ داده بود و حالا رفع شده: نسخه‌ی قبلی این
        تابع، رکورد فعلی کلاینت رو از GET /panel/api/clients/get/{email}
        می‌خوند و همون آبجکت (فقط با enable عوض‌شده) رو به‌عنوان بدنه‌ی
        POST /panel/api/clients/update/{email} می‌فرستاد. مشکل این بود که
        ساختار/نام فیلدهای برگشتی GET هیچ‌وقت واقعاً تأیید نشده بود و ظاهراً
        با چیزی که update انتظار داره (totalGB, expiryTime) یکی نبود —
        نتیجه این می‌شد که این دو فیلد یا اصلاً به update نمی‌رسیدن یا با
        نام اشتباه می‌رسیدن، و پنل مقادیر گم‌شده رو با پیش‌فرض 0 پر می‌کرد.
        چون این پنل 0 رو «نامحدود» تفسیر می‌کنه، هر بار روشن/خاموش کردن
        یک سرویس، کل مدت و حجمش رو نامحدود می‌کرد.

        رفع قطعی: به‌جای GET /clients/get (که ساختارش تأیید نشده)، از
        GET /clients/traffic/{email} استفاده می‌شه — همون endpoint ترافیکی
        که ساختارش قبلاً کامل تأیید شده (up, down, total, expiryTime,
        enable) و همه‌جای دیگه‌ی پروژه هم روش تکیه شده. payload آپدیت هم
        دستی و دقیقاً با نام فیلدهایی که خودِ endpoint آپدیت مستند کرده
        (email, totalGB, expiryTime, tgId, enable) ساخته می‌شه.
        """
        stat = await self.get_client_stat(email)
        if not stat:
            logger.warning(f"set_client_enable: could not fetch current traffic/stat for email={email!r}")
            return False

        current_expiry = stat.get("expiryTime") or 0
        # لایه‌ی ایمنی حیاتی: اگه expiryTime واقعیِ فعلی صفر/نامعتبر برگرده،
        # اصلاً toggle نکن — چون فرستادن همین صفر دقیقاً همون چیزیه که باعث
        # نامحدود شدن سرویس می‌شه. بهتره عملیات fail بشه تا این‌که این ریسک
        # دوباره تکرار بشه.
        if current_expiry <= 0:
            logger.error(
                f"set_client_enable BLOCKED: traffic endpoint returned invalid/zero "
                f"expiryTime={current_expiry!r} for email={email!r} — refusing to send "
                f"an update that could reset this client to UNLIMITED forever."
            )
            return False

        payload = {
            "email": email,
            "totalGB": stat.get("total") or 0,
            "expiryTime": current_expiry,
            "tgId": 0,
            "enable": enable,
        }

        safe_email = quote(email, safe="")
        data = await self._post(f"/panel/api/clients/update/{safe_email}", payload)
        if not data or not data.get("success"):
            logger.warning(
                f"set_client_enable: update failed for email={email!r} — "
                f"response={data!r}"
            )
            return False
        return True



# ── Cached Client ───────────────────────────────────────────────

class _ClientCache:
    def __init__(self):
        self._client: PanelClient | None = None
        self._logged_in_at: datetime | None = None
        self._lock = asyncio.Lock()

    def _is_valid(self) -> bool:
        if self._client is None or self._logged_in_at is None:
            return False
        return (datetime.now() - self._logged_in_at) < _SESSION_TTL

    def invalidate(self):
        self._client = None
        self._logged_in_at = None

    async def get(self) -> PanelClient | None:
        # نکته: یوزر/پس کاملاً حذف شد — این پنل همیشه با API Key وصل می‌شه
        # (لاگین کوکی‌محور دیگه پشتیبانی نمی‌شه، چون روی این پنل کار نمی‌کرد).
        # پس دیگه نیازی به مرحله‌ی login() نیست؛ API Key توی هدر هر
        # درخواست فرستاده می‌شه (رجوع به PanelClient._headers).
        async with self._lock:
            if self._is_valid():
                return self._client

            cfg = await run_db(get_panel_config)
            if not cfg or not cfg[0]:
                self._client = None
                return None

            client = PanelClient(cfg)
            self._client = client
            self._logged_in_at = datetime.now()
            return self._client


_cache = _ClientCache()


def invalidate_panel_cache():
    _cache.invalidate()


async def _get_client() -> PanelClient | None:
    return await _cache.get()


async def get_panel_client() -> PanelClient | None:
    """نسخه پابلیک _get_client — برای استفاده خارج از این ماژول"""
    return await _cache.get()


# ── Public API ──────────────────────────────────────────────────

async def create_vpn_account(
    user_id: int, email: str, duration_days: int, data_limit_gb: float,
    group: str | None = None,
) -> dict | None:
    client = await _get_client()
    if not client:
        return None

    result = await client.add_client(email, duration_days, data_limit_gb)

    if result and group:
        ok = await client.set_client_group(email, group)
        if not ok:
            logger.warning(f"Failed to set panel group '{group}' for client {email}")

    return result


async def renew_vpn_account(email: str, add_days: int = 0, add_bytes: int = 0) -> bool:
    """تمدید (افزایش مدت/حجم) یک کلاینت"""
    client = await _get_client()
    if not client:
        return False

    result = await client.renew_client(email, add_days, add_bytes)
    return bool(result and result.get("success"))


async def set_client_enable(email: str, enable: bool) -> bool:
    """
    فعال/غیرفعال کردن یک کلاینت روی پنل. توضیح کامل ریسک‌ها/روش کار در
    PanelClient.set_client_enable هست.
    """
    client = await _get_client()
    if not client:
        logger.warning("set_client_enable: no panel client available (not configured, or login/auth failed)")
        return False

    result = await client.set_client_enable(email, enable)
    return bool(result)


async def get_client_status(email: str) -> dict | None:
    client = await _get_client()
    if not client:
        return None

    return await client.get_client_stat(email)


async def test_panel_connection() -> tuple[bool, str]:
    cfg = await run_db(get_panel_config)
    if not cfg or not cfg[0]:
        return False, "پنل تنظیم نشده"

    client = PanelClient(cfg)

    if not client.api_key:
        return False, "❌ API Key وارد نشده"

    inbounds = await client.get_inbounds()
    _cache.invalidate()

    if inbounds:
        ids = [str(ib.get("id")) for ib in inbounds[:5]]
        sub_example = client._sub_url("EXAMPLE")
        return True, (
            f"✅ اتصال برقرار\n"
            f"📡 {len(inbounds)} inbound پیدا شد\n"
            f"🔢 IDs: {', '.join(ids)}{'...' if len(inbounds) > 5 else ''}\n"
            f"🔗 نمونه sub: {sub_example}"
        )
    else:
        return False, (
            f"❌ اتصال برقرار ولی inbound دریافت نشد\n"
            f"دسترسی API رو چک کن"
        )


async def get_inbound_list() -> list:
    client = await _get_client()
    if not client:
        return []
    return await client.get_inbounds()