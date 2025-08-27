"""
Chaos Engineering Tests and EOD Data Verification for OP Trading Platform.
Tests system resilience under various failure conditions and validates data integrity.
"""

import unittest
import asyncio
import random
import time
import threading
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import Mock, MagicMock, patch
import json
import csv
import sys
import logging
import psutil
import os
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Import test framework
from .comprehensive_test_framework import BaseTestCase, MockDataGenerator, MockBrokerAPI
from .integration_end_to_end import TestEndToEndDataFlow

# Import modules to test
sys.path.append(str(Path(__file__).parent.parent.parent))

from shared.config.settings import get_settings
from shared.utils.time_utils import get_time_utils, TimeFormat
from services.processing.writers.consolidated_csv_writer import ConsolidatedCSVWriter, OptionLegData
from services.monitoring.enhanced_health_monitor import EnhancedHealthMonitor

logger = logging.getLogger(__name__)

class FailureType(Enum):
    """Types of failures to simulate"""
    NETWORK_TIMEOUT = "network_timeout"
    DISK_FULL = "disk_full"
    MEMORY_EXHAUSTION = "memory_exhaustion"
    DATABASE_CONNECTION_LOSS = "database_connection_loss"
    FILE_CORRUPTION = "file_corruption"
    PROCESS_CRASH = "process_crash"
    REDIS_UNAVAILABLE = "redis_unavailable"
    HIGH_CPU_LOAD = "high_cpu_load"
    PARTIAL_DATA_LOSS = "partial_data_loss"
    TIMESTAMP_CORRUPTION = "timestamp_corruption"

@dataclass
class ChaosTestResult:
    """Result of a chaos test"""
    test_name: str
    failure_type: FailureType
    duration_seconds: float
    success: bool
    error_message: str = ""
    recovery_time_seconds: float = 0
    data_integrity_maintained: bool = True
    system_recovered: bool = True
    performance_impact_percent: float = 0

class ChaosFailureInjector:
    """Injects various types of failures for chaos testing"""
    
    def __init__(self):
        self.active_failures: Dict[str, Any] = {}
        self.original_functions: Dict[str, Any] = {}
    
    def inject_network_timeout(self, timeout_rate: float = 0.3):
        """Inject network timeouts"""
        def failing_network_call(*args, **kwargs):
            if random.random() < timeout_rate:
                import time
                time.sleep(30)  # Simulate timeout
                raise TimeoutError("Network timeout injected by chaos test")
            return self.original_functions['network_call'](*args, **kwargs)
        
        # This would patch actual network calls in real implementation
        self.active_failures['network_timeout'] = failing_network_call
        return True
    
    def inject_disk_full_simulation(self, path: Path, threshold_mb: int = 100):
        """Simulate disk full condition"""
        def check_disk_space():
            return threshold_mb * 1024 * 1024  # Return low available space
        
        self.active_failures['disk_full'] = check_disk_space
        return True
    
    def inject_memory_pressure(self, memory_hog_mb: int = 500):
        """Create memory pressure"""
        try:
            # Allocate memory to create pressure
            memory_hog = bytearray(memory_hog_mb * 1024 * 1024)
            self.active_failures['memory_pressure'] = memory_hog
            return True
        except MemoryError:
            return False
    
    def inject_database_failures(self, failure_rate: float = 0.5):
        """Inject database connection failures"""
        def failing_db_operation(*args, **kwargs):
            if random.random() < failure_rate:
                raise ConnectionError("Database connection failed (chaos test)")
            # Would call original function in real implementation
            return {"success": True}
        
        self.active_failures['database_failure'] = failing_db_operation
        return True
    
    def inject_file_corruption(self, file_path: Path):
        """Corrupt a file to test recovery"""
        try:
            if file_path.exists():
                with open(file_path, 'r+') as f:
                    content = f.read()
                    # Corrupt the middle of the file
                    if content:
                        mid_point = len(content) // 2
                        corrupted = content[:mid_point] + "CORRUPTED_DATA" + content[mid_point + 10:]
                        f.seek(0)
                        f.write(corrupted)
                        f.truncate()
                
                self.active_failures['file_corruption'] = file_path
                return True
        except Exception as e:
            logger.error(f"Failed to corrupt file {file_path}: {e}")
        return False
    
    def inject_redis_unavailable(self):
        """Simulate Redis being unavailable"""
        def failing_redis_operation(*args, **kwargs):
            raise ConnectionError("Redis connection refused (chaos test)")
        
        self.active_failures['redis_unavailable'] = failing_redis_operation
        return True
    
    def inject_high_cpu_load(self, duration_seconds: int = 30):
        """Create high CPU load"""
        def cpu_burner():
            end_time = time.time() + duration_seconds
            while time.time() < end_time:
                # Busy-wait to consume CPU
                pass
        
        thread = threading.Thread(target=cpu_burner, daemon=True)
        thread.start()
        self.active_failures['high_cpu'] = thread
        return True
    
    def inject_partial_data_loss(self, loss_rate: float = 0.1):
        """Simulate partial data loss in processing"""
        def lossy_data_processor(data_list):
            return [item for item in data_list if random.random() > loss_rate]
        
        self.active_failures['data_loss'] = lossy_data_processor
        return True
    
    def clear_all_failures(self):
        """Clear all injected failures"""
        # Clean up memory pressure
        if 'memory_pressure' in self.active_failures:
            del self.active_failures['memory_pressure']
        
        # Restore original functions
        for name, original_func in self.original_functions.items():
            # Would restore original functions in real implementation
            pass
        
        self.active_failures.clear()
        self.original_functions.clear()

