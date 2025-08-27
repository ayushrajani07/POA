"""
Market constants for the OP trading platform.
Centralized constants for indices, buckets, offsets, and market parameters.
"""

from typing import List, Dict, Any, Tuple
from datetime import time as dt_time

# Supported market indices
INDICES = ["NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY", "MIDCPNIFTY"]

# Option expiry buckets
BUCKETS = ["this_week", "next_week", "this_month", "next_month"]

# Strike offset ranges (relative to ATM)
STRIKE_OFFSETS = [-2, -1, 0, 1, 2]
EXTENDED_STRIKE_OFFSETS = [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5]

# Option sides
OPTION_SIDES = ["CALL", "PUT"]

# Market timing constants (IST)
MARKET_TIMINGS = {
    "pre_market_start": dt_time(9, 0),      # 09:00 AM IST
    "market_open": dt_time(9, 15),          # 09:15 AM IST
    "market_close": dt_time(15, 30),        # 03:30 PM IST
    "post_market_end": dt_time(16, 0),      # 04:00 PM IST
}

# Index specifications
INDEX_SPECS = {
    "NIFTY": {
        "full_name": "NIFTY 50",
        "exchange": "NSE",
        "symbol": "NIFTY",
        "base_symbol": "NIFTY",
        "instrument_type": "INDEX",
        "tick_size": 0.05,
        "lot_size": 25,
        "step_size": 50,
        "typical_range": (20000, 30000),
        "margin_multiple": 1.0
    },
    "BANKNIFTY": {
        "full_name": "NIFTY BANK",
        "exchange": "NSE",
        "symbol": "BANKNIFTY",
        "base_symbol": "BANKNIFTY",
        "instrument_type": "INDEX",
        "tick_size": 0.05,
        "lot_size": 15,
        "step_size": 100,
        "typical_range": (45000, 60000),
        "margin_multiple": 1.5
    },
    "SENSEX": {
        "full_name": "BSE SENSEX",
        "exchange": "BSE",
        "symbol": "SENSEX",
        "base_symbol": "SENSEX",
        "instrument_type": "INDEX",
        "tick_size": 0.05,
        "lot_size": 10,
        "step_size": 100,
        "typical_range": (75000, 90000),
        "margin_multiple": 1.2
    },
    "FINNIFTY": {
        "full_name": "NIFTY FINANCIAL SERVICES",
        "exchange": "NSE",
        "symbol": "FINNIFTY",
        "base_symbol": "FINNIFTY",
        "instrument_type": "INDEX",
        "tick_size": 0.05,
        "lot_size": 40,
        "step_size": 50,
        "typical_range": (18000, 25000),
        "margin_multiple": 1.3
    },
    "MIDCPNIFTY": {
        "full_name": "NIFTY MIDCAP SELECT",
        "exchange": "NSE",
        "symbol": "MIDCPNIFTY",
        "base_symbol": "MIDCPNIFTY",
        "instrument_type": "INDEX",
        "tick_size": 0.05,
        "lot_size": 75,
        "step_size": 25,
        "typical_range": (12000, 16000),
        "margin_multiple": 1.1
    }
}

# File naming patterns
FILE_PATTERNS = {
    "csv_legs": "{date}_{file_type}.csv",          # 2025-08-24_legs.csv
    "csv_merged": "{date}_{file_type}.csv",        # 2025-08-24_merged.csv
    "json_snapshot": "{minute_bucket}.json",       # 202508241430.json
    "analytics": "{date}_{analytics_type}.csv",    # 2025-08-24_weekday_agg.csv
}

# Directory structure patterns
DIRECTORY_PATTERNS = {
    "csv_data": "{index}/{bucket}/{offset}",              # NIFTY/this_week/atm
    "json_snapshots": "{index}/{bucket}/{date}",          # NIFTY/this_week/2025-08-24
    "analytics": "{analytics_type}/{index}/{period}",     # weekday_agg/NIFTY/daily
}

# Data validation constants
VALIDATION_LIMITS = {
    "price": {
        "min": 0.05,
        "max": 10000.0
    },
    "volume": {
        "min": 0,
        "max": 10000000
    },
    "oi": {
        "min": 0,
        "max": 100000000
    },
    "iv": {
        "min": 0.001,
        "max": 5.0
    },
    "delta": {
        "min": -1.0,
        "max": 1.0
    },
    "gamma": {
        "min": 0.0,
        "max": 1.0
    },
    "theta": {
        "min": -1000.0,
        "max": 10.0
    },
    "vega": {
        "min": 0.0,
        "max": 1000.0
    }
}

