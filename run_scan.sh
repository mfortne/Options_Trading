#!/bin/bash
# =============================================================
# run_scan.sh — runs the options scanner on a cron schedule
# Cron entry (every hour Mon-Fri):
#   0 * * * 1-5 /mnt/c/Users/laici/Documents/Desktop/PersonalAIFiles/options-trading-engine/run_scan.sh
# =============================================================

PROJECT_DIR="/mnt/c/Users/laici/Documents/Desktop/PersonalAIFiles/options-trading-engine"

cd "$PROJECT_DIR" || exit 1

source "$PROJECT_DIR/venv/bin/activate"

echo "========================================" >> "$PROJECT_DIR/daily_run.log"
echo "Run started: $(date)" >> "$PROJECT_DIR/daily_run.log"

python3 main.py >> "$PROJECT_DIR/daily_run.log" 2>&1

echo "Run finished: $(date)" >> "$PROJECT_DIR/daily_run.log"
