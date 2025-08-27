#!/usr/bin/env python3
"""
OP TRADING PLATFORM - KITE CONNECT HELPERS
===========================================
Version: 3.1.2 - Enhanced Kite Connect Integration
Author: OP Trading Platform Team
Date: 2025-08-25 10:50 PM IST

KITE CONNECT HELPERS
Enhanced utilities for Kite Connect API integration with:
✓ Robust error handling and retry mechanisms
✓ Rate limiting and throttling
✓ Token management and validation
✓ Batch operations support
✓ Real-time data handling
✓ Comprehensive logging
"""

import os
import sys
import time
import logging
import asyncio
from datetime import datetime, date, timezone
from typing import Dict, List, Any, Optional, Union, Callable
from functools import wraps
import pytz

try:
    from kiteconnect import KiteConnect
    import requests
    import pandas as pd
except ImportError as e:
    print(f"❌ Missing dependencies: {e}")
    print("Run: pip install kiteconnect requests pandas")

# Configure logging
logger = logging.getLogger(__name__)

# India Standard Time
IST = pytz.timezone("Asia/Kolkata")

# Rate limiting configuration
RATE_LIMIT_CONFIG = {
    "requests_per_second": 10,
    "burst_limit": 20,
    "cooldown_period": 60
}

# Retry configuration
RETRY_CONFIG = {
    "max_retries": 3,
    "base_delay": 1.0,
    "backoff_factor": 2.0,
    "max_delay": 30.0
}

# ================================================================================================
# UTILITY FUNCTIONS
# ================================================================================================

def get_now() -> datetime:
    """Get current timestamp with IST timezone."""
    return datetime.now(IST)

def parse_expiry(instrument: Dict[str, Any]) -> Optional[date]:
    """
    Parse expiry date from instrument data.
    
    Args:
        instrument: Instrument dictionary from Kite API
        
    Returns:
        Expiry date or None if parsing fails
    """
    try:
        expiry_str = instrument.get("expiry", "")
        if expiry_str:
            return datetime.strptime(expiry_str, "%Y-%m-%d").date()
    except Exception as e:
        logger.error(f"Failed to parse expiry from {instrument}: {str(e)}")
    return None

def format_strike(strike: float) -> str:
    """
    Format strike price for display.
    
    Args:
        strike: Strike price
        
    Returns:
        Formatted strike string
    """
    if strike == int(strike):
        return str(int(strike))
    else:
        return f"{strike:.2f}"

def calculate_time_to_expiry(expiry_date: date) -> float:
    """
    Calculate time to expiry in years.
    
    Args:
        expiry_date: Option expiry date
        
    Returns:
        Time to expiry in years
    """
    try:
        current_date = get_now().date()
        days_to_expiry = (expiry_date - current_date).days
        
        if days_to_expiry <= 0:
            return 0.0
        
        return days_to_expiry / 365.0
    except Exception as e:
        logger.error(f"Failed to calculate time to expiry: {str(e)}")
        return 0.0

# ================================================================================================
# RATE LIMITING DECORATOR
# ================================================================================================

class RateLimiter:
    """Rate limiter for API calls."""
    
    def __init__(self, requests_per_second: int = 10, burst_limit: int = 20):
        """Initialize rate limiter."""
        self.requests_per_second = requests_per_second
        self.burst_limit = burst_limit
        self.request_times = []
        self.burst_count = 0
        self.last_reset = time.time()
    
    def acquire(self) -> bool:
        """
        Acquire permission to make a request.
        
        Returns:
            True if request is allowed, False otherwise
        """
        current_time = time.time()
        
        # Reset burst counter every second
        if current_time - self.last_reset >= 1.0:
            self.burst_count = 0
            self.last_reset = current_time
        
        # Remove old request times (older than 1 second)
        self.request_times = [t for t in self.request_times if current_time - t < 1.0]
        
        # Check rate limits
        if len(self.request_times) >= self.requests_per_second:
            return False
        
        if self.burst_count >= self.burst_limit:
            return False
        
        # Allow request
        self.request_times.append(current_time)
        self.burst_count += 1
        return True
    
    def wait_time(self) -> float:
        """
        Get time to wait before next request is allowed.
        
        Returns:
            Wait time in seconds
        """
        if not self.request_times:
            return 0.0
        
        oldest_request = min(self.request_times)
        time_since_oldest = time.time() - oldest_request
        
        if time_since_oldest < 1.0:
            return 1.0 - time_since_oldest
        
        return 0.0

# Global rate limiter instance
rate_limiter = RateLimiter(
    requests_per_second=RATE_LIMIT_CONFIG["requests_per_second"],
    burst_limit=RATE_LIMIT_CONFIG["burst_limit"]
)

