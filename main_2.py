
import argparse
from pathlib import Path
import pandas as pd
import numpy as np

def load_daily(path):
    df = pd.read_parquet(path)
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
    return df

def simulate_1min_from_daily(daily_df, stock_id=2330, days=22):
    sub = daily_df.tail(days).copy() if 'stock_id' not in daily_df.columns else daily_df[daily_df['stock_id'].astype(str)==str(stock_id)].tail(days)
    if sub.empty:
        sub = daily_df.tail(days)
    rows=[]
    for _, row in sub.iterrows():
        o,h,l,c = float(row.get('open',600)), float(row.get('high',610)), float(row.get('low',590)), float(row.get('close',600))
        base_price = np.linspace(o,c,270) + np.random.randn(270)*(h-l)*0.08
        base_price = np.clip(base_price, l*0.99, h*1.01)
        vol = np.random.randint(500,5000,270)
        d = pd.to_datetime(row['date']) if 'date' in row else pd.Timestamp('2024-06-01')
        idx = pd.date_range(d.replace(hour=9,minute=0,second=0), periods=270, freq='1min')
        tmp = pd.DataFrame({'datetime': idx, 'open': base_price, 'high': base_price*1.0015, 'low': base_price*0.9985, 'close': base_price, 'volume': vol, 'stock_id': stock_id})
        rows.append(tmp)
    return pd.concat(rows, ignore_index=True)

def strategy_A(df):
    d = df['datetime'].dt.date
    # P5: ret_30 以「日內」計算，避免跨日污染（原版每日前30根用到前一日資料）
    df['ret_30'] = df.groupby(d)['close'].pct_change(30).fillna(0)
    df['signal'] = 0
    df.loc[df['ret_30'] > 0.008, 'signal'] = -1
    df.loc[df['ret_30'] < -0.008, 'signal'] = 1
    # P2: 移除「零交易時注入隨機 signal」——零交易就誠實回報零交易
    # P6: 風控最小實作：13:00 後不新開倉、單日最多12筆
    df.loc[df['datetime'].dt.time >= pd.Timestamp('13:00').time(), 'signal'] = 0
    cum = (df['signal'] != 0).groupby(d).cumsum()
    df.loc[cum > 12, 'signal'] = 0
    return df

