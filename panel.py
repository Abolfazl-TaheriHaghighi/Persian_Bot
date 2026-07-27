import asyncio
import logging
import aiohttp
import uuid as uuid_lib
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, quote

from utils import run_db

logger = logging.getLogger(__name__)

_SESSION_TTL = timedelta(hours=23)
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10, connect=5)


class BasePanelClient:
    def __init__(self, cfg: tuple):
        # cfg tuple index mapping from db.get_panel(panel_id):
        # 0: id, 1: name, 2: panel_type, 3: panel_url, 4: auth_type, 5: username, 
        # 6: password, 7: api_key, 8: inbound_id, 9: panel_path, 10: sub_port, 11: sub_path
        self.panel_id = cfg[0]
        self.name = cfg[1]
        self.panel_type = cfg[2] or "3x-ui"
        self.base_url = (cfg[3] or "").rstrip("/")
        self.auth_type = cfg[4]
        self.username = cfg[5]
        self.password = cfg[6]
        self.api_key = cfg[7]
        self.inbound_id = cfg[8]
        self.panel_path = cfg[9] or ""
        self.sub_port = cfg[10] if len(cfg) > 10 and cfg[10] else None
        self.sub_path = cfg[11] if len(cfg) > 11 and cfg[11] else "sub"

    async def get_inbounds(self) -> list:
        raise NotImplementedError

    async def add_client(self, email: str, duration_days: int, data_limit_gb: float, inbound_ids: list | None = None) -> dict | None:
        raise NotImplementedError

    async def renew_client(self, email: str, add_days: int = 0, add_bytes: int = 0) -> dict | None:
        raise NotImplementedError

    async def get_client_stat(self, email: str) -> dict | None:
        raise NotImplementedError

    async def set_client_group(self, email: str, group: str) -> bool:
        raise NotImplementedError

    async def set_client_enable(self, email: str, enable: bool) -> bool:
        raise NotImplementedError


# =====================================================================
# 3x-ui Client (Legacy)
# =====================================================================
class ThreeXUIClient(BasePanelClient):
    def _url(self, path: str) -> str:
        return f"{self.base_url}{self.panel_path}{path}"

    def _sub_url(self, sub_id: str) -> str:
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
                resp = await session.get(self._url(path), headers=self._headers(), ssl=False)
                try:
                    return await resp.json()
                except aiohttp.ContentTypeError:
                    return None
        except Exception as e:
            logger.warning(f"3x-ui GET error on {path}: {e}")
            return None

    async def _post(self, path: str, payload: dict) -> dict | None:
        try:
            async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session:
                resp = await session.post(self._url(path), headers=self._headers(), json=payload, ssl=False)
                try:
                    return await resp.json()
                except aiohttp.ContentTypeError:
                    return None
        except Exception as e:
            logger.warning(f"3x-ui POST error on {path}: {e}")
            return None

    async def get_inbounds(self) -> list:
        data = await self._get("/panel/api/inbounds/list")
        if data and data.get("success"):
            return data.get("obj", [])
        return []

    async def get_all_inbound_ids(self) -> list:
        inbounds = await self.get_inbounds()
        return [ib["id"] for ib in inbounds if ib.get("enable", True)]

    async def add_client(self, email: str, duration_days: int, data_limit_gb: float, inbound_ids: list | None = None) -> dict | None:
        if duration_days <= 0:
            return None

        sub_id = uuid_lib.uuid4().hex[:16]
        expire_ms = int((time.time() + duration_days * 86400) * 1000)
        data_limit_bytes = int(data_limit_gb * 1024 ** 3) if data_limit_gb > 0 else 0

        if not inbound_ids:
            inbound_ids = await self.get_all_inbound_ids()
        if not inbound_ids and self.inbound_id:
            inbound_ids = [int(self.inbound_id) if str(self.inbound_id).isdigit() else self.inbound_id]
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
        payload = {"emails": [email]}
        if add_days:
            payload["addDays"] = add_days
        if add_bytes:
            payload["addBytes"] = add_bytes
        if len(payload) == 1:
            return None

        data = await self._post("/panel/api/clients/bulkAdjust", payload)
        if not data or not data.get("success"):
            return None
        return {"success": True, "adjusted": data.get("obj")}

    async def get_client_stat(self, email: str) -> dict | None:
        safe_email = quote(email, safe="")
        data = await self._get(f"/panel/api/clients/traffic/{safe_email}")
        if data and data.get("success"):
            return data.get("obj")
        return None

    async def set_client_group(self, email: str, group: str) -> bool:
        if not group:
            return True
        data = await self._post("/panel/api/clients/groups/bulkAdd", {
            "emails": [email],
            "group": group,
        })
        return bool(data and data.get("success"))

    async def set_client_enable(self, email: str, enable: bool) -> bool:
        stat = await self.get_client_stat(email)
        if not stat:
            return False

        current_expiry = stat.get("expiryTime") or 0
        if current_expiry <= 0:
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
            return False
        return True


