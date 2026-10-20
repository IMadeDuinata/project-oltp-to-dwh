import os
import sys
import json
from pathlib import Path
import numpy as np
import pandas as pd
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
OUT_DIR = BASE_DIR / "data" / "olist_id"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SEED = 42
SAMPLE_RATE = 0.05
rng = np.random.default_rng(SEED)

INDONESIAN_CITIES = [
    "Jakarta", "Surabaya", "Bandung", "Medan", "Bekasi",
    "Tangerang", "Depok", "Semarang", "Palembang", "Makassar",
    "Yogyakarta", "Denpasar", "Batam", "Pekanbaru", "Bogor",
    "Malang", "Padang", "Manado", "Bandar Lampung", "Samarinda",
    "Pontianak", "Banjarmasin", "Balikpapan", "Jayapura", "Ambon",
    "Mataram", "Kupang", "Ternate", "Sorong", "Kendari",
    "Palu", "Gorontalo", "Mamuju", "Bengkulu", "Pangkal Pinang",
    "Tanjung Pinang", "Serang", "Cirebon", "Solo", "Kediri",
]

INDONESIAN_PROVINCES = [
    "Aceh", "Sumatera Utara", "Sumatera Barat", "Riau",
    "Jambi", "Sumatera Selatan", "Bengkulu", "Lampung",
    "Kep. Bangka Belitung", "Kep. Riau",
    "DKI Jakarta", "Jawa Barat", "Jawa Tengah", "DI Yogyakarta",
    "Jawa Timur", "Banten",
    "Bali", "NTB", "NTT",
    "Kalimantan Barat", "Kalimantan Tengah", "Kalimantan Selatan",
    "Kalimantan Timur", "Kalimantan Utara",
    "Sulawesi Utara", "Sulawesi Tengah", "Sulawesi Selatan",
    "Sulawesi Tenggara", "Gorontalo", "Sulawesi Barat",
    "Maluku", "Maluku Utara",
    "Papua Barat", "Papua",
]  # 34 provinsi

NON_STANDARD_STATUSES = ["PENDING?", "unknown", "SHIPPED?"]

CATEGORY_TRANSLATION_MAP = {
    "beleza_saude": "Kecantikan & Kesehatan",
    "informatica_acessorios": "Komputer & Aksesoris",
    "automotivo": "Otomotif",
    "cama_mesa_banho": "Perlengkapan Rumah & Tidur",
    "moveis_decoracao": "Furnitur & Dekorasi",
    "esporte_lazer": "Olahraga & Rekreasi",
    "bebes": "Perlengkapan Bayi",
    "utilidades_domesticas": "Peralatan Rumah Tangga",
    "telefonia": "Telepon & Komunikasi",
    "relogios_presentes": "Jam Tangan & Hadiah",
    "alimentos_bebidas": "Makanan & Minuman",
    "brinquedos": "Mainan & Hobi",
    "fashion_bolsas_e_acessorios": "Fashion & Tas",
    "eletronicos": "Elektronik",
    "papelaria": "Alat Tulis Kantor",
    "pet_shop": "Kebutuhan Hewan Peliharaan",
    "ferramentas_jardim": "Alat Pertukangan & Taman",
    "consoles_games": "Konsol & Game",
    "perfumaria": "Parfum & Wewangian",
    "artes": "Kesenian & Kerajinan"
}

def make_id_map(series: pd.Series, prefix: str) -> dict:
    unique_ids = series.dropna().unique()
    return {
        old_id: f"{prefix}-2024-{str(i+1).zfill(5)}"
        for i, old_id in enumerate(sorted(unique_ids))
    }

def mangle_date(ts_str, fmt_choice):
    if pd.isna(ts_str) or ts_str == "":
        return ts_str
    try:
        dt = pd.to_datetime(ts_str)
        if fmt_choice == 0:
            return dt.strftime("%d/%m/%Y %H:%M:%S")
        else:
            return dt.strftime("%m-%d-%Y %H:%M:%S")
    except Exception:
        return ts_str

