#!/usr/bin/env python3
"""
Import Taiwan stock data from FinMind PostgreSQL to CCStockWorkEnv SQLite.

Usage:
    python import_from_finmind.py --all                    # Import all data types
    python import_from_finmind.py --stocks                 # Stock info only
    python import_from_finmind.py --prices --days 365      # Last 365 days of prices
    python import_from_finmind.py --financials             # Financial reports
    python import_from_finmind.py --scores                 # Health scores
    python import_from_finmind.py --ticker 2330            # Specific stock only
    python import_from_finmind.py --dry-run                # Preview without writing

Prerequisites:
    uv pip install psycopg2-binary
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from typing import Optional

import psycopg2
import psycopg2.extras

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "tool_scripts", "db_ops"))

from db_manager import get_connection, DB_PATH

# FinMind PostgreSQL connection
PG_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "tw_stock",
    "user": "user",
    "password": "password",
}


def get_pg_connection():
    """Get PostgreSQL connection."""
    return psycopg2.connect(**PG_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)


def import_stock_info(sqlite_conn, pg_conn, ticker: Optional[str] = None, dry_run: bool = False):
    """Import stock info from stock_info → stocks."""
    print("\n📊 Importing stock info...")
    pg_cursor = pg_conn.cursor()

    # Build query
    query = """
        SELECT id, name, industry, listed_type, stock_type, delisted
        FROM stock_info
        WHERE delisted = false
    """
    params = []
    if ticker:
        query += " AND id = %s"
        params.append(ticker)
    query += " ORDER BY id"

    pg_cursor.execute(query, params)
    rows = pg_cursor.fetchall()

    print(f"  Found {len(rows)} stocks in PostgreSQL")

    if dry_run:
        print("  [DRY RUN] Would insert:")
        for i, row in enumerate(rows[:5]):
            print(f"    {row['id']} - {row['name']} ({row['industry']})")
        if len(rows) > 5:
            print(f"    ... and {len(rows) - 5} more")
        return

    # Insert into SQLite
    inserted = 0
    updated = 0
    for row in rows:
        try:
            sqlite_conn.execute(
                """
                INSERT INTO stocks (ticker, market, name, sector, industry, exchange, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, market) DO UPDATE SET
                    name = excluded.name,
                    sector = excluded.sector,
                    industry = excluded.industry,
                    exchange = excluded.exchange,
                    is_active = excluded.is_active,
                    updated_at = datetime('now')
                """,
                (
                    row["id"],
                    "TW",
                    row["name"],
                    row["industry"],  # Use industry as sector
                    row["industry"],
                    row["listed_type"],  # TWSE or TPEx
                    0 if row["delisted"] else 1,
                ),
            )
            if sqlite_conn.total_changes > 0:
                inserted += 1
        except sqlite3.IntegrityError:
            updated += 1

    sqlite_conn.commit()
    print(f"  ✅ Inserted: {inserted}, Updated: {updated}")


def import_daily_prices(
    sqlite_conn,
    pg_conn,
    ticker: Optional[str] = None,
    days: Optional[int] = None,
    dry_run: bool = False,
):
    """Import daily prices from daily_price → daily_prices."""
    print("\n📈 Importing daily prices...")
    pg_cursor = pg_conn.cursor()

    # Build query
    query = """
        SELECT stock_id, date, open, high, low, close, volume
        FROM daily_price
        WHERE 1=1
    """
    params = []

    if ticker:
        query += " AND stock_id = %s"
        params.append(ticker)

    if days:
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        query += " AND date >= %s"
        params.append(cutoff_date)

    query += " ORDER BY stock_id, date"

    pg_cursor.execute(query, params)
    rows = pg_cursor.fetchall()

    print(f"  Found {len(rows):,} price records in PostgreSQL")

    if dry_run:
        print("  [DRY RUN] Would insert:")
        for i, row in enumerate(rows[:5]):
            print(f"    {row['stock_id']} {row['date']} close={row['close']}")
        if len(rows) > 5:
            print(f"    ... and {len(rows) - 5:,} more")
        return

    # Batch insert
    batch_size = 1000
    inserted = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        sqlite_conn.executemany(
            """
            INSERT OR IGNORE INTO daily_prices
            (ticker, market, date, open, high, low, close, volume, adj_close)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["stock_id"],
                    "TW",
                    row["date"].strftime("%Y-%m-%d"),
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row["volume"],
                    row["close"],  # adj_close = close for TW stocks
                )
                for row in batch
            ],
        )
        inserted += sqlite_conn.total_changes
        if (i // batch_size + 1) % 10 == 0:
            print(f"  Progress: {i + len(batch):,} / {len(rows):,}")

    sqlite_conn.commit()
    print(f"  ✅ Inserted: {inserted:,} new price records")


def import_financials(
    sqlite_conn, pg_conn, ticker: Optional[str] = None, dry_run: bool = False
):
    """Import financial reports from financial_report + annual_financial_report → financials."""
    print("\n💰 Importing financial reports...")

    # Import quarterly reports
    print("  [Quarterly Reports]")
    pg_cursor = pg_conn.cursor()

    query = """
        SELECT stock_id, year, quarter, revenue, gross_margin, operating_margin,
               net_margin, eps, roe, free_cash_flow, revenue_yoy
        FROM financial_report
        WHERE 1=1
    """
    params = []
    if ticker:
        query += " AND stock_id = %s"
        params.append(ticker)
    query += " ORDER BY stock_id, year, quarter"

    pg_cursor.execute(query, params)
    quarterly_rows = pg_cursor.fetchall()

    print(f"    Found {len(quarterly_rows):,} quarterly reports")

    if not dry_run:
        inserted_q = 0
        for row in quarterly_rows:
            # Convert year/quarter to period_date (e.g., Q2 2024 → 2024-06-30)
            quarter_end_month = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
            period_date = f"{row['year']}-{quarter_end_month[row['quarter']]}"

            sqlite_conn.execute(
                """
                INSERT OR REPLACE INTO financials
                (ticker, market, period, period_date, revenue, net_income, eps,
                 gross_margin, operating_margin, net_margin, roe, fcf)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["stock_id"],
                    "TW",
                    "quarterly",
                    period_date,
                    row["revenue"],
                    row["revenue"] * (row["net_margin"] / 100) if row["net_margin"] else None,
                    row["eps"],
                    row["gross_margin"],
                    row["operating_margin"],
                    row["net_margin"],
                    row["roe"],
                    row["free_cash_flow"],
                ),
            )
            inserted_q += 1
        sqlite_conn.commit()
        print(f"    ✅ Inserted: {inserted_q:,} quarterly records")
    else:
        for i, row in enumerate(quarterly_rows[:3]):
            print(f"      {row['stock_id']} {row['year']}Q{row['quarter']} EPS={row['eps']}")
        if len(quarterly_rows) > 3:
            print(f"      ... and {len(quarterly_rows) - 3:,} more")

    # Import annual reports
    print("  [Annual Reports]")
    pg_cursor.execute(
        """
        SELECT stock_id, year, revenue, gross_margin, operating_margin,
               net_margin, eps, roe, free_cash_flow, revenue_yoy
        FROM annual_financial_report
        {}
        ORDER BY stock_id, year
        """.format("WHERE stock_id = %s" if ticker else ""),
        [ticker] if ticker else [],
    )
    annual_rows = pg_cursor.fetchall()

    print(f"    Found {len(annual_rows):,} annual reports")

    if not dry_run:
        inserted_a = 0
        for row in annual_rows:
            period_date = f"{row['year']}-12-31"

            sqlite_conn.execute(
                """
                INSERT OR REPLACE INTO financials
                (ticker, market, period, period_date, revenue, net_income, eps,
                 gross_margin, operating_margin, net_margin, roe, fcf)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["stock_id"],
                    "TW",
                    "annual",
                    period_date,
                    row["revenue"],
                    row["revenue"] * (row["net_margin"] / 100) if row["net_margin"] else None,
                    row["eps"],
                    row["gross_margin"],
                    row["operating_margin"],
                    row["net_margin"],
                    row["roe"],
                    row["free_cash_flow"],
                ),
            )
            inserted_a += 1
        sqlite_conn.commit()
        print(f"    ✅ Inserted: {inserted_a:,} annual records")
    else:
        for i, row in enumerate(annual_rows[:3]):
            print(f"      {row['stock_id']} {row['year']} EPS={row['eps']}")
        if len(annual_rows) > 3:
            print(f"      ... and {len(annual_rows) - 3:,} more")


