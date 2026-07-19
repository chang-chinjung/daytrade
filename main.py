import argparse
from pathlib import Path
import pandas as pd
import numpy as np

def load_daily_smart(ddir: Path):
    # 找任意日線檔：優先 tw_market_daily，其次 tw_daily_2022_2024，再 tw_daily*.parquet
    candidates = list(ddir.glob("tw_*.parquet"))
    # 排除 1分K
    candidates = [p for p in candidates if "1min" not in p.name and "real" not in p.name]
    preferred = ["tw_market_daily.parquet", "tw_daily_2022_2024.parquet", "tw_daily.parquet"]
    for name in preferred:
        p = ddir / name
        if p.exists():
            return pd.read_parquet(p), p
    if candidates:
        p = candidates[0]
        return pd.read_parquet(p), p
    return None, None

def normalize_daily(df: pd.DataFrame):
    # FinMind 日線欄位兼容：max->high, min->low, Trading_Volume->volume, date->date
    rename = {"max":"high","min":"low","Max":"high","Min":"low","Trading_Volume":"volume","Trading_money":"amount"}
    df = df.rename(columns={k:v for k,v in rename.items() if k in df.columns})
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
    # 確保有 OHLC
    for c in ["open","high","low","close","volume"]:
        if c not in df.columns:
            df[c] = df.get(c, 600)
    if 'stock_id' not in df.columns:
        df['stock_id'] = 2330
    return df

def simulate_1min_from_daily(daily_df, stock_id=2330, days=22):
    if daily_df is None or daily_df.empty:
        daily_df = pd.DataFrame({'date': pd.date_range('2024-01-01', periods=60), 'open':600,'high':610,'low':590,'close':600+np.random.randn(60)*2,'volume':10000,'stock_id':2330})
    # 標準化
    daily_df = normalize_daily(daily_df)
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
    df['hit_stop'] = df['pnl_gross_raw'] < -stop_loss
    df['pnl_gross'] = df['pnl_gross_raw'].where(~df['hit_stop'], -stop_loss)
    cost_rt = 2*fee + tax + 2*slippage
    df['pnl_net_pre_cb'] = df['pnl_gross'] - cost_rt * df['pos'].abs()
    df['cum_daily'] = df.groupby(d)['pnl_net_pre_cb'].cumsum()
    df['breached'] = df['cum_daily'] < daily_stop
    def apply_circuit(g):
        if g['breached'].any():
            idx = g['breached'].idxmax()
            if g.loc[idx, 'breached']:
                pos = g.index.get_loc(idx)
                g.loc[g.index[pos+1]:, 'pos'] = 0
                g.loc[g.index[pos+1]:, 'pnl_net_pre_cb'] = 0
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
    return {'trades': trades, 'win_rate': win, 'profit_factor': pf, 'mdd': mdd, 'final_equity': float(df['equity'].iloc[-1]), 'stop_cnt': int(df['hit_stop'].sum()), 'cb_days': int(df.groupby(d)['breached'].any().sum())}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--mode', choices=['fast','full'], default='fast')
    ap.add_argument('--data_dir', default='./data')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--fee_rate', type=float, default=0.001425)
    ap.add_argument('--fee_discount', type=float, default=0.28)
    ap.add_argument('--tax_rate', type=float, default=0.0015)
    ap.add_argument('--slippage', type=float, default=0.0005)
    ap.add_argument('--stop_loss', type=float, default=0.008)
    ap.add_argument('--daily_stop', type=float, default=-0.02)
    args=ap.parse_args()
    np.random.seed(args.seed)
    fee=args.fee_rate*args.fee_discount; tax=args.tax_rate; slippage=args.slippage; cost_rt=2*fee+tax+2*slippage
    ddir=Path(args.data_dir); Path("reports").mkdir(exist_ok=True)
    # 1. 優先吃真實1分K
    for real_name in ["tw_1min_real.parquet","tw_1min_real_202301.parquet"]:
        real_path = ddir / real_name
        if real_path.exists():
            try:
                df1=pd.read_parquet(real_path); df1['datetime']=pd.to_datetime(df1['datetime'])
                print(f"[INFO] 使用真實1分K {real_path} shape={df1.shape}")
                dfA=strategy_A(df1.copy()); res=backtest(dfA, fee=fee, tax=tax, slippage=slippage, stop_loss=args.stop_loss, daily_stop=args.daily_stop)
                out=Path("reports")/f"report_{args.mode}.md"; out.write_text(f"# Report {args.mode} 真實1分K {real_path} {res}", encoding='utf-8'); print(f"完成真實 {res}"); return
            except Exception as e: print(f"fallback real {e}")
    # 2. 吃日線
    daily_df, daily_path = load_daily_smart(ddir)
    if daily_df is not None:
        print(f"[INFO] 使用日線 {daily_path} shape={daily_df.shape} -> 合成1分K")
    else:
        print(f"[INFO] 找不到日線，改用合成資料示範")
        daily_df = None
    days=22 if args.mode=='fast' else 252
    df1=simulate_1min_from_daily(daily_df, days=days); dfA=strategy_A(df1.copy())
    res=backtest(dfA, fee=fee, tax=tax, slippage=slippage, stop_loss=args.stop_loss, daily_stop=args.daily_stop)
    res2=backtest(strategy_A(df1.copy()), fee=fee*2, tax=tax, slippage=slippage, stop_loss=args.stop_loss, daily_stop=args.daily_stop)
    res3=backtest(strategy_A(df1.copy()), fee=fee, tax=tax, slippage=0.002, stop_loss=args.stop_loss, daily_stop=args.daily_stop)
    report=f"# Report {args.mode} v3.1 日線相容版\n- 日線來源 {daily_path}\n- 成本{cost_rt:.4%} 停損{args.stop_loss:.2%} 熔斷{args.daily_stop:.2%}\n- {res['trades']}筆 勝率{res['win_rate']:.2%} PF{res['profit_factor']:.2f} MDD{res['mdd']:.2%} 權益{res['final_equity']:.4f} 停損{res['stop_cnt']} 熔斷{res['cb_days']}天\n- 壓測 手續費x2 PF{res2['profit_factor']:.2f} 滑價0.2% PF{res3['profit_factor']:.2f} 權益{res3['final_equity']:.4f}\n"
    out=Path("reports")/f"report_{args.mode}.md"; out.write_text(report, encoding='utf-8'); print(f"完成 {out} {res}")

if __name__=="__main__": main()
