"""
Calculator - Position sizing, P&L calculations, Greeks analysis
Handles all mathematical operations for trading logic
"""

from typing import Optional, Dict, List
from datetime import datetime
from models import (
    OptionChainData, Portfolio, Position, TradeEntry, 
    OptionType, RulesConfig
)


class PositionSizer:
    """Calculate position sizing based on portfolio rules"""
    
    @staticmethod
    def calculate_csp_position_size(portfolio: Portfolio, 
                                     option: OptionChainData,
                                     max_position_size: Optional[int] = None) -> int:
        """
        Calculate how many contracts to sell for CSP
        
        Constraints:
        1. Capital available (strike × 100 × contracts)
        2. Max position size (optional limit)
        3. PDT rules (if applicable)
        
        Args:
            portfolio: Target portfolio
            option: Option to sell
            max_position_size: Optional contract limit (default: 1)
            
        Returns:
            Number of contracts to sell
        """
        if max_position_size is None:
            max_position_size = 1
        
        # Capital required per contract
        capital_per_contract = option.strike * 100
        
        # Available capital
        available_capital = portfolio.available_buying_power()
        
        # How many can we afford?
        affordable_contracts = int(available_capital / capital_per_contract)
        
        # Max to 1 contract (conservative for paper trading)
        contracts = min(affordable_contracts, max_position_size)
        
        return max(0, contracts)
    
    @staticmethod
    def calculate_covered_call_size(portfolio: Portfolio,
                                     shares_owned: int,
                                     option: OptionChainData) -> int:
        """
        Calculate covered call position size
        
        Limited by:
        1. Shares owned (max contracts = shares / 100)
        2. Max position limit
        
        Args:
            portfolio: Target portfolio
            shares_owned: Number of shares held
            option: Call option to sell
            
        Returns:
            Number of contracts to sell
        """
        max_contracts_for_shares = shares_owned // 100
        
        # For paper trading, typically 1 contract
        contracts = min(max_contracts_for_shares, 1)
        
        return contracts
    
    @staticmethod
    def get_recommendation(portfolio: Portfolio,
                          option: OptionChainData,
                          strategy: str = "CSP") -> Dict:
        """
        Get sizing recommendation for an option
        
        Args:
            portfolio: Portfolio to trade
            option: Option to evaluate
            strategy: "CSP" or "CC" (covered call)
            
        Returns:
            Dict with recommendation details
        """
        if strategy == "CSP":
            contracts = PositionSizer.calculate_csp_position_size(portfolio, option)
            capital = contracts * option.strike * 100
        elif strategy == "CC":
            # For demo, assume 100 shares
            contracts = PositionSizer.calculate_covered_call_size(portfolio, 100, option)
            capital = 0  # Covered calls don't tie up capital
        else:
            contracts = 0
            capital = 0
        
        return {
            'strategy': strategy,
            'contracts': contracts,
            'capital_required': capital,
            'premium_credit': option.bid * contracts * 100,
        }


class PnLCalculator:
    """Calculate profit/loss for trades"""
    
    @staticmethod
    def calculate_trade_pnl(entry_premium: float,
                            exit_premium: float,
                            contracts: int,
                            commission: float = 0) -> Dict:
        """
        Calculate P&L for a closed trade
        
        Args:
            entry_premium: Premium received at open
            exit_premium: Premium paid at close
            contracts: Number of contracts
            commission: Total commission (if any)
            
        Returns:
            Dict with P&L details
        """
        # Total credit from selling
        credit = entry_premium * contracts * 100
        
        # Total cost to close
        cost = exit_premium * contracts * 100
        
        # Gross P&L
        gross_pnl = credit - cost
        
        # Net P&L (after commission)
        net_pnl = gross_pnl - commission
        
        # Return %
        pnl_pct = (net_pnl / credit * 100) if credit > 0 else 0
        
        return {
            'credit': credit,
            'cost': cost,
            'gross_pnl': gross_pnl,
            'commission': commission,
            'net_pnl': net_pnl,
            'pnl_percent': pnl_pct,
        }
    
    @staticmethod
    def calculate_unrealized_pnl(entry_premium: float,
                                  current_premium: float,
                                  contracts: int) -> Dict:
        """
        Calculate unrealized P&L for open position
        
        Args:
            entry_premium: Entry premium
            current_premium: Current bid price
            contracts: Number of contracts
            
        Returns:
            Dict with unrealized P&L
        """
        credit = entry_premium * contracts * 100
        cost_to_close = current_premium * contracts * 100
        unrealized = credit - cost_to_close
        unrealized_pct = (unrealized / credit * 100) if credit > 0 else 0
        
        return {
            'credit': credit,
            'current_cost': cost_to_close,
            'unrealized_pnl': unrealized,
            'unrealized_pnl_percent': unrealized_pct,
            'to_profit_target': (entry_premium * 0.5 - current_premium) * contracts * 100,
            'to_loss_limit': (current_premium - entry_premium * 1.3) * contracts * 100,
        }
    
    @staticmethod
    def portfolio_summary(portfolio: Portfolio) -> Dict:
        """
        Calculate portfolio-level P&L summary
        
        Args:
            portfolio: Portfolio to analyze
            
        Returns:
            Dict with portfolio metrics
        """
        # Closed trades
        closed_pnl = 0
        closed_trades = 0
        
        for trade in portfolio.trade_history:
            if trade.profit_loss is not None:
                closed_pnl += trade.profit_loss
                closed_trades += 1
        
        # Open positions
        open_pnl = 0
        for position in portfolio.positions:
            if position.unrealized_pnl:
                open_pnl += position.unrealized_pnl
        
        # Summary
        total_pnl = closed_pnl + open_pnl
        return_pct = (total_pnl / portfolio.balance * 100) if portfolio.balance > 0 else 0
        
        return {
            'closed_trades': closed_trades,
            'closed_pnl': closed_pnl,
            'open_positions': portfolio.active_position_count(),
            'open_pnl': open_pnl,
            'total_pnl': total_pnl,
            'return_percent': return_pct,
            'available_capital': portfolio.available_buying_power(),
        }


