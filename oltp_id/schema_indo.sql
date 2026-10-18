-- ============================================================
-- DDL: OLTP Indonesia (olist_oltp_id)
-- Deviasi dari sql/01_oltp_ddl.sql:
--   1. Database: olist_oltp_id
--   2. orders timestamps: VARCHAR(50) — format tanggal campur
--   3. products: tambah kolom product_category_name_original
-- ============================================================

CREATE DATABASE IF NOT EXISTS olist_oltp_id;
USE olist_oltp_id;

-- STAGING
CREATE TABLE IF NOT EXISTS olist_raw (
    raw_id                         BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id                       VARCHAR(100),
    order_item_id                  VARCHAR(50),
    product_id                     VARCHAR(100),
    seller_id                      VARCHAR(100),
    seller_zip_code_prefix         VARCHAR(50),
    seller_city                    VARCHAR(100),
    seller_state                   VARCHAR(50),
    shipping_limit_date            VARCHAR(50),
    price                          VARCHAR(50),
    freight_value                  VARCHAR(50),
    payment_sequential             VARCHAR(50),
    payment_type                   VARCHAR(50),
    payment_installments           VARCHAR(50),
    payment_value                  VARCHAR(50),
    customer_id                    VARCHAR(100),
    customer_unique_id             VARCHAR(100),
    customer_zip_code_prefix       VARCHAR(50),
    customer_city                  VARCHAR(100),
    customer_state                 VARCHAR(50),
    order_status                   VARCHAR(50),
    order_purchase_timestamp       VARCHAR(50),   -- VARCHAR! bukan DATETIME
    order_approved_at              VARCHAR(50),
    order_delivered_carrier_date   VARCHAR(50),
    order_delivered_customer_date  VARCHAR(50),
    order_estimated_delivery_date  VARCHAR(50),
    product_category_name          VARCHAR(100),
    product_category_name_original VARCHAR(100),  -- tambahan
    product_name_lenght            VARCHAR(50),
    product_description_lenght     VARCHAR(50),
    product_photos_qty             VARCHAR(50),
    product_weight_g               VARCHAR(50),
    product_length_cm              VARCHAR(50),
    product_height_cm              VARCHAR(50),
    product_width_cm               VARCHAR(50),
    INDEX idx_raw_order_id (order_id),
    INDEX idx_raw_customer_id (customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- CUSTOMERS
CREATE TABLE IF NOT EXISTS customers (
    customer_id              VARCHAR(50) PRIMARY KEY,  -- format: CID-2024-NNNNN
    customer_unique_id       VARCHAR(50),               -- nullable: karakteristik sistem
    customer_zip_code_prefix VARCHAR(10),
    customer_city            VARCHAR(100),
    customer_state           VARCHAR(100),              -- lebih panjang: nama provinsi lengkap
    INDEX idx_cust_unique (customer_unique_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- PRODUCTS
CREATE TABLE IF NOT EXISTS products (
    product_id                     VARCHAR(50) PRIMARY KEY,  -- format: PRD-2024-NNNNN
    product_category_name          VARCHAR(100),              -- VARIANT (bisa mixed format)
    product_category_name_original VARCHAR(100),              -- PT asli, canonical
    product_name_length            INT,
    product_description_length     INT,
    product_photos_qty             INT,
    product_weight_g               DECIMAL(10,2),
    product_length_cm              DECIMAL(10,2),
    product_height_cm              DECIMAL(10,2),
    product_width_cm               DECIMAL(10,2),
    INDEX idx_prod_cat (product_category_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- SELLERS
CREATE TABLE IF NOT EXISTS sellers (
    seller_id              VARCHAR(50) PRIMARY KEY,  -- format: SLR-2024-NNNNN
    seller_zip_code_prefix VARCHAR(10),
    seller_city            VARCHAR(100),
    seller_state           VARCHAR(100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ORDERS  ← VARCHAR timestamps!
CREATE TABLE IF NOT EXISTS orders (
    order_id                      VARCHAR(50) PRIMARY KEY,  -- format: ORD-2024-NNNNN
    customer_id                   VARCHAR(50) NOT NULL,
    order_status                  VARCHAR(50),
    order_purchase_timestamp      VARCHAR(50),   -- VARCHAR: format campur
    order_approved_at             VARCHAR(50),
    order_delivered_carrier_date  VARCHAR(50),
    order_delivered_customer_date VARCHAR(50),
    order_estimated_delivery_date VARCHAR(50),
    INDEX idx_ord_cust (customer_id),
    INDEX idx_ord_status (order_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ORDER_ITEMS
CREATE TABLE IF NOT EXISTS order_items (
    item_internal_id    BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id            VARCHAR(50) NOT NULL,
    order_item_id       INT NOT NULL,
    product_id          VARCHAR(50),
    seller_id           VARCHAR(50),
    shipping_limit_date VARCHAR(50),  -- VARCHAR juga
    price               VARCHAR(50),  -- VARCHAR: bisa negatif / outlier
    freight_value       VARCHAR(50),
    INDEX idx_item_order (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ORDER_PAYMENTS
CREATE TABLE IF NOT EXISTS order_payments (
    payment_internal_id  BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id             VARCHAR(50) NOT NULL,
    payment_sequential   INT,
    payment_type         VARCHAR(50),
    payment_installments INT,
    payment_value        VARCHAR(50),  -- VARCHAR: bisa negatif
    INDEX idx_pay_order (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ORDER_REVIEWS
CREATE TABLE IF NOT EXISTS order_reviews (
    review_internal_id       BIGINT AUTO_INCREMENT PRIMARY KEY,
    review_id                VARCHAR(50),        -- format: REV-2024-NNNNN
    order_id                 VARCHAR(50) NOT NULL,
    review_score             INT,
    review_comment_title     VARCHAR(255),
    review_comment_message   TEXT,
    review_creation_date     VARCHAR(50),
    review_answer_timestamp  VARCHAR(50),
    INDEX idx_rev_order (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- GEOLOCATION
CREATE TABLE IF NOT EXISTS geolocation (
    geo_id             BIGINT AUTO_INCREMENT PRIMARY KEY,
    zip_code_prefix    VARCHAR(10),
    geolocation_lat    DECIMAL(15,10),
    geolocation_lng    DECIMAL(15,10),
    city               VARCHAR(100),
    state              VARCHAR(100),
    INDEX idx_geo_zip (zip_code_prefix)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- CATEGORY_TRANSLATION
CREATE TABLE IF NOT EXISTS category_translation (
    product_category_name         VARCHAR(100) PRIMARY KEY,
    product_category_name_english VARCHAR(100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
