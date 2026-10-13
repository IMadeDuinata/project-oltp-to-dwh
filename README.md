# 🛒 Olist E-Commerce — OLTP to DWH Pipeline

End-to-end data engineering project: load Brazilian E-Commerce (Olist) dataset from CSV into MySQL OLTP, transform into a Star Schema Data Warehouse, and generate business insights.

## 📊 Project Overview

Pipeline data yang mengubah dataset e-commerce mentah (113,390 baris) menjadi Data Warehouse siap analisis menggunakan **Star Schema**.

## 🏗️ Architecture

```
data/Olist.csv  →  [load_oltp.py]  →  oltp_olist.olist_raw
                                            ↓
                                    [transform_oltp_to_dwh.py]
                                            ↓
                                    dwh_olist (Star Schema)
                                            ↓
                                    [analytics.py]
                                            ↓
                                        📈 Insights
```

## 📁 Project Structure

```
project-oltp-to-dwh/
├── data/                          # Dataset (tidak di-commit)
│   └── Olist.csv
├── oltp/
│   └── load_oltp.py              # Load CSV → MySQL OLTP
├── dwh/
│   └── create_star_schema.py     # Create star schema tables
├── etl/
│   ├── transform_oltp_to_dwh.py  # ETL: OLTP → DWH
│   └── analytics.py              # Business insight queries
├── .env.example                  # Template .env
├── .gitignore
├── requirements.txt
└── README.md
```

## 🛠️ Tech Stack

- **Python 3.13** — main language
- **MySQL 8.0** — database (OLTP + DWH)
- **Pandas** — data manipulation
- **SQLAlchemy + PyMySQL** — DB connector
- **python-dotenv** — config management

## 🚀 Cara Menjalankan

### 1. Prasyarat
- Python 3.10+
- MySQL 8.0+
- Git

### 2. Clone Repository
```bash
git clone https://github.com/USERNAME/project-oltp-to-dwh.git
cd project-oltp-to-dwh
```

### 3. Download Dataset
Download [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) dari Kaggle, simpan sebagai `data/Olist.csv`.

### 4. Setup Virtual Environment
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 5. Setup Database
```sql
CREATE DATABASE oltp_olist;
CREATE DATABASE dwh_olist;
```

### 6. Konfigurasi `.env`
Copy `.env.example` → `.env`, isi password MySQL kamu.

### 7. Jalankan Pipeline
```bash
python oltp/load_oltp.py
python dwh/create_star_schema.py
python etl/transform_oltp_to_dwh.py
python etl/analytics.py
```

## 📊 Business Insights

### Top 5 Kategori Produk (by Revenue)
| Rank | Kategori | Revenue (R$) |
|------|----------|--------------|
| 1 | beleza_saude | 1,271,413 |
| 2 | relogios_presentes | 1,212,373 |
| 3 | cama_mesa_banho | 1,077,834 |
| 4 | esporte_lazer | 990,418 |
| 5 | informatica_acessorios | 918,838 |

### Revenue Growth
| Tahun | Transaksi | Revenue (R$) |
|-------|-----------|--------------|
| 2016 | 335 | 42,241 |
| 2017 | 51,196 | 6,158,929 |
| 2018 | 61,856 | 7,425,643 |

### Metode Pembayaran
| Metode | Transaksi | Persentase |
|--------|-----------|------------|
| credit_card | 83,703 | 73.8% |
| boleto | 22,047 | 19.4% |
| voucher | 6,012 | 5.3% |
| debit_card | 1,625 | 1.4% |

## 🎓 What I Learned

- **ETL Pipeline** — extract CSV, transform dengan Pandas, load ke MySQL
- **Data Warehouse Design** — star schema dengan fact & dimension tables
- **Data Quality** — handle 3 baris 'column shift' yang ditemukan
- **SQL Analytics** — complex JOIN, GROUP BY, DATEDIFF
- **Security** — credentials di `.env` (bukan hardcode)

## 👤 Author

**I Made Duinata**
- GitHub: [@USERNAME](https://github.com/USERNAME)

## 📄 License

Educational project. Dataset credit to [Olist on Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce).
