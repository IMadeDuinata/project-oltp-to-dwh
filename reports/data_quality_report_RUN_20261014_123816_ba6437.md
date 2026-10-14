# 📋 Laporan Kualitas Data ETL (Before vs After Cleansing)

- **Run ID**: `RUN_20261014_123816_ba6437`
- **Waktu Eksekusi**: `2026-10-14 12:38:16`
- **Total Baris Ditolak (Quarantine)**: `104`

---

## 1. Perbandingan Baris Data: Before vs After

| Nama Tabel / Entitas | Baris Sebelum Cleansing (Before) | Baris Lolos Cleansing (After) | Selisih (Ditolak / Didrop) |
|---|---|---|---|
| **Customers** | 98,674 | 98,674 | 0 |
| **Products** | 32,959 | 32,959 | 0 |
| **Sellers** | 3,103 | 3,103 | 0 |
| **Orders** | 98,674 | 98,642 | 32 |
| **Order Items** | 112,660 | 112,623 | 37 |
| **Order Payments** | 103,065 | 103,031 | 34 |

---

## 2. Rincian Pelanggaran Data & Alasan Karantina (Rejected Rows)

| No | Aturan / Masalah Validasi | Alasan Penolakan | Jumlah Baris Ditolak | Tindakan |
|---|---|---|---|---|
| 1 | Data Anomaly | `order_item references an order rejected during cleansing` | 34 | Karantina ke `rejected_rows` |
| 2 | Data Anomaly | `payment references an order rejected during cleansing` | 31 | Karantina ke `rejected_rows` |
| 3 | Data Anomaly | `order_approved_at is null on active/non-canceled order` | 14 | Karantina ke `rejected_rows` |
| 4 | Data Anomaly | `delivered status but delivery date is null` | 8 | Karantina ke `rejected_rows` |
| 5 | Data Anomaly | `canceled status but delivery date is present` | 6 | Karantina ke `rejected_rows` |
| 6 | Data Anomaly | `invalid payment_type domain (suspected column shift containing state code)` | 3 | Karantina ke `rejected_rows` |
| 7 | Data Anomaly | `duplicate_business_key_order_item` | 2 | Karantina ke `rejected_rows` |
| 8 | Data Anomaly | `order delivered before purchase timestamp` | 1 | Karantina ke `rejected_rows` |
| 9 | Data Anomaly | `estimated delivery date before purchase timestamp` | 1 | Karantina ke `rejected_rows` |
| 10 | Data Anomaly | `purchase timestamp in future date` | 1 | Karantina ke `rejected_rows` |
| 11 | Data Anomaly | `price must be greater than zero` | 1 | Karantina ke `rejected_rows` |
| 12 | Data Anomaly | `freight value cannot be negative` | 1 | Karantina ke `rejected_rows` |
| 13 | Data Anomaly | `invalid order_status domain (suspected column shift or corrupted value)` | 1 | Karantina ke `rejected_rows` |

---

## 3. Catatan Keputusan Teknis Cleansing
1. **Null Handling**:
   - `product_category_name` NULL diimputasi dengan nilai `'unknown'` agar produk tetap dapat dianalisis pada Star Schema.
   - Ukuran fisik produk (berat, panjang, lebar, tinggi) NULL diimputasi dengan 0.
   - Transaksi dengan `order_approved_at` NULL pada status non-canceled ditolak (karena melanggar SOP pembayaran).
2. **Deduplikasi**:
   - Nama kota dan provinsi dinormalisasi (lowercase dan strip whitespace) sebelum pemeriksaan duplikasi.
   - Duplikat persis dan duplikat business key `(order_id, order_item_id)` dikarantina ke `rejected_rows`.
3. **Bad Business Logic**:
   - Tanggal pengiriman lebih awal dari tanggal pembelian (`delivered < purchase`) ditolak.
   - Tanggal estimasi lebih awal dari tanggal pembelian (`estimated < purchase`) ditolak.
   - Status `delivered` tanpa tanggal sampai ditolak.
   - Status `canceled` dengan tanggal pengiriman ditolak.
   - Harga produk `<= 0` atau ongkos kirim `< 0` ditolak.
   - Tanggal pembelian di masa depan (`future date`) ditolak.
4. **Validasi Domain & Column Shift**:
   - Nilai `order_status` yang bukan domain valid (misal angka tahun `'2018'`) atau `payment_type` berisi kode negara bagian (`'SP'`, `'RJ'`) dideteksi sebagai column shift / korupsi data dan dikarantina.
