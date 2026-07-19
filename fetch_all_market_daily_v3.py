"""
fetch_all_market_daily_v3.py - yfinance fallback 版，不靠 FinMind token
pip install yfinance pandas pyarrow
用法:
  python fetch_all_market_daily_v3.py --start 2022-01-01 --out ./data/tw_market_daily_all.parquet --max_stocks 100
"""
import argparse, time
from pathlib import Path
import pandas as pd

def fetch_via_yfinance(stock_ids, start):
    import yfinance as yf
    all_df = []
    for i, sid in enumerate(stock_ids):
        try:
            ticker = f"{sid}.TW"
            print(f"{i+1}/{len(stock_ids)} 抓 {ticker}")
            df = yf.download(ticker, start=start, progress=False, auto_adjust=False)
            if df.empty:
                print(f"  空的 {sid}")
                continue
            # yfinance columns: Open High Low Close Volume
            df = df.reset_index()
            df['stock_id'] = sid
            # 平坦化 multi-index 如果有
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] if c[0]!='' else c[1] for c in df.columns]
            rename = {c.lower():c for c in df.columns}
            # 確保欄位名
            df = df.rename(columns={
                'Date':'date','Open':'open','High':'high','Low':'low','Close':'close','Volume':'volume',
                'Adj Close':'adj_close'
            })
            # 只留需要的
            keep = ['date','stock_id','open','high','low','close','volume']
            for k in keep:
                if k not in df.columns:
                    print(f"  缺 {k} 在 {sid}")
            df = df[keep]
            all_df.append(df)
            time.sleep(0.5)
        except Exception as e:
            print(f"[WARN] {sid} yfinance 失敗 {e}")
            time.sleep(1)
    if all_df:
        return pd.concat(all_df, ignore_index=True)
    return pd.DataFrame()

def get_stock_list_fallback():
    return ["2330","2317","2454","2303","2382","2357","2308","2301","2002","1301","1303","2603","2609","2615","2618","2881","2882","2891","2886","2880","2412","3045","3037","3034","3008","2379","2409","2408","2474","2481","2353","2327","2313","2324","2347","2376","2385","2395","2404","2449","2458","2498","2606","2610","2637","2645","2801","2883","2884","2885","2887","2890","2892","2912","3481","3533","3707","3711","4904","4938","5876","5880","1101","1102","1216","1229","1232"]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--out", default="./data/tw_market_daily_all.parquet")
    parser.add_argument("--max_stocks", type=int, default=100)
    args = parser.parse_args()

    stock_ids = get_stock_list_fallback()[:args.max_stocks]
    print(f"改用 yfinance 抓 {len(stock_ids)} 檔，從 {args.start}")

    big = fetch_via_yfinance(stock_ids, args.start)
    if big.empty:
        print("[FAIL] yfinance 也沒抓到")
        return

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    big.to_parquet(args.out)
    print(f"[PASS] 已產生 {args.out} shape={big.shape} 檔數={big['stock_id'].nunique()}")

if __name__ == "__main__":
    main()
