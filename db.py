import time
import psycopg2
from config import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT


def connect():
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )


def init_db():
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id BIGINT PRIMARY KEY,
            balance INTEGER DEFAULT 0,
            referred_by BIGINT DEFAULT NULL,
            phone TEXT DEFAULT NULL,
            joined_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            amount INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    # روش پرداختی که کاربر برای این تراکنش انتخاب کرده (برای اطلاع ادمین)
    cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS payment_method_id INTEGER")

    # ---- روش‌های پرداخت شارژ حساب (قابل افزودن/ویرایش/حذف توسط ادمین) ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payment_methods (
            id SERIAL PRIMARY KEY
        )
    """)
    # نکته: چون CREATE TABLE IF NOT EXISTS اگه جدولی با این اسم از قبل (با ساختار
    # متفاوت/ناقص) وجود داشته باشه هیچ ستونی اضافه نمی‌کنه، همه‌ی ستون‌ها رو صریحاً
    # با ALTER تضمین می‌کنیم — دقیقاً همون الگویی که برای بقیه‌ی جدول‌های این پروژه هم رعایت شده
    cur.execute("ALTER TABLE payment_methods ADD COLUMN IF NOT EXISTS title TEXT NOT NULL DEFAULT ''")
    cur.execute("ALTER TABLE payment_methods ADD COLUMN IF NOT EXISTS instructions TEXT DEFAULT ''")
    cur.execute("ALTER TABLE payment_methods ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE")
    cur.execute("ALTER TABLE payment_methods ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0")

    # ---- کارت‌های بانکی هر روش پرداخت (یک روش می‌تونه چند کارت داشته باشه) ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payment_method_cards (
            id SERIAL PRIMARY KEY
        )
    """)
    cur.execute("ALTER TABLE payment_method_cards ADD COLUMN IF NOT EXISTS method_id INTEGER REFERENCES payment_methods(id) ON DELETE CASCADE")
    cur.execute("ALTER TABLE payment_method_cards ADD COLUMN IF NOT EXISTS card_number TEXT NOT NULL DEFAULT ''")
    cur.execute("ALTER TABLE payment_method_cards ADD COLUMN IF NOT EXISTS holder_name TEXT NOT NULL DEFAULT ''")
    cur.execute("ALTER TABLE payment_method_cards ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE")
    cur.execute("ALTER TABLE payment_method_cards ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            emoji TEXT DEFAULT '📦',
            is_active BOOLEAN DEFAULT TRUE,
            sort_order INTEGER DEFAULT 0,
            is_custom BOOLEAN DEFAULT FALSE
        )
    """)
    cur.execute("ALTER TABLE categories ADD COLUMN IF NOT EXISTS is_custom BOOLEAN DEFAULT FALSE")

    # ---- لیست دسترسی سفارشی دسته‌بندی (وقتی visibility = 'custom') ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS category_custom_access (
            id SERIAL PRIMARY KEY,
            category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL,
            UNIQUE(category_id, user_id)
        )
    """)

    # ---- مسدودسازی دسته‌بندی برای کاربر خاص (deny-list) ----
    # برخلاف category_custom_access (که یک allow-list برای visibility='custom' است)،
    # این جدول یک دسته‌بندیِ در حالت عادی قابل‌مشاهده (all/partners/users) رو فقط
    # برای یک یا چند کاربر خاص مخفی می‌کنه، بدون اینکه روی بقیه‌ی کاربرها اثر بگذاره.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS category_blocked_users (
            id SERIAL PRIMARY KEY,
            category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL,
            UNIQUE(category_id, user_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id SERIAL PRIMARY KEY,
            category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            description TEXT,
            price INTEGER NOT NULL,
            duration_days INTEGER NOT NULL,
            data_limit_gb NUMERIC(10,2) NOT NULL DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE
        )
    """)

    # ---- زیرگروه‌های پلن دلخواه ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS custom_plan_groups (
            id SERIAL PRIMARY KEY,
            category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            emoji TEXT DEFAULT '🌍',
            price_per_gb INTEGER NOT NULL DEFAULT 0,
            price_per_day INTEGER NOT NULL DEFAULT 0,
            min_gb NUMERIC(10,2) NOT NULL DEFAULT 1,
            max_gb NUMERIC(10,2) NOT NULL DEFAULT 1000,
            min_days INTEGER NOT NULL DEFAULT 1,
            max_days INTEGER NOT NULL DEFAULT 365,
            inbound_ids TEXT DEFAULT '',
            is_active BOOLEAN DEFAULT TRUE,
            sort_order INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS purchases (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            service_id INTEGER,
            service_name TEXT,
            amount_paid INTEGER,
            purchased_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS discount_codes (
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            discount_type TEXT NOT NULL,
            discount_value NUMERIC(10,2) NOT NULL,
            max_uses INTEGER,
            used_count INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ---- تنظیمات ربات (کلید-مقدار) ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # ---- تنظیمات تست رایگان ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS free_trial_config (
            id INTEGER PRIMARY KEY DEFAULT 1,
            is_enabled BOOLEAN DEFAULT FALSE,
            duration_days INTEGER DEFAULT 7,
            data_limit_gb NUMERIC(10,2) DEFAULT 5,
            require_referral BOOLEAN DEFAULT FALSE,
            min_referrals INTEGER DEFAULT 0,
            default_max_uses INTEGER DEFAULT 1
        )
    """)
    # مقدار پیش‌فرض اگه رکورد نبود
    cur.execute("""
        INSERT INTO free_trial_config (id)
        VALUES (1)
        ON CONFLICT (id) DO NOTHING
    """)

    # ---- تست‌های دریافت‌شده (بر اساس شماره تلفن) ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS free_trial_uses (
            id SERIAL PRIMARY KEY,
            phone TEXT NOT NULL,
            telegram_id BIGINT NOT NULL,
            used_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ---- حداکثر تست مجاز برای هر شماره (override) ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS phone_trial_override (
            phone TEXT PRIMARY KEY,
            max_uses INTEGER NOT NULL
        )
    """)

    # ---- تنظیمات رفرال ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referral_config (
            id INTEGER PRIMARY KEY DEFAULT 1,
            is_enabled BOOLEAN DEFAULT FALSE,
            reward_on_join INTEGER DEFAULT 0,
            first_purchase_reward INTEGER DEFAULT 0,
            reward_on_purchase INTEGER DEFAULT 0,
            reward_purchase_percent NUMERIC(5,2) DEFAULT 0
        )
    """)
    cur.execute("""
        INSERT INTO referral_config (id)
        VALUES (1)
        ON CONFLICT (id) DO NOTHING
    """)
    cur.execute("ALTER TABLE referral_config ADD COLUMN IF NOT EXISTS first_purchase_reward INTEGER DEFAULT 0")

    # ---- تاریخچه پاداش‌های رفرال ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referral_rewards (
            id SERIAL PRIMARY KEY,
            referrer_id BIGINT NOT NULL,
            referred_id BIGINT NOT NULL,
            reward_type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ---- تنظیمات پنل VPN ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS panel_config (
            id INTEGER PRIMARY KEY DEFAULT 1,
            panel_url TEXT DEFAULT NULL,
            auth_type TEXT DEFAULT 'apikey',
            username TEXT DEFAULT NULL,
            password TEXT DEFAULT NULL,
            api_key TEXT DEFAULT NULL,
            inbound_id INTEGER DEFAULT NULL,
            panel_path TEXT DEFAULT '',
            sub_port INTEGER DEFAULT 2096,
            sub_path TEXT DEFAULT 'sub'
        )
    """)
    cur.execute("INSERT INTO panel_config (id) VALUES (1) ON CONFLICT (id) DO NOTHING")
    cur.execute("ALTER TABLE panel_config ADD COLUMN IF NOT EXISTS sub_port INTEGER DEFAULT 2096")
    cur.execute("ALTER TABLE panel_config ADD COLUMN IF NOT EXISTS sub_path TEXT DEFAULT 'sub'")
    # روی نصب‌های قبلی که sub_port هنوز NULL مونده (چون ستون قبلاً با پیش‌فرض
    # NULL ساخته شده بود)، مقدار پیش‌فرض ۲۰۹۶ رو الان اعمال می‌کنیم — طبق
    # درخواست که پورت لینک ساب از همون اولین اجرا از پیش ۲۰۹۶ باشه.
    cur.execute("UPDATE panel_config SET sub_port = 2096 WHERE sub_port IS NULL")

    # ---- اکانت‌های VPN ساخته‌شده ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vpn_accounts (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            purchase_id INTEGER,
            email TEXT NOT NULL,
            uuid TEXT,
            sub_id TEXT,
            sub_url TEXT,
            inbound_id INTEGER,
            expire_time BIGINT,
            data_limit BIGINT,
            created_at TIMESTAMP DEFAULT NOW(),
            is_trial BOOLEAN DEFAULT FALSE
        )
    """)
    cur.execute("ALTER TABLE vpn_accounts ADD COLUMN IF NOT EXISTS sub_id TEXT")
    cur.execute("ALTER TABLE vpn_accounts ADD COLUMN IF NOT EXISTS sub_url TEXT")
    cur.execute("ALTER TABLE vpn_accounts ADD COLUMN IF NOT EXISTS note TEXT")

    # migrations برای دیتابیس‌های قبلی
    cur.execute("ALTER TABLE services ADD COLUMN IF NOT EXISTS data_limit_gb NUMERIC(10,2) NOT NULL DEFAULT 0")
    cur.execute("ALTER TABLE services ALTER COLUMN data_limit_gb TYPE NUMERIC(10,2)")
    cur.execute("ALTER TABLE services ADD COLUMN IF NOT EXISTS category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT DEFAULT NULL")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT DEFAULT NULL")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS joined_at TIMESTAMP DEFAULT NOW()")

    # ---- همکاران ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS partners (
            id SERIAL PRIMARY KEY,
            user_id BIGINT UNIQUE NOT NULL,
            phone TEXT,
            description TEXT,
            status TEXT DEFAULT 'active',
            added_at TIMESTAMP DEFAULT NOW()
        )
    """)
    # برچسب گروهی که کلاینت‌های VPN این همکار روی پنل زیرش قرار می‌گیرن (قسمت "گروه")
    cur.execute("ALTER TABLE partners ADD COLUMN IF NOT EXISTS client_group_label TEXT DEFAULT NULL")
    # نام‌گذاری اختصاصی ایمیل کلاینت برای این همکار — پیشوند + ایموجی + شمارنده‌ی خودش
    # (جدا از شمارنده‌ی سراسری client_naming_config)
    cur.execute("ALTER TABLE partners ADD COLUMN IF NOT EXISTS email_prefix TEXT DEFAULT NULL")
    cur.execute("ALTER TABLE partners ADD COLUMN IF NOT EXISTS email_emoji TEXT DEFAULT NULL")
    cur.execute("ALTER TABLE partners ADD COLUMN IF NOT EXISTS email_counter INTEGER NOT NULL DEFAULT 0")

    # ---- درخواست‌های همکاری ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS partner_requests (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            phone TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ---- دسترسی دسته‌بندی‌ها ----
    cur.execute("""
        ALTER TABLE categories ADD COLUMN IF NOT EXISTS visibility TEXT DEFAULT 'all'
    """)

    # ---- کانال‌های اجباری ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS required_channels (
            id SERIAL PRIMARY KEY,
            channel_id TEXT NOT NULL,
            channel_username TEXT,
            channel_title TEXT,
            invite_link TEXT,
            is_active BOOLEAN DEFAULT TRUE
        )
    """)

    # ---- نام‌گذاری خودکار کلاینت‌ها (پیشوند برند + شمارنده‌ی اتمیک) ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS client_naming_config (
            id INTEGER PRIMARY KEY DEFAULT 1,
            prefix TEXT NOT NULL DEFAULT '',
            counter INTEGER NOT NULL DEFAULT 0
        )
    """)
    cur.execute("INSERT INTO client_naming_config (id) VALUES (1) ON CONFLICT (id) DO NOTHING")
    # برچسب گروه پیش‌فرض روی پنل برای کاربران عادی (غیر ادمین، غیر همکار)
    cur.execute("ALTER TABLE client_naming_config ADD COLUMN IF NOT EXISTS default_group TEXT NOT NULL DEFAULT ''")

    # ---- تنظیمات پشتیبان‌گیری از دیتابیس (بکاپ با ربات جداگانه) ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS backup_config (
            id INTEGER PRIMARY KEY DEFAULT 1,
            backup_bot_token TEXT DEFAULT NULL,
            backup_admin_id BIGINT DEFAULT NULL,
            auto_interval_hours INTEGER DEFAULT 0,
            last_backup_at TIMESTAMP DEFAULT NULL
        )
    """)
    cur.execute("INSERT INTO backup_config (id) VALUES (1) ON CONFLICT (id) DO NOTHING")

    # ---- تاریخچه‌ی تمدید اشتراک‌ها (هم مسیر کاربر/همکار، هم تمدید دستی ادمین) ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS renewals (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            purchase_id INTEGER REFERENCES purchases(id) ON DELETE SET NULL,
            client_email TEXT,
            amount_paid INTEGER NOT NULL DEFAULT 0,
            added_days INTEGER NOT NULL DEFAULT 0,
            added_bytes BIGINT NOT NULL DEFAULT 0,
            renewed_by BIGINT,
            renewed_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # ---- ارتقا برای پشتیبانی از چند پنل ----
    # اضافه کردن نام، نوع پنل و تغییر نوع inbound_id برای پشتیبانی از فرمت‌های مختلف (مثل پاسارگارد)
    cur.execute("ALTER TABLE panel_config ADD COLUMN IF NOT EXISTS name TEXT DEFAULT 'پنل اصلی'")
    cur.execute("ALTER TABLE panel_config ADD COLUMN IF NOT EXISTS panel_type TEXT DEFAULT '3x-ui'")
    cur.execute("ALTER TABLE panel_config ALTER COLUMN inbound_id TYPE TEXT USING inbound_id::TEXT")

    # تبدیل ستون id پنل به حالت افزایشی (Serial) برای افزودن پنل‌های جدید
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relkind = 'S' AND relname = 'panel_config_id_seq') THEN
                CREATE SEQUENCE panel_config_id_seq;
                ALTER TABLE panel_config ALTER COLUMN id SET DEFAULT nextval('panel_config_id_seq');
                PERFORM setval('panel_config_id_seq', COALESCE((SELECT MAX(id) FROM panel_config), 0) + 1, false);
            END IF;
        END $$;
    """)

    # ارتباط دسته‌بندی‌ها و اکانت‌ها با یک پنل خاص
    cur.execute("ALTER TABLE categories ADD COLUMN IF NOT EXISTS panel_id INTEGER REFERENCES panel_config(id) ON DELETE SET NULL")
    cur.execute("ALTER TABLE vpn_accounts ADD COLUMN IF NOT EXISTS panel_id INTEGER REFERENCES panel_config(id) ON DELETE SET NULL")

    conn.commit()
    conn.close()


# ================== USERS ==================

def add_user(user_id, referred_by=None):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (telegram_id, balance, referred_by)
        VALUES (%s, 0, %s)
        ON CONFLICT (telegram_id) DO NOTHING
    """, (user_id, referred_by))
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT telegram_id, balance, referred_by, phone FROM users WHERE telegram_id=%s", (user_id,))
    r = cur.fetchone()
    conn.close()
    return r


