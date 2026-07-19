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
    df['ret_30'] = df.groupby(d)['close'].pct_change(30).fillna(0)
    df['signal'] = 0
    df.loc[df['ret_30'] > 0.008, 'signal'] = -1
    df.loc[df['ret_30'] < -0.008, 'signal'] = 1
    df.loc[df['datetime'].dt.time >= pd.Timestamp('13:00').time(), 'signal'] = 0
    cum = (df['signal'] != 0).groupby(d).cumsum()
    df.loc[cum > 12, 'signal'] = 0
    return df

def backtest(df, fee=0.001425*0.28, tax=0.0015, slippage=0.0005, stop_loss=0.008, daily_stop=-0.02):
    d = df['datetime'].dt.date
    df['pos'] = df['signal'].shift(1).fillna(0)
    df.loc[df.groupby(d).head(1).index, 'pos'] = 0
    df['pnl_gross_raw'] = df['pos'] * df.groupby(d)['close'].pct_change().fillna(0)

    # --- 單筆停損 0.8% 實作 ---
    # 持倉僅1根K，若該根毛損益 < -stop_loss，則以 -stop_loss 截斷 (模擬觸價市價出場)
    df['hit_stop'] = df['pnl_gross_raw'] < -stop_loss
    df['pnl_gross'] = df['pnl_gross_raw'].where(~df['hit_stop'], -stop_loss)

    cost_rt = 2*fee + tax + 2*slippage
    df['pnl_net_pre_cb'] = df['pnl_gross'] - cost_rt * df['pos'].abs()

    # --- 單日熔斷 -2% 實作 ---
    df['cum_daily'] = df.groupby(d)['pnl_net_pre_cb'].cumsum()
    # 當日累積已跌破 daily_stop，剩餘時間強制無倉
    df['breached'] = df['cum_daily'] < daily_stop
    # 找出每日首次觸發熔斷的索引，之後全部清倉
    def apply_circuit(g):
        breached_idx = g['breached'].idxmax() if g['breached'].any() else None
        if breached_idx is not None and g.loc[breached_idx, 'breached']:
            first_pos = g.index.get_loc(breached_idx)
            g.loc[g.index[first_pos+1]:, 'pos'] = 0
            g.loc[g.index[first_pos+1]:, 'pnl_net_pre_cb'] = 0
        return g
    df = df.groupby(d, group_keys=False).apply(apply_circuit)

    df['pnl_net'] = df['pnl_net_pre_cb']
    df['equity'] = (1+df['pnl_net']).cumprod()
    trades = int((df['pos']!=0).sum())
    win = float((df.loc[df['pos']!=0, 'pnl_net']>0).mean()) if trades>0 else 0.0
    up = df.loc[df['pnl_net']>0,'pnl_net'].sum()
    dn = abs(df.loc[df['pnl_net']<0,'pnl_net'].sum())
    pf = float(up/dn) if dn>0 else 0.0
    mdd = float((df['equity']/df['equity'].cummax()-1).min())
    stop_cnt = int(df['hit_stop'].sum())
    cb_days = int(df.groupby(d)['breached'].any().sum())
    return {'trades': trades, 'win_rate': win, 'profit_factor': pf, 'mdd': mdd, 'final_equity': float(df['equity'].iloc[-1]), 'stop_cnt': stop_cnt, 'cb_days': cb_days}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--mode', choices=['fast','full'], default='fast')
    ap.add_argument('--data_dir', default='./data')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--fee_rate', type=float, default=0.001425)
    ap.add_argument('--fee_discount', type=float, default=0.28)
    ap.add_argument('--tax_rate', type=float, default=0.0015)
    ap.add_argument('--slippage', type=float, default=0.0005)
    ap.add_argument('--stop_loss', type=float, default=0.008, help='單筆停損 0.8%')
    ap.add_argument('--daily_stop', type=float, default=-0.02, help='單日熔斷 -2%')
    args=ap.parse_args()
    np.random.seed(args.seed)
    fee = args.fee_rate * args.fee_discount
    tax = args.tax_rate
    slippage = args.slippage
    cost_rt = 2*fee + tax + 2*slippage

    ddir=Path(args.data_dir)
    daily_path=ddir/'tw_market_daily.parquet'
    real_1min_path=ddir/'tw_1min_real.parquet'
    Path("reports").mkdir(parents=True, exist_ok=True)

    data_layer=""
    if real_1min_path.exists():
        try:
            df1=pd.read_parquet(real_1min_path)
            df1['datetime']=pd.to_datetime(df1['datetime'])
            data_layer=f"真實1分K {real_1min_path}"
            dfA=strategy_A(df1.copy())
            res=backtest(dfA, fee=fee, tax=tax, slippage=slippage, stop_loss=args.stop_loss, daily_stop=args.daily_stop)
            actual_days=df1['datetime'].dt.date.nunique()
            res_fee2=backtest(strategy_A(df1.copy()), fee=fee*2, tax=tax, slippage=slippage, stop_loss=args.stop_loss, daily_stop=args.daily_stop)
            res_slip=backtest(strategy_A(df1.copy()), fee=fee, tax=tax, slippage=0.002, stop_loss=args.stop_loss, daily_stop=args.daily_stop)
            report=f"""# Intraday-Lab Report ({args.mode} mode) - 真實1分K + 完整風控

- 資料：{data_layer} {df1.shape[0]}根 實際{actual_days}天
- 成本：{cost_rt:.4%} (fee {fee:.4%} tax {tax:.4%} slip {slippage:.4%}) 停損{args.stop_loss:.2%} 熔斷{args.daily_stop:.2%}
- 策略A：{res['trades']}筆 勝率{res['win_rate']:.2%} PF{res['profit_factor']:.2f} MDD{res['mdd']:.2%} 權益{res['final_equity']:.4f} 停損觸發{res['stop_cnt']}次 熔斷{res['cb_days']}天
- 壓測：手續費x2 PF{res_fee2['profit_factor']:.2f} 滑價0.2% PF{res_slip['profit_factor']:.2f} 權益{res_slip['final_equity']:.4f}
"""
            out=Path("reports")/f"report_{args.mode}.md"
            out.write_text(report, encoding='utf-8')
            print(f"完成真實 {out} {res}")
            return
        except Exception as e:
            print(f"真實1分K讀取失敗 fallback: {e}")

    if daily_path.exists():
        try:
            daily=load_daily(daily_path)
            data_layer=f"真實日線 {daily_path}"
        except Exception as e:
            print(f"讀檔失敗用合成: {e}")
            daily=pd.DataFrame({'date': pd.date_range('2024-01-01', periods=60), 'open':600,'high':610,'low':590,'close':600+np.random.randn(60)*3,'volume':10000,'stock_id':2330})
            data_layer="合成日線 (fallback)"
    else:
        print(f"找不到 {daily_path}，改用合成資料")
        daily=pd.DataFrame({'date': pd.date_range('2024-01-01', periods=60), 'open':600,'high':610,'low':590,'close':600+np.random.randn(60)*3,'volume':10000,'stock_id':2330})
        data_layer="合成日線 (雙層合成警告)"

    days=22 if args.mode=='fast' else 252
    df1=simulate_1min_from_daily(daily, stock_id=2330, days=days)
    dfA=strategy_A(df1.copy())
    res=backtest(dfA, fee=fee, tax=tax, slippage=slippage, stop_loss=args.stop_loss, daily_stop=args.daily_stop)
    actual_days=df1['datetime'].dt.date.nunique()
    res_fee2=backtest(strategy_A(df1.copy()), fee=fee*2, tax=tax, slippage=slippage, stop_loss=args.stop_loss, daily_stop=args.daily_stop)
    res_slip=backtest(strategy_A(df1.copy()), fee=fee, tax=tax, slippage=0.002, stop_loss=args.stop_loss, daily_stop=args.daily_stop)

    report=f"""# Intraday-Lab Report ({args.mode} mode) - v3 完整風控版 (條件Pass後下一步)

> 教育研究用途，非投資建議

- 資料來源：{data_layer} -> 合成1分K {df1.shape[0]}根 實際{actual_days}天 名目{days}天
- 參數：seed={args.seed} fee={fee:.4%} tax={tax:.4%} slip={slippage:.4%} 全趟成本{cost_rt:.4%} (單一真相) 停損{args.stop_loss:.2%} 熔斷{args.daily_stop:.2%}
- 策略A：交易{res['trades']}筆 勝率{res['win_rate']:.2%} PF{res['profit_factor']:.2f} MDD{res['mdd']:.2%} 權益{res['final_equity']:.4f} 停損觸發{res['stop_cnt']}次 熔斷{res['cb_days']}天
- 註：bar-level即trade-level，1筆=持倉1根K完整來回

## 風控 (本次新增完成)
- [x] 13:00後不新開倉、單日最多12筆、日內不跨夜
- [x] 單筆停損0.8%：毛損益<-0.8%時截斷為-0.8% (模擬市價停損)
- [x] 單日熔斷-2%：當日累積pnl<-2%後剩餘時間強制無倉

## 壓力測試 (實際重算)
- 手續費x2：PF {res_fee2['profit_factor']:.2f} (基準{res['profit_factor']:.2f})
- 滑價0.05%->0.2%：PF {res_slip['profit_factor']:.2f} 權益{res_slip['final_equity']:.4f}
- 滑價敏感度硬門檻：權益 {res['final_equity']:.2f}->{res_slip['final_equity']:.2f} 若PF<1或權益<0.9判定不可交易

## 結論
管線可重現，風控已完整實作。合成資料仍為 linspace+噪音，天生均值回歸，PF>1為資料構造循環論證不可外推。下一步：取得真實1分K `./data/tw_1min_real.parquet` 後重跑，屆時自動切換為真實1分K版報告，方可談 IS/OOS/盲測。
"""
    out=Path("reports")/f"report_{args.mode}.md"
    out.write_text(report, encoding='utf-8')
    print(f"完成 -> {out} trades={res['trades']} win={res['win_rate']:.2%} stop={res['stop_cnt']} cb_days={res['cb_days']}")

if __name__=="__main__":
    main()
