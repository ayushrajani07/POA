"""
Comprehensive test framework for the OP trading platform.
Includes unit tests, integration tests, property-based testing, and chaos engineering.
Provides mock data feeds for off-market testing and validation.
"""

import unittest
import asyncio
import pytest
import hypothesis
from hypothesis import given, strategies as st, settings, Verbosity
import tempfile
import shutil
import json
import csv
import time
import random
import threading
from typing import Dict, List, Any, Optional, Generator, Callable
from pathlib import Path
from datetime import datetime, date, timedelta
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from dataclasses import dataclass, field
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import logging
import os
import sys
import redis

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from shared.config.settings import get_settings, Settings
from shared.utils.time_utils import get_time_utils, TimeFormat
from shared.utils.coordination import get_redis_coordinator, get_file_coordinator
from services.processing.writers.consolidated_csv_writer import (
    ConsolidatedCSVWriter, OptionLegData, MergedOptionData
)

logger = logging.getLogger(__name__)

# Test configuration
@dataclass 
class TestConfig:
    """Test environment configuration"""
    test_data_dir: Path = field(default_factory=lambda: Path("tests/test_data"))
    mock_redis: bool = True
    enable_chaos_testing: bool = False
    chaos_failure_rate: float = 0.1
    performance_test_duration: int = 300  # seconds
    load_test_concurrent_users: int = 10
    property_test_max_examples: int = 1000