class GreeksAnalyzer:
    """Analyze option Greeks"""
    
    @staticmethod
    def analyze_option(option: OptionChainData) -> Dict:
        """
        Analyze Greeks for an option
        
        Args:
            option: Option to analyze
            
        Returns:
            Dict with Greeks analysis
        """
        analysis = {
            'delta': option.delta,
            'theta': option.theta,
            'gamma': option.gamma,
            'vega': option.vega,
            'implied_volatility': option.implied_volatility,
        }
        
        # Interpretation
        if option.delta is not None:
            abs_delta = abs(option.delta)
            if abs_delta < 0.30:
                analysis['delta_interpretation'] = "Far OTM, low assignment risk"
            elif abs_delta < 0.70:
                analysis['delta_interpretation'] = "At-the-money region"
            else:
                analysis['delta_interpretation'] = "Deep ITM, high assignment risk"
        
        if option.theta is not None:
            if option.theta > 0:
                analysis['theta_interpretation'] = "Time decay in our favor (seller)"
            else:
                analysis['theta_interpretation'] = "Time decay against us (buyer)"
        
        return analysis
    
    @staticmethod
    def compare_expirations(chain_21_dte: list,
                            chain_45_dte: list) -> Dict:
        """
        Compare Greeks across different expirations
        
        Args:
            chain_21_dte: Options with ~21 DTE
            chain_45_dte: Options with ~45 DTE
            
        Returns:
            Comparison analysis
        """
        # Calculate average theta
        theta_21 = sum([o.theta for o in chain_21_dte if o.theta]) / len(chain_21_dte) if chain_21_dte else 0
        theta_45 = sum([o.theta for o in chain_45_dte if o.theta]) / len(chain_45_dte) if chain_45_dte else 0
        
        # Calculate average premium
        premium_21 = sum([o.bid for o in chain_21_dte]) / len(chain_21_dte) if chain_21_dte else 0
        premium_45 = sum([o.bid for o in chain_45_dte]) / len(chain_45_dte) if chain_45_dte else 0
        
        return {
            'near_term': {
                'dte': '~21',
                'avg_theta': theta_21,
                'avg_premium': premium_21,
                'recommendation': "Higher theta decay" if theta_21 > theta_45 else "Lower theta decay"
            },
            'medium_term': {
                'dte': '~45',
                'avg_theta': theta_45,
                'avg_premium': premium_45,
                'recommendation': "More time = less daily decay" if theta_45 < theta_21 else "Same decay"
            }
        }
    
    @staticmethod
    def portfolio_greeks_summary(positions: list) -> Dict:
        """
        Calculate aggregate Greeks for all positions
        
        Args:
            positions: List of open positions
            
        Returns:
            Aggregate Greeks
        """
        if not positions:
            return {'delta': 0, 'theta': 0, 'gamma': 0, 'vega': 0}
        
        # Note: In real trading, delta/theta need adjustment for position direction
        # For CSPs: delta is negative (bearish)
        # For CCs: delta is positive (bullish)
        
        total_delta = 0
        total_theta = 0
        total_gamma = 0
        total_vega = 0
        
        for pos in positions:
            multiplier = -1 if pos.strategy == "CSP" else 1
            
            if pos.delta:
                total_delta += (pos.delta * multiplier * pos.contracts)
            if pos.theta:
                total_theta += (pos.theta * pos.contracts)
            if pos.gamma:
                total_gamma += (pos.gamma * pos.contracts)
            if pos.vega:
                total_vega += (pos.vega * pos.contracts)
        
        return {
            'total_delta': total_delta,
            'total_theta': total_theta,
            'total_gamma': total_gamma,
            'total_vega': total_vega,
            'interpretation': {
                'delta': "Bearish" if total_delta < -0.5 else "Bullish" if total_delta > 0.5 else "Neutral",
                'theta': "Positive (time decay helps)" if total_theta > 0 else "Negative (time decay hurts)",
            }
        }
