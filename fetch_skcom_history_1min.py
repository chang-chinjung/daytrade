"""
群益證券 SKCOM 歷史 1分K 回測管線
路徑：C:\\SKCOM\\元件\\x64\\SKCOM.dll (依你截圖)
功能：抓 2330 等多檔 2022-2024 歷史 Tick -> 轉 1分K -> 存 data/tw_1min_real.parquet

前置：
1. 已安裝群益 API，路徑存在
2. pip install comtypes pandas pyarrow
3. 群益帳號已開通 API，且策略王可登入

用法：
python fetch_skcom_history_1min.py --stocks 2330,2317,2454 --start 2023-01-01 --end 2023-01-31 --out ./data/tw_1min_real.parquet

注意：群益歷史 Tick 一次一天，一天約 3000~5000 筆，回補慢，請耐心等
"""
import argparse
import time
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

SKCOM_PATH = r"C:\SKCOM\元件\x64\SKCOM.dll"

# 載入 COM
import comtypes.client
comtypes.client.GetModule(SKCOM_PATH)
import comtypes.gen.SKCOMLib as sk

# 全域暫存
ticks_data = {}
current_stock = None

class SKQuoteEvent:
    def __init__(self):
        self.connected = False
        
    def OnConnection(self, nKind, nCode):
        # nKind 1=報價主機連線, nCode 0=成功, 3001=報價連線成功
        print(f"[SK] OnConnection kind={nKind} code={nCode}")
        if nCode == 0 or nCode == 3001:
            self.connected = True

    def OnNotifyHistoryTicks(self, sMarketNo, sStockIdx, nPtr, nDate, nTimehms, nTimemicro, nBid, nAsk, nClose, nQty, nSimulate):
        # 歷史 Tick 回補
        global ticks_data, current_stock
        try:
            # nDate: 20230103, nTimehms: 93000
            date_str = str(nDate)
            time_str = f"{nTimehms:06d}"  # 093000
            dt = datetime.strptime(f"{date_str} {time_str}", "%Y%m%d %H%M%S")
            # 微秒
            dt = dt.replace(microsecond=nTimemicro*1000)
            price = nClose / 100.0  # 群益價格*100
            if current_stock not in ticks_data:
                ticks_data[current_stock] = []
            ticks_data[current_stock].append({
                "datetime": dt,
                "price": price,
                "volume": nQty,
                "bid": nBid/100.0,
                "ask": nAsk/100.0
            })
        except Exception as e:
            print(f"解析 Tick 失敗 {e}")

    def OnNotifyTicks(self, sMarketNo, sStockIdx, nPtr, nDate, nTimehms, nTimemicro, nBid, nAsk, nClose, nQty, nSimulate):
        # 即時 Tick (Paper Trading 用)
        self.OnNotifyHistoryTicks(sMarketNo, sStockIdx, nPtr, nDate, nTimehms, nTimemicro, nBid, nAsk, nClose, nQty, nSimulate)

    def OnNotifyKLineData(self, sMarketNo, sStockIdx, bstrKLineData):
        # 有些版本 KLine 直接回字串
        print(f"[KLine] {sStockIdx} {bstrKLineData[:100]}")

def login():
    skC = comtypes.client.CreateObject(sk.SKCenterLib, interface=sk.ISKCenterLib)
    skQ = comtypes.client.CreateObject(sk.SKQuoteLib, interface=sk.ISKQuoteLib)
    
    # 事件綁定
    quote_event = SKQuoteEvent()
    handler = comtypes.client.GetEvents(skQ, quote_event)
    
    print("請輸入群益帳號密碼 (同策略王)")
    user_id = input("帳號 (例 N122507948): ").strip()
    import getpass
    pwd = getpass.getpass("密碼: ").strip()
    
    # 登入
    ret = skC.SKCenterLib_Login(user_id, pwd)
    print(f"Login 回傳 {ret} {skC.SKCenterLib_GetReturnCodeMessage(ret)}")
    if ret != 0:
        print("登入失敗，請檢查帳密或是否已在策略王登入")
        sys.exit(1)
    
    # 進入監控
    ret = skQ.SKQuoteLib_EnterMonitor()
    print(f"EnterMonitor {ret}")
    time.sleep(2)
    
    return skC, skQ, quote_event