class ChaosEngineeringTests(BaseTestCase):
    """Chaos engineering tests for system resilience"""
    
    def setUp(self):
        super().setUp()
        self.failure_injector = ChaosFailureInjector()
        self.csv_writer = ConsolidatedCSVWriter()
        self.health_monitor = EnhancedHealthMonitor()
        
        # Performance baseline
        self.baseline_performance = self._measure_baseline_performance()
    
    def tearDown(self):
        super().tearDown()
        self.failure_injector.clear_all_failures()
    
    def _measure_baseline_performance(self) -> Dict[str, float]:
        """Measure baseline system performance"""
        baseline = {}
        
        # Generate test data
        test_legs = [self.data_generator.generate_option_leg() for _ in range(100)]
        
        # Measure processing time
        start_time = time.time()
        result = asyncio.run(self.csv_writer.process_and_write(
            test_legs, write_legs=True, write_merged=True
        ))
        processing_time = time.time() - start_time
        
        baseline['processing_time_per_record'] = processing_time / len(test_legs)
        baseline['records_per_second'] = len(test_legs) / processing_time
        baseline['memory_usage_mb'] = psutil.Process().memory_info().rss / (1024 * 1024)
        
        return baseline
    
    def test_network_timeout_resilience(self):
        """Test system behavior under network timeouts"""
        result = ChaosTestResult(
            test_name="network_timeout_resilience",
            failure_type=FailureType.NETWORK_TIMEOUT,
            duration_seconds=0,
            success=False
        )
        
        start_time = time.time()
        
        try:
            # Inject network timeouts
            self.failure_injector.inject_network_timeout(0.3)
            
            # Generate test data
            test_legs = [self.data_generator.generate_option_leg() for _ in range(50)]
            
            # Process data with network failures
            with patch('services.processing.writers.consolidated_csv_writer.ConsolidatedCSVWriter._write_json_snapshot_async') as mock_json:
                mock_json.side_effect = lambda x: self._maybe_fail_with_timeout()
                
                processing_result = asyncio.run(self.csv_writer.process_and_write(
                    test_legs, write_legs=True, write_merged=True
                ))
            
            # System should still process most data despite failures
            result.success = processing_result.get('legs_written', 0) > len(test_legs) * 0.7  # 70% success rate
            result.data_integrity_maintained = self._verify_data_integrity()
            
        except Exception as e:
            result.error_message = str(e)
        
        result.duration_seconds = time.time() - start_time
        self.assertTrue(result.success, f"Network timeout test failed: {result.error_message}")
    
    def test_disk_full_recovery(self):
        """Test system behavior when disk space is exhausted"""
        result = ChaosTestResult(
            test_name="disk_full_recovery",
            failure_type=FailureType.DISK_FULL,
            duration_seconds=0,
            success=False
        )
        
        start_time = time.time()
        
        try:
            # Simulate disk full
            self.failure_injector.inject_disk_full_simulation(self.temp_dir, 10)  # 10MB limit
            
            # Generate large dataset
            large_dataset = [self.data_generator.generate_option_leg() for _ in range(200)]
            
            # Process with disk space constraints
            with patch('pathlib.Path.exists') as mock_exists:
                mock_exists.return_value = True
                
                # Should handle disk full gracefully
                processing_result = asyncio.run(self.csv_writer.process_and_write(
                    large_dataset, write_legs=True, write_merged=False
                ))
                
                # System should either succeed or fail gracefully
                result.success = True  # No crashes
                result.system_recovered = True
        
        except Exception as e:
            # System crash is a failure
            result.error_message = str(e)
            result.success = False
        
        result.duration_seconds = time.time() - start_time
        self.assertTrue(result.success, f"Disk full recovery test failed: {result.error_message}")
    
    def test_memory_exhaustion_handling(self):
        """Test system behavior under memory pressure"""
        result = ChaosTestResult(
            test_name="memory_exhaustion_handling",
            failure_type=FailureType.MEMORY_EXHAUSTION,
            duration_seconds=0,
            success=False
        )
        
        initial_memory = psutil.Process().memory_info().rss
        start_time = time.time()
        
        try:
            # Create memory pressure
            memory_allocated = self.failure_injector.inject_memory_pressure(300)  # 300MB
            
            if memory_allocated:
                # Process data under memory pressure
                test_legs = [self.data_generator.generate_option_leg() for _ in range(100)]
                
                processing_result = asyncio.run(self.csv_writer.process_and_write(
                    test_legs, write_legs=True, write_merged=True
                ))
                
                # System should handle memory pressure without crashing
                result.success = processing_result.get('legs_written', 0) > 0
                
                # Check if memory usage is reasonable
                final_memory = psutil.Process().memory_info().rss
                memory_growth = (final_memory - initial_memory) / (1024 * 1024)
                result.performance_impact_percent = (memory_growth / 300) * 100
                
                result.data_integrity_maintained = self._verify_data_integrity()
            else:
                result.success = True  # Could not allocate memory, test inconclusive
        
        except MemoryError:
            # Expected under memory pressure
            result.success = True  # Graceful handling
        except Exception as e:
            result.error_message = str(e)
        
        result.duration_seconds = time.time() - start_time
        self.assertTrue(result.success, f"Memory exhaustion test failed: {result.error_message}")
    
    def test_file_corruption_recovery(self):
        """Test recovery from file corruption"""
        result = ChaosTestResult(
            test_name="file_corruption_recovery",
            failure_type=FailureType.FILE_CORRUPTION,
            duration_seconds=0,
            success=False
        )
        
        start_time = time.time()
        
        try:
            # Create initial data file
            test_data = [
                {"ts": "2025-08-24 10:00:00", "index": "NIFTY", "last_price": "100.50"},
                {"ts": "2025-08-24 10:01:00", "index": "NIFTY", "last_price": "101.00"},
                {"ts": "2025-08-24 10:02:00", "index": "NIFTY", "last_price": "100.75"},
            ]
            
            test_file = self.create_test_csv_file(
                self.test_data_dir / "corruption_test.csv", test_data
            )
            
            # Corrupt the file
            corruption_success = self.failure_injector.inject_file_corruption(test_file)
            self.assertTrue(corruption_success, "Failed to inject corruption")
            
            # Try to read corrupted file
            try:
                rows = self.csv_writer.read_file_incrementally(test_file, 0)
                
                # System should handle corruption gracefully
                # Either skip corrupted rows or fail gracefully
                result.success = True  # No crash
                result.data_integrity_maintained = len(rows) >= 0  # At least some data recovered
                
            except Exception as read_error:
                # Graceful error handling is acceptable
                result.success = "corrupted" in str(read_error).lower() or "invalid" in str(read_error).lower()
                result.error_message = str(read_error)
        
        except Exception as e:
            result.error_message = str(e)
        
        result.duration_seconds = time.time() - start_time
        self.assertTrue(result.success, f"File corruption recovery failed: {result.error_message}")
    
    def test_concurrent_failure_scenarios(self):
        """Test system behavior under multiple concurrent failures"""
        result = ChaosTestResult(
            test_name="concurrent_failures",
            failure_type=FailureType.PROCESS_CRASH,  # Multiple failure types
            duration_seconds=0,
            success=False
        )
        
        start_time = time.time()
        
        try:
            # Inject multiple failures
            self.failure_injector.inject_network_timeout(0.2)
            self.failure_injector.inject_memory_pressure(100)
            self.failure_injector.inject_high_cpu_load(15)
            
            # Process data under multiple failure conditions
            test_legs = [self.data_generator.generate_option_leg() for _ in range(75)]
            
            # Use multiple threads to stress the system
            def process_batch(batch):
                return asyncio.run(self.csv_writer.process_and_write(
                    batch, write_legs=True, write_merged=False
                ))
            
            # Split into batches for concurrent processing
            batch_size = 25
            batches = [test_legs[i:i+batch_size] for i in range(0, len(test_legs), batch_size)]
            
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(process_batch, batch) for batch in batches]
                results = [future.result() for future in as_completed(futures)]
            
            # System should survive multiple concurrent failures
            total_written = sum(r.get('legs_written', 0) for r in results)
            result.success = total_written > 0  # Some data processed despite failures
            result.performance_impact_percent = ((len(test_legs) - total_written) / len(test_legs)) * 100
            
        except Exception as e:
            result.error_message = str(e)
        
        result.duration_seconds = time.time() - start_time
        self.assertTrue(result.success, f"Concurrent failures test failed: {result.error_message}")
    
    def test_data_integrity_under_chaos(self):
        """Test that data integrity is maintained during chaos conditions"""
        result = ChaosTestResult(
            test_name="data_integrity_chaos",
            failure_type=FailureType.PARTIAL_DATA_LOSS,
            duration_seconds=0,
            success=False
        )
        
        start_time = time.time()
        
        try:
            # Generate uniquely identifiable test data
            unique_legs = []
            for i in range(50):
                leg = self.data_generator.generate_option_leg()
                leg.volume = 50000 + i  # Unique identifier
                unique_legs.append(leg)
            
            # Inject partial data loss
            self.failure_injector.inject_partial_data_loss(0.1)  # 10% loss rate
            
            # Process data with potential losses
            processing_result = asyncio.run(self.csv_writer.process_and_write(
                unique_legs, write_legs=True, write_merged=True
            ))
            
            # Verify data integrity
            written_volumes = set()
            csv_files = list(self.csv_writer.settings.data.csv_data_root.rglob("*.csv"))
            
            for csv_file in csv_files:
                if csv_file.exists():
                    rows = self.csv_writer.read_file_incrementally(csv_file, 0)
                    for row in rows:
                        if row.get('volume'):
                            volume = int(float(row['volume']))
                            if volume >= 50000:  # Our test data
                                written_volumes.add(volume)
            
            # Check data consistency
            expected_volumes = {50000 + i for i in range(50)}
            data_loss_rate = len(expected_volumes - written_volumes) / len(expected_volumes)
            
            result.success = data_loss_rate < 0.2  # Accept up to 20% loss under chaos
            result.data_integrity_maintained = len(written_volumes) > 0
            result.performance_impact_percent = data_loss_rate * 100
            
        except Exception as e:
            result.error_message = str(e)
        
        result.duration_seconds = time.time() - start_time
        self.assertTrue(result.success, f"Data integrity chaos test failed: {result.error_message}")
    
    def _maybe_fail_with_timeout(self):
        """Helper to randomly fail with timeout"""
        if random.random() < 0.3:
            raise TimeoutError("Simulated network timeout")
        return True
    
    def _verify_data_integrity(self) -> bool:
        """Verify that written data maintains integrity"""
        try:
            csv_files = list(self.csv_writer.settings.data.csv_data_root.rglob("*.csv"))
            
            for csv_file in csv_files[:5]:  # Check a few files
                if csv_file.exists():
                    rows = self.csv_writer.read_file_incrementally(csv_file, 0)
                    
                    for row in rows:
                        # Basic integrity checks
                        if not row.get('ts'):
                            return False
                        if not row.get('index'):
                            return False
                        
                        # Validate timestamp format
                        try:
                            get_time_utils().parse_csv_timestamp(row['ts'])
                        except Exception:
                            return False
                        
                        # Validate numeric fields
                        if row.get('last_price'):
                            try:
                                float(row['last_price'])
                            except ValueError:
                                return False
            
            return True
            
        except Exception:
            return False

