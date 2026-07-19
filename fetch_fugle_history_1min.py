# fetch_fugle_intraday_1min_true.py
import os, requests, time, pandas as pd
from pathlib import Path

API_KEY = os.getenv("FUGLE_API_KEY")
STOCK = "2330"
START = "2023-01-01"
END = "2023-01-31"

def fetch_day(symbol, date_str):
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/candles/{symbol}"
    headers = {"X-API-KEY": API_KEY}
    params = {"from": date_str, "to": date_str}  # Fugle 要一天一天抓
    r = requests.get(url, headers=headers, params=params, timeout=20)
    if r.status_code != 200:
        print(f"{date_str} {r.status_code} {r.text[:200]}")
        return None
    j = r.json()
    data = j.get("data") or j.get("candles") or []
    if not data:
        return None
    df = pd.DataFrame(data)
    # 欄位可能是 date, open, high, low, close, volume
    df["datetime"] = pd.to_datetime(df["date"])
    df["stock_id"] = symbol
    return df[["datetime","open","high","low","close","volume","stock_id"]]

# 迴圈跑 2023-01 每天
days = pd.date_range(START, END, freq='D')
all_df=[]
for d in days:
    ds = d.strftime("%Y-%m-%d")
    df = fetch_day(STOCK, ds)
    if df is not None and not df.empty:
        print(f"{ds} -> {len(df)}")
        all_df.append(df)
    time.sleep(1.1) # 60/min 限流

final = pd.concat(all_df).sort_values("datetime")
final.to_parquet("./data/tw_1min_real.parquet", index=False)
print(f"DONE {final.shape}")