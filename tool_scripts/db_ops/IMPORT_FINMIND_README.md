# FinMind PostgreSQL → CCStockWorkEnv SQLite 資料匯入指南

## 概述

此工具從你的本機 FinMind PostgreSQL 資料庫匯入台股資料到 CCStockWorkEnv 的 SQLite 資料庫，避免重複呼叫 API，節省配額並提升效能。

## 資料來源

**PostgreSQL 資料庫資訊：**
- Host: `localhost:5432`
- Database: `tw_stock`
- User: `user`
- Password: `password`

**可用資料：**
- 📈 **2,334 檔一般股票**（個股）
- 💰 **3,114,862 筆價格資料**（2020-01-02 ~ 2026-02-11）
- 📊 **41,070 筆財報資料**（2020-2025，季報）

## 安裝依賴（一次性）

```bash
cd /Users/austin.hsieh/temp/CCStockWorkEnv/tool_scripts/db_ops
uv pip install psycopg2-binary
```

## 使用方式

### 1. 測試連線

```bash
cd /Users/austin.hsieh/temp/CCStockWorkEnv/tool_scripts/db_ops
uv run python import_finmind.py --test
```

預期輸出：
```
✅ PostgreSQL 連線成功
   版本: PostgreSQL 15.16 on aarch64-unknown-linux-musl...
   可用表格: annual_financial_report, daily_price, dividend_policy, ...
```

### 2. 匯入股票清單

```bash
# 匯入所有一般股票（個股）
uv run python import_finmind.py --import-stocks --stock-type 個股

# 測試匯入前 10 檔
uv run python import_finmind.py --import-stocks --stock-type 個股 --limit 10
```

### 3. 匯入價格資料（單一股票）

```bash
# 匯入台積電（2330）自 2024-01-01 至今的價格資料
uv run python import_finmind.py --import-prices --ticker 2330 --start-date 2024-01-01

# 指定日期範圍
uv run python import_finmind.py --import-prices --ticker 2330 \
  --start-date 2024-01-01 --end-date 2024-12-31
```

### 4. 匯入財報資料（單一股票）

```bash
# 匯入台積電近 5 年財報
uv run python import_finmind.py --import-financials --ticker 2330
```

### 5. 批次匯入（推薦）

```bash
# 完整匯入：所有一般股票 + 價格（2024至今） + 財報（近5年）
uv run python import_finmind.py --import-all --start-date 2024-01-01 --stock-type 個股

# 測試匯入前 100 檔（約 8 秒）
uv run python import_finmind.py --import-all --start-date 2024-01-01 \
  --stock-type 個股 --limit 100

# 僅匯入 2024-2025 的資料（更快）
uv run python import_finmind.py --import-all --start-date 2024-01-01 \
  --end-date 2025-12-31 --stock-type 個股

# 匯入 ETF 資料
uv run python import_finmind.py --import-all --start-date 2024-01-01 --stock-type ETF
```

## 資料對應表

### 股票清單（stock_info → stocks）

| FinMind (PostgreSQL) | CCStockWorkEnv (SQLite) |
|---------------------|-------------------------|
| `id` | `ticker` |
| `name` | `name` |
| `industry` | `sector` / `industry` |
| `listed_type` (TWSE/TPEx) | `exchange` |
| `stock_type` (個股/ETF/ETN) | — |
| `delisted` | `is_active` (反向) |

### 價格資料（daily_price → daily_prices）

| FinMind (PostgreSQL) | CCStockWorkEnv (SQLite) |
|---------------------|-------------------------|
| `stock_id` | `ticker` |
| `date` | `date` |
| `open` / `high` / `low` / `close` | 同名 |
| `volume` | `volume` |
| — | `adj_close` (= close，台股無需調整) |
| — | `market` (固定 "TW") |

### 財報資料（financial_report → financials）

| FinMind (PostgreSQL) | CCStockWorkEnv (SQLite) |
|---------------------|-------------------------|
| `stock_id` | `ticker` |
| `year` / `quarter` | → `period_date` (計算季末日期) |
| — | `period` (固定 "quarterly") |
| `revenue` | `revenue` |
| `eps` | `eps` |
| `roe` (%) | `roe` (轉為小數) |
| `free_cash_flow` | `fcf` |
| `gross_margin` (%) | `gross_margin` (轉為小數) |
| `operating_margin` (%) | `operating_margin` (轉為小數) |
| `net_margin` (%) | `net_margin` (轉為小數) |
| — | `market` (固定 "TW") |

## 效能估算

基於測試結果（100 檔股票 = 8 秒）：

