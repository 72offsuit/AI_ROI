"""X5 RetailHero purchases.csv.gz(상품 라인 단위) -> 거래(transaction) 단위 parquet.
사용: python -I x5_purchases_to_tx.py <purchases.csv.gz> <out_tx.parquet>
purchase_sum은 거래 총액(라인마다 반복)이므로 transaction_id 단위로 max를 취함."""
import sys, time
import duckdb
src, out = sys.argv[1], sys.argv[2]
t = time.time()
con = duckdb.connect()
con.execute("PRAGMA threads=8")
con.execute(f"""
COPY (
  SELECT client_id, transaction_id,
         min(CAST(transaction_datetime AS TIMESTAMP)) AS ts,
         max(purchase_sum) AS purchase_sum,
         any_value(store_id) AS store_id,
         count(*) AS n_lines,
         sum(product_quantity) AS n_items,
         max(regular_points_spent) AS regular_points_spent,
         max(express_points_spent) AS express_points_spent,
         max(express_points_received) AS express_points_received
  FROM read_csv('{src}', header=true, auto_detect=true)
  GROUP BY client_id, transaction_id
) TO '{out}' (FORMAT PARQUET)
""")
n = con.execute(f"SELECT count(*), count(DISTINCT client_id), min(ts), max(ts) FROM '{out}'").fetchone()
print("tx rows, clients, min, max:", n, round(time.time() - t, 1), "s")
