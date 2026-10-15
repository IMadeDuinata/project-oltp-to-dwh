# Laporan Injeksi Data Kotor (Dirty Data Injection Summary)

**Tanggal Dijalankan**: 2026-10-15 13:30:03  
**Target Tabel**: `olist_raw`  
**Random Seed**: 42 (deterministik)  
**Total Baris Diinjeksi**: 9  

---

## Ringkasan Baris per Jenis Kotoran

| Jenis Kotoran | Jumlah Baris |
|---|---|
| Duplikasi persis (order_id+item) | 1 |
| Bad Logic: delivered < purchase | 1 |
| Bad Logic: estimated < purchase | 1 |
| Bad Logic: price <= 0 | 1 |
| Bad Logic: freight_value < 0 | 1 |
| Bad Logic: future purchase date | 1 |
| Column Shift: invalid order_status | 1 |
| Column Shift: invalid payment_type | 2 |

---

## Detail Order ID yang Diinjeksi

| order_id | Jenis Skenario |
|---|---|
| `DIRTY_DUP_EXACT_001` | Duplikasi persis (2 baris identical) |
| `DIRTY_LOGIC_DELV_BEFORE_PURCH_002` | Bad Logic: delivered < purchase |
| `DIRTY_LOGIC_EST_BEFORE_PURCH_003` | Bad Logic: estimated < purchase |
| `DIRTY_LOGIC_ZERO_PRICE_004` | Bad Logic: price = 0 |
| `DIRTY_LOGIC_NEG_FREIGHT_005` | Bad Logic: freight_value < 0 |
| `DIRTY_LOGIC_FUTURE_DATE_006` | Bad Logic: purchase date masa depan (2035) |
| `DIRTY_SHIFT_COL_007` | Column Shift: order_status='2018', payment_type='SP' |
| `DIRTY_SHIFT_COL_008` | Column Shift: payment_type='RJ' |

---

> **Catatan**: Data kotor ini digunakan untuk menguji pipeline cleansing ETL.
> Semua baris diinjeksi dengan seed deterministik `random.seed(42)` agar reproducible.