def request_history_ticks(skQ, stock_code, date_str):
    """
    請求單日歷史 Tick
    stock_code: 2330
    date_str: 20230101
    """
    global current_stock
    current_stock = f"{stock_code}_{date_str}"
    ticks_data[current_stock] = []
    
    # 群益請求歷史 Tick 需指定 Page
    # Page = 0 自動分配
    # 市場別 0=上市, 1=上櫃, 2=期貨
    market_no = 0
    # 清空舊資料
    skQ.SKQuoteLib_RequestTicks(0, stock_code)
    # 等待回補
    print(f"  等待 {stock_code} {date_str} Tick 回補...")
    timeout = 15
    start_t = time.time()
    while time.time() - start_t < timeout:
        import pythoncom
        pythoncom.PumpWaitingMessages()
        time.sleep(0.1)
        # 若收到 >100 筆可提早結束
        if len(ticks_data.get(current_stock, [])) > 2000:
            time.sleep(1)
            break
    count = len(ticks_data.get(current_stock, []))
    print(f"  -> 收到 {count} 筆 Tick")
    return ticks_data.get(current_stock, [])

def ticks_to_1min(ticks):
    if not ticks:
        return pd.DataFrame()
    df = pd.DataFrame(ticks)
    df = df.sort_values("datetime")
    df.set_index("datetime", inplace=True)
    # Resample 1分K
    ohlc = df['price'].resample('1min').ohlc()
    vol = df['volume'].resample('1min').sum()
    k = pd.concat([ohlc, vol], axis=1).dropna()
    k = k.rename(columns={"open":"open","high":"high","low":"low","close":"close","volume":"volume"})
    return k.reset_index()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stocks', default='2330', help='逗號分隔')
    ap.add_argument('--start', default='2023-01-01')
    ap.add_argument('--end', default='2023-01-31')
    ap.add_argument('--out', default='./data/tw_1min_real.parquet')
    args = ap.parse_args()
    
    skC, skQ, ev = login()
    
    # 等連線
    print("等待報價主機連線 3001...")
    for _ in range(20):
        import pythoncom
        pythoncom.PumpWaitingMessages()
        time.sleep(0.5)
        if ev.connected:
            break
    if not ev.connected:
        print("警告: 未收到 3001 連線成功，但繼續嘗試")
    
    stocks = [s.strip() for s in args.stocks.split(',')]
    start_dt = datetime.strptime(args.start, "%Y-%m-%d")
    end_dt = datetime.strptime(args.end, "%Y-%m-%d")
    
    all_k = []
    cur = start_dt
    while cur <= end_dt:
        # 跳過週末
        if cur.weekday() >= 5:
            cur += timedelta(days=1)
            continue
        date_str = cur.strftime("%Y%m%d")
        print(f"\n=== {cur.strftime('%Y-%m-%d')} ===")
        for stock in stocks:
            ticks = request_history_ticks(skQ, stock, date_str)
            if ticks:
                k1 = ticks_to_1min(ticks)
                if not k1.empty:
                    k1['stock_id'] = stock
                    k1['date'] = cur.date()
                    # 只留 09:00-13:30
                    k1 = k1[(k1['datetime'].dt.time >= pd.Timestamp("09:00").time()) & 
                            (k1['datetime'].dt.time <= pd.Timestamp("13:30").time())]
                    all_k.append(k1)
            time.sleep(1.2)  # 避免過快被限流
        cur += timedelta(days=1)
    
    if not all_k:
        print("沒有抓到任何 K 棒")
        return
    
    final = pd.concat(all_k, ignore_index=True)
    final = final[["datetime","open","high","low","close","volume","stock_id"]].sort_values(["stock_id","datetime"])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    final.to_parquet(out, index=False)
    print(f"\n=== 完成 {out} shape={final.shape} ===")
    print(final.groupby('stock_id').agg(rows=('close','count'), start=('datetime','min'), end=('datetime','max')))
    print("此檔可直接給 main.py --mode fast 吃")

if __name__ == "__main__":
    main()