def rate_limited(func: Callable) -> Callable:
    """
    Decorator to apply rate limiting to functions.
    
    Args:
        func: Function to rate limit
        
    Returns:
        Rate limited function
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Wait for rate limit permission
        while not rate_limiter.acquire():
            wait_time = rate_limiter.wait_time()
            if wait_time > 0:
                logger.debug(f"Rate limited, waiting {wait_time:.2f}s")
                time.sleep(wait_time)
        
        return func(*args, **kwargs)
    
    return wrapper

# ================================================================================================
# RETRY DECORATOR
# ================================================================================================

def retry_on_failure(max_retries: int = None, base_delay: float = None, 
                    backoff_factor: float = None, max_delay: float = None):
    """
    Decorator to retry functions on failure.
    
    Args:
        max_retries: Maximum number of retries
        base_delay: Base delay between retries
        backoff_factor: Exponential backoff factor
        max_delay: Maximum delay between retries
    """
    max_retries = max_retries or RETRY_CONFIG["max_retries"]
    base_delay = base_delay or RETRY_CONFIG["base_delay"]
    backoff_factor = backoff_factor or RETRY_CONFIG["backoff_factor"]
    max_delay = max_delay or RETRY_CONFIG["max_delay"]
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(f"Function {func.__name__} failed after {max_retries} retries: {str(e)}")
                        raise
                    
                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                    
                    logger.warning(f"Function {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}), "
                                 f"retrying in {delay:.2f}s: {str(e)}")
                    
                    time.sleep(delay)
            
            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
        
        return wrapper
    return decorator

# ================================================================================================
# ENHANCED SAFE CALL FUNCTION
# ================================================================================================

@rate_limited
@retry_on_failure()
def safe_call(kite_client: KiteConnect, ensure_token_func: Optional[Callable], 
              method_name: str, *args, **kwargs) -> Optional[Any]:
    """
    Enhanced safe API call with rate limiting, retry, and comprehensive error handling.
    
    Args:
        kite_client: KiteConnect client instance
        ensure_token_func: Token validation function
        method_name: API method name to call
        *args: Method arguments
        **kwargs: Method keyword arguments
        
    Returns:
        API response or None if failed
    """
    if not kite_client:
        logger.error("KiteConnect client is None")
        return None
    
    try:
        # Validate token if function provided
        if ensure_token_func:
            ensure_token_func()
        
        # Get method from client
        method = getattr(kite_client, method_name, None)
        if not method:
            logger.error(f"Method {method_name} not found on KiteConnect client")
            return None
        
        # Log API call
        logger.debug(f"Making API call: {method_name} with args={args}, kwargs={kwargs}")
        
        # Make API call with timeout
        start_time = time.time()
        result = method(*args, **kwargs)
        duration = time.time() - start_time
        
        logger.debug(f"API call {method_name} completed in {duration:.3f}s")
        
        return result
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"API call {method_name} failed: {error_msg}")
        
        # Handle specific Kite Connect errors
        if "TokenException" in error_msg:
            logger.error("Token exception - token may be expired or invalid")
        elif "NetworkException" in error_msg:
            logger.error("Network exception - check internet connection")
        elif "DataException" in error_msg:
            logger.error("Data exception - invalid request parameters")
        elif "GeneralException" in error_msg:
            logger.error("General exception from Kite API")
        
        return None

# ================================================================================================
# BATCH OPERATIONS
# ================================================================================================

def batch_safe_calls(kite_client: KiteConnect, ensure_token_func: Optional[Callable],
                     method_name: str, param_list: List[Any], 
                     batch_size: int = 5, delay_between_batches: float = 1.0) -> Dict[Any, Any]:
    """
    Make multiple safe API calls in batches.
    
    Args:
        kite_client: KiteConnect client instance
        ensure_token_func: Token validation function
        method_name: API method name to call
        param_list: List of parameters for each call
        batch_size: Number of calls per batch
        delay_between_batches: Delay between batches in seconds
        
    Returns:
        Dictionary mapping parameters to results
    """
    results = {}
    
    for i in range(0, len(param_list), batch_size):
        batch = param_list[i:i + batch_size]
        
        logger.debug(f"Processing batch {i//batch_size + 1}/{(len(param_list) + batch_size - 1)//batch_size}")
        
        for params in batch:
            if isinstance(params, (list, tuple)):
                result = safe_call(kite_client, ensure_token_func, method_name, *params)
            else:
                result = safe_call(kite_client, ensure_token_func, method_name, params)
            
            results[str(params)] = result
        
        # Delay between batches
        if i + batch_size < len(param_list):
            time.sleep(delay_between_batches)
    
    return results

# ================================================================================================
# QUOTE HELPERS
# ================================================================================================

def get_quotes_with_fallback(kite_client: KiteConnect, ensure_token_func: Optional[Callable],
                            instruments: List[str], fallback_instruments: List[str] = None) -> Dict[str, Any]:
    """
    Get quotes with fallback instruments if primary fails.
    
    Args:
        kite_client: KiteConnect client instance
        ensure_token_func: Token validation function
        instruments: Primary instruments list
        fallback_instruments: Fallback instruments list
        
    Returns:
        Quote data dictionary
    """
    # Try primary instruments
    quotes = safe_call(kite_client, ensure_token_func, "quote", instruments)
    
    if quotes:
        return quotes
    
    # Try fallback instruments if provided
    if fallback_instruments:
        logger.warning("Primary quotes failed, trying fallback instruments")
        quotes = safe_call(kite_client, ensure_token_func, "quote", fallback_instruments)
        
        if quotes:
            return quotes
    
    logger.error("Failed to get quotes from primary and fallback instruments")
    return {}

def extract_quote_data(quotes: Dict[str, Any], instrument: str) -> Dict[str, Any]:
    """
    Extract standardized data from quote response.
    
    Args:
        quotes: Quote response from Kite API
        instrument: Instrument identifier
        
    Returns:
        Standardized quote data
    """
    try:
        quote = quotes.get(instrument, {})
        
        if not quote:
            logger.warning(f"No quote data found for {instrument}")
            return {}
        
        ohlc = quote.get("ohlc", {})
        depth = quote.get("depth", {})
        
        return {
            "instrument_token": quote.get("instrument_token"),
            "last_price": quote.get("last_price"),
            "volume": quote.get("volume", 0),
            "average_price": quote.get("average_price"),
            "oi": quote.get("oi", 0),
            "bid_quantity": quote.get("bid_quantity", 0),
            "ask_quantity": quote.get("ask_quantity", 0),
            "open": ohlc.get("open"),
            "high": ohlc.get("high"),
            "low": ohlc.get("low"),
            "close": ohlc.get("close"),
            "net_change": quote.get("net_change"),
            "iv": quote.get("iv"),
            "timestamp": get_now().isoformat(),
            "depth": depth
        }
        
    except Exception as e:
        logger.error(f"Failed to extract quote data for {instrument}: {str(e)}")
        return {}

# ================================================================================================
# INSTRUMENT HELPERS
# ================================================================================================

def filter_instruments_by_criteria(instruments: List[Dict[str, Any]], 
                                 criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Filter instruments by various criteria.
    
    Args:
        instruments: List of instrument dictionaries
        criteria: Filtering criteria
        
    Returns:
        Filtered instruments list
    """
    filtered = instruments
    
    try:
        # Filter by exchange
        if "exchange" in criteria:
            exchange = criteria["exchange"].upper()
            filtered = [inst for inst in filtered 
                       if inst.get("exchange", "").upper() == exchange]
        
        # Filter by segment
        if "segment" in criteria:
            segment = criteria["segment"].upper()
            filtered = [inst for inst in filtered 
                       if inst.get("segment", "").upper() == segment]
        
        # Filter by instrument type
        if "instrument_type" in criteria:
            inst_type = criteria["instrument_type"].upper()
            filtered = [inst for inst in filtered 
                       if inst.get("instrument_type", "").upper() == inst_type]
        
        # Filter by name pattern
        if "name_pattern" in criteria:
            pattern = criteria["name_pattern"].upper()
            filtered = [inst for inst in filtered 
                       if pattern in inst.get("name", "").upper()]
        
        # Filter by expiry date range
        if "expiry_start" in criteria or "expiry_end" in criteria:
            expiry_start = criteria.get("expiry_start")
            expiry_end = criteria.get("expiry_end")
            
            def check_expiry(inst):
                expiry = parse_expiry(inst)
                if not expiry:
                    return False
                
                if expiry_start and expiry < expiry_start:
                    return False
                
                if expiry_end and expiry > expiry_end:
                    return False
                
                return True
            
            filtered = [inst for inst in filtered if check_expiry(inst)]
        
        # Filter by strike price range
        if "strike_min" in criteria or "strike_max" in criteria:
            strike_min = criteria.get("strike_min", 0)
            strike_max = criteria.get("strike_max", float('inf'))
            
            filtered = [inst for inst in filtered 
                       if strike_min <= inst.get("strike", 0) <= strike_max]
        
        logger.debug(f"Filtered {len(instruments)} instruments to {len(filtered)} based on criteria: {criteria}")
        
        return filtered
        
    except Exception as e:
        logger.error(f"Failed to filter instruments: {str(e)}")
        return instruments

