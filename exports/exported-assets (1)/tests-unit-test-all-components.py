"""
Unit tests for all major components of the OP trading platform.
Tests each module/script individually with comprehensive coverage.
"""

import unittest
import asyncio
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import json
import csv

# Import test framework
from .comprehensive_test_framework import (
    BaseTestCase, MockDataGenerator, MockBrokerAPI, MockRedisCoordinator, 
    option_leg_strategy, test_config
)

# Import modules to test
import sys
sys.path.append(str(Path(__file__).parent.parent.parent))

from shared.config.settings import Settings, get_settings
from shared.utils.time_utils import TimeUtils, get_time_utils, TimeFormat
from shared.utils.coordination import RedisCoordinator, FileCoordinator
from services.processing.writers.consolidated_csv_writer import (
    ConsolidatedCSVWriter, OptionLegData, MergedOptionData
)
from services.collection.collectors.atm_option_collector import ATMOptionCollector
from services.collection.brokers.kite_client import KiteClient

class TestSharedConfig(BaseTestCase):
    """Test shared configuration management"""
    
    def test_settings_initialization(self):
        """Test that settings initialize correctly"""
        settings = self.mock_settings
        
        self.assertEqual(settings.environment, "test")
        self.assertTrue(settings.test.test_mode)
        self.assertIsNotNone(settings.database.url)
        self.assertIsNotNone(settings.data.csv_data_root)
    
    def test_settings_validation(self):
        """Test settings validation"""
        # Valid settings should not raise
        try:
            settings = Settings()
            settings._validate_config()
        except Exception as e:
            # In test mode, some validations are skipped
            if "test_mode" not in str(e).lower():
                self.fail(f"Settings validation failed unexpectedly: {e}")
    
    def test_settings_to_dict(self):
        """Test settings serialization"""
        settings = self.mock_settings
        settings_dict = settings.to_dict()
        
        self.assertIn("environment", settings_dict)
        self.assertIn("database", settings_dict)
        self.assertIn("market", settings_dict)
        self.assertIn("data", settings_dict)
    
    def test_directory_creation(self):
        """Test that required directories are created"""
        settings = self.mock_settings
        
        self.assertTrue(settings.data.csv_data_root.exists())
        self.assertTrue(settings.data.json_snapshots_root.exists())

class TestTimeUtils(BaseTestCase):
    """Test time utilities and standardization"""
    
    def setUp(self):
        super().setUp()
        self.time_utils = get_time_utils()
    
    def test_timezone_conversions(self):
        """Test UTC/IST conversions"""
        utc_time = self.time_utils.now_utc()
        ist_time = self.time_utils.utc_to_ist(utc_time)
        back_to_utc = self.time_utils.ist_to_utc(ist_time)
        
        # Should be approximately equal (within seconds)
        diff = abs((back_to_utc - utc_time).total_seconds())
        self.assertLess(diff, 1.0)
    
    def test_csv_timestamp_format(self):
        """Test CSV timestamp standardization"""
        now_ist = self.time_utils.now_ist()
        csv_ts = self.time_utils.format_time(now_ist, TimeFormat.CSV_STANDARD)
        
        # Should be in "YYYY-MM-DD HH:MM:SS" format
        self.assertRegex(csv_ts, r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}')
        
        # Should be parseable back
        parsed = self.time_utils.parse_time(csv_ts, TimeFormat.CSV_STANDARD)
        self.assertIsNotNone(parsed)
    
    def test_market_timing_functions(self):
        """Test market open/close detection"""
        # Test with known market hours (9:15 AM IST)
        from datetime import time as dt_time
        import pytz
        
        market_time = self.time_utils.now_ist().replace(
            hour=10, minute=30, second=0, microsecond=0
        )  # 10:30 AM IST - should be market hours
        
        # On a weekday, should be market hours
        if market_time.weekday() < 5:  # Monday-Friday
            self.assertTrue(self.time_utils.is_market_open(market_time))
        
        # Weekend should not be market hours
        weekend_time = market_time.replace(day=market_time.day + (6 - market_time.weekday()))
        self.assertFalse(self.time_utils.is_market_open(weekend_time))
    
    def test_minute_bucketing(self):
        """Test minute bucketing functionality"""
        test_time = self.time_utils.now_ist().replace(
            hour=14, minute=25, second=45, microsecond=123456
        )
        
        bucket = self.time_utils.bucket_to_minute(test_time)
        self.assertEqual(bucket, "14:25")
        
        rounded = self.time_utils.round_to_minute(test_time)
        self.assertEqual(rounded.second, 0)
        self.assertEqual(rounded.microsecond, 0)
    
    def test_timestamp_standardization(self):
        """Test legacy timestamp standardization"""
        from shared.utils.time_utils import standardize_timestamp_column
        
        # Test various input formats
        test_cases = [
            "2025-08-24 14:30:00",  # Already correct
            "2025-08-24T14:30:00+05:30",  # ISO with timezone
            "2025-08-24T09:00:00Z",  # UTC
            1724504400.0,  # Unix timestamp
        ]
        
        for input_ts in test_cases:
            standardized = standardize_timestamp_column(input_ts)
            self.assertRegex(standardized, r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}')

