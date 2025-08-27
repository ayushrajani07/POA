"""
Type definitions for the OP trading platform.
Comprehensive data structures, enums, and type aliases for type safety.
"""

from typing import Dict, List, Any, Optional, Union, TypeVar, Generic, Callable
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from datetime import datetime, date, time as dt_time
import uuid
from decimal import Decimal

# Generic types
T = TypeVar('T')
K = TypeVar('K')
V = TypeVar('V')

# Basic type aliases
Price = float
Volume = int
OpenInterest = int
ImpliedVolatility = float
Greek = float
Timestamp = str
DateString = str
TimeString = str

# Enums
class MarketIndex(Enum):
    """Market indices enum"""
    NIFTY = "NIFTY"
    BANKNIFTY = "BANKNIFTY"
    SENSEX = "SENSEX"
    FINNIFTY = "FINNIFTY"
    MIDCPNIFTY = "MIDCPNIFTY"

class OptionSide(Enum):
    """Option side enum"""
    CALL = "CALL"
    PUT = "PUT"

class ExpiryBucket(Enum):
    """Expiry bucket enum"""
    THIS_WEEK = "this_week"
    NEXT_WEEK = "next_week" 
    THIS_MONTH = "this_month"
    NEXT_MONTH = "next_month"

class ServiceStatus(Enum):
    """Service status enum"""
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    IDLE = "IDLE"
    WARNING = "WARNING"
    ERROR = "ERROR"
    STOPPED = "STOPPED"
    MAINTENANCE = "MAINTENANCE"

class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"

class HealthStatus(Enum):
    """Health check status"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"

class ProcessingStatus(Enum):
    """Data processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

class FileType(Enum):
    """File type enum"""
    CSV_LEGS = "legs"
    CSV_MERGED = "merged"
    JSON_SNAPSHOT = "snapshot"
    ANALYTICS = "analytics"