# CSV column definitions
CSV_COLUMNS = {
    "option_legs": [
        "ts", "index", "bucket", "expiry", "side", "atm_strike", "strike",
        "strike_offset", "last_price", "bid", "ask", "volume", "oi",
        "iv", "delta", "gamma", "theta", "vega"
    ],
    "merged_options": [
        "ts", "index", "bucket", "expiry", "strike_offset", "atm_strike", "strike",
        "call_last_price", "call_bid", "call_ask", "call_volume", "call_oi",
        "call_iv", "call_delta", "call_gamma", "call_theta", "call_vega",
        "put_last_price", "put_bid", "put_ask", "put_volume", "put_oi",
        "put_iv", "put_delta", "put_gamma", "put_theta", "put_vega",
        "total_premium", "total_volume", "total_oi", "put_call_ratio"
    ],
    "index_overview": [
        "ts", "index", "current_price", "change", "change_pct",
        "open", "high", "low", "close", "volume"
    ]
}

# Bucket time mappings (in days from current date)
BUCKET_TIME_MAPPING = {
    "this_week": (0, 7),      # 0 to 7 days
    "next_week": (7, 14),     # 7 to 14 days  
    "this_month": (14, 35),   # 2 to 5 weeks
    "next_month": (35, 65),   # 5 to 9 weeks
}

# Market holidays (would be loaded from external source in production)
MARKET_HOLIDAYS_2025 = [
    "2025-01-26",  # Republic Day
    "2025-03-14",  # Holi
    "2025-03-29",  # Good Friday
    "2025-04-14",  # Ram Navami
    "2025-05-01",  # Labour Day
    "2025-08-15",  # Independence Day
    "2025-09-07",  # Ganesh Chaturthi
    "2025-10-02",  # Gandhi Jayanti
    "2025-11-01",  # Diwali (Laxmi Puja)
    "2025-11-03",  # Diwali Balipratipada
    "2025-11-24",  # Guru Nanak Jayanti
    "2025-12-25",  # Christmas
]

# Trading session constants
TRADING_SESSIONS = {
    "regular": {
        "start": dt_time(9, 15),
        "end": dt_time(15, 30),
        "name": "Regular Trading Session"
    },
    "pre_market": {
        "start": dt_time(9, 0),
        "end": dt_time(9, 15),
        "name": "Pre-Market Session"
    },
    "post_market": {
        "start": dt_time(15, 30),
        "end": dt_time(16, 0),
        "name": "Post-Market Session"
    }
}

# Performance thresholds
PERFORMANCE_THRESHOLDS = {
    "collection": {
        "max_response_time_ms": 5000,
        "min_success_rate": 0.95,
        "max_error_rate": 0.05
    },
    "processing": {
        "max_processing_time_ms": 10000,
        "min_throughput_records_per_second": 1000,
        "max_memory_usage_mb": 2048
    },
    "storage": {
        "max_disk_usage_pct": 90,
        "min_available_space_gb": 5,
        "max_file_write_time_ms": 1000
    }
}

# Alert thresholds
ALERT_THRESHOLDS = {
    "data_freshness_minutes": 5,      # Alert if data is older than 5 minutes
    "processing_delay_minutes": 2,     # Alert if processing takes > 2 minutes
    "error_rate_threshold": 0.10,      # Alert if error rate > 10%
    "memory_usage_threshold": 0.85,    # Alert if memory usage > 85%
    "disk_usage_threshold": 0.90,      # Alert if disk usage > 90%
}

# API rate limits
API_RATE_LIMITS = {
    "kite": {
        "requests_per_second": 10,
        "requests_per_minute": 600,
        "concurrent_connections": 5
    },
    "internal": {
        "requests_per_second": 100,
        "concurrent_connections": 50
    }
}

# Caching settings
CACHE_SETTINGS = {
    "instruments": {
        "ttl_seconds": 3600,    # 1 hour
        "refresh_before_expiry_seconds": 300  # 5 minutes
    },
    "market_status": {
        "ttl_seconds": 60,      # 1 minute
        "refresh_before_expiry_seconds": 10
    },
    "quotes": {
        "ttl_seconds": 30,      # 30 seconds
        "refresh_before_expiry_seconds": 5
    }
}