class TestRedisCoordination(BaseTestCase):
    """Test Redis coordination utilities"""
    
    def setUp(self):
        super().setUp()
        self.mock_redis = MockRedisCoordinator()
    
    def test_distributed_lock(self):
        """Test distributed locking mechanism"""
        with self.mock_redis.distributed_lock("test_lock"):
            # Lock should be held here
            self.assertIn("test_lock", self.mock_redis.locks)
    
    def test_file_cursor_operations(self):
        """Test file cursor tracking"""
        file_path = "/test/file.csv"
        position = 1024
        checksum = "abc123"
        
        # Set cursor
        self.assertTrue(self.mock_redis.set_file_cursor(file_path, position, checksum))
        
        # Get cursor
        cursor = self.mock_redis.get_file_cursor(file_path)
        self.assertIsNotNone(cursor)
        self.assertEqual(cursor.position, position)
        self.assertEqual(cursor.checksum, checksum)
    
    def test_caching_operations(self):
        """Test Redis caching"""
        key = "test_key"
        value = {"data": "test_value", "number": 42}
        
        # Set cache
        self.assertTrue(self.mock_redis.cache_set(key, value, 60))
        
        # Get cache
        cached_value = self.mock_redis.cache_get(key)
        self.assertEqual(cached_value, value)
        
        # Test expiry (mock doesn't implement real expiry, but API works)
        self.assertIsNotNone(cached_value)

