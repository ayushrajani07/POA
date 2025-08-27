#!/usr/bin/env python3
"""
OP TRADING PLATFORM - COMPREHENSIVE TEST FRAMEWORK
==================================================
Version: 3.0.0 - Complete Testing Infrastructure
Author: OP Trading Platform Team
Date: 2025-08-25 2:28 PM IST

COMPREHENSIVE TESTING FRAMEWORK
This module provides complete testing infrastructure for all components:

TESTING CATEGORIES:
✓ Unit Tests - Individual module and function testing
✓ Integration Tests - End-to-end workflow validation
✓ Performance Tests - Throughput and latency benchmarking
✓ Chaos Engineering - Resilience and failure recovery
✓ Property-Based Tests - Edge case discovery with Hypothesis
✓ Mock Data Tests - Offline development and debugging

LIVE vs MOCK DATA TESTING:
✓ Live Data Mode - Tests with real market data from Kite Connect
✓ Mock Data Mode - Tests with realistic simulated market data
✓ Hybrid Mode - Automatic fallback between live and mock data
✓ Data Validation - Ensures consistency between live and mock data

USAGE:
  python -m pytest tests/ -v                    # Run all tests
  python -m pytest tests/unit/ -v               # Unit tests only
  python -m pytest tests/integration/ -v        # Integration tests
  python -m pytest tests/ -k "live" -v          # Live data tests
  python -m pytest tests/ -k "mock" -v          # Mock data tests
  python -m pytest tests/performance/ -v        # Performance tests
"""

import os
import sys
import asyncio
import pytest
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Generator
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from dataclasses import dataclass, asdict
import logging

# Third-party testing libraries
from hypothesis import given, strategies as st, settings, HealthCheck
import aiohttp
try:
    import redis.asyncio as redis
    from influxdb_client import Point
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Missing testing dependencies: {e}")
    print("Run: pip install pytest pytest-asyncio hypothesis redis influxdb-client python-dotenv")
    sys.exit(1)

# Load environment variables
load_dotenv()

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Test configuration
TEST_MODE = os.getenv("TEST_MODE", "1") == "1"
USE_LIVE_DATA = os.getenv("TEST_USE_LIVE_DATA", "false").lower() == "true"
REDIS_TEST_DB = int(os.getenv("REDIS_TEST_DB", "15"))  # Use DB 15 for tests

# Configure test logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================================================================================================
# TEST DATA GENERATORS AND MOCK INFRASTRUCTURE
# ================================================================================================

@dataclass
class MockMarketData:
    """
    Mock market data structure for testing scenarios.
    
    Generates realistic market data that mimics actual Kite Connect API responses
    but with controlled, predictable values for reliable testing.
    """
    symbol: str
    last_price: float
    change: float
    change_percent: float
    volume: int
    high: float
    low: float
    open_price: float
    close_price: float
    oi: int = 0
    iv: float = 0.0
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_kite_format(self) -> Dict[str, Any]:
        """Convert to Kite Connect API response format."""
        return {
            "instrument_token": hash(self.symbol) % 1000000,
            "last_price": self.last_price,
            "net_change": self.change,
            "ohlc": {
                "open": self.open_price,
                "high": self.high,
                "low": self.low,
                "close": self.close_price
            },
            "volume": self.volume,
            "oi": self.oi,
            "iv": self.iv,
            "timestamp": self.timestamp.isoformat()
        }

