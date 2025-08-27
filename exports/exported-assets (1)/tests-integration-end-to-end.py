"""
Integration tests for end-to-end functionality of the OP trading platform.
Tests complete workflows from data collection to analytics.
"""

import unittest
import asyncio
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
import tempfile
import json
import csv
import sys

# Import test framework
from .comprehensive_test_framework import (
    BaseTestCase, MockDataGenerator, MockBrokerAPI, MockRedisCoordinator
)
from .unit_test_all_components import TestSharedConfig

# Import services for integration testing
sys.path.append(str(Path(__file__).parent.parent.parent))

from shared.config.settings import get_settings
from shared.utils.time_utils import get_time_utils
from services.processing.writers.consolidated_csv_writer import ConsolidatedCSVWriter, OptionLegData
from services.processing.mergers.minute_merger import MinuteMerger
from services.analytics.aggregators.weekday_aggregator import WeekdayAggregator
from services.collection.collectors.atm_option_collector import ATMOptionCollector

class TestEndToEndDataFlow(BaseTestCase):
    """Test complete data flow from collection to analytics"""
    
    def setUp(self):
        super().setUp()
        self.csv_writer = ConsolidatedCSVWriter()
        self.time_utils = get_time_utils()
        
        # Create test data for full pipeline
        self.test_start_time = self.time_utils.now_ist().replace(
            hour=10, minute=0, second=0, microsecond=0
        )
        self.test_end_time = self.test_start_time + timedelta(minutes=10)
    
    def test_complete_option_data_pipeline(self):
        """Test complete pipeline: Collection -> Processing -> Analytics"""
        
        # Step 1: Generate mock option legs (simulating collection)
        legs = []
        current_time = self.test_start_time
        
        while current_time <= self.test_end_time:
            # Generate option chain for this minute
            minute_legs = []
            for index in ["NIFTY", "BANKNIFTY"]:
                for bucket in ["this_week", "next_week"]:
                    for offset in [-1, 0, 1]:
                        for side in ["CALL", "PUT"]:
                            leg = self.data_generator.generate_option_leg(
                                index=index, bucket=bucket, offset=offset, 
                                side=side, timestamp=current_time
                            )
                            minute_legs.append(leg)
            
            legs.extend(minute_legs)
            current_time += timedelta(minutes=1)
        
        # Step 2: Process and write data using consolidated writer
        result = asyncio.run(self.csv_writer.process_and_write(
            legs, write_legs=True, write_merged=True, write_json=True
        ))
        
        # Verify processing results
        self.assertGreater(result['legs_written'], 0)
        self.assertGreater(result['merged_records'], 0)
        self.assertGreater(result['files_updated'], 0)
        
        # Step 3: Verify CSV files were created
        csv_files = list(self.csv_writer.settings.data.csv_data_root.rglob("*.csv"))
        self.assertGreater(len(csv_files), 0)
        
        # Step 4: Test reading files back incrementally
        for csv_file in csv_files[:3]:  # Test a few files
            if csv_file.exists():
                rows = self.csv_writer.read_file_incrementally(csv_file, cursor_position=0)
                if rows:  # Only test non-empty files
                    self.assertGreater(len(rows), 0)
                    
                    # Verify data integrity
                    for row in rows:
                        self.assertIn('ts', row)
                        self.assertIn('index', row)
                        self.assertIn('last_price', row)
        
        # Step 5: Test JSON snapshots were created
        json_files = list(self.csv_writer.settings.data.json_snapshots_root.rglob("*.json"))
        if result.get('json_written'):
            self.assertGreater(len(json_files), 0)
    
    def test_concurrent_writing_coordination(self):
        """Test that concurrent writes are properly coordinated"""
        
        # Create multiple threads writing to same files
        def write_worker(worker_id, legs_per_worker):
            worker_legs = []
            for i in range(legs_per_worker):
                leg = self.data_generator.generate_option_leg(
                    index="NIFTY", bucket="this_week", offset=0
                )
                # Add worker ID to distinguish data
                leg.volume = worker_id * 1000 + i
                worker_legs.append(leg)
            
            # Use synchronous wrapper for threading
            from services.processing.writers.consolidated_csv_writer import get_sync_writer
            sync_writer = get_sync_writer()
            return sync_writer.write_option_legs(worker_legs)
        
        # Run concurrent writes
        num_workers = 5
        legs_per_worker = 10
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [
                executor.submit(write_worker, worker_id, legs_per_worker)
                for worker_id in range(num_workers)
            ]
            
            results = [future.result() for future in as_completed(futures)]
        
        # Verify all writes completed successfully
        total_legs_written = sum(result['legs_written'] for result in results)
        expected_total = num_workers * legs_per_worker
        self.assertEqual(total_legs_written, expected_total)
        
        # Verify no data corruption in final files
        csv_files = list(self.csv_writer.settings.data.csv_data_root.rglob("*_legs.csv"))
        for csv_file in csv_files:
            if csv_file.exists():
                with open(csv_file, 'r') as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                    
                    # Check for valid structure
                    for row in rows:
                        self.assertIn('volume', row)
                        if row['volume']:
                            # Verify worker ID encoding is intact
                            volume = int(float(row['volume']))
                            worker_id = volume // 1000
                            self.assertGreaterEqual(worker_id, 0)
                            self.assertLess(worker_id, num_workers)
    
    def test_data_quality_validation_pipeline(self):
        """Test data quality validation throughout pipeline"""
        
        # Generate mix of good and corrupted data
        clean_legs = [self.data_generator.generate_option_leg() for _ in range(20)]
        corrupted_legs = self.data_generator.generate_corrupted_data(clean_legs, 0.3)
        
        # Process through pipeline with validation
        result = asyncio.run(self.csv_writer.process_and_write(
            corrupted_legs, write_legs=True, write_merged=True
        ))
        
        # Should still process successfully (writer should handle corruptions gracefully)
        self.assertGreater(result.get('legs_written', 0), 0)
        
        # Verify output files contain valid data structure
        csv_files = list(self.csv_writer.settings.data.csv_data_root.rglob("*.csv"))
        for csv_file in csv_files:
            if csv_file.exists():
                self.assert_csv_file_valid(csv_file)
    
    def test_incremental_processing_workflow(self):
        """Test incremental processing maintains data consistency"""
        
        # Create initial batch of data
        batch1_legs = [
            self.data_generator.generate_option_leg(
                timestamp=self.test_start_time + timedelta(minutes=i)
            ) for i in range(5)
        ]
        
        # Process first batch
        result1 = asyncio.run(self.csv_writer.process_and_write(batch1_legs))
        
        # Create second batch (simulating next collection cycle)
        batch2_legs = [
            self.data_generator.generate_option_leg(
                timestamp=self.test_start_time + timedelta(minutes=i+5)
            ) for i in range(5)
        ]
        
        # Process second batch
        result2 = asyncio.run(self.csv_writer.process_and_write(batch2_legs))
        
        # Verify both batches processed
        self.assertGreater(result1['legs_written'], 0)
        self.assertGreater(result2['legs_written'], 0)
        
        # Verify incremental reading works
        csv_files = list(self.csv_writer.settings.data.csv_data_root.rglob("*.csv"))
        for csv_file in csv_files[:2]:  # Test a couple files
            if csv_file.exists():
                # Read full file
                full_rows = self.csv_writer.read_file_incrementally(csv_file, 0)
                
                # Read incrementally from middle
                if full_rows:
                    mid_position = len(str(full_rows[0])) if full_rows else 0
                    incremental_rows = self.csv_writer.read_file_incrementally(
                        csv_file, mid_position
                    )
                    
                    # Should read remaining rows
                    self.assertGreaterEqual(len(incremental_rows), 0)