# Database settings
DATABASE_SETTINGS = {
    "influxdb": {
        "measurement_names": {
            "option_quotes": "atm_option_quote",
            "index_data": "index_overview",
            "system_metrics": "system_metrics",
            "collection_stats": "collection_stats"
        },
        "tag_keys": ["index", "bucket", "side", "strike_offset"],
        "field_keys": ["last_price", "bid", "ask", "volume", "oi", "iv", "delta", "gamma", "theta", "vega"],
        "batch_size": 1000,
        "flush_interval_seconds": 10
    }
}

# File operation constants
FILE_OPERATIONS = {
    "csv_buffer_size": 8192,
    "json_buffer_size": 16384,
    "max_file_size_mb": 100,
    "compression_threshold_mb": 10,
    "backup_retention_days": 30
}

# Error codes
ERROR_CODES = {
    # Collection errors (1000-1999)
    "COLLECTION_BROKER_API_ERROR": 1001,
    "COLLECTION_INSTRUMENT_LOAD_ERROR": 1002,
    "COLLECTION_QUOTE_PARSE_ERROR": 1003,
    "COLLECTION_RATE_LIMIT_ERROR": 1004,
    
    # Processing errors (2000-2999) 
    "PROCESSING_CSV_WRITE_ERROR": 2001,
    "PROCESSING_JSON_WRITE_ERROR": 2002,
    "PROCESSING_DATA_VALIDATION_ERROR": 2003,
    "PROCESSING_FILE_LOCK_ERROR": 2004,
    
    # Analytics errors (3000-3999)
    "ANALYTICS_AGGREGATION_ERROR": 3001,
    "ANALYTICS_COMPUTATION_ERROR": 3002,
    "ANALYTICS_OUTPUT_ERROR": 3003,
    
    # System errors (4000-4999)
    "SYSTEM_REDIS_CONNECTION_ERROR": 4001,
    "SYSTEM_DATABASE_CONNECTION_ERROR": 4002,
    "SYSTEM_CONFIGURATION_ERROR": 4003,
    "SYSTEM_HEALTH_CHECK_ERROR": 4004,
}

# Status codes
STATUS_CODES = {
    "INITIALIZING": "Service is starting up",
    "RUNNING": "Service is running normally", 
    "IDLE": "Service is idle (market closed)",
    "WARNING": "Service has non-critical issues",
    "ERROR": "Service has critical errors",
    "STOPPED": "Service has been stopped",
    "MAINTENANCE": "Service is in maintenance mode"
}

# Log levels mapping
LOG_LEVELS = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50
}

# Default values
DEFAULTS = {
    "batch_size": 100,
    "max_workers": 8,
    "timeout_seconds": 30,
    "retry_attempts": 3,
    "retry_delay_seconds": 1.0,
}

# Utility functions for constants
def get_index_spec(index: str) -> Dict[str, Any]:
    """Get specification for an index"""
    return INDEX_SPECS.get(index.upper(), {})

def get_lot_size(index: str) -> int:
    """Get lot size for an index"""
    spec = get_index_spec(index)
    return spec.get("lot_size", 25)

def get_step_size(index: str) -> int:
    """Get step size for an index"""
    spec = get_index_spec(index)
    return spec.get("step_size", 50)

def get_tick_size(index: str) -> float:
    """Get tick size for an index"""
    spec = get_index_spec(index)
    return spec.get("tick_size", 0.05)

def is_valid_index(index: str) -> bool:
    """Check if index is supported"""
    return index.upper() in INDICES

def is_valid_bucket(bucket: str) -> bool:
    """Check if bucket is supported"""
    return bucket.lower() in BUCKETS

def is_valid_offset(offset: int) -> bool:
    """Check if offset is in supported range"""
    return offset in EXTENDED_STRIKE_OFFSETS

def get_csv_columns(file_type: str) -> List[str]:
    """Get CSV columns for a file type"""
    return CSV_COLUMNS.get(file_type, [])

def get_validation_limits(field: str) -> Dict[str, float]:
    """Get validation limits for a field"""
    return VALIDATION_LIMITS.get(field, {})

def get_directory_pattern(pattern_type: str) -> str:
    """Get directory pattern for a type"""
    return DIRECTORY_PATTERNS.get(pattern_type, "")

def get_file_pattern(pattern_type: str) -> str:
    """Get file naming pattern for a type"""
    return FILE_PATTERNS.get(pattern_type, "")