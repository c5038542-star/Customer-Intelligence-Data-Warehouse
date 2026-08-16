"""
etl_pipeline.py
---------------
ETL (Extract, Transform, Load) pipeline for the Customer Intelligence Data
Warehouse (CIDW) prototype.

This script implements the three classic ETL stages described in the
literature (Kimball & Ross, 2013; Connolly & Begg, 2015):

    1. EXTRACT  - read the raw transactional export (CSV) representing data
                  pulled from a CRM / e-commerce platform.
    2. TRANSFORM - clean, validate, de-duplicate, derive new attributes
                   (e.g. line_total, customer segment, date keys) and shape
                   the data into the dimensional model.
    3. LOAD      - populate the staging table and the star-schema warehouse
                   tables (dim_date, dim_customer, dim_product, dim_country,
                   fact_sales).

SUPPORTED DATASETS
------------------
The pipeline runs against EITHER:

  (a) the real, publicly available UCI / Kaggle "Online Retail" dataset
      (Chen, 2015), e.g. the Kaggle mirror "E-Commerce Data"
      (https://www.kaggle.com/datasets/carrie1/ecommerce-data), which uses
      ISO-8859-1 encoding, US-style dates, float-formatted customer IDs
      (e.g. "17850.0"), service stock codes (POST, M, D, BANK CHARGES...),
      negative quantities without a 'C' invoice prefix, and negative
      "Adjust bad debt" prices; OR

  (b) the synthetic validation dataset (online_retail_synthetic.csv), which
      replicates the same schema with deliberately injected, *known*
      data-quality faults so that the cleansing logic can be verified
      against a ground truth.

The transformation logic below handles the quirks of both sources and
reports every action taken in the data-quality report (nothing is silent).

NOTE ON DATABASE CONNECTIVITY
------------------------------
The target production environment is MySQL 8.0 (see schema_warehouse.sql).
Run schema_warehouse.sql FIRST to create the constrained tables, then run
this pipeline with LOAD_MODE = "append" so that the primary keys, foreign
keys and indexes defined in the DDL remain in force. (Using pandas'
if_exists="replace" would silently drop and recreate the tables WITHOUT
constraints - an earlier iteration of this prototype did exactly that, and
the defect was caught and corrected during testing; see Chapter 6.)

To run against MySQL, install `mysql-connector-python` and set:

    DB_CONNECTION_STRING = "mysql+mysqlconnector://<user>:<password>@<host>:3306/cidw_dw"

SQLAlchemy is imported lazily inside load() so that etl_pipeline_demo.py
(which uses Python's built-in sqlite3 instead) genuinely has no external
database dependencies beyond pandas.

Author: Alexander Ugochukwu Ejiogu (Student No. 35038543)
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime
import logging

# -------------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------------
SOURCE_CSV = "../data/online_retail_synthetic.csv"   # or ../data/online_retail_kaggle.csv
DB_CONNECTION_STRING = "sqlite:///../data/cidw_dw.sqlite"
LOAD_MODE = "append"   # "append" preserves DDL constraints; run schema first

# Non-product stock codes present in the real UCI/Kaggle dataset
# (postage, manual adjustments, bank charges, etc.). These are retained in
# fact_sales (they are genuine financial events) but flagged, so that
# product-level analyses can exclude them.
SERVICE_STOCK_CODES = {
    "POST", "D", "M", "S", "C2", "DOT", "CRUK", "PADS",
    "BANK CHARGES", "AMAZONFEE", "ADJUST", "B", "m",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("CIDW_ETL")


# -------------------------------------------------------------------------
# 1. EXTRACT
# -------------------------------------------------------------------------
def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map known column-name variants (e.g. the 'Online Retail II' release
    uses Invoice/Price/Customer ID) onto the canonical schema."""
    rename_map = {
        "Invoice": "InvoiceNo",
        "Price": "UnitPrice",
        "Customer ID": "CustomerID",
    }
    return df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})