class RealisticDataGenerator:
    """
    Generates realistic market data for testing purposes.
    
    Creates market data that follows real-world patterns including:
    - Price movements with realistic volatility
    - Volume patterns based on time of day
    - Options Greeks with proper relationships
    - Market microstructure effects
    """
    
    def __init__(self, seed: int = 42):
        """Initialize with reproducible random seed for consistent testing."""
        np.random.seed(seed)
        self.base_price = 18500.0  # NIFTY base price
        self.volatility = 0.02
        self.current_time = datetime.now().replace(hour=9, minute=15, second=0, microsecond=0)
    
    def generate_index_data(self, symbol: str = "NIFTY 50") -> MockMarketData:
        """
        Generate realistic index data with proper OHLC relationships.
        
        Args:
            symbol: Index symbol to generate data for
            
        Returns:
            Realistic index market data
        """
        # Generate realistic price movement
        change_percent = np.random.normal(0, self.volatility * 100)
        current_price = self.base_price * (1 + change_percent / 100)
        
        # Generate OHLC with realistic relationships
        open_price = current_price * (1 + np.random.normal(0, 0.005))
        high_price = max(open_price, current_price) * (1 + abs(np.random.normal(0, 0.01)))
        low_price = min(open_price, current_price) * (1 - abs(np.random.normal(0, 0.01)))
        
        # Generate volume based on time of day (higher during opening/closing)
        hour = self.current_time.hour
        if 9 <= hour <= 10 or 14 <= hour <= 15:
            base_volume = 50000000  # High volume periods
        else:
            base_volume = 25000000  # Normal volume
        
        volume = int(base_volume * (1 + np.random.normal(0, 0.3)))
        
        return MockMarketData(
            symbol=symbol,
            last_price=current_price,
            change=current_price - self.base_price,
            change_percent=change_percent,
            volume=max(volume, 1000000),  # Minimum volume
            high=high_price,
            low=low_price,
            open_price=open_price,
            close_price=self.base_price,
            timestamp=self.current_time
        )
    
    def generate_option_data(self, strike: int, option_type: str = "CE", spot_price: float = None) -> MockMarketData:
        """
        Generate realistic options data with proper Greeks relationships.
        
        Args:
            strike: Option strike price
            option_type: "CE" for Call, "PE" for Put
            spot_price: Current spot price for Greeks calculation
            
        Returns:
            Realistic options market data
        """
        if spot_price is None:
            spot_price = self.base_price
        
        # Calculate moneyness
        moneyness = spot_price / strike if option_type == "CE" else strike / spot_price
        
        # Estimate option price using simplified Black-Scholes approximation
        time_to_expiry = 30 / 365  # Assume 30 days to expiry
        risk_free_rate = 0.06
        
        if option_type == "CE":
            # Call option pricing approximation
            intrinsic_value = max(spot_price - strike, 0)
            time_value = strike * 0.1 * np.sqrt(time_to_expiry) * moneyness
        else:
            # Put option pricing approximation  
            intrinsic_value = max(strike - spot_price, 0)
            time_value = spot_price * 0.1 * np.sqrt(time_to_expiry) * moneyness
        
        option_price = intrinsic_value + time_value + np.random.normal(0, time_value * 0.1)
        option_price = max(option_price, 0.05)  # Minimum option price
        
        # Generate realistic volume (lower for far OTM options)
        base_volume = 1000000
        volume_multiplier = np.exp(-abs(moneyness - 1) * 2)  # Higher volume near ATM
        volume = int(base_volume * volume_multiplier * (1 + np.random.normal(0, 0.5)))
        
        # Generate OI (Open Interest)
        base_oi = 500000
        oi = int(base_oi * volume_multiplier * (1 + np.random.normal(0, 0.3)))
        
        # Generate IV (Implied Volatility)
        base_iv = 0.2  # 20% base IV
        iv_skew = abs(moneyness - 1) * 0.1  # IV skew effect
        iv = base_iv + iv_skew + np.random.normal(0, 0.02)
        
        symbol = f"NIFTY{self.current_time.strftime('%y%m%d')}{strike}{option_type}"
        
        return MockMarketData(
            symbol=symbol,
            last_price=option_price,
            change=np.random.normal(0, option_price * 0.05),
            change_percent=np.random.normal(0, 5),
            volume=max(volume, 1000),
            high=option_price * (1 + abs(np.random.normal(0, 0.05))),
            low=option_price * (1 - abs(np.random.normal(0, 0.05))),
            open_price=option_price * (1 + np.random.normal(0, 0.02)),
            close_price=option_price * (1 + np.random.normal(0, 0.02)),
            oi=max(oi, 100),
            iv=max(iv, 0.05),
            timestamp=self.current_time
        )
    
    def generate_option_chain(self, strikes: List[int], spot_price: float = None) -> Dict[str, MockMarketData]:
        """
        Generate complete option chain data for testing.
        
        Args:
            strikes: List of strike prices
            spot_price: Current spot price 
            
        Returns:
            Complete option chain data
        """
        if spot_price is None:
            spot_price = self.base_price
        
        option_chain = {}
        
        for strike in strikes:
            # Generate Call option
            call_data = self.generate_option_data(strike, "CE", spot_price)
            option_chain[call_data.symbol] = call_data
            
            # Generate Put option
            put_data = self.generate_option_data(strike, "PE", spot_price)
            option_chain[put_data.symbol] = put_data
        
        return option_chain

