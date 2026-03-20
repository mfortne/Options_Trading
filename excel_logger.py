import pandas as pd
from pathlib import Path
from datetime import datetime

EXCEL_PATH = Path("trades.xlsx")

def log_pipeline_run(symbol: str, current_price: float, eligible_puts: list, eligible_calls: list):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    rows = []
    for put in eligible_puts:
        rows.append({
            "Portfolio": "small",   # hardcode for now since you're testing with first portfolio
            "Timestamp": timestamp,
            "Symbol": symbol,
            "Type": "Put",
            "Strike": put.strike,
            "Bid": put.bid,
            "Delta": put.delta,
            "Spread": put.bid_ask_spread,
            "Underlying Price": current_price
        })
    for call in eligible_calls:
        rows.append({
            "Portfolio": "small",   # hardcode for now since you're testing with first portfolio
            "Timestamp": timestamp,
            "Symbol": symbol,
            "Type": "Call",
            "Strike": call.strike,
            "Bid": call.bid,
            "Delta": call.delta,
            "Spread": call.bid_ask_spread,
            "Underlying Price": current_price
        })
    
    if not rows:
        print("No eligible options → nothing logged")
        return
    
    df_new = pd.DataFrame(rows)
    
    if EXCEL_PATH.exists():
        df_existing = pd.read_excel(EXCEL_PATH)
        df_combined = pd.concat([df_existing, df_new], ignore_index=True)
    else:
        df_combined = df_new
    
    df_combined.to_excel(EXCEL_PATH, index=False)
    print(f"Logged {len(rows)} rows to {EXCEL_PATH}")