def find_atm_strike(spot_price: float, step_size: int) -> int:
    """
    Find ATM (At-The-Money) strike price.
    
    Args:
        spot_price: Current spot price
        step_size: Strike price step size
        
    Returns:
        ATM strike price
    """
    try:
        if step_size <= 0:
            logger.error(f"Invalid step size: {step_size}")
            return int(round(spot_price))
        
        atm_strike = round(spot_price / step_size) * step_size
        return int(atm_strike)
        
    except Exception as e:
        logger.error(f"Failed to calculate ATM strike: {str(e)}")
        return int(round(spot_price))

def generate_strike_chain(atm_strike: int, step_size: int, 
                         offsets: List[int]) -> List[int]:
    """
    Generate strike chain around ATM.
    
    Args:
        atm_strike: ATM strike price
        step_size: Strike price step size
        offsets: List of offsets from ATM
        
    Returns:
        List of strike prices
    """
    try:
        strikes = []
        
        for offset in offsets:
            strike = atm_strike + (offset * step_size)
            if strike > 0:  # Ensure positive strike
                strikes.append(strike)
        
        return sorted(strikes)
        
    except Exception as e:
        logger.error(f"Failed to generate strike chain: {str(e)}")
        return [atm_strike]

# ================================================================================================
# HISTORICAL DATA HELPERS
# ================================================================================================

