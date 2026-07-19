"""
screen_stocks.py v3 - 自動認 FinMind 欄位
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
    if not in_path.exists():
        print(f"[FAIL] 找不到 {in_path}")
        return

    print(f"讀取 {in_path} ...")
    df = pd.read_parquet(in_path)
    print(f"欄位: {list(df.columns)} | 筆數: {len(df)}")

    rename = {}
    for c in df.columns:
        lc = c.lower()
        if lc in ["stock_id","stockid","symbol","stock","代號","stock_code"]: rename[c]="stock_id"
        if lc in ["date","日期","trade_date"]: rename[c]="date"
        if lc in ["open","開盤","開盤價"]: rename[c]="open"
        if lc in ["high","最高","最高價","max"]: rename[c]="high"
        if lc in ["low","最低","最低價","min"]: rename[c]="low"
        if lc in ["close","收盤","收盤價","close_price"]: rename[c]="close"
        if lc in ["volume","trading_volume","trading_shares","成交股數","成交量","trade_volume"]: rename[c]="volume"

    df = df.rename(columns=rename)
    print(f"對應後欄位: {list(df.columns)}")

    if "stock_id" not in df.columns:
        df["stock_id"] = "2330"
        print("[提示] 沒 stock_id，補 2330")

    if "volume" not in df.columns:
        print(f"[FAIL] 找不到 volume，現有: {list(df.columns)}")
        return

    if df["volume"].mean() > 100000:
        df["volume"] = df["volume"] / 1000
        print("[提示] volume 是股數，已 /1000 轉張")

    for col in ["high","low","close"]:
        if col not in df.columns:
            print(f"[FAIL] 缺少 {col}")
            return

    print(f"原始: {df['stock_id'].nunique()} 檔, {len(df)} 筆")

    df = df.sort_values(["stock_id","date"])
    df["date"] = pd.to_datetime(df["date"])

    df["avg_vol20"] = df.groupby("stock_id")["volume"].transform(lambda x: x.rolling(20, min_periods=20).mean())
    df["amplitude"] = (df["high"] - df["low"]) / df["close"].replace(0, pd.NA)
    df["avg_amp"] = df.groupby("stock_id")["amplitude"].transform(lambda x: x.rolling(20, min_periods=20).mean())

    latest = df.dropna(subset=["avg_vol20","avg_amp"]).sort_values("date").groupby("stock_id").tail(1)
    filtered = latest[(latest["avg_vol20"] > args.min_vol) & (latest["avg_amp"] > args.min_amp)]
    filtered = filtered.sort_values("avg_vol20", ascending=False).head(args.top_n)

    Path(args.out_csv).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_report).parent.mkdir(parents=True, exist_ok=True)

    if len(filtered)>0:
        filtered[["stock_id","avg_vol20","avg_amp"]].to_csv(args.out_csv, index=False)
    else:
        print("[提示] 0檔，試 --min_vol 1000 --min_amp 0.01")
        df.tail(1)[["stock_id"]].to_csv(args.out_csv, index=False)

    report = f"""# Screening Report
- 日期: {pd.Timestamp.now().date()}
- 輸入: {args.input} {df['stock_id'].nunique()}檔
- 條件: 量能>{args.min_vol}張, 振幅>{args.min_amp*100:.1f}%%
- 結果: {df['stock_id'].nunique()} -> {len(filtered)} 檔
- Top: {', '.join(filtered.head(10)['stock_id'].astype(str).tolist()) if len(filtered)>0 else '無'}
- 輸出: {args.out_csv}
"""
    Path(args.out_report).write_text(report, encoding="utf-8")
    print(report)
    print(f"[PASS] 已產生 {args.out_csv}")

if __name__ == "__main__":
    main()