def main():
    print("=" * 60)
    print("GENERATING OLIST INDONESIA DATASET (5% sample, deterministic)")
    print("=" * 60)

    # 1. Anchor Orders
    orders_raw_path = RAW_DIR / "olist_orders_dataset.csv"
    print(f"Reading orders anchor: {orders_raw_path}")
    df_orders_full = pd.read_csv(orders_raw_path)
    
    # Deterministic sample 5%
    sample_indices = rng.choice(len(df_orders_full), size=int(len(df_orders_full) * SAMPLE_RATE), replace=False)
    sample_indices.sort()
    df_orders = df_orders_full.iloc[sample_indices].copy().reset_index(drop=True)
    
    anchor_order_ids = set(df_orders["order_id"].unique())
    anchor_customer_ids = set(df_orders["customer_id"].unique())
    print(f"Sampled orders: {len(df_orders)} rows | Unique customer_ids: {len(anchor_customer_ids)}")

    # 2. Filter related tables
    print("Reading and filtering related raw datasets...")
    df_customers = pd.read_csv(RAW_DIR / "olist_customers_dataset.csv")
    df_customers = df_customers[df_customers["customer_id"].isin(anchor_customer_ids)].copy().reset_index(drop=True)

    df_items = pd.read_csv(RAW_DIR / "olist_order_items_dataset.csv")
    df_items = df_items[df_items["order_id"].isin(anchor_order_ids)].copy().reset_index(drop=True)

    df_payments = pd.read_csv(RAW_DIR / "olist_order_payments_dataset.csv")
    df_payments = df_payments[df_payments["order_id"].isin(anchor_order_ids)].copy().reset_index(drop=True)

    df_reviews = pd.read_csv(RAW_DIR / "olist_order_reviews_dataset.csv")
    df_reviews = df_reviews[df_reviews["order_id"].isin(anchor_order_ids)].copy().reset_index(drop=True)

    anchor_product_ids = set(df_items["product_id"].dropna().unique())
    df_products = pd.read_csv(RAW_DIR / "olist_products_dataset.csv")
    df_products = df_products[df_products["product_id"].isin(anchor_product_ids)].copy().reset_index(drop=True)

    anchor_seller_ids = set(df_items["seller_id"].dropna().unique())
    df_sellers = pd.read_csv(RAW_DIR / "olist_sellers_dataset.csv")
    df_sellers = df_sellers[df_sellers["seller_id"].isin(anchor_seller_ids)].copy().reset_index(drop=True)

    df_geo_full = pd.read_csv(RAW_DIR / "olist_geolocation_dataset.csv")
    geo_indices = rng.choice(len(df_geo_full), size=min(3000, len(df_geo_full)), replace=False)
    geo_indices.sort()
    df_geo = df_geo_full.iloc[geo_indices].copy().reset_index(drop=True)

    df_cat_trans = pd.read_csv(RAW_DIR / "product_category_name_translation.csv")

    # 3. Create ID Maps
    print("Building deterministic ID maps...")
    order_map = make_id_map(df_orders["order_id"], "ORD")
    cust_map = make_id_map(df_customers["customer_id"], "CID")
    uid_map = make_id_map(df_customers["customer_unique_id"], "UID")
    prod_map = make_id_map(df_products["product_id"], "PRD")
    seller_map = make_id_map(df_sellers["seller_id"], "SLR")
    rev_map = make_id_map(df_reviews["review_id"], "REV")

    # 4. Substitute IDs
    print("Applying ID substitutions...")
    df_orders["order_id"] = df_orders["order_id"].map(order_map)
    df_orders["customer_id"] = df_orders["customer_id"].map(cust_map)

    df_customers["customer_id"] = df_customers["customer_id"].map(cust_map)
    df_customers["customer_unique_id"] = df_customers["customer_unique_id"].map(uid_map)

    df_items["order_id"] = df_items["order_id"].map(order_map)
    df_items["product_id"] = df_items["product_id"].map(prod_map)
    df_items["seller_id"] = df_items["seller_id"].map(seller_map)

    df_payments["order_id"] = df_payments["order_id"].map(order_map)

    df_reviews["review_id"] = df_reviews["review_id"].map(rev_map)
    df_reviews["order_id"] = df_reviews["order_id"].map(order_map)

    df_products["product_id"] = df_products["product_id"].map(prod_map)
    df_sellers["seller_id"] = df_sellers["seller_id"].map(seller_map)

    # 5. Mutate Geography to Indonesia
    print("Mutating geography (cities, provinces, zip codes)...")
    # Customers geography
    c_city_idx = rng.integers(0, len(INDONESIAN_CITIES), size=len(df_customers))
    c_prov_idx = rng.integers(0, len(INDONESIAN_PROVINCES), size=len(df_customers))
    df_customers["customer_city"] = [INDONESIAN_CITIES[i] for i in c_city_idx]
    df_customers["customer_state"] = [INDONESIAN_PROVINCES[i] for i in c_prov_idx]
    df_customers["customer_zip_code_prefix"] = [str(z).zfill(5) for z in rng.integers(10000, 99999, size=len(df_customers))]

    # Sellers geography
    s_city_idx = rng.integers(0, len(INDONESIAN_CITIES), size=len(df_sellers))
    s_prov_idx = rng.integers(0, len(INDONESIAN_PROVINCES), size=len(df_sellers))
    df_sellers["seller_city"] = [INDONESIAN_CITIES[i] for i in s_city_idx]
    df_sellers["seller_state"] = [INDONESIAN_PROVINCES[i] for i in s_prov_idx]
    df_sellers["seller_zip_code_prefix"] = [str(z).zfill(5) for z in rng.integers(10000, 99999, size=len(df_sellers))]

    # Geolocation geography
    g_city_idx = rng.integers(0, len(INDONESIAN_CITIES), size=len(df_geo))
    g_prov_idx = rng.integers(0, len(INDONESIAN_PROVINCES), size=len(df_geo))
    df_geo["geolocation_city"] = [INDONESIAN_CITIES[i] for i in g_city_idx]
    df_geo["geolocation_state"] = [INDONESIAN_PROVINCES[i] for i in g_prov_idx]
    df_geo["geolocation_zip_code_prefix"] = [str(z).zfill(5) for z in rng.integers(10000, 99999, size=len(df_geo))]

    # 6. Category Variants for Products
    print("Generating product category variants...")
    df_products["product_category_name_original"] = df_products["product_category_name"]
    
    variant_names = []
    for idx, row in df_products.iterrows():
        pt_cat = row["product_category_name"]
        if pd.isna(pt_cat):
            variant_names.append(pt_cat)
            continue
        
        # Canonical name
        if pt_cat in CATEGORY_TRANSLATION_MAP:
            canonical = CATEGORY_TRANSLATION_MAP[pt_cat]
        else:
            # Fallback format: Title Case from snake_case
            canonical = pt_cat.replace("_", " ").title()

        v_type = idx % 5
        if v_type == 0:
            variant_names.append(canonical)
        elif v_type == 1:
            variant_names.append(canonical.lower())
        elif v_type == 2:
            variant_names.append(canonical.lower().replace(" ", "_").replace("&", "").replace("__", "_"))
        elif v_type == 3:
            variant_names.append(canonical.split()[0])
        elif v_type == 4:
            variant_names.append(pt_cat)  # PT untranslated
            
    df_products["product_category_name"] = variant_names

    # 7. Inject System Characteristics
    print("Injecting Indonesian system characteristics (immature system representation)...")
    
    # Characteristic 1: orders mixed date formats (5%)
    # Characteristic 2: orders impossible date (1%)
    # Process order timestamps as string
    date_cols = [
        "order_purchase_timestamp", "order_approved_at",
        "order_delivered_carrier_date", "order_delivered_customer_date",
        "order_estimated_delivery_date"
    ]
    for dc in date_cols:
        df_orders[dc] = df_orders[dc].astype(str).replace({"nan": None, "NaT": None, "None": None})

    rand_date_c1 = rng.random(len(df_orders))
    rand_fmt_c1 = rng.integers(0, 2, size=len(df_orders))
    rand_date_c2 = rng.random(len(df_orders))

    for i in range(len(df_orders)):
        if rand_date_c2[i] < 0.01:
            df_orders.at[i, "order_purchase_timestamp"] = "2099-12-31 00:00:00"
        elif rand_date_c1[i] < 0.05:
            df_orders.at[i, "order_purchase_timestamp"] = mangle_date(
                df_orders.at[i, "order_purchase_timestamp"], rand_fmt_c1[i]
            )

    # Characteristic 3: orders non-standard status (2%)
    rand_status = rng.random(len(df_orders))
    status_choice = rng.integers(0, len(NON_STANDARD_STATUSES), size=len(df_orders))
    for i in range(len(df_orders)):
        if rand_status[i] < 0.02:
            df_orders.at[i, "order_status"] = NON_STANDARD_STATUSES[status_choice[i]]

    # Characteristic 4: orders orphan FK customer_id (2%)
    rand_orphan = rng.random(len(df_orders))
    for i in range(len(df_orders)):
        if rand_orphan[i] < 0.02:
            df_orders.at[i, "customer_id"] = f"ORPHAN-CID-{i+1}"

    # Characteristic 5: customers duplicates (2%)
    dup_size = int(len(df_customers) * 0.02)
    dup_sample_indices = rng.choice(len(df_customers), size=dup_size, replace=False)
    dup_customers = df_customers.iloc[dup_sample_indices].copy()
    df_customers = pd.concat([df_customers, dup_customers], ignore_index=True)

    # Characteristic 6: customers whitespace and case inconsistency (5%)
    rand_c_ws = rng.random(len(df_customers))
    for i in range(len(df_customers)):
        if rand_c_ws[i] < 0.05:
            city = str(df_customers.at[i, "customer_city"])
            state = str(df_customers.at[i, "customer_state"])
            if i % 2 == 0:
                df_customers.at[i, "customer_city"] = f"  {city.upper()} "
                df_customers.at[i, "customer_state"] = state.lower()
            else:
                df_customers.at[i, "customer_city"] = city.lower()
                df_customers.at[i, "customer_state"] = f" {state.upper()}  "

    # Characteristic 7: customers NULL unique_id (1%)
    rand_c_null = rng.random(len(df_customers))
    for i in range(len(df_customers)):
        if rand_c_null[i] < 0.01:
            df_customers.at[i, "customer_unique_id"] = None

    # Characteristic 8: order_items negative price (2%)
    # Characteristic 9: order_items extreme outlier (1%)
    df_items["price"] = df_items["price"].astype(str)
    df_items["freight_value"] = df_items["freight_value"].astype(str)
    df_items["shipping_limit_date"] = df_items["shipping_limit_date"].astype(str)

    rand_item_c8 = rng.random(len(df_items))
    rand_item_c9 = rng.random(len(df_items))
    for i in range(len(df_items)):
        if rand_item_c9[i] < 0.01:
            df_items.at[i, "price"] = "999999999"
        elif rand_item_c8[i] < 0.02:
            try:
                val = float(df_items.at[i, "price"])
                df_items.at[i, "price"] = str(-abs(val))
            except Exception:
                pass

    # Characteristic 10: payments negative value (1%)
    df_payments["payment_value"] = df_payments["payment_value"].astype(str)
    rand_pay = rng.random(len(df_payments))
    for i in range(len(df_payments)):
        if rand_pay[i] < 0.01:
            try:
                val = float(df_payments.at[i, "payment_value"])
                df_payments.at[i, "payment_value"] = str(-abs(val))
            except Exception:
                pass

    # Save to CSV
    print("Saving all datasets to data/olist_id/ ...")
    csv_files = {
        "orders": (df_orders, "orders.csv"),
        "customers": (df_customers, "customers.csv"),
        "order_items": (df_items, "order_items.csv"),
        "products": (df_products, "products.csv"),
        "sellers": (df_sellers, "sellers.csv"),
        "order_payments": (df_payments, "order_payments.csv"),
        "order_reviews": (df_reviews, "order_reviews.csv"),
        "geolocation": (df_geo, "geolocation.csv"),
        "category_translation": (df_cat_trans, "category_translation.csv"),
    }

    row_counts = {}
    for key, (df, filename) in csv_files.items():
        filepath = OUT_DIR / filename
        df.to_csv(filepath, index=False)
        row_counts[key] = len(df)
        print(f" -> {filename}: {len(df):,} rows")

    # Generate _manifest.json
    manifest = {
        "config": {
            "seed": SEED,
            "sample_rate": SAMPLE_RATE,
            "source_anchor": "data/raw/olist_orders_dataset.csv",
            "generated_at": datetime.now().isoformat()
        },
        "row_counts": row_counts,
        "system_characteristics": [
            {"id": 1, "table": "orders", "column": "order_purchase_timestamp", "characteristic": "Format tanggal campur (DD/MM/YYYY, MM-DD-YYYY)", "rate": "5%"},
            {"id": 2, "table": "orders", "column": "order_purchase_timestamp", "characteristic": "Tanggal mustahil (2099-12-31)", "rate": "1%"},
            {"id": 3, "table": "orders", "column": "order_status", "characteristic": "Status tidak standar (PENDING?, unknown, SHIPPED?)", "rate": "2%"},
            {"id": 4, "table": "orders", "column": "customer_id", "characteristic": "Orphan FK (customer_id tidak ada di tabel customers)", "rate": "2%"},
            {"id": 5, "table": "customers", "column": "*", "characteristic": "Duplikasi baris (proses dedup belum jalan)", "rate": "2%"},
            {"id": 6, "table": "customers", "column": "customer_city/state", "characteristic": "Whitespace + case inconsistency", "rate": "5%"},
            {"id": 7, "table": "customers", "column": "customer_unique_id", "characteristic": "NULL unique_id (validasi lemah)", "rate": "1%"},
            {"id": 8, "table": "order_items", "column": "price", "characteristic": "Harga negatif (bug input)", "rate": "2%"},
            {"id": 9, "table": "order_items", "column": "price", "characteristic": "Outlier ekstrem (999999999)", "rate": "1%"},
            {"id": 10, "table": "order_payments", "column": "payment_value", "characteristic": "Payment value negatif", "rate": "1%"}
        ],
        "category_variants": {
            "var0": "canonical ID bahasa Indonesia",
            "var1": "lowercase",
            "var2": "snake_case",
            "var3": "truncated (kata pertama)",
            "var4": "PT untranslated (nama asli Portugis)"
        },
        "id_format": {
            "customer_id": "CID-2024-NNNNN",
            "customer_unique_id": "UID-2024-NNNNN",
            "order_id": "ORD-2024-NNNNN",
            "product_id": "PRD-2024-NNNNN",
            "seller_id": "SLR-2024-NNNNN",
            "review_id": "REV-2024-NNNNN"
        }
    }

    manifest_path = OUT_DIR / "_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Manifest written to: {manifest_path}")
    print("=" * 60)
    print("GENERATION COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()
