from pathlib import Path

import pandas as pd

from warehouse import connect, query

ROOT = Path(__file__).resolve().parent.parent
SQL_FILE = ROOT / "sql" / "04_analysis.sql"
OUT_FILE = ROOT / "results" / "analysis_results.md"

SQL_TITLES = [
    "Raw rows loaded",
    "Clean fact rows: cancellations and guest (no customer_id) lines",
    "Which non-product stock codes were flagged as services, and how much revenue do they carry?",
    "Monthly KPIs (last month is partial)",
    "Year-over-year: Dec 2009-Nov 2010 vs Dec 2010-Nov 2011",
    "Top 10 products by net revenue",
    "Top 10 countries by net revenue",
    "When do orders happen? Orders by weekday and hour",
]


def to_markdown(df: pd.DataFrame) -> str:
    cols = [str(c) for c in df.columns]
    rows = [["" if pd.isna(v) else str(v) for v in row] for row in df.itertuples(index=False)]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def mom_growth(conn) -> pd.DataFrame:
    m = query(conn, "SELECT month, net_revenue FROM bi.monthly_kpis ORDER BY month")
    m["net_revenue"] = m.net_revenue.astype(float)
    m["mom_growth_pct"] = (100 * m.net_revenue.pct_change()).round(1)
    m["month"] = pd.to_datetime(m.month).dt.strftime("%Y-%m")
    m["net_revenue"] = m.net_revenue.round(0).astype(int)
    return m


def abc_summary(conn) -> pd.DataFrame:
    p = query(conn, "SELECT abc_class, net_revenue FROM bi.product_abc")
    p["net_revenue"] = p.net_revenue.astype(float)
    s = p.groupby("abc_class").agg(products=("net_revenue", "size"), revenue=("net_revenue", "sum")).reset_index()
    s["products_pct"] = (100 * s.products / s.products.sum()).round(1)
    s["revenue_pct"] = (100 * s.revenue / s.revenue.sum()).round(1)
    return s[["abc_class", "products", "products_pct", "revenue_pct"]]


def repeat_purchase(conn) -> pd.DataFrame:
    c = query(conn, "SELECT frequency FROM bi.customer_totals WHERE frequency > 0")
    repeat = int((c.frequency >= 2).sum())
    return pd.DataFrame([{
        "customers": len(c), "repeat_customers": repeat,
        "repeat_rate_pct": round(100 * repeat / len(c), 1), "median_orders": c.frequency.median(),
    }])


def order_gaps(conn) -> pd.DataFrame:
    o = query(conn, "SELECT customer_id, order_ts FROM bi.customer_orders ORDER BY customer_id, order_ts")
    gaps = (o.groupby("customer_id").order_ts.diff().dt.total_seconds() / 86400).dropna()
    return pd.DataFrame([{
        "gaps": len(gaps), "mean_days": round(gaps.mean(), 1),
        "median_days": round(gaps.median(), 1), "p90_days": round(gaps.quantile(0.9), 1),
    }])


def cohorts_2010(conn) -> pd.DataFrame:
    r = query(conn, """
        SELECT cohort_month, month_number, cohort_size, retention_rate
        FROM bi.cohort_retention
        WHERE cohort_month BETWEEN '2010-01-01' AND '2010-12-01'
    """)
    r["retention_rate"] = r.retention_rate.astype(float)
    wide = r.pivot(index="cohort_month", columns="month_number", values="retention_rate")
    out = pd.DataFrame({
        "cohort": pd.to_datetime(wide.index).strftime("%Y-%m"),
        "cohort_size": r.groupby("cohort_month").cohort_size.max().to_numpy(),
    })
    for k in (1, 3, 6):
        out[f"m{k}_pct"] = (100 * wide[k]).round(1).to_numpy()
    return out


def rfm_segments(conn) -> pd.DataFrame:
    c = query(conn, "SELECT segment, recency_days, frequency, monetary FROM bi.customer_rfm")
    c["monetary"] = c.monetary.astype(float)
    s = c.groupby("segment").agg(customers=("segment", "size"), revenue=("monetary", "sum"),
                                  avg_recency_days=("recency_days", "mean"),
                                  avg_orders=("frequency", "mean")).reset_index()
    s["customers_pct"] = (100 * s.customers / s.customers.sum()).round(1)
    s["revenue_pct"] = (100 * s.revenue / s.revenue.sum()).round(1)
    s["avg_recency_days"] = s.avg_recency_days.round(0).astype(int)
    s["avg_orders"] = s.avg_orders.round(1)
    s = s.sort_values("revenue_pct", ascending=False)
    return s[["segment", "customers", "customers_pct", "revenue_pct", "avg_recency_days", "avg_orders"]]


def customer_concentration(conn) -> pd.DataFrame:
    c = query(conn, "SELECT customer_id, monetary FROM bi.customer_rfm")
    m = c.monetary.astype(float).sort_values(ascending=False).reset_index(drop=True)
    needed = int((m.cumsum() / m.sum() < 0.80).sum()) + 1
    return pd.DataFrame([{
        "customers_for_80pct": needed, "total_customers": len(m),
        "customers_pct": round(100 * needed / len(m), 1),
    }])


PY_SECTIONS = [
    ("Net revenue month-over-month growth (Pandas)", mom_growth),
    ("ABC classes: how concentrated is product revenue? (Pandas)", abc_summary),
    ("Repeat purchase: share of customers with 2+ orders (Pandas)", repeat_purchase),
    ("Typical gap between consecutive orders of the same customer, days (Pandas)", order_gaps),
    ("Retention after 1, 3 and 6 months by cohort, 2010 cohorts (Pandas)", cohorts_2010),
    ("RFM segments: size and revenue share (Pandas)", rfm_segments),
    ("Customer concentration: what share of customers makes 80% of revenue? (Pandas)", customer_concentration),
]


def main() -> None:
    queries = [q.strip() for q in SQL_FILE.read_text(encoding="utf-8").split(";") if q.strip()]
    if len(queries) != len(SQL_TITLES):
        raise SystemExit(f"{len(queries)} queries in {SQL_FILE.name}, but {len(SQL_TITLES)} titles")

    conn = connect()
    out = ["# Analysis results", "",
           "Generated by `scripts/04_run_analysis.py`: SQL queries from `sql/04_analysis.sql`, "
           "then Pandas calculations on top of the `bi` views.", ""]
    sections = [(t, lambda c, q=q: query(c, q)) for t, q in zip(SQL_TITLES, queries)] + PY_SECTIONS
    for title, fn in sections:
        df = fn(conn)
        out += [f"## {title}", "", to_markdown(df), ""]
        print(f"\n== {title}\n{df.to_string(index=False)}")
    conn.close()
    OUT_FILE.parent.mkdir(exist_ok=True)
    OUT_FILE.write_text("\n".join(out), encoding="utf-8")
    print(f"\nwritten {OUT_FILE}")


if __name__ == "__main__":
    main()
