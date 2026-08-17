"""
etl_pipeline_demo.py
---------------------
Execution variant of etl_pipeline.py using Python's built-in sqlite3 module
so that the pipeline can be demonstrated and its outputs verified in any
Python environment with only pandas installed (SQLAlchemy is NOT required:
etl_pipeline.py imports it lazily inside load(), which this script does not
call).

Unlike a bare pandas to_sql() load, this demo:

  1. Creates the star schema with real PRIMARY KEY, FOREIGN KEY and INDEX
     constraints (a faithful SQLite translation of schema_warehouse.sql),
     with PRAGMA foreign_keys = ON so violations fail loudly;
  2. Loads staging, dimensions and the fact table in dependency order;
  3. Runs post-load referential-integrity checks (orphan-row queries);
  4. Benchmarks three representative analytical queries and prints the
     measured execution times (the evidence base for Section 6.5 of the
     dissertation).

Usage:
    python etl_pipeline_demo.py                          # synthetic dataset
    python etl_pipeline_demo.py ../data/online_retail_kaggle.csv   # real data

The transformation logic is identical to etl_pipeline.py (the documented
production version targeting MySQL); only the load target differs.
"""

import pandas as pd
import sqlite3
import sys
import time
sys.path.insert(0, ".")
from etl_pipeline import extract, transform, SOURCE_CSV, logger

DB_PATH = "../data/cidw_dw.sqlite"

# SQLite translation of schema_warehouse.sql (single-file database, so the
# staging table lives alongside the warehouse tables rather than in a
# separate cidw_staging database).
SQLITE_DDL = """
DROP TABLE IF EXISTS fact_sales;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_customer;
DROP TABLE IF EXISTS dim_product;
DROP TABLE IF EXISTS dim_country;
DROP TABLE IF EXISTS stg_online_retail;

CREATE TABLE stg_online_retail (
    invoice_no    TEXT,
    stock_code    TEXT,
    description   TEXT,
    quantity      INTEGER,
    invoice_date  TIMESTAMP,
    unit_price    REAL,
    customer_id   TEXT,
    country       TEXT
);

CREATE TABLE dim_date (
    date_key      INTEGER PRIMARY KEY,
    full_date     DATE NOT NULL,
    day_of_week   TEXT NOT NULL,
    day_number    INTEGER NOT NULL,
    month_number  INTEGER NOT NULL,
    month_name    TEXT NOT NULL,
    quarter       INTEGER NOT NULL,
    year          INTEGER NOT NULL,
    is_weekend    BOOLEAN NOT NULL
);

CREATE TABLE dim_customer (
    customer_key        INTEGER PRIMARY KEY,
    customer_id         TEXT NOT NULL UNIQUE,
    country             TEXT,
    customer_segment    TEXT DEFAULT 'Unclassified',
    first_purchase_date DATE,
    last_purchase_date  DATE,
    total_orders        INTEGER DEFAULT 0,
    is_active           BOOLEAN DEFAULT 1
);

CREATE TABLE dim_product (
    product_key     INTEGER PRIMARY KEY,
    stock_code      TEXT NOT NULL UNIQUE,
    description     TEXT,
    unit_price_band TEXT
);

CREATE TABLE dim_country (
    country_key   INTEGER PRIMARY KEY,
    country_name  TEXT NOT NULL UNIQUE,
    region        TEXT
);

CREATE TABLE fact_sales (
    sales_key    INTEGER PRIMARY KEY,
    invoice_no   TEXT NOT NULL,
    date_key     INTEGER NOT NULL REFERENCES dim_date(date_key),
    customer_key INTEGER NOT NULL REFERENCES dim_customer(customer_key),
    product_key  INTEGER NOT NULL REFERENCES dim_product(product_key),
    country_key  INTEGER NOT NULL REFERENCES dim_country(country_key),
    quantity     INTEGER NOT NULL,
    unit_price   REAL NOT NULL,
    line_total   REAL NOT NULL,
    is_return    BOOLEAN DEFAULT 0
);

CREATE INDEX idx_fact_date     ON fact_sales (date_key);
CREATE INDEX idx_fact_customer ON fact_sales (customer_key);
CREATE INDEX idx_fact_product  ON fact_sales (product_key);
CREATE INDEX idx_fact_country  ON fact_sales (country_key);
CREATE INDEX idx_fact_invoice  ON fact_sales (invoice_no);
"""