class MockDataGenerator:
    """Generate realistic mock market data for testing"""
    
    def __init__(self):
        self.time_utils = get_time_utils()
        self.indices = ["NIFTY", "BANKNIFTY", "SENSEX"]
        self.buckets = ["this_week", "next_week", "this_month", "next_month"]
        self.offsets = [-2, -1, 0, 1, 2]
        self.sides = ["CALL", "PUT"]
        
        # Realistic market data parameters
        self.base_prices = {"NIFTY": 25000, "BANKNIFTY": 52000, "SENSEX": 82000}
        self.step_sizes = {"NIFTY": 50, "BANKNIFTY": 100, "SENSEX": 100}
    
    def generate_option_leg(self, index: str = None, 
                           bucket: str = None,
                           offset: int = None, 
                           side: str = None,
                           timestamp: datetime = None) -> OptionLegData:
        """Generate a single realistic option leg"""
        
        # Random selections if not specified
        index = index or random.choice(self.indices)
        bucket = bucket or random.choice(self.buckets)
        offset = offset if offset is not None else random.choice(self.offsets)
        side = side or random.choice(self.sides)
        timestamp = timestamp or self.time_utils.now_ist()
        
        # Calculate strikes
        base_price = self.base_prices[index]
        step_size = self.step_sizes[index]
        atm_strike = round(base_price / step_size) * step_size
        strike = atm_strike + (offset * step_size)
        
        # Generate realistic option pricing
        time_to_expiry = self._get_time_to_expiry(bucket)
        intrinsic_value = max(0, (base_price - strike) if side == "CALL" else (strike - base_price))
        
        # Simple IV model (higher for OTM, varies by time)
        iv = self._calculate_realistic_iv(offset, time_to_expiry, index)
        
        # Black-Scholes approximation for time value
        time_value = self._approximate_time_value(base_price, strike, time_to_expiry, iv, side)
        last_price = intrinsic_value + time_value
        
        # Generate volume and OI (correlated with proximity to ATM)
        volume = self._generate_volume(offset, index)
        oi = self._generate_oi(offset, index)
        
        # Generate bid-ask spread
        bid, ask = self._generate_bid_ask_spread(last_price, iv)
        
        # Generate Greeks (simplified)
        delta = self._calculate_delta(base_price, strike, time_to_expiry, iv, side)
        gamma = self._calculate_gamma(base_price, strike, time_to_expiry, iv)
        theta = self._calculate_theta(time_value, time_to_expiry)
        vega = self._calculate_vega(base_price, strike, time_to_expiry, iv)
        
        return OptionLegData(
            ts=self.time_utils.format_time(timestamp, TimeFormat.CSV_STANDARD),
            index=index,
            bucket=bucket,
            expiry=self._get_expiry_date(bucket).isoformat(),
            side=side,
            atm_strike=float(atm_strike),
            strike=float(strike),
            strike_offset=offset,
            last_price=round(last_price, 2),
            bid=round(bid, 2),
            ask=round(ask, 2),
            volume=int(volume),
            oi=int(oi),
            iv=round(iv, 4),
            delta=round(delta, 4),
            gamma=round(gamma, 6),
            theta=round(theta, 4),
            vega=round(vega, 4)
        )
    
    def generate_option_chain(self, index: str, 
                            bucket: str, 
                            timestamp: datetime = None,
                            include_both_sides: bool = True) -> List[OptionLegData]:
        """Generate a complete option chain for given parameters"""
        legs = []
        timestamp = timestamp or self.time_utils.now_ist()
        
        for offset in self.offsets:
            sides_to_generate = self.sides if include_both_sides else ["CALL"]
            for side in sides_to_generate:
                leg = self.generate_option_leg(index, bucket, offset, side, timestamp)
                legs.append(leg)
        
        return legs
    
    def generate_time_series(self, index: str, 
                           bucket: str, 
                           start_time: datetime,
                           end_time: datetime,
                           interval_minutes: int = 1) -> List[OptionLegData]:
        """Generate time series of option data"""
        legs = []
        current_time = start_time
        
        while current_time <= end_time:
            if self.time_utils.is_market_open(current_time):
                chain = self.generate_option_chain(index, bucket, current_time)
                legs.extend(chain)
            
            current_time += timedelta(minutes=interval_minutes)
        
        return legs
    
    def generate_corrupted_data(self, clean_data: List[OptionLegData], 
                              corruption_rate: float = 0.1) -> List[OptionLegData]:
        """Generate data with intentional corruptions for testing error handling"""
        corrupted = []
        
        for leg in clean_data:
            if random.random() < corruption_rate:
                # Apply random corruption
                corruption_type = random.choice([
                    "missing_price", "negative_volume", "extreme_iv", 
                    "invalid_timestamp", "missing_fields"
                ])
                
                leg_dict = leg.to_dict()
                
                if corruption_type == "missing_price":
                    leg_dict["last_price"] = None
                elif corruption_type == "negative_volume":
                    leg_dict["volume"] = -random.randint(1, 1000)
                elif corruption_type == "extreme_iv":
                    leg_dict["iv"] = random.choice([10.0, -1.0, 0.0])  # Unrealistic IV
                elif corruption_type == "invalid_timestamp":
                    leg_dict["ts"] = "invalid-timestamp"
                elif corruption_type == "missing_fields":
                    # Remove random fields
                    fields_to_remove = random.sample(["bid", "ask", "volume", "oi"], 2)
                    for field in fields_to_remove:
                        leg_dict[field] = None
                
                try:
                    corrupted_leg = OptionLegData.from_dict(leg_dict)
                    corrupted.append(corrupted_leg)
                except Exception:
                    # If corruption makes data unparseable, add original
                    corrupted.append(leg)
            else:
                corrupted.append(leg)
        
        return corrupted
    
    def _get_time_to_expiry(self, bucket: str) -> float:
        """Get approximate time to expiry in years"""
        if bucket == "this_week":
            return 7 / 365.25
        elif bucket == "next_week":
            return 14 / 365.25
        elif bucket == "this_month":
            return 30 / 365.25
        else:  # next_month
            return 60 / 365.25
    
    def _get_expiry_date(self, bucket: str) -> date:
        """Get approximate expiry date"""
        today = self.time_utils.get_current_date_ist()
        if bucket == "this_week":
            days_ahead = 7 - today.weekday() if today.weekday() < 4 else 7
            return today + timedelta(days=days_ahead)
        elif bucket == "next_week":
            return today + timedelta(days=14)
        elif bucket == "this_month":
            return today + timedelta(days=30)
        else:
            return today + timedelta(days=60)
    
    def _calculate_realistic_iv(self, offset: int, time_to_expiry: float, index: str) -> float:
        """Calculate realistic implied volatility"""
        base_iv = {"NIFTY": 0.15, "BANKNIFTY": 0.18, "SENSEX": 0.14}[index]
        
        # IV smile: higher for OTM options
        iv_adjustment = abs(offset) * 0.02
        
        # Time decay effect
        time_adjustment = (1 - time_to_expiry) * 0.05
        
        # Random noise
        noise = random.gauss(0, 0.02)
        
        iv = base_iv + iv_adjustment + time_adjustment + noise
        return max(0.05, min(2.0, iv))  # Clamp between reasonable bounds
    
    def _approximate_time_value(self, spot: float, strike: float, 
                               time_to_expiry: float, iv: float, side: str) -> float:
        """Simplified time value calculation"""
        import math
        
        # Simplified Black-Scholes time value
        d1 = (math.log(spot / strike) + (0.05 + 0.5 * iv**2) * time_to_expiry) / (iv * math.sqrt(time_to_expiry))
        d2 = d1 - iv * math.sqrt(time_to_expiry)
        
        try:
            # Approximation using normal distribution
            n_d1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
            n_d2 = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
            
            if side == "CALL":
                time_value = spot * n_d1 - strike * math.exp(-0.05 * time_to_expiry) * n_d2
            else:  # PUT
                time_value = strike * math.exp(-0.05 * time_to_expiry) * (1 - n_d2) - spot * (1 - n_d1)
            
            return max(0, time_value)
        except (OverflowError, ValueError):
            # Fallback for extreme values
            return spot * 0.1 * iv * math.sqrt(time_to_expiry)
    
    def _generate_volume(self, offset: int, index: str) -> int:
        """Generate realistic volume based on strike proximity"""
        base_volumes = {"NIFTY": 10000, "BANKNIFTY": 5000, "SENSEX": 2000}
        base_vol = base_volumes[index]
        
        # Higher volume for ATM
        atm_multiplier = max(0.1, 1 - abs(offset) * 0.3)
        volume = int(random.lognormvariate(math.log(base_vol * atm_multiplier), 0.5))
        return max(0, volume)
    
    def _generate_oi(self, offset: int, index: str) -> int:
        """Generate realistic open interest"""
        base_oi = {"NIFTY": 50000, "BANKNIFTY": 25000, "SENSEX": 10000}[index]
        atm_multiplier = max(0.2, 1 - abs(offset) * 0.2)
        oi = int(random.lognormvariate(math.log(base_oi * atm_multiplier), 0.3))
        return max(0, oi)
    
    def _generate_bid_ask_spread(self, last_price: float, iv: float) -> tuple[float, float]:
        """Generate realistic bid-ask spread"""
        # Spread widens with higher IV and lower price
        spread_pct = min(0.05, 0.01 + iv * 0.02 + max(0, (10 - last_price)) * 0.001)
        spread = last_price * spread_pct
        
        bid = max(0.05, last_price - spread / 2)
        ask = last_price + spread / 2
        
        return bid, ask
    
    def _calculate_delta(self, spot: float, strike: float, 
                        time_to_expiry: float, iv: float, side: str) -> float:
        """Simplified delta calculation"""
        import math
        
        if time_to_expiry <= 0:
            if side == "CALL":
                return 1.0 if spot > strike else 0.0
            else:
                return -1.0 if spot < strike else 0.0
        
        d1 = (math.log(spot / strike) + (0.05 + 0.5 * iv**2) * time_to_expiry) / (iv * math.sqrt(time_to_expiry))
        
        try:
            n_d1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
            if side == "CALL":
                return n_d1
            else:
                return n_d1 - 1
        except (OverflowError, ValueError):
            return 0.5 if side == "CALL" else -0.5
    
    def _calculate_gamma(self, spot: float, strike: float, 
                        time_to_expiry: float, iv: float) -> float:
        """Simplified gamma calculation"""
        import math
        
        if time_to_expiry <= 0:
            return 0.0
        
        d1 = (math.log(spot / strike) + (0.05 + 0.5 * iv**2) * time_to_expiry) / (iv * math.sqrt(time_to_expiry))
        
        try:
            # Approximation of normal PDF
            pdf_d1 = math.exp(-0.5 * d1**2) / math.sqrt(2 * math.pi)
            gamma = pdf_d1 / (spot * iv * math.sqrt(time_to_expiry))
            return gamma
        except (OverflowError, ValueError):
            return 0.001
    
    def _calculate_theta(self, time_value: float, time_to_expiry: float) -> float:
        """Simplified theta calculation"""
        if time_to_expiry <= 0:
            return 0.0
        return -time_value / (time_to_expiry * 365.25)  # Daily theta
    
    def _calculate_vega(self, spot: float, strike: float, 
                       time_to_expiry: float, iv: float) -> float:
        """Simplified vega calculation"""
        import math
        
        if time_to_expiry <= 0:
            return 0.0
        
        d1 = (math.log(spot / strike) + (0.05 + 0.5 * iv**2) * time_to_expiry) / (iv * math.sqrt(time_to_expiry))
        
        try:
            pdf_d1 = math.exp(-0.5 * d1**2) / math.sqrt(2 * math.pi)
            vega = spot * pdf_d1 * math.sqrt(time_to_expiry) / 100  # Per 1% change
            return vega
        except (OverflowError, ValueError):
            return spot * 0.01 * math.sqrt(time_to_expiry)

