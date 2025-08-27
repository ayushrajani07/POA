"""
Standardized time utilities for the OP trading platform.
Handles IST for user interaction and UTC for background operations.
All CSV writers use 'ts' column standardized format.
"""

import pytz
import time
from datetime import datetime, date, time as dt_time, timezone
from typing import Optional, Union, Dict, Any
import logging
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Standard timezone objects
UTC = timezone.utc
IST = pytz.timezone('Asia/Kolkata')

class TimeFormat(Enum):
    """Standard time format types"""
    ISO_UTC = "iso_utc"          # 2025-08-24T14:30:00+00:00
    ISO_IST = "iso_ist"          # 2025-08-24T20:00:00+05:30
    DISPLAY_IST = "display_ist"  # 2025-08-24 20:00:00 IST
    CSV_STANDARD = "csv"         # 2025-08-24 20:00:00 (IST, for ts column)
    MINUTE_BUCKET = "minute"     # 20:00 (HH:MM for bucketing)
    DATE_ONLY = "date"          # 2025-08-24

@dataclass
class MarketSession:
    """Market session timing information"""
    pre_market_start: dt_time
    market_open: dt_time
    market_close: dt_time
    post_market_end: dt_time
    
    @classmethod
    def default_nse(cls) -> 'MarketSession':
        """Default NSE market session times"""
        return cls(
            pre_market_start=dt_time(9, 0),   # 09:00
            market_open=dt_time(9, 15),       # 09:15
            market_close=dt_time(15, 30),     # 15:30
            post_market_end=dt_time(16, 0)    # 16:00
        )