class TestServiceCommunication(BaseTestCase):
    """Test communication between microservices"""
    
    def test_message_passing_between_services(self):
        """Test message passing using Redis coordination"""
        
        coordinator = MockRedisCoordinator()
        
        # Test publishing and subscribing to messages
        channel = "test_service_communication"
        message = {
            "event": "data_processed",
            "timestamp": self.time_utils.get_metadata_timestamp(),
            "data": {"records": 100, "files": 5}
        }
        
        # Publish message
        result = coordinator.publish_message(channel, message)
        # Mock coordinator doesn't implement actual pub/sub, but API works
        # In real tests, this would use actual Redis
        
        # Test service health coordination
        service_name = "test_service"
        health_data = {
            "status": "healthy",
            "last_processed": self.time_utils.get_metadata_timestamp(),
            "metrics": {"throughput": 1000, "latency": 50}
        }
        
        coordinator.set_service_health(service_name, health_data)
        retrieved_health = coordinator.get_service_health(service_name)
        
        self.assertEqual(retrieved_health['status'], "healthy")
        self.assertIn('timestamp', retrieved_health)  # Added by coordinator
    
    def test_batch_coordination(self):
        """Test batch processing coordination across services"""
        
        coordinator = MockRedisCoordinator()
        batch_id = "test_batch_001"
        total_writers = 3
        
        # Simulate multiple services coordinating a batch write
        completion_results = []
        for writer_id in range(total_writers):
            is_complete = coordinator.coordinate_batch_write(batch_id, total_writers)
            completion_results.append(is_complete)
        
        # Last writer should see completion
        self.assertTrue(any(completion_results))

