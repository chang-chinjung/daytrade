import os, requests, time, pandas as pd
from pathlib import Path

API_KEY = os.getenv("FUGLE_API_KEY","").strip()  # 直接用你設的那串，不解碼
STOCK = "2330"

def fetch_day(symbol, date_str):
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/candles/{symbol}"
    headers = {"X-API-KEY": API_KEY}  # 就是這串 base64 原文
    params = {"from": date_str, "to": date_str}
    r = requests.get(url, headers=headers, params=params, timeout=20)
    if r.status_code != 200:
        print(f"{date_str} {r.status_code} {r.text[:150]}")
        return None
    j = r.json()
    data = j.get("data") or j.get("candles") or []
    if not data:
        return None
    df = pd.DataFrame(data)
    df["datetime"] = pd.to_datetime(df["date"])
    df["stock_id"] = symbol
    return df[["datetime","open","high","low","close","volume","stock_id"]]

# 跑 2023-01 完整月
import argparse
ap = argparse.ArgumentParser()
ap.add_argument('--start', default='2023-01-03')
ap.add_argument('--end', default='2023-01-31')
ap.add_argument('--out', default='./data/tw_1min_real.parquet')
args = ap.parse_args()

days = pd.date_range(args.start, args.end, freq='D')
all_df=[]
for d in days:
    ds = d.strftime("%Y-%m-%d")
    if d.weekday() >=5: continue
    df = fetch_day(STOCK, ds)
    if df is not None and not df.empty:
        print(f"{ds} -> {len(df)}")
        all_df.append(df)
    time.sleep(1.1)

if all_df:
    final = pd.concat(all_df, ignore_index=True).sort_values("datetime")
    Path("./data").mkdir(exist_ok=True)
    final.to_parquet(args.out, index=False)
    print(f"\nDONE {args.out} shape={final.shape} 應該要 3000+ 才對")
    print(final.head())
else:
    print("沒抓到，先把 3510 版救回來")