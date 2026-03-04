#!/usr/bin/env python3
"""
Batch compute health scores for all TW stocks in DB.

Reads financials from DB (no external API calls), computes Z-Score, F-Score,
growth rates, and cash flow quality, saves to health_scores table.

Usage:
    python batch_compute_health_tw.py [--period quarterly|annual]
"""

import argparse
import sys
import time
from db_manager import get_connection, DB_PATH
from financial_ops import compute_and_save_health


def get_tickers_with_financials(period: str) -> list[tuple]:
    """Get all distinct (ticker, market) that have financials data."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT ticker, market FROM financials WHERE market='TW' AND period=? ORDER BY ticker",
        (period,),
    ).fetchall()
    conn.close()
    return [(r["ticker"], r["market"]) for r in rows]


def main():
    parser = argparse.ArgumentParser(description="Batch compute health scores for TW stocks")
    parser.add_argument("--period", default="quarterly", choices=["quarterly", "annual"],
                        help="Period type (default: quarterly)")
    args = parser.parse_args()

    tickers = get_tickers_with_financials(args.period)
    total = len(tickers)
    print(f"Computing health scores for {total} TW stocks (period={args.period})...")
    print("=" * 60)

    success = 0
    errors = []
    start = time.time()

    for i, (ticker, market) in enumerate(tickers, 1):
        try:
            results = compute_and_save_health(ticker, market, period=args.period)
            if results:
                success += 1
                if i % 100 == 0 or i == total:
                    elapsed = time.time() - start
                    rate = i / elapsed
                    remaining = (total - i) / rate if rate > 0 else 0
                    print(f"[{i}/{total}] {ticker} ✓  |  elapsed={elapsed:.0f}s  eta={remaining:.0f}s")
        except Exception as e:
            errors.append((ticker, str(e)))
            if len(errors) <= 10:
                print(f"[{i}/{total}] {ticker} ERROR: {e}")

    elapsed = time.time() - start
    print("\n" + "=" * 60)
    print(f"完成！成功: {success}/{total}  失敗: {len(errors)}  耗時: {elapsed:.1f}s")
    if errors:
        print(f"\n前 10 筆錯誤:")
        for ticker, err in errors[:10]:
            print(f"  {ticker}: {err}")


if __name__ == "__main__":
    main()
