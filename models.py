"""
Data models for options trading system
Pydantic models for validation and serialization
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class OptionType(str, Enum):
    """Call or Put"""
    CALL = "CALL"
    PUT = "PUT"


class OptionChainData(BaseModel):
    """Single option contract from Finnhub"""
    symbol: str
    expiration_date: str  # YYYY-MM-DD
    strike: float
    option_type: OptionType
    bid: float
    ask: float
    mid_price: float = Field(default=0.0)  # Calculated (bid + ask) / 2
    bid_ask_spread: float = Field(default=0.0)  # Calculated ask - bid
    last_price: Optional[float] = None
    volume: Optional[int] = None
    open_interest: Optional[int] = None
    implied_volatility: Optional[float] = None
    delta: Optional[float] = None
    theta: Optional[float] = None
    gamma: Optional[float] = None
    vega: Optional[float] = None
    
    def calculate_derived(self):
        """Calculate mid_price and spread"""
        self.mid_price = (self.bid + self.ask) / 2
        self.bid_ask_spread = self.ask - self.bid
        return self
    
    def is_liquid(self, max_spread: float = 0.05) -> bool:
        """Check if option is liquid based on bid-ask spread"""
        return self.bid_ask_spread <= max_spread
    
    def days_to_expiration(self) -> int:
        """
        Calculate DTE (Days To Expiration)
        
        Returns:
            Number of days until expiration
            
        Raises:
            ValueError: If option is already expired
        """
        exp_date = datetime.strptime(self.expiration_date, "%Y-%m-%d").date()
        today = datetime.now().date()
        
        dte = (exp_date - today).days
        
        if dte < 0:
            raise ValueError(f"Option already expired: {self.expiration_date}")
        
        return dte
    
    @staticmethod
    def normalize_delta(delta: Optional[float], option_type: OptionType) -> Optional[float]:
        """
        Normalize delta to always be positive (absolute value)
        
        This ensures consistent comparison across puts and calls.
        Note: Raw API deltas are negative for puts, positive for calls.
        This normalizes them so 0.10-0.20 delta means 80-90% OTM for both.
        
        Args:
            delta: Raw delta from API (can be None)
            option_type: CALL or PUT
            
        Returns:
            Absolute delta (0.0-1.0) or None if input is None
        """
        if delta is None:
            return None
        return abs(delta)


class OptionsChain(BaseModel):
    """All options for a single symbol"""
    symbol: str
    current_price: float
    fetch_time: datetime
    calls: List[OptionChainData] = []
    puts: List[OptionChainData] = []
    
    def get_by_strike_and_type(self, strike: float, option_type: OptionType) -> Optional[OptionChainData]:
        """Retrieve option by strike and type"""
        options = self.calls if option_type == OptionType.CALL else self.puts
        for opt in options:
            if opt.strike == strike:
                return opt
        return None


class TradeEntry(BaseModel):
    """A single trade log entry"""
    entry_date: datetime
    symbol: str
    portfolio_name: str  # "small", "medium", "large"
    action: str  # "STO" (sell to open) or "BTO" (buy to close)
    strategy: str  # "CSP", "CC" (covered call)
    strike: float
    option_type: OptionType
    contracts: int
    premium_per_share: float  # Credit received
    expiration_date: str
    dte_at_entry: int
    current_price_at_entry: float
    
    # Exit info (filled later)
    exit_date: Optional[datetime] = None
    exit_premium: Optional[float] = None
    assigned: bool = False
    
    # P&L
    profit_loss: Optional[float] = None
    profit_loss_pct: Optional[float] = None
    days_held: Optional[int] = None
    
    # Rules thresholds
    take_profit_pct: float = 0.50  # Close at 50% profit
    stop_loss_pct: float = 0.30    # Close at 30% loss
    
    # Metadata
    notes: Optional[str] = None
    
    def calculate_pnl(self, exit_price: float):
        """Calculate profit/loss"""
        credit = self.premium_per_share * self.contracts * 100
        cost_to_close = exit_price * self.contracts * 100
        self.profit_loss = credit - cost_to_close
        self.profit_loss_pct = (self.profit_loss / credit) if credit > 0 else 0
        
        if self.exit_date and self.entry_date:
            self.days_held = (self.exit_date - self.entry_date).days
    
    def take_profit_threshold(self) -> float:
        """Premium price to close for 50% profit"""
        return self.premium_per_share * (1 - self.take_profit_pct)
    
    def stop_loss_threshold(self) -> float:
        """Premium price to close to limit loss to 30%"""
        return self.premium_per_share * (1 + self.stop_loss_pct)


class Position(BaseModel):
    """Current open position"""
    position_id: str  # Unique identifier
    symbol: str
    portfolio_name: str
    strategy: str  # "CSP" or "CC"
    option_type: OptionType
    strike: float
    expiration_date: str
    contracts: int
    entry_date: datetime
    entry_premium: float
    current_premium: float
    current_price: float
    dte: int
    
    # P&L tracking
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    
    # Status
    status: str = "OPEN"  # "OPEN", "CLOSED", "ASSIGNED"
    
    def update_price(self, new_premium: float, current_stock_price: float, new_dte: int):
        """Update live prices"""
        self.current_premium = new_premium
        self.current_price = current_stock_price
        self.dte = new_dte
        
        credit = self.entry_premium * self.contracts * 100
        cost_to_close = new_premium * self.contracts * 100
        self.unrealized_pnl = credit - cost_to_close
        self.unrealized_pnl_pct = (self.unrealized_pnl / credit) if credit > 0 else 0
    
    def should_take_profit(self, take_profit_pct: float = 0.50) -> bool:
        """Check if should close for profit"""
        threshold = self.entry_premium * (1 - take_profit_pct)
        return self.current_premium <= threshold
    
    def should_stop_loss(self, stop_loss_pct: float = 0.30) -> bool:
        """Check if should close to limit loss"""
        threshold = self.entry_premium * (1 + stop_loss_pct)
        return self.current_premium >= threshold


class Portfolio(BaseModel):
    """A trading account with positions"""
    name: str  # "small", "medium", "large"
    balance: float
    max_positions: int
    pdt_compliant: bool
    positions: List[Position] = []
    trade_history: List[TradeEntry] = []
    
    # PDT tracking
    day_trades_count: int = 0  # Resets every 5 days
    last_trade_dates: List[datetime] = []  # Track for PDT
    
    def buying_power_used(self) -> float:
        """Calculate capital tied up in CSPs"""
        used = 0.0
        for pos in self.positions:
            if pos.strategy == "CSP":
                # CSP requires cash equal to strike × 100 × contracts
                used += pos.strike * 100 * pos.contracts
        return used
    
    def available_buying_power(self) -> float:
        """Available capital for new positions"""
        return self.balance - self.buying_power_used()
    
    def can_open_position(self, new_capital_required: float) -> bool:
        """Check if can open new position"""
        # Check position limit
        if len(self.positions) >= self.max_positions:
            return False
        
        # Check buying power
        if self.available_buying_power() < new_capital_required:
            return False
        
        return True
    
    def add_trade(self, trade: TradeEntry):
        """Log a trade"""
        self.trade_history.append(trade)
        if self.pdt_compliant:
            self.last_trade_dates.append(trade.entry_date)
    
    def monthly_returns(self, year: int, month: int) -> float:
        """Calculate monthly P&L"""
        monthly_pnl = 0.0
        for trade in self.trade_history:
            if trade.exit_date:
                if trade.exit_date.year == year and trade.exit_date.month == month:
                    if trade.profit_loss:
                        monthly_pnl += trade.profit_loss
        return monthly_pnl
    
    def ytd_returns(self, year: int) -> float:
        """Calculate year-to-date P&L"""
        ytd_pnl = 0.0
        for trade in self.trade_history:
            if trade.exit_date and trade.exit_date.year == year:
                if trade.profit_loss:
                    ytd_pnl += trade.profit_loss
        return ytd_pnl
    
    def active_position_count(self) -> int:
        """Count open positions"""
        return len([p for p in self.positions if p.status == "OPEN"])


class RulesConfig(BaseModel):
    """Parsed trading rules"""
    target_delta_min: float = 0.10
    target_delta_max: float = 0.20
    min_dte: int = 7
    max_dte: int = 45
    preferred_dte_min: int = 21
    preferred_dte_max: int = 30
    min_premium: float = 0.10
    max_bid_ask_spread: float = 0.05
    take_profit_pct: float = 0.50
    stop_loss_pct: float = 0.30
    avoid_monday_expiration: bool = True
    preferred_symbols: List[str] = []


class PositionManagementRules(BaseModel):
    """Rules for managing positions"""
    enable_rolling: bool = True
    enable_adjustments: bool = True
    max_roll_outs: int = 2  # Max times to roll a position
    roll_when_loss_pct: float = 0.25  # Roll if loss > 25%
