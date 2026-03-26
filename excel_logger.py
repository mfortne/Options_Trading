import pandas as pd
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Optional

# --- Configuration ---
# Use an environment variable or a config file for these in a production app
EXCEL_PATH = Path("trades.xlsx")
# Replace with your actual WSL path to Google Drive
GDRIVE_SYNC_PATH = Path("/mnt/g/My Drive/Options/trades.xlsx") 

def log_pipeline_run(
    symbol: str, 
    current_price: float, 
    eligible_puts: List, 
    eligible_calls: List,
    portfolio_name: str = "small"
):
    """
    Logs option trade data to a local Excel file and syncs to a backup location.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Build rows using a list comprehension or generator for efficiency
    rows = []
    for option_type, options in [("Put", eligible_puts), ("Call", eligible_calls)]:
        for opt in options:
            rows.append({
                "Portfolio": portfolio_name,
                "Timestamp": timestamp,
                "Symbol": symbol,
                "Type": option_type,
                "Strike": getattr(opt, 'strike', None),
                "Bid": getattr(opt, 'bid', None),
                "Delta": getattr(opt, 'delta', None),
                "Spread": getattr(opt, 'bid_ask_spread', None),
                "Underlying Price": current_price
            })
    
    if not rows:
        print("No eligible options → nothing logged")
        return

    df_new = pd.DataFrame(rows)

    # 2. Use a Context Manager for file operations to handle potential locks
    try:
        if EXCEL_PATH.exists():
            # Using 'openpyxl' engine explicitly is a best practice for .xlsx
            df_existing = pd.read_excel(EXCEL_PATH, engine='openpyxl')
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        else:
            df_combined = df_new

        # Save locally
        df_combined.to_excel(EXCEL_PATH, index=False, engine='openpyxl')
        print(f"Successfully logged {len(rows)} rows to {EXCEL_PATH}")

        # 3. Secondary Sync (Google Drive)
        # We copy the file rather than writing twice to ensure data integrity
        if GDRIVE_SYNC_PATH.parent.exists():
            shutil.copy2(EXCEL_PATH, GDRIVE_SYNC_PATH)
            print(f"Cloud backup updated at: {GDRIVE_SYNC_PATH}")
        else:
            print(f"Warning: Cloud path {GDRIVE_SYNC_PATH.parent} not found. Skipping sync.")

    except PermissionError:
        print(f"Error: Could not write to {EXCEL_PATH}. Is the file open in Excel?")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")