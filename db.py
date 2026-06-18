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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            emoji TEXT DEFAULT '📦',
            is_active BOOLEAN DEFAULT TRUE,
            sort_order INTEGER DEFAULT 0
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
            reward_on_purchase INTEGER DEFAULT 0,
            reward_purchase_percent NUMERIC(5,2) DEFAULT 0
        )
    """)
    cur.execute("""
        INSERT INTO referral_config (id)
        VALUES (1)
        ON CONFLICT (id) DO NOTHING
    """)

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

    # migrations برای دیتابیس‌های قبلی
    cur.execute("ALTER TABLE services ADD COLUMN IF NOT EXISTS data_limit_gb NUMERIC(10,2) NOT NULL DEFAULT 0")
    cur.execute("ALTER TABLE services ALTER COLUMN data_limit_gb TYPE NUMERIC(10,2)")
    cur.execute("ALTER TABLE services ADD COLUMN IF NOT EXISTS category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT DEFAULT NULL")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT DEFAULT NULL")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS joined_at TIMESTAMP DEFAULT NOW()")

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

def create_transaction(user_id, amount):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO transactions (user_id, amount, status)
        VALUES (%s, %s, 'pending') RETURNING id
    """, (user_id, amount))
    tx_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return tx_id


def approve_transaction(tx_id, user_id, amount):
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + %s WHERE telegram_id = %s", (amount, user_id))
    cur.execute("UPDATE transactions SET status = 'approved' WHERE id = %s AND status = 'pending'", (tx_id,))
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


# ================== CATEGORIES ==================

def get_all_categories(active_only=True):
    conn = connect()
    cur = conn.cursor()
    if active_only:
        cur.execute("SELECT id, name, emoji FROM categories WHERE is_active=TRUE ORDER BY sort_order, id")
    else:
        cur.execute("SELECT id, name, emoji, is_active, sort_order FROM categories ORDER BY sort_order, id")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_category(cat_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT id, name, emoji, is_active FROM categories WHERE id=%s", (cat_id,))
    r = cur.fetchone()
    conn.close()
    return r


def add_category(name, emoji="📦"):
    conn = connect()
    cur = conn.cursor()
    cur.execute("INSERT INTO categories (name, emoji) VALUES (%s, %s) RETURNING id", (name, emoji))
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
    cur.execute("UPDATE categories SET is_active=FALSE WHERE id=%s", (cat_id,))
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
               s.is_active, COALESCE(c.name,'') as cat_name
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
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT service_name, amount_paid, purchased_at FROM purchases
        WHERE user_id=%s ORDER BY purchased_at DESC LIMIT 10
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


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
    """برمی‌گردونه (is_enabled, reward_on_join, reward_on_purchase, reward_purchase_percent)"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT is_enabled, reward_on_join, reward_on_purchase, reward_purchase_percent FROM referral_config WHERE id=1")
    r = cur.fetchone()
    conn.close()
    return r


def update_referral_config(**kwargs):
    allowed = {"is_enabled", "reward_on_join", "reward_on_purchase", "reward_purchase_percent"}
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