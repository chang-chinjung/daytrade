"""
fetch_real_1min_for_candidates_v2.py - 修復 Fugle 401 + yfinance fallback
401 代表你沒設 FUGLE_TOKEN

用法:
1. 設 Fugle token (去 fugle.com.tw 申請免費):
   $env:FUGLE_TOKEN="你的token"

2. 沒 token 就用 yfinance 抓近7天測試 (June 2024 太舊抓不到):
   python fetch_real_1min_for_candidates_v2.py --candidates ./data/intraday_candidates.csv --use_yfinance --start 2025-05-01 --end 2025-05-08 --limit_stocks 3
"""
import argparse, os, time
from pathlib import Path
import pandas as pd

def fetch_fugle_1min(stock_id, date_str, token):
    import requests
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/candles"
    # Fugle 新版 API 路徑可能是這樣，舊版是 /marketdata/v0.3/candles
    # 這裡嘗試 v1.0
    headers = {"X-API-KEY": token}
    params = {"symbol": stock_id, "from": date_str, "to": date_str, "timeframe": "1"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code==401:
            return None, f"{stock_id} {date_str} 401 {r.text[:100]}"
        r.raise_for_status()
        data = r.json()
        # 轉成 df
        candles = data.get('data', [])
        if not candles:
            return pd.DataFrame(), "empty"
        df = pd.DataFrame(candles)
        df['stock_id']=stock_id
        return df, "ok"
    except Exception as e:
        return None, f"{stock_id} {date_str} error {e}"

def fetch_yfinance_1min(stock_ids, start, end):
    import yfinance as yf
    all_df=[]
    for sid in stock_ids:
        ticker = f"{sid}.TW"
        try:
            print(f"yfinance 抓 {ticker} 1m {start}~{end}")
            df = yf.download(ticker, start=start, end=end, interval="1m", progress=False, auto_adjust=False)
            if df.empty:
                print(f"  空的，改抓 5m 試試")
                df = yf.download(ticker, start=start, end=end, interval="5m", progress=False, auto_adjust=False)
                if df.empty:
                    continue
            df = df.reset_index()
            df['stock_id']=sid
            df = df.rename(columns={"Datetime":"datetime","Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
            # yfinance 1m 的欄位
            all_df.append(df)
            time.sleep(0.5)
        except Exception as e:
            print(f"[WARN] {sid} yf 失敗 {e}")
    if all_df:
        return pd.concat(all_df, ignore_index=True)
    return pd.DataFrame()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", default="./data/intraday_candidates.csv")
    parser.add_argument("--start", default="2024-06-01")
    parser.add_argument("--end", default="2024-06-30")
    parser.add_argument("--out", default="./data/tw_1min_real_32_test.parquet")
    parser.add_argument("--limit_stocks", type=int, default=3)
    parser.add_argument("--use_yfinance", action="store_true", help="不走 Fugle，直接用 yfinance")
    args = parser.parse_args()

    cand = pd.read_csv(args.candidates)
    # 支援兩種格式: 只有 stock_id 或有 avg_vol20 等
    stock_ids = cand['stock_id'].astype(str).tolist()[:args.limit_stocks]
    print(f"讀取 {args.candidates} -> {len(stock_ids)} 檔: {stock_ids}")

    token = os.getenv("FUGLE_TOKEN") or os.getenv("FUGLE_API_KEY")
    
    if args.use_yfinance or not token:
        if not token:
            print("[INFO] 沒設 FUGLE_TOKEN，自動切 yfinance 模式 (只能抓近7天)")
            print("  請改日期: --start 2025-05-01 --end 2025-05-08  或去申請 token")
            # 如果使用者日期太舊，提醒
            print(f"  你現在日期 {args.start}~{args.end} 太舊，yfinance 1m 抓不到，會是空的")
        big = fetch_yfinance_1min(stock_ids, args.start, args.end)
        if not big.empty:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            big.to_parquet(args.out)
            print(f"[PASS] yfinance 已產生 {args.out} shape={big.shape}")
        else:
            print("[FAIL] yfinance 也沒抓到，1m 只能抓近7天，請改日期或設 FUGLE_TOKEN")
        return

    # Fugle 模式
    print(f"[INFO] 使用 Fugle token {token[:8]}... 抓 {args.start}~{args.end}")
    all_dfs=[]
    import datetime
    start_dt = pd.to_datetime(args.start)
    end_dt = pd.to_datetime(args.end)
    dates = pd.date_range(start_dt, end_dt, freq='D')
    
    for sid in stock_ids:
        print(f"\n=== {sid} {args.start}~{args.end} ===")
        for d in dates:
            date_str = d.strftime("%Y-%m-%d")
            if d.weekday()>=5: # 跳週末
                continue
            df, msg = fetch_fugle_1min(sid, date_str, token)
            if df is None and "401" in msg:
                print(msg)
                print("\n[FAIL] 401 Unauthorized -> 你的 FUGLE_TOKEN 錯或過期")
                print("去 https://developer.fugle.tw/ 申請，設 $env:FUGLE_TOKEN")
                return
            if df is not None and not df.empty:
                all_dfs.append(df)
            time.sleep(0.2)

    if all_dfs:
        big = pd.concat(all_dfs, ignore_index=True)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        big.to_parquet(args.out)
        print(f"[PASS] 已產生 {args.out} shape={big.shape}")
    else:
        print("[FAIL] Fugle 沒抓到資料")

if __name__=="__main__":
    main()
