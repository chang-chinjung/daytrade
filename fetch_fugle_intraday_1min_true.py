import os, base64, time, argparse, requests, pandas as pd
from pathlib import Path
from datetime import datetime

# 你貼的 key 是 base64 包兩組，用空格隔開
# ZDQyNDQ0MDYt... = d4244406-78f3-48ca-af9d-232d0d7c1364 (MarketData)
# e65a1b57-13eb-488b-9e4e-49c04e26ba3 (Trade)
RAW = os.getenv("FUGLE_API_KEY","").strip()
def decode_key(raw):
    try:
        # 先試 base64 解
        dec = base64.b64decode(raw).decode().strip()
        # 裡面還有空格，拆兩段
        parts = dec.split()
        print(f"[Key] base64 解開 -> {parts}")
        return parts[0]  # 取第一段當 MarketData key
    except:
        # 若已經是 UUID 直接用
        return raw.split()[0]

API_KEY = decode_key(RAW)
if not API_KEY:
    print("請先 $env:FUGLE_API_KEY='你的key'")
    exit(1)

def fetch_day(symbol, date_str):
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/candles/{symbol}"
    headers = {"X-API-KEY": API_KEY}
    params = {"from": date_str, "to": date_str}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
    except Exception as e:
        print(f"{date_str} 連線失敗 {e}")
        return None
    if r.status_code == 401:
        print(f"{date_str} 401 Unauthorized，請檢查 key 是否為 MarketData key")
        print(r.text[:200])
        return None
    if r.status_code != 200:
        print(f"{date_str} {r.status_code} {r.text[:200]}")
        return None
    j = r.json()
    # 官方回傳格式 {date, data: {candles: [...]} } 或 {candles: [...]}
    candles = None
    if isinstance(j, dict):
        if 'data' in j and isinstance(j['data'], dict) and 'candles' in j['data']:
            candles = j['data']['candles']
        elif 'candles' in j:
            candles = j['candles']
        elif 'data' in j and isinstance(j['data'], list):
            candles = j['data']
        else:
            candles = j.get('data')
    if not candles:
        # print(f"{date_str} 無資料，可能是假日")
        return None
    df = pd.DataFrame(candles)
    if df.empty:
        return None
    # 欄位標準化：date, open, high, low, close, volume
    if 'date' in df.columns:
        df['datetime'] = pd.to_datetime(df['date'])
    elif 'datetime' in df.columns:
        df['datetime'] = pd.to_datetime(df['datetime'])
    else:
        return None
    df['stock_id'] = symbol
    # 有些 volume 叫 turnover
    if 'volume' not in df.columns and 'turnover' in df.columns:
        df['volume'] = df['turnover']
    cols = [c for c in ["datetime","open","high","low","close","volume","stock_id"] if c in df.columns]
    df = df[cols].sort_values("datetime")
    # 只留 09:00-13:30
    df = df[(df["datetime"].dt.time >= pd.Timestamp("09:00").time()) & (df["datetime"].dt.time <= pd.Timestamp("13:30").time())]
    print(f"{date_str} -> {len(df)} 根 {df['datetime'].min().time() if len(df)>0 else ''}~{df['datetime'].max().time() if len(df)>0 else ''}")
    return df

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stocks', default='2330')
    ap.add_argument('--start', default='2023-01-01')
    ap.add_argument('--end', default='2023-01-31')
    ap.add_argument('--out', default='./data/tw_1min_real.parquet')
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)
    days = pd.date_range(start, end, freq='D')

    all_df=[]
    for stock in [s.strip() for s in args.stocks.split(',') if s.strip()]:
        print(f"\n=== {stock} {args.start}~{args.end} ===")
        for d in days:
            ds = d.strftime("%Y-%m-%d")
            df = fetch_day(stock, ds)
            if df is not None and not df.empty:
                all_df.append(df)
            time.sleep(1.1) # 60/min 限流

    if not all_df:
        print("全部沒抓到，可能是 key 錯誤或都是假日")
        return

    final = pd.concat(all_df, ignore_index=True).sort_values(["stock_id","datetime"]).drop_duplicates(["stock_id","datetime"])
    final.to_parquet(out, index=False)
    print(f"\n=== 完成 {out} shape={final.shape} ===")
    print(final.groupby('stock_id').agg(rows=('close','count'), start=('datetime','min'), end=('datetime','max')))

    # 同時備份 3510 版
    backup = out.parent / f"tw_1min_real_fugle_{args.start[:7]}.parquet"
    final.to_parquet(backup, index=False)
    print(f"備份 {backup}")

if __name__=="__main__":
    main()