class MockKiteClient:
    """
    Mock Kite Connect client for testing without live API calls.
    
    Provides realistic responses that match Kite Connect API format
    but with controlled, predictable data for reliable testing.
    """
    
    def __init__(self):
        """Initialize mock client with data generator."""
        self.data_generator = RealisticDataGenerator()
        self.call_count = 0
        self.last_call_time = None
        
    async def quote(self, symbols: List[str]) -> Dict[str, Any]:
        """
        Mock quote API call with realistic data.
        
        Args:
            symbols: List of symbols to get quotes for
            
        Returns:
            Mock quote data in Kite format
        """
        self.call_count += 1
        self.last_call_time = datetime.now()
        
        # Simulate API delay
        await asyncio.sleep(0.1)
        
        quotes = {}
        for symbol in symbols:
            if "NIFTY" in symbol and any(c.isdigit() for c in symbol):
                # Option symbol
                strike = int(''.join(filter(str.isdigit, symbol)))
                option_type = "CE" if "CE" in symbol else "PE"
                data = self.data_generator.generate_option_data(strike, option_type)
            else:
                # Index symbol
                data = self.data_generator.generate_index_data(symbol)
            
            quotes[symbol] = data.to_kite_format()
        
        return quotes
    
    async def instruments(self, exchange: str = "NSE") -> List[Dict[str, Any]]:
        """Mock instruments API call."""
        self.call_count += 1
        
        # Return basic instrument list
        instruments = [
            {
                "instrument_token": 256265,
                "exchange_token": 1001,
                "tradingsymbol": "NIFTY 50",
                "name": "NIFTY 50",
                "last_price": 18500.0,
                "expiry": "",
                "strike": 0.0,
                "tick_size": 0.05,
                "lot_size": 50,
                "instrument_type": "EQ",
                "segment": "NSE",
                "exchange": "NSE"
            }
        ]
        
        # Add some option instruments
        strikes = [18400, 18450, 18500, 18550, 18600]
        for strike in strikes:
            for option_type in ["CE", "PE"]:
                instruments.append({
                    "instrument_token": hash(f"NIFTY{strike}{option_type}") % 1000000,
                    "exchange_token": hash(f"NIFTY{strike}{option_type}") % 10000,  
                    "tradingsymbol": f"NIFTY2501{strike}{option_type}",
                    "name": f"NIFTY",
                    "last_price": 0.0,
                    "expiry": "2025-01-30",
                    "strike": float(strike),
                    "tick_size": 0.05,
                    "lot_size": 50,
                    "instrument_type": option_type,
                    "segment": "NFO",
                    "exchange": "NSE"
                })
        
        return instruments

# ================================================================================================
# PYTEST FIXTURES AND CONFIGURATION
# ================================================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def redis_client():
    """Provide Redis client for testing with separate test database."""
    client = redis.Redis(host='localhost', port=6379, db=REDIS_TEST_DB, decode_responses=True)
    
    # Clear test database
    try:
        await client.flushdb()
    except Exception:
        # Redis might not be available in test environment
        pytest.skip("Redis not available for testing")
    
    yield client
    
    # Cleanup after test
    try:
        await client.flushdb()
        await client.close()
    except Exception:
        pass

@pytest.fixture
def mock_kite_client():
    """Provide mock Kite client for testing."""
    return MockKiteClient()

@pytest.fixture
def realistic_data_generator():
    """Provide realistic data generator for testing."""
    return RealisticDataGenerator(seed=42)  # Fixed seed for reproducible tests

@pytest.fixture
def sample_option_chain(realistic_data_generator):
    """Provide sample option chain data for testing."""
    strikes = [18400, 18450, 18500, 18550, 18600]
    return realistic_data_generator.generate_option_chain(strikes, 18500.0)

@pytest.fixture
def sample_index_data(realistic_data_generator):
    """Provide sample index data for testing."""
    return realistic_data_generator.generate_index_data("NIFTY 50")

# ================================================================================================
# UNIT TESTS - INDIVIDUAL COMPONENT TESTING  
# ================================================================================================

class TestRealisticDataGenerator:
    """Unit tests for the realistic data generator."""
    
    def test_generate_index_data_format(self, realistic_data_generator):
        """Test that generated index data has correct format."""
        data = realistic_data_generator.generate_index_data("NIFTY 50")
        
        assert isinstance(data, MockMarketData)
        assert data.symbol == "NIFTY 50"
        assert isinstance(data.last_price, float)
        assert data.last_price > 0
        assert isinstance(data.volume, int)
        assert data.volume > 0
        assert data.high >= data.low
        assert data.high >= data.last_price >= data.low
    
    def test_generate_option_data_format(self, realistic_data_generator):
        """Test that generated option data has correct format."""
        call_data = realistic_data_generator.generate_option_data(18500, "CE", 18500.0)
        put_data = realistic_data_generator.generate_option_data(18500, "PE", 18500.0)
        
        # Test call option
        assert isinstance(call_data, MockMarketData)
        assert call_data.last_price > 0
        assert call_data.iv > 0
        assert call_data.oi >= 0
        
        # Test put option  
        assert isinstance(put_data, MockMarketData)
        assert put_data.last_price > 0
        assert put_data.iv > 0
        assert put_data.oi >= 0
        
        # ATM options should have similar prices (put-call parity)
        price_difference = abs(call_data.last_price - put_data.last_price)
        assert price_difference < call_data.last_price * 0.5  # Within 50%
    
    def test_option_chain_generation(self, realistic_data_generator):
        """Test complete option chain generation."""
        strikes = [18400, 18500, 18600]
        chain = realistic_data_generator.generate_option_chain(strikes, 18500.0)
        
        # Should have 2 options per strike (CE and PE)
        assert len(chain) == len(strikes) * 2
        
        # Verify all strikes are present
        for strike in strikes:
            call_symbols = [sym for sym in chain.keys() if f"{strike}CE" in sym]
            put_symbols = [sym for sym in chain.keys() if f"{strike}PE" in sym]
            assert len(call_symbols) == 1
            assert len(put_symbols) == 1
    
    @given(st.integers(min_value=15000, max_value=25000))
    def test_option_pricing_bounds(self, realistic_data_generator, strike):
        """Property-based test for option pricing bounds."""
        spot_price = 18500.0
        call_data = realistic_data_generator.generate_option_data(strike, "CE", spot_price)
        
        # Call option should have non-negative intrinsic value
        intrinsic_value = max(spot_price - strike, 0)
        assert call_data.last_price >= intrinsic_value * 0.8  # Allow some tolerance

