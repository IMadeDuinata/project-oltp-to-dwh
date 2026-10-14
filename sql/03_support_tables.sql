-- ============================================================
-- SQL DDL: Support Tables (ETL Log, Rejected Rows, Watermark)
-- ============================================================

USE dwh_olist;

-- 1. ETL Execution Audit Log
CREATE TABLE IF NOT EXISTS etl_log (
    log_id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id          VARCHAR(64) NOT NULL,
    pipeline_name   VARCHAR(100) NOT NULL,
    start_time      DATETIME NOT NULL,
    end_time        DATETIME,
    status          VARCHAR(20) NOT NULL, -- 'RUNNING', 'SUCCESS', 'FAILED'
    rows_in         INT DEFAULT 0,
    rows_clean      INT DEFAULT 0,
    rows_rejected   INT DEFAULT 0,
    rows_loaded     INT DEFAULT 0,
    error_message   TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_log_run_id (run_id),
    INDEX idx_log_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. Rejected Rows (Quarantine Table)
-- Baris yang ditolak TIDAK didrop diam-diam, melainkan disimpan ke tabel ini
CREATE TABLE IF NOT EXISTS rejected_rows (
    rejection_id      BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id            VARCHAR(64) NOT NULL,
    table_source      VARCHAR(100) NOT NULL,
    column_name       VARCHAR(100),
    rejection_reason  VARCHAR(255) NOT NULL,
    raw_record_json   JSON NOT NULL,
    rejected_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_rej_run_id (run_id),
    INDEX idx_rej_table (table_source),
    INDEX idx_rej_reason (rejection_reason)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. Watermark Table for Incremental Loads
CREATE TABLE IF NOT EXISTS etl_watermark (
    pipeline_name        VARCHAR(100) PRIMARY KEY,
    watermark_column     VARCHAR(100) NOT NULL,
    last_watermark_value VARCHAR(100) NOT NULL,
    updated_at           DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
