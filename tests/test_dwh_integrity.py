"""
Integration Tests Integritas Data Warehouse (pytest):
Menguji:
1. Tidak ada foreign key orphan di tabel fakta (semua merujuk ke SK dimensi valid atau -1 Unknown)
2. Keunikan grain fakta (tidak ada duplikasi baris pada tingkat grain yang ditentukan)
3. Konsistensi measure keuangan: SUM(price) DWH konsisten dengan OLTP setelah dikurangi baris rejected
4. Keberadaan record Unknown (-1) di seluruh tabel dimensi
5. Integritas struktur SCD Type 2 pada dim_customer
"""

import json
import pytest
from sqlalchemy import text
from etl.config import get_oltp_engine, get_oltp_br_engine, get_oltp_id_engine, get_dwh_engine


@pytest.fixture(scope="module")
def dwh_engine():
    return get_dwh_engine()


@pytest.fixture(scope="module")
def oltp_engine():
    return get_oltp_engine()


@pytest.fixture(scope="module")
def oltp_br_engine():
    return get_oltp_br_engine()


@pytest.fixture(scope="module")
def oltp_id_engine():
    return get_oltp_id_engine()


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


def test_sum_measure_consistency(oltp_br_engine, oltp_id_engine, dwh_engine):
    """
    Memverifikasi konsistensi measure keuangan multi-source:
    SUM(price) di DWH fact_order_items per country harus sama persis dengan
    SUM(price) di masing-masing OLTP (BR & ID) setelah memperhitungkan baris item yang direject.
    """
    with dwh_engine.connect() as dwh_conn:
        # Ambil run_id sukses terakhir dari etl_log
        latest_run_id = dwh_conn.execute(
            text("SELECT run_id FROM etl_log WHERE status = 'SUCCESS' ORDER BY log_id DESC LIMIT 1")
        ).scalar()
        assert latest_run_id is not None, "Belum ada run ETL yang berstatus SUCCESS di etl_log"

        sources = [
            ("BR", oltp_br_engine, "order_items", "price"),
            ("ID", oltp_id_engine, "order_items", "price"),
        ]

        for country, engine, tbl_name, col_name in sources:
            dwh_sum = dwh_conn.execute(
                text("SELECT COALESCE(ROUND(SUM(price), 2), 0.00) FROM fact_order_items WHERE source_country = :sc"),
                {"sc": country}
            ).scalar()

            rej_records = dwh_conn.execute(text("""
                SELECT raw_record_json
                FROM rejected_rows
                WHERE table_source = :tbl AND run_id = :rid
            """), {"tbl": tbl_name, "rid": latest_run_id}).fetchall()

            sum_rejected = 0.0
            for r in rej_records:
                rec = json.loads(r[0])
                if rec.get("source_country") == country:
                    val = rec.get("price")
                    if val is not None:
                        try:
                            sum_rejected += float(val)
                        except (ValueError, TypeError):
                            pass

            with engine.connect() as oltp_conn:
                oltp_sum = oltp_conn.execute(
                    text(f"SELECT COALESCE(ROUND(SUM(CAST({col_name} AS DECIMAL(20,2))), 2), 0.00) FROM {tbl_name}")
                ).scalar()

            diff = abs((float(dwh_sum) + sum_rejected) - float(oltp_sum))
            print(f"\nMeasure Audit [{country}]: DWH Sum={dwh_sum}, Rej Sum={sum_rejected:.2f}, OLTP Sum={oltp_sum}, Diff={diff:.4f}")
            assert diff < 0.01, f"Selisih measure melebihi toleransi pada source {country}: diff={diff}"


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