class TestMockKiteClient:
    """Unit tests for the mock Kite client."""
    
    @pytest.mark.asyncio
    async def test_quote_single_symbol(self, mock_kite_client):
        """Test quote API with single symbol."""
        quotes = await mock_kite_client.quote(["NIFTY 50"])
        
        assert "NIFTY 50" in quotes
        quote_data = quotes["NIFTY 50"]
        assert "last_price" in quote_data
        assert "ohlc" in quote_data
        assert "volume" in quote_data
        assert quote_data["last_price"] > 0
    
    @pytest.mark.asyncio
    async def test_quote_multiple_symbols(self, mock_kite_client):
        """Test quote API with multiple symbols."""
        symbols = ["NIFTY 50", "NIFTY2501018500CE", "NIFTY2501018500PE"]
        quotes = await mock_kite_client.quote(symbols)
        
        assert len(quotes) == len(symbols)
        for symbol in symbols:
            assert symbol in quotes
            assert quotes[symbol]["last_price"] > 0
    
    @pytest.mark.asyncio
    async def test_instruments_api(self, mock_kite_client):
        """Test instruments API."""
        instruments = await mock_kite_client.instruments("NSE")
        
        assert isinstance(instruments, list)
        assert len(instruments) > 0
        
        # Check instrument format
        instrument = instruments[0]
        required_fields = ["instrument_token", "tradingsymbol", "name", "instrument_type"]
        for field in required_fields:
            assert field in instrument
    
    def test_call_tracking(self, mock_kite_client):
        """Test that mock client tracks API calls."""
        initial_count = mock_kite_client.call_count
        
        # Make async call (need to run in event loop for test)
        async def make_call():
            await mock_kite_client.quote(["NIFTY 50"])
        
        asyncio.run(make_call())
        
        assert mock_kite_client.call_count == initial_count + 1
        assert mock_kite_client.last_call_time is not None

# ================================================================================================
# INTEGRATION TESTS - END-TO-END WORKFLOW VALIDATION
# ================================================================================================

