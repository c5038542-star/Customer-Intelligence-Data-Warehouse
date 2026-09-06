"""
app.py
------
CIDW Web Prototype  — an AI-Enabled Customer Intelligence Platform.

A Streamlit application that turns the CIDW data warehouse and predictive
analytics module into an interactive analytical decision-support prototype
for user acceptance testing with potential beneficiaries.

Six screens accessible from the left sidebar:
    1. Overview             high-level KPIs and auto-generated insights
    2. Sales Analytics      revenue trends by month/country/product
    3. Customer Intelligence RFM segments, high-value customers
    4. Product Analytics    top products by revenue
    5. AI Predictions       churn risk with explainable AI + clusters
    6. Reports & Insights   auto-generated business insights, downloadable

Run from the project root with:
    streamlit run code/app.py

Author: Alexander Ugochukwu Ejiogu (Student No. 35038543)
MSc Computing Research Project, Sheffield Hallam University, 2026
"""

import subprocess
import sys
import os
import json
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="CIDW  — Customer Intelligence Platform",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

NAVY, DEEP, TEAL, MINT, ACCENT = "#21295C", "#065A82", "#1C7293", "#028090", "#B85042"

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# ----------------------------------------------------------------------
# Auto-build warehouse and ML outputs if missing (for Streamlit Cloud)
# ----------------------------------------------------------------------
import subprocess
import sys

CODE_DIR = Path(__file__).resolve().parent

def ensure_dataset_built(dataset_label, source_csv, db_target, risk_target, metrics_target):
    """If the SQLite/CSV/JSON outputs are missing, rebuild them from source."""
    # Check if all outputs exist AND the db actually has the fact_sales table
if db_target.exists() and risk_target.exists() and metrics_target.exists():
    try:
        import sqlite3 as _sq
        conn = _sq.connect(str(db_target))
        row_count = conn.execute("SELECT COUNT(*) FROM fact_sales").fetchone()[0]
        conn.close()
        if row_count > 0:
            return  # genuinely already built
        else:
            # DB exists but is empty — delete it and rebuild
            db_target.unlink()
    except Exception:
        # DB exists but is corrupt — delete and rebuild
        if db_target.exists():
            db_target.unlink()

    source_path = DATA_DIR / source_csv
    if not source_path.exists():
        # Source CSV also missing — nothing we can do
        return

    with st.spinner(f"First-time setup: building {dataset_label} warehouse (30-60 seconds)..."):
        try:
            # Run ETL against the source CSV
            subprocess.run(
                [sys.executable, str(CODE_DIR / "etl_pipeline_demo.py"),
                 str(source_path)],
                cwd=str(CODE_DIR), check=True, capture_output=True, text=True, timeout=600,
            )
            # ETL writes to data/cidw_dw.sqlite — rename to target
            default_db = DATA_DIR / "cidw_dw.sqlite"
            if default_db.exists() and default_db != db_target:
                default_db.rename(db_target)

            # Run ML pipeline
            subprocess.run(
                [sys.executable, str(CODE_DIR / "predictive_analytics.py")],
                cwd=str(CODE_DIR), check=True, capture_output=True, text=True, timeout=600,
            )
            # ML writes to data/high_risk_customers.csv and data/predictive_metrics.json — rename
            for src_name, dst in [
                ("high_risk_customers.csv", risk_target),
                ("predictive_metrics.json", metrics_target),
            ]:
                src = DATA_DIR / src_name
                if src.exists() and src != dst:
                    src.rename(dst)
        except subprocess.CalledProcessError as e:
            st.error(f"Failed to build {dataset_label} warehouse.")
        with st.expander("Error details (for debugging)"):
            st.code(f"STDERR:\n{e.stderr}\n\nSTDOUT:\n{e.stdout}", language="text")
            st.stop()
        except subprocess.CalledProcessError as e:
            st.error(f"Failed to build {dataset_label} warehouse.")
       with st.expander("Error details (for debugging)"):
            st.code(f"STDERR:\n{e.stderr}\n\nSTDOUT:\n{e.stdout}", language="text")
            st.stop()

# Build synthetic (always attempt — it's small and fast)
ensure_dataset_built(
    "synthetic",
    "online_retail_synthetic.csv",
    DATA_DIR / "cidw_dw_synthetic.sqlite",
    DATA_DIR / "high_risk_customers_synthetic.csv",
    DATA_DIR / "predictive_metrics_synthetic.json",
)

# Build UCI only when running locally (not on cloud, where the build times out)
IS_CLOUD = os.environ.get("STREAMLIT_SERVER_HEADLESS") == "true" or "streamlit" in os.environ.get("HOME", "").lower() or "/mount/src" in str(CODE_DIR)

