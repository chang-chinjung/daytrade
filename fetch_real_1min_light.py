"""
fetch_real_1min_light.py - Task 3 輕量版，無需 finmind/lxml，Windows Python 3.14 友善
只依賴 requests + pandas + pyarrow + yfinance(備援)
用法同原版：
  export FINMIND_TOKEN=xxx
  python fetch_real_1min_light.py --stocks 2330 --start 2023-01-01 --end 2023-12-31 --out ./data/tw_1min_real.parquet
API 文件：https://finmind.github.io/tutor/TaiwanMarket/TechDetail/#taiwanstockminuteprice
"""
import argparse, os, sys, time
from pathlib import Path
import pandas as pd
import requests

FINMIND_API = "https://api.finmindtrade.com/api/v4/data"

def fetch_finmind_rest(stock, start, end, token):
    # FinMind REST 直連，不用 finmind 套件
    params = {
        "dataset": "TaiwanStockMinutePrice",
        "data_id": str(stock),
        "start_date": start,
        "end_date": end,
    }
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"  # 舊版也支援 token 在 params
        params["token"] = token  # 兼容 v3
    print(f"[FinMind REST] {stock} {start}~{end}")
    r = requests.get(FINMIND_API, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    j = r.json()
    if j.get("msg") != "success":
        raise RuntimeError(f"FinMind API msg={j}")
    data = j.get("data", [])
    if not data:
        raise RuntimeError(f"FinMind 空 {stock}")
    df = pd.DataFrame(data)
    # 欄位：date, stock_id, Time, open, high, low, close, Trading_Volume / volume
    # 組 datetime
    if "Time" in df.columns:
        df["datetime"] = pd.to_datetime(df["date"].astype(str) + " " + df["Time"].astype(str))
    else:
        df["datetime"] = pd.to_datetime(df["date"])
    df["stock_id"] = df["stock_id"].astype(str)
    # volume 欄位名兼容
    if "Trading_Volume" in df.columns and "volume" not in df.columns:
        df["volume"] = df["Trading_Volume"]
    for c in ["open","high","low","close","volume"]:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df[["datetime","open","high","low","close","volume","stock_id"]].sort_values("datetime")
    # 9:00-13:30
    df = df[(df["datetime"].dt.time >= pd.Timestamp("09:00").time()) & (df["datetime"].dt.time <= pd.Timestamp("13:30").time())]
    print(f"[FinMind REST] {stock} {len(df)} rows {df['datetime'].min()}~{df['datetime'].max()}")
    return df

def fetch_yfinance(stock, start, end):
    import yfinance as yf
    ticker = f"{stock}.TW"
    print(f"[yfinance] {ticker} {start}~{end}")
    data = yf.download(ticker, start=start, end=end, interval="1m", auto_adjust=False, progress=False, threads=False)
    if data.empty:
        raise RuntimeError("yfinance 空")
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data = data.reset_index().rename(columns={"Datetime":"datetime","Date":"datetime","Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
    data["stock_id"] = str(stock)
    data["datetime"] = pd.to_datetime(data["datetime"])
    return data[["datetime","open","high","low","close","volume","stock_id"]].dropna().sort_values("datetime")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stocks', default='2330')
    ap.add_argument('--start', default='2023-01-01')
    ap.add_argument('--end', default='2023-12-31')
    ap.add_argument('--out', default='./data/tw_1min_real.parquet')
    args = ap.parse_args()
    token = os.getenv("FINMIND_TOKEN","") or os.getenv("FINMIND_API_TOKEN","")
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    all_df=[]
    for s in [x.strip() for x in args.stocks.split(',') if x.strip()]:
        df=None
        try:
            if token:
                df = fetch_finmind_rest(s, args.start, args.end, token)
            else:
                print("[提示] 無 FINMIND_TOKEN，先試 yfinance 近7天")
                raise RuntimeError("no token")
        except Exception as e:
            print(f"[FinMind REST] {s} 失敗 {e} -> fallback yfinance")
            try:
                # yfinance 1m 僅近7天，若使用者給的區間太早，自動縮到近7天
                try:
                    df = fetch_yfinance(s, args.start, args.end)
                except:
                    end = pd.Timestamp.now().strftime("%Y-%m-%d")
                    start = (pd.Timestamp.now() - pd.Timedelta(days=6)).strftime("%Y-%m-%d")
                    df = fetch_yfinance(s, start, end)
            except Exception as e2:
                print(f"[yfinance] {s} 失敗 {e2}")
        if df is not None and not df.empty:
            all_df.append(df)
        time.sleep(0.6)

    if not all_df:
        print("全部失敗")
        sys.exit(1)
    final = pd.concat(all_df, ignore_index=True).sort_values(["stock_id","datetime"]).drop_duplicates(["stock_id","datetime"])
    final.to_parquet(out, index=False)
    print(f"\n=== 完成 {out} shape={final.shape} ===")
    print(final.groupby('stock_id').agg(rows=('close','count'), start=('datetime','min'), end=('datetime','max')))

if __name__ == "__main__":
    main()
