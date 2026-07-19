# intraday_lab_full - Task3 pass

## Results
- yfinance 100 -> 66 stocks ok (3707 delisted)
- filter 66 -> 32 stocks (target 30-50)
  min_vol 5000, min_amp 3%

## Run order
python fetch_all_market_daily_v3.py --start 2022-01-01 --out ./data/tw_market_daily_all.parquet --max_stocks 100
python screen_stocks_final.py --input ./data/tw_market_daily_all.parquet --min_vol 5000 --min_amp 0.03 --top_n 50
python fetch_fugle_raw_v3_fixed.py --input ./data/intraday_candidates.csv --start 2024-06-03 --end 2024-06-07 --out ./data/tw_1min_real.parquet --sleep 1.1

FUGLE_API_KEY must be in env, not committed.
