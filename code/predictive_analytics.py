"""
predictive_analytics.py
------------------------
Predictive-analytics extension for the CIDW prototype. Complements the
descriptive analytics (RFM segmentation, dashboards) with three linked
techniques that operate on the loaded warehouse:

  1. K-Means Clustering  - unsupervised discovery of natural customer groups
     from the RFM (Recency, Frequency, Monetary) feature space, chosen
     without prior labels. The optimal number of clusters is selected via
     the silhouette score (Rousseeuw, 1987).

  2. Random Forest Classification - supervised prediction of churn risk
     from the customer's behavioural features. A customer is labelled as
     churned when their recency exceeds 90 days.

  3. Explainable AI (XAI) - global (permutation) feature importance and
     per-customer prediction reasoning, so a manager can act on WHY a
     customer is flagged rather than just the label. Rationale: SHAP is not
     available in this environment; permutation importance (Fisher, Rudin
     & Dominici, 2019, JMLR) provides a model-agnostic, defensible
     alternative rooted in the same literature.

The module reads from the SQLite warehouse produced by etl_pipeline_demo.py
and writes visualisations and a churn-risk CSV that a marketing team can
act on directly.

Author: Alexander Ugochukwu Ejiogu (Student No. 35038543)
"""

import json
import sqlite3
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (silhouette_score, precision_score, recall_score,
                              f1_score, roc_auc_score, confusion_matrix,
                              classification_report)
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance

warnings.filterwarnings("ignore", category=UserWarning)

DB_PATH = "../data/cidw_dw.sqlite"
OUT_IMG = "../images"
OUT_DATA = "../data"

# Colour palette matching the rest of the prototype
NAVY, DEEP, TEAL, MINT, ACCENT = "#21295C", "#065A82", "#1C7293", "#028090", "#B85042"


def load_customer_features(conn: sqlite3.Connection) -> pd.DataFrame:
    """Build per-customer feature frame from fact_sales and dim_customer."""
    sql = """
    WITH per_cust AS (
        SELECT
            dc.customer_key,
            dc.customer_id,
            dc.customer_segment,
            dc.country,
            MAX(CASE WHEN f.is_return = 0 THEN dd.full_date END) AS last_purchase,
            MIN(CASE WHEN f.is_return = 0 THEN dd.full_date END) AS first_purchase,
            COUNT(DISTINCT CASE WHEN f.is_return = 0 THEN f.invoice_no END) AS frequency,
            COALESCE(SUM(CASE WHEN f.is_return = 0 THEN f.line_total END), 0.0) AS monetary,
            COUNT(DISTINCT CASE WHEN f.is_return = 1 THEN f.invoice_no END) AS return_count
        FROM dim_customer dc
        LEFT JOIN fact_sales f ON dc.customer_key = f.customer_key
        LEFT JOIN dim_date dd ON f.date_key = dd.date_key
        WHERE dc.customer_id != 'GUEST'
        GROUP BY dc.customer_key, dc.customer_id, dc.customer_segment, dc.country
    ),
    dataset_bounds AS (
        SELECT MAX(full_date) AS ref_date FROM dim_date
    )
    SELECT p.*, b.ref_date FROM per_cust p, dataset_bounds b
    """
    df = pd.read_sql(sql, conn, parse_dates=["last_purchase", "first_purchase", "ref_date"])
    df = df[df["frequency"] > 0].copy()

    df["recency_days"] = (df["ref_date"] - df["last_purchase"]).dt.days
    df["tenure_days"] = (df["ref_date"] - df["first_purchase"]).dt.days.clip(lower=0)
    df["avg_order_value"] = df["monetary"] / df["frequency"].clip(lower=1)
    df["return_rate"] = df["return_count"] / (df["frequency"] + df["return_count"]).clip(lower=1)

    keep = ["customer_key", "customer_id", "customer_segment", "country",
            "recency_days", "frequency", "monetary", "tenure_days",
            "avg_order_value", "return_rate"]
    return df[keep].reset_index(drop=True)


def cluster_customers(df: pd.DataFrame, k_range=(2, 8), random_state=42):
    features = ["recency_days", "frequency", "monetary"]
    X = df[features].copy()
    X["monetary"] = np.log1p(X["monetary"])
    X_scaled = StandardScaler().fit_transform(X)

    sil_scores, inertias = [], []
    for k in range(k_range[0], k_range[1] + 1):
        km = KMeans(n_clusters=k, random_state=random_state, n_init=10)
        labels = km.fit_predict(X_scaled)
        sil_scores.append(silhouette_score(X_scaled, labels))
        inertias.append(km.inertia_)

    k_best = int(np.argmax(sil_scores)) + k_range[0]
    km = KMeans(n_clusters=k_best, random_state=random_state, n_init=10)
    df["cluster"] = km.fit_predict(X_scaled)

    print(f"K-Means: silhouette-optimal k = {k_best} (score = {max(sil_scores):.3f})")
    return df, {"k_range": list(range(k_range[0], k_range[1] + 1)),
                "silhouettes": sil_scores, "inertias": inertias,
                "k_best": k_best, "best_score": max(sil_scores)}


