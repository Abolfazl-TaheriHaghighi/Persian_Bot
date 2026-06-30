import asyncio
import aiohttp
import uuid as uuid_lib
import time
import json
from datetime import datetime, timedelta
from urllib.parse import urlparse

from db import get_panel_config
from utils import run_db

_SESSION_TTL = timedelta(hours=23)


class PanelClient:
    def __init__(self, cfg: tuple):
        self.base_url = cfg[0].rstrip("/")
        self.auth_type = cfg[1]
        self.username = cfg[2]
        self.password = cfg[3]
        self.api_key = cfg[4]
        self.inbound_id = cfg[5]
        self.panel_path = cfg[6] or ""
        # sub_port و sub_path برای ساخت لینک subscription
        self.sub_port = cfg[7] if len(cfg) > 7 and cfg[7] else None
        self.sub_path = cfg[8] if len(cfg) > 8 and cfg[8] else "sub"
        self.session_cookie = None

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
        if self.auth_type == "apikey":
            return {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "accept": "application/json",
            }
        return {"Content-Type": "application/json", "accept": "application/json"}

    async def login(self) -> bool:
        if self.auth_type == "apikey":
            return True
        async with aiohttp.ClientSession() as session:
            try:
                # 3x-ui login با form-data (نه JSON)
                resp = await session.post(
                    self._url("/login"),
                    data={"username": self.username, "password": self.password},
                    ssl=False
                )
                data = await resp.json()
                if data.get("success"):
                    self.session_cookie = resp.cookies
                    return True
                return False
            except Exception:
                return False

    async def _get(self, path: str) -> dict | None:
        async with aiohttp.ClientSession(cookies=self.session_cookie) as session:
            try:
                resp = await session.get(
                    self._url(path), headers=self._headers(), ssl=False
                )
                return await resp.json()
            except Exception:
                return None

    async def _post(self, path: str, payload: dict) -> dict | None:
        async with aiohttp.ClientSession(cookies=self.session_cookie) as session:
            try:
                resp = await session.post(
                    self._url(path), headers=self._headers(), json=payload, ssl=False
                )
                return await resp.json()
            except Exception:
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

    async def get_client_stat(self, email: str) -> dict | None:
        data = await self._get(f"/panel/api/inbounds/getClientTraffics/{email}")
        if data and data.get("success"):
            return data.get("obj")
        return None


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
        async with self._lock:
            if self._is_valid():
                return self._client

            cfg = await run_db(get_panel_config)
            if not cfg or not cfg[0]:
                self._client = None
                return None

            client = PanelClient(cfg)

            if client.auth_type == "apikey":
                from pro_guard import is_pro
                if not is_pro():
                    self._client = None
                    return None
                self._client = client
                self._logged_in_at = datetime.now()
                return self._client

            ok = await client.login()
            if not ok:
                self._client = None
                return None

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

async def create_vpn_account(user_id: int, email: str, duration_days: int, data_limit_gb: float) -> dict | None:
    client = await _get_client()
    if not client:
        return None
    result = await client.add_client(email, duration_days, data_limit_gb)
    if result is None:
        _cache.invalidate()
        client = await _get_client()
        if client:
            result = await client.add_client(email, duration_days, data_limit_gb)
    return result


async def get_client_status(email: str) -> dict | None:
    client = await _get_client()
    if not client:
        return None
    result = await client.get_client_stat(email)
    if result is None:
        _cache.invalidate()
        client = await _get_client()
        if client:
            result = await client.get_client_stat(email)
    return result


async def test_panel_connection() -> tuple[bool, str]:
    cfg = await run_db(get_panel_config)
    if not cfg or not cfg[0]:
        return False, "پنل تنظیم نشده"

    client = PanelClient(cfg)

    if client.auth_type == "userpass":
        ok = await client.login()
        if not ok:
            return False, (
                f"❌ لاگین ناموفق\n"
                f"🌐 URL: {client.base_url}{client.panel_path}/login\n"
                f"یوزر/پس رو چک کن (به حروف کوچیک/بزرگ حساسه)"
            )
    elif client.auth_type == "apikey":
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