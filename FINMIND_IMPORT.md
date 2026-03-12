# FinMind PostgreSQL 資料匯入指南

## 概述

本文件說明如何將 FinMind PostgreSQL 資料庫的台股資料匯入到 CCStockWorkEnv SQLite 環境。

## 資料來源

### FinMind PostgreSQL
- **位置**: `localhost:5432`
- **資料庫**: `tw_stock`
- **使用者**: `user` / `password`
- **專案路徑**: `/Users/austin.hsieh/temp/stockAnalyne`

### 資料表結構對照

| FinMind PostgreSQL | CCStockWorkEnv SQLite | 說明 |
|-------------------|----------------------|------|
| `stock_info` | `stocks` | 股票清單 |
| `daily_price` | `daily_prices` | 每日價格 |
| `financial_report` | `financials` | 財報資料 |
| `annual_financial_report` | `financials` (period='annual') | 年度財報 |
| `monthly_revenue` | _(未匯入)_ | 月營收 |
| `dividend_policy` | _(未匯入)_ | 股利政策 |
| `stock_shares_outstanding` | _(未匯入)_ | 股本資料 |

## 匯入工具

### 安裝依賴

```bash
cd /Users/austin.hsieh/temp/CCStockWorkEnv
uv pip install psycopg2-binary
```

### 工具路徑

```
tool_scripts/db_ops/import_finmind.py
```

## 使用方式

### 1. 測試連線

```bash
cd tool_scripts/db_ops
uv run python import_finmind.py --test
```

**預期輸出**：
```
✅ PostgreSQL 連線成功
   版本: PostgreSQL 15.16 on aarch64-unknown-linux-musl...
   可用表格: annual_financial_report, daily_price, dividend_policy, ...
```

### 2. 匯入股票清單

```bash
# 匯入所有股票
uv run python import_finmind.py --import-stocks

# 僅匯入前 50 檔（測試用）
uv run python import_finmind.py --import-stocks --limit 50
```

### 3. 匯入價格資料

```bash
# 單一股票
uv run python import_finmind.py --import-prices --ticker 2330 --start-date 2024-01-01

# 指定結束日期
uv run python import_finmind.py --import-prices --ticker 2330 --start-date 2024-01-01 --end-date 2024-12-31
```

### 4. 匯入財報資料

```bash
# 單一股票（預設近 5 年）
uv run python import_finmind.py --import-financials --ticker 2330
```

### 5. 批次匯入所有資料

```bash
# 匯入所有股票的所有資料（自 2024-01-01）
uv run python import_finmind.py --import-all --start-date 2024-01-01

# 僅匯入前 100 檔（測試用）
uv run python import_finmind.py --import-all --start-date 2024-01-01 --limit 100
```

## 欄位映射

### 股票清單 (stock_info → stocks)

| FinMind | CCStock | 轉換邏輯 |
|---------|---------|---------|
| `id` | `ticker` | 直接映射 |
| `name` | `name` | 直接映射 |
| `industry` | `sector` | 直接映射 |
| `industry` | `industry` | 直接映射 |
| `listed_type` | `exchange` | TWSE/TPEx |
| `stock_type` | _(不儲存)_ | Stock/ETF/ETN |
| _(固定)_ | `market` | 'TW' |
| _(固定)_ | `currency` | 'TWD' |
| `delisted = false` | `is_active = 1` | 僅匯入未下市股票 |

### 價格資料 (daily_price → daily_prices)

| FinMind | CCStock | 轉換邏輯 |
|---------|---------|---------|
| `stock_id` | `ticker` | 直接映射 |
| `date` | `date` | 格式化為 YYYY-MM-DD |
| `open` | `open` | 直接映射 |
| `high` | `high` | 直接映射 |
| `low` | `low` | 直接映射 |
| `close` | `close` | 直接映射 |
| `volume` | `volume` | 直接映射 |
| `close` | `adj_close` | 台股無需調整，直接使用收盤價 |
| `ma5` | _(不儲存)_ | 可自行計算 |
| `ma20` | _(不儲存)_ | 可自行計算 |

### 財報資料 (financial_report → financials)

| FinMind | CCStock | 轉換邏輯 |
|---------|---------|---------|
| `stock_id` | `ticker` | 直接映射 |
| `year`, `quarter` | `period_date` | 轉換為季末日期 (e.g., 2024Q1 → 2024-03-31) |
| _(固定)_ | `period` | 'quarterly' |
| `revenue` | `revenue` | 直接映射（單位：元） |
| `eps` | `eps` | 直接映射 |
| `roe` | `roe` | **除以 100**（30.5% → 0.305） |
| `gross_margin` | `gross_margin` | **除以 100** |
| `operating_margin` | `operating_margin` | **除以 100** |
| `net_margin` | `net_margin` | **除以 100** |
| `free_cash_flow` | `fcf` | 直接映射 |
| `revenue_qoq` | _(不儲存)_ | 可自行計算 |
| `revenue_yoy` | _(不儲存)_ | 可自行計算 |

