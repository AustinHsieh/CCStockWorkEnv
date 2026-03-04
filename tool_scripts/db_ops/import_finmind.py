#!/usr/bin/env python3
"""
Import data from FinMind PostgreSQL to CCStockWorkEnv SQLite.

Usage:
    # 先安裝依賴（一次性）
    cd tool_scripts/db_ops && uv pip install psycopg2-binary

    # 測試連線
    uv run python import_finmind.py --test

    # 匯入股票清單
    uv run python import_finmind.py --import-stocks

    # 匯入價格資料（指定股票和日期範圍）
    uv run python import_finmind.py --import-prices --ticker 2330 --start-date 2024-01-01

    # 匯入財報資料（指定股票）
    uv run python import_finmind.py --import-financials --ticker 2330

    # 批次匯入（所有資料）
    uv run python import_finmind.py --import-all --start-date 2024-01-01
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("❌ psycopg2 未安裝。請先執行：")
    print("   cd tool_scripts/db_ops && uv pip install psycopg2-binary")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
SQLITE_DB = os.path.join(PROJECT_ROOT, "data", "ccstockworkenv.db")

# PostgreSQL 連線設定
PG_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "tw_stock",
    "user": "user",
    "password": "password"
}


def get_pg_conn():
    """取得 PostgreSQL 連線"""
    return psycopg2.connect(**PG_CONFIG, cursor_factory=RealDictCursor)


def get_sqlite_conn():
    """取得 SQLite 連線"""
    conn = sqlite3.connect(SQLITE_DB)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def test_connection() -> bool:
    """測試 PostgreSQL 連線"""
    try:
        conn = get_pg_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT version()")
        version = cursor.fetchone()["version"]
        print(f"✅ PostgreSQL 連線成功")
        print(f"   版本: {version[:50]}...")

        # 檢查表格
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        tables = [row["table_name"] for row in cursor.fetchall()]
        print(f"   可用表格: {', '.join(tables)}")

        conn.close()
        return True
    except Exception as e:
        print(f"❌ PostgreSQL 連線失敗: {e}")
        return False


def import_stocks(limit: Optional[int] = None, stock_type: str = "Stock") -> int:
    """
    匯入股票清單

    FinMind schema:
      stock_info (id, name, industry, listed_type, stock_type, delisted)

    CCStock schema:
      stocks (ticker, market, name, sector, industry, currency, exchange, is_active)
    """
    pg_conn = get_pg_conn()
    sqlite_conn = get_sqlite_conn()

    query = """
        SELECT id, name, industry, listed_type, stock_type, delisted
        FROM stock_info
        WHERE delisted = false AND stock_type = %s
        ORDER BY id
    """
    if limit:
        query += f" LIMIT {limit}"

    cursor = pg_conn.cursor()
    print(f"🔍 查詢條件: stock_type='{stock_type}', delisted=false")
    cursor.execute(query, (stock_type,))
    stocks = cursor.fetchall()

    print(f"📥 從 FinMind 讀取到 {len(stocks)} 檔股票")

    inserted = 0
    skipped = 0

    for stock in stocks:
        ticker = stock["id"]
        name = stock["name"]
        industry = stock["industry"]
        listed_type = stock["listed_type"]  # TWSE/TPEx
        stock_type = stock["stock_type"]    # Stock/ETF/ETN/Index/Other

        # 映射到 CCStock schema
        sector = industry  # FinMind 的 industry 作為 sector
        exchange = listed_type  # TWSE/TPEx
        is_active = 1
        currency = "TWD"
        market = "TW"

        try:
            sqlite_conn.execute("""
                INSERT INTO stocks (ticker, market, name, sector, industry, currency, exchange, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, market) DO UPDATE SET
                    name = excluded.name,
                    sector = excluded.sector,
                    industry = excluded.industry,
                    updated_at = datetime('now')
            """, (ticker, market, name, sector, industry, currency, exchange, is_active))
            inserted += 1
        except Exception as e:
            print(f"⚠️  無法匯入 {ticker} {name}: {e}")
            skipped += 1

    sqlite_conn.commit()
    pg_conn.close()
    sqlite_conn.close()

    print(f"✅ 匯入完成: {inserted} 檔新增/更新, {skipped} 檔跳過")
    return inserted


def import_prices(ticker: str, start_date: str, end_date: Optional[str] = None) -> int:
    """
    匯入價格資料

    FinMind schema:
      daily_price (stock_id, date, open, high, low, close, volume, ma5, ma20)

    CCStock schema:
      daily_prices (ticker, market, date, open, high, low, close, volume, adj_close)
    """
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    pg_conn = get_pg_conn()
    sqlite_conn = get_sqlite_conn()

    cursor = pg_conn.cursor()
    cursor.execute("""
        SELECT stock_id, date, open, high, low, close, volume
        FROM daily_price
        WHERE stock_id = %s AND date >= %s AND date <= %s
        ORDER BY date
    """, (ticker, start_date, end_date))

    prices = cursor.fetchall()

    if not prices:
        print(f"⚠️  無資料: {ticker} ({start_date} ~ {end_date})")
        pg_conn.close()
        sqlite_conn.close()
        return 0

    print(f"📥 從 FinMind 讀取到 {ticker} 的 {len(prices)} 筆價格資料")

    inserted = 0
    for price in prices:
        try:
            sqlite_conn.execute("""
                INSERT INTO daily_prices (ticker, market, date, open, high, low, close, volume, adj_close)
                VALUES (?, 'TW', ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, market, date) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    adj_close = excluded.adj_close
            """, (
                price["stock_id"],
                price["date"].strftime("%Y-%m-%d"),
                price["open"],
                price["high"],
                price["low"],
                price["close"],
                price["volume"],
                price["close"]  # adj_close = close (台股無需調整)
            ))
            inserted += 1
        except Exception as e:
            print(f"⚠️  無法匯入 {ticker} {price['date']}: {e}")

    sqlite_conn.commit()
    pg_conn.close()
    sqlite_conn.close()

    print(f"✅ {ticker} 匯入完成: {inserted} 筆")
    return inserted


def import_financials(ticker: str, years: int = 5) -> int:
    """
    匯入財報資料

    FinMind schema:
      financial_report (stock_id, year, quarter, revenue, gross_margin,
                       operating_margin, net_margin, eps, roe, free_cash_flow,
                       revenue_qoq, revenue_yoy)

    CCStock schema:
      financials (ticker, market, period, period_date, revenue, gross_profit,
                  operating_income, net_income, eps, roe, fcf, gross_margin,
                  operating_margin, net_margin, ...)
    """
    pg_conn = get_pg_conn()
    sqlite_conn = get_sqlite_conn()

    current_year = datetime.now().year
    start_year = current_year - years

    cursor = pg_conn.cursor()
    cursor.execute("""
        SELECT stock_id, year, quarter, revenue, gross_margin, operating_margin,
               net_margin, eps, roe, free_cash_flow, revenue_qoq, revenue_yoy
        FROM financial_report
        WHERE stock_id = %s AND year >= %s
        ORDER BY year, quarter
    """, (ticker, start_year))

    reports = cursor.fetchall()

    if not reports:
        print(f"⚠️  無財報資料: {ticker} ({start_year} 年後)")
        pg_conn.close()
        sqlite_conn.close()
        return 0

    print(f"📥 從 FinMind 讀取到 {ticker} 的 {len(reports)} 筆財報")

    inserted = 0
    for report in reports:
        year = report["year"]
        quarter = report["quarter"]

        # 計算 period_date (假設為該季最後一天)
        month = quarter * 3
        if month == 12:
            period_date = f"{year}-12-31"
        else:
            from calendar import monthrange
            last_day = monthrange(year, month)[1]
            period_date = f"{year}-{month:02d}-{last_day:02d}"

        # 轉換單位 (FinMind revenue/fcf 單位可能是千元)
        revenue = report["revenue"] if report["revenue"] else None
        fcf = report["free_cash_flow"] if report["free_cash_flow"] else None

        # 從百分比轉換為小數 (例如 30.5% → 0.305)
        gross_margin = report["gross_margin"] / 100 if report["gross_margin"] else None
        operating_margin = report["operating_margin"] / 100 if report["operating_margin"] else None
        net_margin = report["net_margin"] / 100 if report["net_margin"] else None
        roe = report["roe"] / 100 if report["roe"] else None

        try:
            sqlite_conn.execute("""
                INSERT INTO financials (
                    ticker, market, period, period_date,
                    revenue, eps, roe, fcf,
                    gross_margin, operating_margin, net_margin
                )
                VALUES (?, 'TW', 'quarterly', ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, market, period, period_date) DO UPDATE SET
                    revenue = excluded.revenue,
                    eps = excluded.eps,
                    roe = excluded.roe,
                    fcf = excluded.fcf,
                    gross_margin = excluded.gross_margin,
                    operating_margin = excluded.operating_margin,
                    net_margin = excluded.net_margin,
                    updated_at = datetime('now')
            """, (
                ticker, period_date,
                revenue, report["eps"], roe, fcf,
                gross_margin, operating_margin, net_margin
            ))
            inserted += 1
        except Exception as e:
            print(f"⚠️  無法匯入 {ticker} {year}Q{quarter}: {e}")

    sqlite_conn.commit()
    pg_conn.close()
    sqlite_conn.close()

    print(f"✅ {ticker} 財報匯入完成: {inserted} 筆")
    return inserted


def import_all(start_date: str, stock_limit: Optional[int] = None, stock_type: str = "Stock") -> Dict[str, int]:
    """批次匯入所有資料"""
    stats = {
        "stocks": 0,
        "prices": 0,
        "financials": 0
    }

    print("=" * 60)
    print("開始批次匯入 FinMind 資料到 CCStockWorkEnv")
    print(f"股票類型: {stock_type}")
    print(f"價格日期範圍: {start_date} ~ 今日")
    print("=" * 60)

    # 1. 匯入股票清單
    print("\n[1/3] 匯入股票清單...")
    stats["stocks"] = import_stocks(limit=stock_limit, stock_type=stock_type)

    # 2. 取得已匯入的股票清單
    sqlite_conn = get_sqlite_conn()
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT ticker FROM stocks WHERE market = 'TW'")
    tickers = [row["ticker"] for row in cursor.fetchall()]
    sqlite_conn.close()

    if stock_limit:
        tickers = tickers[:stock_limit]

    print(f"\n[2/3] 匯入價格資料（{len(tickers)} 檔，自 {start_date}）...")
    for i, ticker in enumerate(tickers, 1):
        print(f"  [{i}/{len(tickers)}] {ticker}", end=" ")
        count = import_prices(ticker, start_date)
        stats["prices"] += count

    print(f"\n[3/3] 匯入財報資料（{len(tickers)} 檔，近 5 年）...")
    for i, ticker in enumerate(tickers, 1):
        print(f"  [{i}/{len(tickers)}] {ticker}", end=" ")
        count = import_financials(ticker, years=5)
        stats["financials"] += count

    print("\n" + "=" * 60)
    print("批次匯入完成")
    print("=" * 60)
    print(f"✅ 股票: {stats['stocks']} 檔")
    print(f"✅ 價格: {stats['prices']} 筆")
    print(f"✅ 財報: {stats['financials']} 筆")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Import data from FinMind PostgreSQL to CCStockWorkEnv SQLite"
    )
    parser.add_argument("--test", action="store_true", help="測試 PostgreSQL 連線")
    parser.add_argument("--import-stocks", action="store_true", help="匯入股票清單")
    parser.add_argument("--import-prices", action="store_true", help="匯入價格資料")
    parser.add_argument("--import-financials", action="store_true", help="匯入財報資料")
    parser.add_argument("--import-all", action="store_true", help="批次匯入所有資料")

    parser.add_argument("--ticker", type=str, help="股票代號 (用於 --import-prices 和 --import-financials)")
    parser.add_argument("--start-date", type=str, help="開始日期 (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="結束日期 (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, help="限制匯入股票數量 (測試用)")
    parser.add_argument("--stock-type", type=str, default="Stock", help="股票類型 (Stock/ETF/ETN，預設 Stock)")

    args = parser.parse_args()

    if args.test:
        test_connection()

    elif args.import_stocks:
        import_stocks(limit=args.limit, stock_type=args.stock_type)

    elif args.import_prices:
        if not args.ticker:
            print("❌ 請指定 --ticker")
            sys.exit(1)
        if not args.start_date:
            print("❌ 請指定 --start-date (YYYY-MM-DD)")
            sys.exit(1)
        import_prices(args.ticker, args.start_date, args.end_date)

    elif args.import_financials:
        if not args.ticker:
            print("❌ 請指定 --ticker")
            sys.exit(1)
        import_financials(args.ticker)

    elif args.import_all:
        if not args.start_date:
            # 預設匯入近 2 年資料
            args.start_date = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")
        import_all(args.start_date, stock_limit=args.limit, stock_type=args.stock_type)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
