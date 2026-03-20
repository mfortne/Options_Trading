"""
Rules parser - Extract trading rules from markdown configuration
Parses trading_rules.md into structured RulesConfig
"""

import re
from typing import Dict, List
from models import RulesConfig


class RulesParser:
    """Parse trading rules from markdown file"""
    
    @staticmethod
    def parse_file(filepath: str) -> RulesConfig:
        """
        Parse markdown rules file into RulesConfig
        
        Args:
            filepath: Path to trading_rules.md
            
        Returns:
            RulesConfig object with all rules extracted
        """
        with open(filepath, 'r') as f:
            content = f.read()
        
        rules = RulesConfig()
        
        # Extract configuration variables section
        var_section = RulesParser._extract_section(content, "Configuration Variables")
        if var_section:
            rules = RulesParser._parse_variables(var_section, rules)
        
        # Extract entry rules
        entry_section = RulesParser._extract_section(content, "Entry Rules")
        if entry_section:
            rules = RulesParser._parse_entry_rules(entry_section, rules)
        
        # Extract exit rules
        exit_section = RulesParser._extract_section(content, "Exit Rules")
        if exit_section:
            rules = RulesParser._parse_exit_rules(exit_section, rules)
        
        return rules
    
    @staticmethod
    def _extract_section(content: str, section_name: str) -> str:
        """
        Extract a section from markdown content
        
        Args:
            content: Full markdown content
            section_name: Section header to find
            
        Returns:
            Content of the section or empty string
        """
        # Find section header (## or ### format)
        pattern = rf"^#+\s*{re.escape(section_name)}.*?(?=^#+\s|\Z)"
        match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
        if match:
            return match.group(0)
        return ""
    
    @staticmethod
    def _parse_variables(section: str, rules: RulesConfig) -> RulesConfig:
        """
        Parse configuration variables from code block
        
        Example:
        ```python
        TARGET_PROFIT_PCT = 0.50
        MAX_LOSS_PCT = 0.30
        TARGET_DELTA_RANGE = (0.10, 0.20)
        ```
        """
        # Extract code block
        code_match = re.search(r'```(?:python)?\n(.*?)\n```', section, re.DOTALL)
        if not code_match:
            return rules
        
        code = code_match.group(1)
        
        # Parse variable assignments
        patterns = {
            'target_profit_pct': (r'TARGET_PROFIT_PCT\s*=\s*([\d.]+)', float),
            'stop_loss_pct': (r'MAX_LOSS_PCT\s*=\s*([\d.]+)', float),
            'min_dte': (r'MIN_DTE\s*=\s*(\d+)', int),
            'max_dte': (r'MAX_DTE\s*=\s*(\d+)', int),
            'preferred_dte_min': (r'PREFERRED_DTE\s*=\s*\(\s*(\d+)', int),
            'preferred_dte_max': (r'PREFERRED_DTE\s*=\s*\(\s*\d+,\s*(\d+)', int),
            'min_premium': (r'MIN_PREMIUM\s*=\s*([\d.]+)', float),
            'max_bid_ask_spread': (r'MAX_BID_ASK_SPREAD\s*=\s*([\d.]+)', float),
            'avoid_monday_expiration': (r'NO_MONDAY_EXPIRATION\s*=\s*(True|False)', lambda x: x == 'True'),
        }
        
        for attr, (pattern, converter) in patterns.items():
            match = re.search(pattern, code)
            if match:
                try:
                    value = converter(match.group(1))
                    setattr(rules, attr, value)
                except (ValueError, IndexError):
                    pass
        
        # Parse delta range (special case)
        delta_match = re.search(r'TARGET_DELTA_RANGE\s*=\s*\(\s*([\d.]+)\s*,\s*([\d.]+)\s*\)', code)
        if delta_match:
            try:
                rules.target_delta_min = float(delta_match.group(1))
                rules.target_delta_max = float(delta_match.group(2))
            except ValueError:
                pass
        
        return rules
    
    @staticmethod
    def _parse_entry_rules(section: str, rules: RulesConfig) -> RulesConfig:
        """
        Parse entry rules section
        Extracts strike selection, DTE, premium requirements
        """
        # Look for delta/OTM mentions
        if '80-90% OTM' in section or '80-90' in section:
            # Already set in variables section
            pass
        
        # Extract strike price description if present
        # (For future: could extract specific strike offsets)
        
        return rules
    
    @staticmethod
    def _parse_exit_rules(section: str, rules: RulesConfig) -> RulesConfig:
        """
        Parse exit rules section
        Extracts take profit % and stop loss %
        """
        # Extract take profit percentage
        tp_match = re.search(r'(?:drops?|50%|profit)\s*(?:at|when|:)\s*([0-9.]+)%', section, re.IGNORECASE)
        if tp_match:
            try:
                rules.take_profit_pct = float(tp_match.group(1)) / 100
            except ValueError:
                pass
        
        # Extract stop loss percentage
        sl_match = re.search(r'(?:loss|hits?|reaches?)\s*(?:at|when|:)\s*([0-9.]+)%', section, re.IGNORECASE)
        if sl_match:
            try:
                rules.stop_loss_pct = float(sl_match.group(1)) / 100
            except ValueError:
                pass
        
        return rules
    
    @staticmethod
    def create_from_config(config_dict: Dict) -> RulesConfig:
        """
        Create RulesConfig directly from config dictionary
        (Fallback if markdown parsing fails)
        
        Args:
            config_dict: Dictionary with rules section from portfolio_config.json
            
        Returns:
            RulesConfig object
        """
        return RulesConfig(
            target_delta_min=config_dict.get('target_delta_min', 0.10),
            target_delta_max=config_dict.get('target_delta_max', 0.20),
            min_dte=config_dict.get('min_dte', 7),
            max_dte=config_dict.get('max_dte', 45),
            preferred_dte_min=config_dict.get('preferred_dte_min', 21),
            preferred_dte_max=config_dict.get('preferred_dte_max', 30),
            min_premium=config_dict.get('min_premium', 0.10),
            max_bid_ask_spread=config_dict.get('max_bid_ask_spread', 0.05),
            take_profit_pct=config_dict.get('take_profit_pct', 0.50),
            stop_loss_pct=config_dict.get('stop_loss_pct', 0.30),
            avoid_monday_expiration=config_dict.get('avoid_monday_expiration', True),
            preferred_symbols=config_dict.get('preferred_symbols', []),
        )
