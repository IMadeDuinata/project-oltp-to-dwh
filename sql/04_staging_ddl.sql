-- ============================================================
-- SQL DDL: Staging Area Fisik Per Entitas (Database: dwh_staging)
-- Port: 3308 (Server DWH)
-- ============================================================

CREATE DATABASE IF NOT EXISTS dwh_staging DEFAULT CHARACTER SET utf8mb4;
USE dwh_staging;

-- 1. STAGING CUSTOMERS
CREATE TABLE IF NOT EXISTS stg_customers (
    _stg_id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    _source_country          VARCHAR(5) NOT NULL,
    _extracted_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
    customer_id              VARCHAR(100),
    customer_unique_id       VARCHAR(100),
    customer_zip_code_prefix VARCHAR(50),
    customer_city            VARCHAR(255),
    customer_state           VARCHAR(100),
    INDEX idx_stg_cust_id (customer_id),
    INDEX idx_stg_cust_src (_source_country)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. STAGING PRODUCTS
CREATE TABLE IF NOT EXISTS stg_products (
    _stg_id                        BIGINT AUTO_INCREMENT PRIMARY KEY,
    _source_country                VARCHAR(5) NOT NULL,
    _extracted_at                  DATETIME DEFAULT CURRENT_TIMESTAMP,
    product_id                     VARCHAR(100),
    product_category_name          VARCHAR(255),
    product_category_name_original VARCHAR(255),
    product_name_length            VARCHAR(50),
    product_description_length     VARCHAR(50),
    product_photos_qty             VARCHAR(50),
    product_weight_g               VARCHAR(50),
    product_length_cm              VARCHAR(50),
    product_height_cm              VARCHAR(50),
    product_width_cm               VARCHAR(50),
    INDEX idx_stg_prod_id (product_id),
    INDEX idx_stg_prod_src (_source_country)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. STAGING SELLERS
CREATE TABLE IF NOT EXISTS stg_sellers (
    _stg_id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    _source_country        VARCHAR(5) NOT NULL,
    _extracted_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    seller_id              VARCHAR(100),
    seller_zip_code_prefix VARCHAR(50),
    seller_city            VARCHAR(255),
    seller_state           VARCHAR(100),
    INDEX idx_stg_seller_id (seller_id),
    INDEX idx_stg_seller_src (_source_country)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. STAGING ORDERS
CREATE TABLE IF NOT EXISTS stg_orders (
    _stg_id                       BIGINT AUTO_INCREMENT PRIMARY KEY,
    _source_country               VARCHAR(5) NOT NULL,
    _extracted_at                 DATETIME DEFAULT CURRENT_TIMESTAMP,
    order_id                      VARCHAR(100),
    customer_id                   VARCHAR(100),
    order_status                  VARCHAR(100),
    order_purchase_timestamp      VARCHAR(100),
    order_approved_at             VARCHAR(100),
    order_delivered_carrier_date  VARCHAR(100),
    order_delivered_customer_date VARCHAR(100),
    order_estimated_delivery_date VARCHAR(100),
    INDEX idx_stg_ord_id (order_id),
    INDEX idx_stg_ord_cust (customer_id),
    INDEX idx_stg_ord_src (_source_country)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. STAGING ORDER ITEMS
CREATE TABLE IF NOT EXISTS stg_order_items (
    _stg_id             BIGINT AUTO_INCREMENT PRIMARY KEY,
    _source_country     VARCHAR(5) NOT NULL,
    _extracted_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    item_internal_id    VARCHAR(50),
    order_id            VARCHAR(100),
    order_item_id       VARCHAR(50),
    product_id          VARCHAR(100),
    seller_id           VARCHAR(100),
    shipping_limit_date VARCHAR(100),
    price               VARCHAR(100),
    freight_value       VARCHAR(100),
    INDEX idx_stg_item_order (order_id),
    INDEX idx_stg_item_prod (product_id),
    INDEX idx_stg_item_src (_source_country)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. STAGING ORDER PAYMENTS
CREATE TABLE IF NOT EXISTS stg_order_payments (
    _stg_id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    _source_country      VARCHAR(5) NOT NULL,
    _extracted_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    payment_internal_id  VARCHAR(50),
    order_id             VARCHAR(100),
    payment_sequential   VARCHAR(50),
    payment_type         VARCHAR(100),
    payment_installments VARCHAR(50),
    payment_value        VARCHAR(100),
    INDEX idx_stg_pay_order (order_id),
    INDEX idx_stg_pay_src (_source_country)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
