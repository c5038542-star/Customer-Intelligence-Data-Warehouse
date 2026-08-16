-- =============================================================================
-- schema_warehouse.sql
-- Star-schema Data Warehouse DDL for the Customer Intelligence Data Warehouse
-- (CIDW) prototype.
--
-- Target RDBMS : MySQL 8.0+
-- Author       : Alexander Ugochukwu Ejiogu (Student No. 35038543)
--
-- This script creates:
--   1. A staging schema (cidw_staging) that mirrors the raw source extract.
--   2. A presentation/warehouse schema (cidw_dw) implementing a star schema
--      with one fact table (fact_sales) and four dimension tables
--      (dim_customer, dim_product, dim_date, dim_country).
--
-- The design follows Kimball's dimensional modelling approach (Kimball &
-- Ross, 2013), in which a central fact table records measurable business
-- events (sales transactions) and is surrounded by denormalised dimension
-- tables that provide descriptive context for analysis.
-- =============================================================================

-- -----------------------------------------------------------------------
-- 1. STAGING SCHEMA
-- -----------------------------------------------------------------------
DROP DATABASE IF EXISTS cidw_staging;
CREATE DATABASE cidw_staging CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE cidw_staging;

-- Raw extract table: structure mirrors the source CRM/e-commerce export.
-- No constraints are enforced here deliberately, as staging tables should
-- accept data "as is" to allow downstream data-quality profiling.
CREATE TABLE stg_online_retail (
    invoice_no      VARCHAR(20),
    stock_code      VARCHAR(20),
    description     VARCHAR(255),
    quantity        INT,
    invoice_date    DATETIME,
    unit_price      DECIMAL(10,2),
    customer_id     VARCHAR(20),
    country         VARCHAR(100),
    load_timestamp  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_stg_invoice ON stg_online_retail (invoice_no);
CREATE INDEX idx_stg_customer ON stg_online_retail (customer_id);


-- -----------------------------------------------------------------------
-- 2. PRESENTATION / WAREHOUSE SCHEMA (STAR SCHEMA)
-- -----------------------------------------------------------------------
DROP DATABASE IF EXISTS cidw_dw;
CREATE DATABASE cidw_dw CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE cidw_dw;

-- ---------------------------------------------------------------
-- 2.1 Dimension: Date
-- A conformed date dimension allows time-based slicing (day, month,
-- quarter, year) without recomputing date parts in BI tools.
-- ---------------------------------------------------------------
CREATE TABLE dim_date (
    date_key        INT PRIMARY KEY,        -- format YYYYMMDD
    full_date       DATE NOT NULL,
    day_of_week     VARCHAR(10) NOT NULL,
    day_number      TINYINT NOT NULL,
    month_number    TINYINT NOT NULL,
    month_name      VARCHAR(10) NOT NULL,
    quarter         TINYINT NOT NULL,
    year            SMALLINT NOT NULL,
    is_weekend      BOOLEAN NOT NULL
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- 2.2 Dimension: Customer
-- Slowly Changing Dimension Type 1 (overwrite on change) is used,
-- which is appropriate for this prototype as customer attributes
-- (segment, country) are refreshed in full on each load (Kimball &
-- Ross, 2013).
-- ---------------------------------------------------------------
CREATE TABLE dim_customer (
    customer_key    INT AUTO_INCREMENT PRIMARY KEY,
    customer_id     VARCHAR(20) NOT NULL UNIQUE,
    country         VARCHAR(100),
    customer_segment VARCHAR(50) DEFAULT 'Unclassified',
    first_purchase_date DATE,
    last_purchase_date  DATE,
    total_orders    INT DEFAULT 0,
    is_active       BOOLEAN DEFAULT TRUE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- 2.3 Dimension: Product
-- ---------------------------------------------------------------
CREATE TABLE dim_product (
    product_key     INT AUTO_INCREMENT PRIMARY KEY,
    stock_code      VARCHAR(20) NOT NULL UNIQUE,
    description     VARCHAR(255),
    unit_price_band VARCHAR(20)   -- e.g. 'Low', 'Medium', 'High'
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- 2.4 Dimension: Country (supports geo-level BI aggregation
-- independent of the customer dimension)
-- ---------------------------------------------------------------
CREATE TABLE dim_country (
    country_key     INT AUTO_INCREMENT PRIMARY KEY,
    country_name    VARCHAR(100) NOT NULL UNIQUE,
    region          VARCHAR(50)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- 2.5 Fact: Sales
-- Grain: one row per product line on a sales invoice (the lowest
-- level of detail available in the source data), in line with
-- Kimball's recommendation to model facts at the most atomic grain
-- possible (Kimball & Ross, 2013).
-- ---------------------------------------------------------------
CREATE TABLE fact_sales (
    sales_key       BIGINT AUTO_INCREMENT PRIMARY KEY,
    invoice_no      VARCHAR(20) NOT NULL,
    date_key        INT NOT NULL,
    customer_key    INT NOT NULL,
    product_key     INT NOT NULL,
    country_key     INT NOT NULL,
    quantity        INT NOT NULL,
    unit_price      DECIMAL(10,2) NOT NULL,
    line_total      DECIMAL(12,2) NOT NULL,
    is_return       BOOLEAN DEFAULT FALSE,
    CONSTRAINT fk_fact_date     FOREIGN KEY (date_key)     REFERENCES dim_date(date_key),
    CONSTRAINT fk_fact_customer FOREIGN KEY (customer_key) REFERENCES dim_customer(customer_key),
    CONSTRAINT fk_fact_product  FOREIGN KEY (product_key)  REFERENCES dim_product(product_key),
    CONSTRAINT fk_fact_country  FOREIGN KEY (country_key)  REFERENCES dim_country(country_key)
) ENGINE=InnoDB;

CREATE INDEX idx_fact_date     ON fact_sales (date_key);
CREATE INDEX idx_fact_customer ON fact_sales (customer_key);
CREATE INDEX idx_fact_product  ON fact_sales (product_key);
CREATE INDEX idx_fact_country  ON fact_sales (country_key);
CREATE INDEX idx_fact_invoice  ON fact_sales (invoice_no);

-- -----------------------------------------------------------------------
-- 3. ANALYTICAL VIEWS
-- Pre-aggregated views simplify Power BI / Tableau data-source connections
-- and demonstrate the "semantic layer" concept discussed in the literature
-- review (Turban et al., 2020).
-- -----------------------------------------------------------------------

-- 3.1 Monthly revenue and order volume by country
CREATE OR REPLACE VIEW vw_monthly_sales_by_country AS
SELECT
    d.year,
    d.month_number,
    d.month_name,
    c.country_name,
    COUNT(DISTINCT f.invoice_no)              AS total_orders,
    SUM(f.line_total)                          AS total_revenue,
    SUM(f.quantity)                            AS total_units
FROM fact_sales f
JOIN dim_date d     ON f.date_key = d.date_key
JOIN dim_country c  ON f.country_key = c.country_key
WHERE f.is_return = FALSE
GROUP BY d.year, d.month_number, d.month_name, c.country_name;

-- 3.2 Customer RFM (Recency, Frequency, Monetary) base view, used to
-- support the customer segmentation discussed in Chapter 5.
CREATE OR REPLACE VIEW vw_customer_rfm AS
SELECT
    dc.customer_key,
    dc.customer_id,
    dc.country,
    dc.customer_segment,
    DATEDIFF((SELECT MAX(full_date) FROM dim_date), MAX(dd.full_date)) AS recency_days,
    COUNT(DISTINCT f.invoice_no)  AS frequency,
    SUM(f.line_total)             AS monetary_value
FROM fact_sales f
JOIN dim_customer dc ON f.customer_key = dc.customer_key
JOIN dim_date dd     ON f.date_key = dd.date_key
WHERE f.is_return = FALSE
GROUP BY dc.customer_key, dc.customer_id, dc.country, dc.customer_segment;

-- 3.3 Top products by revenue
CREATE OR REPLACE VIEW vw_top_products AS
SELECT
    p.stock_code,
    p.description,
    SUM(f.quantity)    AS total_units_sold,
    SUM(f.line_total)  AS total_revenue
FROM fact_sales f
JOIN dim_product p ON f.product_key = p.product_key
WHERE f.is_return = FALSE
GROUP BY p.stock_code, p.description
ORDER BY total_revenue DESC;
