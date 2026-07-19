import comtypes.client, time, pandas as pd
from pathlib import Path
SKCOM_DLL = r"C:\SKCOM\SKCOM.dll"
comtypes.client.GetModule(SKCOM_DLL)
import comtypes.gen.SKCOMLib as sk
ticks=[]
class E:
    def OnNotifyTicks(self, m, idx, p, d, t, micro, bid, ask, close, qty, sim):
        price=close/100.0
        h=t//10000; mm=(t%10000)//100; s=t%100
        from datetime import datetime
        dt=datetime.now().replace(hour=h, minute=mm, second=s, microsecond=micro*1000)
        ticks.append({"datetime":dt,"close":price,"volume":qty})
    def OnNotifyHistoryTicks(self, m, idx, p, d, t, micro, bid, ask, close, qty, sim):
        self.OnNotifyTicks(m,idx,p,d,t,micro,bid,ask,close,qty,sim)

skC=comtypes.client.CreateObject(sk.SKCenterLib, interface=sk.ISKCenterLib)
skQ=comtypes.client.CreateObject(sk.SKQuoteLib, interface=sk.ISKQuoteLib)
uid="N122507948"
pwd=input("密碼:")
print(skC.SKCenterLib_Login(uid,pwd))
ev=E(); comtypes.client.GetEvents(skQ, ev)
skQ.SKQuoteLib_EnterMonitor()
time.sleep(2)
skQ.SKQuoteLib_RequestTicks(0,"2330")
print("收30秒")
import pythoncom
for _ in range(300):
    pythoncom.PumpWaitingMessages(); time.sleep(0.1)
df=pd.DataFrame(ticks).sort_values("datetime").set_index("datetime")
k=df['close'].resample('1min').ohlc()
k['volume']=df['volume'].resample('1min').sum()
k=k.dropna().reset_index(); k['stock_id']="2330"
Path("./data").mkdir(exist_ok=True)
k.to_parquet("./data/tw_1min_real.parquet", index=False)
print(k.head())