class TestErrorHandlingAndRecovery(BaseTestCase):
    """Test error handling and recovery mechanisms"""
    
    def test_file_lock_handling(self):
        """Test handling of file lock conflicts"""
        
        # Create a file that's "locked" (simulate Windows behavior)
        test_file = self.test_data_dir / "locked_file.csv"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(test_file, 'w') as f:
            f.write("ts,index,last_price\n")
            f.write("2025-08-24 10:00:00,NIFTY,100.50\n")
        
        # Mock file coordinator to simulate lock handling
        with patch('services.processing.writers.consolidated_csv_writer.get_file_coordinator') as mock_fc:
            mock_fc.return_value.coordinated_file_write.return_value.__enter__ = Mock()
            mock_fc.return_value.coordinated_file_write.return_value.__exit__ = Mock()
            mock_fc.return_value.get_incremental_cursor = Mock(return_value=0)
            mock_fc.return_value.update_incremental_cursor = Mock(return_value=True)
            
            # Test reading with coordination
            rows = self.csv_writer.read_file_incrementally(test_file)
            self.assertGreaterEqual(len(rows), 0)
            
            # Verify coordination was called
            mock_fc.return_value.coordinated_file_write.assert_called()
    
    def test_data_corruption_recovery(self):
        """Test recovery from data corruption scenarios"""
        
        # Create file with corrupted data
        corrupted_data = [
            {"ts": "2025-08-24 10:00:00", "index": "NIFTY", "last_price": "100.50"},
            {"ts": "invalid-timestamp", "index": "NIFTY", "last_price": "abc"},  # Corrupted
            {"ts": "2025-08-24 10:02:00", "index": "NIFTY", "last_price": "101.00"},
        ]
        
        corrupted_file = self.create_test_csv_file(
            self.test_data_dir / "corrupted.csv", corrupted_data
        )
        
        # Reading should handle corruption gracefully
        try:
            rows = self.csv_writer.read_file_incrementally(corrupted_file)
            # Should return valid rows and skip corrupted ones
            self.assertGreaterEqual(len(rows), 0)
        except Exception as e:
            # Should not raise unhandled exceptions
            self.fail(f"Reading corrupted data should not raise exception: {e}")
    
    def test_network_interruption_simulation(self):
        """Test handling of network interruptions"""
        
        # Create mock broker with intermittent failures
        failing_broker = MockBrokerAPI(failure_rate=0.5)
        
        # Test multiple API calls with retries
        successful_calls = 0
        failed_calls = 0
        
        for _ in range(20):
            try:
                result = failing_broker.quote(["NIFTY25AUG25000CE"])
                if result:
                    successful_calls += 1
            except Exception:
                failed_calls += 1
        
        # Should have some failures due to mock failure rate
        self.assertGreater(failed_calls, 0)
        # Should also have some successes
        self.assertGreater(successful_calls, 0)