class MockBrokerAPI:
    """Mock broker API for testing without real market data"""
    
    def __init__(self, failure_rate: float = 0.0):
        self.data_generator = MockDataGenerator()
        self.failure_rate = failure_rate  # For chaos testing
        self.call_count = 0
        self.last_quotes = {}
    
    def quote(self, instruments: List[str]) -> Dict[str, Dict[str, Any]]:
        """Mock quote API call"""
        self.call_count += 1
        
        # Chaos testing: random failures
        if random.random() < self.failure_rate:
            raise Exception(f"Mock API failure (chaos test)")
        
        quotes = {}
        for instrument in instruments:
            # Parse instrument token to generate appropriate quote
            # This is simplified - real implementation would use instrument mapping
            quotes[instrument] = {
                "last_price": round(random.uniform(50, 500), 2),
                "bid": round(random.uniform(45, 495), 2),
                "ask": round(random.uniform(55, 505), 2),
                "volume": random.randint(0, 10000),
                "oi": random.randint(0, 50000),
                "ohlc": {
                    "open": round(random.uniform(45, 505), 2),
                    "high": round(random.uniform(50, 510), 2),
                    "low": round(random.uniform(40, 495), 2),
                    "close": round(random.uniform(45, 505), 2)
                }
            }
        
        self.last_quotes = quotes
        return quotes
    
    def instruments(self, exchange: str = "NFO") -> List[Dict[str, Any]]:
        """Mock instruments API call"""
        # Return simplified instrument list
        instruments = []
        for index in ["NIFTY", "BANKNIFTY", "SENSEX"]:
            for expiry in ["2025-08-29", "2025-09-05", "2025-09-26", "2025-10-31"]:
                for strike in range(15000, 35000, 50):  # Sample strikes
                    for side in ["CE", "PE"]:
                        instruments.append({
                            "instrument_token": f"{index}_{expiry}_{strike}_{side}",
                            "exchange_token": random.randint(1000, 9999),
                            "tradingsymbol": f"{index}{expiry.replace('-', '')}{strike}{side}",
                            "name": index,
                            "last_price": 0,
                            "expiry": expiry,
                            "strike": strike,
                            "tick_size": 0.05,
                            "lot_size": 25 if index == "NIFTY" else 15,
                            "instrument_type": side,
                            "segment": "NFO-OPT",
                            "exchange": "NFO"
                        })
        return instruments