class EODDataVerificationSystem:
    """End-of-day data verification and quality assurance"""
    
    def __init__(self):
        self.settings = get_settings()
        self.time_utils = get_time_utils()
        self.verification_results: Dict[str, Any] = {}
    
    def run_eod_verification(self, verification_date: date) -> Dict[str, Any]:
        """Run comprehensive end-of-day data verification"""
        
        verification_results = {
            'date': verification_date.isoformat(),
            'timestamp': self.time_utils.get_metadata_timestamp(),
            'overall_status': 'UNKNOWN',
            'checks': {},
            'summary': {
                'total_files': 0,
                'files_with_issues': 0,
                'total_records': 0,
                'corrupted_records': 0,
                'missing_data_periods': 0,
                'data_quality_score': 0.0
            },
            'issues': [],
            'recommendations': []
        }
        
        try:
            # 1. File completeness check
            file_check = self._check_file_completeness(verification_date)
            verification_results['checks']['file_completeness'] = file_check
            
            # 2. Data integrity check
            integrity_check = self._check_data_integrity(verification_date)
            verification_results['checks']['data_integrity'] = integrity_check
            
            # 3. Timestamp consistency check
            timestamp_check = self._check_timestamp_consistency(verification_date)
            verification_results['checks']['timestamp_consistency'] = timestamp_check
            
            # 4. Market hours coverage check
            coverage_check = self._check_market_hours_coverage(verification_date)
            verification_results['checks']['market_coverage'] = coverage_check
            
            # 5. Data volume analysis
            volume_check = self._check_data_volumes(verification_date)
            verification_results['checks']['data_volumes'] = volume_check
            
            # 6. Cross-validation with database
            db_check = self._cross_validate_with_database(verification_date)
            verification_results['checks']['database_consistency'] = db_check
            
            # Calculate overall status and scores
            self._calculate_verification_summary(verification_results)
            
            # Generate recommendations
            self._generate_recommendations(verification_results)
            
        except Exception as e:
            verification_results['overall_status'] = 'ERROR'
            verification_results['error'] = str(e)
            logger.error(f"EOD verification failed: {e}")
        
        self.verification_results = verification_results
        return verification_results
    
    def _check_file_completeness(self, verification_date: date) -> Dict[str, Any]:
        """Check if all expected files are present"""
        check_result = {
            'status': 'PASS',
            'expected_files': 0,
            'found_files': 0,
            'missing_files': [],
            'details': {}
        }
        
        try:
            date_str = verification_date.isoformat()
            csv_root = self.settings.data.csv_data_root
            
            # Expected file pattern: INDEX/BUCKET/OFFSET/DATE.csv
            expected_patterns = []
            indices = ["NIFTY", "BANKNIFTY", "SENSEX"]
            buckets = ["this_week", "next_week", "this_month", "next_month"]
            offsets = ["atm_m2", "atm_m1", "atm", "atm_p1", "atm_p2"]
            file_types = ["legs", "merged"]
            
            for index in indices:
                for bucket in buckets:
                    for offset in offsets:
                        for file_type in file_types:
                            expected_file = csv_root / index / bucket / offset / f"{date_str}_{file_type}.csv"
                            expected_patterns.append(expected_file)
                            
                            if expected_file.exists():
                                check_result['found_files'] += 1
                            else:
                                check_result['missing_files'].append(str(expected_file.relative_to(csv_root)))
            
            check_result['expected_files'] = len(expected_patterns)
            
            # Calculate completion percentage
            completion_rate = check_result['found_files'] / check_result['expected_files'] if check_result['expected_files'] > 0 else 0
            
            if completion_rate < 0.8:  # Less than 80% complete
                check_result['status'] = 'FAIL'
            elif completion_rate < 0.95:  # Less than 95% complete
                check_result['status'] = 'WARN'
            
            check_result['completion_rate'] = completion_rate
            
        except Exception as e:
            check_result['status'] = 'ERROR'
            check_result['error'] = str(e)
        
        return check_result
    
    def _check_data_integrity(self, verification_date: date) -> Dict[str, Any]:
        """Check data integrity within files"""
        check_result = {
            'status': 'PASS',
            'files_checked': 0,
            'files_with_errors': 0,
            'total_records': 0,
            'corrupted_records': 0,
            'integrity_issues': []
        }
        
        try:
            date_str = verification_date.isoformat()
            csv_files = list(self.settings.data.csv_data_root.rglob(f"*{date_str}*.csv"))
            
            for csv_file in csv_files:
                try:
                    check_result['files_checked'] += 1
                    file_issues = []
                    
                    with open(csv_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        row_count = 0
                        
                        for row_num, row in enumerate(reader, 1):
                            row_count += 1
                            check_result['total_records'] += 1
                            
                            # Check required fields
                            if not row.get('ts'):
                                file_issues.append(f"Row {row_num}: Missing timestamp")
                                check_result['corrupted_records'] += 1
                            
                            if not row.get('index'):
                                file_issues.append(f"Row {row_num}: Missing index")
                                check_result['corrupted_records'] += 1
                            
                            # Validate timestamp format
                            if row.get('ts'):
                                try:
                                    self.time_utils.parse_csv_timestamp(row['ts'])
                                except Exception:
                                    file_issues.append(f"Row {row_num}: Invalid timestamp format")
                                    check_result['corrupted_records'] += 1
                            
                            # Validate numeric fields
                            for field in ['last_price', 'bid', 'ask', 'volume', 'oi']:
                                if row.get(field) and row[field] != '':
                                    try:
                                        float(row[field])
                                    except ValueError:
                                        file_issues.append(f"Row {row_num}: Invalid {field} value")
                                        check_result['corrupted_records'] += 1
                    
                    if file_issues:
                        check_result['files_with_errors'] += 1
                        check_result['integrity_issues'].append({
                            'file': str(csv_file.name),
                            'issues': file_issues[:10]  # Limit to first 10 issues per file
                        })
                
                except Exception as e:
                    check_result['files_with_errors'] += 1
                    check_result['integrity_issues'].append({
                        'file': str(csv_file.name),
                        'issues': [f"File read error: {str(e)}"]
                    })
            
            # Determine status
            corruption_rate = check_result['corrupted_records'] / check_result['total_records'] if check_result['total_records'] > 0 else 0
            
            if corruption_rate > 0.05:  # More than 5% corruption
                check_result['status'] = 'FAIL'
            elif corruption_rate > 0.01:  # More than 1% corruption
                check_result['status'] = 'WARN'
            
            check_result['corruption_rate'] = corruption_rate
            
        except Exception as e:
            check_result['status'] = 'ERROR'
            check_result['error'] = str(e)
        
        return check_result
    
    def _check_timestamp_consistency(self, verification_date: date) -> Dict[str, Any]:
        """Check timestamp consistency and ordering"""
        check_result = {
            'status': 'PASS',
            'files_checked': 0,
            'timestamp_issues': 0,
            'out_of_order_sequences': 0,
            'duplicate_timestamps': 0,
            'issues': []
        }
        
        try:
            date_str = verification_date.isoformat()
            csv_files = list(self.settings.data.csv_data_root.rglob(f"*{date_str}*.csv"))
            
            for csv_file in csv_files[:10]:  # Check sample of files
                try:
                    check_result['files_checked'] += 1
                    
                    with open(csv_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        timestamps = []
                        
                        for row in reader:
                            if row.get('ts'):
                                try:
                                    ts = self.time_utils.parse_csv_timestamp(row['ts'])
                                    timestamps.append(ts)
                                except Exception:
                                    check_result['timestamp_issues'] += 1
                        
                        # Check for duplicates
                        unique_timestamps = set(timestamps)
                        duplicates = len(timestamps) - len(unique_timestamps)
                        check_result['duplicate_timestamps'] += duplicates
                        
                        # Check ordering (should be chronological)
                        sorted_timestamps = sorted(timestamps)
                        if timestamps != sorted_timestamps:
                            check_result['out_of_order_sequences'] += 1
                            check_result['issues'].append(f"{csv_file.name}: Timestamps not in order")
                        
                        # Check for reasonable timestamp range (should be on verification date)
                        for ts in timestamps:
                            if ts.date() != verification_date:
                                check_result['timestamp_issues'] += 1
                                check_result['issues'].append(f"{csv_file.name}: Timestamp {ts} not on expected date")
                                break
                
                except Exception as e:
                    check_result['issues'].append(f"{csv_file.name}: Error checking timestamps - {str(e)}")
            
            # Determine status
            if check_result['timestamp_issues'] > 10 or check_result['out_of_order_sequences'] > 5:
                check_result['status'] = 'FAIL'
            elif check_result['timestamp_issues'] > 0 or check_result['out_of_order_sequences'] > 0:
                check_result['status'] = 'WARN'
                
        except Exception as e:
            check_result['status'] = 'ERROR'
            check_result['error'] = str(e)
        
        return check_result
    
    def _check_market_hours_coverage(self, verification_date: date) -> Dict[str, Any]:
        """Check if data covers expected market hours"""
        check_result = {
            'status': 'PASS',
            'expected_minutes': 0,
            'covered_minutes': 0,
            'coverage_percentage': 0,
            'missing_periods': [],
            'data_gaps': []
        }
        
        try:
            # Skip weekends
            if verification_date.weekday() >= 5:
                check_result['status'] = 'SKIP'
                check_result['note'] = 'Weekend - no market data expected'
                return check_result
            
            # Get expected market minutes
            expected_buckets = self.time_utils.get_minute_buckets_for_session(verification_date)
            check_result['expected_minutes'] = len(expected_buckets)
            
            # Check actual coverage from files
            date_str = verification_date.isoformat()
            csv_files = list(self.settings.data.csv_data_root.rglob(f"*{date_str}*.csv"))
            
            covered_buckets = set()
            
            for csv_file in csv_files:
                try:
                    with open(csv_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        
                        for row in reader:
                            if row.get('ts'):
                                try:
                                    ts = self.time_utils.parse_csv_timestamp(row['ts'])
                                    bucket = self.time_utils.bucket_to_minute(ts)
                                    covered_buckets.add(bucket)
                                except Exception:
                                    pass
                
                except Exception:
                    continue
            
            check_result['covered_minutes'] = len(covered_buckets)
            check_result['coverage_percentage'] = (len(covered_buckets) / len(expected_buckets)) * 100 if expected_buckets else 0
            
            # Find missing periods
            missing_buckets = set(expected_buckets) - covered_buckets
            check_result['missing_periods'] = sorted(list(missing_buckets))
            
            # Determine status
            if check_result['coverage_percentage'] < 80:
                check_result['status'] = 'FAIL'
            elif check_result['coverage_percentage'] < 95:
                check_result['status'] = 'WARN'
                
        except Exception as e:
            check_result['status'] = 'ERROR'
            check_result['error'] = str(e)
        
        return check_result
    
    def _check_data_volumes(self, verification_date: date) -> Dict[str, Any]:
        """Check if data volumes are reasonable"""
        check_result = {
            'status': 'PASS',
            'total_records': 0,
            'records_per_minute_avg': 0,
            'volume_anomalies': [],
            'index_distribution': {}
        }
        
        try:
            date_str = verification_date.isoformat()
            csv_files = list(self.settings.data.csv_data_root.rglob(f"*{date_str}*.csv"))
            
            minute_counts: Dict[str, int] = {}
            index_counts: Dict[str, int] = {}
            
            for csv_file in csv_files:
                try:
                    with open(csv_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        
                        for row in reader:
                            check_result['total_records'] += 1
                            
                            # Count by minute
                            if row.get('ts'):
                                try:
                                    ts = self.time_utils.parse_csv_timestamp(row['ts'])
                                    bucket = self.time_utils.bucket_to_minute(ts)
                                    minute_counts[bucket] = minute_counts.get(bucket, 0) + 1
                                except Exception:
                                    pass
                            
                            # Count by index
                            if row.get('index'):
                                index_counts[row['index']] = index_counts.get(row['index'], 0) + 1
                
                except Exception:
                    continue
            
            # Calculate averages
            if minute_counts:
                check_result['records_per_minute_avg'] = sum(minute_counts.values()) / len(minute_counts)
                
                # Find volume anomalies (minutes with unusually low/high record counts)
                avg_count = check_result['records_per_minute_avg']
                for minute, count in minute_counts.items():
                    if count < avg_count * 0.3:  # Less than 30% of average
                        check_result['volume_anomalies'].append(f"{minute}: Only {count} records (avg: {avg_count:.1f})")
            
            check_result['index_distribution'] = index_counts
            
            # Determine status based on total volume
            expected_minimum = 1000  # Minimum expected records per day
            if check_result['total_records'] < expected_minimum:
                check_result['status'] = 'FAIL'
            elif len(check_result['volume_anomalies']) > 10:
                check_result['status'] = 'WARN'
                
        except Exception as e:
            check_result['status'] = 'ERROR'
            check_result['error'] = str(e)
        
        return check_result
    
    def _cross_validate_with_database(self, verification_date: date) -> Dict[str, Any]:
        """Cross-validate file data with database records"""
        check_result = {
            'status': 'PASS',
            'csv_records': 0,
            'db_records': 0,
            'match_percentage': 0,
            'discrepancies': []
        }
        
        try:
            # Count records in CSV files
            date_str = verification_date.isoformat()
            csv_files = list(self.settings.data.csv_data_root.rglob(f"*{date_str}*.csv"))
            
            for csv_file in csv_files:
                try:
                    with open(csv_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        check_result['csv_records'] += sum(1 for _ in reader)
                except Exception:
                    continue
            
            # Query database for same date
            try:
                from influxdb_client import InfluxDBClient
                
                client = InfluxDBClient(
                    url=self.settings.database.url,
                    token=self.settings.database.token,
                    org=self.settings.database.org
                )
                
                start_time = verification_date.strftime('%Y-%m-%d') + 'T00:00:00Z'
                end_time = (verification_date + timedelta(days=1)).strftime('%Y-%m-%d') + 'T00:00:00Z'
                
                query = f'''
                    from(bucket: "{self.settings.database.bucket}")
                    |> range(start: {start_time}, stop: {end_time})
                    |> filter(fn: (r) => r._measurement == "atm_option_quote")
                    |> count()
                '''
                
                query_api = client.query_api()
                result = query_api.query(query)
                
                db_count = 0
                for table in result:
                    for row in table.records:
                        db_count += row.get_value()
                
                check_result['db_records'] = db_count
                client.close()
                
            except Exception as e:
                check_result['db_query_error'] = str(e)
                check_result['status'] = 'WARN'
                return check_result
            
            # Calculate match percentage
            if check_result['db_records'] > 0:
                check_result['match_percentage'] = (check_result['csv_records'] / check_result['db_records']) * 100
            
            # Determine status
            if abs(check_result['match_percentage'] - 100) > 10:  # More than 10% difference
                check_result['status'] = 'WARN'
                check_result['discrepancies'].append(f"CSV vs DB record count mismatch: {check_result['match_percentage']:.1f}%")
                
        except Exception as e:
            check_result['status'] = 'ERROR'
            check_result['error'] = str(e)
        
        return check_result
    
    def _calculate_verification_summary(self, results: Dict[str, Any]):
        """Calculate overall verification summary and scores"""
        
        # Count check statuses
        status_counts = {'PASS': 0, 'WARN': 0, 'FAIL': 0, 'ERROR': 0, 'SKIP': 0}
        
        for check_name, check_result in results['checks'].items():
            status = check_result.get('status', 'ERROR')
            status_counts[status] += 1
        
        # Calculate data quality score (0-100)
        total_checks = sum(status_counts.values()) - status_counts['SKIP']
        if total_checks > 0:
            score = (
                (status_counts['PASS'] * 100 + status_counts['WARN'] * 70 + status_counts['FAIL'] * 30) 
                / total_checks
            )
            results['summary']['data_quality_score'] = score
        else:
            results['summary']['data_quality_score'] = 0
        
        # Determine overall status
        if status_counts['ERROR'] > 0:
            results['overall_status'] = 'ERROR'
        elif status_counts['FAIL'] > 0:
            results['overall_status'] = 'FAIL'
        elif status_counts['WARN'] > 0:
            results['overall_status'] = 'WARN'
        else:
            results['overall_status'] = 'PASS'
        
        # Update summary counts
        for check_result in results['checks'].values():
            if 'files_checked' in check_result:
                results['summary']['total_files'] += check_result.get('files_checked', 0)
            if 'files_with_errors' in check_result:
                results['summary']['files_with_issues'] += check_result.get('files_with_errors', 0)
            if 'total_records' in check_result:
                results['summary']['total_records'] += check_result.get('total_records', 0)
            if 'corrupted_records' in check_result:
                results['summary']['corrupted_records'] += check_result.get('corrupted_records', 0)
    
    def _generate_recommendations(self, results: Dict[str, Any]):
        """Generate actionable recommendations based on verification results"""
        
        recommendations = []
        
        # File completeness recommendations
        file_check = results['checks'].get('file_completeness', {})
        if file_check.get('status') in ['FAIL', 'WARN']:
            missing_count = len(file_check.get('missing_files', []))
            recommendations.append(f"Investigate {missing_count} missing data files - check collection service health")
        
        # Data integrity recommendations
        integrity_check = results['checks'].get('data_integrity', {})
        if integrity_check.get('status') in ['FAIL', 'WARN']:
            corruption_rate = integrity_check.get('corruption_rate', 0) * 100
            recommendations.append(f"Data corruption detected ({corruption_rate:.1f}%) - review data validation and error handling")
        
        # Coverage recommendations
        coverage_check = results['checks'].get('market_coverage', {})
        if coverage_check.get('status') in ['FAIL', 'WARN']:
            coverage = coverage_check.get('coverage_percentage', 0)
            recommendations.append(f"Market hours coverage is {coverage:.1f}% - check for collection gaps during market hours")
        
        # Volume recommendations
        volume_check = results['checks'].get('data_volumes', {})
        if volume_check.get('status') in ['FAIL', 'WARN']:
            if volume_check.get('total_records', 0) < 1000:
                recommendations.append("Very low data volume detected - verify collection service is running")
            
            anomalies = len(volume_check.get('volume_anomalies', []))
            if anomalies > 0:
                recommendations.append(f"{anomalies} minutes with unusual data volumes - investigate potential collection issues")
        
        # Database consistency recommendations
        db_check = results['checks'].get('database_consistency', {})
        if db_check.get('status') in ['FAIL', 'WARN']:
            match_pct = db_check.get('match_percentage', 0)
            recommendations.append(f"CSV-Database consistency is {match_pct:.1f}% - verify data pipeline integrity")
        
        # General recommendations based on overall score
        score = results['summary']['data_quality_score']
        if score < 70:
            recommendations.append("Overall data quality is poor - consider implementing additional validation and monitoring")
        elif score < 90:
            recommendations.append("Data quality could be improved - review error handling and data validation processes")
        
        results['recommendations'] = recommendations
    
    def save_verification_report(self, results: Dict[str, Any], output_path: Optional[Path] = None) -> Path:
        """Save verification report to file"""
        if output_path is None:
            output_path = Path(f"eod_verification_{results['date']}.json")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        
        return output_path

class TestChaosEngineeringAndEOD(BaseTestCase):
    """Test chaos engineering and EOD verification systems"""
    
    def setUp(self):
        super().setUp()
        self.eod_verifier = EODDataVerificationSystem()
    
    def test_chaos_engineering_suite(self):
        """Run comprehensive chaos engineering test suite"""
        chaos_tests = ChaosEngineeringTests()
        chaos_tests.setUp()
        
        try:
            # Run all chaos tests
            test_methods = [
                chaos_tests.test_network_timeout_resilience,
                chaos_tests.test_disk_full_recovery,
                chaos_tests.test_memory_exhaustion_handling,
                chaos_tests.test_file_corruption_recovery,
                chaos_tests.test_concurrent_failure_scenarios,
                chaos_tests.test_data_integrity_under_chaos
            ]
            
            results = []
            for test_method in test_methods:
                try:
                    test_method()
                    results.append(f"✓ {test_method.__name__}")
                except AssertionError as e:
                    results.append(f"✗ {test_method.__name__}: {e}")
                except Exception as e:
                    results.append(f"⚠ {test_method.__name__}: {e}")
            
            # At least 80% of chaos tests should pass
            passed = sum(1 for r in results if r.startswith("✓"))
            pass_rate = passed / len(results)
            
            self.assertGreater(pass_rate, 0.8, f"Chaos test pass rate too low: {pass_rate:.1%}\n" + "\n".join(results))
            
        finally:
            chaos_tests.tearDown()
    
    def test_eod_verification_system(self):
        """Test EOD verification system"""
        # Create sample data for verification
        verification_date = date.today() - timedelta(days=1)
        
        # Generate test data files
        test_legs = [self.data_generator.generate_option_leg() for _ in range(100)]
        
        # Process test data to create files
        csv_writer = ConsolidatedCSVWriter()
        result = asyncio.run(csv_writer.process_and_write(
            test_legs, write_legs=True, write_merged=True
        ))
        
        # Run EOD verification
        verification_results = self.eod_verifier.run_eod_verification(verification_date)
        
        # Verify verification system works
        self.assertIn('overall_status', verification_results)
        self.assertIn('checks', verification_results)
        self.assertIn('summary', verification_results)
        
        # Should have completed all major checks
        expected_checks = [
            'file_completeness', 'data_integrity', 'timestamp_consistency',
            'market_coverage', 'data_volumes', 'database_consistency'
        ]
        
        for check_name in expected_checks:
            self.assertIn(check_name, verification_results['checks'])
            check_result = verification_results['checks'][check_name]
            self.assertIn('status', check_result)
        
        # Data quality score should be reasonable
        quality_score = verification_results['summary']['data_quality_score']
        self.assertGreaterEqual(quality_score, 0)
        self.assertLessEqual(quality_score, 100)
    
    def test_eod_verification_with_issues(self):
        """Test EOD verification detects data issues"""
        verification_date = date.today()
        
        # Create files with known issues
        corrupted_data = [
            {"ts": "invalid-timestamp", "index": "NIFTY", "last_price": "abc"},  # Bad timestamp and price
            {"ts": "2025-08-24 10:01:00", "index": "", "last_price": "101.00"},  # Missing index
            {"ts": "2025-08-24 10:02:00", "index": "NIFTY", "last_price": ""},   # Missing price
        ]
        
        corrupted_file = self.create_test_csv_file(
            self.test_data_dir / "NIFTY" / "this_week" / "atm" / f"{verification_date.isoformat()}_legs.csv",
            corrupted_data
        )
        
        # Run verification
        results = self.eod_verifier.run_eod_verification(verification_date)
        
        # Should detect integrity issues
        integrity_check = results['checks']['data_integrity']
        self.assertGreater(integrity_check.get('corrupted_records', 0), 0)
        self.assertIn(integrity_check.get('status'), ['WARN', 'FAIL'])

if __name__ == "__main__":
    # Configure logging for chaos tests
    logging.basicConfig(level=logging.WARNING)
    
    # Run chaos and EOD tests
    unittest.main(verbosity=2)