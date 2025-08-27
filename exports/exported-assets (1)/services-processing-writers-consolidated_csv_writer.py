"""
Consolidated CSV Writer with incremental reading and async processing.
Combines CSV sidecar and daily split functionality for improved efficiency.
Implements minute cursors and Windows file lock coordination.
"""

import os
import csv
import gzip
import json
import asyncio
import aiofiles
import logging
import hashlib
from typing import Dict, List, Any, Optional, Union, TextIO
from pathlib import Path
from datetime import datetime, date
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import time
import threading

from ...shared.utils.coordination import get_file_coordinator, get_redis_coordinator
from ...shared.utils.time_utils import get_time_utils, now_csv_format, TimeFormat
from ...shared.config.settings import get_settings

logger = logging.getLogger(__name__)

@dataclass
class OptionLegData:
    """Standardized option leg data structure"""
    ts: str                    # Standardized timestamp (IST format)
    index: str                # NIFTY, BANKNIFTY, SENSEX
    bucket: str               # this_week, next_week, this_month, next_month
    expiry: str               # Expiry date
    side: str                 # CALL, PUT
    atm_strike: float         # ATM strike price
    strike: float             # Actual strike price
    strike_offset: int        # Offset from ATM (-2, -1, 0, 1, 2)
    last_price: float         # Last traded price
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[int] = None
    oi: Optional[int] = None
    iv: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for CSV writing"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OptionLegData':
        """Create from dictionary"""
        # Handle optional fields
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

@dataclass
class MergedOptionData:
    """Merged CE+PE data for a specific strike/offset"""
    ts: str
    index: str
    bucket: str
    expiry: str
    strike_offset: int
    atm_strike: float
    strike: float
    
    # CALL data
    call_last_price: Optional[float] = None
    call_bid: Optional[float] = None
    call_ask: Optional[float] = None
    call_volume: Optional[int] = None
    call_oi: Optional[int] = None
    call_iv: Optional[float] = None
    call_delta: Optional[float] = None
    call_gamma: Optional[float] = None
    call_theta: Optional[float] = None
    call_vega: Optional[float] = None
    
    # PUT data
    put_last_price: Optional[float] = None
    put_bid: Optional[float] = None
    put_ask: Optional[float] = None
    put_volume: Optional[int] = None
    put_oi: Optional[int] = None
    put_iv: Optional[float] = None
    put_delta: Optional[float] = None
    put_gamma: Optional[float] = None
    put_theta: Optional[float] = None
    put_vega: Optional[float] = None
    
    # Computed fields
    total_premium: Optional[float] = None
    total_volume: Optional[int] = None
    total_oi: Optional[int] = None
    put_call_ratio: Optional[float] = None
    
    def __post_init__(self):
        """Compute derived fields"""
        # Total premium (call + put)
        if self.call_last_price is not None and self.put_last_price is not None:
            self.total_premium = self.call_last_price + self.put_last_price
        
        # Total volume
        call_vol = self.call_volume or 0
        put_vol = self.put_volume or 0
        if call_vol > 0 or put_vol > 0:
            self.total_volume = call_vol + put_vol
        
        # Total OI
        call_oi = self.call_oi or 0
        put_oi = self.put_oi or 0
        if call_oi > 0 or put_oi > 0:
            self.total_oi = call_oi + put_oi
        
        # Put-call ratio (put OI / call OI)
        if self.call_oi and self.call_oi > 0 and self.put_oi:
            self.put_call_ratio = self.put_oi / self.call_oi