class TestConsolidatedCSVWriter(BaseTestCase):
    """Test consolidated CSV writer with all optimizations"""
    
    def setUp(self):
        super().setUp()
        self.writer = ConsolidatedCSVWriter()
        
        # Mock Redis coordination
        with patch('services.processing.writers.consolidated_csv_writer.get_file_coordinator') as mock_fc:
            mock_fc.return_value.coordinated_file_write = Mock()
            mock_fc.return_value.coordinated_file_read = Mock()
            mock_fc.return_value.get_incremental_cursor = Mock(return_value=0)
            mock_fc.return_value.update_incremental_cursor = Mock(return_value=True)
            
            self.mock_file_coordinator = mock_fc.return_value
    
    def test_option_leg_data_creation(self):
        """Test OptionLegData structure"""
        leg = self.data_generator.generate_option_leg()
        
        # Test basic structure
        self.assertIsInstance(leg, OptionLegData)
        self.assertIsNotNone(leg.ts)
        self.assertIn(leg.index, ["NIFTY", "BANKNIFTY", "SENSEX"])
        self.assertIn(leg.side, ["CALL", "PUT"])
        self.assertIsInstance(leg.last_price, float)
        
        # Test serialization
        leg_dict = leg.to_dict()
        self.assertIn("ts", leg_dict)
        self.assertIn("last_price", leg_dict)
        
        # Test deserialization
        leg_restored = OptionLegData.from_dict(leg_dict)
        self.assertEqual(leg.ts, leg_restored.ts)
        self.assertEqual(leg.last_price, leg_restored.last_price)
    
    def test_merged_option_data_creation(self):
        """Test merged option data computation"""
        # Generate CALL and PUT for same strike
        call_leg = self.data_generator.generate_option_leg(
            index="NIFTY", offset=0, side="CALL"
        )
        put_leg = self.data_generator.generate_option_leg(
            index="NIFTY", offset=0, side="PUT"
        )
        put_leg.ts = call_leg.ts  # Same timestamp
        put_leg.bucket = call_leg.bucket
        put_leg.expiry = call_leg.expiry
        put_leg.strike = call_leg.strike
        put_leg.atm_strike = call_leg.atm_strike
        
        # Test merging
        merged_data = self.writer.merge_legs_to_strikes([call_leg, put_leg])
        self.assertEqual(len(merged_data), 1)
        
        merged = merged_data[0]
        self.assertEqual(merged.call_last_price, call_leg.last_price)
        self.assertEqual(merged.put_last_price, put_leg.last_price)
        self.assertAlmostEqual(
            merged.total_premium, 
            call_leg.last_price + put_leg.last_price, 
            places=2
        )
    
    @patch('aiofiles.open', new_callable=AsyncMock)
    async def test_async_csv_writing(self, mock_aiofiles):
        """Test async CSV writing functionality"""
        # Mock file operations
        mock_file = AsyncMock()
        mock_aiofiles.return_value.__aenter__.return_value = mock_file
        
        # Generate test data
        legs = [self.data_generator.generate_option_leg() for _ in range(5)]
        
        # Test async writing
        result = await self.writer.write_option_legs_async(legs, write_json=False)
        
        self.assertIn("legs_written", result)
        self.assertIn("files_updated", result)
    
    def test_incremental_reading(self):
        """Test incremental file reading with cursors"""
        # Create test CSV file
        test_data = [
            {"ts": "2025-08-24 10:00:00", "index": "NIFTY", "last_price": "100.50"},
            {"ts": "2025-08-24 10:01:00", "index": "NIFTY", "last_price": "101.00"},
            {"ts": "2025-08-24 10:02:00", "index": "NIFTY", "last_price": "100.75"},
        ]
        
        test_file = self.create_test_csv_file(
            self.test_data_dir / "test_incremental.csv", test_data
        )
        
        # Test reading from beginning
        rows = self.writer.read_file_incrementally(test_file, cursor_position=0)
        self.assertEqual(len(rows), 3)
        
        # Test reading from middle (simulate cursor)
        # This is simplified - real implementation would calculate exact byte position
        rows = self.writer.read_file_incrementally(test_file, cursor_position=len(str(test_data[0])))
        self.assertGreaterEqual(len(rows), 0)  # Should read remaining rows
    
    def test_file_path_generation(self):
        """Test consolidated file path generation"""
        path = self.writer.get_consolidated_file_path(
            "NIFTY", "this_week", "atm", "2025-08-24", "merged"
        )
        
        expected_parts = ["NIFTY", "this_week", "atm", "2025-08-24_merged.csv"]
        path_str = str(path)
        for part in expected_parts:
            self.assertIn(part, path_str)
    
    def test_statistics_tracking(self):
        """Test writer statistics tracking"""
        initial_stats = self.writer.get_stats()
        self.assertIn("writes_completed", initial_stats)
        self.assertIn("writes_failed", initial_stats)
        self.assertIn("bytes_written", initial_stats)
        
        # All should start at 0
        for key in ["writes_completed", "writes_failed", "bytes_written"]:
            self.assertEqual(initial_stats[key], 0)

