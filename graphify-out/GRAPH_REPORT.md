# Graph Report - project-oltp-to-dwh  (2026-10-15)

## Corpus Check
- Corpus is ~22,509 words - fits in a single context window. You may not need a graph.

## Summary
- 202 nodes · 429 edges · 18 communities (9 shown, 9 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 6 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- DWH Schema & Unknown Records
- ETL Config & Extraction
- ETL Pipeline Orchestration
- Data Cleansing & Validation
- DWH Loading Pipeline
- Dirty Data Injection
- ETL Job Scheduler
- Analytics & KPI Queries
- Star Schema Architecture Design
- Cleansing Specs & Quarantine
- Business Insights & Metrics
- Data Quality Audits
- OLTP 3NF Schema Specs
- Project Scope & Automation
- System Arch & Dependencies
- Historical Quality Runs
- Devenv Nix Environment
- Payment Installments Analysis

## God Nodes (most connected - your core abstractions)
1. `run_pipeline()` - 24 edges
2. `get_dwh_engine()` - 15 edges
3. `clean_all_data()` - 11 edges
4. `extract_oltp_data()` - 11 edges
5. `record_rejections()` - 10 edges
6. `clean_bad_business_logic()` - 8 edges
7. `load_all_dimensions()` - 8 edges
8. `clean_null_handling()` - 7 edges
9. `clean_deduplication()` - 7 edges
10. `clean_domain_validation_and_shift()` - 7 edges

## Surprising Connections (you probably didn't know these)
- `execute_etl_job()` --calls--> `run_pipeline()`  [EXTRACTED]
  scheduler/run_scheduler.py → etl/run_etl.py
- `Dirty Data Injection Anomaly Scenarios` --conceptually_related_to--> `ETL Cleansing and Quarantine Requirements`  [INFERRED]
  reports/injection_summary.md → INSTRUCTION.md
- `ETL Cleansing Rejection Rules Breakdown` --implements--> `Data Cleansing Multi-Technique Matrix`  [INFERRED]
  reports/data_quality_report_latest.md → README.md
- `test_null_handling()` --calls--> `clean_null_handling()`  [EXTRACTED]
  tests/test_clean.py → etl/clean.py
- `test_deduplication_and_text_normalization()` --calls--> `clean_deduplication()`  [EXTRACTED]
  tests/test_clean.py → etl/clean.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Data Quality Cleansing and Validation Cycle** — instruction_cleansing_requirements, reports_injection_summary_injection_scenarios, reports_data_quality_report_latest_cleansing_audit, readme_data_cleansing_techniques [INFERRED 0.85]
- **Star Schema Architectural Design and Grain Modeling** — instruction_dwh_star_schema_spec, readme_dwh_star_schema_design, readme_grain_and_cartesian_solution [EXTRACTED 1.00]

## Communities (18 total, 9 thin omitted)

### Community 0 - "DWH Schema & Unknown Records"
Cohesion: 0.10
Nodes (9): execute_sql_file(), main(), setup_unknown_records(), main(), build_staging_from_raw_csvs(), load_staging_data(), main(), init_oltp_tables() (+1 more)

### Community 1 - "ETL Config & Extraction"
Cohesion: 0.08
Nodes (15): get_db_url(), get_dwh_engine(), get_oltp_engine(), extract_oltp_data(), get_last_watermark(), main(), update_watermark(), dwh_engine() (+7 more)

### Community 2 - "ETL Pipeline Orchestration"
Cohesion: 0.11
Nodes (12): load_rejected_rows(), generate_data_quality_report(), run_pipeline(), build_dim_customer(), build_dim_date(), build_dim_payment_type(), build_dim_product(), build_dim_seller() (+4 more)

### Community 3 - "Data Cleansing & Validation"
Cohesion: 0.17
Nodes (12): clean_all_data(), clean_bad_business_logic(), clean_deduplication(), clean_domain_validation_and_shift(), clean_null_handling(), main(), record_rejections(), run_query() (+4 more)

### Community 4 - "DWH Loading Pipeline"
Cohesion: 0.19
Nodes (5): load_all_dimensions(), load_facts_transactional(), log_etl_execution(), upsert_dim_customer_scd2(), upsert_dimension()

### Community 5 - "Dirty Data Injection"
Cohesion: 0.23
Nodes (4): generate_injection_summary(), get_dirty_records_to_inject(), inject_dirty_data(), save_injection_report()

### Community 9 - "Cleansing Specs & Quarantine"
Cohesion: 0.50
Nodes (4): ETL Cleansing and Quarantine Requirements, Data Cleansing Multi-Technique Matrix, ETL Cleansing Rejection Rules Breakdown, Dirty Data Injection Anomaly Scenarios

### Community 10 - "Business Insights & Metrics"
Cohesion: 0.67
Nodes (3): Business Insights and Analytical Findings, Analytics Query Output and Execution Results, Order Value Tier Delivery Delay Analysis

### Community 11 - "Data Quality Audits"
Cohesion: 0.67
Nodes (3): Latest ETL Data Quality Audit and Row Reconciliation, ETL Data Quality Audit Run 54ffa1, Controlled Dirty Data Injection Summary

## Knowledge Gaps
- **16 isolated node(s):** `Project Requirements and Specifications`, `OLTP 3NF Normalization Specification`, `OLTP to DWH End-to-End Pipeline Architecture`, `OLTP 3NF Database Design (oltp_olist)`, `Pipeline Scheduling and Automation Guide` (+11 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 93 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `run_pipeline()` connect `ETL Pipeline Orchestration` to `DWH Schema & Unknown Records`, `ETL Config & Extraction`, `Data Cleansing & Validation`, `DWH Loading Pipeline`, `ETL Job Scheduler`?**
  _High betweenness centrality (0.058) - this node is a cross-community bridge._
- **What connects `Project Requirements and Specifications`, `OLTP 3NF Normalization Specification`, `OLTP to DWH End-to-End Pipeline Architecture` to the rest of the system?**
  _16 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `DWH Schema & Unknown Records` be split into smaller, more focused modules?**
  _Cohesion score 0.1039136302294197 - nodes in this community are weakly interconnected._
- **Why does `get_dwh_engine()` connect `ETL Config & Extraction` to `ETL Pipeline Orchestration`, `DWH Loading Pipeline`, `Analytics & KPI Queries`?**
  _High betweenness centrality (0.040) - this node is a cross-community bridge._
- **Should `ETL Config & Extraction` be split into smaller, more focused modules?**
  _Cohesion score 0.07936507936507936 - nodes in this community are weakly interconnected._
- **Why does `extract_oltp_data()` connect `ETL Config & Extraction` to `ETL Pipeline Orchestration`, `Data Cleansing & Validation`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **Should `ETL Pipeline Orchestration` be split into smaller, more focused modules?**
  _Cohesion score 0.10756302521008404 - nodes in this community are weakly interconnected._