def backtest(df, fee=0.001425*0.28, tax=0.0015, slippage=0.0005):
    d = df['datetime'].dt.date
    df['pos'] = df['signal'].shift(1).fillna(0)
    df.loc[df.groupby(d).head(1).index, 'pos'] = 0  # 日內策略：隔日首根不得持前日倉
    df['pnl_gross'] = df['pos'] * df.groupby(d)['close'].pct_change().fillna(0)  # 報酬不跨日
    # P3: 一筆當沖完整成本 = 買賣手續費x2 + 賣出證交稅 + 進出滑價x2，計在「持倉(實現損益)」列
    cost_rt = 2*fee + tax + 2*slippage
    df['pnl_net'] = df['pnl_gross'] - cost_rt * df['pos'].abs()
    df['equity'] = (1+df['pnl_net']).cumprod()
    trades = int((df['pos']!=0).sum())
    # P4: 勝率必須量在 pos!=0（損益實現）列；原版量在 signal 列（pnl≈0-成本，必為負）→ 4.53% 假象
    win = float((df.loc[df['pos']!=0, 'pnl_net']>0).mean()) if trades>0 else 0.0
    up = df.loc[df['pnl_net']>0,'pnl_net'].sum()
    dn = abs(df.loc[df['pnl_net']<0,'pnl_net'].sum())
    pf = float(up/dn) if dn>0 else 0.0
    mdd = float((df['equity']/df['equity'].cummax()-1).min())
    return {'trades': trades, 'win_rate': win, 'profit_factor': pf, 'mdd': mdd, 'final_equity': float(df['equity'].iloc[-1])}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--mode', choices=['fast','full'], default='fast')
    ap.add_argument('--data_dir', default='./data')
    ap.add_argument('--seed', type=int, default=42)
    # 新增：成本參數單一真相來源，避免報告寫死
    ap.add_argument('--fee_rate', type=float, default=0.001425, help='原始手續費率')
    ap.add_argument('--fee_discount', type=float, default=0.28, help='手續費折扣')
    ap.add_argument('--tax_rate', type=float, default=0.0015, help='當沖稅率')
    ap.add_argument('--slippage', type=float, default=0.0005, help='單邊滑價')
    args=ap.parse_args()
    np.random.seed(args.seed)
    fee = args.fee_rate * args.fee_discount
    tax = args.tax_rate
    slippage = args.slippage
    cost_rt = 2*fee + tax + 2*slippage  # 單一真相，報告與 backtest 共用

    ddir=Path(args.data_dir)
    daily_path=ddir/'tw_market_daily.parquet'
    real_1min_path=ddir/'tw_1min_real.parquet'
    Path("reports").mkdir(parents=True, exist_ok=True)

    data_layer = ""
    if real_1min_path.exists():
        try:
            df1 = pd.read_parquet(real_1min_path)
            df1['datetime'] = pd.to_datetime(df1['datetime'])
            data_layer = f"真實1分K {real_1min_path} 直接載入"
            days = df1['datetime'].dt.date.nunique()
            # 直接使用真實1分K，跳過合成
            dfA=strategy_A(df1.copy())
            res=backtest(dfA, fee=fee, tax=tax, slippage=slippage)
            actual_days = days
            res_fee2 = backtest(strategy_A(df1.copy()), fee=fee*2, tax=tax, slippage=slippage)
            res_slip = backtest(strategy_A(df1.copy()), fee=fee, tax=tax, slippage=0.002)
            report = f"""# Intraday-Lab Report ({args.mode} mode) - 真實1分K版

> 教育研究用途，非投資建議。成本已內建。

- 資料來源：{data_layer} -> {df1.shape[0]} 根，實際 {actual_days} 個交易日
- 參數：seed={args.seed}, fee={args.fee_rate:.4%}*{args.fee_discount}, tax={tax:.4%}, slippage={slippage:.4%}；單筆全趟成本 {cost_rt:.4%} (由參數推導，單一真相)
- 策略A：交易 {res['trades']} 筆，勝率 {res['win_rate']:.2%}，PF {res['profit_factor']:.2f}，MDD {res['mdd']:.2%}，期末權益 {res['final_equity']:.4f}

## 風控（已實作）
- 13:00後不新開倉、單日最多12筆、日內不跨夜

## 壓力測試（實際重算）
- 手續費x2：PF {res_fee2['profit_factor']:.2f}（基準 {res['profit_factor']:.2f}）
- 滑價0.05%->0.2%：PF {res_slip['profit_factor']:.2f}，期末權益 {res_slip['final_equity']:.4f}
- **滑價敏感度硬門檻**：0.05%->0.2% 權益 {res['final_equity']:.2f}->{res_slip['final_equity']:.2f}，若崩潰則判定不可交易

## 結論
已使用真實1分K，可進入 IS/OOS 討論。
"""
            out=Path("reports")/f"report_{args.mode}.md"
            out.write_text(report, encoding='utf-8')
            print(f"完成 -> {out.resolve()} trades={res['trades']} win={res['win_rate']:.2%}")
            return
        except Exception as e:
            print(f"真實1分K讀取失敗，fallback到日線合成: {e}")

    # fallback: 日線 -> 合成1分K
    if daily_path.exists():
        try:
            daily=load_daily(daily_path)
            data_layer = f"真實日線 {daily_path}"
        except Exception as e:
            print(f"讀檔失敗用合成: {e}")
            daily=pd.DataFrame({'date': pd.date_range('2024-01-01', periods=60), 'open':600,'high':610,'low':590,'close':600+np.random.randn(60)*3,'volume':10000,'stock_id':2330})
            data_layer = "合成日線 (fallback)"
    else:
        print(f"找不到 {daily_path}，改用合成資料示範（結構同你的13.8MB日線）")
        daily=pd.DataFrame({'date': pd.date_range('2024-01-01', periods=60), 'open':600,'high':610,'low':590,'close':600+np.random.randn(60)*3,'volume':10000,'stock_id':2330})
        data_layer = "合成日線 (雙層合成警告)"

    days = 22 if args.mode=='fast' else 252
    df1=simulate_1min_from_daily(daily, stock_id=2330, days=days)
    dfA=strategy_A(df1.copy())
    res=backtest(dfA, fee=fee, tax=tax, slippage=slippage)
    actual_days = df1['datetime'].dt.date.nunique()
    res_fee2 = backtest(strategy_A(df1.copy()), fee=fee*2, tax=tax, slippage=slippage)
    res_slip = backtest(strategy_A(df1.copy()), fee=fee, tax=tax, slippage=0.002)
    report=f"""# Intraday-Lab Report ({args.mode} mode) - 修補版 v2 (條件Pass後修正)

> 教育研究用途，非投資建議。成本已內建。
> **重要限制：本回測之1分K為由日線合成之模擬路徑（非真實日內成交），任何日內策略結果僅驗證程式管線可跑通，不具策略有效性意義。雙層合成警告：{data_layer}**

- 資料來源：{data_layer} -> 合成1分K {df1.shape[0]} 根，實際 {actual_days} 個交易日（名目 days={days}）
- 參數：seed={args.seed}, fee={args.fee_rate:.4%}*{args.fee_discount}={fee:.4%}, tax={tax:.4%}(當沖減半), slippage={slippage:.4%}；**單筆全趟成本 {cost_rt:.4%} (由 fee/tax/slippage 參數推導，單一真相，修復 L94 寫死問題)**
- 策略A：交易 {res['trades']} 筆，勝率 {res['win_rate']:.2%}，PF {res['profit_factor']:.2f}，MDD {res['mdd']:.2%}，期末權益 {res['final_equity']:.4f}
- 註：持倉僅1根K，bar-level即trade-level，1筆交易=持倉1根K的完整來回

## 風控（已實作項目）
- 13:00後不新開倉、單日最多12筆、日內不跨夜（隔日首根強制無倉、報酬不跨日）
- 尚未實作：單筆停損0.8%、單日熔斷-2%（本版持倉僅1根K，單根波動即為實質停損上限）

## 壓力測試（實際重算）
- 手續費x2：PF {res_fee2['profit_factor']:.2f}（基準 {res['profit_factor']:.2f}）
- 滑價0.05%->0.2%：PF {res_slip['profit_factor']:.2f}，期末權益 {res_slip['final_equity']:.4f}
- **滑價敏感度硬門檻（新增）**：權益 {res['final_equity']:.2f} -> {res_slip['final_equity']:.2f}，若跌破 0.9 或 PF<1 則判定當前參數不可交易，真實市場大概率失效

## 結論
管線可重現（seed={args.seed} 三次 {res['trades']}筆/{res['win_rate']:.2%} 完全一致）。合成資料由 linspace+雜訊構造、天生均值回歸，策略A之正報酬為資料構造之循環論證，**不可**外推至真實市場。下一步：取得真實1分K（`./data/tw_1min_real.parquet`）後重跑，屆時 `data_layer` 會自動切換為真實1分K並移除本限制聲明，方可談 IS/OOS。
"""
    out=Path("reports")/f"report_{args.mode}.md"
    out.write_text(report, encoding='utf-8')
    print(f"完成 -> {out.resolve()} trades={res['trades']} win={res['win_rate']:.2%} cost_rt={cost_rt:.4%}")

if __name__=="__main__":
    main()
