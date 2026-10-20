USE dwh_olist;
ALTER TABLE dim_customer DROP INDEX uk_customer_unique;
ALTER TABLE dim_customer ADD INDEX idx_dc_unique_id (customer_unique_id);
ALTER TABLE dim_customer MODIFY COLUMN customer_state VARCHAR(100);
ALTER TABLE dim_seller MODIFY COLUMN seller_state VARCHAR(100);
