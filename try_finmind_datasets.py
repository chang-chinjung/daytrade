import os, requests, pandas as pd
from pathlib import Path

def try_fetch(dataset, stock, start, end, token):
    for ver in ["v4","v3"]:
        url=f"https://api.finmindtrade.com/api/{ver}/data"
        params={"dataset":dataset,"data_id":stock,"start_date":start,"end_date":end,"token":token}
        hdr={"Authorization": f"Bearer {token}"} if token else {}
        try:
            r=requests.get(url, params=params, headers=hdr, timeout=20)
            print(f"[{ver}] {dataset} {stock} {start}~{end} -> {r.status_code}")
            if r.status_code==200:
                j=r.json()
                print(f"  msg={j.get('msg')} count={len(j.get('data',[]))}")
                if j.get('data'):
                    print(j['data'][:1])
                    return True
            else:
                print(r.text[:800])
        except Exception as e:
            print(f"  ex {e}")
    return False

token=os.getenv("FINMIND_TOKEN","")
if not token:
    print("set FINMIND_TOKEN first")
else:
    # 試你說的 2023-01
    for ds in ["TaiwanStockMinutePrice","TaiwanStockPrice","TaiwanStockTradingDailyReport","TaiwanStockPriceMinute","TaiwanStockTick"]:
        try_fetch(ds,"2330","2023-01-01","2023-01-31",token)
