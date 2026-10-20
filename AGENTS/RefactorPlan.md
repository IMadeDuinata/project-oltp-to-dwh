TASK: Phase A Completion + Config Bridge

Context: Repo DWH Olist dual-source. Devenv menjalankan 3 MySQL instances: oltp-br :3306, oltp-id :3307, dwh :3308. OLTP Indonesia sudah siap (oltp_id/schema_indo.sql + oltp_id/load_to_oltp_id.py). Yang kurang adalah sisi Brazil dan unifikasi config.

# Tambahkan FK ke oltp_id/schema_indo.sql

Tambahkan FK constraints ke tabel-tabel berikut, tapi tetap tanpa ON DELETE CASCADE — biarkan FK terdefinisi tapi tidak enforced ketat di aplikasi level:

```sql
-- Di tabel orders, tambahkan setelah INDEX:
FOREIGN KEY (customer_id) REFERENCES customers(customer_id)

-- Di tabel order_items, tambahkan setelah INDEX:
FOREIGN KEY (order_id) REFERENCES orders(order_id),
FOREIGN KEY (product_id) REFERENCES products(product_id),
FOREIGN KEY (seller_id) REFERENCES sellers(seller_id)

-- Di tabel order_payments, tambahkan setelah INDEX:
FOREIGN KEY (order_id) REFERENCES orders(order_id)

-- Di tabel order_reviews, tambahkan setelah INDEX:
FOREIGN KEY (order_id) REFERENCES orders(order_id)
```

load_to_oltp_id.py sudah pakai FOREIGN_KEY_CHECKS = 0 saat load — jadi data kotor tetap bisa masuk. Tidak perlu ubah loader-nya.

# Lengkapi sql/01_oltp_ddl.sql

Tambahkan tiga tabel yang ada di schema ID tapi belum ada di BR, setelah order_payments:

```sql
-- ORDER_REVIEWS
CREATE TABLE IF NOT EXISTS order_reviews (
    review_internal_id      BIGINT AUTO_INCREMENT PRIMARY KEY,
    review_id               VARCHAR(50),
    order_id                VARCHAR(50) NOT NULL,
    review_score            INT,
    review_comment_title    VARCHAR(255),
    review_comment_message  TEXT,
    review_creation_date    DATETIME,
    review_answer_timestamp DATETIME,
    INDEX idx_rev_order (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- GEOLOCATION
CREATE TABLE IF NOT EXISTS geolocation (
    geo_id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    zip_code_prefix VARCHAR(10),
    geolocation_lat DECIMAL(15,10),
    geolocation_lng DECIMAL(15,10),
    city            VARCHAR(100),
    state           VARCHAR(10),
    INDEX idx_geo_zip (zip_code_prefix)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- CATEGORY_TRANSLATION
CREATE TABLE IF NOT EXISTS category_translation (
    product_category_name         VARCHAR(100) PRIMARY KEY,
    product_category_name_english VARCHAR(100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

Database name tetap oltp_olist (jangan diubah, config sudah pakai ini).

# Buat oltp/load_br.py

Mirip struktur oltp_id/load_to_oltp_id.py tapi untuk Brazil. Baca dari data/raw/. Urutan load: customers, sellers, products, orders, order_items, order_payments, order_reviews, geolocation, category_translation. Mapping nama file CSV ke tabel:

```python
CSV_MAP = {
    "customers":           "olist_customers_dataset.csv",
    "sellers":             "olist_sellers_dataset.csv",
    "products":            "olist_products_dataset.csv",
    "orders":              "olist_orders_dataset.csv",
    "order_items":         "olist_order_items_dataset.csv",
    "order_payments":      "olist_order_payments_dataset.csv",
    "order_reviews":       "olist_order_reviews_dataset.csv",
    "geolocation":         "olist_geolocation_dataset.csv",
    "category_translation":"product_category_name_translation.csv",
}
```
Khusus geolocation: rename kolom geolocation_zip_code_prefix→zip_code_prefix, geolocation_city→city, geolocation_state→state sebelum load. Khusus products: rename product_name_lenght→product_name_length, product_description_lenght→product_description_length. Pakai DB_PORT (3306) dari .env. Load dengan to_sql(if_exists='append', chunksize=1000), idempotent via truncate dulu.

# Update etl/config.py

Tambahkan fungsi dan env vars berikut, tanpa mengubah fungsi yang sudah ada:

```python
DB_PORT_OLTP_BR = int(os.getenv("DB_PORT_OLTP_BR", "3306"))
DB_PORT_OLTP_ID = int(os.getenv("DB_PORT_OLTP_ID", "3307"))
DB_PORT_DWH     = int(os.getenv("DB_PORT_DWH", "3308"))
DB_NAME_OLTP_BR = os.getenv("DB_NAME_OLTP_BR", "oltp_olist")
DB_NAME_OLTP_ID = os.getenv("DB_NAME_OLTP_ID", "olist_oltp_id")

def get_oltp_br_engine():
    return create_engine(
        URL.create("mysql+pymysql", username=DB_USER, password=DB_PASSWORD,
                   host=DB_HOST, port=DB_PORT_OLTP_BR, database=DB_NAME_OLTP_BR,
                   query={"charset": "utf8mb4"}), pool_pre_ping=True)

def get_oltp_id_engine():
    return create_engine(
        URL.create("mysql+pymysql", username=DB_USER, password=DB_PASSWORD,
                   host=DB_HOST, port=DB_PORT_OLTP_ID, database=DB_NAME_OLTP_ID,
                   query={"charset": "utf8mb4"}), pool_pre_ping=True)
```
get_oltp_engine() yang lama tetap ada, arahkan ke BR engine sebagai alias: get_oltp_engine = get_oltp_br_engine.

# Update .env.example

Pastikan ada semua variabel ini:

DB_HOST=127.0.0.1
DB_USER=root
DB_PASSWORD=
DB_PORT_OLTP_BR=3306
DB_PORT_OLTP_ID=3307
DB_PORT_DWH=3308
DB_NAME_OLTP_BR=oltp_olist
DB_NAME_OLTP_ID=olist_oltp_id
DB_NAME_DWH=dwh_olist

JANGAN sentuh: etl/transform.py, etl/load.py, etl/clean.py, etl/run_etl.py, etl/extract.py, tests/, oltp_id/.