# =====================================================================
# PasarGuard Client
# =====================================================================
class PasarguardClient(BasePanelClient):
    def __init__(self, cfg: tuple):
        super().__init__(cfg)
        self._access_token = None
        self._token_expires_at = 0

    async def _get_token(self) -> str | None:
        now = time.time()
        if self._access_token and now < self._token_expires_at:
            return self._access_token

        payload = {"username": self.username, "password": self.password}
        try:
            async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session:
                resp = await session.post(f"{self.base_url}/api/admin/token", data=payload, ssl=False)
                if resp.status == 200:
                    data = await resp.json()
                    self._access_token = data.get("access_token")
                    self._token_expires_at = now + 3000
                    return self._access_token
                else:
                    logger.error(f"Pasarguard login failed: {resp.status} - {await resp.text()}")
                    return None
        except Exception as e:
            logger.error(f"Pasarguard login error: {e}")
            return None

    async def _headers(self) -> dict | None:
        token = await self._get_token()
        if not token:
            return None
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }

    def _sub_url(self, sub_id: str) -> str:
        parsed = urlparse(self.base_url)
        sub_base = f"{parsed.scheme}://{parsed.hostname}:{self.sub_port}" if self.sub_port else self.base_url
        return f"{sub_base}/{self.sub_path}/{sub_id}"

    async def _request(self, method: str, path: str, payload: dict = None) -> dict | None:
        headers = await self._headers()
        if not headers:
            return None
        url = f"{self.base_url}{path}"
        try:
            async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session:
                if method == "GET":
                    resp = await session.get(url, headers=headers, ssl=False)
                elif method == "POST":
                    resp = await session.post(url, headers=headers, json=payload, ssl=False)
                elif method == "PUT":
                    resp = await session.put(url, headers=headers, json=payload, ssl=False)
                else:
                    return None
                
                if resp.status in (200, 201):
                    return await resp.json()
                else:
                    logger.warning(f"Pasarguard {method} {path} error: {resp.status} - {await resp.text()}")
                    return None
        except Exception as e:
            logger.error(f"Pasarguard {method} error on {path}: {e}")
            return None

    async def get_inbounds(self) -> list:
        data = await self._request("GET", "/api/nodes")
        if not data:
            return []
        
        nodes_list = []
        if isinstance(data, dict) and "nodes" in data and isinstance(data["nodes"], list):
            nodes_list = data["nodes"]
        elif isinstance(data, list):
            nodes_list = data

        return [{"id": n.get("id"), "remark": n.get("name") or f"Node {n.get('id')}"} for n in nodes_list if n.get("id") is not None]

    async def add_client(self, email: str, duration_days: int, data_limit_gb: float, inbound_ids: list | None = None) -> dict | None:
        if duration_days <= 0:
            return None

        # محاسبات زمانی با منطقه زمانی UTC برای هماهنگی با پاسارگارد
        expire_ms = int((time.time() + (duration_days * 86400)) * 1000)
        expire_dt = datetime.fromtimestamp(expire_ms / 1000.0, tz=timezone.utc)
        expire_str = expire_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        
        data_limit_bytes = int(data_limit_gb * 1024 ** 3) if data_limit_gb > 0 else 0

        payload = {
            "username": email,
            "data_limit": data_limit_bytes,
            "expire": expire_str,
            "status": "active",
            "proxies": {"vless": {}},
        }

        if inbound_ids:
            payload["node_ids"] = [int(i) for i in inbound_ids if str(i).isdigit()]
        elif self.inbound_id:
            payload["node_ids"] = [int(i) for i in str(self.inbound_id).split(',') if str(i).isdigit()]

        data = await self._request("POST", "/api/user/", payload=payload)
        if not data:
            return None

        # گرفتن خروجی خام API پاسارگارد (که معمولاً نسبی است)
        raw_sub_url = data.get("subscription_url", "")
        # استخراج UUID (بخش آخر لینک)
        sub_id = raw_sub_url.split("/")[-1] if raw_sub_url else ""
        
        # ترکیب اصولی آدرس پنل + پورت ساب (اگر تنظیم شده باشد) + UUID
        final_sub_url = self._sub_url(sub_id) if sub_id else ""

        return {
            "email": email,
            "sub_id": sub_id,
            "sub_url": final_sub_url,
            "expire_time": expire_ms,
            "data_limit": data_limit_bytes,
            "inbound_ids": inbound_ids,
        }

    async def get_client_stat(self, email: str) -> dict | None:
        data = await self._request("GET", f"/api/user/{quote(email, safe='')}")
        if not data:
            return None
        
        expire_str = data.get("expire")
        expire_ms = 0
        if expire_str:
            try:
                if expire_str.endswith("Z"):
                    expire_str = expire_str.replace("Z", "+00:00")
                dt = datetime.fromisoformat(expire_str)
                expire_ms = int(dt.timestamp() * 1000)
            except Exception as e:
                logger.error(f"Time parse error: {e}")

        return {
            "enable": data.get("status") == "active",
            "total": data.get("data_limit", 0),
            "up": data.get("used_traffic", 0),
            "down": 0,
            "expiryTime": expire_ms,
        }

    async def set_client_group(self, email: str, group: str) -> bool:
        if not group:
            return True
        payload = {"note": group}
        resp = await self._request("PUT", f"/api/user/{quote(email, safe='')}", payload=payload)
        return bool(resp)

    async def set_client_enable(self, email: str, enable: bool) -> bool:
        payload = {"status": "active" if enable else "disabled"}
        resp = await self._request("PUT", f"/api/user/{quote(email, safe='')}", payload=payload)
        return bool(resp)


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
            if not cfg or not cfg[3]: # cfg[3] is panel_url
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