if not IS_CLOUD and (DATA_DIR / "online_retail_uci.csv").exists():
    ensure_dataset_built(
        "UCI",
        "online_retail_uci.csv",
        DATA_DIR / "cidw_dw_uci.sqlite",
        DATA_DIR / "high_risk_customers_uci.csv",
        DATA_DIR / "predictive_metrics_uci.json",
    )

DATASET_OPTIONS = {
    "Synthetic (validation)": {
        "db":        DATA_DIR / "cidw_dw_synthetic.sqlite",
        "risk_csv":  DATA_DIR / "high_risk_customers_synthetic.csv",
        "metrics":   DATA_DIR / "predictive_metrics_synthetic.json",
        "description": "35,533-row synthetic twin with injected DQ faults (174 duplicates, 530 missing IDs, 106 zero-prices). Ground-truth validation dataset.",
    },
    "UCI Online Retail (real)": {
        "db":        DATA_DIR / "cidw_dw_uci.sqlite",
        "risk_csv":  DATA_DIR / "high_risk_customers_uci.csv",
        "metrics":   DATA_DIR / "predictive_metrics_uci.json",
        "description": "541,909-row real dataset from a UK-based online retailer (Chen, 2015 — UCI ML Repository, CC BY 4.0). Dec 2010 – Dec 2011.",
    },
}


