import sys
import time
from pathlib import Path

from warehouse import (DB_NAME, apply_most_frequent_values, build_cohort_retention, build_customer_rfm,
                       build_dim_date, build_product_abc, connect, copy_df)

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def ensure_database() -> None:
    conn = connect("postgres")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
        if cur.fetchone() is None:
            cur.execute(f"CREATE DATABASE {DB_NAME}")
            print(f"created database {DB_NAME}")
    conn.close()


def run_sql_file(conn, name: str) -> None:
    t = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute((SQL_DIR / name).read_text(encoding="utf-8"))
    print(f"{name}: {time.perf_counter() - t:.1f}s")


def load_table(conn, df, table: str) -> None:
    t = time.perf_counter()
    copy_df(conn, df, table)
    print(f"{table}: {len(df):,} rows, {time.perf_counter() - t:.1f}s")


def main(csv_path: str) -> None:
    ensure_database()
    conn = connect()
    with conn:
        run_sql_file(conn, "01_schema.sql")
        with conn.cursor() as cur, open(csv_path, encoding="utf-8") as f:
            t = time.perf_counter()
            cur.copy_expert("COPY staging.raw_transactions FROM STDIN WITH (FORMAT csv, HEADER true)", f)
            print(f"staging.raw_transactions: {cur.rowcount:,} rows, {time.perf_counter() - t:.1f}s")
        load_table(conn, build_dim_date(conn), "dw.dim_date")
        run_sql_file(conn, "02_transform.sql")
        apply_most_frequent_values(conn)
        run_sql_file(conn, "03_views.sql")
        load_table(conn, build_cohort_retention(conn), "bi.cohort_retention")
        load_table(conn, build_customer_rfm(conn), "bi.customer_rfm")
        load_table(conn, build_product_abc(conn), "bi.product_abc")
        with conn.cursor() as cur:
            for table in ("dw.dim_product", "dw.dim_customer", "dw.fact_sales"):
                cur.execute(f"SELECT count(*) FROM {table}")
                print(f"{table}: {cur.fetchone()[0]:,} rows")
    conn.close()


if __name__ == "__main__":
    main(sys.argv[1])
