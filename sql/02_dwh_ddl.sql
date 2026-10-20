-- ============================================================
-- SQL DDL: Data Warehouse Database (dwh_olist) - Star Schema
-- ============================================================

CREATE DATABASE IF NOT EXISTS dwh_olist;
USE dwh_olist;

-- ============================================================
-- 1. TABEL DIMENSI
-- ============================================================

-- 1a. Dim Customer (SCD Type 2)
CREATE TABLE IF NOT EXISTS dim_customer (
    customer_sk        INT AUTO_INCREMENT PRIMARY KEY,
    customer_id        VARCHAR(50) NOT NULL,
    customer_unique_id VARCHAR(50) NOT NULL,
    customer_zip_code  VARCHAR(10),
    customer_city      VARCHAR(100),
    customer_state     VARCHAR(100),
    valid_from         DATETIME NOT NULL DEFAULT '1970-01-01 00:00:00',
    valid_to           DATETIME DEFAULT NULL,
    is_current         TINYINT(1) NOT NULL DEFAULT 1,
    INDEX idx_dc_cust_id (customer_id),
    INDEX idx_dc_unique_id (customer_unique_id),
    INDEX idx_dc_state (customer_state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 1b. Dim Product
CREATE TABLE IF NOT EXISTS dim_product (
    product_sk                 INT AUTO_INCREMENT PRIMARY KEY,
    product_id                 VARCHAR(50) NOT NULL,
    product_category_name      VARCHAR(100),
    product_name_length        INT,
    product_description_length INT,
    product_photos_qty         INT,
    product_weight_g           DECIMAL(10,2),
    product_length_cm          DECIMAL(10,2),
    product_height_cm          DECIMAL(10,2),
    product_width_cm           DECIMAL(10,2),
    UNIQUE KEY uk_product_id (product_id),
    INDEX idx_dp_category (product_category_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 1c. Dim Seller
CREATE TABLE IF NOT EXISTS dim_seller (
    seller_sk       INT AUTO_INCREMENT PRIMARY KEY,
    seller_id       VARCHAR(50) NOT NULL,
    seller_zip_code VARCHAR(10),
    seller_city     VARCHAR(100),
    seller_state    VARCHAR(100),
    UNIQUE KEY uk_seller_id (seller_id),
    INDEX idx_ds_state (seller_state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 1d. Dim Payment Type
CREATE TABLE IF NOT EXISTS dim_payment_type (
    payment_type_sk INT AUTO_INCREMENT PRIMARY KEY,
    payment_type    VARCHAR(50) NOT NULL,
    UNIQUE KEY uk_payment_type (payment_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 1e. Dim Date (Role-Playing Dimension)
CREATE TABLE IF NOT EXISTS dim_date (
    date_sk     INT PRIMARY KEY, -- Format YYYYMMDD
    full_date   DATE NOT NULL,
    day         INT,
    month       INT,
    month_name  VARCHAR(20),
    quarter     INT,
    year        INT,
    day_of_week VARCHAR(20),
    is_weekend  TINYINT(1),
    UNIQUE KEY uk_full_date (full_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ============================================================
-- 2. TABEL FAKTA (2 Tabel Fakta dengan Grain Berbeda)
-- ============================================================

-- Fact 1: fact_order_items
-- Grain: 1 baris per (order_id, order_item_id)
-- Measures: price, freight_value, total_item_value
CREATE TABLE IF NOT EXISTS fact_order_items (
    order_item_sk              BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id                   VARCHAR(50) NOT NULL,
    order_item_id              INT NOT NULL,
    customer_sk                INT NOT NULL,
    product_sk                 INT NOT NULL,
    seller_sk                  INT NOT NULL,
    purchase_date_sk           INT NOT NULL,
    shipping_limit_date_sk     INT NOT NULL,
    order_status               VARCHAR(50),
    price                      DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    freight_value              DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    total_item_value           DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    INDEX idx_foi_order (order_id),
    INDEX idx_foi_cust (customer_sk),
    INDEX idx_foi_prod (product_sk),
    INDEX idx_foi_seller (seller_sk),
    INDEX idx_foi_pdate (purchase_date_sk),
    INDEX idx_foi_sdate (shipping_limit_date_sk),
    CONSTRAINT fk_foi_customer FOREIGN KEY (customer_sk) REFERENCES dim_customer(customer_sk),
    CONSTRAINT fk_foi_product  FOREIGN KEY (product_sk)  REFERENCES dim_product(product_sk),
    CONSTRAINT fk_foi_seller   FOREIGN KEY (seller_sk)   REFERENCES dim_seller(seller_sk),
    CONSTRAINT fk_foi_pdate    FOREIGN KEY (purchase_date_sk) REFERENCES dim_date(date_sk),
    CONSTRAINT fk_foi_sdate    FOREIGN KEY (shipping_limit_date_sk) REFERENCES dim_date(date_sk),
    source_country             VARCHAR(5) NOT NULL DEFAULT 'BR'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Fact 2: fact_order_delivery
-- Grain: 1 baris per order_id
-- Measures: actual_delivery_days, estimated_delivery_days, delivery_delay_days, is_delayed
CREATE TABLE IF NOT EXISTS fact_order_delivery (
    order_delivery_sk          BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id                   VARCHAR(50) NOT NULL,
    customer_sk                INT NOT NULL,
    purchase_date_sk           INT NOT NULL,
    delivered_date_sk          INT NOT NULL,
    estimated_date_sk          INT NOT NULL,
    order_status               VARCHAR(50),
    actual_delivery_days       DECIMAL(8,2),
    estimated_delivery_days    DECIMAL(8,2),
    delivery_delay_days        DECIMAL(8,2),
    is_delayed                 TINYINT(1) NOT NULL DEFAULT 0,
    INDEX idx_fod_order (order_id),
    INDEX idx_fod_cust (customer_sk),
    INDEX idx_fod_pdate (purchase_date_sk),
    INDEX idx_fod_ddate (delivered_date_sk),
    INDEX idx_fod_edate (estimated_date_sk),
    CONSTRAINT fk_fod_customer FOREIGN KEY (customer_sk) REFERENCES dim_customer(customer_sk),
    CONSTRAINT fk_fod_pdate    FOREIGN KEY (purchase_date_sk) REFERENCES dim_date(date_sk),
    CONSTRAINT fk_fod_ddate    FOREIGN KEY (delivered_date_sk) REFERENCES dim_date(date_sk),
    CONSTRAINT fk_fod_edate    FOREIGN KEY (estimated_date_sk) REFERENCES dim_date(date_sk),
    source_country             VARCHAR(5) NOT NULL DEFAULT 'BR'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Fact 3: fact_order_payments
-- Grain: 1 baris per (order_id, payment_sequential)
-- Measures: payment_value, payment_installments
-- FK: dim_payment_type, dim_date (purchase), dim_customer
CREATE TABLE IF NOT EXISTS fact_order_payments (
    payment_fact_sk        BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id               VARCHAR(50) NOT NULL,
    payment_sequential     INT NOT NULL,
    customer_sk            INT NOT NULL,
    payment_type_sk        INT NOT NULL,
    purchase_date_sk       INT NOT NULL,
    payment_value          DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    payment_installments   INT NOT NULL DEFAULT 1,
    INDEX idx_fop_order    (order_id),
    INDEX idx_fop_cust     (customer_sk),
    INDEX idx_fop_paytype  (payment_type_sk),
    INDEX idx_fop_date     (purchase_date_sk),
    UNIQUE KEY uk_fop_grain (order_id, payment_sequential),
    CONSTRAINT fk_fop_customer FOREIGN KEY (customer_sk)       REFERENCES dim_customer(customer_sk),
    CONSTRAINT fk_fop_paytype  FOREIGN KEY (payment_type_sk)   REFERENCES dim_payment_type(payment_type_sk),
    CONSTRAINT fk_fop_date     FOREIGN KEY (purchase_date_sk)  REFERENCES dim_date(date_sk),
    source_country             VARCHAR(5) NOT NULL DEFAULT 'BR'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