class ConsolidatedCSVWriter:
    """
    High-performance CSV writer that consolidates sidecar and split functionality.
    Features:
    - Incremental reading with minute cursors
    - Async batch writing
    - Redis coordination for file locking
    - Memory-mapped file access for large files
    - Automatic archival and compression
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.time_utils = get_time_utils()
        self.file_coordinator = get_file_coordinator()
        self.redis_coordinator = get_redis_coordinator()
        
        # Threading for async operations
        self.executor = ThreadPoolExecutor(max_workers=self.settings.service.processing_max_workers)
        self.write_lock = threading.Lock()
        
        # Batch processing
        self.batch_buffer: Dict[str, List[Any]] = {}
        self.batch_size = self.settings.service.processing_batch_size
        self.last_flush_time = time.time()
        self.flush_interval = 30  # seconds
        
        # Performance tracking
        self.stats = {
            'writes_completed': 0,
            'writes_failed': 0,
            'bytes_written': 0,
            'files_processed': 0,
            'cursor_updates': 0,
            'batch_flushes': 0
        }
    
    def get_consolidated_file_path(self, index: str, bucket: str, offset: str, date_str: str, 
                                 file_type: str = "merged") -> Path:
        """
        Get file path for consolidated CSV files.
        file_type: 'legs' for individual legs, 'merged' for CE+PE merged data
        """
        base_path = self.settings.data.csv_data_root
        return base_path / index / bucket / offset / f"{date_str}_{file_type}.csv"
    
    def get_json_snapshot_path(self, index: str, bucket: str, date_str: str, 
                              timestamp: str) -> Path:
        """Get JSON snapshot path for audit trail"""
        base_path = self.settings.data.json_snapshots_root
        # Create minute-based directory structure for better organization
        minute_dir = timestamp.replace(":", "").replace(" ", "_").replace("-", "")[:12]  # YYYYMMDDHHMM
        return base_path / index / bucket / date_str / f"{minute_dir}.json"
    
    async def write_option_legs_async(self, legs: List[OptionLegData], 
                                    write_json: bool = True) -> Dict[str, int]:
        """
        Write option legs to consolidated CSV files asynchronously.
        Returns statistics about writes performed.
        """
        if not legs:
            return {'legs_written': 0, 'files_updated': 0}
        
        # Group legs by file path
        file_groups: Dict[str, List[OptionLegData]] = {}
        json_data = []
        
        for leg in legs:
            date_str = self.time_utils.parse_csv_timestamp(leg.ts).date().isoformat()
            
            # Determine offset string
            if leg.strike_offset >= 0:
                offset_str = f"atm_p{leg.strike_offset}" if leg.strike_offset > 0 else "atm"
            else:
                offset_str = f"atm_m{abs(leg.strike_offset)}"
            
            file_path = self.get_consolidated_file_path(
                leg.index, leg.bucket, offset_str, date_str, "legs"
            )
            
            key = str(file_path)
            if key not in file_groups:
                file_groups[key] = []
            file_groups[key].append(leg)
            
            # Prepare JSON data if needed
            if write_json:
                json_data.append(leg.to_dict())
        
        # Write JSON snapshot asynchronously (audit trail)
        if write_json and json_data:
            await self._write_json_snapshot_async(json_data)
        
        # Write CSV files
        tasks = []
        for file_path, file_legs in file_groups.items():
            task = self._write_legs_to_file_async(Path(file_path), file_legs)
            tasks.append(task)
        
        # Execute all writes concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Aggregate results
        total_legs = 0
        files_updated = 0
        for result in results:
            if isinstance(result, dict):
                total_legs += result.get('legs_written', 0)
                files_updated += 1 if result.get('legs_written', 0) > 0 else 0
            elif isinstance(result, Exception):
                logger.error(f"Write task failed: {result}")
                self.stats['writes_failed'] += 1
        
        self.stats['writes_completed'] += files_updated
        return {'legs_written': total_legs, 'files_updated': files_updated}
    
    async def _write_legs_to_file_async(self, file_path: Path, legs: List[OptionLegData]) -> Dict[str, int]:
        """Write legs to a specific CSV file with incremental cursor tracking"""
        
        # Ensure directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Use Redis coordination to prevent file lock conflicts
        lock_name = f"csv_write_{hashlib.md5(str(file_path).encode()).hexdigest()}"
        
        try:
            with self.file_coordinator.coordinated_file_write(str(file_path)):
                # Check if file exists to determine if we need headers
                file_exists = file_path.exists()
                
                # Get current cursor position
                current_position = self.file_coordinator.get_incremental_cursor(str(file_path))
                
                # Open file for appending
                async with aiofiles.open(file_path, 'a', newline='', encoding='utf-8') as csvfile:
                    # Create CSV writer
                    fieldnames = list(OptionLegData.__dataclass_fields__.keys())
                    
                    # Write headers if new file
                    if not file_exists:
                        header_line = ','.join(fieldnames) + '\n'
                        await csvfile.write(header_line)
                    
                    # Write data rows
                    legs_written = 0
                    bytes_written = 0
                    
                    for leg in legs:
                        row_data = leg.to_dict()
                        # Ensure all fields are present
                        row_values = [str(row_data.get(field, '')) for field in fieldnames]
                        row_line = ','.join(row_values) + '\n'
                        
                        await csvfile.write(row_line)
                        legs_written += 1
                        bytes_written += len(row_line.encode('utf-8'))
                    
                    await csvfile.fsync()  # Force write to disk
                
                # Update cursor position
                new_position = current_position + bytes_written
                file_checksum = self._calculate_file_checksum(file_path)
                self.file_coordinator.update_incremental_cursor(str(file_path), new_position, file_checksum)
                
                self.stats['bytes_written'] += bytes_written
                self.stats['cursor_updates'] += 1
                
                logger.debug(f"Wrote {legs_written} legs to {file_path}")
                return {'legs_written': legs_written, 'bytes_written': bytes_written}
                
        except Exception as e:
            logger.error(f"Failed to write legs to {file_path}: {e}")
            self.stats['writes_failed'] += 1
            return {'legs_written': 0, 'bytes_written': 0}
    
    async def write_merged_data_async(self, merged_data: List[MergedOptionData]) -> Dict[str, int]:
        """Write merged CE+PE data to consolidated files"""
        if not merged_data:
            return {'records_written': 0, 'files_updated': 0}
        
        # Group by file path
        file_groups: Dict[str, List[MergedOptionData]] = {}
        
        for record in merged_data:
            date_str = self.time_utils.parse_csv_timestamp(record.ts).date().isoformat()
            
            # Determine offset string
            if record.strike_offset >= 0:
                offset_str = f"atm_p{record.strike_offset}" if record.strike_offset > 0 else "atm"
            else:
                offset_str = f"atm_m{abs(record.strike_offset)}"
            
            file_path = self.get_consolidated_file_path(
                record.index, record.bucket, offset_str, date_str, "merged"
            )
            
            key = str(file_path)
            if key not in file_groups:
                file_groups[key] = []
            file_groups[key].append(record)
        
        # Write files
        tasks = []
        for file_path, records in file_groups.items():
            task = self._write_merged_to_file_async(Path(file_path), records)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        total_records = 0
        files_updated = 0
        for result in results:
            if isinstance(result, dict):
                total_records += result.get('records_written', 0)
                files_updated += 1 if result.get('records_written', 0) > 0 else 0
            elif isinstance(result, Exception):
                logger.error(f"Merged write task failed: {result}")
                self.stats['writes_failed'] += 1
        
        return {'records_written': total_records, 'files_updated': files_updated}
    
    async def _write_merged_to_file_async(self, file_path: Path, records: List[MergedOptionData]) -> Dict[str, int]:
        """Write merged data to a specific file"""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        lock_name = f"csv_write_{hashlib.md5(str(file_path).encode()).hexdigest()}"
        
        try:
            with self.file_coordinator.coordinated_file_write(str(file_path)):
                file_exists = file_path.exists()
                
                async with aiofiles.open(file_path, 'a', newline='', encoding='utf-8') as csvfile:
                    fieldnames = list(MergedOptionData.__dataclass_fields__.keys())
                    
                    if not file_exists:
                        header_line = ','.join(fieldnames) + '\n'
                        await csvfile.write(header_line)
                    
                    records_written = 0
                    for record in records:
                        row_data = asdict(record)
                        row_values = [str(row_data.get(field, '')) for field in fieldnames]
                        row_line = ','.join(row_values) + '\n'
                        
                        await csvfile.write(row_line)
                        records_written += 1
                    
                    await csvfile.fsync()
                
                logger.debug(f"Wrote {records_written} merged records to {file_path}")
                return {'records_written': records_written}
                
        except Exception as e:
            logger.error(f"Failed to write merged data to {file_path}: {e}")
            return {'records_written': 0}
    
    async def _write_json_snapshot_async(self, data: List[Dict[str, Any]]) -> bool:
        """Write JSON snapshot for audit trail"""
        if not data:
            return True
        
        try:
            # Use first record to determine file path
            first_record = data[0]
            ts = first_record.get('ts', now_csv_format())
            index = first_record.get('index', 'UNKNOWN')
            bucket = first_record.get('bucket', 'unknown')
            
            date_str = self.time_utils.parse_csv_timestamp(ts).date().isoformat()
            json_path = self.get_json_snapshot_path(index, bucket, date_str, ts)
            
            json_path.parent.mkdir(parents=True, exist_ok=True)
            
            snapshot_data = {
                'timestamp': self.time_utils.get_metadata_timestamp(),
                'record_count': len(data),
                'data': data
            }
            
            async with aiofiles.open(json_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(snapshot_data, indent=2, ensure_ascii=False))
            
            # Compress if enabled
            if self.settings.data.compression_enabled:
                await self._compress_json_file_async(json_path)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to write JSON snapshot: {e}")
            return False
    
    def merge_legs_to_strikes(self, legs: List[OptionLegData]) -> List[MergedOptionData]:
        """
        Merge CALL and PUT legs into strike-based records.
        This consolidates the sidecar and daily split functionality.
        """
        # Group legs by key (index, bucket, expiry, strike_offset, minute)
        grouped_legs: Dict[tuple, Dict[str, OptionLegData]] = {}
        
        for leg in legs:
            # Round timestamp to minute for grouping
            dt = self.time_utils.parse_csv_timestamp(leg.ts)
            minute_ts = self.time_utils.format_time(
                self.time_utils.round_to_minute(dt), 
                TimeFormat.CSV_STANDARD
            )
            
            key = (leg.index, leg.bucket, leg.expiry, leg.strike_offset, minute_ts)
            
            if key not in grouped_legs:
                grouped_legs[key] = {}
            
            grouped_legs[key][leg.side] = leg
        
        # Create merged records
        merged_records = []
        for (index, bucket, expiry, strike_offset, ts), sides in grouped_legs.items():
            
            call_leg = sides.get('CALL')
            put_leg = sides.get('PUT')
            
            # Skip if we don't have at least one side
            if not call_leg and not put_leg:
                continue
            
            # Use the available leg for basic info
            ref_leg = call_leg or put_leg
            
            merged = MergedOptionData(
                ts=ts,
                index=index,
                bucket=bucket,
                expiry=expiry,
                strike_offset=strike_offset,
                atm_strike=ref_leg.atm_strike,
                strike=ref_leg.strike
            )
            
            # Fill CALL data
            if call_leg:
                merged.call_last_price = call_leg.last_price
                merged.call_bid = call_leg.bid
                merged.call_ask = call_leg.ask
                merged.call_volume = call_leg.volume
                merged.call_oi = call_leg.oi
                merged.call_iv = call_leg.iv
                merged.call_delta = call_leg.delta
                merged.call_gamma = call_leg.gamma
                merged.call_theta = call_leg.theta
                merged.call_vega = call_leg.vega
            
            # Fill PUT data
            if put_leg:
                merged.put_last_price = put_leg.last_price
                merged.put_bid = put_leg.bid
                merged.put_ask = put_leg.ask
                merged.put_volume = put_leg.volume
                merged.put_oi = put_leg.oi
                merged.put_iv = put_leg.iv
                merged.put_delta = put_leg.delta
                merged.put_gamma = put_leg.gamma
                merged.put_theta = put_leg.theta
                merged.put_vega = put_leg.vega
            
            # Compute derived fields (done in __post_init__)
            merged.__post_init__()
            merged_records.append(merged)
        
        return merged_records
    
    async def process_and_write(self, legs: List[OptionLegData], 
                              write_legs: bool = True, 
                              write_merged: bool = True,
                              write_json: bool = None) -> Dict[str, Any]:
        """
        Process option legs and write to appropriate files.
        This is the main entry point for consolidated writing.
        """
        if write_json is None:
            write_json = not self.settings.data.enable_archival  # Write JSON only if not archiving
        
        results = {
            'legs_written': 0,
            'merged_records': 0,
            'files_updated': 0,
            'json_written': False,
            'processing_time_ms': 0
        }
        
        start_time = time.time()
        
        try:
            # Write individual legs if requested
            if write_legs:
                legs_result = await self.write_option_legs_async(legs, write_json)
                results['legs_written'] = legs_result['legs_written']
                results['files_updated'] += legs_result['files_updated']
                results['json_written'] = write_json
            
            # Merge and write consolidated data if requested
            if write_merged:
                merged_data = self.merge_legs_to_strikes(legs)
                merged_result = await self.write_merged_data_async(merged_data)
                results['merged_records'] = merged_result['records_written']
                results['files_updated'] += merged_result['files_updated']
            
            results['processing_time_ms'] = int((time.time() - start_time) * 1000)
            logger.info(f"Processed {len(legs)} legs in {results['processing_time_ms']}ms")
            
        except Exception as e:
            logger.error(f"Failed to process and write legs: {e}")
            results['error'] = str(e)
        
        return results
    
    def read_file_incrementally(self, file_path: Path, 
                               cursor_position: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Read CSV file incrementally from cursor position.
        Returns new rows since last read.
        """
        if not file_path.exists():
            return []
        
        # Get cursor from Redis if not provided
        if cursor_position is None:
            cursor_position = self.file_coordinator.get_incremental_cursor(str(file_path))
        
        try:
            with self.file_coordinator.coordinated_file_read(str(file_path)):
                with open(file_path, 'r', newline='', encoding='utf-8') as f:
                    # Seek to cursor position
                    f.seek(cursor_position)
                    
                    # Read new content
                    content = f.read()
                    if not content:
                        return []
                    
                    # Parse new CSV rows
                    lines = content.strip().split('\n')
                    if not lines or (len(lines) == 1 and not lines[0]):
                        return []
                    
                    # Handle case where cursor is in middle of header row
                    csv_reader = csv.DictReader(lines)
                    rows = list(csv_reader)
                    
                    # Update cursor position
                    new_position = cursor_position + len(content.encode('utf-8'))
                    checksum = self._calculate_file_checksum(file_path)
                    self.file_coordinator.update_incremental_cursor(str(file_path), new_position, checksum)
                    
                    return rows
                    
        except Exception as e:
            logger.error(f"Failed to read file incrementally {file_path}: {e}")
            return []
    
    async def _compress_json_file_async(self, json_path: Path) -> bool:
        """Compress JSON file asynchronously"""
        try:
            compressed_path = json_path.with_suffix('.json.gz')
            
            with open(json_path, 'rb') as f_in:
                with gzip.open(compressed_path, 'wb') as f_out:
                    f_out.write(f_in.read())
            
            # Remove original if compression successful
            json_path.unlink()
            return True
            
        except Exception as e:
            logger.error(f"Failed to compress {json_path}: {e}")
            return False
    
    def _calculate_file_checksum(self, file_path: Path) -> str:
        """Calculate MD5 checksum of file for validation"""
        try:
            hash_md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception:
            return ""
    
    def get_stats(self) -> Dict[str, Any]:
        """Get writer statistics"""
        return dict(self.stats)
    
    def cleanup_old_files(self, days_old: int = None) -> Dict[str, int]:
        """Clean up old files according to archival policy"""
        if days_old is None:
            days_old = self.settings.data.archival_days
        
        if not self.settings.data.enable_archival:
            return {'files_archived': 0, 'files_deleted': 0}
        
        # Implementation of cleanup logic would go here
        # For now, return empty stats
        return {'files_archived': 0, 'files_deleted': 0}
    
    def __del__(self):
        """Cleanup resources"""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=True)