def get_balance(user_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE telegram_id=%s", (user_id,))
    r = cur.fetchone()
    conn.close()
    return r[0] if r else 0


def deduct_balance(user_id, amount):
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE telegram_id=%s FOR UPDATE", (user_id,))
    r = cur.fetchone()
    if not r or r[0] < amount:
        conn.close()
        return False
    cur.execute("UPDATE users SET balance = balance - %s WHERE telegram_id = %s", (amount, user_id))
    conn.commit()
    conn.close()
    return True


def get_all_users():
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT telegram_id, balance FROM users ORDER BY telegram_id")
    rows = cur.fetchall()
    conn.close()
    return rows


def set_balance(user_id, amount):
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = %s WHERE telegram_id = %s", (amount, user_id))
    conn.commit()
    conn.close()


def add_balance(user_id, amount):
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + %s WHERE telegram_id = %s", (amount, user_id))
    conn.commit()
    conn.close()


def set_user_phone(user_id, phone):
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE users SET phone=%s WHERE telegram_id=%s", (phone, user_id))
    conn.commit()
    conn.close()


def get_referral_count(user_id):
    """تعداد زیرمجموعه‌های مستقیم"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE referred_by=%s", (user_id,))
    r = cur.fetchone()
    conn.close()
    return r[0] if r else 0


def get_referrals(user_id):
    """لیست زیرمجموعه‌ها"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT telegram_id, balance, joined_at FROM users WHERE referred_by=%s ORDER BY joined_at DESC", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


# ================== TRANSACTIONS ==================

def create_transaction(user_id, amount, payment_method_id=None):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO transactions (user_id, amount, status, payment_method_id)
        VALUES (%s, %s, 'pending', %s) RETURNING id
    """, (user_id, amount, payment_method_id))
    tx_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return tx_id


def approve_transaction(tx_id, user_id, amount):
    conn = connect()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE transactions
        SET status = 'approved'
        WHERE id = %s
        AND status = 'pending'
        """,
        (tx_id,)
    )

    if cur.rowcount > 0:
        cur.execute(
            """
            UPDATE users
            SET balance = balance + %s
            WHERE telegram_id = %s
            """,
            (amount, user_id)
        )

    conn.commit()
    conn.close()


