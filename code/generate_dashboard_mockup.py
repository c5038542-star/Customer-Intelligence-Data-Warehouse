"""
generate_dashboard_mockup.py
------------------------------
Creates a single composite image resembling a Power BI dashboard layout,
combining the key visualisations into one "report page" for inclusion as
Figure 5.x (Prototype Dashboard) in the dissertation.
"""

import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns

sns.set_theme(style="whitegrid")
DB_PATH = "../data/cidw_dw.sqlite"
conn = sqlite3.connect(DB_PATH)

fig = plt.figure(figsize=(16, 9.5))
fig.patch.set_facecolor("#F4F6F8")
gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.55, wspace=0.35,
                        height_ratios=[0.18, 1, 1])

# --- Title bar / KPI cards -------------------------------------------------
kpi_query = """
SELECT
  (SELECT SUM(line_total) FROM fact_sales WHERE is_return=0) AS total_revenue,
  (SELECT COUNT(DISTINCT invoice_no) FROM fact_sales WHERE is_return=0) AS total_orders,
  (SELECT COUNT(*) FROM dim_customer WHERE customer_id != 'GUEST') AS total_customers,
  (SELECT ROUND(AVG(line_total),2) FROM (
      SELECT invoice_no, SUM(line_total) AS line_total FROM fact_sales
      WHERE is_return=0 GROUP BY invoice_no)) AS avg_order_value
"""
kpi = pd.read_sql(kpi_query, conn).iloc[0]

kpi_titles = ["Total Revenue", "Total Orders", "Active Customers", "Avg. Order Value"]
kpi_values = [
    f"£{kpi['total_revenue']:,.0f}",
    f"{kpi['total_orders']:,}",
    f"{kpi['total_customers']:,}",
    f"£{kpi['avg_order_value']:,.2f}",
]
kpi_colors = ["#065A82", "#1C7293", "#21295C", "#028090"]

for i in range(4):
    ax = fig.add_subplot(gs[0, :])
    ax.axis("off")
    x = 0.02 + i * 0.245
    ax.text(x, 0.5, kpi_values[i], fontsize=22, fontweight="bold", color=kpi_colors[i],
            transform=ax.transAxes, va="center")
    ax.text(x, 0.05, kpi_titles[i], fontsize=11, color="#444444",
            transform=ax.transAxes, va="center")

fig.text(0.02, 0.965, "Customer Intelligence Dashboard — Sales & CRM Overview (2022–2023)",
         fontsize=15, fontweight="bold", color="#21295C")

# --- Monthly Revenue Trend (line) ------------------------------------------
ax1 = fig.add_subplot(gs[1, :2])
q1 = """
SELECT d.year, d.month_number, d.month_name, SUM(f.line_total) AS total_revenue
FROM fact_sales f JOIN dim_date d ON f.date_key = d.date_key
WHERE f.is_return = 0
GROUP BY d.year, d.month_number, d.month_name ORDER BY d.year, d.month_number
"""
df1 = pd.read_sql(q1, conn)
df1["period"] = df1["month_name"].str[:3] + " " + df1["year"].astype(str)
ax1.plot(df1["period"], df1["total_revenue"], marker="o", color="#065A82", linewidth=2)
ax1.fill_between(range(len(df1)), df1["total_revenue"], color="#065A82", alpha=0.1)
ax1.set_title("Monthly Revenue Trend", fontsize=12, fontweight="bold", loc="left")
ax1.set_xticks(range(len(df1)))
ax1.set_xticklabels(df1["period"], rotation=55, fontsize=7)
ax1.set_ylabel("Revenue (£)", fontsize=9)

# --- Customer Segments (donut) ----------------------------------------------
ax2 = fig.add_subplot(gs[1, 2])
q2 = "SELECT customer_segment, COUNT(*) AS n FROM dim_customer GROUP BY customer_segment"
df2 = pd.read_sql(q2, conn)
colors2 = sns.color_palette("Set2", len(df2))
wedges, _ = ax2.pie(df2["n"], colors=colors2, startangle=140, wedgeprops=dict(width=0.45))
ax2.legend(wedges, df2["customer_segment"], fontsize=7, loc="center left",
           bbox_to_anchor=(0.95, 0.5))
ax2.set_title("Customer Segments", fontsize=12, fontweight="bold", loc="left")

# --- Top products (bar) -----------------------------------------------------
ax3 = fig.add_subplot(gs[2, 0])
q3 = """
SELECT p.description, SUM(f.line_total) AS rev FROM fact_sales f
JOIN dim_product p ON f.product_key = p.product_key
WHERE f.is_return = 0 GROUP BY p.description ORDER BY rev DESC LIMIT 6
"""
df3 = pd.read_sql(q3, conn)
df3["desc_short"] = df3["description"].str[:22]
sns.barplot(data=df3, y="desc_short", x="rev", color="#21295C", ax=ax3)
ax3.set_title("Top Products by Revenue", fontsize=12, fontweight="bold", loc="left")
ax3.set_xlabel("Revenue (£)", fontsize=9)
ax3.set_ylabel("")
ax3.tick_params(axis='y', labelsize=8)

# --- Revenue by country (bar) ------------------------------------------------
ax4 = fig.add_subplot(gs[2, 1])
q4 = """
SELECT c.country_name, SUM(f.line_total) AS rev FROM fact_sales f
JOIN dim_country c ON f.country_key = c.country_key
WHERE f.is_return = 0 GROUP BY c.country_name ORDER BY rev DESC LIMIT 6
"""
df4 = pd.read_sql(q4, conn)
sns.barplot(data=df4, y="country_name", x="rev", color="#028090", ax=ax4)
ax4.set_title("Revenue by Country (Top 6)", fontsize=12, fontweight="bold", loc="left")
ax4.set_xlabel("Revenue (£)", fontsize=9)
ax4.set_ylabel("")
ax4.tick_params(axis='y', labelsize=8)

# --- Orders by weekday (bar) -------------------------------------------------
ax5 = fig.add_subplot(gs[2, 2])
q5 = """
SELECT d.day_of_week, COUNT(DISTINCT f.invoice_no) AS orders
FROM fact_sales f JOIN dim_date d ON f.date_key = d.date_key
WHERE f.is_return = 0 GROUP BY d.day_of_week
"""
df5 = pd.read_sql(q5, conn)
order_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
df5["day_of_week"] = pd.Categorical(df5["day_of_week"], categories=order_days, ordered=True)
df5 = df5.sort_values("day_of_week")
sns.barplot(data=df5, x="day_of_week", y="orders", color="#1C7293", ax=ax5)
ax5.set_title("Orders by Day of Week", fontsize=12, fontweight="bold", loc="left")
ax5.set_xticks(range(len(df5)))
ax5.set_xticklabels(df5["day_of_week"], rotation=60, fontsize=7)
ax5.set_ylabel("")
ax5.set_xlabel("")

plt.savefig("../images/dashboard_mockup.png", dpi=150, facecolor="#F4F6F8", bbox_inches="tight")
plt.close()
print("Dashboard mockup saved.")
conn.close()
