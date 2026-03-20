"""
SQLite caching for options data
Minimizes API calls by caching recent fetches
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from models import OptionsChain, OptionChainData, OptionType


class OptionsCache:
    """SQLite cache for options chains"""
    
    def __init__(self, db_path: str = "data/cache.db"):
        """
        Initialize cache
        
        Args:
            db_path: Path to SQLite database
            
        Raises:
            PermissionError: If cannot write to database path
            RuntimeError: If database initialization fails
        """
        self.db_path = db_path
        
        # Create directory with error handling
        try:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            raise PermissionError(f"Cannot write to {self.db_path}. Check directory permissions: {e}")
        except Exception as e:
            raise RuntimeError(f"Error creating cache directory at {self.db_path}: {e}")
        
        self._init_db()
    
    def _init_db(self):
        """Create tables if they don't exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Options chain cache
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS options_chains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                expiration_date TEXT NOT NULL,
                current_price REAL,
                fetch_time TIMESTAMP,
                data TEXT NOT NULL,
                UNIQUE(symbol, expiration_date)
            )
        """)
        
        # Stock price cache (for quote endpoint)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT UNIQUE NOT NULL,
                current_price REAL,
                fetch_time TIMESTAMP
            )
        """)
        
        # Metadata for cache management
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache_meta (
                key TEXT UNIQUE NOT NULL,
                value TEXT,
                updated_time TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    def set_options_chain(self, chain: OptionsChain, ttl_minutes: int = 60):
        """
        Cache options chain
        
        Args:
            chain: OptionsChain object
            ttl_minutes: Time to live in minutes
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Serialize to JSON
        chain_dict = {
            'symbol': chain.symbol,
            'current_price': chain.current_price,
            'fetch_time': chain.fetch_time.isoformat(),
            'calls': [json.loads(c.model_dump_json()) for c in chain.calls],
            'puts': [json.loads(p.model_dump_json()) for p in chain.puts],
        }
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO options_chains
                (symbol, expiration_date, current_price, fetch_time, data)
                VALUES (?, ?, ?, ?, ?)
            """, (
                chain.symbol,
                chain.calls[0].expiration_date if chain.calls else chain.puts[0].expiration_date,
                chain.current_price,
                datetime.now(),
                json.dumps(chain_dict)
            ))
            conn.commit()
        finally:
            conn.close()
    
    def get_options_chain(self, symbol: str, expiration_date: str, 
                         ttl_minutes: int = 60) -> Optional[OptionsChain]:
        """
        Retrieve cached options chain if fresh enough
        
        Args:
            symbol: Stock symbol
            expiration_date: Expiration date (YYYY-MM-DD)
            ttl_minutes: Maximum age in minutes before cache expires
            
        Returns:
            OptionsChain if cache hit and fresh, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT data, fetch_time FROM options_chains
                WHERE symbol = ? AND expiration_date = ?
            """, (symbol, expiration_date))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            data_json, fetch_time_str = row
            fetch_time = datetime.fromisoformat(fetch_time_str)
            
            # Check if cache is still fresh
            age = datetime.now() - fetch_time
            if age > timedelta(minutes=ttl_minutes):
                return None
            
            # Deserialize
            chain_dict = json.loads(data_json)
            chain = OptionsChain(
                symbol=chain_dict['symbol'],
                current_price=chain_dict['current_price'],
                fetch_time=datetime.fromisoformat(chain_dict['fetch_time']),
                calls=[
                    OptionChainData(**call_dict)
                    for call_dict in chain_dict['calls']
                ],
                puts=[
                    OptionChainData(**put_dict)
                    for put_dict in chain_dict['puts']
                ]
            )
            
            return chain
        
        finally:
            conn.close()
    
    def set_quote(self, symbol: str, quote: dict, ttl_minutes: int = 5):
        """
        Cache stock quote
        
        Args:
            symbol: Stock symbol
            quote: Quote data (from finnhub_client.get_quote)
            ttl_minutes: Time to live
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO quotes
                (symbol, current_price, fetch_time)
                VALUES (?, ?, ?)
            """, (symbol, quote['current_price'], datetime.now()))
            
            conn.commit()
        finally:
            conn.close()
    
    def get_quote(self, symbol: str, ttl_minutes: int = 5) -> Optional[float]:
        """
        Retrieve cached quote if fresh
        
        Args:
            symbol: Stock symbol
            ttl_minutes: Maximum age
            
        Returns:
            Current price or None if cache miss/expired
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT current_price, fetch_time FROM quotes
                WHERE symbol = ?
            """, (symbol,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            price, fetch_time_str = row
            fetch_time = datetime.fromisoformat(fetch_time_str)
            
            age = datetime.now() - fetch_time
            if age > timedelta(minutes=ttl_minutes):
                return None
            
            return price
        
        finally:
            conn.close()
    
    def clear_expired(self, ttl_minutes: int = 60):
        """Remove expired cache entries"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cutoff_time = datetime.now() - timedelta(minutes=ttl_minutes)
            cursor.execute("""
                DELETE FROM options_chains WHERE fetch_time < ?
            """, (cutoff_time,))
            
            cursor.execute("""
                DELETE FROM quotes WHERE fetch_time < ?
            """, (cutoff_time,))
            
            conn.commit()
        finally:
            conn.close()
    
    def get_cache_size(self) -> dict:
        """Get cache statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) FROM options_chains")
            chains_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM quotes")
            quotes_count = cursor.fetchone()[0]
            
            return {
                'options_chains': chains_count,
                'quotes': quotes_count,
            }
        finally:
            conn.close()
    
    def clear_all(self):
        """Clear entire cache (for testing)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("DELETE FROM options_chains")
            cursor.execute("DELETE FROM quotes")
            conn.commit()
        finally:
            conn.close()