def extract(source_path: str) -> pd.DataFrame:
    """Read the raw CRM/e-commerce export into a DataFrame.

    The real Kaggle CSV is ISO-8859-1 encoded; the synthetic CSV is UTF-8.
    Both are handled transparently.
    """
    logger.info("EXTRACT: Reading source file %s", source_path)
    try:
        df = pd.read_csv(source_path, dtype={"CustomerID": "string", "Customer ID": "string"})
    except UnicodeDecodeError:
        logger.info("EXTRACT: UTF-8 decode failed; retrying with ISO-8859-1 (Kaggle encoding)")
        df = pd.read_csv(source_path, dtype={"CustomerID": "string", "Customer ID": "string"},
                         encoding="ISO-8859-1")
    df = _normalise_columns(df)
    logger.info("EXTRACT: %d rows, %d columns read", *df.shape)
    return df


# -------------------------------------------------------------------------
# 2. TRANSFORM
# -------------------------------------------------------------------------
def transform(df: pd.DataFrame) -> dict:
    """
    Clean and reshape the raw extract into dimension and fact DataFrames
    ready for loading into the star schema.

    Returns a dict of DataFrames: staging, dim_date, dim_customer,
    dim_product, dim_country, fact_sales, plus a data-quality report.
    """
    logger.info("TRANSFORM: Starting data cleansing")
    initial_rows = len(df)
    dq_report = {"initial_rows": initial_rows}

    # --- 2.1 Remove exact duplicate rows -------------------------------
    df = df.drop_duplicates()
    dq_report["duplicates_removed"] = initial_rows - len(df)

    # --- 2.2 Parse dates -------------------------------------------------
    # The synthetic dataset uses ISO timestamps; the real Kaggle dataset
    # uses US-style "12/1/2010 8:26" strings. format="mixed" handles both;
    # unparseable rows are dropped and counted.
    try:
        df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"], errors="coerce", format="mixed")
    except (TypeError, ValueError):
        # pandas < 2.0 fallback
        df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"], errors="coerce")
    unparseable = int(df["InvoiceDate"].isna().sum())
    dq_report["unparseable_dates_removed"] = unparseable
    df = df.dropna(subset=["InvoiceDate"])

    # --- 2.3 Handle missing / float-formatted CustomerID -----------------
    # Records without a CustomerID cannot be attributed to a customer for
    # CRM analysis; following common practice (Han, Kamber & Pei, 2012)
    # these are routed to a designated "Guest" customer rather than
    # discarded, preserving revenue totals while flagging the gap for the
    # data-quality report. The real dataset stores IDs as floats
    # ("17850.0"), which are normalised to plain integers strings here.
    df["CustomerID"] = (
        df["CustomerID"].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    )
    df.loc[df["CustomerID"].isin(["", "nan", "<NA>"]), "CustomerID"] = pd.NA
    missing_customers = df["CustomerID"].isna().sum()
    dq_report["missing_customer_ids"] = int(missing_customers)
    df["CustomerID"] = df["CustomerID"].fillna("GUEST")

    # --- 2.4 Handle zero / negative unit prices -------------------------
    # A zero price typically indicates a free promotional item or a data
    # entry error: retained but flagged (line_total = 0 does not distort
    # revenue). Negative prices occur only as accounting adjustments
    # ("Adjust bad debt") in the real dataset and are removed, as they are
    # not sales events at the declared grain of the fact table.
    negative_price_rows = int((df["UnitPrice"] < 0).sum())
    dq_report["negative_price_rows_removed"] = negative_price_rows
    df = df[df["UnitPrice"] >= 0]
    zero_price_rows = (df["UnitPrice"] == 0).sum()
    dq_report["zero_price_rows_flagged"] = int(zero_price_rows)

    # --- 2.5 Identify returns/cancellations -----------------------------
    # Invoices prefixed with 'C' represent cancellations in the source
    # system convention (Chen, 2015). The real dataset also contains
    # negative-quantity stock adjustments WITHOUT a 'C' prefix; both are
    # treated as returns/adjustments so that quantity-based measures on
    # sales remain non-negative.
    df["is_return"] = (
        df["InvoiceNo"].astype(str).str.startswith("C") | (df["Quantity"] < 0)
    )
    dq_report["return_or_adjustment_rows"] = int(df["is_return"].sum())

    # --- 2.6 Flag non-product (service) stock codes ----------------------
    df["is_service_code"] = df["StockCode"].astype(str).str.strip().isin(SERVICE_STOCK_CODES)
    dq_report["service_code_rows_flagged"] = int(df["is_service_code"].sum())

    # --- 2.7 Derive line_total -------------------------------------------
    df["line_total"] = df["Quantity"] * df["UnitPrice"]

    dq_report["final_rows"] = len(df)
    logger.info(
        "TRANSFORM: Cleansing complete. %d rows retained (removed %d duplicates, "
        "%d negative-price adjustments; reassigned %d missing customer IDs to "
        "'GUEST'; flagged %d zero-price and %d service-code rows)",
        dq_report["final_rows"], dq_report["duplicates_removed"],
        dq_report["negative_price_rows_removed"], dq_report["missing_customer_ids"],
        dq_report["zero_price_rows_flagged"], dq_report["service_code_rows_flagged"]
    )

    # ---------------------------------------------------------------
    # 2.8 Build dim_date
    # ---------------------------------------------------------------
    unique_dates = pd.Series(df["InvoiceDate"].dt.date.unique())
    dim_date = pd.DataFrame({"full_date": pd.to_datetime(unique_dates)})
    dim_date["date_key"] = dim_date["full_date"].dt.strftime("%Y%m%d").astype(int)
    dim_date["day_of_week"] = dim_date["full_date"].dt.day_name()
    dim_date["day_number"] = dim_date["full_date"].dt.day
    dim_date["month_number"] = dim_date["full_date"].dt.month
    dim_date["month_name"] = dim_date["full_date"].dt.month_name()
    dim_date["quarter"] = dim_date["full_date"].dt.quarter
    dim_date["year"] = dim_date["full_date"].dt.year
    dim_date["is_weekend"] = dim_date["full_date"].dt.dayofweek >= 5
    dim_date = dim_date.sort_values("date_key").reset_index(drop=True)
    dim_date["full_date"] = dim_date["full_date"].dt.date

    # ---------------------------------------------------------------
    # 2.9 Build dim_country
    # ---------------------------------------------------------------
    countries = sorted(df["Country"].dropna().unique())
    dim_country = pd.DataFrame({
        "country_key": range(1, len(countries) + 1),
        "country_name": countries
    })
    region_map = {
        "United Kingdom": "UK & Ireland", "EIRE": "UK & Ireland",
        "Channel Islands": "UK & Ireland",
    }
    dim_country["region"] = dim_country["country_name"].map(region_map).fillna("Europe / Other")

    # ---------------------------------------------------------------
    # 2.10 Build dim_product
    # ---------------------------------------------------------------
    products = (
        df.groupby("StockCode")
        .agg(description=("Description", "first"),
             avg_price=("UnitPrice", "mean"),
             is_service=("is_service_code", "max"))
        .reset_index()
    )
    products["description"] = products["description"].fillna("(no description)")

    def price_band(p):
        if p < 2:
            return "Low"
        elif p < 5:
            return "Medium"
        else:
            return "High"

    products["unit_price_band"] = products["avg_price"].apply(price_band)
    products.loc[products["is_service"] == True, "unit_price_band"] = "Service/Adjustment"
    products["product_key"] = range(1, len(products) + 1)
    dim_product = products[["product_key", "StockCode", "description", "unit_price_band"]]
    dim_product.columns = ["product_key", "stock_code", "description", "unit_price_band"]

    # ---------------------------------------------------------------
    # 2.11 Build dim_customer (with RFM-based segmentation)
    #
    # CORRECTED LOGIC (defect found during testing, see Chapter 6):
    # the dimension is built from ALL customers referenced anywhere in
    # the transaction data - including customers whose only activity is
    # a cancellation/return. An earlier iteration built the dimension
    # from non-return rows only, which produced fact rows (return lines)
    # with no matching customer_key - orphan rows that violated
    # referential integrity. Purchase-based RFM statistics are still
    # computed from non-return transactions; return-only customers are
    # assigned to an explicit 'Returns Only' segment.
    # ---------------------------------------------------------------
    all_customers = (
        df.groupby("CustomerID")
        .agg(country=("Country", "first"),
             first_seen=("InvoiceDate", "min"),
             last_seen=("InvoiceDate", "max"))
        .reset_index()
    )

    purchase_summary = (
        df[df["is_return"] == False]
        .groupby("CustomerID")
        .agg(
            first_purchase_date=("InvoiceDate", "min"),
            last_purchase_date=("InvoiceDate", "max"),
            total_orders=("InvoiceNo", "nunique"),
            total_spend=("line_total", "sum"),
        )
        .reset_index()
    )

    cust_summary = all_customers.merge(purchase_summary, on="CustomerID", how="left")
    cust_summary["total_orders"] = cust_summary["total_orders"].fillna(0).astype(int)
    cust_summary["total_spend"] = cust_summary["total_spend"].fillna(0.0)
    # For return-only customers, fall back to their return activity dates
    cust_summary["first_purchase_date"] = cust_summary["first_purchase_date"].fillna(
        cust_summary["first_seen"])
    cust_summary["last_purchase_date"] = cust_summary["last_purchase_date"].fillna(
        cust_summary["last_seen"])

    max_date = df["InvoiceDate"].max()
    cust_summary["recency_days"] = (max_date - cust_summary["last_purchase_date"]).dt.days

    def segment_customer(row):
        if row["CustomerID"] == "GUEST":
            return "Guest / Unidentified"
        if row["total_orders"] == 0:
            return "Returns Only"
        if row["recency_days"] <= 60 and row["total_orders"] >= 6:
            return "Champions"
        if row["recency_days"] <= 90 and row["total_orders"] >= 3:
            return "Loyal Customers"
        if row["recency_days"] > 150:
            return "At Risk / Hibernating"
        if row["total_orders"] <= 1:
            return "New Customers"
        return "Potential Loyalists"

    cust_summary["customer_segment"] = cust_summary.apply(segment_customer, axis=1)
    cust_summary["is_active"] = cust_summary["recency_days"] <= 90
    cust_summary["customer_key"] = range(1, len(cust_summary) + 1)

    dim_customer = cust_summary[[
        "customer_key", "CustomerID", "country", "customer_segment",
        "first_purchase_date", "last_purchase_date", "total_orders", "is_active"
    ]].copy()
    dim_customer.columns = [
        "customer_key", "customer_id", "country", "customer_segment",
        "first_purchase_date", "last_purchase_date", "total_orders", "is_active"
    ]
    dim_customer["first_purchase_date"] = dim_customer["first_purchase_date"].dt.date
    dim_customer["last_purchase_date"] = dim_customer["last_purchase_date"].dt.date

    # ---------------------------------------------------------------
    # 2.12 Build fact_sales (join surrogate keys)
    # ---------------------------------------------------------------
    df["date_key"] = df["InvoiceDate"].dt.strftime("%Y%m%d").astype(int)

    fact = df.merge(dim_customer[["customer_id", "customer_key"]],
                    left_on="CustomerID", right_on="customer_id", how="left")
    fact = fact.merge(dim_product[["stock_code", "product_key"]],
                      left_on="StockCode", right_on="stock_code", how="left")
    fact = fact.merge(dim_country[["country_name", "country_key"]],
                      left_on="Country", right_on="country_name", how="left")

    fact_sales = fact[[
        "InvoiceNo", "date_key", "customer_key", "product_key", "country_key",
        "Quantity", "UnitPrice", "line_total", "is_return"
    ]].copy()
    fact_sales.columns = [
        "invoice_no", "date_key", "customer_key", "product_key", "country_key",
        "quantity", "unit_price", "line_total", "is_return"
    ]
    fact_sales.insert(0, "sales_key", range(1, len(fact_sales) + 1))

    # --- 2.13 In-pipeline referential integrity assertion ----------------
    # Fail fast (rather than loading silently) if any fact row lacks a
    # dimension key. With the corrected dim_customer logic above this
    # should always be zero.
    orphan_counts = {
        "customer_key": int(fact_sales["customer_key"].isna().sum()),
        "product_key": int(fact_sales["product_key"].isna().sum()),
        "country_key": int(fact_sales["country_key"].isna().sum()),
    }
    dq_report["orphan_fact_rows"] = orphan_counts
    if any(v > 0 for v in orphan_counts.values()):
        raise ValueError(f"Referential integrity violated before load: {orphan_counts}")
    for col in ("customer_key", "product_key", "country_key"):
        fact_sales[col] = fact_sales[col].astype(int)

    # Staging copy: the raw (post-parse) extract, mirroring stg_online_retail
    staging = df[["InvoiceNo", "StockCode", "Description", "Quantity",
                  "InvoiceDate", "UnitPrice", "CustomerID", "Country"]].copy()
    staging.columns = ["invoice_no", "stock_code", "description", "quantity",
                       "invoice_date", "unit_price", "customer_id", "country"]

    logger.info(
        "TRANSFORM: Dimensional model built - dim_date(%d), dim_customer(%d), "
        "dim_product(%d), dim_country(%d), fact_sales(%d); orphan fact rows: 0",
        len(dim_date), len(dim_customer), len(dim_product), len(dim_country), len(fact_sales)
    )

    return {
        "staging": staging,
        "dim_date": dim_date,
        "dim_customer": dim_customer,
        "dim_product": dim_product,
        "dim_country": dim_country,
        "fact_sales": fact_sales,
        "dq_report": dq_report,
    }