def plot_kmeans_diagnostics(diag: dict, out_path: str):
    fig, ax1 = plt.subplots(figsize=(9, 5))
    ax2 = ax1.twinx()
    ks = diag["k_range"]
    ax1.plot(ks, diag["inertias"], marker="o", color=DEEP, label="Inertia (elbow)")
    ax2.plot(ks, diag["silhouettes"], marker="s", color=ACCENT, label="Silhouette")
    ax1.axvline(diag["k_best"], linestyle="--", color="grey", alpha=0.5)
    ax1.set_xlabel("Number of clusters (k)")
    ax1.set_ylabel("Inertia", color=DEEP)
    ax2.set_ylabel("Silhouette score", color=ACCENT)
    plt.title(f"K-Means diagnostics \u2014 optimal k = {diag['k_best']}",
              fontsize=13, fontweight="bold")
    ax1.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def plot_cluster_scatter(df: pd.DataFrame, out_path: str):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    palette = sns.color_palette("Set2", df["cluster"].nunique())

    sns.scatterplot(data=df, x="recency_days", y="monetary", hue="cluster",
                    palette=palette, alpha=0.65, s=45, ax=axes[0], legend="full")
    axes[0].set_title("Clusters in Recency \u00D7 Monetary space",
                      fontsize=12, fontweight="bold")
    axes[0].set_xlabel("Recency (days since last purchase)")
    axes[0].set_ylabel("Monetary value (\u00A3)")

    sns.scatterplot(data=df, x="frequency", y="monetary", hue="cluster",
                    palette=palette, alpha=0.65, s=45, ax=axes[1], legend="full")
    axes[1].set_title("Clusters in Frequency \u00D7 Monetary space",
                      fontsize=12, fontweight="bold")
    axes[1].set_xlabel("Frequency (distinct orders)")
    axes[1].set_ylabel("Monetary value (\u00A3)")

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def cluster_profile(df: pd.DataFrame) -> pd.DataFrame:
    prof = (df.groupby("cluster")
              .agg(customers=("customer_key", "count"),
                   recency_days=("recency_days", "median"),
                   frequency=("frequency", "median"),
                   monetary=("monetary", "median"),
                   avg_order_value=("avg_order_value", "median"))
              .round(2))
    return prof


def train_churn_classifier(df: pd.DataFrame,
                           churn_days: int = 90,
                           random_state: int = 42):
    df = df.copy()
    df["churned"] = (df["recency_days"] > churn_days).astype(int)

    # Recency AND tenure_days excluded to avoid target leakage:
    # in the synthetic dataset, tenure and recency are near-perfectly
    # correlated because the generator draws both from the same
    # segment-based ranges, giving the model unrealistic access to the
    # target. The model must learn from genuine behavioural signal only.
    feature_cols = ["frequency", "monetary",
                    "avg_order_value", "return_rate"]
    X = df[feature_cols].values
    y = df["churned"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=random_state, stratify=y
    )

    clf = RandomForestClassifier(
        n_estimators=200, max_depth=6, min_samples_leaf=5,
        class_weight="balanced", random_state=random_state, n_jobs=-1
    )
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    y_proba = clf.predict_proba(X_test)[:, 1]

    metrics = {
        "precision": precision_score(y_test, y_pred),
        "recall": recall_score(y_test, y_pred),
        "f1": f1_score(y_test, y_pred),
        "roc_auc": roc_auc_score(y_test, y_proba),
        "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
        "positive_class_rate_train": float(y_train.mean()),
        "positive_class_rate_test": float(y_test.mean()),
    }

    print("\nChurn classifier metrics (test set, held-out 25%):")
    print(classification_report(y_test, y_pred,
                                target_names=["Retained", "Churned"], digits=3))
    print(f"ROC-AUC = {metrics['roc_auc']:.3f}")

    return clf, feature_cols, X_test, y_test, y_pred, y_proba, metrics


def plot_confusion_matrix(metrics: dict, out_path: str):
    cm = np.array(metrics["confusion_matrix"])
    fig, ax = plt.subplots(figsize=(6.5, 5))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", cbar=False,
                xticklabels=["Retained", "Churned"],
                yticklabels=["Retained", "Churned"], ax=ax)
    ax.set_title(f"Churn classifier confusion matrix\n"
                 f"F1 = {metrics['f1']:.3f}    ROC-AUC = {metrics['roc_auc']:.3f}",
                 fontsize=12, fontweight="bold")
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def explain_classifier(clf, feature_cols, X_test, y_test, random_state=42):
    impurity_imp = pd.Series(clf.feature_importances_, index=feature_cols).sort_values()

    perm = permutation_importance(clf, X_test, y_test,
                                  n_repeats=20, random_state=random_state, n_jobs=-1)
    perm_df = pd.DataFrame({
        "feature": feature_cols,
        "importance_mean": perm.importances_mean,
        "importance_std": perm.importances_std,
    }).sort_values("importance_mean")

    print("\nGlobal feature importance (permutation, 20 repeats):")
    print(perm_df.to_string(index=False))
    return impurity_imp, perm_df