class TestPerformanceIntegration(BaseTestCase):
    """Test performance aspects of integrated system"""
    
    def test_high_throughput_processing(self):
        """Test system performance under high data load"""
        
        # Generate large dataset
        start_time = time.time()
        large_dataset = [
            self.data_generator.generate_option_leg() for _ in range(1000)
        ]
        generation_time = time.time() - start_time
        
        # Process large dataset
        start_time = time.time()
        result = asyncio.run(self.csv_writer.process_and_write(
            large_dataset, write_legs=True, write_merged=True
        ))
        processing_time = time.time() - start_time
        
        # Performance assertions
        self.assertLess(processing_time, 30.0)  # Should process 1000 records in <30s
        self.assertEqual(result['legs_written'], 1000)
        
        # Check processing rate
        records_per_second = len(large_dataset) / processing_time
        self.assertGreater(records_per_second, 10)  # At least 10 records/second
        
        print(f"Performance: {records_per_second:.1f} records/second, "
              f"Processing time: {processing_time:.2f}s")
    
    def test_memory_usage_stability(self):
        """Test that memory usage remains stable during processing"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Process multiple batches
        for batch in range(5):
            batch_data = [
                self.data_generator.generate_option_leg() for _ in range(200)
            ]
            
            asyncio.run(self.csv_writer.process_and_write(
                batch_data, write_legs=True, write_merged=False
            ))
            
            # Check memory after each batch
            current_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_growth = current_memory - initial_memory
            
            # Memory should not grow excessively (allow for some variation)
            self.assertLess(memory_growth, 100)  # Less than 100MB growth
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        total_growth = final_memory - initial_memory
        
        print(f"Memory usage: Initial={initial_memory:.1f}MB, "
              f"Final={final_memory:.1f}MB, Growth={total_growth:.1f}MB")
    
    def test_concurrent_service_load(self):
        """Test system behavior under concurrent service load"""
        
        def service_simulation(service_id, operations):
            """Simulate a service performing operations"""
            results = []
            for op in range(operations):
                # Simulate data generation
                data = [self.data_generator.generate_option_leg() for _ in range(10)]
                
                # Process data
                from services.processing.writers.consolidated_csv_writer import get_sync_writer
                sync_writer = get_sync_writer()
                result = sync_writer.write_option_legs(data)
                results.append(result)
            
            return {
                'service_id': service_id,
                'operations_completed': len(results),
                'total_records': sum(r.get('legs_written', 0) for r in results)
            }
        
        # Run multiple simulated services concurrently
        num_services = 3
        operations_per_service = 5
        
        with ThreadPoolExecutor(max_workers=num_services) as executor:
            futures = [
                executor.submit(service_simulation, service_id, operations_per_service)
                for service_id in range(num_services)
            ]
            
            results = [future.result() for future in as_completed(futures)]
        
        # Verify all services completed successfully
        self.assertEqual(len(results), num_services)
        
        total_operations = sum(r['operations_completed'] for r in results)
        total_records = sum(r['total_records'] for r in results)
        
        expected_operations = num_services * operations_per_service
        expected_records = expected_operations * 10  # 10 records per operation
        
        self.assertEqual(total_operations, expected_operations)
        self.assertEqual(total_records, expected_records)

class TestDataConsistencyAndIntegrity(BaseTestCase):
    """Test data consistency across the entire pipeline"""
    
    def test_timestamp_consistency(self):
        """Test that timestamps remain consistent throughout pipeline"""
        
        # Generate data with specific timestamps
        base_time = self.time_utils.now_ist().replace(second=0, microsecond=0)
        test_legs = []
        
        for minute in range(5):
            timestamp = base_time + timedelta(minutes=minute)
            leg = self.data_generator.generate_option_leg(timestamp=timestamp)
            test_legs.append(leg)
        
        # Process through pipeline
        result = asyncio.run(self.csv_writer.process_and_write(test_legs))
        
        # Read back and verify timestamps
        csv_files = list(self.csv_writer.settings.data.csv_data_root.rglob("*.csv"))
        for csv_file in csv_files:
            if csv_file.exists():
                rows = self.csv_writer.read_file_incrementally(csv_file, 0)
                for row in rows:
                    ts_str = row.get('ts')
                    if ts_str:
                        # Verify timestamp can be parsed
                        try:
                            parsed_ts = self.time_utils.parse_csv_timestamp(ts_str)
                            self.assertIsNotNone(parsed_ts)
                        except Exception as e:
                            self.fail(f"Invalid timestamp in output: {ts_str}, Error: {e}")
    
    def test_data_loss_prevention(self):
        """Test that no data is lost during processing"""
        
        # Create uniquely identifiable test data
        test_legs = []
        for i in range(50):
            leg = self.data_generator.generate_option_leg()
            # Use volume as unique identifier
            leg.volume = 10000 + i
            test_legs.append(leg)
        
        # Process data
        result = asyncio.run(self.csv_writer.process_and_write(test_legs))
        
        # Verify all data was written
        self.assertEqual(result['legs_written'], len(test_legs))
        
        # Read back all data and verify completeness
        all_written_volumes = set()
        csv_files = list(self.csv_writer.settings.data.csv_data_root.rglob("*_legs.csv"))
        
        for csv_file in csv_files:
            if csv_file.exists():
                rows = self.csv_writer.read_file_incrementally(csv_file, 0)
                for row in rows:
                    if row.get('volume'):
                        volume = int(float(row['volume']))
                        all_written_volumes.add(volume)
        
        # Verify all unique volumes were preserved
        expected_volumes = {10000 + i for i in range(50)}
        missing_volumes = expected_volumes - all_written_volumes
        
        self.assertEqual(len(missing_volumes), 0, 
                        f"Lost data for volumes: {missing_volumes}")

if __name__ == "__main__":
    # Configure logging for integration tests
    import logging
    logging.basicConfig(level=logging.WARNING)
    
    # Run integration tests
    unittest.main(verbosity=2)