def load_sqlite(tables: dict, db_path: str = DB_PATH) -> sqlite3.Connection:
    logger.info("LOAD: Connecting to sqlite database %s", db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(SQLITE_DDL)

    load_order = [("stg_online_retail", "staging"), ("dim_date", "dim_date"),
                  ("dim_customer", "dim_customer"), ("dim_product", "dim_product"),
                  ("dim_country", "dim_country"), ("fact_sales", "fact_sales")]
    for table_name, key in load_order:
        df = tables[key]
        df.to_sql(table_name, conn, if_exists="append", index=False)
        logger.info("LOAD: %s -> %d rows written", table_name, len(df))

    conn.commit()
    logger.info("LOAD: Complete.")
    return conn


def run_integrity_checks(conn: sqlite3.Connection) -> None:
    """Post-load referential-integrity verification (test T7)."""
    print("\n--- Referential Integrity Checks (T7) ---")
    checks = {
        "orphan customer keys": """SELECT COUNT(*) FROM fact_sales f
            LEFT JOIN dim_customer d ON f.customer_key = d.customer_key
            WHERE d.customer_key IS NULL""",
        "orphan product keys": """SELECT COUNT(*) FROM fact_sales f
            LEFT JOIN dim_product d ON f.product_key = d.product_key
            WHERE d.product_key IS NULL""",
        "orphan date keys": """SELECT COUNT(*) FROM fact_sales f
            LEFT JOIN dim_date d ON f.date_key = d.date_key
            WHERE d.date_key IS NULL""",
        "orphan country keys": """SELECT COUNT(*) FROM fact_sales f
            LEFT JOIN dim_country d ON f.country_key = d.country_key
            WHERE d.country_key IS NULL""",
    }
    all_ok = True
    for label, sql in checks.items():
        n = conn.execute(sql).fetchone()[0]
        status = "PASS" if n == 0 else "FAIL"
        all_ok &= (n == 0)
        print(f"{label}: {n}  [{status}]")
    fk_violations = conn.execute("PRAGMA foreign_key_check;").fetchall()
    print(f"PRAGMA foreign_key_check violations: {len(fk_violations)}  "
          f"[{'PASS' if not fk_violations else 'FAIL'}]")
    if not all_ok or fk_violations:
        raise SystemExit("Referential integrity check FAILED - see above.")


def run_benchmarks(conn: sqlite3.Connection) -> None:
    """Measured evidence for the query-performance claims in Section 6.5."""
    print("\n--- Analytical Query Benchmarks (Section 6.5) ---")
    benchmarks = {
        "Monthly revenue aggregation": """
            SELECT d.year, d.month_number, SUM(f.line_total)
            FROM fact_sales f JOIN dim_date d ON f.date_key = d.date_key
            WHERE f.is_return = 0
            GROUP BY d.year, d.month_number""",
        "Customer RFM aggregation": """
            SELECT dc.customer_id, COUNT(DISTINCT f.invoice_no),
                   SUM(f.line_total), MAX(dd.full_date)
            FROM fact_sales f
            JOIN dim_customer dc ON f.customer_key = dc.customer_key
            JOIN dim_date dd ON f.date_key = dd.date_key
            WHERE f.is_return = 0
            GROUP BY dc.customer_id""",
        "Product revenue ranking": """
            SELECT p.description, SUM(f.line_total) AS rev
            FROM fact_sales f
            JOIN dim_product p ON f.product_key = p.product_key
            WHERE f.is_return = 0
            GROUP BY p.description ORDER BY rev DESC LIMIT 10""",
    }
    for label, sql in benchmarks.items():
        timings = []
        for _ in range(5):
            t0 = time.perf_counter()
            conn.execute(sql).fetchall()
            timings.append(time.perf_counter() - t0)
        print(f"{label}: mean {sum(timings)/len(timings)*1000:.1f} ms "
              f"over 5 runs (min {min(timings)*1000:.1f} ms, "
              f"max {max(timings)*1000:.1f} ms)")


if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else SOURCE_CSV
    raw = extract(source)
    tables = transform(raw)
    conn = load_sqlite(tables)

    print("\n--- Data Quality Report ---")
    for k, v in tables["dq_report"].items():
        print(f"{k}: {v}")

    run_integrity_checks(conn)
    run_benchmarks(conn)

    print("\n--- Sample query: vw_monthly_sales_by_country equivalent ---")
    q = """
    SELECT d.year, d.month_name, c.country_name,
           COUNT(DISTINCT f.invoice_no) AS total_orders,
           ROUND(SUM(f.line_total), 2) AS total_revenue
    FROM fact_sales f
    JOIN dim_date d ON f.date_key = d.date_key
    JOIN dim_country c ON f.country_key = c.country_key
    WHERE f.is_return = 0
    GROUP BY d.year, d.month_name, c.country_name
    ORDER BY total_revenue DESC
    LIMIT 10
    """
    print(pd.read_sql(q, conn))
    conn.close()
