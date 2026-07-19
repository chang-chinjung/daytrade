"""
fetch_real_1min.py - Task 3 真實1分K落地
支援三路徑：FinMind (主) -> Fugle (備) -> yfinance (最後備援)
教育研究用途，落地為 ./data/tw_1min_real.parquet 後 main.py 會自動優先使用真實K

本地執行：
  pip install finmind yfinance fugle-marketdata pandas pyarrow
  export FINMIND_TOKEN=your_token  # https://finmind.github.io/ 免費註冊
  export FUGLE_API_KEY=your_key    # 可選，https://developer.fugle.tw/
  python fetch_real_1min.py --stocks 2330,2317 --start 2022-01-01 --end 2024-12-31 --out ./data/tw_1min_real.parquet

若無 token，會自動走 yfinance 抓最近 7 天 1分K (Yahoo 限制)
"""
import argparse, os, sys, time
from pathlib import Path
import pandas as pd

def fetch_finmind_minute(stock, start, end, token):
    from FinMind.data import DataLoader
    dl = DataLoader()
    if token:
        dl.login_by_token(api_token=token)
    # FinMind 有兩種 API 寫法，兼容
    candidates = []
    try:
        # 新版
        df = dl.taiwan_stock_minute(stock_id=stock, start_date=start, end_date=end)
        candidates.append(df)
    except Exception as e:
        print(f"[FinMind] taiwan_stock_minute fail {stock} {e}")
    try:
        df2 = dl.get_data(dataset="TaiwanStockMinutePrice", data_id=stock, start_date=start, end_date=end)
        candidates.append(df2)
    except Exception as e:
        print(f"[FinMind] get_data fail {stock} {e}")
    
    for df in candidates:
        if df is None or df.empty:
            continue
        # 標準化欄位
        df = df.rename(columns={"date":"datetime", "Date":"datetime", "stock_id":"stock_id"})
        if "datetime" not in df.columns:
            # FinMind 回傳有 date + Time
            if "date" in df.columns:
                df["datetime"] = pd.to_datetime(df["date"].astype(str) + " " + df.get("Time", "09:00:00").astype(str))
        df["datetime"] = pd.to_datetime(df["datetime"])
        df["stock_id"] = str(stock)
        # 確保有 OHLCV
        for c in ["open","high","low","close","volume"]:
            if c not in df.columns:
                df[c] = df.get(c.capitalize(), 0)
        df = df[["datetime","open","high","low","close","volume","stock_id"]].sort_values("datetime")
        # 台股 9:00-13:30 過濾
        df = df[(df["datetime"].dt.time >= pd.Timestamp("09:00").time()) & (df["datetime"].dt.time <= pd.Timestamp("13:30").time())]
        if not df.empty:
            print(f"[FinMind] {stock} {len(df)} rows {df['datetime'].min()}~{df['datetime'].max()}")
            return df
    raise RuntimeError(f"FinMind 無 {stock} 資料")

def fetch_fugle_minute(stock, start, end, api_key):
    # Fugle 官方 intraday 需訂閱，此為骨架，依官方文件補
    # https://developer.fugle.tw/docs/keystat
    try:
        from fugle_marketdata import RestClient
        client = RestClient(api_key=api_key)
        # 範例：需逐日抓，Fugle 限制較嚴
        print("[Fugle] 骨架呼叫，請依官方文件實作 intraday/candles")
        raise NotImplementedError("Fugle intraday 需付費權限，請用 FinMind 為主")
    except Exception as e:
        raise

def fetch_yfinance(stock, start, end):
    import yfinance as yf
    ticker = f"{stock}.TW"
    # yfinance 1m 只給最近7天，自動縮範圍
    print(f"[yfinance] {ticker} {start}~{end} (注意：1m 僅近7天有效)")
    data = yf.download(ticker, start=start, end=end, interval="1m", auto_adjust=False, progress=False, threads=False)
    if data.empty:
        raise RuntimeError("yfinance 空")
    # yfinance 有時回 MultiIndex
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data = data.reset_index()
    data = data.rename(columns={"Datetime":"datetime","Date":"datetime","Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
    data["stock_id"] = str(stock)
    data["datetime"] = pd.to_datetime(data["datetime"])
    data = data[["datetime","open","high","low","close","volume","stock_id"]].dropna().sort_values("datetime")
    return data

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stocks', default='2330', help='逗號分隔，如 2330,2317,2454')
    ap.add_argument('--start', default='2022-01-01')
    ap.add_argument('--end', default='2024-12-31')
    ap.add_argument('--out', default='./data/tw_1min_real.parquet')
    ap.add_argument('--source', default='auto', choices=['auto','finmind','fugle','yfinance'])
    args = ap.parse_args()

    finmind_token = os.getenv("FINMIND_TOKEN","") or os.getenv("FINMIND_API_TOKEN","")
    fugle_key = os.getenv("FUGLE_API_KEY","")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    all_df = []
    for s in [x.strip() for x in args.stocks.split(',') if x.strip()]:
        df = None
        # 1. FinMind
        if args.source in ('auto','finmind'):
            try:
                df = fetch_finmind_minute(s, args.start, args.end, finmind_token)
            except Exception as e:
                print(f"[FinMind] {s} 失敗 {e}")
        # 2. Fugle
        if df is None and args.source in ('auto','fugle') and fugle_key:
            try:
                df = fetch_fugle_minute(s, args.start, args.end, fugle_key)
            except Exception as e:
                print(f"[Fugle] {s} 失敗 {e}")
        # 3. yfinance fallback
        if df is None and args.source in ('auto','yfinance'):
            try:
                # 若 start 太早，yfinance 會空，自動改近7天
                if args.source == 'auto':
                    # 先試使用者區間
                    try:
                        df = fetch_yfinance(s, args.start, args.end)
                    except:
                        # fallback 近7天
                        end = pd.Timestamp.now().strftime("%Y-%m-%d")
                        start = (pd.Timestamp.now() - pd.Timedelta(days=6)).strftime("%Y-%m-%d")
                        df = fetch_yfinance(s, start, end)
                else:
                    df = fetch_yfinance(s, args.start, args.end)
            except Exception as e:
                print(f"[yfinance] {s} 失敗 {e}")
        if df is not None and not df.empty:
            all_df.append(df)
        time.sleep(0.5)  # 避免被限流

    if not all_df:
        print("全部失敗，請檢查 FINMIND_TOKEN 或網路")
        sys.exit(1)

    final = pd.concat(all_df, ignore_index=True).sort_values(["stock_id","datetime"])
    # 去重
    final = final.drop_duplicates(subset=["stock_id","datetime"])
    final.to_parquet(out, index=False)
    print(f"\n=== 完成 ===")
    print(f"輸出 {out} shape={final.shape}")
    print(f"stock: {final['stock_id'].unique().tolist()}")
    print(f"時間: {final['datetime'].min()} ~ {final['datetime'].max()}")
    print(f"下一步: python main.py --mode fast  # 會自動偵測 {out} 優先使用真實K")
    # 同時產生摘要
    summary = final.groupby('stock_id').agg(rows=('close','count'), start=('datetime','min'), end=('datetime','max'))
    print(summary)

if __name__ == "__main__":
    main()
