"""
generate_diagrams.py
----------------------
Generates all conceptual/technical diagrams for the dissertation using
Graphviz:
  1. System architecture diagram
  2. ETL data-flow diagram
  3. Star-schema entity relationship diagram
  4. Research methodology "onion" (rendered as nested process diagram)
"""

import graphviz

OUT = "../images"

# ---------------------------------------------------------------------
# 1. System Architecture Diagram
# ---------------------------------------------------------------------
g = graphviz.Digraph("architecture", format="png")
g.attr(rankdir="LR", fontname="Helvetica", fontsize="11", splines="spline",
       bgcolor="white", pad="0.4")
g.attr("node", fontname="Helvetica", fontsize="11", shape="box", style="rounded,filled",
       margin="0.25,0.15")
g.attr("edge", fontname="Helvetica", fontsize="9", color="#555555")

with g.subgraph(name="cluster_sources") as c:
    c.attr(label="Data Sources", style="rounded,dashed", color="#888888", fontname="Helvetica", fontsize="11")
    c.node("crm", "CRM System\n(Customer Records)", fillcolor="#CADCFC", color="#1E2761")
    c.node("ecom", "E-commerce Platform\n(Transactions)", fillcolor="#CADCFC", color="#1E2761")
    c.node("web", "Website / Social Media\n(Engagement Data)", fillcolor="#CADCFC", color="#1E2761")

with g.subgraph(name="cluster_etl") as c:
    c.attr(label="ETL Layer (Python)", style="rounded,dashed", color="#888888", fontname="Helvetica", fontsize="11")
    c.node("extract", "Extract\n(Pandas)", fillcolor="#A7BEAE", color="#2C5F2D")
    c.node("transform", "Transform\n(Cleansing, Validation,\nDimensional Modelling)", fillcolor="#A7BEAE", color="#2C5F2D")
    c.node("load", "Load\n(SQLAlchemy)", fillcolor="#A7BEAE", color="#2C5F2D")
    c.edge("extract", "transform")
    c.edge("transform", "load")

with g.subgraph(name="cluster_dw") as c:
    c.attr(label="Data Warehouse (MySQL)", style="rounded,dashed", color="#888888", fontname="Helvetica", fontsize="11")
    c.node("staging", "Staging Schema\n(cidw_staging)", fillcolor="#F9E795", color="#B85042")
    c.node("warehouse", "Star Schema\n(cidw_dw)\nFact + Dimension Tables", fillcolor="#F9E795", color="#B85042")
    c.node("views", "Analytical Views\n(vw_monthly_sales,\nvw_customer_rfm,\nvw_top_products)", fillcolor="#F9E795", color="#B85042")
    c.edge("staging", "warehouse")
    c.edge("warehouse", "views")

with g.subgraph(name="cluster_bi") as c:
    c.attr(label="Business Intelligence Layer", style="rounded,dashed", color="#888888", fontname="Helvetica", fontsize="11")
    c.node("bi", "Power BI / Tableau\nDashboards & Reports", fillcolor="#F96167", color="#7A1E20", fontcolor="white")

with g.subgraph(name="cluster_users") as c:
    c.attr(label="End Users", style="rounded,dashed", color="#888888", fontname="Helvetica", fontsize="11")
    c.node("managers", "Business Managers\n& Marketing Teams", fillcolor="#FFFFFF", color="#333333")
    c.node("it", "IT Administrators", fillcolor="#FFFFFF", color="#333333")

g.edge("crm", "extract")
g.edge("ecom", "extract")
g.edge("web", "extract")
g.edge("load", "staging")
g.edge("views", "bi")
g.edge("bi", "managers")
g.edge("bi", "it")

g.render(f"{OUT}/fig_architecture", cleanup=True)
print("Architecture diagram done")

# ---------------------------------------------------------------------
# 2. ETL Data Flow Diagram
# ---------------------------------------------------------------------
g2 = graphviz.Digraph("etl_flow", format="png")
g2.attr(rankdir="TB", fontname="Helvetica", fontsize="11", splines="spline", bgcolor="white", pad="0.4")
g2.attr("node", fontname="Helvetica", fontsize="11", shape="box", style="rounded,filled", margin="0.25,0.12")
g2.attr("edge", fontname="Helvetica", fontsize="9", color="#555555")

g2.node("raw", "Raw CRM/E-commerce Extract\n(online_retail.csv)", fillcolor="#CADCFC", color="#1E2761")
g2.node("extract2", "EXTRACT\nRead CSV into DataFrame", fillcolor="#A7BEAE", color="#2C5F2D")
g2.node("dedupe", "Remove duplicate records", fillcolor="#A7BEAE", color="#2C5F2D")
g2.node("dates", "Parse & validate\nInvoiceDate", fillcolor="#A7BEAE", color="#2C5F2D")
g2.node("missing", "Handle missing CustomerID\n(assign 'GUEST')", fillcolor="#A7BEAE", color="#2C5F2D")
g2.node("derive", "Derive line_total,\nis_return, date_key", fillcolor="#A7BEAE", color="#2C5F2D")
g2.node("dims", "Build Dimension Tables\n(dim_date, dim_customer,\ndim_product, dim_country)", fillcolor="#F9E795", color="#B85042")
g2.node("fact", "Build Fact Table\n(fact_sales)", fillcolor="#F9E795", color="#B85042")
g2.node("loadwh", "LOAD into MySQL\nData Warehouse", fillcolor="#F96167", color="#7A1E20", fontcolor="white")
g2.node("dq", "Data Quality Report\n(rows cleaned, anomalies\nflagged for audit)", fillcolor="#FFFFFF", color="#333333")

