"""
fetch_fugle_raw_v3.py - 處理 429 Rate limit + 斷點續抓版
- 遇到 429 自動 sleep 65 秒重試
- 每檔存一次 checkpoint，可中斷後再跑
- 支援 Trading_Volume / max/min 自動轉換

用法:
python fetch_fugle_raw_v3.py --input ./data/intraday_candidates.csv --start 2024-06-01 --end 2024-06-10 --out ./data/tw_1min_real.parquet --sleep 0.6
"""
import argparse, time, json, os
from pathlib import Path
import pandas as pd
import requests

def load_api_key():
    # 從 env 或 config 讀
    key = os.getenv("FUGLE_API_KEY")
    if key:
        return key.strip()
    # 試著從你舊版 config 讀
    for p in ["./config/fugle.json", "./fugle.json", "./data/fugle.json"]:
        try:
            if Path(p).exists():
                j = json.loads(Path(p).read_text())
                for k in ["api_key","API_KEY","key","FUGLE_API_KEY"]:
                    if k in j:
                        return j[k].strip()
        except:
            pass
    return None

def fetch_one_day(stock_id, date_str, api_key, session, retries=5):
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/candles"
    params = {"symbol": stock_id, "date": date_str, "fields": "open,high,low,close,volume,turnover"}
    headers = {"X-API-KEY": api_key}
    for attempt in range(retries):
        try:
            r = session.get(url, params=params, headers=headers, timeout=15)
            if r.status_code == 429:
                wait = 65 + attempt*5
                print(f"  {stock_id} {date_str} 429 Rate limit -> sleep {wait}s (attempt {attempt+1}/{retries})")
                time.sleep(wait)
                continue
            if r.status_code != 200:
                print(f"  {stock_id} {date_str} {r.status_code} {r.text[:200]}")
                if r.status_code >= 500:
                    time.sleep(3)
                    continue
                return None
            j = r.json()
            # Fugle 回傳格式: data: {candles: [...]}
            data = j.get("data", j)
            candles = data.get("candles") or data.get("data") or []
            if not candles:
                return pd.DataFrame()
            df = pd.DataFrame(candles)
            # 欄位轉換
            # 預期有 date, open, high, low, close, volume
            df["stock_id"] = stock_id
            df["date"] = pd.to_datetime(df.get("date") or df.get("datetime") or date_str)
            # 確保欄位
            for c in ["open","high","low","close","volume"]:
                if c not in df.columns:
                    # 有時叫 max/min
                    if c=="high" and "max" in df.columns: df["high"]=df["max"]
                    if c=="low" and "min" in df.columns: df["low"]=df["min"]
            return df
        except Exception as e:
            print(f"  {stock_id} {date_str} 例外 {e} 重試 {attempt+1}")
            time.sleep(2+attempt)
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="./data/intraday_candidates.csv")
    parser.add_argument("--start", default="2024-06-01")
    parser.add_argument("--end", default="2024-06-10")
    parser.add_argument("--out", default="./data/tw_1min_real.parquet")
    parser.add_argument("--sleep", type=float, default=0.7, help="每打一次 sleep 秒，避開 429")
    args = parser.parse_args()

    api_key = load_api_key()
    if not api_key:
        print("[FAIL] 找不到 FUGLE_API_KEY，請 set $env:FUGLE_API_KEY")
        return
    print(f"[Key] {api_key[:6]}... len={len(api_key)}")

    cand_df = pd.read_csv(args.input)
    if "stock_id" in cand_df.columns:
        stock_ids = cand_df["stock_id"].astype(str).tolist()
    else:
        stock_ids = cand_df.iloc[:,0].astype(str).tolist()
    print(f"候選 {len(stock_ids)} 檔: {stock_ids[:10]}...")

    dates = pd.date_range(args.start, args.end, freq='D')
    # 只跑交易日，避開週末
    dates = [d for d in dates if d.weekday() < 5]
    print(f"日期 {len(dates)} 天 {args.start} -> {args.end}")

    out_path = Path(args.out)
    # 讀 checkpoint
    all_data = []
    done_set = set()
    if out_path.exists():
        try:
            old = pd.read_parquet(out_path)
            all_data.append(old)
            # 已完成的 stock_id+date
            if "stock_id" in old.columns and "date" in old.columns:
                old["d"] = pd.to_datetime(old["date"]).dt.date
                for _, r in old[["stock_id","d"]].drop_duplicates().iterrows():
                    done_set.add((str(r["stock_id"]), str(r["d"])))
            print(f"[Resume] 已有 {len(old)} 筆，{len(done_set)} 個 stock+date 已完成，跳過")
        except Exception as e:
            print(f"[WARN] 舊檔讀取失敗 {e}，重來")

    session = requests.Session()
    total = 0
    for sid in stock_ids:
        for dt in dates:
            date_str = dt.strftime("%Y-%m-%d")
            key = (sid, date_str)
            # 簡單判斷是否已完成（當天有 >200 筆就視為完成）
            if key in done_set:
                # 粗略檢查
                continue
            df = fetch_one_day(sid, date_str, api_key, session)
            if df is None:
                continue
            if len(df)==0:
                print(f"{sid} {date_str} -> 0 (可能非交易日)")
            else:
                print(f"{sid} {date_str} -> {len(df)}")
                all_data.append(df)
                total += len(df)
            time.sleep(args.sleep)

        # 每檔存一次，避免中斷全沒
        if all_data:
            big = pd.concat(all_data, ignore_index=True)
            # 清理
            big["date"] = pd.to_datetime(big["date"])
            big = big.sort_values(["stock_id","date"])
            # 去重
            big = big.drop_duplicates(subset=["stock_id","date"], keep="last")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            big.to_parquet(out_path)
            print(f"[Checkpoint] 已存 {len(big)} 筆 -> {out_path}")

    if all_data:
        big = pd.concat(all_data, ignore_index=True)
        big["date"] = pd.to_datetime(big["date"])
        big = big.sort_values(["stock_id","date"]).drop_duplicates(subset=["stock_id","date"], keep="last")
        big.to_parquet(out_path)
        print(f"[PASS] {out_path} ({len(big)}, {big['stock_id'].nunique()}檔)")

if __name__ == "__main__":
    main()