def reject_transaction(tx_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE transactions SET status = 'rejected' WHERE id = %s AND status = 'pending'", (tx_id,))
    conn.commit()
    conn.close()


def get_pending_transactions():
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, amount, created_at FROM transactions WHERE status = 'pending' ORDER BY created_at")
    rows = cur.fetchall()
    conn.close()
    return rows


# ================== PAYMENT METHODS (شارژ حساب) ==================

def get_active_payment_methods():
    """برای نمایش به کاربر — فقط روش‌های فعال"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT id, title FROM payment_methods WHERE is_active=TRUE ORDER BY sort_order, id")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_all_payment_methods():
    """برای مدیریت توسط ادمین — همه، فعال و غیرفعال"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT id, title, is_active, sort_order FROM payment_methods ORDER BY sort_order, id")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_payment_method(method_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT id, title, instructions, is_active FROM payment_methods WHERE id=%s", (method_id,))
    r = cur.fetchone()
    conn.close()
    return r


def add_payment_method(title: str, instructions: str = ""):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO payment_methods (title, instructions) VALUES (%s, %s) RETURNING id",
        (title, instructions)
    )
    mid = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return mid


def update_payment_method(method_id: int, field: str, value):
    allowed = {"title": "title", "instructions": "instructions"}
    col = allowed.get(field)
    if not col:
        return
    conn = connect()
    cur = conn.cursor()
    cur.execute(f"UPDATE payment_methods SET {col}=%s WHERE id=%s", (value, method_id))
    conn.commit()
    conn.close()


def toggle_payment_method(method_id: int):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE payment_methods SET is_active = NOT is_active WHERE id=%s RETURNING is_active",
        (method_id,)
    )
    r = cur.fetchone()
    conn.commit()
    conn.close()
    return r[0] if r else None