# ----------------------------------------------------------------------
# Custom CSS
# ----------------------------------------------------------------------
st.markdown(
    f"""
    <style>
        .main .block-container {{ padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1300px; }}
        h1, h2, h3 {{ color: {NAVY}; font-family: 'Cambria', serif; }}
        .stTabs [data-baseweb="tab-list"] {{ gap: 0.5rem; }}
        div[data-testid="stMetric"] {{
            background: linear-gradient(135deg, #F5F8FB 0%, #E9F0F5 100%);
            border-left: 5px solid {DEEP};
            padding: 1rem 1.2rem; border-radius: 8px;
        }}
        div[data-testid="stMetric"] label {{
            color: {DEEP} !important;
            font-weight: 700 !important;
            font-size: 1.0rem !important;
        }}
        div[data-testid="stMetric"] label p {{
            color: {DEEP} !important;
            font-weight: 700 !important;
            font-size: 1.0rem !important;
        }}
        div[data-testid="stMetricLabel"],
        div[data-testid="stMetricLabel"] * {{
            color: {DEEP} !important;
            font-weight: 700 !important;
            font-size: 1.0rem !important;
        }}
        div[data-testid="stMetricValue"],
        div[data-testid="stMetricValue"] * {{
            color: {NAVY} !important;
            font-size: 2.0rem !important;
            font-weight: 700 !important;
        }}
        .insight-box {{
            background: #E6F1EF; border-left: 5px solid {MINT};
            padding: 1rem 1.2rem; border-radius: 6px; margin: 0.6rem 0;
            color: #21295C !important;
        }}
        .insight-box b, .insight-box strong {{ color: #21295C !important; }}
        .insight-box i, .insight-box em {{ color: #065A82 !important; }}
        .risk-box {{
            background: #FBEDEA; border-left: 5px solid {ACCENT};
            padding: 1rem 1.2rem; border-radius: 6px; margin: 0.6rem 0;
            color: #21295C !important;
        }}
        .risk-box b, .risk-box strong {{ color: #B85042 !important; }}
        .risk-box i, .risk-box em {{ color: #21295C !important; }}
        .stDataFrame {{ font-size: 0.9rem; }}
        section[data-testid="stSidebar"] {{ background: #F5F8FB; }}
        section[data-testid="stSidebar"] h1 {{ font-size: 1.3rem !important; }}
                    section[data-testid="stSidebar"] .stRadio label {{
            font-size: 1.15rem !important;
            padding: 0.5rem 0 !important;
            color: #21295C !important;
        }}
        section[data-testid="stSidebar"] .stRadio label p {{
            font-size: 1.15rem !important;
            line-height: 1.7 !important;
            color: #21295C !important;
        }}
        section[data-testid="stSidebar"] .stRadio label div {{
            color: #21295C !important;
        }}
        section[data-testid="stSidebar"] * {{
            color: #21295C;
        }}  
                section[data-testid="stSidebar"] .stSelectbox label {{
            color: #B85042 !important;
            font-weight: 700 !important;
        }}
        section[data-testid="stSidebar"] .stSelectbox > div {{
            background-color: #FFFFFF !important;
        }}
        section[data-testid="stSidebar"] .stSelectbox > div > div {{
            background-color: #FFFFFF !important;
        }}
        section[data-testid="stSidebar"] .stSelectbox div {{
            background-color: #FFFFFF !important;
            color: #21295C !important;
        }}
        section[data-testid="stSidebar"] .stSelectbox input {{
            color: #21295C !important;
            background-color: #FFFFFF !important;
            -webkit-text-fill-color: #21295C !important;
        }}
        section[data-testid="stSidebar"] .stSelectbox span {{
            color: #21295C !important;
        }}
        section[data-testid="stSidebar"] .stSelectbox svg {{
            fill: #21295C !important;
        }}
        section[data-testid="stSelectbox"] div[role="listbox"] {{
            background-color: #FFFFFF !important;
        }}
        section[data-testid="stSelectbox"] div[role="listbox"] * {{
            color: #21295C !important;
        }}
        div[data-baseweb="popover"] div[role="listbox"] {{
            background-color: #FFFFFF !important;
        }}
        div[data-baseweb="popover"] div[role="listbox"] * {{
            color: #21295C !important;
        }}
        section[data-testid="stSidebar"] .stCaption,
        section[data-testid="stSidebar"] .stCaption * {{
            color: #21295C !important;
            font-size: 0.85rem !important;
            line-height: 1.4 !important;
        }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ----------------------------------------------------------------------
# Cached loaders
# ----------------------------------------------------------------------
@st.cache_data
def load_from_sql(query: str, db_path: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    try:
        return pd.read_sql(query, conn)
    finally:
        conn.close()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

DATASET_OPTIONS = {
    "Synthetic (validation)": {
        "db":        DATA_DIR / "cidw_dw_synthetic.sqlite",
        "risk_csv":  DATA_DIR / "high_risk_customers_synthetic.csv",
        "metrics":   DATA_DIR / "predictive_metrics_synthetic.json",
        "description": "35,533-row synthetic twin with injected DQ faults (174 duplicates, 530 missing IDs, 106 zero-prices). Ground-truth validation dataset.",
    },
    "UCI Online Retail (real)": {
        "db":        DATA_DIR / "cidw_dw_uci.sqlite",
        "risk_csv":  DATA_DIR / "high_risk_customers_uci.csv",
        "metrics":   DATA_DIR / "predictive_metrics_uci.json",
        "description": "541,909-row real dataset from a UK-based online retailer (Chen, 2015 — UCI ML Repository, CC BY 4.0). Dec 2010 – Dec 2011.",
    },
}


# ----------------------------------------------------------------------
# Cached loaders
# ----------------------------------------------------------------------
@st.cache_data
def load_high_risk_customers(path_str: str) -> pd.DataFrame:
    path = Path(path_str)
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame()


@st.cache_data
def load_predictive_metrics(path_str: str) -> dict:
    path = Path(path_str)
    if path.exists():
        return json.loads(path.read_text())
    return {}


@st.cache_data
def kpi_summary() -> dict:
    q = """
    SELECT
        SUM(CASE WHEN is_return=0 THEN line_total ELSE 0 END) AS total_revenue,
        COUNT(DISTINCT CASE WHEN is_return=0 THEN invoice_no END) AS total_orders,
        COUNT(DISTINCT customer_key) AS active_customers,
        AVG(CASE WHEN is_return=0 THEN line_total ELSE NULL END) AS avg_line_value
    FROM fact_sales
    """
    row = load_from_sql(q, str(DB_PATH)).iloc[0]
    return {
        "revenue": float(row["total_revenue"] or 0),
        "orders": int(row["total_orders"] or 0),
        "customers": int(row["active_customers"] or 0),
        "avg_line": float(row["avg_line_value"] or 0),
    }

# ----------------------------------------------------------------------
# Dataset selector 
# ----------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        "<div style='color: #B85042; font-weight: 700; font-size: 0.95rem; "
        "margin: 0.3rem 0 0.2rem 0;'>DATASET</div>",
        unsafe_allow_html=True,
    )
    dataset_choice = st.selectbox(
        "Choose dataset",
        list(DATASET_OPTIONS.keys()),
        label_visibility="collapsed",
        key="dataset_selector",
    )
    # Clear caches whenever the dataset changes
    if "prev_dataset" not in st.session_state:
        st.session_state.prev_dataset = dataset_choice
    if st.session_state.prev_dataset != dataset_choice:
        st.cache_data.clear()
        st.session_state.prev_dataset = dataset_choice
    dataset = DATASET_OPTIONS[dataset_choice]
    st.caption(dataset["description"])
    st.markdown("---")

# Now switch the paths the loaders will use
DB_PATH = dataset["db"]
RISK_CSV_PATH = dataset["risk_csv"]
METRICS_PATH = dataset["metrics"]

# ----------------------------------------------------------------------
# Sidebar
# ----------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        "<div style='font-size: 2.2rem; text-align: center; margin: 0.5rem 0;'>📊</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='color: #21295C; font-size: 1.4rem; font-weight: 700; "
        "text-align: center; line-height: 1.3; margin-bottom: 0.4rem; "
        "font-family: Cambria, serif;'>"
        "CIDW Platform"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='color: #065A82; font-size: 1.0rem; font-weight: 600; "
        "text-align: center; line-height: 1.4; margin-bottom: 0.5rem;'>"
        "AI-Enabled Data Warehousing System for Predictive Customer "
        "Relationship Management and Business Intelligence"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    screen = st.radio(
        "Navigate to:",
        [
            "🏠   Overview",
            "💰   Sales Analytics",
            "👥   Customer Intelligence",
            "📦   Product Analytics",
            "🔮   AI Predictions",
            "📋   Reports & Insights",
        ],
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.caption(
        "**Prototype** — MSc Computing Research Project\n\n"
        "Alexander U. Ejiogu\n\n"
        "Student No. 35038543\n\n"
        "Sheffield Hallam University, 2026"
    )


# ======================================================================
# SCREEN 1  — OVERVIEW
# ======================================================================
if screen.endswith("Overview"):
    st.title("Customer Intelligence Platform  — Overview")
    st.markdown(
        "*A single-glance view of business performance across the customer base, "
        "backed by an AI-enabled data-warehousing system.*"
    )
    st.markdown("&nbsp;")

    k = kpi_summary()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total revenue",   f"£{k['revenue']:,.0f}")
    c2.metric("Total orders",     f"{k['orders']:,}")
    c3.metric("Active customers", f"{k['customers']:,}")
    c4.metric("Avg. line value",  f"£{k['avg_line']:,.2f}")

    st.markdown("&nbsp;")

    c_left, c_right = st.columns([3, 2])

    with c_left:
        st.subheader("Revenue trend")
        trend = load_from_sql("""
            SELECT printf('%04d-%02d', dd.year, dd.month_number) AS month,
                   SUM(f.line_total) AS revenue
            FROM fact_sales f
            JOIN dim_date dd ON f.date_key = dd.date_key
            WHERE f.is_return = 0
            GROUP BY dd.year, dd.month_number
            ORDER BY dd.year, dd.month_number
        """, str(DB_PATH))
        fig = px.line(trend, x="month", y="revenue", markers=True,
                      color_discrete_sequence=[DEEP])
        fig.update_layout(
            height=350, margin=dict(l=10, r=10, t=20, b=10),
            xaxis_title=None, yaxis_title="Revenue (£)",
            plot_bgcolor="white",
        )
        fig.update_traces(line=dict(width=3))
        st.plotly_chart(fig, use_container_width=True)

    with c_right:
        st.subheader("Top 5 products")
        top = load_from_sql("""
            SELECT dp.description AS product,
                   SUM(f.line_total) AS revenue
            FROM fact_sales f
            JOIN dim_product dp ON f.product_key = dp.product_key
            WHERE f.is_return = 0
            GROUP BY dp.description
            ORDER BY revenue DESC LIMIT 5
        """, str(DB_PATH))
        top["product"] = top["product"].str[:35]
        fig = px.bar(top, x="revenue", y="product", orientation="h",
                     color_discrete_sequence=[TEAL])
        fig.update_layout(
            height=350, margin=dict(l=10, r=10, t=20, b=10),
            yaxis={"categoryorder": "total ascending"},
            xaxis_title="Revenue (£)", yaxis_title=None, plot_bgcolor="white",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("&nbsp;")
    st.subheader("🤖  AI-generated insights")

    metrics = load_predictive_metrics(str(METRICS_PATH))
    risk_df = load_high_risk_customers(str(RISK_CSV_PATH))

    seg = load_from_sql("""
        SELECT customer_segment AS segment, COUNT(*) AS n
        FROM dim_customer
        WHERE customer_id != 'GUEST'
        GROUP BY customer_segment
        ORDER BY n DESC
    """, str(DB_PATH))

    insights = []
    if not seg.empty:
        top_seg = seg.iloc[0]
        pct = 100 * top_seg["n"] / seg["n"].sum()
        insights.append(
            f"Largest customer segment: *{top_seg['segment']}* — "
            f"{int(top_seg['n']):,} customers ({pct:.0f}% of the base)."
        )
    if metrics.get("kmeans"):
        km = metrics["kmeans"]
        insights.append(
            f"Customer clustering: the AI identified "
            f"*{km['k_best']} natural behavioural groups* in the data "
            f"(silhouette score = {km['silhouette']:.3f})."
        )
    if metrics.get("churn"):
        ch = metrics["churn"]
        insights.append(
            f"Churn prediction: the classifier flags "
            f"*{len(risk_df)} customers at elevated churn risk*. "
            f"Model recall = {ch['recall']:.1%} — it catches roughly "
            f"three-quarters of true churners."
        )
    if metrics.get("top_features"):
        top_feat = sorted(metrics["top_features"],
                          key=lambda x: -x["importance_mean"])[0]
        insights.append(
            f"Key churn driver (Explainable AI): *{top_feat['feature']}* "
            "is the dominant behavioural predictor. Retention effort should "
            "target customers whose order rate is slowing."
        )

    for ins in insights:
        st.markdown(f"<div class='insight-box'>{ins}</div>", unsafe_allow_html=True)


# ======================================================================
# SCREEN 2  — SALES ANALYTICS
# ======================================================================
elif screen.endswith("Sales Analytics"):
    st.title("Sales Analytics")
    st.markdown("*Revenue and order patterns across time, geography and products.*")

    tab1, tab2, tab3 = st.tabs(["📈  Monthly revenue", "🌍  Revenue by country", "📅  Orders by weekday"])

    with tab1:
        st.subheader("Monthly revenue trend")
        trend = load_from_sql("""
            SELECT printf('%04d-%02d', dd.year, dd.month_number) AS month,
                   SUM(f.line_total) AS revenue,
                   COUNT(DISTINCT f.invoice_no) AS orders
            FROM fact_sales f JOIN dim_date dd ON f.date_key = dd.date_key
            WHERE f.is_return = 0
            GROUP BY dd.year, dd.month_number
            ORDER BY dd.year, dd.month_number
        """, str(DB_PATH))
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=trend["month"], y=trend["revenue"], mode="lines+markers",
                                 name="Revenue (£)", line=dict(color=DEEP, width=3),
                                 yaxis="y"))
        fig.add_trace(go.Bar(x=trend["month"], y=trend["orders"],
                             name="Orders", marker_color=MINT, opacity=0.4, yaxis="y2"))
        fig.update_layout(
            height=420, margin=dict(l=10, r=10, t=30, b=10),
            yaxis=dict(title="Revenue (£)", color=DEEP),
            yaxis2=dict(title="Orders", color=MINT, overlaying="y", side="right"),
            hovermode="x unified", plot_bgcolor="white",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.info(f"Peak revenue month: **{trend.loc[trend['revenue'].idxmax(), 'month']}** "
                f"at **£{trend['revenue'].max():,.0f}**")

    with tab2:
        st.subheader("Revenue by country")
        top_n = st.slider("Number of countries to show", 5, 15, 10)
        country = load_from_sql(f"""
            SELECT dc.country_name AS country,
                   SUM(f.line_total) AS revenue
            FROM fact_sales f JOIN dim_country dc ON f.country_key = dc.country_key
            WHERE f.is_return = 0
            GROUP BY dc.country_name
            ORDER BY revenue DESC LIMIT {top_n}
        """, str(DB_PATH))
        fig = px.bar(country, x="country", y="revenue", color="revenue",
                     color_continuous_scale=["#B8CDE3", DEEP, NAVY])
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=10),
                          coloraxis_showscale=False, plot_bgcolor="white",
                          xaxis_title=None, yaxis_title="Revenue (£)")
        st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.subheader("Orders by day of week")
        wkday = load_from_sql("""
            SELECT dd.day_of_week AS day, COUNT(DISTINCT f.invoice_no) AS orders
            FROM fact_sales f JOIN dim_date dd ON f.date_key = dd.date_key
            WHERE f.is_return = 0
            GROUP BY dd.day_of_week
            ORDER BY CASE dd.day_of_week
              WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3
              WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5
              WHEN 'Saturday' THEN 6 WHEN 'Sunday' THEN 7 END
        """, str(DB_PATH))
        fig = px.bar(wkday, x="day", y="orders",
                     color_discrete_sequence=[TEAL])
        fig.update_layout(height=380, margin=dict(l=10, r=10, t=20, b=10),
                          xaxis_title=None, yaxis_title="Orders", plot_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)


# ======================================================================
# SCREEN 3  — CUSTOMER INTELLIGENCE
# ======================================================================
elif screen.endswith("Customer Intelligence"):
    st.title("Customer Intelligence")
    st.markdown("*RFM-based segmentation and high-value customer profiles.*")

    # RFM computed live from fact_sales joined to dim_customer
    seg = load_from_sql("""
        SELECT dc.customer_segment AS segment,
               COUNT(DISTINCT dc.customer_key) AS customers,
               COALESCE(SUM(CASE WHEN f.is_return=0 THEN f.line_total END), 0) AS total_spend,
               COALESCE(COUNT(DISTINCT CASE WHEN f.is_return=0 THEN f.invoice_no END), 0) AS total_orders
        FROM dim_customer dc
        LEFT JOIN fact_sales f ON dc.customer_key = f.customer_key
        WHERE dc.customer_id != 'GUEST'
        GROUP BY dc.customer_segment
        ORDER BY customers DESC
    """, str(DB_PATH))
    seg["avg_spend"] = (seg["total_spend"] / seg["customers"]).round(0)
    seg["avg_orders"] = (seg["total_orders"] / seg["customers"]).round(1)

    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("Customer segments (RFM)")
        fig = px.bar(seg, x="segment", y="customers", color="segment",
                     color_discrete_sequence=px.colors.qualitative.Set2)
        fig.update_layout(height=380, margin=dict(l=10, r=10, t=20, b=10),
                          showlegend=False, xaxis_title=None,
                          yaxis_title="Customers", plot_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("Segment profile")
        prof = seg[["segment", "customers", "avg_spend", "avg_orders"]].copy()
        prof["avg_spend"] = prof["avg_spend"].astype(int).apply(lambda x: f"£{x:,}")
        prof.columns = ["Segment", "Customers", "Avg spend", "Avg orders"]
        st.dataframe(prof, use_container_width=True, hide_index=True, height=380)

    st.markdown("---")

    st.subheader("Segment drill-down")
    selected = st.selectbox("Choose a segment to explore:", seg["segment"].tolist())
    drill = load_from_sql(f"""
        SELECT dc.customer_id AS "Customer ID",
               dc.country AS "Country",
               dc.total_orders AS "Orders",
               COALESCE(SUM(CASE WHEN f.is_return=0 THEN f.line_total END), 0) AS "Total spend (£)"
        FROM dim_customer dc
        LEFT JOIN fact_sales f ON dc.customer_key = f.customer_key
        WHERE dc.customer_segment = '{selected}' AND dc.customer_id != 'GUEST'
        GROUP BY dc.customer_key, dc.customer_id, dc.country, dc.total_orders
        ORDER BY "Total spend (£)" DESC LIMIT 100
    """, str(DB_PATH))
    drill["Total spend (£)"] = drill["Total spend (£)"].round(0).astype(int)
    st.caption(f"Showing top 100 customers in **{selected}** by total spend")
    st.dataframe(drill, use_container_width=True, hide_index=True, height=350)


# ======================================================================
# SCREEN 4  — PRODUCT ANALYTICS
# ======================================================================
elif screen.endswith("Product Analytics"):
    st.title("Product Analytics")
    st.markdown("*Which products drive revenue and how demand shifts over time.*")

    metric = st.radio("Rank products by:", ["Revenue", "Quantity sold", "Distinct orders"],
                       horizontal=True)
    metric_sql = {
        "Revenue":         "SUM(f.line_total)",
        "Quantity sold":   "SUM(f.quantity)",
        "Distinct orders": "COUNT(DISTINCT f.invoice_no)",
    }[metric]
    top_n = st.slider("Number of products", 5, 20, 10)

    prod = load_from_sql(f"""
        SELECT dp.description AS product,
               {metric_sql} AS value
        FROM fact_sales f JOIN dim_product dp ON f.product_key = dp.product_key
        WHERE f.is_return = 0
        GROUP BY dp.description
        ORDER BY value DESC LIMIT {top_n}
    """, str(DB_PATH))
    prod["product"] = prod["product"].str[:45]

    fig = px.bar(prod, x="value", y="product", orientation="h",
                 color="value", color_continuous_scale=["#B8CDE3", DEEP, NAVY])
    fig.update_layout(height=520, margin=dict(l=10, r=10, t=20, b=10),
                      yaxis={"categoryorder": "total ascending"},
                      coloraxis_showscale=False, plot_bgcolor="white",
                      xaxis_title=metric, yaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)


# ======================================================================
# SCREEN 5  — AI PREDICTIONS
# ======================================================================
elif screen.endswith("AI Predictions"):
    st.title("AI Predictions  — Churn Risk & Explainable AI")
    st.markdown("*Machine-learning-driven predictions with plain-English reasoning.*")

    metrics = load_predictive_metrics(str(METRICS_PATH))
    risk_df = load_high_risk_customers(str(RISK_CSV_PATH))

    if risk_df.empty or not metrics:
        st.warning(
            "Predictive analytics outputs not found. "
            "Run `python code/predictive_analytics.py` first to generate them."
        )
    else:
        ch = metrics.get("churn", {})
        km = metrics.get("kmeans", {})

        st.subheader("📊  Model performance")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("F1 score",   f"{ch.get('f1', 0):.3f}")
        c2.metric("ROC-AUC",    f"{ch.get('roc_auc', 0):.3f}")
        c3.metric("Recall",     f"{ch.get('recall', 0):.1%}")
        c4.metric("Precision",  f"{ch.get('precision', 0):.1%}")

        st.markdown(
            "<div class='insight-box'>"
            "The classifier catches around three-quarters of true churners "
            "(recall). This is the metric that matters most for retention "
            "marketing, where a missed churner is a lost customer. "
            "Recency and tenure were deliberately excluded from the features "
            "to avoid target leakage."
            "</div>",
            unsafe_allow_html=True,
        )

        st.markdown("---")

        st.subheader("⚠️  Customers at risk of churn")
        st.markdown("*Ranked by predicted churn probability, with a plain-English reason.*")

        n_show = st.slider("Number of customers to show", 10, 50, 20)

        display_df = risk_df.head(n_show).copy()
        display_df.columns = [c.replace("_", " ").title() for c in display_df.columns]
        if "Churn Probability" in display_df.columns:
            display_df["Churn Probability"] = (display_df["Churn Probability"] * 100).round(1).astype(str) + "%"
        for col in ["Recency Days", "Frequency"]:
            if col in display_df.columns:
                display_df[col] = display_df[col].astype(int)
        if "Monetary" in display_df.columns:
            display_df["Monetary"] = display_df["Monetary"].round(0).astype(int).apply(lambda x: f"£{x:,}")

        st.dataframe(display_df, use_container_width=True, hide_index=True, height=430)

        st.download_button(
            "⬇️  Download high-risk customers as CSV",
            risk_df.head(n_show).to_csv(index=False).encode("utf-8"),
            file_name="high_risk_customers_export.csv",
            mime="text/csv",
        )

        st.markdown("---")

        st.subheader("🔍  Explainable AI — what drives the churn prediction?")
        feats = sorted(metrics.get("top_features", []),
                       key=lambda x: x["importance_mean"])
        if feats:
            fdf = pd.DataFrame(feats)
            fig = px.bar(fdf, x="importance_mean", y="feature", orientation="h",
                         error_x="importance_std", color_discrete_sequence=[ACCENT])
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10),
                              xaxis_title="Permutation importance (mean ± SD)",
                              yaxis_title=None, plot_bgcolor="white")
            st.plotly_chart(fig, use_container_width=True)

            top_feat = max(feats, key=lambda x: x["importance_mean"])
            st.markdown(
                f"<div class='risk-box'>"
                f"<b>Key finding:</b> <i>{top_feat['feature']}</i> is the dominant "
                f"predictor of churn (permutation importance "
                f"{top_feat['importance_mean']:.3f} ± {top_feat['importance_std']:.3f}). "
                f"<br><b>Actionable insight:</b> Retention effort should target "
                f"customers whose order rate is slowing, not those segmented by "
                f"cumulative spend alone."
                f"</div>",
                unsafe_allow_html=True,
            )

        st.markdown("---")

        st.subheader("🎯  Customer clusters (K-Means)")
        st.markdown(
            f"The AI identified **{km.get('k_best', 'N/A')} natural behavioural "
            f"clusters** (silhouette-optimal, score = "
            f"{km.get('silhouette', 0):.3f})."
        )

        profiles = km.get("profiles", {})
        if profiles:
            prof_rows = []
            for cid, p in profiles.items():
                prof_rows.append({
                    "Cluster": f"Cluster {cid}",
                    "Customers": int(p["customers"]),
                    "Median recency (days)": int(p["recency_days"]),
                    "Median frequency": int(p["frequency"]),
                    "Median monetary": f"£{int(p['monetary']):,}",
                })
            st.dataframe(pd.DataFrame(prof_rows), use_container_width=True, hide_index=True)


# ======================================================================
# SCREEN 6  — REPORTS & INSIGHTS
# ======================================================================
else:  # Reports & Insights
    st.title("Reports & Insights")
    st.markdown("*Auto-generated business insights ready to act on.*")

    k = kpi_summary()
    metrics = load_predictive_metrics(str(METRICS_PATH))
    risk_df = load_high_risk_customers(str(RISK_CSV_PATH))

    seg = load_from_sql("""
        SELECT dc.customer_segment AS segment,
               COUNT(DISTINCT dc.customer_key) AS n,
               COALESCE(SUM(CASE WHEN f.is_return=0 THEN f.line_total END), 0) AS revenue
        FROM dim_customer dc
        LEFT JOIN fact_sales f ON dc.customer_key = f.customer_key
        WHERE dc.customer_id != 'GUEST'
        GROUP BY dc.customer_segment
        ORDER BY revenue DESC
    """, str(DB_PATH))
    top_month = load_from_sql("""
        SELECT printf('%04d-%02d', dd.year, dd.month_number) AS month,
               SUM(f.line_total) AS rev
        FROM fact_sales f JOIN dim_date dd ON f.date_key=dd.date_key
        WHERE f.is_return=0
        GROUP BY dd.year, dd.month_number
        ORDER BY rev DESC LIMIT 1
    """, str(DB_PATH)).iloc[0]
    top_product = load_from_sql("""
        SELECT dp.description AS p, SUM(f.line_total) AS r
        FROM fact_sales f JOIN dim_product dp ON f.product_key=dp.product_key
        WHERE f.is_return=0
        GROUP BY dp.description ORDER BY r DESC LIMIT 1
    """, str(DB_PATH)).iloc[0]
    top_country = load_from_sql("""
        SELECT dc.country_name AS c, SUM(f.line_total) AS r
        FROM fact_sales f JOIN dim_country dc ON f.country_key=dc.country_key
        WHERE f.is_return=0 GROUP BY dc.country_name ORDER BY r DESC LIMIT 1
    """, str(DB_PATH)).iloc[0]

    st.subheader("Executive summary")
    st.markdown(f"""
    <div class='insight-box'>
    <b>Business performance</b><br>
    Total revenue of <b>£{k['revenue']:,.0f}</b> across <b>{k['orders']:,} orders</b>
    from <b>{k['customers']:,} customers</b>. Average line value <b>£{k['avg_line']:,.2f}</b>.
    </div>
    """, unsafe_allow_html=True)

    st.subheader("Actionable insights")
    insights = [
        (f"🏆 <b>Peak sales month:</b> {top_month['month']} generated the highest "
         f"revenue at £{top_month['rev']:,.0f}. Investigate what drove the peak "
         "and whether it can be repeated."),
        (f"⭐ <b>Top revenue product:</b> \"{top_product['p'][:50]}\" generated "
         f"£{top_product['r']:,.0f}. Ensure stock and consider bundling "
         "with complementary items."),
        (f"🌍 <b>Top country:</b> {top_country['c']} led revenue at "
         f"£{top_country['r']:,.0f}. Assess whether localised campaigns could "
         "expand share."),
    ]
    if not seg.empty:
        top_seg = seg.iloc[0]
        total_rev = seg["revenue"].sum()
        pct = 100 * top_seg["revenue"] / total_rev if total_rev else 0
        insights.append(
            f"👥 <b>Largest revenue segment:</b> \"{top_seg['segment']}\" "
            f"accounts for {pct:.0f}% of total revenue ({int(top_seg['n']):,} "
            f"customers). Prioritise retention here."
        )
    if not risk_df.empty:
        insights.append(
            f"⚠️ <b>Churn risk:</b> {len(risk_df)} customers are flagged at "
            f"elevated churn risk. Launch a targeted re-engagement campaign "
            "in the next 14 days."
        )
    if metrics.get("top_features"):
        top_feat = max(metrics["top_features"], key=lambda x: x["importance_mean"])
        insights.append(
            f"🔍 <b>Retention insight (Explainable AI):</b> <i>{top_feat['feature']}</i> "
            "is the dominant predictor of churn. Marketing should focus on "
            "customers whose order rate is slowing, regardless of past spend."
        )

    for ins in insights:
        st.markdown(f"<div class='insight-box'>{ins}</div>", unsafe_allow_html=True)

    st.markdown("---")

    st.subheader("Download report")
    st.markdown("Export a plain-text business report combining all of the above.")

    def build_text_report() -> bytes:
        lines = []
        lines.append("=" * 70)
        lines.append("CIDW — BUSINESS INTELLIGENCE REPORT")
        lines.append("=" * 70)
        lines.append("")
        lines.append("EXECUTIVE SUMMARY")
        lines.append("-" * 70)
        lines.append(f"Total revenue:      £{k['revenue']:,.0f}")
        lines.append(f"Total orders:       {k['orders']:,}")
        lines.append(f"Active customers:   {k['customers']:,}")
        lines.append(f"Avg. line value:    £{k['avg_line']:,.2f}")
        lines.append("")
        lines.append("ACTIONABLE INSIGHTS")
        lines.append("-" * 70)
        for i, ins in enumerate(insights, 1):
            plain = ins.replace("<b>", "").replace("</b>", "")
            plain = plain.replace("<i>", "").replace("</i>", "")
            for emoji in ["🏆", "⭐", "🌍", "👥", "⚠️", "🔍"]:
                plain = plain.replace(emoji, "")
            lines.append(f"{i}. {plain.strip()}")
            lines.append("")
        if metrics.get("churn"):
            ch = metrics["churn"]
            lines.append("MODEL PERFORMANCE (churn classifier)")
            lines.append("-" * 70)
            lines.append(f"F1 score:   {ch['f1']:.3f}")
            lines.append(f"ROC-AUC:    {ch['roc_auc']:.3f}")
            lines.append(f"Recall:     {ch['recall']:.1%}")
            lines.append(f"Precision:  {ch['precision']:.1%}")
        lines.append("")
        lines.append("=" * 70)
        lines.append("Generated by CIDW — MSc Computing Research Project")
        lines.append("Alexander U. Ejiogu (35038543) — Sheffield Hallam University")
        lines.append("=" * 70)
        return "\n".join(lines).encode("utf-8")

    st.download_button(
        "⬇️  Download report (.txt)",
        build_text_report(),
        file_name="cidw_business_report.txt",
        mime="text/plain",
    )