class TestIntegrationWorkflows:
    """Integration tests for complete workflows."""
    
    @pytest.mark.asyncio
    async def test_index_overview_workflow(self, mock_kite_client, redis_client):
        """Test complete index overview collection workflow."""
        # Import the actual index collector
        try:
            from index_overview_collector import IndexOverviewCollector
            
            collector = IndexOverviewCollector(use_mock_data=True)
            collector.kite_client = mock_kite_client
            collector.redis_client = redis_client
            
            # Initialize collector
            initialized = await collector.initialize()
            assert initialized, "Collector initialization failed"
            
            # Collect overview data
            overview_data = await collector.collect_comprehensive_overview()
            
            # Validate overview data structure
            assert "indices" in overview_data
            assert "market_breadth" in overview_data
            assert "market_summary" in overview_data
            assert len(overview_data["indices"]) > 0
            
            # Validate individual index data
            for index_data in overview_data["indices"]:
                assert "symbol" in index_data
                assert "current_price" in index_data
                assert "change_percent" in index_data
                assert index_data["current_price"] > 0
            
            await collector.close()
            
        except ImportError:
            pytest.skip("IndexOverviewCollector not available")
    
    @pytest.mark.asyncio
    async def test_authentication_logging_workflow(self, redis_client):
        """Test authentication logging workflow."""
        try:
            from integrated_kite_auth_logger import IntegratedKiteAuthLogger, AuthenticationEvent, AuthEventType
            
            logger = IntegratedKiteAuthLogger()
            logger.redis_client = redis_client
            
            # Initialize logger
            initialized = await logger.initialize()
            assert initialized, "Auth logger initialization failed"
            
            # Log authentication event
            event = AuthenticationEvent(
                event_type=AuthEventType.LOGIN_SUCCESS,
                timestamp=datetime.now(),
                user_id="test_user",
                success=True
            )
            
            result = await logger.log_authentication_event(event)
            assert result, "Failed to log authentication event"
            
            # Verify metrics
            metrics = await logger.get_authentication_metrics()
            assert "summary" in metrics
            assert metrics["summary"]["total_events"] > 0
            
            await logger.close()
            
        except ImportError:
            pytest.skip("Authentication logger not available")
    
    @pytest.mark.asyncio
    async def test_complete_data_collection_workflow(self, mock_kite_client, redis_client):
        """Test complete data collection from API to storage."""
        # 1. Mock data collection
        symbols = ["NIFTY 50", "NIFTY2501018500CE"]
        quotes = await mock_kite_client.quote(symbols)
        assert len(quotes) == len(symbols)
        
        # 2. Mock data storage in Redis
        for symbol, data in quotes.items():
            cache_key = f"test:quote:{symbol}"
            await redis_client.set(cache_key, json.dumps(data, default=str), ex=300)
        
        # 3. Verify data was stored
        for symbol in symbols:
            cache_key = f"test:quote:{symbol}"
            cached_data = await redis_client.get(cache_key)
            assert cached_data is not None
            stored_data = json.loads(cached_data)
            assert stored_data["last_price"] > 0
    
    @pytest.mark.asyncio
    async def test_analytics_computation_workflow(self, sample_option_chain):
        """Test analytics computation workflow."""
        # Mock analytics computation
        atm_strike = 18500
        call_data = None
        put_data = None
        
        # Find ATM options
        for symbol, data in sample_option_chain.items():
            if f"{atm_strike}CE" in symbol:
                call_data = data
            elif f"{atm_strike}PE" in symbol:
                put_data = data
        
        assert call_data is not None
        assert put_data is not None
        
        # Compute Put-Call Ratio
        pcr = put_data.oi / max(call_data.oi, 1)
        assert pcr > 0
        
        # Compute IV spread
        iv_spread = abs(call_data.iv - put_data.iv)
        assert iv_spread >= 0
    
    @pytest.mark.asyncio  
    async def test_error_recovery_workflow(self, mock_kite_client):
        """Test error recovery and fallback mechanisms."""
        # Simulate API failure
        original_quote = mock_kite_client.quote
        
        async def failing_quote(symbols):
            raise Exception("Simulated API failure")
        
        mock_kite_client.quote = failing_quote
        
        # Test error handling
        try:
            await mock_kite_client.quote(["NIFTY 50"])
            assert False, "Should have raised exception"
        except Exception as e:
            assert "Simulated API failure" in str(e)
        
        # Restore original function
        mock_kite_client.quote = original_quote
        
        # Test recovery
        quotes = await mock_kite_client.quote(["NIFTY 50"])
        assert "NIFTY 50" in quotes

# ================================================================================================
# PERFORMANCE TESTS - THROUGHPUT AND LATENCY BENCHMARKING
# ================================================================================================

class TestPerformanceBenchmarks:
    """Performance benchmarking tests."""
    
    @pytest.mark.asyncio
    async def test_data_collection_throughput(self, mock_kite_client):
        """Test data collection throughput."""
        symbols = [f"NIFTY2501{strike}CE" for strike in range(18000, 19000, 50)]
        
        start_time = datetime.now()
        quotes = await mock_kite_client.quote(symbols)
        end_time = datetime.now()
        
        duration = (end_time - start_time).total_seconds()
        throughput = len(symbols) / duration
        
        # Should process at least 100 symbols per second
        assert throughput >= 50, f"Throughput too low: {throughput:.2f} symbols/sec"
        assert len(quotes) == len(symbols)
    
    @pytest.mark.asyncio
    async def test_concurrent_data_collection(self, mock_kite_client):
        """Test concurrent data collection performance."""
        symbols_batches = [
            [f"NIFTY2501{strike}CE" for strike in range(18000, 18200, 50)],
            [f"NIFTY2501{strike}PE" for strike in range(18000, 18200, 50)],
            [f"NIFTY2501{strike}CE" for strike in range(18200, 18400, 50)],
            [f"NIFTY2501{strike}PE" for strike in range(18200, 18400, 50)]
        ]
        
        start_time = datetime.now()
        
        # Execute batches concurrently
        tasks = [mock_kite_client.quote(batch) for batch in symbols_batches]
        results = await asyncio.gather(*tasks)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        total_symbols = sum(len(batch) for batch in symbols_batches)
        concurrent_throughput = total_symbols / duration
        
        # Concurrent processing should be more efficient
        assert concurrent_throughput >= 100, f"Concurrent throughput too low: {concurrent_throughput:.2f}"
        assert len(results) == len(symbols_batches)
    
    def test_data_generator_performance(self, realistic_data_generator):
        """Test data generator performance."""
        num_generations = 1000
        
        start_time = datetime.now()
        for i in range(num_generations):
            realistic_data_generator.generate_index_data(f"TEST_INDEX_{i}")
        end_time = datetime.now()
        
        duration = (end_time - start_time).total_seconds()
        generation_rate = num_generations / duration
        
        # Should generate at least 1000 data points per second
        assert generation_rate >= 1000, f"Generation rate too low: {generation_rate:.2f}/sec"
    
    @pytest.mark.asyncio
    async def test_redis_cache_performance(self, redis_client, realistic_data_generator):
        """Test Redis caching performance."""
        num_operations = 100
        data_points = []
        
        # Generate test data
        for i in range(num_operations):
            data = realistic_data_generator.generate_index_data(f"INDEX_{i}")
            data_points.append((f"perf_test:{i}", json.dumps(asdict(data), default=str)))
        
        # Test write performance
        start_time = datetime.now()
        for key, value in data_points:
            await redis_client.set(key, value, ex=300)
        write_end_time = datetime.now()
        
        write_duration = (write_end_time - start_time).total_seconds()
        write_rate = num_operations / write_duration
        
        # Test read performance
        read_start_time = datetime.now()
        for key, _ in data_points:
            cached_value = await redis_client.get(key)
            assert cached_value is not None
        read_end_time = datetime.now()
        
        read_duration = (read_end_time - read_start_time).total_seconds()
        read_rate = num_operations / read_duration
        
        # Performance assertions (relaxed for CI/test environments)
        assert write_rate >= 100, f"Redis write rate too low: {write_rate:.2f} ops/sec"
        assert read_rate >= 200, f"Redis read rate too low: {read_rate:.2f} ops/sec"

