# Intraday-Lab v4.1 架構規格書 - Architect: Muse Spark 1.1
> 目標：從條件Pass推進到真實1分K可交易驗證，支援 IS/OOS/盲測與Paper Trading + 全市場篩選
> 分工：Architect/Harness/Loop = Muse, Coding = Fable 5 (審計+風控) + GPT-5.6 Sol (高速策略迭代)
> 執行環境：Claude Code / Codex (使用者本地) + PowerShell 7 (Windows)
> 更新日誌 v4 -> v4.1：補 Fugle 免費版陷阱、2000檔篩選、多檔架構、PowerShell 踩雷
> 日期: 2026-07-17

## 1. 系統總覽
```
Data Layer (FinMind日線真實 + Fugle今日266根 + SKCOM歷史K權限 -> tw_1min_real.parquet)
  -> Screening Layer (2000檔 -> 量能>5000張 + 振幅>3% + 籌碼 + 題材 -> 30~50檔) [v4.1新增]
  -> Feature Layer (日內特徵, groupby date, 無未來)
  -> Strategy Layer (A/B/C 插件式, 支援單檔與多檔 portfolio)
  -> Risk Layer (單筆停損0.8%, 單日熔斷-2%, 13:00禁開, 單日12筆, 不跨夜, 流動性熔斷)
  -> Execution Layer (1根K持有, 市價模擬, 滑價敏感度測試, 多檔併發控制)
  -> Eval Layer (PF, Win, MDD, Equity, StopCnt, CbDays, 隨機對照, 多檔熱力圖)
  -> Report Layer (單一真相成本, 實際天數, 雙層合成警告, 資料來源揭露)
```

## 2. 資料契約 (Data Contract)
### 2.1 真實1分K (優先)
- 路徑: ./data/tw_1min_real.parquet
- 欄位: datetime[ns, 統一 tz-naive Asia/Taipei, 若來源+08:00需 tz_localize(None)], open, high, low, close, volume, stock_id[str]
- 粒度: 理論 270根/天 09:00-13:30, 實務 Fugle 回 266根 (前4分無成交), 允許 260~270
- 驗證:
  - df.groupby([stock_id, date]).size() 不可重複
  - 同一 stock_id+datetime 不可重複 (曾出現 266*21=5586 bug)
  - OHLC 不可全天相同 (如 2375/2385 全天相同即廢檔)
  - datetime 不可全部等於今天 (代表 intraday API 被當歷史用)

### 2.2 日線 Fallback (長回測用)
- 來源: tw_market_daily.parquet (FinMind 真日線 2022-2024, 2000檔真實)
- 合成: simulate_1min_from_daily (linspace+randn*(h-l)*0.08)
- 用途: 2年回測, 解決 Fugle 免費版無歷史1分K, 必須印 "合成日線 (雙層合成警告)"
- 備份: copy ./data/tw_1min_real.parquet ./data/tw_1min_real_202301_3510.parquet -Force (PowerShell 注意空白)

### 2.3 Fugle API 限制 (v4.1 新增 血淚)
- intraday/candles/{symbol} 只回今天, 傳 from=2023-01-01 會被忽略, loop 21天會變 5586重複
- 歷史1分K需付費 $2999/月, 免費版歷史只能日K
- Key: 環境變數 FUGLE_API_KEY 值為 Base64原文 (含兩個UUID空格), 不可自行解碼, 直接放 X-API-KEY
- 限流 60/min, sleep 1.1s, 401即停
- 正確用法:
  - 回測: 用 2.2 合成
  - Paper: fetch_fugle_intraday_1min_final.py --start TODAY --end TODAY --out ./data/tw_1min_today.parquet

### 2.4 全市場多檔契約 (v4.1 新增)
- 來源: tw_market_daily.parquet 2000檔
- 單檔: 2330 代表權值
- 多檔: 50檔組合 0050+金融+傳產, 驗證非過擬合單股
- 全量2000檔僅跑 Screening, 不跑1分K (1.35億根筆電會炸)
- 必須含 stock_id, backtest 需 groupby [stock_id, date]

## 3. 核心模組介面 (給F5/Sol實作)

