#!/usr/bin/env python3
"""
Import monthly revenue from FinMind PostgreSQL to CCStockWorkEnv SQLite.

Usage:
    python import_monthly_revenue.py           # Import all
    python import_monthly_revenue.py --ticker 2330  # Single stock
"""

import argparse
import sys
import time
import psycopg2
import psycopg2.extras
from db_manager import get_connection, DB_PATH

PG_CONFIG = {
    "host": "localhost", "port": 5432,
    "database": "tw_stock", "user": "user", "password": "password",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="Import single stock only")
    args = parser.parse_args()

    pg = psycopg2.connect(**PG_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)
    cur = pg.cursor()

    query = """
        SELECT stock_id, year, month, revenue,
               diff_percent AS yoy_pct,
               diff_percent_mon AS mom_pct,
               current_year_cumulative AS cum_revenue,
               cumulative_diff_percent AS cum_yoy_pct
        FROM monthly_revenue
    """
    params = []
    if args.ticker:
        query += " WHERE stock_id = %s"
        params.append(args.ticker)
    query += " ORDER BY stock_id, year, month"

    cur.execute(query, params)
    rows = cur.fetchall()
    pg.close()

    print(f"從 PostgreSQL 讀取 {len(rows):,} 筆月營收資料")

    sqlite = get_connection()
    batch_size = 2000
    inserted = 0
    t0 = time.time()

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        sqlite.executemany("""
            INSERT OR REPLACE INTO monthly_revenue
            (ticker, market, year, month, revenue, yoy_pct, mom_pct, cum_revenue, cum_yoy_pct)
            VALUES (?, 'TW', ?, ?, ?, ?, ?, ?, ?)
        """, [
            (r["stock_id"], r["year"], r["month"], r["revenue"],
             r["yoy_pct"], r["mom_pct"], r["cum_revenue"], r["cum_yoy_pct"])
            for r in batch
        ])
        sqlite.commit()
        inserted += len(batch)
        if inserted % 20000 == 0 or inserted == len(rows):
            print(f"  [{inserted:,}/{len(rows):,}] {time.time()-t0:.1f}s")

    sqlite.close()
    print(f"✅ 完成！共匯入 {inserted:,} 筆，耗時 {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