| 股票數 | 預估時間 | 價格資料筆數 | 財報資料筆數 |
|-------|---------|------------|------------|
| 100 檔 | ~8 秒 | ~45,000 | ~1,500 |
| 500 檔 | ~40 秒 | ~225,000 | ~7,500 |
| 2,334 檔 | **~3-4 分鐘** | **~1,050,000** | **~35,000** |

**注意**：
- 價格資料筆數取決於日期範圍（2024-01-01 至今約 514 個交易日）
- 財報資料每檔股票近 5 年約 19 筆（5年 × 4季 - 1）

## 常見問題

### Q1: 如何檢查匯入結果？

```bash
cd /Users/austin.hsieh/temp/CCStockWorkEnv/tool_scripts/db_ops
uv run python db_manager.py --info
```

預期輸出：
```
Tables:
  stocks: 2334 rows
  daily_prices: ~1,050,000 rows
  financials: ~35,000 rows
```

### Q2: 如何更新已匯入的資料？

重新執行匯入指令即可，腳本使用 `ON CONFLICT ... DO UPDATE`，會自動更新現有資料。

```bash
# 更新台積電的最新資料
uv run python import_finmind.py --import-prices --ticker 2330 --start-date 2024-01-01
uv run python import_finmind.py --import-financials --ticker 2330
```

### Q3: 匯入失敗怎麼辦？

1. 確認 PostgreSQL 正在運行：
   ```bash
   psql -h localhost -U user -d tw_stock -c "SELECT COUNT(*) FROM stock_info;"
   ```

2. 檢查連線設定：
   ```bash
   uv run python import_finmind.py --test
   ```

3. 如果密碼錯誤，編輯 `import_finmind.py` 第 46-52 行：
   ```python
   PG_CONFIG = {
       "host": "localhost",
       "port": 5432,
       "database": "tw_stock",
       "user": "user",        # ← 確認正確
       "password": "password" # ← 確認正確
   }
   ```

### Q4: 可以匯入更早期的資料嗎？

可以！調整 `--start-date` 參數：

```bash
# 匯入 2020 年至今的所有資料
uv run python import_finmind.py --import-all --start-date 2020-01-01 --stock-type 個股

# 注意：2020-2026 共 6 年資料，約 1,500 個交易日
# 匯入時間會延長至 6-8 分鐘
```

### Q5: 可以只匯入特定產業的股票嗎？

目前腳本不支援產業篩選，但你可以先匯入所有股票，然後在 SQLite 中查詢：

```bash
cd /Users/austin.hsieh/temp/CCStockWorkEnv/tool_scripts/db_ops
uv run python stock_ops.py --list --market TW --sector 半導體
```

或手動編輯 `import_finmind.py` 第 97 行，加入 `AND industry = '半導體'` 條件。

## 資料品質

### 已處理的問題

✅ **百分比轉換**：財報中的百分比欄位（毛利率、ROE 等）自動轉為小數
  - FinMind: 30.5% → SQLite: 0.305

✅ **期末日期計算**：財報的 `year`/`quarter` 自動轉換為 `period_date`
  - 2024Q1 → 2024-03-31
  - 2024Q4 → 2024-12-31

✅ **市場標記**：所有台股資料自動標記為 `market = 'TW'`

✅ **去重機制**：使用 `UNIQUE CONSTRAINT`，避免重複匯入

### 注意事項

⚠️ **ETF/ETN 可能無財報**：FinMind 的 ETF 類股票通常沒有財報資料（正常現象）

⚠️ **新上市股票資料不完整**：近期上市的股票可能只有部分季度的財報

⚠️ **價格資料缺失**：停牌或下市前的股票可能某些日期無交易資料

## 下一步：使用匯入的資料

匯入完成後，你可以使用 CCStockWorkEnv 的工具進行分析：

```bash
# 查詢台積電財務資料
cd /Users/austin.hsieh/temp/CCStockWorkEnv/tool_scripts/db_ops
uv run python financial_ops.py --get 2330 --market TW --period quarterly

# 計算台積電健康評分
uv run python financial_ops.py --compute-health 2330 --market TW

# 篩選高品質股票
cd /Users/austin.hsieh/temp/CCStockWorkEnv/tool_scripts/financial_calc
uv run python screener.py --market TW --min-roe 0.15 --min-fscore 7
```

## 腳本位置

```
/Users/austin.hsieh/temp/CCStockWorkEnv/tool_scripts/db_ops/
├── import_finmind.py          # 主要匯入腳本
├── IMPORT_FINMIND_README.md   # 本文件
├── db_manager.py              # 資料庫管理
├── stock_ops.py               # 股票清單操作
├── price_ops.py               # 價格資料操作
└── financial_ops.py           # 財報資料操作
```

## 授權與免責聲明

此工具僅用於教育和研究目的。FinMind 資料受其使用條款約束，請確保符合 FinMind API 的使用規範。