### 3.0 Screening 模組 (v4.1 新增, 對應使用者上傳的當沖篩選表)
- 檔案: screen_stocks.py
- 指標面向 (來自圖片):
  - 量能: 日均成交量 > 5,000張, 20日均, 流動性高不卡單
  - 波動: 日內振幅 >3% 或平均波動率高, 當沖靠價差
  - 籌碼: 外資/投信/主力進出明顯, 短線資金流向清楚 (FinMind 籌碼表, 連3天同向)
  - 技術面: 5分K-1分K均線糾結或突破, 短線支撐壓力明顯, 利於判斷進出點
  - 題材: 熱門族群 AI/半導體/電動車, 有新聞加持短線活躍 (產業對照表)
- 使用方式:
  - 先用成交量排行篩冷門股
  - 再看振幅排行挑波動大標的
  - 最後籌碼+題材精篩到30-50檔
- 輸出: ./data/intraday_candidates.csv (stock_id, avg_vol20, avg_amp, reason)

### 3.1 strategy_A(df) -> df with signal
- Input: df 含 datetime, close, stock_id
- Output: df['signal'] in {-1,0,1}
- 約束:
  - ret_30 = groupby([stock_id,date]).pct_change(30) 不可跨日跨股
  - 13:00後 signal=0
  - cum>12截斷
  - 不可注入隨機 (零交易就回報零交易)
  - 多檔時需 groupby stock_id 獨立算訊號

### 3.2 backtest(df, fee, tax, slippage, stop_loss=0.008, daily_stop=-0.02)
- pos = signal.shift(1) groupby stock_id, 首根=0
- pnl_gross_raw = pos * groupby([stock_id,date]).pct_change(close)
- 停損: if pnl_gross_raw < -stop_loss => -stop_loss
- 成本: cost_rt = 2*fee+tax+2*slippage, 單一真相
- pnl_net_pre = pnl_gross - cost_rt*|pos|
- 熔斷: cum_daily = groupby([stock_id,date]).cumsum(pnl_net_pre); if < daily_stop => 當日剩餘 pos=0
- 指標: trades, win, PF, MDD, equity, stop_cnt, cb_days + 多檔 breakdown

### 3.3 風控模組 (risk.py) - F5負責審計
- 函式: apply_risk(df, stop_loss, daily_stop, max_per_day=12, cutoff="13:00")
- 必須被所有策略呼叫, 單元測試: 13:00後0訊號, 單日最多12, 觸發熔斷後無倉
- v4.1新增: 流動性熔斷, 若 avg_vol20<5000 則當日禁開

## 4. Harness 設計 (Muse負責)

### 4.1 評測Harness (eval_harness.py)
- 入口: python eval_harness.py --config configs/is_oos.yaml
- 功能:
  - 自動切換 fast(22天)/full(252天)/IS(2022-2024)/OOS(2025)/盲測(2026H1)
  - 3次seed=42驗證可重現 (md5比對)
  - 壓測: fee*2, slippage 0.05%->0.2%, 隨機對照組 (同成本, 隨機訊號, N=100)
  - 滑價敏感度硬門檻: PF<1 or equity<0.9 => FAIL
  - v4.1新增: --universe 參數, 支援 1檔/50檔/2000檔篩選模式, 輸出多檔熱力圖

### 4.2 Paper Trading Harness (paper_trading_runner.py)
- T07: 跑完回測自動進入30天模擬交易日誌
- 輸入: ./data/tw_1min_today.parquet (Fugle今日266根真實)
- 輸出: logs/paper_YYYY-MM-DD.jsonl, 含 datetime, stock_id, signal, pos, pnl_net, hit_stop, breached
- 供Fable5盲測驗收
- v4.1: 需支援定時抓 Fugle 今天, 並自動對比 50檔候選的當日振幅

### 4.3 Screening Harness (v4.1 新增)
- 入口: python screen_stocks.py --min_vol 5000 --min_amp 0.03 --top_n 50
- 輸入: tw_market_daily.parquet
- 輸出: intraday_candidates.csv + screening_report.md
- 驗收: 2000檔 -> 30~50檔, 電子股占比 60%+, 平均振幅>3%

## 5. Loop Engineering (Muse負責)
### 5.1 迭代Loop
```
Spec -> F5/Sol Code (Claude Code/Codex) -> Screening -> Harness Auto Test -> Report -> Fable5 Review -> Patch -> 回到Spec
```
- 每次Loop產物: minimal_fix.patch + main_patched.py + review_response.md + screening_log
- 禁止寫死數字, 所有報告數字必須來自實算函式回傳

### 5.2 速度優化
- Sol負責策略B/C快速原型, F5負責風控與審計patch, Muse合併衝突, 保證單一真相

