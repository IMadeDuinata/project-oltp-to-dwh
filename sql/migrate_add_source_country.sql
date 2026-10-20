-- ============================================================
-- SQL Migration: Menambahkan kolom source_country ke tabel fakta
-- Digunakan untuk menandai asal data ('BR' atau 'ID')
-- ============================================================

USE dwh_olist;

ALTER TABLE fact_order_items ADD COLUMN source_country VARCHAR(5) NOT NULL DEFAULT 'BR';
ALTER TABLE fact_order_delivery ADD COLUMN source_country VARCHAR(5) NOT NULL DEFAULT 'BR';
ALTER TABLE fact_order_payments ADD COLUMN source_country VARCHAR(5) NOT NULL DEFAULT 'BR';
