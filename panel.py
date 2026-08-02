import asyncio
import logging
from datetime import datetime, timedelta

from utils import run_db
from panels.base import BasePanelClient
from panels.threexui import ThreeXUIClient
from panels.pasarguard import PasarguardClient

logger = logging.getLogger(__name__)

_SESSION_TTL = timedelta(hours=23)


# ── Multi-Panel Cached Client ───────────────────────────────────

class _ClientCache:
    def __init__(self):
        # نگهداری سشن‌های لاگین شده بر اساس panel_id
        self._clients = {}
        self._lock = asyncio.Lock()

    def _is_valid(self, panel_id: int) -> bool:
        record = self._clients.get(panel_id)
        if not record or not record.get("client") or not record.get("logged_in_at"):
            return False
        return (datetime.now() - record["logged_in_at"]) < _SESSION_TTL

    def invalidate(self, panel_id: int = None):
        if panel_id is not None:
            self._clients.pop(panel_id, None)
        else:
            self._clients.clear()

    async def get(self, panel_id: int) -> BasePanelClient | None:
        async with self._lock:
            if self._is_valid(panel_id):
                return self._clients[panel_id]["client"]

            from db import get_panel
            cfg = await run_db(get_panel, panel_id)
            if not cfg or not cfg[3]:  # cfg[3] is panel_url
                return None

            panel_type = cfg[2] or "3x-ui"
            if panel_type.lower() == "pasarguard":
                client = PasarguardClient(cfg)
            else:
                client = ThreeXUIClient(cfg)

            self._clients[panel_id] = {
                "client": client,
                "logged_in_at": datetime.now()
            }
            return client


_cache = _ClientCache()

def invalidate_panel_cache(panel_id: int = None):
    _cache.invalidate(panel_id)


async def get_panel_client(panel_id: int = 1) -> BasePanelClient | None:
    return await _cache.get(panel_id)


# ── Public API ──────────────────────────────────────────────────
# تمام این توابع برای حفظ کارکرد قدیمی ربات تا قبل از اعمال مرحله‌ی بعد،
# مقدار پیش‌فرض panel_id=1 را می‌پذیرند.

async def create_vpn_account(
    user_id: int, email: str, duration_days: int, data_limit_gb: float,
    group: str | None = None, panel_id: int = 1
) -> dict | None:
    client = await get_panel_client(panel_id)
    if not client:
        return None

    result = await client.add_client(email, duration_days, data_limit_gb)

    if result and group:
        ok = await client.set_client_group(email, group)
        if not ok:
            logger.warning(f"Failed to set panel group '{group}' for client {email} on panel {panel_id}")

    return result


async def renew_vpn_account(email: str, add_days: int = 0, add_bytes: int = 0, panel_id: int = 1) -> bool:
    client = await get_panel_client(panel_id)
    if not client:
        return False

    result = await client.renew_client(email, add_days, add_bytes)
    return bool(result and result.get("success"))


async def set_client_enable(email: str, enable: bool, panel_id: int = 1) -> bool:
    client = await get_panel_client(panel_id)
    if not client:
        logger.warning(f"set_client_enable: no panel client available for ID {panel_id}")
        return False

    result = await client.set_client_enable(email, enable)
    return bool(result)


async def get_client_status(email: str, panel_id: int = 1) -> dict | None:
    client = await get_panel_client(panel_id)
    if not client:
        return None

    return await client.get_client_stat(email)


async def test_panel_connection(panel_id: int = 1) -> tuple[bool, str]:
    from db import get_panel
    cfg = await run_db(get_panel, panel_id)
    if not cfg or not cfg[3]:
        return False, "پنل تنظیم نشده"

    panel_type = cfg[2] or "3x-ui"

    if panel_type.lower() == "pasarguard":
        client = PasarguardClient(cfg)
        if not client.username or not client.password:
            return False, "❌ نام کاربری و رمز عبور برای PasarGuard وارد نشده"
    else:
        client = ThreeXUIClient(cfg)
        if not client.api_key:
            return False, "❌ API Key وارد نشده"

    inbounds = await client.get_inbounds()
    _cache.invalidate(panel_id)

    # تغییر مهم در شرط زیر انجام شده تا لیست خالی را متصل در نظر نگیرد
    if inbounds:
        ids = [str(ib.get("id")) for ib in inbounds[:5]]
        dummy_id = "test-sub-id" if panel_type == "3x-ui" else "proxy/test"
        try:
            sub_example = client._sub_url(dummy_id)
        except AttributeError:
            sub_example = "نامشخص در این پنل"

        return True, (
            f"✅ اتصال برقرار\n"
            f"نوع پنل: {panel_type.upper()}\n"
            f"📡 {len(inbounds)} رکورد/نود پیدا شد\n"
            f"🔢 IDs: {', '.join(ids)}{'...' if len(inbounds) > 5 else ''}\n"
            f"🔗 نمونه sub: {sub_example}"
        )
    else:
        return False, (
            f"❌ ارتباط با سرور برقرار شد اما هیچ Inbound/Node ای پیدا نشد!\n"
            f"احتمالات:\n"
            f"۱. هنوز در پنل خود هیچ نود/اینباندی نساخته‌اید.\n"
            f"۲. آدرس یا پورت API در تنظیمات اشتباه است."
        )


async def get_inbound_list(panel_id: int = 1) -> list:
    client = await get_panel_client(panel_id)
    if not client:
        return []
    return await client.get_inbounds()