"""
screen_stocks.py v4.1 - Architect 最終版
支援 FinMind: Trading_Volume, max/min
"""
import argparse
from pathlib import Path
import pandas as pd

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="./data/tw_market_daily.parquet")
    parser.add_argument("--min_vol", type=int, default=5000, help="20日均量 > 張")
    parser.add_argument("--min_amp", type=float, default=0.03, help="平均振幅 > 3%%")
    parser.add_argument("--top_n", type=int, default=50)
    parser.add_argument("--out_csv", default="./data/intraday_candidates.csv")
    parser.add_argument("--out_report", default="./reports/screening_report.md")
    args = parser.parse_args()

    in_path = Path(args.input)
    df = pd.read_parquet(in_path)
    print(f"欄位: {list(df.columns)} | 筆數: {len(df)}")

    rename = {}
    for c in df.columns:
        lc = c.lower()
        if lc in ["stock_id","stockid","symbol"]: rename[c]="stock_id"
        if lc in ["date","trade_date"]: rename[c]="date"
        if lc in ["open"]: rename[c]="open"
        if lc in ["high","max"]: rename[c]="high"
        if lc in ["low","min"]: rename[c]="low"
        if lc in ["close"]: rename[c]="close"
        if lc in ["volume","trading_volume"]: rename[c]="volume"

    df = df.rename(columns=rename)
    print(f"對應後: {list(df.columns)}")

    if df["volume"].mean() > 100000:
        df["volume"] = df["volume"] / 1000

    df = df.sort_values(["stock_id","date"])
    df["date"] = pd.to_datetime(df["date"])
    df["avg_vol20"] = df.groupby("stock_id")["volume"].transform(lambda x: x.rolling(20, min_periods=20).mean())
    df["amplitude"] = (df["high"] - df["low"]) / df["close"].replace(0, pd.NA)
    df["avg_amp"] = df.groupby("stock_id")["amplitude"].transform(lambda x: x.rolling(20, min_periods=20).mean())

    latest = df.dropna(subset=["avg_vol20","avg_amp"]).sort_values("date").groupby("stock_id").tail(1)
    filtered = latest[(latest["avg_vol20"] > args.min_vol) & (latest["avg_amp"] > args.min_amp)].sort_values("avg_vol20", ascending=False).head(args.top_n)

    Path(args.out_csv).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_report).parent.mkdir(parents=True, exist_ok=True)

    if len(filtered)>0:
        filtered[["stock_id","avg_vol20","avg_amp"]].to_csv(args.out_csv, index=False)
    else:
        print(f"[提示] 0檔，試 --min_vol 1000 --min_amp 0.01，最新 vol={latest['avg_vol20'].iloc[-1]:.0f}, amp={latest['avg_amp'].iloc[-1]*100:.2f}%%")
        latest[["stock_id","avg_vol20","avg_amp"]].to_csv(args.out_csv, index=False)

    print(f"[PASS] {df['stock_id'].nunique()} -> {len(filtered)} 檔，已產生 {args.out_csv}")

if __name__ == "__main__":
    main()
