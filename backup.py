import asyncio
import gzip
import logging
import os
import shutil
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.types import FSInputFile

from config import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT
from db import get_backup_config, update_backup_last_run
from utils import run_db

logger = logging.getLogger(__name__)


_BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")


_TELEGRAM_MAX_FILE_BYTES = 50 * 1024 * 1024

_AUTO_CHECK_INTERVAL_SECONDS = 3600


async def create_db_dump() -> str:

    if shutil.which("pg_dump") is None:
        raise RuntimeError(
            "دستور pg_dump روی این سرور پیدا نشد. با "
            "'sudo apt install postgresql-client' نصبش کن."
        )

    os.makedirs(_BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sql_path = os.path.join(_BACKUP_DIR, f"backup_{timestamp}.sql")
    gz_path = f"{sql_path}.gz"


    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASSWORD or ""

    cmd = [
        "pg_dump",
        "-h", DB_HOST,
        "-p", str(DB_PORT),
        "-U", DB_USER,
        "-d", DB_NAME,
        "-F", "p",  
        "-f", sql_path,
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()

    if process.returncode != 0:
        if os.path.exists(sql_path):
            os.remove(sql_path)
        error_msg = stderr.decode(errors="ignore").strip() or "خطای نامشخص از pg_dump"
        raise RuntimeError(f"pg_dump شکست خورد: {error_msg}")

    def _compress_and_cleanup():
        with open(sql_path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        os.remove(sql_path)

    await run_db(_compress_and_cleanup)

    return gz_path


async def send_backup_now(bot_token: str, admin_id: int) -> tuple[bool, str]:

    dump_path = None
    try:
        dump_path = await create_db_dump()
    except Exception as e:
        logger.error(f"Backup dump creation failed: {e}")
        return False, f"❌ خطا در ساخت بکاپ:\n{e}"

    try:
        file_size = os.path.getsize(dump_path)
        if file_size > _TELEGRAM_MAX_FILE_BYTES:
            size_mb = file_size / (1024 * 1024)
            return False, (
                f"❌ حجم بکاپ ({size_mb:.1f} مگابایت) از سقف ۵۰ مگابایتی تلگرام "
                f"برای ارسال فایل توسط بات‌ها بیشتره.\n"
                f"باید بکاپ رو مستقیم از سرور (فایل داخل پوشه‌ی backups/) دانلود کنی."
            )

        async with Bot(token=bot_token) as backup_bot:
            caption = (
                f"💾 بکاپ دیتابیس {DB_NAME}\n"
                f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await backup_bot.send_document(
                chat_id=admin_id,
                document=FSInputFile(dump_path),
                caption=caption,
            )
        return True, "✅ بکاپ با موفقیت گرفته و ارسال شد."

    except Exception as e:
        logger.error(f"Backup send failed: {e}")
        return False, (
            f"❌ خطا در ارسال بکاپ:\n{e}\n\n"
            f"نکته: مطمئن شو که آیدی ادمین گیرنده حداقل یک‌بار به ربات بکاپ /start زده باشه، "
            f"وگرنه تلگرام اجازه‌ی شروع مکالمه از سمت بات رو نمی‌ده."
        )
    finally:
        if dump_path and os.path.exists(dump_path):
            try:
                os.remove(dump_path)
            except Exception:
                pass


async def auto_backup_loop():

    while True:
        try:
            cfg = await run_db(get_backup_config)
            if cfg:
                bot_token, admin_id, interval_hours, last_backup_at = cfg
                if bot_token and admin_id and interval_hours and interval_hours > 0:
                    now = datetime.now()
                    due = (last_backup_at is None) or (
                        (now - last_backup_at) >= timedelta(hours=interval_hours)
                    )
                    if due:
                        ok, msg = await send_backup_now(bot_token, admin_id)
                        if ok:
                            await run_db(update_backup_last_run)
                        logger.info(f"Auto backup result: success={ok} - {msg}")
        except Exception as e:
            logger.error(f"Auto backup loop error: {e}")

        await asyncio.sleep(_AUTO_CHECK_INTERVAL_SECONDS)