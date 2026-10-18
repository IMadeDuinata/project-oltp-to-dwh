# OLTP Indonesia (olist_oltp_id)

Sistem OLTP kedua untuk proyek DWH multi-source. Merepresentasikan sistem e-commerce Indonesia yang belum mature — berbeda karakteristik dari sistem Brazil (`oltp_olist`).

## Prasyarat
- MySQL running (default: `127.0.0.1:3306`)
- File `.env` di root project berisi:
  ```env
  DB_HOST=127.0.0.1
  DB_PORT=3306
  DB_USER=root
  DB_PASSWORD=secret
  ```
- Dependencies: `pandas numpy sqlalchemy pymysql python-dotenv`

## Cara Run (2 Langkah)

```bash
# Langkah 1: Generate CSV dummy Indonesia
python oltp_id/generate_olist_id.py

# Langkah 2: Load CSV ke MySQL (database olist_oltp_id dibuat otomatis)
python oltp_id/load_to_oltp_id.py
```

## Output

- `data/olist_id/` — 9 file CSV + `_manifest.json`
- MySQL database `olist_oltp_id` — tabel staging `olist_raw` dan 9 tabel 3NF OLTP.

## Manifest

Detail karakteristik sistem ada di:
`data/olist_id/_manifest.json`

## Verifikasi SQL

```sql
USE olist_oltp_id;

-- 1. Format ID Indonesia
SELECT customer_id FROM customers LIMIT 5;
-- Expected: CID-2024-00001, ...

-- 2. Repeat buyer
SELECT customer_unique_id, COUNT(*) FROM customers
GROUP BY customer_unique_id HAVING COUNT(*) > 1 LIMIT 5;

-- 3. Status tidak standar
SELECT * FROM orders WHERE order_status LIKE '%?';

-- 4. Category variants
SELECT DISTINCT product_category_name FROM products LIMIT 20;

-- 5. Harga negatif
SELECT order_id, price FROM order_items WHERE CAST(price AS DECIMAL) < 0 LIMIT 5;

-- 6. Orphan FK (intentional)
SELECT o.customer_id FROM orders o
LEFT JOIN customers c ON o.customer_id = c.customer_id
WHERE c.customer_id IS NULL LIMIT 5;
```
