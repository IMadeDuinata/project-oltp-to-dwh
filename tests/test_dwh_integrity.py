"""
Integration Tests Integritas Data Warehouse (pytest):
Menguji:
1. Tidak ada foreign key orphan di tabel fakta (semua merujuk ke SK dimensi valid atau -1 Unknown)
2. Keunikan grain fakta (tidak ada duplikasi baris pada tingkat grain yang ditentukan)
3. Konsistensi measure keuangan: SUM(price) DWH konsisten dengan OLTP setelah dikurangi baris rejected
4. Keberadaan record Unknown (-1) di seluruh tabel dimensi
5. Integritas struktur SCD Type 2 pada dim_customer
"""

import pytest
from sqlalchemy import text
from etl.config import get_oltp_engine, get_dwh_engine


@pytest.fixture(scope="module")
def dwh_engine():
    return get_dwh_engine()


@pytest.fixture(scope="module")
def oltp_engine():
    return get_oltp_engine()


def test_unknown_records_in_dimensions(dwh_engine):
    """Memastikan record Unknown (sk = -1) ada di setiap tabel dimensi."""
    dimensions = {
        "dim_customer": "customer_sk",
        "dim_product": "product_sk",
        "dim_seller": "seller_sk",
        "dim_payment_type": "payment_type_sk",
        "dim_date": "date_sk",
    }
    with dwh_engine.connect() as conn:
        for dim_table, sk_col in dimensions.items():
            cnt = conn.execute(
                text(f"SELECT COUNT(*) FROM `{dim_table}` WHERE `{sk_col}` = -1")
            ).scalar()
            assert cnt == 1, f"Tabel `{dim_table}` tidak memiliki record Unknown (-1)"


def test_fact_order_items_grain_uniqueness(dwh_engine):
    """Memastikan grain (order_id, order_item_id) di fact_order_items unik 100%."""
    with dwh_engine.connect() as conn:
        dups = conn.execute(text("""
            SELECT order_id, order_item_id, COUNT(*) AS cnt
            FROM fact_order_items
            GROUP BY order_id, order_item_id
            HAVING cnt > 1
        """)).fetchall()
        assert len(dups) == 0, f"Ditemukan {len(dups)} duplikat grain di fact_order_items"


def test_fact_order_delivery_grain_uniqueness(dwh_engine):
    """Memastikan grain order_id di fact_order_delivery unik 100%."""
    with dwh_engine.connect() as conn:
        dups = conn.execute(text("""
            SELECT order_id, COUNT(*) AS cnt
            FROM fact_order_delivery
            GROUP BY order_id
            HAVING cnt > 1
        """)).fetchall()
        assert len(dups) == 0, f"Ditemukan {len(dups)} duplikat grain di fact_order_delivery"


def test_no_orphan_foreign_keys_in_facts(dwh_engine):
    """Memastikan tidak ada FK orphan yang tidak terdaftar di dimensi."""
    checks = [
        ("fact_order_items", "customer_sk", "dim_customer", "customer_sk"),
        ("fact_order_items", "product_sk", "dim_product", "product_sk"),
        ("fact_order_items", "seller_sk", "dim_seller", "seller_sk"),
        ("fact_order_items", "purchase_date_sk", "dim_date", "date_sk"),
        ("fact_order_delivery", "customer_sk", "dim_customer", "customer_sk"),
        ("fact_order_delivery", "purchase_date_sk", "dim_date", "date_sk"),
    ]
    with dwh_engine.connect() as conn:
        for f_tbl, f_key, d_tbl, d_key in checks:
            orphan_count = conn.execute(text(f"""
                SELECT COUNT(*)
                FROM `{f_tbl}` f
                LEFT JOIN `{d_tbl}` d ON f.`{f_key}` = d.`{d_key}`
                WHERE d.`{d_key}` IS NULL
            """)).scalar()
            assert orphan_count == 0, f"Ditemukan {orphan_count} orphan FK pada {f_tbl}.{f_key} -> {d_tbl}.{d_key}"


def test_sum_measure_consistency(oltp_engine, dwh_engine):
    """
    Memverifikasi konsistensi measure keuangan:
    SUM(price) di DWH fact_order_items harus sama persis dengan
    SUM(price) di OLTP order_items setelah dikurangi baris item yang direject.
    """
    with dwh_engine.connect() as dwh_conn, oltp_engine.connect() as oltp_conn:
        # Sum price DWH
        dwh_sum = dwh_conn.execute(text("SELECT ROUND(SUM(price), 2) FROM fact_order_items")).scalar()
        
        # Ambil run_id sukses terakhir dari etl_log
        latest_run_id = dwh_conn.execute(
            text("SELECT run_id FROM etl_log WHERE status = 'SUCCESS' ORDER BY log_id DESC LIMIT 1")
        ).scalar()
        assert latest_run_id is not None, "Belum ada run ETL yang berstatus SUCCESS di etl_log"

        # Cari sum price item yang ditolak di rejected_rows pada run_id terakhir
        rej_prices = dwh_conn.execute(text("""
            SELECT JSON_UNQUOTE(JSON_EXTRACT(raw_record_json, '$.price')) AS price_val
            FROM rejected_rows
            WHERE table_source = 'order_items' AND run_id = :rid
        """), {"rid": latest_run_id}).fetchall()
        
        sum_rejected_price = sum(float(r[0]) for r in rej_prices if r[0] is not None and float(r[0]) > 0)
        
        # Sum price OLTP
        oltp_sum = oltp_conn.execute(text("SELECT ROUND(SUM(price), 2) FROM order_items")).scalar()

        # Ekspektasi: dwh_sum + sum_rejected_price == oltp_sum
        diff = abs((float(dwh_sum) + sum_rejected_price) - float(oltp_sum))
        print(f"\nMeasure Audit: DWH Sum={dwh_sum}, Rej Sum={sum_rejected_price}, OLTP Sum={oltp_sum}, Diff={diff}")
        assert diff < 0.01, f"Selisih measure melebihi toleransi: diff={diff}"


def test_dim_customer_scd2_structure(dwh_engine):
    """Memverifikasi kolom SCD Type 2 pada dim_customer."""
    with dwh_engine.connect() as conn:
        res = conn.execute(text("""
            SELECT 
                COUNT(*) AS total_rows,
                SUM(is_current) AS current_rows,
                SUM(CASE WHEN valid_from IS NOT NULL THEN 1 ELSE 0 END) AS valid_from_rows
            FROM dim_customer
            WHERE customer_sk != -1
        """)).mappings().first()

        assert res["total_rows"] > 0
        assert res["total_rows"] == res["current_rows"]
        assert res["total_rows"] == res["valid_from_rows"]
