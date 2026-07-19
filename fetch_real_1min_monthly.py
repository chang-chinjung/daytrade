import os, time, sys
from pathlib import Path
import pandas as pd
import requests
API="https://api.finmindtrade.com/api/v4/data"

def months(s,e):
    s=pd.Timestamp(s); e=pd.Timestamp(e); cur=s; out=[]
    while cur<=e:
        me=(cur+pd.offsets.MonthEnd(0))
        if me>e: me=e
        out.append((cur.strftime("%Y-%m-%d"), me.strftime("%Y-%m-%d")))
        cur=me+pd.Timedelta(days=1)
    return out

def one(stock,s,e,token):
    params={"dataset":"TaiwanStockMinutePrice","data_id":str(stock),"start_date":s,"end_date":e,"token":token}
    hdr={"Authorization": f"Bearer {token}"} if token else {}
    r=requests.get(API, params=params, headers=hdr, timeout=30)
    print(f"GET {s}~{e} -> {r.status_code}")
    if r.status_code!=200:
        print(r.text[:500])
        raise RuntimeError(f"status {r.status_code}")
    j=r.json()
    if j.get("msg")!="success":
        raise RuntimeError(str(j)[:500])
    data=j.get("data",[])
    if not data:
        raise RuntimeError("empty")
    df=pd.DataFrame(data)
    if "Time" in df.columns:
        df["datetime"]=pd.to_datetime(df["date"].astype(str)+" "+df["Time"].astype(str))
    else:
        df["datetime"]=pd.to_datetime(df["date"])
    df["stock_id"]=df["stock_id"].astype(str)
    if "Trading_Volume" in df.columns:
        df["volume"]=df["Trading_Volume"]
    for c in ["open","high","low","close","volume"]:
        df[c]=pd.to_numeric(df[c], errors='coerce')
    df=df[["datetime","open","high","low","close","volume","stock_id"]].sort_values("datetime")
    df=df[(df["datetime"].dt.time>=pd.Timestamp("09:00").time()) & (df["datetime"].dt.time<=pd.Timestamp("13:30").time())]
    return df

def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument('--stocks', default='2330')
    ap.add_argument('--start', default='2023-01-01')
    ap.add_argument('--end', default='2023-12-31')
    ap.add_argument('--out', default='./data/tw_1min_real.parquet')
    args=ap.parse_args()
    token=os.getenv("FINMIND_TOKEN","")
    out=Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    all_df=[]
    for stock in [x.strip() for x in args.stocks.split(',') if x.strip()]:
        dfs=[]
        for s,e in months(args.start, args.end):
            try:
                print(f"[{stock}] {s}~{e}")
                df=one(stock,s,e,token)
                print(f"  -> {len(df)}")
                dfs.append(df)
            except Exception as ex:
                print(f"  fail {ex}")
            time.sleep(1)
        if dfs:
            final=pd.concat(dfs, ignore_index=True).drop_duplicates(["stock_id","datetime"]).sort_values("datetime")
            all_df.append(final)
    if not all_df:
        print("all fail"); sys.exit(1)
    final=pd.concat(all_df, ignore_index=True).sort_values(["stock_id","datetime"]).drop_duplicates(["stock_id","datetime"])
    final.to_parquet(out, index=False)
    print(f"DONE {out} shape={final.shape}")
    print(final.groupby('stock_id').agg(rows=('close','count'), start=('datetime','min'), end=('datetime','max')))

if __name__=="__main__":
    main()
