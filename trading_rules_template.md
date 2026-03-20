# Trading Rules Configuration

**Last Updated**: 2025-02-17  
**Source**: Proven family strategies (Carl, Nancy, Don)  
**Status**: Paper trading

---

## Portfolio Configuration

### Account 1: Small Account
```
Balance: <$500
Max Positions: 1
Primary Symbol: TQQQ
Purpose: Testing strategy on small capital
```

### Account 2: Medium Account (PDT Compliant)
```
Balance: $50,000
Max Positions: 2
PDT Rules: Yes (day trade limit = 3 per rolling 5 days)
Symbols: QQQ, SPY, or other liquid options
Purpose: Balanced growth with compliance
```

### Account 3: Large Account
```
Balance: $200,000
Max Positions: 5
PDT Rules: No
Symbols: NVDA, QQQ, SPY, IWM, Russell 2000
Purpose: Maximum premium capture
```

---

## Entry Rules (When to Open a Position)

### Cash-Secured Put (CSP) Entry

**Conditions**:
- Strike price: **80-90% OTM** (delta 0.10-0.20)
- Expiration: **7-45 DTE** (days to expiration), prefer 21-30 DTE
- Premium: Must be > $0.10 per contract
- Volume: Bid-ask spread < $0.05 for liquid execution
- Expiration Day: **NOT Monday** (avoid thin liquidity)

**Example**:
- Current stock price: $100
- Sell put at strike $90 (10% below)
- Collect $0.25-$0.50 premium per share ($25-$50 per contract)

**Capital Requirement** (CSP ties up cash):
- Reserve 100 × Strike Price per contract
- Example: Sell $90 put = need $9,000 cash in account

### Covered Call Entry (After CSP Assignment)

**Conditions**:
- Only sold if **assigned shares from CSP**
- Strike price: **80-90% OTM** (delta 0.10-0.20) above current stock price
- Same DTE rules as puts
- Goal: Additional premium on assigned shares

**Example**:
- Assigned 100 shares at $90 from CSP
- Stock now trading at $88-$92
- Sell call at strike $100 (8-12% above current)
- Collect $0.15-$0.35 premium

---

## Exit Rules (When to Close a Position)

### Take Profit (TP)

**Rule**: Buy to close (BTC) when premium drops **50% or more**

**Example**:
- Sold put for $0.50 premium
- Premium now at $0.25 or less
- **Action**: BTC to lock in 50%+ profit
- Profit per contract: ~$25 (50% of $50)

**Timer**: Close when ready, no time pressure (good problem)

### Stop Loss (SL)

**Rule**: BTC when loss reaches **30% or more**

**Example**:
- Sold put for $0.50 premium ($50 per contract)
- Premium now at $0.65 or higher
- Loss: $0.15 per share = $15 per contract (30% loss)
- **Action**: BTC to limit loss
- Max loss per contract: ~$15 (30% of $50)

**Important**: 
- Don't hold losers hoping to recover
- Sell calls if approaching -30% to offset (roll strategy)
- Consider market conditions (support/resistance)

### Assignment

**If put is ITM at expiration**:
- You will be **assigned 100 shares** at strike price
- This is OK—you intended to own the stock
- **Auto-convert**: Immediately sell covered calls on assigned shares

**If call is ITM at expiration**:
- Your shares will be **called away** at strike price
- Cash returned to account
- **Cycle repeats**: Sell new CSP

---

## Position Management Rules

### Rolling Strategy (Optional)

If a position is near -30% loss and you believe in the trade:
1. BTC the current option at loss
2. STO (Sell to Open) a new option **further out** (add 1-2 weeks DTE)
3. Collect additional premium to offset loss
4. Requires higher credit to make it worthwhile

**Rule of Thumb**: Only roll if new premium > loss on closed position

### Multiple Positions

**Medium Account (2 max)**:
- Typically: 1 CSP + 1 covered call (from assignment)
- Or: 2 CSPs on different symbols
- Avoid overlapping expirations to reduce management burden

**Large Account (5 max)**:
- Spread across symbols (QQQ, NVDA, SPY, etc.)
- Stagger expirations (some 2-week, some 4-week)
- Monitor Greeks: total portfolio delta, theta

---

## Market Conditions & Timing

### When to Enter (from Carl's Rules)

1. **Identify market trend** (bullish/bearish/neutral)
2. **Find support & resistance** on daily chart
3. **Enter when**:
   - For CSP: Stock near support, expected to bounce up
   - For Calls: Stock near resistance, expected to consolidate
4. **Higher premiums** when stock is near support/resistance

### When NOT to Enter

- Market in strong downtrend (puts risky)
- No clear support/resistance (uncertainty)
- Low IV environment (premiums weak)
- Illiquid options (wide spreads)
- Within 3 days of earnings (IV crush risk)

---

## Greeks (Risk Management)

### Delta (Price Movement Risk)

**Target**: Sell options with **delta 0.10-0.20** (80-90% OTM probability)
- Lower delta = more likely to stay OTM
- Higher delta = more premium but higher risk

### Theta (Time Decay, Our Friend)

**Target**: Positive theta = premium decays in our favor
- Sell options → we benefit from time decay
- Monitor especially in final 2 weeks (theta accelerates)

### Greeks to Ignore (for now)

- Vega (volatility) - monitor but not strict rules
- Gamma (delta acceleration) - track but not a stop rule

---

## Example Trade Log (Paper Trading)

```
Date: 2025-02-17
Account: Medium ($50K)
Action: SELL TO OPEN (STO)
Symbol: QQQ
Type: CSP (Cash-Secured Put)
Strike: $420
Expiration: 2025-02-28 (11 DTE)
Premium Received: $0.35 per share ($35 per contract)
Capital Reserved: $42,000 (strike × 100)

TARGET PROFIT: $0.175 or less ($17.50 per contract = 50% of $35)
TARGET LOSS: $0.455 or higher ($45.50 per contract = 30% loss vs $35 credit)

Status: OPEN
Days Held: 0
Current Premium: $0.35 (no change yet)
P&L: $0
Notes: Near daily support at $420, IV elevated, strong premium
```

---

## Configuration Variables (Easy to Adjust)

```python
# Put these at the top of your rules file for quick tweaking
TARGET_PROFIT_PCT = 0.50          # 50% profit = BTC
MAX_LOSS_PCT = 0.30               # 30% loss = BTC
TARGET_DELTA_RANGE = (0.10, 0.20) # 80-90% OTM
MIN_DTE = 7                        # Min days to expiration
MAX_DTE = 45                       # Max days to expiration
PREFERRED_DTE = (21, 30)           # Sweet spot
MIN_PREMIUM = 0.10                 # Minimum credit per share
MAX_BID_ASK_SPREAD = 0.05         # Max spread for liquidity
NO_MONDAY_EXPIRATION = True        # Avoid Monday expirations
```

---

## Reminders (From Carl's Rules)

1. **Keep it simple** - Don't over-complicate
2. **Patience** - Wait for good setups
3. **Don't predict** - React to what the market does
4. **Consider support/resistance** - Key technical levels matter
5. **Have discipline** - Follow your rules, don't deviate
6. **Be a survivor** - Protect capital above all else
7. **No Monday expirations** - Too thin, unpredictable
8. **Never get in front of a train** - Don't fight the trend

---

## Resources

- **Support/Resistance Analysis**: TradingView charts (free)
- **Options Data**: Finnhub API (free tier)
- **Greeks Calculator**: Online (built into most platforms)
- **Community**: WarriorTrading.com for education

---

**Next**: Review this with your dad/aunt and adjust thresholds as needed. 
Export to `config/trading_rules.md` when ready.
