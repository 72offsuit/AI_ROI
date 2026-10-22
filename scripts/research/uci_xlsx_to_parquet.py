"""UCI Online Retail II xlsx(2개 시트) -> parquet 캐시 변환. 사용: python -I uci_xlsx_to_parquet.py <xlsx> <out.parquet>"""
import sys, time
import pandas as pd
src, out = sys.argv[1], sys.argv[2]
t = time.time()
sheets = pd.read_excel(src, sheet_name=None, engine="openpyxl",
                       dtype={"Invoice": str, "StockCode": str, "Description": str, "Country": str})
parts = []
for name, df in sheets.items():
    df["sheet"] = name
    parts.append(df)
    print(name, df.shape, df["InvoiceDate"].min(), df["InvoiceDate"].max(), flush=True)
df = pd.concat(parts, ignore_index=True)
df.to_parquet(out, index=False)
print("done", df.shape, round(time.time() - t, 1), "s")
