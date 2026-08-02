import logging
import aiohttp

logger = logging.getLogger(__name__)

# تایم‌اوت مشترک برای همه‌ی درخواست‌های HTTP به پنل‌ها
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10, connect=5)


class BasePanelClient:
    """
    کلاس پایه‌ی abstract برای هر نوع پنل (3x-ui، PasarGuard و هر پنل جدیدی که
    بعداً اضافه بشه). هر پنل جدید فقط باید از این کلاس ارث‌بری کنه و متدهای
    زیر رو پیاده‌سازی کنه.
    """

    def __init__(self, cfg: tuple):
        # cfg tuple index mapping from db.get_panel(panel_id):
        # 0: id, 1: name, 2: panel_type, 3: panel_url, 4: auth_type, 5: username,
        # 6: password, 7: api_key, 8: panel_path, 9: sub_port, 10: sub_path
        # نکته: ستون inbound_id عمداً حذف شده — انتخاب Inbound (در 3x-ui) یا
        # Node (در PasarGuard) همیشه خودکاره و از تنظیمات پیش‌فرض خودِ پنل
        # می‌آد، نه یک مقدار دستی که اینجا نگه داشته بشه.
        self.panel_id = cfg[0]
        self.name = cfg[1]
        self.panel_type = cfg[2] or "3x-ui"
        self.base_url = (cfg[3] or "").rstrip("/")
        self.auth_type = cfg[4]
        self.username = cfg[5]
        self.password = cfg[6]
        self.api_key = cfg[7]
        self.panel_path = cfg[8] or ""
        self.sub_port = cfg[9] if len(cfg) > 9 and cfg[9] else None
        self.sub_path = cfg[10] if len(cfg) > 10 and cfg[10] else "sub"

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