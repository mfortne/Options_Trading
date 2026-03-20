# Template-Based Local Setup Instructions

## Overview

This project uses **sanitized templates** for sensitive configuration files. This approach:
- ✅ Keeps API keys out of version control
- ✅ Prevents accidental credential commits
- ✅ Enables easy local deployment
- ✅ Maintains production security

---

## Quick Start (2 minutes)

### Python Users
```bash
# From project root
python setup_local_config.py
```

### Bash/Shell Users
```bash
# From project root
bash setup_local_config.sh
```

Both scripts will:
1. ✅ Create necessary directories (data/, logs/, config/)
2. ✅ Copy templates to correct locations
3. ✅ Verify everything is set up
4. ✅ Show next steps

---

## Manual Setup (if scripts don't work)

### 1. Create Directories
```bash
mkdir -p data
mkdir -p logs
mkdir -p config
```

### 2. Copy Templates
```bash
# Copy environment variables template
cp templates/.env.template .env

# Copy portfolio configuration template
cp templates/portfolio_config.json.template config/portfolio_config.json
```

### 3. Configure API Key
Edit `.env`:
```bash
# Option 1: Edit in text editor
nano .env
# Find: FINNHUB_API_KEY=your_finnhub_api_key_here
# Replace with your actual key from https://finnhub.io

# Option 2: Command line (Linux/Mac)
sed -i 's/your_finnhub_api_key_here/YOUR_ACTUAL_KEY_HERE/' .env
```

### 4. Configure Portfolio (Optional)
Edit `config/portfolio_config.json`:
```bash
nano config/portfolio_config.json
# Adjust account balances, symbols, position limits as needed
```

---

## What Each Template Does

### `.env.template` → `.env`

**Purpose**: Store environment variables and secrets

**Contains**:
- FINNHUB_API_KEY (required)
- SCHWAB credentials (optional, for Phase 2)
- Database settings
- Logging configuration

**Why Templated**:
- Never commit real API keys
- Different keys per environment (dev/prod)
- Easy to update without code changes

**How to Get Values**:
- FINNHUB_API_KEY: https://finnhub.io (free sign up)
- SCHWAB credentials: From your Schwab account (Phase 2)

### `portfolio_config.json.template` → `config/portfolio_config.json`

**Purpose**: Store trading configuration and portfolio settings

**Contains**:
- 3 portfolio definitions (small/medium/large)
- All trading rules (delta, DTE, premium, etc.)
- API settings
- Caching configuration

**Why Templated**:
- Different configs for testing vs. live trading
- Easy to reset to defaults
- Template shows best practices

**How to Customize**:
- Update account balances to match your accounts
- Adjust symbols to your watchlist
- Configure position limits
- Toggle PDT enforcement per portfolio

---

## Verification

### Test 1: Environment Variables
```bash
# Check .env was created
ls -la .env
# Should show: -rw-r--r-- ... .env

# Verify it's gitignored
git status
# .env should NOT appear in git status
```

### Test 2: Configuration
```bash
# Check config was created
ls -la config/portfolio_config.json
# Should show the file exists

# Verify it's gitignored
git status
# config/portfolio_config.json should NOT appear
```

### Test 3: Full Setup
```bash
# Run data pipeline test
python src/main.py
# Should not error about missing .env or config

# Run rules engine test
python src/test_rules_engine.py
# Should not error about missing configuration
```

---

## Security Checklist

✅ **Before Committing**:
- [ ] `.env` is in `.gitignore`
- [ ] `config/portfolio_config.json` is in `.gitignore`
- [ ] No real API keys in any committed files
- [ ] `.env` file is in `.gitignore` before you create it
- [ ] Run `git status` and verify no sensitive files show

✅ **Templates That Are Safe**:
- [ ] `templates/.env.template` - Has placeholder values
- [ ] `templates/portfolio_config.json.template` - Has dummy key

✅ **Local Files That Are Hidden**:
- [ ] `.env` - Your actual secrets (never commit)
- [ ] `config/portfolio_config.json` - Your actual config (never commit)
- [ ] `data/cache.db` - Trading data (never commit)

---

## Troubleshooting

### "Module not found" or "No such file or directory"

**Problem**: Missing `.env` or `config/portfolio_config.json`

**Solution**:
```bash
python setup_local_config.py
```

Or manually:
```bash
cp templates/.env.template .env
cp templates/portfolio_config.json.template config/portfolio_config.json
```

### "Finnhub API Error: 401 Unauthorized"

**Problem**: FINNHUB_API_KEY is wrong or still a placeholder

**Solution**:
1. Get your API key from https://finnhub.io
2. Edit `.env`
3. Replace `FINNHUB_API_KEY=your_finnhub_api_key_here` with your actual key
4. Save and retry

### ".env file not found"

**Problem**: Setup script didn't run or failed

**Solution**:
```bash
# Try Python version
python setup_local_config.py

# Or bash version
bash setup_local_config.sh

# Or manual
cp templates/.env.template .env
cp templates/portfolio_config.json.template config/portfolio_config.json
```

### "FileNotFoundError: portfolio_config.json"

**Problem**: `config/portfolio_config.json` wasn't copied

**Solution**:
```bash
mkdir -p config
cp templates/portfolio_config.json.template config/portfolio_config.json
```

### Templates Not in templates/ Directory

**Problem**: Files were moved or setup went wrong

**Solution**:
```bash
# Verify templates exist
ls -la templates/

# Should show:
# - .env.template
# - portfolio_config.json.template
# - README.md
```

---

## For Different Environments

### Development (Testing)
```bash
# .env
FINNHUB_API_KEY=your_test_key
ENVIRONMENT=development
LOG_LEVEL=DEBUG

# config/portfolio_config.json
Use small account ($500) for testing
```

### Production (Live Trading - Phase 2)
```bash
# .env
FINNHUB_API_KEY=your_production_key
SCHWAB_API_KEY=your_schwab_key
ENVIRONMENT=production
LOG_LEVEL=INFO

# config/portfolio_config.json
Use appropriate account balances
Enable live Schwab API
```

---

## What's in Templates/ Directory

```
templates/
├── .env.template                      # Environment variables
├── portfolio_config.json.template     # Portfolio configuration
└── README.md                          # This file
```

These are **ALWAYS COMMITTED** to GitHub because they contain NO secrets.

They're provided so anyone cloning the repo can:
1. Run one setup script
2. Add their API key
3. Start trading immediately

---

## File Management Summary

### In `.gitignore` (Never Committed)
```
.env                          # Your secrets
.env.*                        # Any .env variants
config/portfolio_config.json  # Your configuration
data/cache.db                 # Trading data
*.backup
secrets/
private/
```

### In Repository (Safe to Commit)
```
templates/.env.template                      # Placeholder only
templates/portfolio_config.json.template     # Placeholder only
templates/README.md                          # Instructions
setup_local_config.py                        # Setup script
setup_local_config.sh                        # Setup script (bash)
```

---

## Next Steps After Setup

1. ✅ **Run setup script**: `python setup_local_config.py`
2. ✅ **Add API key**: Edit `.env`, add FINNHUB_API_KEY
3. ✅ **Verify**: Run `python src/main.py`
4. ✅ **Start trading**: Begin paper trading!

---

## Questions?

- **Setup issues?** → See troubleshooting above
- **Template structure?** → See `templates/README.md`
- **Full setup?** → See `docs/SETUP.md`
- **Quick start?** → See `docs/QUICK_START.md`

Everything is designed for **zero-friction setup**! 🚀