class TimeUtils:
    """Centralized time utilities with standardized formats"""
    
    def __init__(self, market_session: Optional[MarketSession] = None):
        self.market_session = market_session or MarketSession.default_nse()
    
    # Core time functions
    def now_utc(self) -> datetime:
        """Current UTC time"""
        return datetime.now(UTC)
    
    def now_ist(self) -> datetime:
        """Current IST time"""
        return datetime.now(IST)
    
    def utc_to_ist(self, utc_dt: datetime) -> datetime:
        """Convert UTC datetime to IST"""
        if utc_dt.tzinfo is None:
            utc_dt = utc_dt.replace(tzinfo=UTC)
        elif utc_dt.tzinfo != UTC:
            utc_dt = utc_dt.astimezone(UTC)
        
        return utc_dt.astimezone(IST)
    
    def ist_to_utc(self, ist_dt: datetime) -> datetime:
        """Convert IST datetime to UTC"""
        if ist_dt.tzinfo is None:
            ist_dt = IST.localize(ist_dt)
        elif ist_dt.tzinfo != IST:
            ist_dt = ist_dt.astimezone(IST)
        
        return ist_dt.astimezone(UTC)
    
    # Standard formatting functions
    def format_time(self, dt: datetime, format_type: TimeFormat) -> str:
        """Format datetime according to standard formats"""
        if dt.tzinfo is None:
            # Assume IST if no timezone info
            dt = IST.localize(dt)
        
        if format_type == TimeFormat.ISO_UTC:
            return dt.astimezone(UTC).isoformat()
        
        elif format_type == TimeFormat.ISO_IST:
            return dt.astimezone(IST).isoformat()
        
        elif format_type == TimeFormat.DISPLAY_IST:
            ist_dt = dt.astimezone(IST)
            return ist_dt.strftime("%Y-%m-%d %H:%M:%S IST")
        
        elif format_type == TimeFormat.CSV_STANDARD:
            # Standard 'ts' column format (IST without timezone suffix)
            ist_dt = dt.astimezone(IST)
            return ist_dt.strftime("%Y-%m-%d %H:%M:%S")
        
        elif format_type == TimeFormat.MINUTE_BUCKET:
            ist_dt = dt.astimezone(IST)
            return ist_dt.strftime("%H:%M")
        
        elif format_type == TimeFormat.DATE_ONLY:
            return dt.date().isoformat()
        
        else:
            raise ValueError(f"Unknown format type: {format_type}")
    
    def parse_time(self, time_str: str, format_type: TimeFormat) -> datetime:
        """Parse time string according to standard formats"""
        try:
            if format_type == TimeFormat.ISO_UTC:
                return datetime.fromisoformat(time_str.replace('Z', '+00:00'))
            
            elif format_type == TimeFormat.ISO_IST:
                return datetime.fromisoformat(time_str)
            
            elif format_type == TimeFormat.CSV_STANDARD:
                # Parse as IST without timezone
                dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                return IST.localize(dt)
            
            elif format_type == TimeFormat.DISPLAY_IST:
                # Remove IST suffix and parse
                clean_str = time_str.replace(" IST", "")
                dt = datetime.strptime(clean_str, "%Y-%m-%d %H:%M:%S")
                return IST.localize(dt)
            
            elif format_type == TimeFormat.DATE_ONLY:
                dt = datetime.strptime(time_str, "%Y-%m-%d")
                return IST.localize(dt)
            
            else:
                raise ValueError(f"Unknown format type: {format_type}")
                
        except Exception as e:
            logger.error(f"Failed to parse time '{time_str}' with format {format_type}: {e}")
            raise
    
    # Market timing functions
    def is_market_open(self, check_time: Optional[datetime] = None) -> bool:
        """Check if market is currently open"""
        if check_time is None:
            check_time = self.now_ist()
        else:
            check_time = check_time.astimezone(IST)
        
        # Check if it's a weekday (Monday = 0, Sunday = 6)
        if check_time.weekday() >= 5:  # Saturday or Sunday
            return False
        
        current_time = check_time.time()
        return self.market_session.market_open <= current_time <= self.market_session.market_close
    
    def is_pre_market(self, check_time: Optional[datetime] = None) -> bool:
        """Check if it's pre-market hours"""
        if check_time is None:
            check_time = self.now_ist()
        else:
            check_time = check_time.astimezone(IST)
        
        if check_time.weekday() >= 5:  # Weekend
            return False
        
        current_time = check_time.time()
        return self.market_session.pre_market_start <= current_time < self.market_session.market_open
    
    def is_post_market(self, check_time: Optional[datetime] = None) -> bool:
        """Check if it's post-market hours"""
        if check_time is None:
            check_time = self.now_ist()
        else:
            check_time = check_time.astimezone(IST)
        
        if check_time.weekday() >= 5:  # Weekend
            return False
        
        current_time = check_time.time()
        return self.market_session.market_close < current_time <= self.market_session.post_market_end
    
    def get_market_status(self, check_time: Optional[datetime] = None) -> str:
        """Get current market status string"""
        if check_time is None:
            check_time = self.now_ist()
        
        if check_time.weekday() >= 5:
            return "CLOSED_WEEKEND"
        
        if self.is_pre_market(check_time):
            return "PRE_MARKET"
        elif self.is_market_open(check_time):
            return "OPEN"
        elif self.is_post_market(check_time):
            return "POST_MARKET"
        else:
            return "CLOSED"
    
    def time_to_market_open(self, check_time: Optional[datetime] = None) -> Optional[int]:
        """Seconds until market opens (None if market is open or weekend)"""
        if check_time is None:
            check_time = self.now_ist()
        else:
            check_time = check_time.astimezone(IST)
        
        if check_time.weekday() >= 5:  # Weekend
            # Calculate time to next Monday
            days_to_monday = 7 - check_time.weekday()
            next_market_open = check_time.replace(
                hour=self.market_session.market_open.hour,
                minute=self.market_session.market_open.minute,
                second=0,
                microsecond=0
            ) + pytz.timedelta(days=days_to_monday)
        else:
            next_market_open = check_time.replace(
                hour=self.market_session.market_open.hour,
                minute=self.market_session.market_open.minute,
                second=0,
                microsecond=0
            )
            
            if check_time.time() >= self.market_session.market_open:
                # Market has already opened today, check next day
                next_market_open += pytz.timedelta(days=1)
                if next_market_open.weekday() >= 5:  # If it's weekend, go to Monday
                    days_to_monday = 7 - next_market_open.weekday()
                    next_market_open += pytz.timedelta(days=days_to_monday)
        
        if self.is_market_open(check_time):
            return None  # Market is already open
        
        return int((next_market_open - check_time).total_seconds())
    
    def wait_until_market_open(self, max_wait_seconds: int = 28800):  # 8 hours default
        """Block until market opens (with timeout)"""
        wait_seconds = self.time_to_market_open()
        if wait_seconds is None:
            return  # Already open
        
        if wait_seconds > max_wait_seconds:
            logger.warning(f"Market opens in {wait_seconds}s, exceeding max wait of {max_wait_seconds}s")
            return
        
        logger.info(f"Waiting {wait_seconds} seconds for market to open")
        time.sleep(wait_seconds)
    
    # Bucketing and aggregation functions
    def bucket_to_minute(self, dt: datetime) -> str:
        """Convert datetime to HH:MM minute bucket (IST)"""
        return self.format_time(dt, TimeFormat.MINUTE_BUCKET)
    
    def get_minute_buckets_for_session(self, date_: date) -> list[str]:
        """Get all minute buckets for a trading session"""
        session_start = IST.localize(datetime.combine(date_, self.market_session.market_open))
        session_end = IST.localize(datetime.combine(date_, self.market_session.market_close))
        
        buckets = []
        current = session_start
        while current <= session_end:
            buckets.append(self.bucket_to_minute(current))
            current += pytz.timedelta(minutes=1)
        
        return buckets
    
    def round_to_minute(self, dt: datetime) -> datetime:
        """Round datetime down to the minute"""
        return dt.replace(second=0, microsecond=0)
    
    # CSV timestamp standardization
    def get_csv_timestamp(self, dt: Optional[datetime] = None) -> str:
        """Get standardized CSV timestamp (IST, for 'ts' column)"""
        if dt is None:
            dt = self.now_ist()
        return self.format_time(dt, TimeFormat.CSV_STANDARD)
    
    def get_metadata_timestamp(self, dt: Optional[datetime] = None) -> str:
        """Get standardized metadata timestamp (UTC ISO)"""
        if dt is None:
            dt = self.now_utc()
        return self.format_time(dt, TimeFormat.ISO_UTC)
    
    def parse_csv_timestamp(self, ts_str: str) -> datetime:
        """Parse standardized CSV timestamp"""
        return self.parse_time(ts_str, TimeFormat.CSV_STANDARD)
    
    # Date utilities
    def get_current_date_ist(self) -> date:
        """Get current date in IST"""
        return self.now_ist().date()
    
    def get_weekday_name(self, dt: datetime) -> str:
        """Get weekday name (Monday, Tuesday, etc.)"""
        return dt.astimezone(IST).strftime("%A").lower()
    
    def get_date_range(self, start_date: date, end_date: date) -> list[date]:
        """Get list of dates in range (inclusive)"""
        dates = []
        current = start_date
        while current <= end_date:
            dates.append(current)
            current += pytz.timedelta(days=1)
        return dates
    
    def get_trading_days(self, start_date: date, end_date: date) -> list[date]:
        """Get trading days (excluding weekends) in date range"""
        dates = self.get_date_range(start_date, end_date)
        return [d for d in dates if d.weekday() < 5]  # Monday=0, Friday=4

