# پیش‌نیازهای سیستمی

## Python
- نسخه: **3.11 یا بالاتر**
- دانلود: https://www.python.org/downloads/

## PostgreSQL
- نسخه: **14 یا بالاتر**
- دانلود ویندوز: https://www.postgresql.org/download/windows/
- نصب اوبونتو:
  ```bash
  sudo apt update
  sudo apt install postgresql postgresql-contrib
  ```

## کتابخونه‌های پایتون
نصب همه با یه دستور:
```bash
pip install -r requirements.txt
```

| کتابخونه | نسخه | کاربرد |
|----------|-------|---------|
| aiogram | 3.7.0 | فریم‌ورک ربات تلگرام |
| psycopg2-binary | 2.9+ | اتصال به PostgreSQL |
| python-dotenv | 1.0+ | خواندن فایل .env |
| aiohttp | 3.9+ | درخواست HTTP به پنل VPN |
| cryptography | 42.0+ | رمزنگاری لایسنس |
| qrcode[pil] | 7.4+ | ساخت QR Code |
| Pillow | 10.0+ | پردازش تصویر QR |

## سیستم‌عامل
- **لینوکس (توصیه‌شده):** Ubuntu 22.04 LTS
- **ویندوز:** پشتیبانی می‌شه (برای توسعه)

## حداقل منابع سرور
- CPU: 1 هسته
- RAM: 1 GB
- Storage: 20 GB