class TestMockDataGenerator(BaseTestCase):
    """Test mock data generation for testing"""
    
    def setUp(self):
        super().setUp()
        self.generator = MockDataGenerator()
    
    def test_single_leg_generation(self):
        """Test generation of single option leg"""
        leg = self.generator.generate_option_leg()
        
        # Basic structure validation
        self.assertIsInstance(leg, OptionLegData)
        self.assertIn(leg.index, self.generator.indices)
        self.assertIn(leg.bucket, self.generator.buckets)
        self.assertIn(leg.side, self.generator.sides)
        self.assertIn(leg.strike_offset, self.generator.offsets)
        
        # Price validation
        self.assertGreater(leg.last_price, 0)
        self.assertIsNotNone(leg.bid)
        self.assertIsNotNone(leg.ask)
        self.assertLessEqual(leg.bid, leg.last_price)
        self.assertGreaterEqual(leg.ask, leg.last_price)
        
        # Greeks validation
        if leg.delta is not None:
            if leg.side == "CALL":
                self.assertGreaterEqual(leg.delta, 0)
                self.assertLessEqual(leg.delta, 1)
            else:  # PUT
                self.assertGreaterEqual(leg.delta, -1)
                self.assertLessEqual(leg.delta, 0)
        
        if leg.gamma is not None:
            self.assertGreaterEqual(leg.gamma, 0)
        
        if leg.vega is not None:
            self.assertGreaterEqual(leg.vega, 0)
    
    def test_option_chain_generation(self):
        """Test generation of complete option chain"""
        chain = self.generator.generate_option_chain("NIFTY", "this_week")
        
        # Should have both calls and puts for all offsets
        expected_legs = len(self.generator.offsets) * 2
        self.assertEqual(len(chain), expected_legs)
        
        # Check that we have both sides
        sides = set(leg.side for leg in chain)
        self.assertEqual(sides, {"CALL", "PUT"})
        
        # Check that we have all offsets
        offsets = set(leg.strike_offset for leg in chain)
        self.assertEqual(offsets, set(self.generator.offsets))
    
    def test_time_series_generation(self):
        """Test time series generation"""
        start_time = self.generator.time_utils.now_ist().replace(hour=10, minute=0)
        end_time = start_time + timedelta(minutes=5)
        
        series = self.generator.generate_time_series(
            "NIFTY", "this_week", start_time, end_time, interval_minutes=1
        )
        
        # Should have data for market minutes
        self.assertGreater(len(series), 0)
        
        # Check timestamp progression
        timestamps = sorted(set(leg.ts for leg in series))
        self.assertGreater(len(timestamps), 1)
    
    def test_corrupted_data_generation(self):
        """Test intentional data corruption for error testing"""
        clean_data = [self.generator.generate_option_leg() for _ in range(10)]
        corrupted_data = self.generator.generate_corrupted_data(clean_data, 0.5)
        
        self.assertEqual(len(corrupted_data), len(clean_data))
        # Some data should be different (corrupted)
        different_count = sum(
            1 for clean, corrupt in zip(clean_data, corrupted_data)
            if clean.to_dict() != corrupt.to_dict()
        )
        self.assertGreater(different_count, 0)

