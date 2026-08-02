import logging
import time
import uuid as uuid_lib
import aiohttp
from urllib.parse import urlparse, quote

from .base import BasePanelClient, _REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


class ThreeXUIClient(BasePanelClient):
    """کلاینت اختصاصی پنل 3x-ui (Legacy)"""

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