def import_health_scores(
    sqlite_conn, pg_conn, ticker: Optional[str] = None, dry_run: bool = False
):
    """Import health scores from stock_score_cache → research_cache."""
    print("\n🏥 Importing health scores...")
    pg_cursor = pg_conn.cursor()

    query = """
        SELECT stock_id, quality_score, financial_health_score, revenue_health_score,
               dividend_health_score, fcf_health_score, composite_health_normalized,
               calculated_at
        FROM stock_score_cache
        WHERE 1=1
    """
    params = []
    if ticker:
        query += " AND stock_id = %s"
        params.append(ticker)

    pg_cursor.execute(query, params)
    rows = pg_cursor.fetchall()

    print(f"  Found {len(rows):,} score records")

    if dry_run:
        print("  [DRY RUN] Would insert as research_cache:")
        for i, row in enumerate(rows[:5]):
            print(
                f"    {row['stock_id']} quality={row['quality_score']:.1f} "
                f"composite={row['composite_health_normalized']:.1f}"
            )
        if len(rows) > 5:
            print(f"    ... and {len(rows) - 5:,} more")
        return

    # Store as JSON in research_cache
    inserted = 0
    for row in rows:
        data = {
            "quality_score": row["quality_score"],
            "financial_health_score": row["financial_health_score"],
            "revenue_health_score": row["revenue_health_score"],
            "dividend_health_score": row["dividend_health_score"],
            "fcf_health_score": row["fcf_health_score"],
            "composite_health_normalized": row["composite_health_normalized"],
            "calculated_at": row["calculated_at"].isoformat() if row["calculated_at"] else None,
        }

        sqlite_conn.execute(
            """
            INSERT OR REPLACE INTO research_cache
            (ticker, market, data_type, last_fetched_at, data_json, fetch_source)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                row["stock_id"],
                "TW",
                "health_scores_finmind",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                json.dumps(data, ensure_ascii=False),
                "finmind_postgresql",
            ),
        )
        inserted += 1

    sqlite_conn.commit()
    print(f"  ✅ Inserted: {inserted:,} health score records in research_cache")


def main():
    parser = argparse.ArgumentParser(
        description="Import Taiwan stock data from FinMind PostgreSQL to CCStockWorkEnv SQLite"
    )
    parser.add_argument("--all", action="store_true", help="Import all data types")
    parser.add_argument("--stocks", action="store_true", help="Import stock info")
    parser.add_argument("--prices", action="store_true", help="Import daily prices")
    parser.add_argument("--financials", action="store_true", help="Import financial reports")
    parser.add_argument("--scores", action="store_true", help="Import health scores")
    parser.add_argument("--ticker", type=str, help="Import specific stock only (e.g., 2330)")
    parser.add_argument(
        "--days", type=int, help="For --prices, limit to last N days (default: all)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--db", type=str, default=DB_PATH, help="SQLite database path")

    args = parser.parse_args()

    # Validate flags
    if not any([args.all, args.stocks, args.prices, args.financials, args.scores]):
        parser.print_help()
        print("\nError: Must specify at least one import option (--all, --stocks, --prices, etc.)")
        sys.exit(1)

    # Test PostgreSQL connection
    try:
        pg_conn = get_pg_connection()
        print(f"✅ Connected to FinMind PostgreSQL at {PG_CONFIG['host']}:{PG_CONFIG['port']}")
    except Exception as e:
        print(f"❌ Failed to connect to PostgreSQL: {e}")
        sys.exit(1)

    # Test SQLite connection
    try:
        sqlite_conn = get_connection(args.db)
        print(f"✅ Connected to SQLite at {args.db}")
    except Exception as e:
        print(f"❌ Failed to connect to SQLite: {e}")
        sys.exit(1)

    if args.dry_run:
        print("\n⚠️  DRY RUN MODE - No data will be written\n")

    # Import data
    try:
        if args.all or args.stocks:
            import_stock_info(sqlite_conn, pg_conn, ticker=args.ticker, dry_run=args.dry_run)

        if args.all or args.prices:
            import_daily_prices(
                sqlite_conn, pg_conn, ticker=args.ticker, days=args.days, dry_run=args.dry_run
            )

        if args.all or args.financials:
            import_financials(sqlite_conn, pg_conn, ticker=args.ticker, dry_run=args.dry_run)

        if args.all or args.scores:
            import_health_scores(sqlite_conn, pg_conn, ticker=args.ticker, dry_run=args.dry_run)

        print("\n✅ Import complete!")

    except Exception as e:
        print(f"\n❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        pg_conn.close()
        sqlite_conn.close()


if __name__ == "__main__":
    main()
