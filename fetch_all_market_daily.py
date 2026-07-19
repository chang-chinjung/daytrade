"""
fetch_all_market_daily_v2.py - 修復 Token illegal + 支援無 token 抓 100檔測試
用法:
  python fetch_all_market_daily_v2.py --start 2022-01-01 --out ./data/tw_market_daily_all.parquet --max_stocks 100
  (先用 100 檔測試，通了再 1000)

如果有 FinMind token 設環境變數:
  $env:FINMIND_TOKEN="eyJ0..."
"""
import argparse, time, os
from pathlib import Path
import pandas as pd

try:
    from FinMind.data import DataLoader
    HAS_FINMIND = True
except:
    HAS_FINMIND = False
    print("[FAIL] 請 pip install FinMind")

def get_stock_list_fallback():
    # 50檔電子+傳產+金融，夠你先跑 2000->50 的邏輯
    return ["2330","2317","2454","2303","2382","2357","2308","2301","2002","1301","1303","2603","2609","2615","2618","2881","2882","2891","2886","2880","2412","3045","3037","3034","3008","2379","2382","2409","2408","2474","2481","2353","2327","2313","2303","2324","2347","2376","2385","2395","2404","2449","2458","2498","2501","2606","2610","2637","2645","2801","2809","2812","2820","2834","2883","2884","2885","2887","2890","2892","2912","3481","3533","3707","3711","4904","4938","5876","5880","1101","1102","1216","1229","1232"]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--out", default="./data/tw_market_daily_all.parquet")
    parser.add_argument("--max_stocks", type=int, default=100, help="先抓100檔測試，通了再1000")
    args = parser.parse_args()

    dl = DataLoader()
    token = os.getenv("FINMIND_TOKEN")
    if token:
        try:
            dl.login_by_token(api_token=token)
            print("[INFO] Token 登入成功")
        except Exception as e:
            print(f"[WARN] Token 登入失敗 Token is illegal -> 改用無 token 模式 (只能抓少許): {e}")
            dl = DataLoader() # 重置，不登入
    else:
        print("[INFO] 沒設 FINMIND_TOKEN，用無 token 模式 (100檔還行，2000檔會限流)")

    # 1. 拿清單
    try:
        info = dl.taiwan_stock_info()
        stock_ids = info['stock_id'].unique().tolist()
        print(f"[INFO] API 拿到清單 {len(stock_ids)} 檔")
    except Exception as e:
        print(f"[WARN] taiwan_stock_info 失敗 {e}，改用 fallback 70檔清單")
        stock_ids = get_stock_list_fallback()

    stock_ids = stock_ids[:args.max_stocks]
    print(f"準備抓 {len(stock_ids)} 檔，從 {args.start}")

    all_df = []
    fail = 0
    for i, sid in enumerate(stock_ids):
        try:
            df = dl.taiwan_stock_daily(stock_id=sid, start_date=args.start)
            if len(df)==0:
                continue
            # 統一欄位 max/min -> high/low，方便 screen_stocks
            df = df.rename(columns={"max":"high","min":"low","Trading_Volume":"volume"})
            all_df.append(df)
            print(f"{i+1}/{len(stock_ids)} {sid} {len(df)}筆")
            time.sleep(0.35) # 避免限流
        except Exception as e:
            fail+=1
            print(f"[WARN] {sid} 失敗 {e}")
            time.sleep(1.5)
            if fail>10 and i<20:
                print("[FAIL] 連續失敗太多，可能是 token 或限流，先停")
                break

    if not all_df:
        print("[FAIL] 一筆都沒抓到，請檢查 token 或改用 fallback 單檔測試")
        return

    big = pd.concat(all_df, ignore_index=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    big.to_parquet(args.out)
    print(f"[PASS] 已產生 {args.out} shape={big.shape} 檔數={big['stock_id'].nunique()}")

if __name__ == "__main__":
    main()