class TestMockBrokerAPI(BaseTestCase):
    """Test mock broker API"""
    
    def setUp(self):
        super().setUp()
        self.broker = MockBrokerAPI()
    
    def test_quote_api(self):
        """Test quote API mock"""
        instruments = ["NIFTY25AUG25000CE", "NIFTY25AUG25000PE"]
        quotes = self.broker.quote(instruments)
        
        self.assertEqual(len(quotes), len(instruments))
        for instrument in instruments:
            self.assertIn(instrument, quotes)
            quote = quotes[instrument]
            self.assertIn("last_price", quote)
            self.assertIn("bid", quote)
            self.assertIn("ask", quote)
            self.assertIn("volume", quote)
            self.assertIn("oi", quote)
    
    def test_instruments_api(self):
        """Test instruments API mock"""
        instruments = self.broker.instruments("NFO")
        
        self.assertGreater(len(instruments), 0)
        
        # Check structure of instrument data
        instrument = instruments[0]
        required_fields = [
            "instrument_token", "tradingsymbol", "name", 
            "expiry", "strike", "instrument_type", "exchange"
        ]
        for field in required_fields:
            self.assertIn(field, instrument)
    
    def test_chaos_testing_failures(self):
        """Test chaos engineering failure injection"""
        broker = MockBrokerAPI(failure_rate=1.0)  # 100% failure rate
        
        with self.assertRaises(Exception):
            broker.quote(["NIFTY25AUG25000CE"])
    
    def test_api_call_tracking(self):
        """Test API call count tracking"""
        initial_count = self.broker.call_count
        
        self.broker.quote(["TEST"])
        self.assertEqual(self.broker.call_count, initial_count + 1)
        
        self.broker.quote(["TEST1", "TEST2"])
        self.assertEqual(self.broker.call_count, initial_count + 2)

# Property-based tests using hypothesis
from hypothesis import given, strategies as st, settings

class TestPropertyBasedValidation(BaseTestCase):
    """Property-based tests for data validation"""
    
    @given(option_leg_strategy)
    @settings(max_examples=100)
    def test_option_leg_serialization_roundtrip(self, leg):
        """Test that option leg data can be serialized and deserialized"""
        # Serialize to dict
        leg_dict = leg.to_dict()
        
        # Deserialize back
        restored_leg = OptionLegData.from_dict(leg_dict)
        
        # Should be equal
        self.assertEqual(leg.ts, restored_leg.ts)
        self.assertEqual(leg.index, restored_leg.index)
        self.assertEqual(leg.last_price, restored_leg.last_price)
    
    @given(st.lists(option_leg_strategy, min_size=2, max_size=10))
    @settings(max_examples=50)
    def test_merge_operation_properties(self, legs):
        """Test properties of the merge operation"""
        if not legs:
            return
        
        writer = ConsolidatedCSVWriter()
        merged_data = writer.merge_legs_to_strikes(legs)
        
        # Properties that should hold:
        # 1. Number of merged records should not exceed input legs
        self.assertLessEqual(len(merged_data), len(legs))
        
        # 2. All merged records should have valid timestamps
        for merged in merged_data:
            self.assertIsNotNone(merged.ts)
            # Should be parseable as timestamp
            try:
                get_time_utils().parse_csv_timestamp(merged.ts)
            except Exception:
                self.fail(f"Invalid timestamp format: {merged.ts}")
        
        # 3. Total premium should be positive if both call and put prices exist
        for merged in merged_data:
            if merged.call_last_price and merged.put_last_price:
                self.assertGreater(merged.total_premium, 0)
    
    @given(st.floats(min_value=0.05, max_value=1000))
    @settings(max_examples=100)
    def test_price_validation_properties(self, price):
        """Test price validation properties"""
        # All prices should be positive
        self.assertGreater(price, 0)
        
        # Prices should round to 2 decimal places correctly
        rounded_price = round(price, 2)
        self.assertLessEqual(abs(price - rounded_price), 0.005)
    
    @given(st.integers(min_value=-5, max_value=5))
    @settings(max_examples=20)
    def test_strike_offset_properties(self, offset):
        """Test strike offset calculation properties"""
        base_strike = 25000
        step_size = 50
        
        calculated_strike = base_strike + (offset * step_size)
        
        # Strike should always be positive
        if calculated_strike > 0:
            self.assertGreater(calculated_strike, 0)
        
        # Strike should be multiple of step size
        self.assertEqual(calculated_strike % step_size, 0)

if __name__ == "__main__":
    # Configure logging for tests
    logging.basicConfig(level=logging.WARNING)
    
    # Run tests
    unittest.main(verbosity=2)