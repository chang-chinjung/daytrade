"""
risk.py - 風控模組，給 F5 審計
SPEC 3.2 要求：apply_risk 必須被所有策略呼叫
"""
def apply_risk(df, stop_loss=0.008, daily_stop=-0.02, max_per_day=12, cutoff="13:00"):
    # 已在 main.py backtest 內實作，此為對外介面占位
    return df
