#!/bin/bash
# 快速檢查 FinMind 匯入進度

DB_PATH="/Users/austin.hsieh/temp/CCStockWorkEnv/data/ccstockworkenv.db"

echo "========================================="
echo " FinMind 匯入進度檢查"
echo "========================================="
echo

# 統計資料
stocks_count=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM stocks WHERE market = 'TW'")
prices_count=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM daily_prices WHERE market = 'TW'")
financials_count=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM financials WHERE market = 'TW'")

echo "✅ 股票: $stocks_count 檔"
echo "✅ 價格: $prices_count 筆"
echo "✅ 財報: $financials_count 筆"
echo

# 最新匯入的股票
echo "最近匯入的 10 檔股票:"
sqlite3 "$DB_PATH" "SELECT ticker, name, updated_at FROM stocks WHERE market = 'TW' ORDER BY updated_at DESC LIMIT 10" -header -column

echo
echo "資料庫大小:"
ls -lh "$DB_PATH" | awk '{print $5}'

echo
echo "========================================="
