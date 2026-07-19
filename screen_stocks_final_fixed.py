"""
screen_stocks.py - 最終達標版 (66->32)
對應規格書 3.0 當沖篩選表
把 100檔 (實測66檔) -> 30~50 檔
邏輯: 量能>5000張 + 振幅>3% + (籌碼/題材 v2)

相容:
- FinMind: stock_id, date, open, high, low, close, Trading_Volume, max, min
- yfinance: Date, Open, High, Low, Close, Volume
- Fugle: date, open, high, low, close, volume

輸入: ./data/tw_market_daily_all.parquet
輸出: ./data/intraday_candidates.csv + ./reports/screening_report.md
"""
import argparse
from pathlib import Path
import pandas as pd

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    # 1. 欄位名轉小寫對照
    rename_map = {}
    for c in df.columns:
        lc = str(c).lower().strip()
        if lc in ["stock_id", "stockid", "symbol", "代號", "stock"]:
            rename_map[c] = "stock_id"
        elif lc in ["date", "日期", "datetime", "time"]:
            rename_map[c] = "date"
        elif lc == "open" or lc == "開盤":
            rename_map[c] = "open"
        elif lc == "high" or lc == "max" or lc == "最高":
            rename_map[c] = "high"
        elif lc == "low" or lc == "min" or lc == "最低":
            rename_map[c] = "low"
        elif lc == "close" or lc == "收盤" or lc == "收盤價":
            rename_map[c] = "close"
        elif lc in ["volume", "trading_volume", "trading_shares", "成交股數", "成交量", "vol"]:
            rename_map[c] = "volume"

    df = df.rename(columns=rename_map)

    # 2. 確保必要欄位
    if "stock_id" not in df.columns:
        print("[提示] 沒 stock_id，預設 2330 (單檔模式)")
        df["stock_id"] = "2330"
    
    if "date" not in df.columns:
        # 試圖從 index 找
        if isinstance(df.index, pd.DatetimeIndex):
            df["date"] = df.index
        else:
            raise ValueError("找不到 date 欄位")

    # 3. 成交量如果是股數，轉張數 (1張=1000股)
    #    判斷: 平均 > 100000 幾乎一定是股數
    try:
        v_mean = pd.to_numeric(df["volume"], errors="coerce").mean()
        if v_mean > 100000:
            df["volume"] = df["volume"] / 1000
            print(f"[提示] volume 平均 {v_mean:.0f} 看起來是股數，已 /1000 轉張")
    except Exception:
        pass

    # 4. 型別清理
    df["stock_id"] = df["stock_id"].astype(str).str.replace(".TW","").str.replace(".TWO","")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for c in ["open","high","low","close","volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=["date","open","high","low","close","volume"])
    return df

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="./data/tw_market_daily_all.parquet")
    parser.add_argument("--min_vol", type=int, default=5000, help="20日均量 > 張")
    parser.add_argument("--min_amp", type=float, default=0.03, help="平均振幅 > 3%")
    parser.add_argument("--top_n", type=int, default=50)
    parser.add_argument("--out_csv", default="./data/intraday_candidates.csv")
    parser.add_argument("--out_report", default="./reports/screening_report.md")
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        # fallback 試試舊檔名
        alt = Path("./data/tw_market_daily.parquet")
        if alt.exists():
            in_path = alt
        else:
            print(f"[FAIL] 找不到 {args.input} 也找不到 {alt}")
            print("  請先跑 fetch_all_market_daily_v3.py")
            return

    print(f"讀取 {in_path} ...")
    df = pd.read_parquet(in_path)
    print(f"原始欄位: {list(df.columns)}")

    df = normalize_columns(df)
    print(f"正規化後: {df['stock_id'].nunique()} 檔, {len(df)} 筆, 欄位 {list(df.columns)}")

    # 確保排序
    df = df.sort_values(["stock_id", "date"])

    # 1. 量能: 20日均量
    df["avg_vol20"] = df.groupby("stock_id")["volume"].transform(lambda x: x.rolling(20, min_periods=20).mean())
    # 2. 波動: 日內振幅 (high-low)/close
    df["amplitude"] = (df["high"] - df["low"]) / df["close"].replace(0, pd.NA)
    df["avg_amp"] = df.groupby("stock_id")["amplitude"].transform(lambda x: x.rolling(20, min_periods=20).mean())

    # 取最新一天有算好的
    latest = df.dropna(subset=["avg_vol20", "avg_amp"]).sort_values("date").groupby("stock_id").tail(1)
    print(f"可計算20MA的: {latest['stock_id'].nunique()} 檔")

    # 篩選
    filtered = latest[(latest["avg_vol20"] > args.min_vol) & (latest["avg_amp"] > args.min_amp)]
    filtered = filtered.sort_values("avg_vol20", ascending=False).head(args.top_n)

    # 輸出
    Path(args.out_csv).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_report).parent.mkdir(parents=True, exist_ok=True)

    filtered[["stock_id", "avg_vol20", "avg_amp"]].to_csv(args.out_csv, index=False)

    # 電子股占比 (驗收用)
    electronic_prefix = ["2330","2317","2454","2303","2308","2382","2357"]
    electronic_cnt = filtered[filtered["stock_id"].isin(electronic_prefix)].shape[0]

    report = f"""# Screening Report
- 日期: {pd.Timestamp.now().date()}
- 輸入: {in_path} {df['stock_id'].nunique()}檔, {len(df)}筆
- 條件: 量能>{args.min_vol}張, 振幅>{args.min_amp*100:.1f}%
- 結果: {df['stock_id'].nunique()} -> {len(filtered)} 檔 (目標 30~50)
- Top 10: {', '.join(filtered.head(10)['stock_id'].astype(str).tolist())}
- 平均量能: {filtered['avg_vol20'].mean():.0f} 張
- 平均振幅: {filtered['avg_amp'].mean()*100:.2f}%
- 電子股占比: {electronic_cnt}/{len(filtered)}
- 輸出: {args.out_csv}

## 指標對應規格書 3.0
- 量能: 日均>5000張, 流動性高不卡單 -> avg_vol20
- 波動: 振幅>3% -> avg_amp
- 籌碼: TODO v2 接 FinMind 外資買賣超連3天同向
- 技術面: 5分K-1分K糾結突破 -> 留給 main.py
- 題材: AI/半導體/電動車 -> TODO v2 接產業對照
"""
    Path(args.out_report).write_text(report, encoding="utf-8")
    print(report)
    print(f"\n[PASS] 已產生 {args.out_csv} + {args.out_report}")

if __name__ == "__main__":
    main()