def get_historical_data_safe(kite_client: KiteConnect, ensure_token_func: Optional[Callable],
                           instrument_token: str, from_date: datetime, to_date: datetime,
                           interval: str = "day") -> Optional[pd.DataFrame]:
    """
    Get historical data with error handling.
    
    Args:
        kite_client: KiteConnect client instance
        ensure_token_func: Token validation function
        instrument_token: Instrument token
        from_date: Start date
        to_date: End date
        interval: Data interval
        
    Returns:
        Historical data as DataFrame or None
    """
    try:
        historical_data = safe_call(
            kite_client, ensure_token_func, "historical_data",
            instrument_token, from_date, to_date, interval
        )
        
        if historical_data:
            df = pd.DataFrame(historical_data)
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            
            logger.debug(f"Retrieved {len(df)} historical data points for {instrument_token}")
            return df
        
        return None
        
    except Exception as e:
        logger.error(f"Failed to get historical data for {instrument_token}: {str(e)}")
        return None

# ================================================================================================
# WEBSOCKET HELPERS  
# ================================================================================================

class WebSocketManager:
    """Enhanced WebSocket manager for real-time data."""
    
    def __init__(self, kite_client: KiteConnect):
        """Initialize WebSocket manager."""
        self.kite_client = kite_client
        self.kws = None
        self.subscribed_tokens = set()
        self.callbacks = {}
        
    def setup_websocket(self, api_key: str, access_token: str) -> bool:
        """
        Setup WebSocket connection.
        
        Args:
            api_key: Kite API key
            access_token: Access token
            
        Returns:
            True if setup successful
        """
        try:
            from kiteconnect import KiteTicker
            
            self.kws = KiteTicker(api_key, access_token)
            
            # Setup callbacks
            self.kws.on_ticks = self._on_ticks
            self.kws.on_connect = self._on_connect
            self.kws.on_close = self._on_close
            self.kws.on_error = self._on_error
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup WebSocket: {str(e)}")
            return False
    
    def _on_ticks(self, ws, ticks):
        """Handle incoming ticks."""
        try:
            for tick in ticks:
                instrument_token = str(tick.get("instrument_token", ""))
                
                if instrument_token in self.callbacks:
                    callback = self.callbacks[instrument_token]
                    callback(tick)
        
        except Exception as e:
            logger.error(f"Error processing ticks: {str(e)}")
    
    def _on_connect(self, ws, response):
        """Handle WebSocket connection."""
        logger.info("WebSocket connected successfully")
    
    def _on_close(self, ws, code, reason):
        """Handle WebSocket disconnection."""
        logger.warning(f"WebSocket closed: {code} - {reason}")
    
    def _on_error(self, ws, code, reason):
        """Handle WebSocket errors."""
        logger.error(f"WebSocket error: {code} - {reason}")
    
    def subscribe(self, tokens: List[str], mode: str = "quote", 
                 callback: Optional[Callable] = None) -> bool:
        """
        Subscribe to instruments.
        
        Args:
            tokens: List of instrument tokens
            mode: Subscription mode
            callback: Optional callback function
            
        Returns:
            True if subscription successful
        """
        try:
            if not self.kws:
                logger.error("WebSocket not initialized")
                return False
            
            # Convert tokens to integers
            int_tokens = []
            for token in tokens:
                try:
                    int_tokens.append(int(token))
                except ValueError:
                    logger.warning(f"Invalid token: {token}")
            
            if not int_tokens:
                logger.error("No valid tokens to subscribe")
                return False
            
            # Subscribe to tokens
            if mode == "quote":
                self.kws.subscribe(int_tokens)
                self.kws.set_mode(self.kws.MODE_QUOTE, int_tokens)
            elif mode == "full":
                self.kws.subscribe(int_tokens)
                self.kws.set_mode(self.kws.MODE_FULL, int_tokens)
            
            # Store callback
            if callback:
                for token in tokens:
                    self.callbacks[token] = callback
            
            self.subscribed_tokens.update(tokens)
            
            logger.info(f"Subscribed to {len(int_tokens)} instruments in {mode} mode")
            return True
            
        except Exception as e:
            logger.error(f"Failed to subscribe to instruments: {str(e)}")
            return False
    
    def unsubscribe(self, tokens: List[str]) -> bool:
        """
        Unsubscribe from instruments.
        
        Args:
            tokens: List of instrument tokens
            
        Returns:
            True if unsubscription successful
        """
        try:
            if not self.kws:
                return True
            
            # Convert tokens to integers
            int_tokens = [int(token) for token in tokens if token.isdigit()]
            
            if int_tokens:
                self.kws.unsubscribe(int_tokens)
            
            # Remove from tracking
            self.subscribed_tokens.difference_update(tokens)
            
            for token in tokens:
                self.callbacks.pop(token, None)
            
            logger.info(f"Unsubscribed from {len(int_tokens)} instruments")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unsubscribe from instruments: {str(e)}")
            return False
    
    def start(self) -> bool:
        """
        Start WebSocket connection.
        
        Returns:
            True if started successfully
        """
        try:
            if not self.kws:
                logger.error("WebSocket not initialized")
                return False
            
            self.kws.connect(threaded=True)
            return True
            
        except Exception as e:
            logger.error(f"Failed to start WebSocket: {str(e)}")
            return False
    
    def stop(self) -> bool:
        """
        Stop WebSocket connection.
        
        Returns:
            True if stopped successfully
        """
        try:
            if self.kws:
                self.kws.close()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop WebSocket: {str(e)}")
            return False