# Synchronous wrapper functions for backwards compatibility
class SyncCSVWriter:
    """Synchronous wrapper around ConsolidatedCSVWriter"""
    
    def __init__(self):
        self.async_writer = ConsolidatedCSVWriter()
        self.loop = None
    
    def _get_loop(self):
        """Get or create event loop"""
        if self.loop is None or self.loop.is_closed():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        return self.loop
    
    def write_option_legs(self, legs: List[OptionLegData], **kwargs) -> Dict[str, Any]:
        """Synchronous wrapper for writing option legs"""
        loop = self._get_loop()
        return loop.run_until_complete(
            self.async_writer.process_and_write(legs, **kwargs)
        )
    
    def read_incremental(self, file_path: Path, cursor_position: Optional[int] = None) -> List[Dict[str, Any]]:
        """Synchronous incremental reading"""
        return self.async_writer.read_file_incrementally(file_path, cursor_position)

# Global instances
consolidated_writer = ConsolidatedCSVWriter()
sync_writer = SyncCSVWriter()

def get_consolidated_writer() -> ConsolidatedCSVWriter:
    """Get the global consolidated CSV writer"""
    return consolidated_writer

def get_sync_writer() -> SyncCSVWriter:
    """Get the synchronous CSV writer wrapper"""
    return sync_writer