# -------------------------------------------------------------------------
# 3. LOAD
# -------------------------------------------------------------------------
def load(tables: dict, connection_string: str = DB_CONNECTION_STRING,
         mode: str = LOAD_MODE):
    """Load the transformed DataFrames into the target database.

    mode="append" (default) assumes schema_warehouse.sql has been executed
    first, so that the DDL-defined primary keys, foreign keys and indexes
    remain in force. Existing rows are cleared with DELETE so the load is
    re-runnable. mode="replace" is retained only for ad-hoc exploration and
    is NOT recommended, as pandas recreates the tables without constraints.
    """
    # Lazy import: only the MySQL/SQLAlchemy path needs this dependency.
    from sqlalchemy import create_engine, text

    logger.info("LOAD: Connecting to %s (mode=%s)", connection_string, mode)
    engine = create_engine(connection_string)

    load_order = ["staging", "dim_date", "dim_customer", "dim_product",
                  "dim_country", "fact_sales"]
    table_names = {"staging": "stg_online_retail"}

    with engine.begin() as conn:
        if mode == "append":
            # Clear in reverse dependency order so FKs are not violated.
            for key in reversed(load_order):
                name = table_names.get(key, key)
                try:
                    conn.execute(text(f"DELETE FROM {name}"))
                except Exception:
                    logger.warning("LOAD: table %s not found - run "
                                   "schema_warehouse.sql first", name)

    for key in load_order:
        name = table_names.get(key, key)
        df = tables[key]
        df.to_sql(name, engine, if_exists=(mode if mode == "replace" else "append"),
                  index=False)
        logger.info("LOAD: %s -> %d rows written", name, len(df))

    logger.info("LOAD: Complete.")
    return engine


# -------------------------------------------------------------------------
# Main pipeline
# -------------------------------------------------------------------------
def run_pipeline(source_path: str = SOURCE_CSV,
                 connection_string: str = DB_CONNECTION_STRING):
    start = datetime.now()
    logger.info("===== CIDW ETL PIPELINE START =====")

    raw = extract(source_path)
    tables = transform(raw)
    engine = load(tables, connection_string)

    duration = (datetime.now() - start).total_seconds()
    logger.info("===== CIDW ETL PIPELINE COMPLETE in %.2f seconds =====", duration)

    return engine, tables


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else SOURCE_CSV
    run_pipeline(source_path=src)
