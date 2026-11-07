import sys
import pandas as pd

def main(path: str) -> None:
    df = pd.read_csv(path, dtype={"invoice": str, "stock_code": str}, parse_dates=["invoice_date"])
    n = len(df)
    print(f"rows: {n:,}")
    print(f"period: {df.invoice_date.min()} .. {df.invoice_date.max()}")
    print("\nmissing values:")
    print(df.isna().sum().to_string())
    print(f"\nfull duplicate rows: {df.duplicated().sum():,}")
    cancel = df.invoice.str.startswith("C")
    print(f"cancellation lines (invoice starts with C): {cancel.sum():,}")
    print(f"other non-numeric invoices: {(~df.invoice.str.isdigit() & ~cancel).sum():,}")
    print(f"quantity <= 0: {(df.quantity <= 0).sum():,}   price <= 0: {(df.price <= 0).sum():,}")
    print(f"customers: {df.customer_id.nunique():,}   products: {df.stock_code.nunique():,}   "
          f"countries: {df.country.nunique()}")
    odd = df.loc[~df.stock_code.str.match(r"^\d{5}"), "stock_code"].value_counts().head(15)
    print("\nnon-product stock codes (top 15):")
    print(odd.to_string())
    print(f"\nmax description length: {df.description.str.len().max()}")
    print(f"max stock_code length: {df.stock_code.str.len().max()}")
    print(f"max invoice length: {df.invoice.str.len().max()}")
    print(f"max country length: {df.country.str.len().max()}")
    print(f"stock codes with >1 description: {(df.groupby('stock_code').description.nunique() > 1).sum():,}")

if __name__ == "__main__":
    main(sys.argv[1])
