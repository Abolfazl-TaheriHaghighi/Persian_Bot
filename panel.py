import aiohttp
import uuid as uuid_lib
import time
from db import get_panel_config


class PanelClient:
    """کلاینت API برای پنل 3x-ui"""

    def __init__(self):
        cfg = get_panel_config()
        if not cfg or not cfg[0]:
            raise ValueError("پنل تنظیم نشده")

        self.base_url = cfg[0].rstrip("/")
        self.auth_type = cfg[1]
        self.username = cfg[2]
        self.password = cfg[3]
        self.api_key = cfg[4]
        self.inbound_id = cfg[5]
        self.panel_path = cfg[6] or ""
        self.session_cookie = None

    def _url(self, path: str) -> str:
        return f"{self.base_url}{self.panel_path}{path}"

    def _headers(self) -> dict:
        if self.auth_type == "apikey":
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}

    async def login(self) -> bool:
        if self.auth_type == "apikey":
            return True
        async with aiohttp.ClientSession() as session:
            try:
                resp = await session.post(
                    self._url("/login"),
                    json={"username": self.username, "password": self.password},
                    ssl=False
                )
                data = await resp.json()
                if data.get("success"):
                    self.session_cookie = resp.cookies
                    return True
                return False
            except Exception:
                return False

    async def get_inbounds(self) -> list:
        async with aiohttp.ClientSession(cookies=self.session_cookie) as session:
            try:
                resp = await session.get(
                    self._url("/panel/api/inbounds/list"),
                    headers=self._headers(),
                    ssl=False
                )
                data = await resp.json()
                return data.get("obj", []) if data.get("success") else []
            except Exception:
                return []

    async def add_client(
        self,
        inbound_id: int,
        email: str,
        duration_days: int,
        data_limit_gb: float
    ) -> dict | None:
        client_uuid = str(uuid_lib.uuid4())
        sub_id = uuid_lib.uuid4().hex[:16]  # subId برای سابسکریپشن
        expire_ms = int((time.time() + duration_days * 86400) * 1000)
        data_limit_bytes = int(data_limit_gb * 1024 ** 3) if data_limit_gb > 0 else 0

        import json
        client_obj = {
            "id": client_uuid,
            "email": email,
            "enable": True,
            "expiryTime": expire_ms,
            "totalGB": data_limit_bytes,
            "limitIp": 0,
            "tgId": "",
            "subId": sub_id
        }
        client_data = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [client_obj]})
        }

        async with aiohttp.ClientSession(cookies=self.session_cookie) as session:
            try:
                resp = await session.post(
                    self._url("/panel/api/inbounds/addClient"),
                    json=client_data,
                    headers=self._headers(),
                    ssl=False
                )
                data = await resp.json()
                if data.get("success"):
                    sub_url = f"{self.base_url}{self.panel_path}/sub/{sub_id}"
                    return {
                        "uuid": client_uuid,
                        "email": email,
                        "sub_id": sub_id,
                        "sub_url": sub_url,
                        "expire_time": expire_ms,
                        "data_limit": data_limit_bytes,
                        "inbound_id": inbound_id
                    }
                return None
            except Exception:
                return None

    async def get_client_stat(self, email: str) -> dict | None:
        async with aiohttp.ClientSession(cookies=self.session_cookie) as session:
            try:
                resp = await session.get(
                    self._url(f"/panel/api/inbounds/getClientTraffics/{email}"),
                    headers=self._headers(),
                    ssl=False
                )
                data = await resp.json()
                return data.get("obj") if data.get("success") else None
            except Exception:
                return None


async def _get_client() -> PanelClient | None:
    try:
        client = PanelClient()
    except ValueError:
        return None

    # در حالت رایگان فقط یوزر/پس مجازه
    if client.auth_type == "apikey":
        from pro_guard import is_pro
        if not is_pro():
            return None

    if client.auth_type == "userpass":
        ok = await client.login()
        if not ok:
            return None
    return client


async def create_vpn_account(user_id: int, email: str, duration_days: int, data_limit_gb: float) -> dict | None:
    client = await _get_client()
    if not client or not client.inbound_id:
        return None
    return await client.add_client(client.inbound_id, email, duration_days, data_limit_gb)


async def get_client_status(email: str) -> dict | None:
    client = await _get_client()
    if not client:
        return None
    return await client.get_client_stat(email)


async def test_panel_connection() -> tuple[bool, str]:
    try:
        client = PanelClient()
    except ValueError:
        return False, "پنل تنظیم نشده"
    if client.auth_type == "userpass":
        ok = await client.login()
        if not ok:
            return False, "لاگین ناموفق — یوزر/پس رو چک کن"
    inbounds = await client.get_inbounds()
    if inbounds is not None:
        return True, f"✅ اتصال برقرار | {len(inbounds)} inbound پیدا شد"
    return False, "خطا در اتصال"


async def get_inbound_list() -> list:
    client = await _get_client()
    if not client:
        return []
    return await client.get_inbounds()