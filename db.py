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
            balance INTEGER DEFAULT 0
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

    # migrations برای دیتابیس‌های قبلی
    cur.execute("ALTER TABLE services ADD COLUMN IF NOT EXISTS data_limit_gb NUMERIC(10,2) NOT NULL DEFAULT 0")
    cur.execute("ALTER TABLE services ALTER COLUMN data_limit_gb TYPE NUMERIC(10,2)")
    cur.execute("ALTER TABLE services ADD COLUMN IF NOT EXISTS category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL")

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

    conn.commit()
    conn.close()


# -------------------- USERS --------------------

def add_user(user_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (telegram_id, balance)
        VALUES (%s, 0)
        ON CONFLICT (telegram_id) DO NOTHING
    """, (user_id,))
    conn.commit()
    conn.close()


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


# -------------------- TRANSACTIONS --------------------

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


# -------------------- CATEGORIES --------------------

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


# -------------------- SERVICES --------------------

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


# -------------------- PURCHASES --------------------

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

# -------------------- HARD DELETE & UPDATE --------------------

def hard_delete_service(service_id):
    """حذف واقعی سرویس از دیتابیس"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM services WHERE id=%s", (service_id,))
    conn.commit()
    conn.close()


def update_service(service_id, field, value):
    """ویرایش یه فیلد از سرویس"""
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


# -------------------- DISCOUNT CODES --------------------

def create_discount_code(code, discount_type, discount_value, max_uses=None):
    conn = connect()
    cur = conn.cursor()
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
    """, (code.upper(),))
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
    cur.execute("UPDATE discount_codes SET is_active=FALSE WHERE id=%s", (dc_id,))
    conn.commit()
    conn.close()