def delete_payment_method(method_id: int):
    """حذف کامل — کارت‌های زیرمجموعه هم به‌خاطر ON DELETE CASCADE خودکار حذف می‌شن"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM payment_methods WHERE id=%s", (method_id,))
    conn.commit()
    conn.close()


def get_method_cards(method_id: int, active_only: bool = True):
    conn = connect()
    cur = conn.cursor()
    if active_only:
        cur.execute("""
            SELECT id, card_number, holder_name, is_active
            FROM payment_method_cards WHERE method_id=%s AND is_active=TRUE
            ORDER BY sort_order, id
        """, (method_id,))
    else:
        cur.execute("""
            SELECT id, card_number, holder_name, is_active
            FROM payment_method_cards WHERE method_id=%s
            ORDER BY sort_order, id
        """, (method_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_card(card_id: int):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, method_id, card_number, holder_name, is_active FROM payment_method_cards WHERE id=%s",
        (card_id,)
    )
    r = cur.fetchone()
    conn.close()
    return r


def add_payment_card(method_id: int, card_number: str, holder_name: str):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO payment_method_cards (method_id, card_number, holder_name) VALUES (%s, %s, %s) RETURNING id",
        (method_id, card_number, holder_name)
    )
    cid = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return cid


def update_payment_card(card_id: int, field: str, value):
    allowed = {"card_number": "card_number", "holder_name": "holder_name"}
    col = allowed.get(field)
    if not col:
        return
    conn = connect()
    cur = conn.cursor()
    cur.execute(f"UPDATE payment_method_cards SET {col}=%s WHERE id=%s", (value, card_id))
    conn.commit()
    conn.close()


def toggle_payment_card(card_id: int):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE payment_method_cards SET is_active = NOT is_active WHERE id=%s RETURNING is_active",
        (card_id,)
    )
    r = cur.fetchone()
    conn.commit()
    conn.close()
    return r[0] if r else None


def delete_payment_card(card_id: int):
    conn = connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM payment_method_cards WHERE id=%s", (card_id,))
    conn.commit()
    conn.close()


# ================== CATEGORIES ==================

def get_all_categories(active_only=True):
    conn = connect()
    cur = conn.cursor()
    if active_only:
        cur.execute("SELECT id, name, emoji, is_custom FROM categories WHERE is_active=TRUE ORDER BY sort_order, id")
    else:
        cur.execute("SELECT id, name, emoji, is_active, sort_order, is_custom FROM categories ORDER BY sort_order, id")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_category(cat_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT id, name, emoji, is_active, is_custom FROM categories WHERE id=%s", (cat_id,))
    r = cur.fetchone()
    conn.close()
    return r


def add_category(name, emoji="📦", is_custom=False, panel_id=None):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO categories (name, emoji, is_custom, panel_id) VALUES (%s, %s, %s, %s) RETURNING id",
        (name, emoji, is_custom, panel_id)
    )
    cid = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return cid


def toggle_category(cat_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE categories SET is_active = NOT is_active WHERE id=%s RETURNING is_active", (cat_id,))
    r = cur.fetchone()
    conn.commit()
    conn.close()
    return r[0] if r else None


def delete_category(cat_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE services SET category_id=NULL WHERE category_id=%s", (cat_id,))
    cur.execute("DELETE FROM categories WHERE id=%s", (cat_id,))
    conn.commit()
    conn.close()


def get_category_full(cat_id):
    """گرفتن اطلاعات کامل دسته به همراه نام پنل متصل (برای منوی ادمین)"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.id, c.name, c.emoji, c.is_active, c.is_custom, c.panel_id, p.name as panel_name
        FROM categories c
        LEFT JOIN panel_config p ON c.panel_id = p.id
        WHERE c.id=%s
    """, (cat_id,))
    r = cur.fetchone()
    conn.close()
    return r

def update_category(cat_id, field, value):
    """ویرایش فیلدهای دسته‌بندی (نام یا پنل متصل)"""
    allowed = {"name": "name", "panel_id": "panel_id"}
    col = allowed.get(field)
    if not col:
        return
    conn = connect()
    cur = conn.cursor()
    cur.execute(f"UPDATE categories SET {col}=%s WHERE id=%s", (value, cat_id))
    conn.commit()
    conn.close()

# ================== SERVICES ==================

def get_services_by_category(cat_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, description, price, duration_days, data_limit_gb
        FROM services WHERE category_id=%s AND is_active=TRUE ORDER BY price
    """, (cat_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_all_services(active_only=True):
    conn = connect()
    cur = conn.cursor()
    if active_only:
        cur.execute("""
            SELECT s.id, s.name, s.description, s.price, s.duration_days, s.data_limit_gb,
                   COALESCE(c.name,'بدون دسته') as cat_name
            FROM services s LEFT JOIN categories c ON s.category_id=c.id
            WHERE s.is_active=TRUE ORDER BY s.price
        """)
    else:
        cur.execute("""
            SELECT s.id, s.name, s.description, s.price, s.duration_days, s.data_limit_gb,
                   s.is_active, COALESCE(c.name,'بدون دسته') as cat_name, s.category_id
            FROM services s LEFT JOIN categories c ON s.category_id=c.id
            ORDER BY s.id
        """)
    rows = cur.fetchall()
    conn.close()
    return rows


def get_service(service_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.id, s.name, s.description, s.price, s.duration_days, s.data_limit_gb,
               s.is_active, COALESCE(c.name,'') as cat_name, c.panel_id
        FROM services s LEFT JOIN categories c ON s.category_id=c.id
        WHERE s.id=%s
    """, (service_id,))
    r = cur.fetchone()
    conn.close()
    return r


def add_service(name, description, price, duration_days, data_limit_gb=0, category_id=None):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO services (name, description, price, duration_days, data_limit_gb, category_id)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
    """, (name, description, price, duration_days, data_limit_gb, category_id))
    sid = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return sid


def delete_service(service_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE services SET is_active=FALSE WHERE id=%s", (service_id,))
    conn.commit()
    conn.close()


def toggle_service(service_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE services SET is_active = NOT is_active WHERE id=%s RETURNING is_active", (service_id,))
    r = cur.fetchone()
    conn.commit()
    conn.close()
    return r[0] if r else None


def hard_delete_service(service_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM services WHERE id=%s", (service_id,))
    conn.commit()
    conn.close()


def update_service(service_id, field, value):
    field_map = {
        "name": "name",
        "description": "description",
        "price": "price",
        "duration": "duration_days",
        "data_limit": "data_limit_gb",
        "category": "category_id",
        "duration_days": "duration_days",
        "data_limit_gb": "data_limit_gb",
        "category_id": "category_id",
    }
    col = field_map.get(field)
    if not col:
        return
    conn = connect()
    cur = conn.cursor()
    cur.execute(f"UPDATE services SET {col}=%s WHERE id=%s", (value, service_id))
    conn.commit()
    conn.close()


# ================== PURCHASES ==================

def create_purchase(user_id, service_id, service_name, amount_paid):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO purchases (user_id, service_id, service_name, amount_paid)
        VALUES (%s, %s, %s, %s) RETURNING id
    """, (user_id, service_id, service_name, amount_paid))
    pid = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return pid


def get_user_purchases(user_id):
    """
    تمام خریدهای کاربر (بدون محدودیت تعداد) به همراه دسته‌بندی و ایمیل کلاینت VPN.
    نکته: v.email می‌تونه NULL باشه اگه ساخت اکانت VPN بعد از پرداخت با خطا مواجه
    شده باشه (مورد نادر، ولی از نظر دیتابیسی ممکنه).
    """
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.id, p.service_name, p.amount_paid, p.purchased_at,
               COALESCE(c.name, '—') as category_name,
               v.email
        FROM purchases p
        LEFT JOIN services s ON p.service_id = s.id
        LEFT JOIN categories c ON s.category_id = c.id
        LEFT JOIN vpn_accounts v ON v.purchase_id = p.id
        WHERE p.user_id=%s
        ORDER BY p.purchased_at DESC
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_user_stats(user_id):
    """
    آمار خلاصه برای صفحه‌ی «پروفایل من»: تعداد کل خریدها + تعداد سرویس‌های
    فعال. عمداً از COUNT() سبک استفاده شده (نه fetch کامل رکوردها) و «فعال»
    بر اساس expire_time محلی محاسبه می‌شه (نه تماس زنده با پنل) — چون اینجا
    فقط یک شمارشِ سریع لازمه، نه جزئیات لحظه‌ای، و رفتن سراغ پنل غیرضروری
    کندش می‌کنه. expire_time=NULL یا 0 یعنی نامحدود (همیشه فعال حساب می‌شه).
    """
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM purchases WHERE user_id=%s", (user_id,))
    total_purchases = cur.fetchone()[0]

    now_ms = int(time.time() * 1000)
    cur.execute("""
        SELECT COUNT(*) FROM vpn_accounts
        WHERE user_id=%s AND (expire_time IS NULL OR expire_time = 0 OR expire_time > %s)
    """, (user_id, now_ms))
    active_services = cur.fetchone()[0]

    conn.close()
    return total_purchases, active_services


def get_all_purchases():
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, user_id, service_name, amount_paid, purchased_at
        FROM purchases ORDER BY purchased_at DESC LIMIT 50
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


# ================== RENEWALS ==================

def get_renewal_info(purchase_id, user_id=None):
    conn = connect()
    cur = conn.cursor()
    if user_id is not None:
        cur.execute("""
            SELECT v.email, s.id, s.name, s.price, s.duration_days, s.data_limit_gb, p.user_id, v.panel_id
            FROM purchases p
            JOIN vpn_accounts v ON v.purchase_id = p.id
            JOIN services s ON s.id = p.service_id
            WHERE p.id = %s AND p.user_id = %s
        """, (purchase_id, user_id))
    else:
        cur.execute("""
            SELECT v.email, s.id, s.name, s.price, s.duration_days, s.data_limit_gb, p.user_id, v.panel_id
            FROM purchases p
            JOIN vpn_accounts v ON v.purchase_id = p.id
            JOIN services s ON s.id = p.service_id
            WHERE p.id = %s
        """, (purchase_id,))
    r = cur.fetchone()
    conn.close()
    return r


def apply_renewal_after_panel_success(target_user_id, purchase_id, amount, add_days, add_bytes, renewed_by=None):
    """
    فقط بعد از موفقیت bulkAdjust روی پنل صدا زده بشه. کسر موجودی و آپدیت
    expire_time/data_limit محلی رو در یک تراکنش اتمیک انجام می‌ده — اگه موجودی
    هم‌زمان (race) کافی نبود، هیچ‌کدوم اعمال نمی‌شه (return False).
    """
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE telegram_id=%s FOR UPDATE", (target_user_id,))
    r = cur.fetchone()
    if not r or r[0] < amount:
        conn.close()
        return False
    cur.execute("UPDATE users SET balance = balance - %s WHERE telegram_id=%s", (amount, target_user_id))
    cur.execute("""
        UPDATE vpn_accounts
        SET expire_time = expire_time + %s,
            data_limit = data_limit + %s
        WHERE purchase_id = %s
    """, (add_days * 86400 * 1000, add_bytes, purchase_id))
    cur.execute("""
        INSERT INTO renewals (user_id, purchase_id, amount_paid, added_days, added_bytes, renewed_by)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (target_user_id, purchase_id, amount, add_days, add_bytes, renewed_by or target_user_id))
    conn.commit()
    conn.close()
    return True


def log_manual_renewal(email, added_days, added_bytes, renewed_by):
    """
    لاگ تمدید دستیِ ادمین (بدون کسر موجودی و بدون purchase_id مشخص — چون این
    مسیر با ایمیل خام کار می‌کنه، نه با یک خریدِ ثبت‌شده در دیتابیس).
    """
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO renewals (user_id, purchase_id, client_email, amount_paid, added_days, added_bytes, renewed_by)
        VALUES (NULL, NULL, %s, 0, %s, %s, %s)
    """, (email, added_days, added_bytes, renewed_by))
    conn.commit()
    conn.close()


# ================== DISCOUNT CODES ==================

def create_discount_code(code, discount_type, discount_value, max_uses=None):
    code = code.strip().upper()
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT id, is_active FROM discount_codes WHERE code=%s", (code,))
    existing = cur.fetchone()
    if existing:
        existing_id, is_active = existing
        cur.execute("""
            UPDATE discount_codes
            SET discount_type=%s, discount_value=%s, max_uses=%s,
                used_count=0, is_active=TRUE, created_at=NOW()
            WHERE id=%s
        """, (discount_type, discount_value, max_uses, existing_id))
        conn.commit()
        conn.close()
        return existing_id
    else:
        cur.execute("""
            INSERT INTO discount_codes (code, discount_type, discount_value, max_uses)
            VALUES (%s, %s, %s, %s) RETURNING id
        """, (code, discount_type, discount_value, max_uses))
        cid = cur.fetchone()[0]
        conn.commit()
        conn.close()
        return cid


def get_discount_code(code):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, code, discount_type, discount_value, max_uses, used_count
        FROM discount_codes
        WHERE code=%s AND is_active=TRUE
    """, (code.strip().upper(),))
    r = cur.fetchone()
    conn.close()
    return r


def use_discount_code(dc_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE discount_codes SET used_count = used_count + 1 WHERE id=%s", (dc_id,))
    conn.commit()
    conn.close()


def get_all_discount_codes():
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, code, discount_type, discount_value, max_uses, used_count
        FROM discount_codes WHERE is_active=TRUE ORDER BY id
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_discount_code(dc_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM discount_codes WHERE id=%s", (dc_id,))
    conn.commit()
    conn.close()


# ================== FREE TRIAL ==================

def get_trial_config():
    """برمی‌گردونه (is_enabled, duration_days, data_limit_gb, require_referral, min_referrals, default_max_uses)"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT is_enabled, duration_days, data_limit_gb, require_referral, min_referrals, default_max_uses FROM free_trial_config WHERE id=1")
    r = cur.fetchone()
    conn.close()
    return r


def update_trial_config(**kwargs):
    """آپدیت یک یا چند فیلد از کانفیگ تست"""
    allowed = {"is_enabled", "duration_days", "data_limit_gb", "require_referral", "min_referrals", "default_max_uses"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k}=%s" for k in fields)
    conn = connect()
    cur = conn.cursor()
    cur.execute(f"UPDATE free_trial_config SET {set_clause} WHERE id=1", list(fields.values()))
    conn.commit()
    conn.close()


def get_trial_use_count(phone):
    """چند بار این شماره تست گرفته"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM free_trial_uses WHERE phone=%s", (phone,))
    r = cur.fetchone()
    conn.close()
    return r[0] if r else 0


def get_phone_max_uses(phone):
    """حداکثر استفاده مجاز برای این شماره (override یا default)"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT max_uses FROM phone_trial_override WHERE phone=%s", (phone,))
    r = cur.fetchone()
    conn.close()
    if r:
        return r[0]
    # برگرداندن مقدار پیش‌فرض
    cfg = get_trial_config()
    return cfg[5] if cfg else 1  # default_max_uses


def set_phone_max_uses(phone, max_uses):
    """ست یا آپدیت override برای یک شماره"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO phone_trial_override (phone, max_uses) VALUES (%s, %s)
        ON CONFLICT (phone) DO UPDATE SET max_uses=%s
    """, (phone, max_uses, max_uses))
    conn.commit()
    conn.close()


def delete_phone_override(phone):
    conn = connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM phone_trial_override WHERE phone=%s", (phone,))
    conn.commit()
    conn.close()


def clear_trial_uses(phone):
    """پاک کردن تاریخچه تست یه شماره — برای ریست کردن"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM free_trial_uses WHERE phone=%s", (phone,))
    conn.commit()
    conn.close()


def get_all_phone_overrides():
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT phone, max_uses FROM phone_trial_override ORDER BY phone")
    rows = cur.fetchall()
    conn.close()
    return rows


def record_trial_use(phone, telegram_id):
    """ثبت یک استفاده از تست"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("INSERT INTO free_trial_uses (phone, telegram_id) VALUES (%s, %s)", (phone, telegram_id))
    conn.commit()
    conn.close()


def get_all_trial_uses():
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT phone, telegram_id, used_at FROM free_trial_uses
        ORDER BY used_at DESC LIMIT 100
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


# ================== REFERRAL ==================

def get_referral_config():
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT is_enabled, reward_on_join, first_purchase_reward, reward_on_purchase, reward_purchase_percent
        FROM referral_config WHERE id=1
    """)
    r = cur.fetchone()
    conn.close()
    return r


def update_referral_config(**kwargs):
    allowed = {"is_enabled", "reward_on_join", "first_purchase_reward", "reward_on_purchase", "reward_purchase_percent"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k}=%s" for k in fields)
    conn = connect()
    cur = conn.cursor()
    cur.execute(f"UPDATE referral_config SET {set_clause} WHERE id=1", list(fields.values()))
    conn.commit()
    conn.close()


def get_referral_stats(user_id):
    """تعداد زیرمجموعه‌ها و مجموع پاداش‌های دریافتی"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE referred_by=%s", (user_id,))
    ref_count = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(amount),0) FROM referral_rewards WHERE referrer_id=%s", (user_id,))
    total_reward = cur.fetchone()[0]
    conn.close()
    return ref_count, total_reward


def give_referral_reward(referrer_id, referred_id, reward_type, amount):
    """اضافه کردن پاداش رفرال به حساب دعوت‌کننده"""
    if amount <= 0:
        return
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + %s WHERE telegram_id = %s", (amount, referrer_id))
    cur.execute("""
        INSERT INTO referral_rewards (referrer_id, referred_id, reward_type, amount)
        VALUES (%s, %s, %s, %s)
    """, (referrer_id, referred_id, reward_type, amount))
    conn.commit()
    conn.close()


def get_referral_rewards_history(user_id, limit=20):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT referred_id, reward_type, amount, created_at
        FROM referral_rewards WHERE referrer_id=%s
        ORDER BY created_at DESC LIMIT %s
    """, (user_id, limit))
    rows = cur.fetchall()
    conn.close()
    return rows