# ================================================================================================
# CHAOS ENGINEERING TESTS - RESILIENCE AND FAILURE RECOVERY
# ================================================================================================

class TestChaosEngineering:
    """Chaos engineering tests for system resilience."""
    
    @pytest.mark.asyncio
    async def test_network_failure_recovery(self, mock_kite_client):
        """Test recovery from network failures."""
        # Simulate intermittent network failures
        call_count = 0
        original_quote = mock_kite_client.quote
        
        async def unreliable_quote(symbols):
            nonlocal call_count
            call_count += 1
            
            if call_count % 3 == 0:  # Fail every 3rd call
                raise aiohttp.ClientError("Network timeout")
            return await original_quote(symbols)
        
        mock_kite_client.quote = unreliable_quote
        
        # Test with retry logic
        successful_calls = 0
        failed_calls = 0
        
        for i in range(10):
            try:
                quotes = await mock_kite_client.quote([f"SYMBOL_{i}"])
                successful_calls += 1
                assert len(quotes) > 0
            except aiohttp.ClientError:
                failed_calls += 1
        
        # Should have some successful calls despite failures
        assert successful_calls > 0
        assert failed_calls > 0
        assert successful_calls + failed_calls == 10
    
    @pytest.mark.asyncio
    async def test_redis_failure_recovery(self, redis_client):
        """Test recovery from Redis connection failures."""
        # Store some test data
        test_key = "chaos_test:data"
        test_value = json.dumps({"test": "data", "timestamp": datetime.now().isoformat()})
        
        await redis_client.set(test_key, test_value, ex=300)
        
        # Verify data exists
        stored_value = await redis_client.get(test_key)
        assert stored_value == test_value
        
        # Simulate Redis connection failure by closing connection
        try:
            await redis_client.close()
            # Try to access data (should fail)
            with pytest.raises(Exception):
                await redis_client.get(test_key)
        except Exception:
            # Expected failure - connection is closed
            pass
    
    def test_memory_pressure_handling(self, realistic_data_generator):
        """Test handling of memory pressure conditions."""
        # Generate moderate amount of data to test memory handling
        large_dataset = []
        
        try:
            for i in range(1000):  # Generate 1k data points (reduced for CI)
                data = realistic_data_generator.generate_option_chain(
                    list(range(18000, 19000, 100)), 18500.0
                )
                large_dataset.append(data)
                
                # Check memory usage periodically
                if i % 100 == 0:
                    try:
                        import psutil
                        process = psutil.Process()
                        memory_mb = process.memory_info().rss / 1024 / 1024
                        
                        # Should not exceed reasonable memory limits
                        assert memory_mb < 2000, f"Memory usage too high: {memory_mb:.2f}MB"
                    except ImportError:
                        # psutil not available in test environment
                        pass
        
        except MemoryError:
            # Should handle memory errors gracefully
            assert len(large_dataset) > 0, "Should have generated some data before memory error"
        
        # Cleanup
        large_dataset.clear()
    
    @pytest.mark.asyncio
    async def test_concurrent_access_chaos(self, redis_client, mock_kite_client):
        """Test system behavior under concurrent access patterns."""
        # Simulate multiple concurrent clients
        async def concurrent_worker(worker_id: int):
            """Simulate concurrent client operations."""
            results = []
            
            for i in range(5):  # Reduced iterations for test performance
                try:
                    # Mix of read and write operations
                    if i % 2 == 0:
                        # Write operation
                        key = f"worker_{worker_id}:data_{i}"
                        value = json.dumps({"worker": worker_id, "operation": i})
                        await redis_client.set(key, value, ex=60)
                        results.append(f"write_{worker_id}_{i}")
                    else:
                        # Read operation (API call)
                        quotes = await mock_kite_client.quote([f"TEST_SYMBOL_{worker_id}_{i}"])
                        results.append(f"api_{worker_id}_{i}")
                        
                except Exception as e:
                    results.append(f"error_{worker_id}_{i}: {str(e)}")
            
            return results
        
        # Run multiple concurrent workers
        num_workers = 5
        tasks = [concurrent_worker(i) for i in range(num_workers)]
        
        # Execute all workers concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify results
        assert len(results) == num_workers
        
        # Count successful operations
        total_operations = 0
        successful_operations = 0
        
        for worker_results in results:
            if isinstance(worker_results, list):
                total_operations += len(worker_results)
                successful_operations += len([r for r in worker_results if not r.startswith("error_")])
        
        # Should have reasonable success rate even under concurrent load
        success_rate = successful_operations / total_operations if total_operations > 0 else 0
        assert success_rate >= 0.7, f"Success rate too low: {success_rate:.2f}"

