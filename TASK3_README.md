
# Task 3 - 接真實1分K

目標：把合成1分K換成真實1分K，main.py 會自動偵測 ./data/tw_1min_real.parquet

## 步驟 1：拿免費 Token
FinMind 免費註冊：https://finmind.github.io/
註冊後後台有 token，複製。

## 步驟 2：本地執行
```bash
cd intraday_lab_full
pip install finmind yfinance pandas pyarrow
export FINMIND_TOKEN=你的token  # Windows: set FINMIND_TOKEN=xxx

# 先小試 1檔 1年
python fetch_real_1min.py --stocks 2330 --start 2023-01-01 --end 2023-12-31

# 成功後全量
python fetch_real_1min.py --stocks 2330,2317,2454 --start 2022-01-01 --end 2024-12-31 --out ./data/tw_1min_real.parquet
```

## 步驟 3：驗收
```bash
python main.py --mode fast   # 會顯示 "完成真實" 而非合成
python eval_harness.py --mode fast  # 仍需 PASS
```

yfinance 備援：若無 token，會自動抓近7天 1分K，適合快速測試。

常見坑：
- FinMind 每分鐘限流 10 次，已加 sleep(0.5)
- 台股 1分K 僅 9:00-13:30，已過濾
- parquet 需 pyarrow
