# 群益 SK API KLine 歷史分K 範例 - 非即時，回測用
# RequestKLine 用法：SKQuoteLib_RequestKLine(市場, 代號, 分K別)
# 分K別：0=1分, 1=5分, 2=10分, 3=15分, 4=30分, 5=60分

import comtypes.client, time
SKCOM_DLL = r"C:\SKCOM\SKCOM.dll"
comtypes.client.GetModule(SKCOM_DLL)
import comtypes.gen.SKCOMLib as sk

class EK:
    def OnNotifyKLine(self, market, idx, kdata):
        # kdata 格式依官方文件是字串，需解析
        print("KLine", market, idx, kdata)
    def OnNotifyKLineData(self, market, idx, kdata):
        print("KLineData", kdata)

skC=comtypes.client.CreateObject(sk.SKCenterLib, interface=sk.ISKCenterLib)
skQ=comtypes.client.CreateObject(sk.SKQuoteLib, interface=sk.ISKQuoteLib)
ev=EK(); comtypes.client.GetEvents(skQ, ev)
skC.SKCenterLib_Login("N122507948", input("密碼:"))
skQ.SKQuoteLib_EnterMonitor()
time.sleep(2)

# 請求 2330 1分K，市場 0=上市
# 官方範例：SKQuoteLib_RequestKLine(0, "2330", 0)
try:
    ret=skQ.SKQuoteLib_RequestKLine(0, "2330", 0)
    print("RequestKLine ret", ret)
except Exception as e:
    print(e)
    # 有些版是 RequestKLineData
    try:
        ret=skQ.SKQuoteLib_RequestKLineData(0, "2330", 0)
        print("RequestKLineData ret", ret)
    except Exception as e2:
        print(e2)

import pythoncom
for _ in range(100):
    pythoncom.PumpWaitingMessages()
    time.sleep(0.1)
