import sys
import pandas as pd

def main(src: str, dst: str) -> None:
    sheets = pd.read_excel(src, sheet_name=None, dtype={"Invoice": str, "StockCode": str})
    df = pd.concat(sheets.values(), ignore_index=True)
    df.columns = ["invoice", "stock_code", "description", "quantity",
                  "invoice_date", "price", "customer_id", "country"]
    df["customer_id"] = df["customer_id"].astype("Int64")
    df.to_csv(dst, index=False, date_format="%Y-%m-%d %H:%M:%S")
    print(f"sheets: {list(sheets)}")
    print(f"rows written: {len(df):,} -> {dst}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
