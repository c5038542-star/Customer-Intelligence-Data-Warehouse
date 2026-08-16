"""
generate_dataset.py
--------------------
Generates a synthetic transactional dataset modelled on the structure of the
publicly available UCI/Kaggle 'Online Retail' dataset
(Chen, 2015 - https://archive.ics.uci.edu/ml/datasets/online+retail).

The synthetic dataset preserves the same schema (InvoiceNo, StockCode,
Description, Quantity, InvoiceDate, UnitPrice, CustomerID, Country) and
realistic statistical properties (seasonality, repeat customers, returns,
multiple countries) so that it can be used to populate the staging area of
the data warehouse prototype without relying on an external network
connection. It is intended purely for demonstration of the ETL pipeline,
star-schema loading and BI dashboard developed for this dissertation.

Author: Generated for dissertation prototype (Alexander Ugochukwu Ejiogu)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random

random.seed(42)
np.random.seed(42)

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------
COUNTRIES = [
    "United Kingdom", "Germany", "France", "EIRE", "Spain", "Netherlands",
    "Belgium", "Switzerland", "Portugal", "Australia", "Norway", "Italy",
    "Channel Islands", "Finland", "Sweden", "Austria", "Denmark", "Cyprus"
]
COUNTRY_WEIGHTS = np.array([0.40, 0.10, 0.09, 0.06, 0.05, 0.05, 0.04, 0.03, 0.03,
                             0.025, 0.02, 0.02, 0.02, 0.015, 0.015, 0.01, 0.01, 0.01])
COUNTRY_WEIGHTS = COUNTRY_WEIGHTS / COUNTRY_WEIGHTS.sum()

PRODUCTS = [
    ("85123A", "WHITE HANGING HEART T-LIGHT HOLDER", 2.55),
    ("71053", "WHITE METAL LANTERN", 3.39),
    ("84406B", "CREAM CUPID HEARTS COAT HANGER", 2.75),
    ("84029G", "KNITTED UNION FLAG HOT WATER BOTTLE", 3.39),
    ("84029E", "RED WOOLLY HOTTIE WHITE HEART", 3.39),
    ("22752", "SET 7 BABUSHKA NESTING BOXES", 7.65),
    ("21730", "GLASS STAR FROSTED T-LIGHT HOLDER", 4.25),
    ("22633", "HAND WARMER UNION JACK", 1.85),
    ("22632", "HAND WARMER RED POLKA DOT", 1.85),
    ("84879", "ASSORTED COLOUR BIRD ORNAMENT", 1.69),
    ("21212", "PACK OF 72 RETROSPOT CAKE CASES", 0.55),
    ("22745", "POPPY'S PLAYHOUSE BEDROOM", 2.10),
    ("22748", "POPPY'S PLAYHOUSE KITCHEN", 2.10),
    ("22749", "FELTCRAFT PRINCESS CHARLOTTE DOLL", 3.75),
    ("22622", "BOX OF VINTAGE ALPHABET BLOCKS", 9.95),
    ("23203", "JUMBO BAG VINTAGE DOILY", 4.13),
    ("23298", "SPACEBOY LUNCH BOX", 1.95),
    ("21929", "JUMBO BAG PINK VINTAGE PAISLEY", 2.08),
    ("22910", "PAPER CHAIN KIT VINTAGE CHRISTMAS", 2.95),
    ("84978", "HANGING HEART JAR T-LIGHT HOLDER", 1.45),
    ("20725", "LUNCH BAG RED RETROSPOT", 1.65),
    ("20727", "LUNCH BAG BLACK SKULL", 1.65),
    ("47566", "PARTY BUNTING", 4.95),
    ("23355", "HOT WATER BOTTLE KEEP CALM", 4.95),
    ("21034", "REX CASH+CARRY JUMBO SHOPPER", 1.25),
]

CUSTOMER_SEGMENTS = {
    "Champions": dict(n=120, freq=(8, 20), recency_days=(0, 30), aov=(40, 120)),
    "Loyal": dict(n=300, freq=(4, 10), recency_days=(0, 60), aov=(25, 70)),
    "Potential Loyalists": dict(n=450, freq=(2, 5), recency_days=(0, 90), aov=(15, 45)),
    "At Risk": dict(n=350, freq=(2, 6), recency_days=(120, 250), aov=(15, 60)),
    "Hibernating": dict(n=400, freq=(1, 3), recency_days=(180, 365), aov=(10, 40)),
    "New Customers": dict(n=280, freq=(1, 2), recency_days=(0, 30), aov=(10, 50)),
}

N_CUSTOMERS = sum(v["n"] for v in CUSTOMER_SEGMENTS.values())
START_DATE = datetime(2022, 1, 1)
END_DATE = datetime(2023, 12, 31)
TOTAL_DAYS = (END_DATE - START_DATE).days


def seasonal_weight(date):
    """Apply a seasonal multiplier - higher sales in Nov/Dec (pre-Christmas)
    and a smaller bump in spring."""
    month = date.month
    if month in (11, 12):
        return 1.8
    if month in (3, 4):
        return 1.2
    if month in (1,):
        return 0.7
    return 1.0


def generate_customers():
    customers = []
    cust_id = 12346
    for segment, params in CUSTOMER_SEGMENTS.items():
        for _ in range(params["n"]):
            country = np.random.choice(COUNTRIES, p=COUNTRY_WEIGHTS)
            customers.append({
                "CustomerID": cust_id,
                "Segment": segment,
                "Country": country,
                "FrequencyRange": params["freq"],
                "RecencyRange": params["recency_days"],
                "AOVRange": params["aov"],
            })
            cust_id += 1
    return customers


def generate_transactions(customers, target_rows=65000):
    rows = []
    invoice_counter = 536365

    for cust in customers:
        freq_min, freq_max = cust["FrequencyRange"]
        rec_min, rec_max = cust["RecencyRange"]
        n_orders = random.randint(freq_min, freq_max)

        for _ in range(n_orders):
            recency_days = random.randint(rec_min, rec_max)
            order_date = END_DATE - timedelta(days=recency_days)
            # shift slightly randomly within +/- 5 days for spread
            order_date = order_date - timedelta(days=random.randint(0, 5))
            order_date = max(START_DATE, min(order_date, END_DATE))

            invoice_no = str(invoice_counter)
            invoice_counter += 1

            n_lines = random.randint(1, 8)
            is_return = random.random() < 0.025  # ~2.5% cancellations/returns

            for _ in range(n_lines):
                stock_code, description, base_price = random.choice(PRODUCTS)
                qty = random.randint(1, 24)
                price_jitter = round(base_price * random.uniform(0.95, 1.08), 2)

                if is_return:
                    invoice = "C" + invoice_no
                    qty = -abs(qty)
                else:
                    invoice = invoice_no

                # add some time-of-day variation
                ts = order_date + timedelta(
                    hours=random.randint(8, 19), minutes=random.randint(0, 59)
                )

                rows.append({
                    "InvoiceNo": invoice,
                    "StockCode": stock_code,
                    "Description": description,
                    "Quantity": qty,
                    "InvoiceDate": ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "UnitPrice": price_jitter,
                    "CustomerID": cust["CustomerID"],
                    "Country": cust["Country"],
                })

            if len(rows) >= target_rows:
                break
        if len(rows) >= target_rows:
            break

    df = pd.DataFrame(rows)

    # introduce a small amount of data quality issues, typical of the real
    # dataset, to give the ETL pipeline something meaningful to clean
    n = len(df)
    missing_idx = np.random.choice(n, size=int(n * 0.015), replace=False)
    df.loc[missing_idx, "CustomerID"] = np.nan

    dup_idx = np.random.choice(n, size=int(n * 0.005), replace=False)
    dup_rows = df.loc[dup_idx]
    df = pd.concat([df, dup_rows], ignore_index=True)

    zero_price_idx = np.random.choice(len(df), size=int(len(df) * 0.003), replace=False)
    df.loc[zero_price_idx, "UnitPrice"] = 0.0

    return df


if __name__ == "__main__":
    customers = generate_customers()
    df = generate_transactions(customers, target_rows=65000)
    df = df.sort_values("InvoiceDate").reset_index(drop=True)
    out_path = "/home/claude/dissertation/data/online_retail_synthetic.csv"
    df.to_csv(out_path, index=False)
    print(f"Generated {len(df):,} rows -> {out_path}")
    print(df.head())
    print("\nSummary:")
    print(df.describe(include='all'))