def plot_feature_importance(impurity_imp, perm_df, out_path: str):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    axes[0].barh(impurity_imp.index, impurity_imp.values, color=DEEP)
    axes[0].set_title("Impurity-based importance (Random Forest built-in)",
                      fontsize=11, fontweight="bold")
    axes[0].set_xlabel("Importance")

    axes[1].barh(perm_df["feature"], perm_df["importance_mean"],
                 xerr=perm_df["importance_std"], color=ACCENT,
                 error_kw={"elinewidth": 1.2, "capsize": 3})
    axes[1].set_title("Permutation importance (\u00B11 SD over 20 repeats)",
                      fontsize=11, fontweight="bold")
    axes[1].set_xlabel("Mean decrease in accuracy")

    plt.suptitle("Explainable AI: what drives the churn prediction?",
                 fontsize=13, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()


def per_customer_reasons(df_features: pd.DataFrame, clf, feature_cols,
                         perm_df: pd.DataFrame, top_n: int = 20,
                         out_csv: str = None):
    """Score every customer and produce plain-English risk reasons."""
    X_all = df_features[feature_cols].values
    proba = clf.predict_proba(X_all)[:, 1]
    df = df_features.copy()
    df["churn_probability"] = proba

    def explain_row(row):
        parts = []
        if row["recency_days"] > 90:
            parts.append(f"has not purchased for {int(row['recency_days'])} days")
        if row["frequency"] <= 2:
            parts.append(f"only {int(row['frequency'])} order(s) on record")
        if row["monetary"] < df_features["monetary"].median():
            parts.append("below-median spend")
        if row["tenure_days"] < df_features["tenure_days"].median():
            parts.append("short customer tenure")
        return "; ".join(parts) if parts else "borderline profile"

    df["risk_reason"] = df.apply(explain_row, axis=1)
    at_risk = df.sort_values("churn_probability", ascending=False).head(top_n)

    if out_csv:
        cols = ["customer_id", "customer_segment", "country", "churn_probability",
                "recency_days", "frequency", "monetary", "risk_reason"]
        at_risk[cols].to_csv(out_csv, index=False)
    return at_risk


def plot_top_risk_customers(at_risk: pd.DataFrame, out_path: str):
    fig, ax = plt.subplots(figsize=(11, 6))
    top = at_risk.head(15).sort_values("churn_probability")
    ax.barh([f"ID {cid}" for cid in top["customer_id"].astype(str)],
            top["churn_probability"], color=ACCENT)
    ax.set_xlim(0, 1)
    ax.set_xlabel("Predicted churn probability")
    ax.set_title("Top 15 customers ranked by churn risk",
                 fontsize=13, fontweight="bold")
    for i, (_, row) in enumerate(top.iterrows()):
        ax.text(row["churn_probability"] + 0.01, i,
                f" {row['risk_reason'][:55]}",
                va="center", fontsize=8, color="#333333")
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()


def main():
    Path(OUT_IMG).mkdir(parents=True, exist_ok=True)
    Path(OUT_DATA).mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    try:
        df = load_customer_features(conn)
        print(f"Loaded {len(df):,} customers with purchase history")

        df_clustered, diag = cluster_customers(df)
        plot_kmeans_diagnostics(diag, f"{OUT_IMG}/chart_kmeans_diagnostics.png")
        plot_cluster_scatter(df_clustered, f"{OUT_IMG}/chart_kmeans_clusters.png")
        profile = cluster_profile(df_clustered)
        print("\nCluster profiles (medians):")
        print(profile)

        ct = pd.crosstab(df_clustered["cluster"], df_clustered["customer_segment"])
        print("\nCluster \u00D7 rule-based segment contingency:")
        print(ct)

        clf, feats, X_te, y_te, y_pred, y_proba, metrics = train_churn_classifier(df_clustered)
        plot_confusion_matrix(metrics, f"{OUT_IMG}/chart_churn_confusion.png")

        impurity_imp, perm_df = explain_classifier(clf, feats, X_te, y_te)
        plot_feature_importance(impurity_imp, perm_df,
                                f"{OUT_IMG}/chart_churn_importance.png")

        at_risk = per_customer_reasons(
            df_clustered, clf, feats, perm_df,
            top_n=50, out_csv=f"{OUT_DATA}/high_risk_customers.csv"
        )
        plot_top_risk_customers(at_risk, f"{OUT_IMG}/chart_churn_top_risks.png")

        with open(f"{OUT_DATA}/predictive_metrics.json", "w") as f:
            json.dump({
                "kmeans": {"k_best": diag["k_best"],
                           "silhouette": diag["best_score"],
                           "profiles": profile.to_dict("index")},
                "churn": metrics,
                "top_features": perm_df.to_dict("records"),
            }, f, indent=2, default=str)

        print("\nAll predictive-analytics outputs generated in ../images and ../data")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