## 6. 驗收清單 (給Fable5)
- [ ] 無未來函數 shift(1), groupby([stock_id,date])
- [ ] Seed可重現 3次完全一致
- [ ] 成本完整 2*fee+tax+2*slip 計在pos列
- [ ] 風控6項皆有程式碼與單測 (含流動性熔斷)
- [ ] 誠實性 無寫死PF/勝率, 雙層合成警告, 滑價崩潰如實揭露, Fugle資料來源揭露 (合成/今日真實)
- [ ] 可替換性 tw_1min_real.parquet 存在即自動切換, 且驗證無重複datetime
- [ ] 滑價敏感度達標 PF>1且equity>0.9 (0.05%->0.2%)
- [ ] [v4.1新增] Screening可重現 2000->50, 量能>5000張, 振幅>3% 有log
- [ ] [v4.1新增] 多檔回測 50檔 PF分布圖, 非單一2330過擬合
- [ ] [v4.1新增] Paper Trading 使用 Fugle今日266根真實, 非合成

## 7. 下一步任務分配 (直接貼給Claude Code/Codex)

### Task-1 (Sol, 高速): 實作 Strategy B 動能突破
- 輸入: 真實1分K, 昨日高低, 開盤區間
- 輸出: signal, 需通過Harness fast測試

### Task-2 (F5, 審計): 補強 risk.py 單元測試 + 熔斷邏輯邊界
- 測試案例: 13:00整點, 單日剛好12筆第13筆截斷, 熔斷當根是否計入, 流動性<5000張禁開

### Task-3 (Muse, Harness): 完成 eval_harness.py 與 paper_trading_runner.py 空殼
- 讓F5產出的不是神器, 是一份站得住腳的研究報告, 包含它在哪裡會失效

### Task-4 (Sol, v4.1新增): 實作 screen_stocks.py 全市場篩選
- 輸入: tw_market_daily.parquet 2000檔
- 邏輯: 量能>5000張 + 振幅>3% + 籌碼連3天同向 + 題材AI/半導體/電動車
- 輸出: intraday_candidates.csv 50檔 + screening_report.md
- 驗收: 跑 python screen_stocks.py 出 30~50檔, 電子60%

### Task-5 (F5, v4.1新增): 多檔 backtest 支援
- 修改 backtest() 支援 groupby stock_id, 輸出 per-stock PF, 多檔熱力圖
- 壓測 50檔 1個月 (3510*50=175k根) 筆電可跑完
- 驗收: python main.py --universe 50 --mode fast 出熱力圖

## 8. 報告產出規範 (v4.1新增, 給F5/Sol填)
### 8.1 必須產生的報告
所有程式改完後, 必須在 `./reports/` 下產生以下檔案, 格式照 `report_template.md`:
- `screening_report.md` - 2000->50 的log, 含 Top5, 平均量能振幅
- `backtest_report.md` - main.py fast/full 的 trades/win/PF/MDD/stop_cnt
- `harness_report.json` - eval_harness.py 6項 PASS/FAIL + md5
- `paper_report.md` - Fugle 266根 當日PnL, 不可是5586

### 8.2 報告模板
- 模板檔: `report_template.md` (已附在同層)
- Fable 5 填完 -> 丟給 5.6 Sol 填 Review
- Sol 簽完 -> 統一打包丟回給 Muse + User
- 禁止口頭回報數字, 全部以報告檔為準, 數字必須來自實算

### 8.3 Loop 流程定義 (正式版)
```
[Architect: Muse] SPEC v4.1 + report_template.md
      |
      v
[User] 你 -> 把 intraday_lab_full 資料夾 + SPEC + template 放到 local
      |
      v
[Fable 5 Code] 實作/重構 screen_stocks.py, main.py, risk.py
      | 產出: screening_report.md + backtest_report.md + harness_report.json (照template)
      v
[5.6 Sol Review] 審效能與邊界, 在 template 第8節寫 Review 結論, 簽 [ ] 建議合併
      |
      v
[Muse Handle] 我審誠實性/無未來/成本單一真理/5586陷阱, 產出 SPEC v4.2 + patch
      |
      v
[User] 你再帶回給 Fable 5 下一輪
```

---
Architect簽核: Muse Spark 1.1
日期: 2026-07-17 v4.1 (補Fugle陷阱+2000檔篩選+多檔架構+報告規範)