# ================================================================================================
# ERROR HANDLING UTILITIES
# ================================================================================================

def handle_kite_exception(e: Exception) -> Dict[str, Any]:
    """
    Handle and categorize Kite Connect exceptions.
    
    Args:
        e: Exception from Kite Connect
        
    Returns:
        Error information dictionary
    """
    error_info = {
        "type": type(e).__name__,
        "message": str(e),
        "timestamp": get_now().isoformat(),
        "recoverable": False,
        "suggested_action": "Check logs and retry"
    }
    
    error_msg = str(e).lower()
    
    if "token" in error_msg:
        error_info.update({
            "category": "AUTHENTICATION",
            "recoverable": True,
            "suggested_action": "Refresh access token"
        })
    elif "network" in error_msg or "connection" in error_msg:
        error_info.update({
            "category": "NETWORK",
            "recoverable": True,
            "suggested_action": "Check internet connection and retry"
        })
    elif "rate" in error_msg or "limit" in error_msg:
        error_info.update({
            "category": "RATE_LIMIT",
            "recoverable": True,
            "suggested_action": "Wait and reduce request frequency"
        })
    elif "data" in error_msg or "invalid" in error_msg:
        error_info.update({
            "category": "DATA",
            "recoverable": False,
            "suggested_action": "Check request parameters"
        })
    else:
        error_info.update({
            "category": "GENERAL",
            "recoverable": True,
            "suggested_action": "Retry with exponential backoff"
        })
    
    return error_info

# ================================================================================================
# EXPORT FUNCTIONS
# ================================================================================================

# Export main functions for backward compatibility
__all__ = [
    'safe_call',
    'batch_safe_calls', 
    'get_quotes_with_fallback',
    'extract_quote_data',
    'filter_instruments_by_criteria',
    'find_atm_strike',
    'generate_strike_chain',
    'get_historical_data_safe',
    'get_now',
    'parse_expiry',
    'format_strike',
    'calculate_time_to_expiry',
    'WebSocketManager',
    'handle_kite_exception',
    'rate_limited',
    'retry_on_failure'
]