# ================== CATEGORY VISIBILITY ==================

def set_category_visibility(cat_id, visibility):
    """visibility: 'all' | 'partners' | 'users' | 'custom'"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE categories SET visibility=%s WHERE id=%s", (visibility, cat_id))
    conn.commit()
    conn.close()


def get_categories_for_user(is_partner_user: bool, user_id: int = None):
    """دسته‌بندی‌های قابل نمایش برای کاربر — شامل حالت سفارشی (custom) بر اساس user_id"""
    conn = connect()
    cur = conn.cursor()
    if is_partner_user:
        cur.execute("""
            SELECT id, name, emoji, is_custom FROM categories
            WHERE is_active=TRUE AND (visibility IS NULL OR visibility IN ('all','partners'))
            ORDER BY sort_order, id
        """)
    else:
        cur.execute("""
            SELECT id, name, emoji, is_custom FROM categories
            WHERE is_active=TRUE AND (visibility IS NULL OR visibility IN ('all','users'))
            ORDER BY sort_order, id
        """)
    rows = list(cur.fetchall())

    # دسته‌بندی‌های visibility='custom' که این کاربر به‌صورت جداگانه بهشون دسترسی داره
    if user_id is not None:
        cur.execute("""
            SELECT c.id, c.name, c.emoji, c.is_custom
            FROM categories c
            JOIN category_custom_access a ON a.category_id = c.id
            WHERE c.is_active=TRUE AND c.visibility='custom' AND a.user_id=%s
            ORDER BY c.sort_order, c.id
        """, (user_id,))
        custom_rows = cur.fetchall()
        existing_ids = {r[0] for r in rows}
        for r in custom_rows:
            if r[0] not in existing_ids:
                rows.append(r)

    # حذف دسته‌بندی‌هایی که مخصوصاً برای این کاربر مسدود شدن (deny-list) —
    # این فیلتر مستقل از visibility اجرا می‌شه، یعنی حتی دسته‌های 'all'/'partners'/
    # 'users' هم اگه توی لیست مسدودی این کاربر باشن، از نتیجه حذف می‌شن.
    if user_id is not None:
        cur.execute("SELECT category_id FROM category_blocked_users WHERE user_id=%s", (user_id,))
        blocked_ids = {r[0] for r in cur.fetchall()}
        if blocked_ids:
            rows = [r for r in rows if r[0] not in blocked_ids]

    conn.close()
    return rows


def block_category_for_user(category_id: int, user_id: int):
    """مخفی کردن یک دسته‌بندی مشخص فقط برای یک کاربر خاص (بقیه‌ی کاربرها بدون تغییر می‌بینن)"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO category_blocked_users (category_id, user_id)
        VALUES (%s, %s) ON CONFLICT (category_id, user_id) DO NOTHING
    """, (category_id, user_id))
    conn.commit()
    conn.close()


def unblock_category_for_user(category_id: int, user_id: int):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM category_blocked_users WHERE category_id=%s AND user_id=%s",
        (category_id, user_id)
    )
    conn.commit()
    conn.close()


def get_category_blocked_users(category_id: int):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT b.user_id, u.phone
        FROM category_blocked_users b
        LEFT JOIN users u ON u.telegram_id = b.user_id
        WHERE b.category_id=%s
        ORDER BY b.id
    """, (category_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_all_user_ids():
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT telegram_id FROM users")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


def get_partner_user_ids():
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM partners WHERE status='active'")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


# ================== LICENSE ==================

# ================== REQUIRED CHANNELS ==================

def get_active_channels():
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, channel_id, channel_username, channel_title, invite_link
        FROM required_channels WHERE is_active=TRUE
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def get_all_channels():
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, channel_id, channel_username, channel_title, invite_link, is_active
        FROM required_channels ORDER BY id
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def add_channel(channel_id, channel_username, channel_title, invite_link=None):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO required_channels (channel_id, channel_username, channel_title, invite_link)
        VALUES (%s, %s, %s, %s) RETURNING id
    """, (channel_id, channel_username, channel_title, invite_link))
    cid = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return cid


def delete_channel(ch_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM required_channels WHERE id=%s", (ch_id,))
    conn.commit()
    conn.close()


def toggle_channel(ch_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        UPDATE required_channels SET is_active = NOT is_active
        WHERE id=%s RETURNING is_active
    """, (ch_id,))
    r = cur.fetchone()
    conn.commit()
    conn.close()
    return r[0] if r else None


