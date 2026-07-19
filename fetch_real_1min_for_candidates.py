"""
fetch_real_1min_for_candidates.py - 依 intraday_candidates.csv 32檔抓真實1分K
用法:
  $env:FUGLE_API_KEY="你的MarketData key"
  python fetch_real_1min_for_candidates.py --candidates ./data/intraday_candidates.csv --start 2024-06-01 --end 2024-06-30 --out ./data/tw_1min_real_32.parquet
"""
import os, base64, time, argparse, requests, pandas as pd
from pathlib import Path

RAW = os.getenv("FUGLE_API_KEY","").strip()
def decode_key(raw):
    try:
        dec = base64.b64decode(raw).decode().strip()
        parts = dec.split()
        return parts[0]
    except:
        return raw.split()[0] if raw else ""

API_KEY = decode_key(RAW)

def fetch_day(symbol, date_str):
    if not API_KEY:
        print("[FAIL] 沒設 FUGLE_API_KEY")
        return None
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/candles/{symbol}"
    headers = {"X-API-KEY": API_KEY}
    params = {"from": date_str, "to": date_str}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
    except Exception as e:
        print(f"{symbol} {date_str} 連線失敗 {e}")
        return None
    if r.status_code != 200:
        if r.status_code != 404:
            print(f"{symbol} {date_str} {r.status_code} {r.text[:150]}")
        return None
    j = r.json()
    candles = None
    if isinstance(j, dict):
        if 'data' in j and isinstance(j['data'], dict) and 'candles' in j['data']:
            candles = j['data']['candles']
        elif 'candles' in j:
            candles = j['candles']
        elif 'data' in j and isinstance(j['data'], list):
            candles = j['data']
    if not candles:
        return None
    df = pd.DataFrame(candles)
    if df.empty:
        return None
    if 'date' in df.columns:
        df['datetime'] = pd.to_datetime(df['date'])
    elif 'datetime' in df.columns:
        df['datetime'] = pd.to_datetime(df['datetime'])
    else:
        return None
    df['stock_id'] = symbol
    if 'volume' not in df.columns and 'turnover' in df.columns:
        df['volume'] = df['turnover']
    cols = [c for c in ["datetime","open","high","low","close","volume","stock_id"] if c in df.columns]
    df = df[cols].sort_values("datetime")
    df = df[(df["datetime"].dt.time >= pd.Timestamp("09:00").time()) & (df["datetime"].dt.time <= pd.Timestamp("13:30").time())]
    return df

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--candidates', default='./data/intraday_candidates.csv')
    ap.add_argument('--start', default='2024-06-01')
    ap.add_argument('--end', default='2024-06-30')
    ap.add_argument('--out', default='./data/tw_1min_real_32.parquet')
    ap.add_argument('--limit_stocks', type=int, default=0, help="0=全部，先測3檔就設3")
    args = ap.parse_args()

    if not Path(args.candidates).exists():
        print(f"[FAIL] 找不到 {args.candidates}")
        return

    cand = pd.read_csv(args.candidates)
    stocks = cand['stock_id'].astype(str).tolist()
    if args.limit_stocks>0:
        stocks = stocks[:args.limit_stocks]
    print(f"讀取 {args.candidates} -> {len(stocks)} 檔: {stocks}")

    if not API_KEY:
        print("[FAIL] 請先設 $env:FUGLE_API_KEY='你的key' (要 MarketData key，不是Trade)")
        return

    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)
    days = pd.date_range(start, end, freq='D')

    all_df=[]
    for stock in stocks:
        print(f"\n=== {stock} {args.start}~{args.end} ===")
        for d in days:
            ds = d.strftime("%Y-%m-%d")
            df = fetch_day(stock, ds)
            if df is not None and not df.empty:
                all_df.append(df)
                print(f"  {ds} -> {len(df)} 根")
            time.sleep(1.1)

    if not all_df:
        print("全部沒抓到，檢查 key 或日期是否假日")
        return

    final = pd.concat(all_df, ignore_index=True).sort_values(["stock_id","datetime"]).drop_duplicates(["stock_id","datetime"])
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    final.to_parquet(args.out, index=False)
    print(f"\n[PASS] 完成 {args.out} shape={final.shape}")
    print(final.groupby('stock_id').agg(rows=('close','count'), start=('datetime','min'), end=('datetime','max')))

if __name__=="__main__":
    main()