g2.edge("raw", "extract2")
g2.edge("extract2", "dedupe")
g2.edge("dedupe", "dates")
g2.edge("dates", "missing")
g2.edge("missing", "derive")
g2.edge("derive", "dims")
g2.edge("derive", "fact")
g2.edge("dims", "loadwh")
g2.edge("fact", "loadwh")
g2.edge("derive", "dq")

g2.render(f"{OUT}/fig_etl_flow", cleanup=True)
print("ETL flow diagram done")

# ---------------------------------------------------------------------
# 3. Star Schema ERD
# ---------------------------------------------------------------------
g3 = graphviz.Graph("star_schema", format="png")
g3.attr(fontname="Helvetica", fontsize="11", bgcolor="white", pad="0.5",
        layout="dot", rankdir="TB", nodesep="0.8", ranksep="0.9")
g3.attr("node", fontname="Helvetica", fontsize="10", shape="none")

def table_html(title, fields, color):
    rows = "".join(
        f'<tr><td align="left"><font face="Helvetica" point-size="9">{f}</font></td></tr>'
        for f in fields
    )
    return f'''<
<table border="1" cellborder="0" cellspacing="0" cellpadding="4" bgcolor="white">
<tr><td bgcolor="{color}"><font face="Helvetica-Bold" point-size="11" color="white">{title}</font></td></tr>
{rows}
</table>>'''

g3.node("fact_sales", table_html("fact_sales", [
    "sales_key (PK)", "invoice_no", "date_key (FK)", "customer_key (FK)",
    "product_key (FK)", "country_key (FK)", "quantity", "unit_price",
    "line_total", "is_return"
], "#1E2761"))

g3.node("dim_date", table_html("dim_date", [
    "date_key (PK)", "full_date", "day_of_week", "month_number",
    "month_name", "quarter", "year", "is_weekend"
], "#2C5F2D"))

g3.node("dim_customer", table_html("dim_customer", [
    "customer_key (PK)", "customer_id", "country", "customer_segment",
    "first_purchase_date", "last_purchase_date", "total_orders", "is_active"
], "#2C5F2D"))

g3.node("dim_product", table_html("dim_product", [
    "product_key (PK)", "stock_code", "description", "unit_price_band"
], "#2C5F2D"))

g3.node("dim_country", table_html("dim_country", [
    "country_key (PK)", "country_name", "region"
], "#2C5F2D"))

g3.attr("edge", color="#888888", fontname="Helvetica", fontsize="8")

with g3.subgraph(name="rank_top") as s:
    s.attr(rank="same")
    s.node("dim_date")
    s.node("dim_country")

with g3.subgraph(name="rank_mid") as s:
    s.attr(rank="same")
    s.node("fact_sales")

with g3.subgraph(name="rank_bottom") as s:
    s.attr(rank="same")
    s.node("dim_customer")
    s.node("dim_product")

g3.edge("fact_sales", "dim_date", label="1:N")
g3.edge("fact_sales", "dim_customer", label="1:N")
g3.edge("fact_sales", "dim_product", label="1:N")
g3.edge("fact_sales", "dim_country", label="1:N")

g3.render(f"{OUT}/fig_star_schema", cleanup=True)
print("Star schema ERD done")

# ---------------------------------------------------------------------
# 4. Research Onion (Methodology)
# ---------------------------------------------------------------------
g4 = graphviz.Digraph("methodology", format="png")
g4.attr(rankdir="TB", fontname="Helvetica", fontsize="11", bgcolor="white", pad="0.4")
g4.attr("node", fontname="Helvetica", fontsize="11", shape="box", style="rounded,filled", margin="0.25,0.15")
g4.attr("edge", style="invis")

g4.node("phil", "Research Philosophy:\nPragmatism", fillcolor="#E1F5EE", color="#0F6E56")
g4.node("approach", "Research Approach:\nDeductive", fillcolor="#CEDFF6", color="#185FA5")
g4.node("strategy", "Research Strategy:\nCase Study & System Design", fillcolor="#FDE7E1", color="#993C1D")
g4.node("choice", "Methodological Choice:\nMixed Methods\n(Quantitative + Qualitative)", fillcolor="#FBE8F0", color="#993556")
g4.node("horizon", "Time Horizon:\nCross-sectional", fillcolor="#F1EFE8", color="#5F5E5A")
g4.node("techniques", "Techniques & Procedures:\nSystem Implementation,\nPerformance Metrics,\nUser Evaluation", fillcolor="#FAEEDA", color="#854F0B")

g4.edge("phil", "approach")
g4.edge("approach", "strategy")
g4.edge("strategy", "choice")
g4.edge("choice", "horizon")
g4.edge("horizon", "techniques")

g4.render(f"{OUT}/fig_methodology", cleanup=True)
print("Methodology diagram done")