# ================== PARTNERS ==================

def is_partner(user_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT id FROM partners WHERE user_id=%s AND status='active'", (user_id,))
    r = cur.fetchone()
    conn.close()
    return r is not None


def add_partner(user_id, phone=None, description=None):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO partners (user_id, phone, description)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE
        SET status='active', phone=EXCLUDED.phone, description=EXCLUDED.description
    """, (user_id, phone, description))
    conn.commit()
    conn.close()


def remove_partner(user_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE partners SET status='inactive' WHERE user_id=%s", (user_id,))
    cur.execute("DELETE FROM partner_requests WHERE user_id=%s", (user_id,))
    conn.commit()
    conn.close()


def get_all_partners():
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, user_id, phone, description, status, added_at
        FROM partners ORDER BY added_at DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def get_partner(user_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, user_id, phone, description, status, added_at, client_group_label,
               email_prefix, email_emoji, email_counter
        FROM partners WHERE user_id=%s
    """, (user_id,))
    r = cur.fetchone()
    conn.close()
    return r


def set_partner_email_naming(user_id: int, emoji: str | None, prefix: str | None):
    """
    تنظیم یا پاک کردن (با prefix=None) نام‌گذاری اختصاصی ایمیل این همکار.
    شمارنده دست نمی‌خوره — فقط با reset_partner_email_counter صفر می‌شه.
    """
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE partners SET email_emoji=%s, email_prefix=%s WHERE user_id=%s",
        (emoji, prefix, user_id)
    )
    conn.commit()
    conn.close()


def reset_partner_email_counter(user_id: int):
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE partners SET email_counter=0 WHERE user_id=%s", (user_id,))
    conn.commit()
    conn.close()


def set_partner_group_label(user_id: int, label: str | None):
    """تنظیم یا پاک کردن (با None) برچسب گروه پنل این همکار"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE partners SET client_group_label=%s WHERE user_id=%s", (label, user_id))
    conn.commit()
    conn.close()


# ================== PARTNER REQUESTS ==================

def create_partner_request(user_id, phone, description):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO partner_requests (user_id, phone, description, status)
        VALUES (%s, %s, %s, 'pending')
        ON CONFLICT DO NOTHING
    """, (user_id, phone, description))
    conn.commit()
    conn.close()


def get_pending_partner_requests():
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, user_id, phone, description, created_at
        FROM partner_requests WHERE status='pending' ORDER BY created_at
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def update_partner_request_status(req_id, status):
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE partner_requests SET status=%s WHERE id=%s", (status, req_id))
    conn.commit()
    conn.close()


def get_partner_request(req_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, user_id, phone, description
        FROM partner_requests WHERE id=%s
    """, (req_id,))
    r = cur.fetchone()
    conn.close()
    return r


def has_pending_request(user_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT id FROM partner_requests
        WHERE user_id=%s AND status='pending'
    """, (user_id,))
    r = cur.fetchone()
    conn.close()
    return r is not None


# ================== PANEL CONFIG ==================
# نکته: این نسخه ۹ ستونی است (شامل sub_port و sub_path) — panel.py مستقیماً
# به این دو ستون برای ساخت لینک subscription وابسته است. نسخه‌ی قدیمی‌تر
# ۷ ستونی که این دو فیلد را نداشت، به‌عمد حذف شده است.

def get_panel_config():
    """برمی‌گردونه (panel_url, auth_type, username, password, api_key, inbound_id, panel_path, sub_port, sub_path)"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT panel_url, auth_type, username, password, api_key, inbound_id, panel_path, sub_port, sub_path
        FROM panel_config WHERE id=1
    """)
    r = cur.fetchone()
    conn.close()
    return r


def update_panel_config(**kwargs):
    allowed = {"panel_url", "auth_type", "username", "password", "api_key", "inbound_id", "panel_path", "sub_port", "sub_path"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k}=%s" for k in fields)
    conn = connect()
    cur = conn.cursor()
    cur.execute(f"UPDATE panel_config SET {set_clause} WHERE id=1", list(fields.values()))
    conn.commit()
    conn.close()


# ================== VPN ACCOUNTS ==================

def save_vpn_account(user_id, email, uuid, inbound_id, expire_time, data_limit,
                     purchase_id=None, is_trial=False, sub_id=None, sub_url=None, panel_id=1):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO vpn_accounts
        (user_id, purchase_id, email, uuid, sub_id, sub_url, inbound_id, expire_time, data_limit, is_trial, panel_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
    """, (user_id, purchase_id, email, uuid, sub_id, sub_url, inbound_id, expire_time, data_limit, is_trial, panel_id))
    vid = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return vid


def get_user_vpn_accounts(user_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            v.id, v.email, v.uuid, v.sub_url, v.inbound_id, v.expire_time,
            v.data_limit, v.created_at, v.is_trial,
            COALESCE(p.service_name, s.name, 'تست رایگان') as service_name,
            COALESCE(c.name, '—') as category_name,
            v.purchase_id, v.note, v.panel_id
        FROM vpn_accounts v
        LEFT JOIN purchases p ON v.purchase_id = p.id
        LEFT JOIN services s ON p.service_id = s.id
        LEFT JOIN categories c ON s.category_id = c.id
        WHERE v.user_id=%s
        ORDER BY v.created_at DESC
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_vpn_account(account_id, user_id=None):
    conn = connect()
    cur = conn.cursor()
    if user_id is not None:
        cur.execute("""
            SELECT
                v.id, v.email, v.uuid, v.sub_url, v.inbound_id, v.expire_time,
                v.data_limit, v.created_at, v.is_trial,
                COALESCE(p.service_name, s.name, 'تست رایگان') as service_name,
                COALESCE(c.name, '—') as category_name,
                v.purchase_id, v.note, v.user_id, v.panel_id
            FROM vpn_accounts v
            LEFT JOIN purchases p ON v.purchase_id = p.id
            LEFT JOIN services s ON p.service_id = s.id
            LEFT JOIN categories c ON s.category_id = c.id
            WHERE v.id=%s AND v.user_id=%s
        """, (account_id, user_id))
    else:
        cur.execute("""
            SELECT
                v.id, v.email, v.uuid, v.sub_url, v.inbound_id, v.expire_time,
                v.data_limit, v.created_at, v.is_trial,
                COALESCE(p.service_name, s.name, 'تست رایگان') as service_name,
                COALESCE(c.name, '—') as category_name,
                v.purchase_id, v.note, v.user_id, v.panel_id
            FROM vpn_accounts v
            LEFT JOIN purchases p ON v.purchase_id = p.id
            LEFT JOIN services s ON p.service_id = s.id
            LEFT JOIN categories c ON s.category_id = c.id
            WHERE v.id=%s
        """, (account_id,))
    r = cur.fetchone()
    conn.close()
    return r


def set_vpn_account_note(account_id, note):
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE vpn_accounts SET note=%s WHERE id=%s", (note, account_id))
    conn.commit()
    conn.close()


def has_previous_purchase(user_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM purchases WHERE user_id=%s", (user_id,))
    r = cur.fetchone()
    conn.close()
    return r[0] > 1


# ================== CLIENT NAMING (برند + شمارنده) ==================

def get_client_naming_config():
    """برمی‌گردونه (prefix, counter, default_group) — برای نمایش وضعیت فعلی به ادمین"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT prefix, counter, default_group FROM client_naming_config WHERE id=1")
    r = cur.fetchone()
    conn.close()
    return r


