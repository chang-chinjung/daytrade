
"""
fetch_real_1min.py - 真實1分K落地 (FinMind + yfinance fallback)
"""
import argparse, os, sys
from pathlib import Path
import pandas as pd

def fetch_finmind_minute(stock, start, end, token):
    from FinMind.data import DataLoader
    dl = DataLoader()
    dl.login_by_token(api_token=token or "")
    for attr in ["taiwan_stock_minute","get_data"]:
        try:
            if attr=="taiwan_stock_minute":
                df=dl.taiwan_stock_minute(stock_id=stock, start_date=start, end_date=end)
            else:
                df=dl.get_data(dataset="TaiwanStockMinutePrice", data_id=stock, start_date=start, end_date=end)
            if df is not None and not df.empty:
                df=df.rename(columns={"date":"datetime"})
                df["datetime"]=pd.to_datetime(df["datetime"])
                df["stock_id"]=stock
                return df[["datetime","open","high","low","close","volume","stock_id"]]
        except Exception as e:
            print(f"try {attr} fail {e}")
            continue
    raise RuntimeError("FinMind 無資料")

def fetch_yfinance(stock, start, end):
    import yfinance as yf
    ticker=f"{stock}.TW"
    data=yf.download(ticker, start=start, end=end, interval="1m", auto_adjust=False, progress=False)
    data=data.reset_index().rename(columns={"Datetime":"datetime","Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
    data["stock_id"]=str(stock)
    return data[["datetime","open","high","low","close","volume","stock_id"]]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--stocks', default='2330')
    ap.add_argument('--start', default='2022-01-01')
    ap.add_argument('--end', default='2024-12-31')
    ap.add_argument('--out', default='./data/tw_1min_real.parquet')
    args=ap.parse_args()
    token=os.getenv("FINMIND_TOKEN","")
    out=Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    all_df=[]
    for s in args.stocks.split(','):
        s=s.strip()
        try:
            all_df.append(fetch_finmind_minute(s, args.start, args.end, token))
        except Exception as e:
            print(f"FinMind fail {s} {e}, try yfinance")
            try: all_df.append(fetch_yfinance(s, args.start, args.end))
            except Exception as e2: print(f"fail {s} {e2}")
    if not all_df: sys.exit(1)
    final=pd.concat(all_df).sort_values(["stock_id","datetime"])
    final.to_parquet(out, index=False)
    print(f"done {out} {final.shape}")

if __name__=="__main__": main()
