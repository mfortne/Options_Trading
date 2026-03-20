#!/usr/bin/env bash
# Cron job wrapper for options-trading-engine

# Ensure we have a reasonable PATH (cron's PATH is minimal)
export PATH="/usr/local/bin:/usr/bin:/bin:/home/mfortne/.local/bin:/home/mfortne/.local/share/pnpm"

# Change to project directory
cd /home/mfortne/projects/options-trading-engine || { echo "[$(date)] Project directory not found"; exit 1; }

# Run main.py using the virtual environment if available
VENV_PY="./venv/bin/python"
if [ -x "$VENV_PY" ]; then
    "$VENV_PY" main.py
    exit_code=$?
elif command -v python &>/dev/null; then
    python main.py
    exit_code=$?
else
    echo "[$(date)] Python interpreter not found"
    exit_code=127
fi

# Attempt to send WhatsApp notification via exact openclaw path
OPENCLAWBIN="/home/mfortne/.local/share/pnpm/openclaw"
if [ -x "$OPENCLAWBIN" ]; then
    "$OPENCLAWBIN" message send \
        --channel whatsapp \
        --target "+18642801172" \
        --message "Options engine run completed at $(date). Exit code: $exit_code" \
    >/dev/null 2>&1
else
    echo "[$(date)] openclaw binary not found; cannot send WhatsApp notification"
fi

# Log locally
echo "[$(date)] Options engine run complete. Exit code: $exit_code" >> /home/mfortne/projects/options-trading-engine/cron.log

# Exit with the correct status
exit $exit_code