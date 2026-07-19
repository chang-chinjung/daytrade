"""
fetch_fugle_raw_v3_fixed.py - 修復版
1. 正確 endpoint: /marketdata/v1.0/stock/intraday/candles/{symbol}
2. 空資料時不報 KeyError: date
3. 支援 resume + 假日跳過
pip install requests pandas pyarrow
$env:FUGLE_API_KEY="你的MarketData key (UUID) 或 base64包"
python fetch_fugle_raw_v3_fixed.py --input ./data/intraday_candidates.csv --start 2024-06-01 --end 2024-06-10 --out ./data/tw_1min_real.parquet --sleep 1.1
"""
import os, base64, time, argparse, requests
from pathlib import Path
import pandas as pd
from datetime import datetime, timedelta

RAW = os.getenv("FUGLE_API_KEY","").strip()

def decode_key(raw):
    if not raw:
        return ""
    # 你的格式是 base64 裡面包兩個 UUID 用空格隔開
    try:
        dec = base64.b64decode(raw).decode().strip()
        parts = dec.split()
        print(f"[Key] base64 解開 -> 取第1段 MarketData key len={len(parts[0])}")
        return parts[0]
    except Exception:
        # 已經是 UUID
        first = raw.split()[0]
        print(f"[Key] 直接使用 len={len(first)} -> {first[:8]}...")
        return first

API_KEY = decode_key(RAW)
if not API_KEY:
    print("請先 $env:FUGLE_API_KEY='你的key'")
    # 不直接 exit，讓用戶看到說明

def fetch_day(symbol, date_str):
    # 正確 endpoint 2024 版
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/candles/{symbol}"
    headers = {"X-API-KEY": API_KEY}
    params = {"from": date_str, "to": date_str}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
    except Exception as e:
        print(f"  {symbol} {date_str} 連線失敗 {e}")
        return None
    if r.status_code == 404:
        # 沒這個商品或當天沒資料，靜默跳過
        return None
    if r.status_code == 401:
        print(f"  {symbol} {date_str} 401 Unauthorized，檢查是否為 MarketData key")
        print(r.text[:200])
        return None
    if r.status_code == 429:
        print(f"  429限流，睡5秒")
        time.sleep(5)
        return None
    if r.status_code != 200:
        print(f"  {symbol} {date_str} {r.status_code} {r.text[:300]}")
        return None
    try:
        j = r.json()
    except:
        return None

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
    # 確保必要欄位
    for col in ["open","high","low","close","volume"]:
        if col not in df.columns:
            df[col]=0
    cols = [c for c in ["datetime","open","high","low","close","volume","stock_id"] if c in df.columns]
    df = df[cols].sort_values("datetime")
    df = df[(df["datetime"].dt.time >= pd.Timestamp("09:00").time()) & (df["datetime"].dt.time <= pd.Timestamp("13:30").time())]
    if df.empty:
        return None
    return df

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', default='./data/intraday_candidates.csv')
    ap.add_argument('--start', default='2024-06-01')
    ap.add_argument('--end', default='2024-06-10')
    ap.add_argument('--out', default='./data/tw_1min_real.parquet')
    ap.add_argument('--sleep', type=float, default=1.1, help="60/min限流，設1.1安全")
    args = ap.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"[FAIL] 找不到 {in_path}")
        return
    cand = pd.read_csv(in_path)
    # 相容欄位名
    col = 'stock_id' if 'stock_id' in cand.columns else cand.columns[0]
    stocks = cand[col].astype(str).str.replace(".TW","").tolist()
    print(f"候選 {len(stocks)} 檔: {stocks[:10]}...")

    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)
    days = pd.date_range(start, end, freq='D')
    print(f"日期 {len(days)} 天 {args.start} -> {args.end}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # resume
    existed = []
    done_set = set()
    if out_path.exists():
        try:
            old = pd.read_parquet(out_path)
            if not old.empty and 'datetime' in old.columns:
                old['date_only'] = pd.to_datetime(old['datetime']).dt.date
                old['stock_id'] = old['stock_id'].astype(str)
                for _, r in old[['stock_id','date_only']].drop_duplicates().iterrows():
                    done_set.add(f"{r['stock_id']}_{r['date_only']}")
                existed.append(old)
                print(f"[Resume] 已有 {len(old)} 筆，{len(done_set)} 個 stock+date 已完成")
        except Exception as e:
            print(f"[Resume] 讀舊檔失敗 {e}")

    all_df = existed
    for symbol in stocks:
        for d in days:
            ds = d.strftime("%Y-%m-%d")
            key = f"{symbol}_{d.date()}"
            if key in done_set:
                continue
            # 跳過週末
            if d.weekday() >= 5:
                continue
            df = fetch_day(symbol, ds)
            if df is not None and not df.empty:
                all_df.append(df)
                print(f"  {symbol} {ds} -> {len(df)} 根")
            time.sleep(args.sleep)

    if not all_df:
        print("[FAIL] 全部沒抓到，可能是 key 錯誤、都是假日、或都是冷門股無1分K")
        # 產生空檔避免後面 KeyError
        pd.DataFrame(columns=["datetime","open","high","low","close","volume","stock_id"]).to_parquet(out_path, index=False)
        return

    big = pd.concat(all_df, ignore_index=True)
    # 防呆：避免空的
    if big.empty or 'datetime' not in big.columns:
        print("[FAIL] 合併後仍空")
        return

    # 去重 + 排序
    big = big.sort_values(["stock_id","datetime"]).drop_duplicates(["stock_id","datetime"])
    # 為了相容你之前用 date 欄位的程式，補 date 欄位
    big['date'] = pd.to_datetime(big['datetime']).dt.date
    big.to_parquet(out_path, index=False)
    print(f"\n[PASS] 已產生 {out_path} shape={big.shape}")
    print(big.groupby('stock_id').agg(rows=('close','count'), start=('datetime','min'), end=('datetime','max')).head(20))

if __name__ == "__main__":
    main()