# Data structures
@dataclass
class OptionLegData:
    """Individual option leg data structure"""
    ts: Timestamp                           # Standardized timestamp (IST format)
    index: str                             # Market index (NIFTY, BANKNIFTY, etc.)
    bucket: str                            # Expiry bucket (this_week, next_week, etc.)
    expiry: DateString                     # Expiry date (YYYY-MM-DD)
    side: str                              # Option side (CALL, PUT)
    atm_strike: Price                      # ATM strike price
    strike: Price                          # Actual strike price
    strike_offset: int                     # Offset from ATM (-2, -1, 0, 1, 2)
    last_price: Price                      # Last traded price
    bid: Optional[Price] = None            # Bid price
    ask: Optional[Price] = None            # Ask price
    volume: Optional[Volume] = None        # Trading volume
    oi: Optional[OpenInterest] = None      # Open interest
    iv: Optional[ImpliedVolatility] = None # Implied volatility
    delta: Optional[Greek] = None          # Delta
    gamma: Optional[Greek] = None          # Gamma
    theta: Optional[Greek] = None          # Theta
    vega: Optional[Greek] = None           # Vega
    
    def __post_init__(self):
        """Validate data after initialization"""
        if self.last_price < 0:
            raise ValueError("Last price cannot be negative")
        if self.bid is not None and self.bid < 0:
            raise ValueError("Bid price cannot be negative")
        if self.ask is not None and self.ask < 0:
            raise ValueError("Ask price cannot be negative")
        if self.volume is not None and self.volume < 0:
            raise ValueError("Volume cannot be negative")
        if self.oi is not None and self.oi < 0:
            raise ValueError("Open interest cannot be negative")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {k: v for k, v in self.__dict__.items()}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OptionLegData':
        """Create from dictionary"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

@dataclass
class MergedOptionData:
    """Merged CE+PE option data for a specific strike/offset"""
    ts: Timestamp
    index: str
    bucket: str
    expiry: DateString
    strike_offset: int
    atm_strike: Price
    strike: Price
    
    # CALL data
    call_last_price: Optional[Price] = None
    call_bid: Optional[Price] = None
    call_ask: Optional[Price] = None
    call_volume: Optional[Volume] = None
    call_oi: Optional[OpenInterest] = None
    call_iv: Optional[ImpliedVolatility] = None
    call_delta: Optional[Greek] = None
    call_gamma: Optional[Greek] = None
    call_theta: Optional[Greek] = None
    call_vega: Optional[Greek] = None
    
    # PUT data
    put_last_price: Optional[Price] = None
    put_bid: Optional[Price] = None
    put_ask: Optional[Price] = None
    put_volume: Optional[Volume] = None
    put_oi: Optional[OpenInterest] = None
    put_iv: Optional[ImpliedVolatility] = None
    put_delta: Optional[Greek] = None
    put_gamma: Optional[Greek] = None
    put_theta: Optional[Greek] = None
    put_vega: Optional[Greek] = None
    
    # Computed fields
    total_premium: Optional[Price] = None
    total_volume: Optional[Volume] = None
    total_oi: Optional[OpenInterest] = None
    put_call_ratio: Optional[float] = None
    
    def compute_derived_fields(self):
        """Compute derived fields from CALL/PUT data"""
        # Total premium
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
        
        # Put-call ratio
        if self.call_oi and self.call_oi > 0 and self.put_oi:
            self.put_call_ratio = self.put_oi / self.call_oi

@dataclass  
class IndexOverviewData:
    """Index overview/spot data"""
    ts: Timestamp
    index: str
    current_price: Price
    change: Price
    change_pct: float
    open: Optional[Price] = None
    high: Optional[Price] = None
    low: Optional[Price] = None
    close: Optional[Price] = None
    volume: Optional[Volume] = None

@dataclass
class InstrumentInfo:
    """Instrument metadata"""
    token: str
    tradingsymbol: str
    exchange: str
    name: str
    instrument_type: str
    segment: str
    exchange_token: Optional[str] = None
    expiry: Optional[DateString] = None
    strike: Optional[Price] = None
    tick_size: float = 0.05
    lot_size: int = 1

@dataclass
class BrokerQuote:
    """Broker API quote response"""
    instrument_token: str
    last_price: Price
    last_quantity: Optional[int] = None
    average_price: Optional[Price] = None
    volume: Optional[Volume] = None
    buy_quantity: Optional[int] = None
    sell_quantity: Optional[int] = None
    ohlc: Optional[Dict[str, Price]] = None
    oi: Optional[OpenInterest] = None
    oi_day_high: Optional[OpenInterest] = None
    oi_day_low: Optional[OpenInterest] = None
    timestamp: Optional[datetime] = None
    depth: Optional[Dict[str, List[Dict[str, Any]]]] = None

@dataclass
class CollectionResult:
    """Result of data collection operation"""
    success: bool
    legs_collected: int
    processing_time_ms: int = 0
    files_updated: int = 0
    error_message: Optional[str] = None
    collection_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)

@dataclass
class ProcessingResult:
    """Result of data processing operation"""
    success: bool
    records_processed: int
    records_written: int
    processing_time_ms: int = 0
    files_created: List[str] = field(default_factory=list)
    files_updated: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    operation_id: str = field(default_factory=lambda: str(uuid.uuid4()))

@dataclass
class AnalyticsResult:
    """Result of analytics computation"""
    success: bool
    computation_type: str
    records_analyzed: int
    output_records: int
    computation_time_ms: int = 0
    output_files: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None

@dataclass
class HealthMetric:
    """Individual health metric"""
    name: str
    value: float
    status: HealthStatus
    threshold_warning: float = 0
    threshold_critical: float = 0
    unit: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    message: str = ""

@dataclass
class ServiceHealth:
    """Service health status"""
    service_name: str
    status: ServiceStatus
    metrics: Dict[str, HealthMetric] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=datetime.utcnow)
    uptime_seconds: float = 0
    restart_count: int = 0
    error_count: int = 0
    last_error: str = ""
    version: str = "1.0.0"
    
    def is_healthy(self) -> bool:
        """Check if service is healthy"""
        return self.status in [ServiceStatus.RUNNING, ServiceStatus.IDLE]

@dataclass
class Alert:
    """System alert"""
    id: str
    service_name: str
    severity: AlertSeverity
    title: str
    description: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    acknowledged: bool = False
    resolved: bool = False
    auto_resolved: bool = False
    recovery_action: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class APIRequest:
    """API request structure"""
    endpoint: str
    method: str
    headers: Dict[str, str] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)
    body: Optional[Dict[str, Any]] = None
    timeout: int = 30
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))

@dataclass
class APIResponse:
    """API response structure"""
    status_code: int
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    message: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    processing_time_ms: int = 0
    request_id: Optional[str] = None

@dataclass
class ConfigurationUpdate:
    """Configuration update event"""
    component: str
    setting_name: str
    old_value: Any
    new_value: Any
    updated_by: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    requires_restart: bool = False

@dataclass
class PerformanceMetrics:
    """Performance monitoring metrics"""
    service_name: str
    timestamp: datetime
    cpu_usage_percent: float
    memory_usage_mb: float
    memory_usage_percent: float
    disk_usage_percent: float
    network_io_mb: float
    requests_per_second: float = 0
    error_rate: float = 0
    avg_response_time_ms: float = 0
    active_connections: int = 0

@dataclass
class DataQualityReport:
    """Data quality assessment report"""
    date: DateString
    total_records: int
    valid_records: int
    invalid_records: int
    missing_fields: Dict[str, int] = field(default_factory=dict)
    validation_errors: List[str] = field(default_factory=list)
    data_coverage_percent: float = 0.0
    quality_score: float = 0.0
    recommendations: List[str] = field(default_factory=list)

# Function type aliases
DataProcessor = Callable[[List[OptionLegData]], ProcessingResult]
DataValidator = Callable[[OptionLegData], bool]
ErrorHandler = Callable[[Exception], None]
EventHandler = Callable[[str, Dict[str, Any]], None]

# Generic data containers
@dataclass
class GenericResult(Generic[T]):
    """Generic result container"""
    success: bool
    data: Optional[T] = None
    error_message: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

@dataclass
class PaginatedResult(Generic[T]):
    """Paginated result container"""
    items: List[T]
    total_count: int
    page: int
    page_size: int
    has_next: bool
    has_previous: bool

# Configuration types
@dataclass
class DatabaseConfig:
    """Database configuration"""
    url: str
    username: str
    password: str
    database: str
    timeout: int = 30
    pool_size: int = 10
    ssl_enabled: bool = False

@dataclass
class RedisConfig:
    """Redis configuration"""
    host: str
    port: int
    db: int = 0
    password: Optional[str] = None
    timeout: float = 5.0
    max_connections: int = 100

@dataclass
class APIConfig:
    """API service configuration"""
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    timeout: int = 30
    max_request_size_mb: int = 10
    cors_enabled: bool = True
    rate_limiting: bool = True

# Market data specific types
StrikePrice = Decimal
ATMStrike = Decimal
StrikeOffset = int
ExpiryDate = date
OptionChain = Dict[StrikePrice, Dict[str, OptionLegData]]  # strike -> {CALL/PUT -> leg}
MarketQuote = Dict[str, BrokerQuote]  # instrument_token -> quote

# Time series types
TimeSeries = List[Tuple[datetime, float]]  # timestamp, value pairs
OHLC = Tuple[Price, Price, Price, Price]  # open, high, low, close
VolumeProfile = Dict[Price, Volume]  # price -> volume

# Analytics types
AggregationType = Enum('AggregationType', 'SUM AVG MIN MAX COUNT MEDIAN STD')
GroupByField = Enum('GroupByField', 'INDEX BUCKET SIDE OFFSET MINUTE HOUR DAY')

@dataclass
class AggregationConfig:
    """Configuration for data aggregation"""
    group_by: List[str]
    aggregations: Dict[str, str]  # field -> aggregation_type
    filters: Dict[str, Any] = field(default_factory=dict)
    time_range: Optional[Tuple[datetime, datetime]] = None

# Validation types
ValidationRule = Callable[[Any], bool]
ValidationContext = Dict[str, Any]

@dataclass
class ValidationError:
    """Data validation error"""
    field_name: str
    field_value: Any
    rule_name: str
    error_message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

# Event types
@dataclass
class SystemEvent:
    """System event"""
    event_type: str
    source: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

# Type guards and validators
def is_valid_price(price: Any) -> bool:
    """Check if value is a valid price"""
    try:
        return isinstance(price, (int, float)) and price >= 0
    except:
        return False

def is_valid_volume(volume: Any) -> bool:
    """Check if value is a valid volume"""
    try:
        return isinstance(volume, int) and volume >= 0
    except:
        return False

def is_valid_timestamp(timestamp: Any) -> bool:
    """Check if value is a valid timestamp"""
    try:
        if isinstance(timestamp, str):
            datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return True
        elif isinstance(timestamp, datetime):
            return True
        return False
    except:
        return False

# Factory functions
def create_option_leg(data: Dict[str, Any]) -> OptionLegData:
    """Factory function to create OptionLegData with validation"""
    try:
        return OptionLegData.from_dict(data)
    except Exception as e:
        raise ValueError(f"Invalid option leg data: {e}")

def create_collection_result(success: bool, legs_collected: int, **kwargs) -> CollectionResult:
    """Factory function to create CollectionResult"""
    return CollectionResult(
        success=success,
        legs_collected=legs_collected,
        **kwargs
    )

def create_health_metric(name: str, value: float, status: HealthStatus, **kwargs) -> HealthMetric:
    """Factory function to create HealthMetric"""
    return HealthMetric(
        name=name,
        value=value,
        status=status,
        **kwargs
    )