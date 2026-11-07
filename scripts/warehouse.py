import io
import os

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras

DB_NAME = "retail"
DB_USER = os.environ.get("PGUSER", "postgres")


def connect(dbname: str = DB_NAME):
    return psycopg2.connect(dbname=dbname, user=DB_USER)


def query(conn, sql: str) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql)
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


def copy_df(conn, df: pd.DataFrame, table: str) -> None:
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False)
    buf.seek(0)
    with conn.cursor() as cur:
        cur.copy_expert(f"COPY {table} ({', '.join(df.columns)}) FROM STDIN WITH (FORMAT csv)", buf)


def build_dim_date(conn) -> pd.DataFrame:
    bounds = query(conn, """
        SELECT min(invoice_date)::date AS first_day, max(invoice_date)::date AS last_day
        FROM staging.raw_transactions
        WHERE invoice ~ '^C?[0-9]+$' AND price > 0 AND quantity <> 0
    """).iloc[0]
    days = pd.date_range(bounds.first_day, bounds.last_day, freq="D")
    return pd.DataFrame({
        "date_key": days.date,
        "year": days.year,
        "quarter": days.quarter,
        "month": days.month,
        "month_start": days.to_period("M").to_timestamp().date,
        "month_name": days.strftime("%b"),
        "iso_week": days.isocalendar().week.to_numpy(),
        "day_of_week": days.dayofweek + 1,
        "day_name": days.strftime("%a"),
        "is_weekend": days.dayofweek >= 5,
    })


def most_frequent(df: pd.DataFrame, key: str, value: str) -> pd.DataFrame:
    df = df.dropna(subset=[value]).sort_values([key, "n", value], ascending=[True, False, True])
    return df.drop_duplicates(key)[[key, value]]


def apply_most_frequent_values(conn) -> None:
    desc = most_frequent(query(conn, """
        SELECT stock_code, description, count(*) AS n
        FROM clean
        GROUP BY stock_code, description
    """), "stock_code", "description")
    country = most_frequent(query(conn, """
        SELECT customer_id, country, count(*) AS n
        FROM clean
        WHERE customer_id IS NOT NULL
        GROUP BY customer_id, country
    """), "customer_id", "country")
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, "UPDATE dw.dim_product SET description = %s WHERE stock_code = %s",
                                      list(zip(desc.description, desc.stock_code)), page_size=1000)
        psycopg2.extras.execute_batch(cur, "UPDATE dw.dim_customer SET country = %s WHERE customer_id = %s",
                                      [(c, int(i)) for c, i in zip(country.country, country.customer_id)],
                                      page_size=1000)


def build_cohort_retention(conn) -> pd.DataFrame:
    act = query(conn, "SELECT customer_id, cohort_month, month FROM bi.customer_activity")
    cohort = pd.to_datetime(act.cohort_month)
    month = pd.to_datetime(act.month)
    act["month_number"] = (month.dt.year - cohort.dt.year) * 12 + (month.dt.month - cohort.dt.month)
    counts = (act.groupby(["cohort_month", "month_number"]).customer_id.nunique()
              .rename("active_customers").reset_index())
    size = counts[counts.month_number == 0].set_index("cohort_month").active_customers
    counts["cohort_size"] = counts.cohort_month.map(size)
    counts["retention_rate"] = (counts.active_customers / counts.cohort_size).round(4)
    return counts


def ntile(values: pd.Series, n: int, ascending: bool) -> pd.Series:
    order = values.sort_values(ascending=ascending, kind="stable").index
    total = len(order)
    sizes = [total // n + (1 if i < total % n else 0) for i in range(n)]
    buckets = np.repeat(np.arange(1, n + 1), sizes)
    return pd.Series(buckets, index=order).reindex(values.index)


def segment(r: int, f: int) -> str:
    if r >= 4 and f >= 4:
        return "Champions"
    if r >= 3 and f >= 3:
        return "Loyal"
    if r >= 4 and f <= 2:
        return "New / Promising"
    if r <= 2 and f >= 3:
        return "At Risk"
    if r <= 2 and f <= 2:
        return "Lost"
    return "Need Attention"


def build_customer_rfm(conn) -> pd.DataFrame:
    cust = query(conn, """
        SELECT customer_id, country, cohort_month, last_order_date, frequency, monetary
        FROM bi.customer_totals
        WHERE frequency > 0 AND monetary > 0
    """)
    last_day = query(conn, "SELECT max(date_key) AS last_day FROM dw.fact_sales").last_day[0]
    cust["recency_days"] = (pd.to_datetime(last_day) + pd.Timedelta(days=1)
                            - pd.to_datetime(cust.last_order_date)).dt.days
    cust["r_score"] = ntile(cust.recency_days, 5, ascending=False)
    cust["f_score"] = ntile(cust.frequency, 5, ascending=True)
    cust["m_score"] = ntile(cust.monetary.astype(float), 5, ascending=True)
    cust["segment"] = [segment(r, f) for r, f in zip(cust.r_score, cust.f_score)]
    return cust[["customer_id", "recency_days", "frequency", "monetary", "r_score", "f_score",
                 "m_score", "country", "cohort_month", "segment"]]


def build_product_abc(conn) -> pd.DataFrame:
    prod = query(conn, "SELECT stock_code, description, net_revenue, net_units, orders FROM bi.product_totals")
    prod["net_revenue"] = prod.net_revenue.astype(float)
    prod = prod.sort_values(["net_revenue", "stock_code"], ascending=[False, True]).reset_index(drop=True)
    prod["revenue_rank"] = prod.net_revenue.rank(method="min", ascending=False).astype(int)
    prod["cumulative_share"] = (prod.net_revenue.cumsum() / prod.net_revenue.sum()).round(6)
    prod["abc_class"] = np.select([prod.cumulative_share <= 0.80, prod.cumulative_share <= 0.95], ["A", "B"], "C")
    return prod
