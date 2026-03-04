import sqlite3

conn = sqlite3.connect('../../data/ccstockworkenv.db')
conn.row_factory = sqlite3.Row

print('📊 台股重要股票資料驗證\n')
print('=' * 70)

# 檢查重要股票
important_stocks = [
    ('2330', '台積電'),
    ('2454', '聯發科'),
    ('2412', '中華電'),
    ('2317', '鴻海'),
    ('2308', '台達電')
]

for ticker, name in important_stocks:
    # 檢查股票基本資料
    stock = conn.execute('SELECT * FROM stocks WHERE ticker = ? AND market = "TW"', (ticker,)).fetchone()
    
    # 檢查價格資料
    price_count = conn.execute('SELECT COUNT(*) FROM daily_prices WHERE ticker = ? AND market = "TW"', (ticker,)).fetchone()[0]
    latest_price = conn.execute('SELECT date, close FROM daily_prices WHERE ticker = ? AND market = "TW" ORDER BY date DESC LIMIT 1', (ticker,)).fetchone()
    
    # 檢查財報資料
    fin_count = conn.execute('SELECT COUNT(*) FROM financials WHERE ticker = ? AND market = "TW"', (ticker,)).fetchone()[0]
    latest_fin = conn.execute('SELECT period_date, revenue, eps, roe FROM financials WHERE ticker = ? AND market = "TW" ORDER BY period_date DESC LIMIT 1', (ticker,)).fetchone()
    
    print(f'{ticker} {name}')
    print(f'  股票資料: {"✅" if stock else "❌"}')
    
    if latest_price:
        print(f'  價格資料: {price_count} 筆 (最新: {latest_price["date"]}, 收盤價: {latest_price["close"]:.2f})')
    else:
        print(f'  價格資料: {price_count} 筆 (無最新價格)')
    
    if latest_fin:
        print(f'  財報資料: {fin_count} 筆 (最新: {latest_fin["period_date"]})')
        if latest_fin['revenue']:
            rev_b = latest_fin["revenue"]/1e9
            eps = latest_fin["eps"] if latest_fin["eps"] else 0
            roe = latest_fin["roe"]*100 if latest_fin["roe"] else 0
            print(f'            營收: {rev_b:.2f}B, EPS: {eps:.2f}, ROE: {roe:.2f}%')
    else:
        print(f'  財報資料: {fin_count} 筆 (無最新財報)')
    print()

# 統計摘要
print('=' * 70)
print('📈 資料庫統計摘要\n')

# 價格資料統計
price_stats = conn.execute('''
    SELECT 
        COUNT(DISTINCT ticker) as stock_count,
        COUNT(*) as total_records,
        MIN(date) as earliest,
        MAX(date) as latest
    FROM daily_prices
    WHERE market = "TW"
''').fetchone()

print(f'價格資料:')
print(f'  涵蓋股票: {price_stats["stock_count"]} 檔')
print(f'  總筆數: {price_stats["total_records"]:,} 筆')
print(f'  日期範圍: {price_stats["earliest"]} ~ {price_stats["latest"]}')
print()

# 財報資料統計
fin_stats = conn.execute('''
    SELECT 
        COUNT(DISTINCT ticker) as stock_count,
        COUNT(*) as total_records,
        MIN(period_date) as earliest,
        MAX(period_date) as latest
    FROM financials
    WHERE market = "TW"
''').fetchone()

print(f'財報資料:')
print(f'  涵蓋股票: {fin_stats["stock_count"]} 檔')
print(f'  總筆數: {fin_stats["total_records"]:,} 筆')
print(f'  日期範圍: {fin_stats["earliest"]} ~ {fin_stats["latest"]}')

conn.close()