def set_default_client_group(group_name: str):
    """تنظیم برچسب گروه پیش‌فرض روی پنل برای کاربران عادی (غیر ادمین، غیر همکار)"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO client_naming_config (id, default_group)
        VALUES (1, %s)
        ON CONFLICT (id) DO UPDATE SET default_group=EXCLUDED.default_group
    """, (group_name,))
    conn.commit()
    conn.close()


def get_client_group_for_user(user_id: int) -> str:
    """
    برچسب گروه پنلی که باید روی کلاینت جدید این کاربر گذاشته بشه:
    - ادمین  → "Admin" (ثابت)
    - همکار فعال با برچسب اختصاصی تنظیم‌شده → همون برچسب
    - بقیه (کاربر عادی، یا همکاری که برچسب اختصاصی نداره) → گروه پیش‌فرض تنظیم‌شده توسط ادمین
    اگه هیچ‌کدوم تنظیم نشده باشه، رشته‌ی خالی برمی‌گردونه (یعنی گروهی روی پنل ست نشه)
    """
    from config import is_admin
    if is_admin(user_id):
        return "Admin"

    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT client_group_label FROM partners WHERE user_id=%s AND status='active'",
        (user_id,)
    )
    r = cur.fetchone()
    if r and r[0]:
        conn.close()
        return r[0]

    cur.execute("SELECT default_group FROM client_naming_config WHERE id=1")
    r2 = cur.fetchone()
    conn.close()
    return r2[0] if r2 and r2[0] else ""


def set_client_naming_prefix(prefix: str):
    """تنظیم یا تغییر پیشوند — شمارنده دست نمی‌خوره (فقط با reset_client_naming_counter صفر می‌شه)"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO client_naming_config (id, prefix, counter)
        VALUES (1, %s, 0)
        ON CONFLICT (id) DO UPDATE SET prefix=EXCLUDED.prefix
    """, (prefix,))
    conn.commit()
    conn.close()


def reset_client_naming_counter():
    """ریست شمارنده به صفر — احتیاط: اگه کلاینت‌های قبلی با اعداد کوچیک‌تر هنوز فعال باشن، تکراری می‌شن"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE client_naming_config SET counter=0 WHERE id=1")
    conn.commit()
    conn.close()


def get_next_client_email(user_id: int | None = None) -> str:
    """
    اتمیک: شمارنده رو یکی افزایش می‌ده و ایمیل کامل کلاینت رو برمی‌گردونه.
    ترتیب اولویت:
      ۱. اگه user_id مربوط به یک همکار فعال با پیشوند ایمیل اختصاصی خودش باشه،
         از شمارنده‌ی مخصوص همون همکار استفاده می‌شه (partners.email_counter).
      ۲. وگرنه از شمارنده‌ی سراسری (client_naming_config) استفاده می‌شه.
      ۳. اگه هیچ‌کدوم تنظیم نشده باشن، به فرمت قدیمی (client + timestamp) fallback
         می‌کنه تا هیچ‌وقت ایمیل خالی/نامعتبر ساخته نشه.
    هر دو حالت با یک UPDATE اتمیک (بدون فاصله‌ی زمانی بین خوندن و افزایش شمارنده)
    از race condition زیر بار همزمان (چند خرید هم‌زمان) جلوگیری می‌کنن.
    """
    conn = connect()
    cur = conn.cursor()

    if user_id is not None:
        cur.execute("""
            UPDATE partners
            SET email_counter = email_counter + 1
            WHERE user_id=%s AND status='active'
              AND email_prefix IS NOT NULL AND email_prefix != ''
            RETURNING email_emoji, email_prefix, email_counter
        """, (user_id,))
        r_partner = cur.fetchone()
        if r_partner:
            conn.commit()
            conn.close()
            emoji, prefix, counter = r_partner
            return f"{emoji or ''}{prefix}{counter}"

    cur.execute("""
        UPDATE client_naming_config
        SET counter = counter + 1
        WHERE id=1
        RETURNING prefix, counter
    """)
    r = cur.fetchone()
    conn.commit()
    conn.close()

    if not r or not r[0]:
        import time
        return f"client{int(time.time())}"

    prefix, counter = r
    return f"{prefix}{counter}"




def add_category_custom_flag(cat_id, is_custom=True):
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE categories SET is_custom=%s WHERE id=%s", (is_custom, cat_id))
    conn.commit()
    conn.close()


def is_custom_category(cat_id) -> bool:
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT is_custom FROM categories WHERE id=%s", (cat_id,))
    r = cur.fetchone()
    conn.close()
    return bool(r and r[0])


def get_custom_groups(category_id, active_only=True):
    conn = connect()
    cur = conn.cursor()
    if active_only:
        cur.execute("""
            SELECT id, name, emoji, price_per_gb, price_per_day, min_gb, max_gb, min_days, max_days, inbound_ids
            FROM custom_plan_groups WHERE category_id=%s AND is_active=TRUE
            ORDER BY sort_order, id
        """, (category_id,))
    else:
        cur.execute("""
            SELECT id, name, emoji, price_per_gb, price_per_day, min_gb, max_gb, min_days, max_days, inbound_ids, is_active
            FROM custom_plan_groups WHERE category_id=%s
            ORDER BY sort_order, id
        """, (category_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_custom_group(group_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, category_id, name, emoji, price_per_gb, price_per_day,
               min_gb, max_gb, min_days, max_days, inbound_ids, is_active
        FROM custom_plan_groups WHERE id=%s
    """, (group_id,))
    r = cur.fetchone()
    conn.close()
    return r


def add_custom_group(category_id, name, emoji="🌍"):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO custom_plan_groups (category_id, name, emoji)
        VALUES (%s, %s, %s) RETURNING id
    """, (category_id, name, emoji))
    gid = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return gid


def update_custom_group(group_id, field, value):
    allowed = {
        "name": "name", "emoji": "emoji",
        "price_per_gb": "price_per_gb", "price_per_day": "price_per_day",
        "min_gb": "min_gb", "max_gb": "max_gb",
        "min_days": "min_days", "max_days": "max_days",
        "inbound_ids": "inbound_ids",
    }
    col = allowed.get(field)
    if not col:
        return
    conn = connect()
    cur = conn.cursor()
    cur.execute(f"UPDATE custom_plan_groups SET {col}=%s WHERE id=%s", (value, group_id))
    conn.commit()
    conn.close()


def toggle_custom_group(group_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE custom_plan_groups SET is_active = NOT is_active WHERE id=%s RETURNING is_active", (group_id,))
    r = cur.fetchone()
    conn.commit()
    conn.close()
    return r[0] if r else None


def delete_custom_group(group_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM custom_plan_groups WHERE id=%s", (group_id,))
    conn.commit()
    conn.close()


# ================== CATEGORY CUSTOM ACCESS ==================

def add_category_custom_user(category_id, user_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO category_custom_access (category_id, user_id)
        VALUES (%s, %s) ON CONFLICT (category_id, user_id) DO NOTHING
    """, (category_id, user_id))
    conn.commit()
    conn.close()


def remove_category_custom_user(category_id, user_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM category_custom_access WHERE category_id=%s AND user_id=%s",
        (category_id, user_id)
    )
    conn.commit()
    conn.close()


def get_category_custom_users(category_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT a.user_id, u.phone
        FROM category_custom_access a
        LEFT JOIN users u ON u.telegram_id = a.user_id
        WHERE a.category_id=%s
        ORDER BY a.id
    """, (category_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def has_category_custom_access(category_id, user_id) -> bool:
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM category_custom_access WHERE category_id=%s AND user_id=%s",
        (category_id, user_id)
    )
    r = cur.fetchone()
    conn.close()
    return r is not None


def find_user_id_by_phone(phone: str):
    """پیدا کردن آیدی عددی کاربر از روی شماره (اگه قبلاً تو دیتابیس ثبت شده)"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT telegram_id FROM users WHERE phone=%s", (phone,))
    r = cur.fetchone()
    conn.close()
    return r[0] if r else None