## 資料品質

### 已驗證項目

✅ **股票清單**
- 包含上市/上櫃股票、ETF
- 自動過濾已下市股票
- 產業分類正確

✅ **價格資料**
- 每日 OHLCV 資料完整
- 日期範圍：2024-01-01 至最新（視 FinMind 資料庫而定）
- 無重複資料（PRIMARY KEY 約束）

✅ **財報資料**
- 季報資料完整（2021-2025）
- ROE、毛利率等比率已正確轉換為小數
- ETF 無財報資料（正常）

### 已知限制

⚠️ **未匯入的資料表**
- `monthly_revenue`（月營收）
- `dividend_policy`（股利政策）
- `stock_shares_outstanding`（股本資料）
- `stock_score_cache`（健康評分）

這些資料表可在未來版本中擴充匯入。

⚠️ **資料範圍**
- 預設僅匯入 2024-01-01 後的價格資料（可調整 `--start-date`）
- 財報資料預設近 5 年（可調整）

## 匯入統計

### 測試匯入（10 檔股票）

```
✅ 股票: 10 檔
✅ 價格: 1,028 筆
✅ 財報: 38 筆
```

### 完整匯入（預估）

假設 FinMind 資料庫有 ~1,700 檔台股：

```
預估股票: 1,700 檔
預估價格: 1,700 * 500 天 = 850,000 筆
預估財報: 1,700 * 20 季 = 34,000 筆
預估時間: 15-30 分鐘
```

## 衝突處理

所有匯入操作使用 `ON CONFLICT ... DO UPDATE` 策略：
- 如果資料已存在 → 更新為最新值
- 如果資料不存在 → 插入新記錄

這表示可以安全地重複執行匯入，不會產生重複資料。

## 日誌

匯入日誌位於：
```
data/logs/finmind_import_YYYYMMDD_HHMMSS.log
```

## 匯入後檢查

### 檢查資料庫狀態

```bash
cd tool_scripts/db_ops
uv run python db_manager.py --info
```

### 查詢股票清單

```bash
uv run python stock_ops.py --list --market TW
```

### 檢查特定股票資料

```bash
# 查看股票資訊
sqlite3 ccstockworkenv.db "SELECT * FROM stocks WHERE ticker = '2330'"

# 查看最新價格
sqlite3 ccstockworkenv.db "SELECT * FROM daily_prices WHERE ticker = '2330' ORDER BY date DESC LIMIT 5"

# 查看財報
sqlite3 ccstockworkenv.db "SELECT * FROM financials WHERE ticker = '2330' ORDER BY period_date DESC LIMIT 5"
```

## 維護與更新

### 定期更新價格資料

建議每日收盤後執行：

```bash
# 匯入所有股票的最新價格（僅匯入新資料）
uv run python import_finmind.py --import-all --start-date $(date -v-7d +%Y-%m-%d)
```

### 季報更新

財報發布後（通常每季結束後 1 個月）：

```bash
# 更新所有股票財報
cd tool_scripts/db_ops
# TODO: 建立批次財報更新腳本
```

## 擴充方向

### 1. 匯入月營收資料

在 `import_finmind.py` 中新增：

```python
def import_monthly_revenue(ticker: str) -> int:
    # 從 monthly_revenue 表讀取
    # 儲存到 SQLite (需新增 monthly_revenues 表)
    pass
```

### 2. 匯入股利資料

在 `import_finmind.py` 中新增：

```python
def import_dividends(ticker: str) -> int:
    # 從 dividend_policy 表讀取
    # 儲存到 SQLite (需新增 dividends 表)
    pass
```

### 3. 匯入健康評分

FinMind 已計算的評分可直接匯入：

```python
def import_health_scores(ticker: str) -> int:
    # 從 stock_score_cache 表讀取
    # 對映到 CCStock 的 health_scores 表
    pass
```

## 故障排除

### 連線失敗

```
❌ PostgreSQL 連線失敗: connection refused
```

**解決方式**：
1. 確認 PostgreSQL 容器正在執行：`docker ps`
2. 確認連線參數正確（`PG_CONFIG` in `import_finmind.py`）

### 權限錯誤

```
❌ permission denied for table stock_info
```

**解決方式**：
確認資料庫使用者有 SELECT 權限。

### 匯入速度慢

**優化建議**：
1. 批次插入（目前是逐筆插入）
2. 使用 SQLite WAL 模式（已啟用）
3. 調整 SQLite cache size

## 作者

- **建立日期**: 2026-03-04
- **工具版本**: v1.0
- **支援市場**: 台股 (TW)

---

## 相關文件

- [CLAUDE.md](./CLAUDE.md) — CCStockWorkEnv 專案說明
- [db_manager.py](./tool_scripts/db_ops/db_manager.py) — 資料庫 schema 管理
- [FinMind 官方文件](https://finmind.github.io/)