class MockRedisCoordinator:
    """Mock Redis coordinator for testing without Redis dependency"""
    
    def __init__(self):
        self.data = {}
        self.locks = set()
        self.cursors = {}
    
    def ping(self) -> bool:
        return True
    
    def distributed_lock(self, lock_name: str, timeout: int = 30, retry_delay: float = 0.1):
        """Mock distributed lock"""
        return MockContextManager(lambda: None)
    
    def set_file_cursor(self, file_path: str, position: int, checksum: str = "") -> bool:
        self.cursors[file_path] = {"position": position, "checksum": checksum, "last_updated": time.time()}
        return True
    
    def get_file_cursor(self, file_path: str):
        cursor_data = self.cursors.get(file_path)
        if cursor_data:
            from shared.utils.coordination import CursorPosition
            return CursorPosition(
                file_path=file_path,
                position=cursor_data["position"],
                last_updated=cursor_data["last_updated"],
                checksum=cursor_data["checksum"]
            )
        return None
    
    def cache_set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        self.data[key] = {"value": value, "expires": time.time() + ttl}
        return True
    
    def cache_get(self, key: str):
        entry = self.data.get(key)
        if entry and entry["expires"] > time.time():
            return entry["value"]
        return None

class MockContextManager:
    """Simple mock context manager"""
    def __init__(self, cleanup_func: Callable = None):
        self.cleanup_func = cleanup_func
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.cleanup_func:
            self.cleanup_func()

# Base test classes

