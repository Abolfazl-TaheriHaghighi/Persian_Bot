# راهنمای نصب و راه‌اندازی

## ۱. پیش‌نیازها

### Python
- نسخه **3.11** یا بالاتر
- دانلود: https://www.python.org/downloads/

### PostgreSQL
- نسخه **14** یا بالاتر
- دانلود (ویندوز): https://www.postgresql.org/download/windows/
- دانلود (اوبونتو): `sudo apt install postgresql postgresql-contrib`

---

## ۲. نصب کتابخونه‌ها

```bash
pip install -r requirements.txt
```

یا دستی:

```bash
pip install aiogram==3.7.0
pip install psycopg2-binary
pip install python-dotenv
pip install aiohttp
pip install cryptography
pip install "qrcode[pil]"
pip install Pillow
```

---

## ۳. ساخت دیتابیس

```sql
-- وارد PostgreSQL بشو
psql -U postgres

-- دیتابیس بساز
CREATE DATABASE vpnbot;

-- خروج
\q
```

---

## ۴. تنظیم فایل .env

فایل `.env.example` رو کپی کن و اسمش رو `.env` بذار:

```bash
cp .env.example .env
```

بعد مقادیر رو پر کن:

```env
BOT_TOKEN=توکن_ربات_از_BotFather
ADMIN_ID=آیدی_عددی_تلگرام_خودت

DB_NAME=vpnbot
DB_USER=postgres
DB_PASSWORD=پسورد_دیتابیس
DB_HOST=localhost
DB_PORT=5432

# فقط برای خودت بذار — مشتری نداره
MASTER_KEY=یه_رشته_تصادفی_بلند

# برای ساخت مقدار تصادفی:
# python -c "import secrets; print(secrets.token_hex(32))"
LICENSE_SIGN_KEY=یه_رشته_تصادفی_دیگه
```

---

## ۵. اجرای ربات

```bash
python bot.py
```

---

## ۶. اجرا به عنوان سرویس (لینوکس)

```bash
# فایل سرویس بساز
sudo nano /etc/systemd/system/vpnbot.service
```

محتوا:

```ini
[Unit]
Description=VPN Telegram Bot
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/anypartvpnbot
ExecStart=/usr/bin/python3 bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable vpnbot
sudo systemctl start vpnbot

# چک وضعیت
sudo systemctl status vpnbot

# لاگ‌ها
sudo journalctl -u vpnbot -f
```

---

## ساختار پروژه

```
anypartvpnbot/
├── bot.py
├── config.py
├── db.py
├── license.py
├── pro_guard.py
├── panel.py
├── keyboards.py
├── utils.py
├── states.py
├── generate_license.py
├── requirements.txt
├── .env
├── .env.example
├── .gitignore
└── handlers/
    ├── __init__.py
    ├── user.py
    ├── payments.py
    ├── services.py
    ├── referral.py
    ├── admin.py
    ├── partner.py
    ├── broadcast.py
    └── license_handler.py
```