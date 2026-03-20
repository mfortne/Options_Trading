"""
Rules engine - Evaluate options against trading rules
Generates entry signals and checks exit conditions
"""

from typing import List, Optional, Tuple
from datetime import datetime, timedelta
from models import (
    OptionChainData, OptionsChain, Portfolio, Position, RulesConfig, 
    OptionType, PositionManagementRules
)


class RulesEngine:
    """Core trading rules evaluation"""
    
    def __init__(self, rules: RulesConfig):
        """
        Initialize rules engine
        
        Args:
            rules: RulesConfig with all thresholds
        """
        self.rules = rules
    
    # ========== ENTRY EVALUATION ==========
    
    def evaluate_option_for_entry(self, option: OptionChainData, 
                                   current_price: float) -> Tuple[bool, str]:
        """
        Evaluate if option meets entry criteria
        
        Args:
            option: Option to evaluate
            current_price: Current stock price
            
        Returns:
            (is_eligible, reason_if_not_eligible)
        """
        # Check expiration type (Monday check)
        if self.rules.avoid_monday_expiration:
            exp_date = datetime.strptime(option.expiration_date, "%Y-%m-%d")
            if exp_date.weekday() == 0:  # 0 = Monday
                return False, "Monday expiration (ruled out)"
        
        # Check DTE
        dte = option.days_to_expiration()
        if dte < self.rules.min_dte:
            return False, f"DTE {dte} < min {self.rules.min_dte}"
        if dte > self.rules.max_dte:
            return False, f"DTE {dte} > max {self.rules.max_dte}"
        
        # Check premium
        if option.bid < self.rules.min_premium:
            return False, f"Premium ${option.bid:.2f} < min ${self.rules.min_premium}"
        
        # Check liquidity (bid-ask spread)
        if option.bid_ask_spread > self.rules.max_bid_ask_spread:
            return False, f"Spread ${option.bid_ask_spread:.2f} > max ${self.rules.max_bid_ask_spread}"
        
        # Check delta
        if option.delta is None:
            return False, "No delta data"
        
        # Normalize delta to absolute value (works for both puts and calls)
        abs_delta = OptionChainData.normalize_delta(option.delta, option.option_type)
        if not (self.rules.target_delta_min <= abs_delta <= self.rules.target_delta_max):
            return False, f"Delta {abs_delta:.2f} not in range {self.rules.target_delta_min}-{self.rules.target_delta_max}"
        
        # Check OTM status
        if option.option_type == OptionType.PUT:
            # Put strike should be below current price (OTM)
            if option.strike >= current_price:
                return False, f"Put ${option.strike} >= current ${current_price:.2f} (ITM)"
        elif option.option_type == OptionType.CALL:
            # Call strike should be above current price (OTM)
            if option.strike <= current_price:
                return False, f"Call ${option.strike} <= current ${current_price:.2f} (ITM)"
        
        return True, ""
    
    def screen_options(self, chain: OptionsChain, option_type: OptionType) -> List[OptionChainData]:
        """
        Screen all options in chain for entry opportunities
        
        Args:
            chain: OptionsChain to screen
            option_type: CALL or PUT
            
        Returns:
            List of eligible options, sorted by premium (highest first)
        """
        options = chain.calls if option_type == OptionType.CALL else chain.puts
        eligible = []
        
        for option in options:
            is_eligible, _ = self.evaluate_option_for_entry(option, chain.current_price)
            if is_eligible:
                eligible.append(option)
        
        # Sort by bid price (premium) - highest first
        eligible.sort(key=lambda x: x.bid, reverse=True)
        return eligible
    
    # ========== EXIT EVALUATION ==========
    
    def check_take_profit(self, position: Position) -> bool:
        """
        Check if position should close for profit
        
        Uses 50% profit rule: close when premium drops 50%
        
        Args:
            position: Current position
            
        Returns:
            True if should take profit
        """
        threshold = position.entry_premium * (1 - self.rules.take_profit_pct)
        should_close = position.current_premium <= threshold
        
        if should_close:
            profit = (position.entry_premium - position.current_premium) * position.contracts * 100
            print(f"  ✓ TAKE PROFIT: {position.symbol} {position.option_type.value} "
                  f"${position.strike} - Profit: ${profit:.2f} "
                  f"({self.rules.take_profit_pct*100:.0f}%)")
        
        return should_close
    
    def check_stop_loss(self, position: Position) -> bool:
        """
        Check if position should close to limit loss
        
        Uses 30% stop loss rule: close when loss reaches 30%
        
        Args:
            position: Current position
            
        Returns:
            True if should stop loss
        """
        threshold = position.entry_premium * (1 + self.rules.stop_loss_pct)
        should_close = position.current_premium >= threshold
        
        if should_close:
            loss = (position.current_premium - position.entry_premium) * position.contracts * 100
            print(f"  ⚠ STOP LOSS: {position.symbol} {position.option_type.value} "
                  f"${position.strike} - Loss: ${loss:.2f} "
                  f"({self.rules.stop_loss_pct*100:.0f}%)")
        
        return should_close
    
    def check_time_decay(self, position: Position) -> Optional[str]:
        """
        Monitor time decay (theta)
        
        Returns suggestion to close near expiration
        
        Args:
            position: Current position
            
        Returns:
            Suggestion message or None
        """
        if position.dte <= 1:
            return f"1 DTE or less - consider closing: {position.symbol}"
        
        if position.dte <= 3 and position.theta and position.theta > 0:
            # Theta acceleration in final 3 days
            return f"3 DTE or less - theta accelerating: {position.symbol}"
        
        return None
    
    def evaluate_position(self, position: Position) -> dict:
        """
        Comprehensive position evaluation
        
        Args:
            position: Position to evaluate
            
        Returns:
            Dict with status, recommendation, and details
        """
        result = {
            'position_id': position.position_id,
            'symbol': position.symbol,
            'status': 'MONITORING',
            'actions': [],
            'details': {}
        }
        
        # Check take profit
        if self.check_take_profit(position):
            result['status'] = 'TAKE_PROFIT'
            result['actions'].append('CLOSE_FOR_PROFIT')
        
        # Check stop loss (if not already closing)
        elif self.check_stop_loss(position):
            result['status'] = 'STOP_LOSS'
            result['actions'].append('CLOSE_FOR_LOSS')
        
        # Check time decay
        decay_msg = self.check_time_decay(position)
        if decay_msg:
            result['actions'].append(f'MONITOR: {decay_msg}')
        
        # Calculate P&L
        credit = position.entry_premium * position.contracts * 100
        cost_to_close = position.current_premium * position.contracts * 100
        unrealized_pnl = credit - cost_to_close
        unrealized_pnl_pct = (unrealized_pnl / credit * 100) if credit > 0 else 0
        
        result['details'] = {
            'entry_premium': position.entry_premium,
            'current_premium': position.current_premium,
            'unrealized_pnl': unrealized_pnl,
            'unrealized_pnl_pct': unrealized_pnl_pct,
            'days_held': (datetime.now() - position.entry_date).days,
            'dte': position.dte,
        }
        
        return result
    
    # ========== PORTFOLIO LEVEL ==========
    
    def can_open_trade(self, portfolio: Portfolio, capital_required: float) -> tuple[bool, str]:
        """
        Check if portfolio can open new trade
        Evaluates position count, buying power, PDT rules
        
        Args:
            portfolio: Target portfolio
            capital_required: Capital needed for position (CSP strike × 100)
            
        Returns:
            (can_trade, reason_if_not)
        """
        # Check position limit
        if portfolio.active_position_count() >= portfolio.max_positions:
            return False, f"Max {portfolio.max_positions} positions reached"
        
        # Check buying power
        available = portfolio.available_buying_power()
        if available < capital_required:
            return False, f"Need ${capital_required:.0f}, available ${available:.0f}"
        
        # Check PDT rules
        if portfolio.pdt_compliant:
            # Count day trades in last 5 rolling days
            five_days_ago = datetime.now() - timedelta(days=5)
            recent_trades = [d for d in portfolio.last_trade_dates if d >= five_days_ago]
            
            if len(recent_trades) >= 3:
                return False, f"PDT limit: {len(recent_trades)} day trades in 5 days (max 3)"
        
        return True, ""
    
    def get_tradable_opportunities(self, chain: OptionsChain, 
                                    portfolio: Portfolio, 
                                    max_results: int = 5) -> dict:
        """
        Get top trading opportunities for a portfolio
        
        Args:
            chain: Options chain to analyze
            portfolio: Target portfolio
            max_results: Max options to return per type
            
        Returns:
            Dict with puts and calls opportunities
        """
        opportunities = {
            'puts': [],
            'calls': []
        }
        
        # Screen puts (CSP strategy)
        eligible_puts = self.screen_options(chain, OptionType.PUT)
        for put in eligible_puts[:max_results]:
            capital_needed = put.strike * 100  # CSP ties up cash
            can_trade, reason = self.can_open_trade(portfolio, capital_needed)
            
            if can_trade:
                opportunities['puts'].append({
                    'option': put,
                    'capital_required': capital_needed,
                    'profit_target': put.bid * 0.5,  # 50% profit
                    'loss_limit': put.bid * 1.3,      # 30% loss
                })
        
        # Screen calls (covered call strategy, if has shares)
        eligible_calls = self.screen_options(chain, OptionType.CALL)
        for call in eligible_calls[:max_results]:
            # Calls don't require capital (if covered)
            capital_needed = 0
            can_trade, reason = self.can_open_trade(portfolio, capital_needed)
            
            if can_trade:
                opportunities['calls'].append({
                    'option': call,
                    'capital_required': 0,
                    'profit_target': call.bid * 0.5,
                    'loss_limit': call.bid * 1.3,
                })
        
        return opportunities