# Global time utilities instance
time_utils = TimeUtils()

def get_time_utils() -> TimeUtils:
    """Get the global time utilities instance"""
    return time_utils

# Convenience functions for common operations
def now_csv_format() -> str:
    """Current time in CSV format (IST)"""
    return time_utils.get_csv_timestamp()

def now_metadata_format() -> str:
    """Current time in metadata format (UTC)"""
    return time_utils.get_metadata_timestamp()

def ist_now() -> datetime:
    """Current IST time"""
    return time_utils.now_ist()

def utc_now() -> datetime:
    """Current UTC time"""
    return time_utils.now_utc()

def is_market_open() -> bool:
    """Check if market is currently open"""
    return time_utils.is_market_open()

def get_market_status() -> str:
    """Get current market status"""
    return time_utils.get_market_status()

def csv_to_display(csv_timestamp: str) -> str:
    """Convert CSV timestamp to display format"""
    dt = time_utils.parse_csv_timestamp(csv_timestamp)
    return time_utils.format_time(dt, TimeFormat.DISPLAY_IST)

def minute_bucket(dt: datetime) -> str:
    """Get minute bucket for datetime"""
    return time_utils.bucket_to_minute(dt)

# Legacy timestamp migration utilities
def standardize_timestamp_column(timestamp_value: Union[str, datetime, float]) -> str:
    """
    Standardize various timestamp formats to CSV standard.
    Handles migration from ts_ist, timestamp columns to standard 'ts'.
    """
    try:
        if isinstance(timestamp_value, str):
            # Try different parsing strategies
            if 'T' in timestamp_value and ('+' in timestamp_value or 'Z' in timestamp_value):
                # ISO format with timezone
                dt = datetime.fromisoformat(timestamp_value.replace('Z', '+00:00'))
                return time_utils.format_time(dt, TimeFormat.CSV_STANDARD)
            
            elif len(timestamp_value) == 19 and timestamp_value.count(':') == 2:
                # Assume "YYYY-MM-DD HH:MM:SS" format in IST
                return timestamp_value  # Already in correct format
            
            else:
                # Try to parse as ISO format
                dt = datetime.fromisoformat(timestamp_value)
                return time_utils.format_time(dt, TimeFormat.CSV_STANDARD)
        
        elif isinstance(timestamp_value, datetime):
            return time_utils.format_time(timestamp_value, TimeFormat.CSV_STANDARD)
        
        elif isinstance(timestamp_value, (int, float)):
            # Unix timestamp
            dt = datetime.fromtimestamp(timestamp_value, tz=IST)
            return time_utils.format_time(dt, TimeFormat.CSV_STANDARD)
        
        else:
            raise ValueError(f"Unsupported timestamp type: {type(timestamp_value)}")
            
    except Exception as e:
        logger.error(f"Failed to standardize timestamp '{timestamp_value}': {e}")
        # Return current time as fallback
        return now_csv_format()

# Validation functions
def validate_csv_timestamp(ts_str: str) -> bool:
    """Validate that timestamp string is in correct CSV format"""
    try:
        time_utils.parse_csv_timestamp(ts_str)
        return True
    except Exception:
        return False

def detect_timestamp_format(ts_str: str) -> Optional[TimeFormat]:
    """Detect the format of a timestamp string"""
    formats_to_try = [
        TimeFormat.CSV_STANDARD,
        TimeFormat.ISO_UTC,
        TimeFormat.ISO_IST,
        TimeFormat.DISPLAY_IST
    ]
    
    for fmt in formats_to_try:
        try:
            time_utils.parse_time(ts_str, fmt)
            return fmt
        except Exception:
            continue
    
    return None