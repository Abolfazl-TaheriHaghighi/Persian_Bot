import logging
import time
import aiohttp
from datetime import datetime, timezone
from urllib.parse import urlparse, quote

from .base import BasePanelClient, _REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


class PasarguardClient(BasePanelClient):
    """کلاینت اختصاصی پنل PasarGuard"""

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