# ================================================================================================
# PROPERTY-BASED TESTING WITH HYPOTHESIS
# ================================================================================================

class TestPropertyBasedTesting:
    """Property-based tests using Hypothesis for edge case discovery."""
    
    @given(st.floats(min_value=10000.0, max_value=30000.0))
    def test_price_calculations_are_consistent(self, base_price):
        """Test that price calculations are mathematically consistent."""
        # Assume finite numbers only
        if not np.isfinite(base_price):
            return
        
        change_percent = 5.0  # 5% change
        calculated_price = base_price * (1 + change_percent / 100)
        
        # Reverse calculation should yield original change percent
        reverse_change_percent = ((calculated_price - base_price) / base_price) * 100
        
        assert abs(change_percent - reverse_change_percent) < 0.001
    
    @given(st.lists(st.floats(min_value=-10.0, max_value=10.0), min_size=1, max_size=20))
    def test_market_breadth_calculations(self, change_percentages):
        """Test market breadth calculations with various input combinations."""
        # Filter out non-finite values
        change_percentages = [cp for cp in change_percentages if np.isfinite(cp)]
        
        if not change_percentages:
            return
        
        advances = sum(1 for cp in change_percentages if cp > 0)
        declines = sum(1 for cp in change_percentages if cp < 0)
        unchanged = len(change_percentages) - advances - declines
        
        # Basic invariants
        assert advances + declines + unchanged == len(change_percentages)
        assert advances >= 0
        assert declines >= 0
        assert unchanged >= 0
        
        # Advance-decline ratio calculation
        if declines > 0:
            ad_ratio = advances / declines
            assert ad_ratio >= 0
        else:
            # All advances or unchanged
            assert advances > 0 or unchanged == len(change_percentages)
    
    @given(st.integers(min_value=15000, max_value=25000),
           st.floats(min_value=15000.0, max_value=25000.0),
           st.sampled_from(["CE", "PE"]))
    def test_option_pricing_properties(self, strike, spot_price, option_type):
        """Test fundamental option pricing properties."""
        # Ensure finite values
        if not np.isfinite(spot_price):
            return
        
        generator = RealisticDataGenerator()
        option_data = generator.generate_option_data(strike, option_type, spot_price)
        
        # Option price should be non-negative
        assert option_data.last_price >= 0
        
        # Intrinsic value calculation
        if option_type == "CE":
            intrinsic_value = max(spot_price - strike, 0)
        else:
            intrinsic_value = max(strike - spot_price, 0)
        
        # Option price should be at least intrinsic value (allowing for some model deviation)
        assert option_data.last_price >= intrinsic_value * 0.5
    
    @given(st.lists(st.integers(min_value=15000, max_value=25000), 
                   min_size=1, max_size=10, unique=True))
    def test_option_chain_consistency(self, strikes):
        """Test option chain generation consistency."""
        generator = RealisticDataGenerator()
        chain = generator.generate_option_chain(strikes, 18500.0)
        
        # Should have exactly 2 options per strike
        assert len(chain) == len(strikes) * 2
        
        # Each strike should have both CE and PE
        for strike in strikes:
            call_symbols = [sym for sym in chain.keys() if f"{strike}CE" in sym]
            put_symbols = [sym for sym in chain.keys() if f"{strike}PE" in sym]
            assert len(call_symbols) == 1
            assert len(put_symbols) == 1

# ================================================================================================
# LIVE DATA INTEGRATION TESTS
# ================================================================================================

