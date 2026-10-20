-- ============================================================
-- SQL DDL: OLTP Database (oltp_olist)
-- ============================================================

CREATE DATABASE IF NOT EXISTS oltp_olist;
USE oltp_olist;

-- 1. STAGING TABLE (olist_raw)
-- Menampung flat data / CSV apa adanya sebelum dipecah ke 3NF
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
    order_purchase_timestamp       VARCHAR(50),
    order_approved_at              VARCHAR(50),
    order_delivered_carrier_date   VARCHAR(50),
    order_delivered_customer_date  VARCHAR(50),
    order_estimated_delivery_date  VARCHAR(50),
    product_category_name          VARCHAR(100),
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

-- 2. TABEL-TABEL 3NF NORMALIZED OLTP
-- Catatan: Constraints dilonggarkan agar data kotor tetap bisa masuk ke OLTP
-- karena proses pembersihan adalah tanggung jawab pipeline ETL.

CREATE TABLE IF NOT EXISTS customers (
    customer_id              VARCHAR(50) PRIMARY KEY,
    customer_unique_id       VARCHAR(50) NOT NULL,
    customer_zip_code_prefix VARCHAR(10),
    customer_city            VARCHAR(100),
    customer_state           VARCHAR(10),
    INDEX idx_cust_unique (customer_unique_id),
    INDEX idx_cust_state (customer_state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS products (
    product_id                 VARCHAR(50) PRIMARY KEY,
    product_category_name      VARCHAR(100),
    product_name_length        INT,
    product_description_length INT,
    product_photos_qty         INT,
    product_weight_g           DECIMAL(10,2),
    product_length_cm          DECIMAL(10,2),
    product_height_cm          DECIMAL(10,2),
    product_width_cm           DECIMAL(10,2),
    INDEX idx_prod_cat (product_category_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sellers (
    seller_id              VARCHAR(50) PRIMARY KEY,
    seller_zip_code_prefix VARCHAR(10),
    seller_city            VARCHAR(100),
    seller_state           VARCHAR(10),
    INDEX idx_seller_state (seller_state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS orders (
    order_id                      VARCHAR(50) PRIMARY KEY,
    customer_id                   VARCHAR(50) NOT NULL,
    order_status                  VARCHAR(50),
    order_purchase_timestamp      DATETIME,
    order_approved_at             DATETIME,
    order_delivered_carrier_date  DATETIME,
    order_delivered_customer_date DATETIME,
    order_estimated_delivery_date DATETIME,
    INDEX idx_ord_cust (customer_id),
    INDEX idx_ord_status (order_status),
    INDEX idx_ord_purchase (order_purchase_timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS order_items (
    item_internal_id    BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id            VARCHAR(50) NOT NULL,
    order_item_id       INT NOT NULL,
    product_id          VARCHAR(50),
    seller_id           VARCHAR(50),
    shipping_limit_date DATETIME,
    price               DECIMAL(10,2),
    freight_value       DECIMAL(10,2),
    INDEX idx_item_order (order_id),
    INDEX idx_item_prod (product_id),
    INDEX idx_item_seller (seller_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS order_payments (
    payment_internal_id  BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id             VARCHAR(50) NOT NULL,
    payment_sequential   INT NOT NULL,
    payment_type         VARCHAR(50),
    payment_installments INT,
    payment_value        DECIMAL(10,2),
    INDEX idx_pay_order (order_id),
    INDEX idx_pay_type (payment_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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
