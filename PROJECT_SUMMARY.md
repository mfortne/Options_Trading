# Options Trading Rules Engine - Project Summary

## Scope
Build a Python-based options trading tracker using **Finnhub API** (free tier, caching) for paper trading across 3 portfolio sizes.

## Core Strategy
- **Sell OTM puts (CSP)** and **covered calls** at 80-90% OTM (delta ~0.10-0.20)
- **Take profit**: Buy to close (BTC) when premium drops 50%+
- **Stop loss**: BTC when loss reaches 30%+
- **Auto-convert**: Assigned shares → covered calls
- **Weekly expirations preferred** (no Monday expiration)

## Portfolio Configuration
| Account | Balance | Max Positions | PDT Rules |
|---------|---------|---------------|-----------|
| Small   | <$500   | 1             | Yes*      |
| Medium  | $50K    | 2             | Yes       |
| Large   | $200K   | 5             | No        |

*Small account also follows PDT rules (max 3 day trades per 5 rolling days)

## Data Sources
- **Primary**: Finnhub API (free tier: 60 calls/min, unlimited historical)
- **Caching**: Local SQLite to minimize API calls
- **Refresh**: Multiple times daily, cached

## Deliverables (Phase 1)
1. **Rules Engine** - Markdown rules file with configurable parameters
2. **Data Fetcher** - Finnhub integration with caching
3. **Trade Logger** - Excel multi-tab tracker (entry/exit, P&L, Greeks)
4. **Paper Trading UI** - Dashboard to view opportunities & positions

## Future (Phase 2+)
- Schwab API integration for live execution
- Advanced Greeks tracking (theta decay alerts)
- Straddle/strangle support

## Git Repository Structure
```
options-trading-bot/
├── README.md                      # Project overview
├── LICENSE                        # MIT
├── requirements.txt               # Python deps
├── .gitignore                     # Standard Python
│
├── config/
│   ├── trading_rules.md          # Rules (configurable)
│   ├── portfolio_config.json     # Account settings
│   └── api_keys.example.json     # Finnhub key template
│
├── src/
│   ├── __init__.py
│   ├── main.py                   # Entry point
│   ├── data/
│   │   ├── __init__.py
│   │   ├── finnhub_client.py    # Finnhub wrapper
│   │   ├── cache.py             # SQLite caching
│   │   └── models.py            # Data classes
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── rules_parser.py      # Parse trading rules
│   │   ├── rules_engine.py      # Apply rules logic
│   │   └── calculator.py        # P&L, Greeks, sizing
│   ├── trading/
│   │   ├── __init__.py
│   │   ├── portfolio.py         # Multi-account tracker
│   │   ├── position.py          # Single position logic
│   │   └── logger.py            # Excel output
│   └── ui/
│       ├── __init__.py
│       └── dashboard.py         # Web UI (Flask/Streamlit)
│
├── tests/
│   ├── test_rules_engine.py
│   ├── test_calculator.py
│   └── test_portfolio.py
│
├── data/
│   ├── cache.db                 # SQLite (local, not committed)
│   ├── trades.xlsx              # Output Excel (not committed)
│   └── .gitkeep
│
├── docs/
│   ├── SETUP.md                 # Installation & API key setup
│   ├── TRADING_RULES.md         # Detailed rules documentation
│   └── ARCHITECTURE.md          # System design
│
└── scripts/
    ├── generate_trades.py       # Run screening
    └── backtest.py              # Test rules on family data
```

## Key Files (Not in Repo)
- `api_keys.json` - Finnhub API key (add to `.gitignore`)
- `trades.xlsx` - Output file (add to `.gitignore`)
- `cache.db` - Cached data (add to `.gitignore`)

## Next Steps
1. **Session 1**: Build project skeleton + Finnhub data fetcher + caching
2. **Session 2**: Parse rules MD file + implement rules engine
3. **Session 3**: Build Excel logger + portfolio tracker
4. **Session 4**: Create dashboard UI

---

**Context window optimized**: This summary contains all essential info from Michael_Stocks.xlsx without redundancy.
