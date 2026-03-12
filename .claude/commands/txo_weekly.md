# TXO 周選擇權賣方評估

評估本週台指選擇權（TXO）周選賣方策略是否符合進場條件，並計算建議交易設定。

## 使用方式

```
/txo_weekly
/txo_weekly --otm 2.5        # 指定賣出 OTM 百分比（預設 2.0）
/txo_weekly --iv 25          # 指定 IV 假設（預設 20%）
```

## 執行步驟

執行此 command 時，依序執行以下步驟：

### Step 1：取得大盤即時數據

```bash
cd tool_scripts/market_data && uv run python fetcher_factory.py quote ^TWII --market TW
```

### Step 2：計算 MA20 及前週漲幅

執行以下 Python 腳本：

```python
import yfinance as yf
import pandas as pd
from datetime import datetime

t = yf.Ticker('^TWII')
hist = t.history(period='2mo').reset_index()
hist['Date'] = pd.to_datetime(hist['Date']).dt.tz_localize(None)
hist = hist.sort_values('Date')

# MA20
ma20 = hist['Close'].rolling(20).mean().iloc[-1]
ma60 = hist['Close'].rolling(60).mean().iloc[-1] if len(hist) >= 60 else None
current = hist['Close'].iloc[-1]

# 前週漲幅（週線）
hist['week'] = hist['Date'].dt.to_period('W-WED')
weekly = hist.groupby('week').agg(open=('Open','first'), close=('Close','last')).reset_index()
weekly['ret'] = (weekly['close'] - weekly['open']) / weekly['open'] * 100
prev_week_ret = float(weekly['ret'].iloc[-2]) if len(weekly) >= 2 else None
this_week_ret = float(weekly['ret'].iloc[-1])

print(f"Current: {current:.0f}")
print(f"MA20: {ma20:.0f}")
print(f"Above MA20: {current > ma20}")
print(f"Prev week return: {prev_week_ret:.2f}%")
print(f"This week return so far: {this_week_ret:.2f}%")
```

### Step 3：套用5條執行規則判斷

依據 `.claude/skills/txo_weekly_strategy.md` 的規則：

| 規則 | 條件 | 結果 |
|------|------|------|
| 規則一 | TWII > MA20 | ✅/❌ |
| 規則二 | 前週漲幅 < 4% | ✅/❌ |

**進場判斷邏輯：**
- 兩條規則都符合 → **✅ 本週可進場**
- 任一規則不符合 → **⛔ 本週跳過，說明原因**

### Step 4：計算建議交易設定（若可進場）

使用當前 TWII 價格計算：

```python
import math

def norm_cdf(x):
    return 0.5*(1+math.erf(x/math.sqrt(2)))

def bs_put(S, K, T=5/365, sigma=0.20, r=0.015):
    if T <= 0 or K <= 0: return 0
    d1 = (math.log(S/K) + (r+sigma**2/2)*T)/(sigma*math.sqrt(T))
    d2 = d1 - sigma*math.sqrt(T)
    return max(0, K*math.exp(-r*T)*norm_cdf(-d2) - S*norm_cdf(-d1))

# 參數
S = <current_twii>
otm_sell = 0.02   # 2% OTM（或 --otm 參數）
otm_buy  = 0.035  # 3.5% OTM

sell_k = round(S * (1 - otm_sell) / 100) * 100  # 取整百
buy_k  = round(S * (1 - otm_buy)  / 100) * 100

p_sell = bs_put(S, sell_k)
p_buy  = bs_put(S, buy_k)
net_cr = p_sell - p_buy
max_loss = (sell_k - buy_k) - net_cr
breakeven = sell_k - net_cr
ror = net_cr / max_loss * 100

print(f"賣出 Put: {sell_k} @ {p_sell:.1f}點 (NT${p_sell*50:.0f})")
print(f"買入 Put: {buy_k} @ {p_buy:.1f}點 (NT${p_buy*50:.0f})")
print(f"淨收: {net_cr:.1f}點 (NT${net_cr*50:.0f})")
print(f"最大損失: {max_loss:.1f}點 (NT${max_loss*50:.0f})")
print(f"損益兩平: {breakeven:.0f}")
print(f"ROR: {ror:.1f}%")
```

### Step 5：產生 HTML 報告

依 `.claude/skills/report_generation_guide.md` 格式，產生報告包含：

1. **進場條件評估卡片**（綠色=通過 / 紅色=不通過）
2. **建議交易設定表**（賣出/買入履約價、損益計算）
3. **損益圖**（SVG，顯示到期日損益結構）
4. **操作 SOP**（進場時機、停損停利規則）
5. **TWII K 線圖 iframe**

報告命名格式：`YYYYMMDD_HHMMSS_txo_weekly_eval`

### Step 6：驗證並回報

```bash
# 確認報告 URL 正常
curl -s -o /dev/null -w "%{http_code}" http://localhost:8800/reports/<SLUG>/

# Playwright 截圖驗證
npx playwright screenshot --browser chromium \
  --viewport-size "375,812" --full-page --wait-for-timeout 3000 \
  "http://localhost:8800/reports/<SLUG>/" /tmp/txo_eval.png
```

## 回覆格式

**若可進場：**
```
✅ 本週周選可進場

📊 建議交易：Bull Put Spread
• 賣出 Put：XXXXX（約價外 2%）
• 買入 Put：XXXXX（保護腳）
• 淨收權利金：約 NT$X,XXX
• 損益兩平：XXXXX（跌 X.X% 才虧損）
• 到期日：XXXX-XX-XX（週三）

🔗 完整報告：<URL>
```

**若不可進場：**
```
⛔ 本週跳過

❌ 不符合條件：
• 規則一：TWII(XXXXX) < MA20(XXXXX) — 跌破均線
• 規則二：前週漲幅 +X.X% > 4% — 急漲後風險高

📌 建議：等待 <具體條件> 後再評估
🔗 詳細分析：<URL>
```

## 參考資料

- 策略規則詳見：`.claude/skills/txo_weekly_strategy.md`
- 報告格式詳見：`.claude/skills/report_generation_guide.md`
- 1年回測結果：勝率 91.2%、總損益 +NT$53,221、MaxDD -NT$12,032（51週資料）