def get_custom_access_category_ids(user_id):
    """دسته‌بندی‌هایی که این کاربر به صورت سفارشی بهشون دسترسی داره"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT category_id FROM category_custom_access WHERE user_id=%s", (user_id,))
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


# ================== DATABASE BACKUP CONFIG ==================

def get_backup_config():
    """برمی‌گردونه (backup_bot_token, backup_admin_id, auto_interval_hours, last_backup_at)"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT backup_bot_token, backup_admin_id, auto_interval_hours, last_backup_at
        FROM backup_config WHERE id=1
    """)
    r = cur.fetchone()
    conn.close()
    return r


def update_backup_config(**kwargs):
    """
    آپدیت یک یا چند فیلد از تنظیمات بکاپ. کلیدهای مجاز از یک whitelist ثابت
    میان (نه از ورودی کاربر)، پس امکان SQL injection از طریق نام ستون وجود نداره؛
    مقادیر هم همیشه با %s پارامتری می‌شن.
    """
    allowed = {"backup_bot_token", "backup_admin_id", "auto_interval_hours"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k}=%s" for k in fields)
    conn = connect()
    cur = conn.cursor()
    cur.execute(f"UPDATE backup_config SET {set_clause} WHERE id=1", list(fields.values()))
    conn.commit()
    conn.close()


def update_backup_last_run():
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE backup_config SET last_backup_at=NOW() WHERE id=1")
    conn.commit()
    conn.close()


# ================== BRAND NAME (شخصی‌سازی متن‌های ربات) ==================

def get_brand_name() -> str:
    """
    نام برندی که در متن‌های کاربری (خوش‌آمدگویی، سرصفحه‌ی خانه و...) نشون داده می‌شه.
    اگه ادمین هنوز چیزی تنظیم نکرده باشه، مقدار پیش‌فرض "Persian Bot" برمی‌گرده.
    از جدول bot_settings (کلید-مقدار عمومی که از قبل توی پروژه بود) استفاده می‌شه.
    """
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT value FROM bot_settings WHERE key='brand_name'")
    r = cur.fetchone()
    conn.close()
    return r[0] if r and r[0] else "Persian Bot"


def set_brand_name(name: str):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bot_settings (key, value) VALUES ('brand_name', %s)
        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value
    """, (name,))
    conn.commit()
    conn.close()


# ---- قالب‌های پیش‌فرض (دقیقاً همون متن‌های قبلی که hardcode بودن در utils.py) ----

_DEFAULT_WELCOME_TEXT = (
    "👋 سلام {name} عزیز، به {brand} خوش اومدی! 🥳\n{sep}\n"
    "🚀 مطمئن‌ترین بستر خرید و مدیریت سرویس VPN بر پایه‌ی V2Ray\n"
    "🔒 ارتباط کاملاً رمزنگاری‌شده و ضدفیلتر\n\n"
    "✨ امکانات ربات:\n"
    "🛒 خرید آنی سرویس از دسته‌بندی‌های متنوع\n"
    "🎁 دریافت تست رایگان قبل از خرید\n"
    "🎛 ساخت پلن دلخواه — خودت حجم و مدت رو انتخاب کن\n"
    "💳 شارژ حساب با چند روش پرداخت\n"
    "📊 مشاهده‌ی لحظه‌ای وضعیت و حجم باقی‌مانده‌ی هر سرویس\n\n"
    "🎯 و بیشتر:\n"
    "👥 دعوت دوستان و دریافت پاداش رفرال\n"
    "🤝 امکان همکاری و نمایندگی فروش\n"
    "📋 تاریخچه‌ی کامل خریدها\n"
    "🎁 کدهای تخفیف برای خریدهای بیشتر\n{sep}\n"
    "📌 یکی از گزینه‌های زیر رو انتخاب کن:"
)

_DEFAULT_HOME_TEXT = (
    "🏠 {brand}\n{sep}\n"
    "💰 موجودی: {balance} تومان\n{sep}\n"
    "یکی از گزینه‌های زیر رو انتخاب کن:"
)


def get_welcome_text() -> str:
    """
    قالب متن خوش‌آمدگویی /start. Placeholder های پشتیبانی‌شده: {name}, {brand}, {sep}
    (جایگزینی امنشون توی utils.build_welcome_text انجام می‌شه). اگه ادمین چیزی
    تنظیم نکرده باشه، قالب پیش‌فرض (همون متن قبلی) برمی‌گرده.
    """
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT value FROM bot_settings WHERE key='welcome_text'")
    r = cur.fetchone()
    conn.close()
    return r[0] if r and r[0] else _DEFAULT_WELCOME_TEXT


def set_welcome_text(template: str):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bot_settings (key, value) VALUES ('welcome_text', %s)
        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value
    """, (template,))
    conn.commit()
    conn.close()


def reset_welcome_text():
    conn = connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM bot_settings WHERE key='welcome_text'")
    conn.commit()
    conn.close()


def get_home_text() -> str:
    """
    قالب متن صفحه‌ی «خانه». Placeholder های پشتیبانی‌شده: {brand}, {balance}, {sep}
    """
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT value FROM bot_settings WHERE key='home_text'")
    r = cur.fetchone()
    conn.close()
    return r[0] if r and r[0] else _DEFAULT_HOME_TEXT


def set_home_text(template: str):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bot_settings (key, value) VALUES ('home_text', %s)
        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value
    """, (template,))
    conn.commit()
    conn.close()


def reset_home_text():
    conn = connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM bot_settings WHERE key='home_text'")
    conn.commit()
    conn.close()


# ================== SUPPORT INFO (اطلاعات پشتیبانی، قابل مدیریت از پنل ادمین) ==================

def get_support_username() -> str:
    """آیدی تلگرام پشتیبانی (بدون @). خالی یعنی هنوز تنظیم نشده."""
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT value FROM bot_settings WHERE key='support_username'")
    r = cur.fetchone()
    conn.close()
    return r[0] if r and r[0] else ""


def set_support_username(username: str):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bot_settings (key, value) VALUES ('support_username', %s)
        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value
    """, (username,))
    conn.commit()
    conn.close()


def get_support_phone() -> str:
    """شماره تماس پشتیبانی. خالی یعنی هنوز تنظیم نشده."""
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT value FROM bot_settings WHERE key='support_phone'")
    r = cur.fetchone()
    conn.close()
    return r[0] if r and r[0] else ""


def set_support_phone(phone: str):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bot_settings (key, value) VALUES ('support_phone', %s)
        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value
    """, (phone,))
    conn.commit()
    conn.close()

# ================== MULTI-PANEL MANAGEMENT ==================

def get_all_panels():
    """دریافت لیست تمام پنل‌های ثبت شده"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT id, name, panel_type, panel_url FROM panel_config ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return rows

def get_panel(panel_id: int):
    """دریافت اطلاعات کامل یک پنل خاص"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, panel_type, panel_url, auth_type, username, password,
               api_key, inbound_id, panel_path, sub_port, sub_path
        FROM panel_config WHERE id=%s
    """, (panel_id,))
    r = cur.fetchone()
    conn.close()
    return r

def add_panel(name: str, panel_type: str):
    """افزودن پنل جدید"""
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO panel_config (name, panel_type) VALUES (%s, %s) RETURNING id",
        (name, panel_type)
    )
    pid = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return pid

def update_panel_field(panel_id: int, field: str, value):
    """ویرایش یک فیلد خاص از یک پنل مشخص"""
    allowed = {"name", "panel_type", "panel_url", "auth_type", "username",
               "password", "api_key", "inbound_id", "panel_path", "sub_port", "sub_path"}
    if field not in allowed:
        return
    conn = connect()
    cur = conn.cursor()
    cur.execute(f"UPDATE panel_config SET {field}=%s WHERE id=%s", (value, panel_id))
    conn.commit()
    conn.close()

def delete_panel(panel_id: int):
    """حذف کامل یک پنل"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM panel_config WHERE id=%s", (panel_id,))
    conn.commit()
    conn.close()