class PositionManagementRules:
    """Rules for managing open positions"""
    
    @staticmethod
    def should_roll(position: Position, current_premium: float, 
                   new_credit: float, stop_loss_pct: float = 0.30) -> bool:
        """
        Determine if position should be rolled
        
        Roll when:
        - Position is near stop loss
        - New credit > loss amount
        
        Args:
            position: Current position
            current_premium: Current option premium
            new_credit: Credit from new option
            stop_loss_pct: Stop loss threshold
            
        Returns:
            True if should roll
        """
        loss_threshold = position.entry_premium * (1 + stop_loss_pct)
        
        if current_premium >= loss_threshold:
            # Near stop loss
            loss = (current_premium - position.entry_premium) * position.contracts * 100
            
            if new_credit > abs(loss):
                # New credit offsets loss
                return True
        
        return False
    
    @staticmethod
    def calculate_roll_outcome(position: Position, 
                               close_premium: float,
                               new_premium: float,
                               new_dte: int) -> dict:
        """
        Calculate P&L impact of rolling
        
        Args:
            position: Current position
            close_premium: Premium paid to close current
            new_premium: Premium received from new position
            new_dte: DTE of new position
            
        Returns:
            Dict with roll outcome and new P&L
        """
        original_credit = position.entry_premium * position.contracts * 100
        close_cost = close_premium * position.contracts * 100
        new_credit = new_premium * position.contracts * 100
        
        original_loss = close_cost - original_credit
        roll_net = -original_loss + new_credit
        total_credit = original_credit + new_credit
        
        return {
            'original_loss': original_loss,
            'roll_credit': new_credit,
            'net_impact': roll_net,
            'total_credit_earned': total_credit,
            'new_dte': new_dte,
        }
