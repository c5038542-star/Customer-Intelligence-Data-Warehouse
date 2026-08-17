"""
generate_bi_charts.py
----------------------
Generates the analytical visualisations used in Chapter 5 (Implementation)
and Chapter 6 (Evaluation) of the dissertation. These charts represent the
outputs that would be produced in Power BI / Tableau connected to the
vw_monthly_sales_by_country, vw_customer_rfm and vw_top_products views
defined in schema_warehouse.sql. They are generated here directly from the
warehouse tables using matplotlib/seaborn for reproducibility.
"""

import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

sns.set_theme(style="whitegrid", palette="deep")
DB_PATH = "../data/cidw_dw.sqlite"
OUT_DIR = "../images"

conn = sqlite3.connect(DB_PATH)

# -------------------------------------------------------------------
# 1. Monthly revenue trend (2022-2023)
# -------------------------------------------------------------------
q1 = """
SELECT d.year, d.month_number, d.month_name,
       SUM(f.line_total) AS total_revenue
FROM fact_sales f
JOIN dim_date d ON f.date_key = d.date_key
WHERE f.is_return = 0
GROUP BY d.year, d.month_number, d.month_name
ORDER BY d.year, d.month_number
"""
df1 = pd.read_sql(q1, conn)
df1["period"] = df1["month_name"].str[:3] + " " + df1["year"].astype(str)

plt.figure(figsize=(11, 5))
plt.plot(df1["period"], df1["total_revenue"], marker="o", color="#1C7293", linewidth=2)
plt.title("Monthly Revenue Trend (2022-2023)", fontsize=14, fontweight="bold")
plt.ylabel("Revenue (£)")
plt.xlabel("Month")
plt.xticks(rotation=60, fontsize=8)
plt.tight_layout()
plt.savefig(f"{OUT_DIR}/chart_monthly_revenue_trend.png", dpi=150)
plt.close()

# -------------------------------------------------------------------
# 2. Revenue by country (top 10)
# -------------------------------------------------------------------
q2 = """
SELECT c.country_name, SUM(f.line_total) AS total_revenue
FROM fact_sales f
JOIN dim_country c ON f.country_key = c.country_key
WHERE f.is_return = 0
GROUP BY c.country_name
ORDER BY total_revenue DESC
LIMIT 10
"""
df2 = pd.read_sql(q2, conn)

plt.figure(figsize=(9, 5.5))
sns.barplot(data=df2, y="country_name", x="total_revenue", color="#065A82")
plt.title("Top 10 Countries by Revenue", fontsize=14, fontweight="bold")
plt.xlabel("Revenue (£)")
plt.ylabel("")
plt.tight_layout()
plt.savefig(f"{OUT_DIR}/chart_revenue_by_country.png", dpi=150)
plt.close()

# -------------------------------------------------------------------
# 3. Customer segmentation (RFM-based)
# -------------------------------------------------------------------
q3 = """
SELECT customer_segment, COUNT(*) AS customer_count,
       SUM(total_orders) AS total_orders
FROM dim_customer
GROUP BY customer_segment
ORDER BY customer_count DESC
"""
df3 = pd.read_sql(q3, conn)

plt.figure(figsize=(8, 5.5))
colors = sns.color_palette("Set2", len(df3))
plt.pie(df3["customer_count"], labels=df3["customer_segment"], autopct="%1.1f%%",
        colors=colors, startangle=140, textprops={"fontsize": 9})
plt.title("Customer Segmentation by RFM Profile", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(f"{OUT_DIR}/chart_customer_segments.png", dpi=150)
plt.close()

# -------------------------------------------------------------------
# 4. Top 10 products by revenue
# -------------------------------------------------------------------
q4 = """
SELECT p.description, SUM(f.line_total) AS total_revenue,
       SUM(f.quantity) AS total_units
FROM fact_sales f
JOIN dim_product p ON f.product_key = p.product_key
WHERE f.is_return = 0 AND p.unit_price_band != 'Service/Adjustment'
GROUP BY p.description
ORDER BY total_revenue DESC
LIMIT 10
"""
df4 = pd.read_sql(q4, conn)
df4["description_short"] = df4["description"].str[:30]

plt.figure(figsize=(9, 5.5))
sns.barplot(data=df4, y="description_short", x="total_revenue", color="#21295C")
plt.title("Top 10 Products by Revenue", fontsize=14, fontweight="bold")
plt.xlabel("Revenue (£)")
plt.ylabel("")
plt.tight_layout()
plt.savefig(f"{OUT_DIR}/chart_top_products.png", dpi=150)
plt.close()

# -------------------------------------------------------------------
# 5. Order volume by day of week (operational insight)
# -------------------------------------------------------------------
q5 = """
SELECT d.day_of_week, COUNT(DISTINCT f.invoice_no) AS total_orders
FROM fact_sales f
JOIN dim_date d ON f.date_key = d.date_key
WHERE f.is_return = 0
GROUP BY d.day_of_week
"""
df5 = pd.read_sql(q5, conn)
order_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
df5["day_of_week"] = pd.Categorical(df5["day_of_week"], categories=order_days, ordered=True)
df5 = df5.sort_values("day_of_week")

plt.figure(figsize=(9, 5))
sns.barplot(data=df5, x="day_of_week", y="total_orders", color="#028090")
plt.title("Order Volume by Day of Week", fontsize=14, fontweight="bold")
plt.ylabel("Number of Orders")
plt.xlabel("")
plt.xticks(rotation=30)
plt.tight_layout()
plt.savefig(f"{OUT_DIR}/chart_orders_by_weekday.png", dpi=150)
plt.close()

# -------------------------------------------------------------------
# 6. RFM scatter: Recency vs Monetary, sized by Frequency
# -------------------------------------------------------------------
q6 = """
SELECT dc.customer_segment,
       (julianday((SELECT MAX(last_purchase_date) FROM dim_customer)) - julianday(dc.last_purchase_date)) AS recency_days,
       dc.total_orders AS frequency,
       SUM(f.line_total) AS monetary_value
FROM dim_customer dc
JOIN fact_sales f ON dc.customer_key = f.customer_key
WHERE f.is_return = 0 AND dc.customer_segment != 'Guest / Unidentified'
GROUP BY dc.customer_key
"""
df6 = pd.read_sql(q6, conn)

plt.figure(figsize=(9, 6))
sns.scatterplot(data=df6, x="recency_days", y="monetary_value", hue="customer_segment",
                 size="frequency", sizes=(20, 200), alpha=0.6, palette="Set2")
plt.title("Customer RFM Distribution: Recency vs Monetary Value", fontsize=14, fontweight="bold")
plt.xlabel("Recency (days since last purchase)")
plt.ylabel("Monetary Value (£)")
plt.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)
plt.tight_layout()
plt.savefig(f"{OUT_DIR}/chart_rfm_scatter.png", dpi=150)
plt.close()

print("All charts generated successfully in", OUT_DIR)
conn.close()