class BaseTestCase(unittest.TestCase):
    """Base test case with common setup"""
    
    def setUp(self):
        """Set up test environment"""
        self.test_config = TestConfig()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="op_test_"))
        
        # Set up mock environment
        self.mock_settings = self._create_mock_settings()
        self.data_generator = MockDataGenerator()
        self.mock_broker = MockBrokerAPI()
        
        if self.test_config.mock_redis:
            self.mock_redis = MockRedisCoordinator()
        
        # Create test data directory
        self.test_data_dir = self.temp_dir / "test_data"
        self.test_data_dir.mkdir(parents=True, exist_ok=True)
    
    def tearDown(self):
        """Clean up after tests"""
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass  # Ignore cleanup errors in tests
    
    def _create_mock_settings(self) -> Settings:
        """Create mock settings for testing"""
        # Set environment variables for testing
        test_env = {
            "ENV": "test",
            "TEST_MODE": "1",
            "CSV_DATA_ROOT": str(self.temp_dir / "csv_data"),
            "JSON_SNAPSHOTS_ROOT": str(self.temp_dir / "json_snapshots"),
            "REDIS_HOST": "localhost",
            "REDIS_PORT": "6379",
            "INFLUXDB_URL": "http://localhost:8086",
            "ENABLE_INCREMENTAL": "true",
            "USE_MEMORY_MAPPING": "false",  # Disable for tests
            "MAX_MEMORY_USAGE_MB": "512"
        }
        
        for key, value in test_env.items():
            os.environ[key] = value
        
        from shared.config.settings import reload_settings
        return reload_settings()
    
    def create_test_csv_file(self, file_path: Path, data: List[Dict[str, Any]]) -> Path:
        """Helper to create test CSV files"""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        if data:
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)
        
        return file_path
    
    def assert_csv_file_valid(self, file_path: Path, expected_row_count: int = None):
        """Assert that a CSV file is valid and optionally has expected row count"""
        self.assertTrue(file_path.exists(), f"CSV file does not exist: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        if expected_row_count is not None:
            self.assertEqual(len(rows), expected_row_count, 
                           f"Expected {expected_row_count} rows, got {len(rows)}")
        
        # Validate that we have some basic expected columns
        if rows:
            expected_columns = {"ts", "index", "last_price"}
            actual_columns = set(rows[0].keys())
            self.assertTrue(expected_columns.issubset(actual_columns), 
                          f"Missing expected columns: {expected_columns - actual_columns}")

# Import hypothesis for property-based testing
import math

# Property-based testing strategies
option_leg_strategy = st.builds(
    OptionLegData,
    ts=st.just(get_time_utils().get_csv_timestamp()),
    index=st.sampled_from(["NIFTY", "BANKNIFTY", "SENSEX"]),
    bucket=st.sampled_from(["this_week", "next_week", "this_month", "next_month"]),
    expiry=st.dates(min_value=date.today(), max_value=date.today() + timedelta(days=90)).map(lambda d: d.isoformat()),
    side=st.sampled_from(["CALL", "PUT"]),
    atm_strike=st.floats(min_value=10000, max_value=50000).map(lambda x: round(x, 0)),
    strike=st.floats(min_value=10000, max_value=50000).map(lambda x: round(x, 0)),
    strike_offset=st.integers(min_value=-5, max_value=5),
    last_price=st.floats(min_value=0.05, max_value=1000).map(lambda x: round(x, 2)),
    bid=st.one_of(st.none(), st.floats(min_value=0.05, max_value=999).map(lambda x: round(x, 2))),
    ask=st.one_of(st.none(), st.floats(min_value=0.05, max_value=1001).map(lambda x: round(x, 2))),
    volume=st.one_of(st.none(), st.integers(min_value=0, max_value=1000000)),
    oi=st.one_of(st.none(), st.integers(min_value=0, max_value=10000000)),
    iv=st.one_of(st.none(), st.floats(min_value=0.01, max_value=3.0).map(lambda x: round(x, 4))),
    delta=st.one_of(st.none(), st.floats(min_value=-1.0, max_value=1.0).map(lambda x: round(x, 4))),
    gamma=st.one_of(st.none(), st.floats(min_value=0, max_value=0.1).map(lambda x: round(x, 6))),
    theta=st.one_of(st.none(), st.floats(min_value=-100, max_value=0).map(lambda x: round(x, 4))),
    vega=st.one_of(st.none(), st.floats(min_value=0, max_value=100).map(lambda x: round(x, 4)))
)

# Global test instances
mock_data_generator = MockDataGenerator()
test_config = TestConfig()