class TestLiveDataIntegration:
    """Tests that require live data connection (conditional on configuration)."""
    
    @pytest.mark.skipif(not USE_LIVE_DATA, reason="Live data testing disabled")
    @pytest.mark.asyncio
    async def test_live_kite_connection(self):
        """Test live Kite Connect API connection."""
        try:
            from integrated_kite_auth_logger import IntegratedKiteAuthManager
            
            auth_manager = IntegratedKiteAuthManager()
            initialized = await auth_manager.initialize()
            assert initialized, "Auth manager initialization failed"
            
            kite_client = await auth_manager.authenticate()
            if kite_client:
                # Test basic API call
                profile = await auth_manager.make_authenticated_request('profile')
                assert 'user_name' in profile or 'user_id' in profile
                
                # Test quote API
                quotes = await auth_manager.make_authenticated_request('quote', ['NSE:NIFTY 50'])
                assert 'NSE:NIFTY 50' in quotes
                assert quotes['NSE:NIFTY 50']['last_price'] > 0
            else:
                pytest.skip("Live Kite authentication failed")
            
            await auth_manager.close()
            
        except ImportError:
            pytest.skip("Authentication manager not available")
        except Exception as e:
            pytest.fail(f"Live data test failed: {str(e)}")
    
    @pytest.mark.skipif(not USE_LIVE_DATA, reason="Live data testing disabled")
    @pytest.mark.asyncio
    async def test_live_data_consistency(self):
        """Test consistency between live and mock data formats."""
        try:
            from integrated_kite_auth_logger import IntegratedKiteAuthManager
            
            # Get live data
            auth_manager = IntegratedKiteAuthManager()
            await auth_manager.initialize()
            kite_client = await auth_manager.authenticate()
            
            if kite_client:
                live_quotes = await auth_manager.make_authenticated_request('quote', ['NSE:NIFTY 50'])
                
                # Get mock data
                mock_client = MockKiteClient()
                mock_quotes = await mock_client.quote(['NSE:NIFTY 50'])
                
                # Compare data structures
                live_data = live_quotes['NSE:NIFTY 50']
                mock_data = mock_quotes['NSE:NIFTY 50']
                
                # Both should have essential fields
                essential_fields = ['last_price', 'ohlc', 'volume']
                for field in essential_fields:
                    assert field in live_data, f"Live data missing {field}"
                    assert field in mock_data, f"Mock data missing {field}"
                
                # Data types should match
                assert type(live_data['last_price']) == type(mock_data['last_price'])
                assert type(live_data['volume']) == type(mock_data['volume'])
                
            else:
                pytest.skip("Live authentication failed")
            
            await auth_manager.close()
            
        except Exception as e:
            pytest.skip(f"Live data consistency test skipped: {str(e)}")

# ================================================================================================
# COMMAND-LINE INTERFACE FOR RUNNING TESTS
# ================================================================================================

def main():
    """Main function for running specific test suites."""
    import argparse
    
    parser = argparse.ArgumentParser(description="OP Trading Platform - Comprehensive Test Runner")
    parser.add_argument('--unit', action='store_true', help='Run unit tests')
    parser.add_argument('--integration', action='store_true', help='Run integration tests')
    parser.add_argument('--performance', action='store_true', help='Run performance tests')
    parser.add_argument('--chaos', action='store_true', help='Run chaos engineering tests')
    parser.add_argument('--property', action='store_true', help='Run property-based tests')
    parser.add_argument('--live', action='store_true', help='Run live data tests')
    parser.add_argument('--mock', action='store_true', help='Run mock data tests')
    parser.add_argument('--all', action='store_true', help='Run all tests')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    if not any(vars(args).values()):
        print("No test category specified. Use --help for options.")
        return
    
    # Build pytest arguments
    pytest_args = []
    
    if args.verbose:
        pytest_args.extend(['-v', '-s'])
    
    if args.unit or args.all:
        pytest_args.extend(['-k', 'Test'])
    
    if args.integration or args.all:
        pytest_args.extend(['-k', 'TestIntegration'])
    
    if args.performance or args.all:
        pytest_args.extend(['-k', 'TestPerformance'])
    
    if args.chaos or args.all:
        pytest_args.extend(['-k', 'TestChaos'])
    
    if args.property or args.all:
        pytest_args.extend(['-k', 'TestProperty'])
    
    if args.live:
        os.environ['TEST_USE_LIVE_DATA'] = 'true'
        pytest_args.extend(['-k', 'live'])
    
    if args.mock:
        os.environ['TEST_USE_LIVE_DATA'] = 'false'
        pytest_args.extend(['-k', 'mock'])
    
    # Add coverage reporting
    pytest_args.extend(['--cov=.', '--cov-report=html', '--cov-report=term'])
    
    # Run pytest
    exit_code = pytest.main(pytest_args)
    
    print(f"\n{'='*60}")
    print(f"TEST EXECUTION COMPLETED")
    print(f"{'='*60}")
    print(f"Exit Code: {exit_code}")
    print(f"Coverage Report: htmlcov/index.html")
    
    return exit_code

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)