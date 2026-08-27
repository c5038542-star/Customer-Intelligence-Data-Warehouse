# Customer Intelligence Data Warehouse (CIDW) — prototype code

This is the code that goes with my MSc Computing dissertation,  
*"Implementation of an AI-Enabled Data Warehousing System for
Predictive Customer Relationship Management and Business Intelligence"*
(Alexander Ugochukwu Ejiogu, Student No. 35038543).

## Folder structure

The scripts use relative paths, so keep things laid out like this:

```
project/
├── code/      <- all .py files and schema_warehouse.sql
├── data/      <- datasets; the SQLite warehouse gets created here
└── images/    <- charts and dashboard images land here
```

Everything should be run from inside `code/`.

## Datasets

I run the pipeline against two datasets:

The first is the real one, UCI's "Online Retail" dataset (Chen, 2015), about 541,909 rows. I used the Kaggle mirror ("E-Commerce Data" by user carrie1): https://www.kaggle.com/datasets/carrie1/ecommerce-data. Download it and save the CSV as `data/online_retail_kaggle.csv`. The pipeline deals with its real world messiness on its own, so no manual cleanup is needed first.

The second is a synthetic dataset I generated myself (`data/online_retail_synthetic.csv`, ~35,533 rows, regenerate it any time with `generate_dataset.py`). I deliberately seeded it with known data quality faults so I could check the cleansing logic against answers I already knew, rather than just trusting the output on the real data.

## What's in here

- `etl_pipeline.py` — the production ETL pipeline (pandas + SQLAlchemy).
- `etl_pipeline_demo.py` — a self-contained SQLite version with integrity checks and timing benchmarks built in, so it runs without a database server.
- `schema_warehouse.sql` — MySQL DDL for the staging tables, star schema and analytical views.
- `generate_dataset.py` — regenerates the synthetic dataset above.
- `generate_bi_charts.py` — produces six BI charts from the warehouse.
- `generate_dashboard_mockup.py` — a composite, Power BI style dashboard image.
- `generate_diagrams.py` — architecture, ETL, star schema and methodology diagrams for the write up.
- `predictive_analytics.py` — the ML extension: K-Means clustering, a Random Forest churn classifier, and explainable AI via permutation importance, all run against the loaded warehouse.

## Running it

### Option A — SQLite demo (easiest, no server needed)

```bash
pip install pandas matplotlib seaborn scikit-learn
cd code
python etl_pipeline_demo.py                                  # synthetic dataset
python etl_pipeline_demo.py ../data/online_retail_kaggle.csv # real dataset
python generate_bi_charts.py
python generate_dashboard_mockup.py
python predictive_analytics.py
```

The demo script prints out the data-quality report, referential-integrity checks (orphan row queries plus `PRAGMA foreign_key_check`), and mean execution times for three representative analytical queries.

`predictive_analytics.py` then prints the silhouette-optimal K for clustering, the churn classifier's metrics (precision, recall, F1, ROC-AUC), and the permutation feature importances, and writes `high_risk_customers.csv`, which a marketing team could realistically hand off and act on.

### Option B — MySQL (production-style setup)

Create the schema first:

```bash
mysql -u <user> -p < schema_warehouse.sql
```

Then set `DB_CONNECTION_STRING` in `etl_pipeline.py` and run:

```bash
pip install pandas sqlalchemy mysql-connector-python
python etl_pipeline.py
```

From there you can point Power BI or Tableau at `cidw_dw` and build visuals on `vw_monthly_sales_by_country`, `vw_customer_rfm` and `vw_top_products`.

## The predictive analytics extension

`predictive_analytics.py` builds on the descriptive pipeline with three techniques that follow on from each other: first cluster customers to find natural groupings, then classify them to predict churn, then explain what the classifier is actually picking up on.

**Clustering.** K-Means over the RFM feature space, with K chosen by silhouette score (Rousseeuw, 1987) rather than picked by hand. On the synthetic warehouse this settles on K=7 with a silhouette of 0.43, which lines up nicely with the seven behavioural profiles I baked into the generator.

**Classification.** A Random Forest predicts churn from behavioural features. I left recency out on purpose to avoid target leakage, and on the synthetic dataset I also dropped tenure, since it's generated from the same ranges as the label and would otherwise let the model cheat. So it's learning from frequency, monetary value, average order value and return rate only. On the held-out 25% test set: precision 0.483, recall 0.749, F1 0.587, ROC-AUC 0.669 not spectacular, but honest, and not leaking information it shouldn't have.

**Explainability.** Both impurity based and permutation based feature importance (Fisher, Rudin & Dominici, 2019), plus plain English, per-customer reasons for the 50 highest risk customers, written out to `high_risk_customers.csv`. I went with permutation importance instead of SHAP mainly because it's model agnostic needs nothing beyond scikit-learn, and is well established in its own right in the XAI literature. SHAP felt like overkill for what this needed to show.

## Fixes made along the way

A running list of issues I ran into and corrected during development:

1. Orphan fact rows — `dim_customer` now gets built from every customer, not just the ones with matching orders.
2. Loads now append into the DDL created tables instead of overwriting them, so constraints are preserved.
3. The staging table (`stg_online_retail`) is actually populated now, not skipped.
4. SQLAlchemy is imported lazily, so the demo script only needs pandas to run.
5. Handled real dataset quirks properly, encoding, date parsing, ID formats, service/non-product codes.
6. Added the integrity checks and repeatable query benchmarks mentioned above.
7. Cleaned up matplotlib tick warnings and excluded service codes from the product chart.
