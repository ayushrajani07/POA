"""
Centralized configuration management for the OP trading platform.
Handles all environment variables, constants, and service configurations.
"""

import os
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path
import json
import yaml
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

@dataclass
class DatabaseConfig:
    """InfluxDB configuration"""
    url: str = field(default_factory=lambda: os.getenv("INFLUXDB_URL", "http://localhost:8086"))
    org: str = field(default_factory=lambda: os.getenv("INFLUXDB_ORG", "your-org"))
    bucket: str = field(default_factory=lambda: os.getenv("INFLUXDB_BUCKET", "your-bucket"))
    token: str = field(default_factory=lambda: os.getenv("INFLUXDB_TOKEN", ""))
    timeout: int = field(default_factory=lambda: int(os.getenv("INFLUXDB_TIMEOUT", "30")))
    retry_attempts: int = field(default_factory=lambda: int(os.getenv("INFLUXDB_RETRY_ATTEMPTS", "3")))
    batch_size: int = field(default_factory=lambda: int(os.getenv("INFLUXDB_BATCH_SIZE", "1000")))
    flush_interval: int = field(default_factory=lambda: int(os.getenv("INFLUXDB_FLUSH_INTERVAL", "10")))

@dataclass
class BrokerConfig:
    """Broker API configuration"""
    api_key: str = field(default_factory=lambda: os.getenv("KITE_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("KITE_API_SECRET", ""))
    access_token: str = field(default_factory=lambda: os.getenv("KITE_ACCESS_TOKEN", ""))
    request_timeout: int = field(default_factory=lambda: int(os.getenv("BROKER_REQUEST_TIMEOUT", "30")))
    max_retries: int = field(default_factory=lambda: int(os.getenv("BROKER_MAX_RETRIES", "3")))
    rate_limit_delay: float = field(default_factory=lambda: float(os.getenv("BROKER_RATE_LIMIT_DELAY", "0.25")))

@dataclass
class RedisConfig:
    """Redis configuration for coordination and caching"""
    host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    db: int = field(default_factory=lambda: int(os.getenv("REDIS_DB", "0")))
    password: Optional[str] = field(default_factory=lambda: os.getenv("REDIS_PASSWORD"))
    socket_timeout: float = field(default_factory=lambda: float(os.getenv("REDIS_SOCKET_TIMEOUT", "5.0")))
    retry_on_timeout: bool = field(default_factory=lambda: os.getenv("REDIS_RETRY_ON_TIMEOUT", "true").lower() == "true")

@dataclass
class MarketConfig:
    """Market session and timing configuration"""
    timezone: str = field(default_factory=lambda: os.getenv("MARKET_TIMEZONE", "Asia/Kolkata"))
    session_start: str = field(default_factory=lambda: os.getenv("SESSION_START_HHMM", "09:15"))
    session_end: str = field(default_factory=lambda: os.getenv("SESSION_END_HHMM", "15:30"))
    pre_market_start: str = field(default_factory=lambda: os.getenv("PRE_MARKET_START", "09:00"))
    post_market_end: str = field(default_factory=lambda: os.getenv("POST_MARKET_END", "16:00"))
    supported_indices: List[str] = field(default_factory=lambda: 
        os.getenv("SUPPORTED_INDICES", "NIFTY,BANKNIFTY,SENSEX").split(","))
    offsets: List[int] = field(default_factory=lambda: 
        [int(x) for x in os.getenv("LOGGER_OFFSETS", "-2,-1,0,1,2").split(",")])

@dataclass
class DataConfig:
    """Data storage and processing configuration"""
    # Storage paths
    base_data_dir: Path = field(default_factory=lambda: Path(os.getenv("BASE_DATA_DIR", "data")))
    csv_data_root: Path = field(default_factory=lambda: Path(os.getenv("CSV_DATA_ROOT", "data/csv_data")))
    json_snapshots_root: Path = field(default_factory=lambda: Path(os.getenv("JSON_SNAPSHOTS_ROOT", "data/raw_snapshots")))
    advanced_data_root: Path = field(default_factory=lambda: Path(os.getenv("ADVANCED_DATA_ROOT", "data_adv")))
    
    # Processing settings
    enable_archival: bool = field(default_factory=lambda: os.getenv("ENABLE_ARCHIVAL", "false").lower() == "true")
    archival_days: int = field(default_factory=lambda: int(os.getenv("ARCHIVAL_DAYS", "30")))
    compression_enabled: bool = field(default_factory=lambda: os.getenv("COMPRESSION_ENABLED", "false").lower() == "true")
    
    # Incremental processing
    enable_incremental: bool = field(default_factory=lambda: os.getenv("ENABLE_INCREMENTAL", "true").lower() == "true")
    cursor_storage_path: Path = field(default_factory=lambda: Path(os.getenv("CURSOR_STORAGE_PATH", "data/.cursors")))
    
    # Memory optimization
    max_memory_usage_mb: int = field(default_factory=lambda: int(os.getenv("MAX_MEMORY_USAGE_MB", "2048")))
    use_memory_mapping: bool = field(default_factory=lambda: os.getenv("USE_MEMORY_MAPPING", "true").lower() == "true")

@dataclass
class ServiceConfig:
    """Service-specific configuration"""
    # Collection service
    collection_loop_interval: int = field(default_factory=lambda: int(os.getenv("COLLECTION_LOOP_INTERVAL", "30")))
    collection_max_workers: int = field(default_factory=lambda: int(os.getenv("COLLECTION_MAX_WORKERS", "4")))
    
    # Processing service  
    processing_batch_size: int = field(default_factory=lambda: int(os.getenv("PROCESSING_BATCH_SIZE", "100")))
    processing_max_workers: int = field(default_factory=lambda: int(os.getenv("PROCESSING_MAX_WORKERS", "8")))
    
    # Analytics service
    analytics_streaming_enabled: bool = field(default_factory=lambda: os.getenv("ANALYTICS_STREAMING_ENABLED", "true").lower() == "true")
    analytics_eod_enabled: bool = field(default_factory=lambda: os.getenv("ANALYTICS_EOD_ENABLED", "true").lower() == "true")
    
    # API service
    api_host: str = field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))
    api_port: int = field(default_factory=lambda: int(os.getenv("API_PORT", "8000")))
    api_workers: int = field(default_factory=lambda: int(os.getenv("API_WORKERS", "4")))

@dataclass
class MonitoringConfig:
    """Health monitoring and alerting configuration"""
    health_check_interval: int = field(default_factory=lambda: int(os.getenv("HEALTH_CHECK_INTERVAL", "30")))
    alert_threshold_critical: int = field(default_factory=lambda: int(os.getenv("ALERT_THRESHOLD_CRITICAL", "5")))
    alert_threshold_warning: int = field(default_factory=lambda: int(os.getenv("ALERT_THRESHOLD_WARNING", "3")))
    
    # Self-healing settings
    auto_restart_enabled: bool = field(default_factory=lambda: os.getenv("AUTO_RESTART_ENABLED", "true").lower() == "true")
    max_restart_attempts: int = field(default_factory=lambda: int(os.getenv("MAX_RESTART_ATTEMPTS", "3")))
    restart_cooldown: int = field(default_factory=lambda: int(os.getenv("RESTART_COOLDOWN", "300")))
    
    # Performance monitoring
    track_memory_usage: bool = field(default_factory=lambda: os.getenv("TRACK_MEMORY_USAGE", "true").lower() == "true")
    track_cpu_usage: bool = field(default_factory=lambda: os.getenv("TRACK_CPU_USAGE", "true").lower() == "true")
    track_disk_usage: bool = field(default_factory=lambda: os.getenv("TRACK_DISK_USAGE", "true").lower() == "true")

@dataclass
class TestConfig:
    """Testing and development configuration"""
    test_mode: bool = field(default_factory=lambda: os.getenv("TEST_MODE", "false").lower() == "true")
    mock_data_enabled: bool = field(default_factory=lambda: os.getenv("MOCK_DATA_ENABLED", "false").lower() == "true")
    mock_data_path: Path = field(default_factory=lambda: Path(os.getenv("MOCK_DATA_PATH", "tests/fixtures/mock_data")))
    test_database_enabled: bool = field(default_factory=lambda: os.getenv("TEST_DATABASE_ENABLED", "false").lower() == "true")

class Settings:
    """Main settings class that aggregates all configuration"""
    
    def __init__(self):
        # Environment
        self.environment = os.getenv("ENV", "development")
        self.debug = os.getenv("DEBUG", "false").lower() == "true"
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        
        # Load all config sections
        self.database = DatabaseConfig()
        self.broker = BrokerConfig()
        self.redis = RedisConfig()
        self.market = MarketConfig()
        self.data = DataConfig()
        self.service = ServiceConfig()
        self.monitoring = MonitoringConfig()
        self.test = TestConfig()
        
        # Ensure required directories exist
        self._create_directories()
        
        # Validate configuration
        self._validate_config()
    
    def _create_directories(self):
        """Create required directories if they don't exist"""
        directories = [
            self.data.base_data_dir,
            self.data.csv_data_root,
            self.data.json_snapshots_root,
            self.data.advanced_data_root,
            self.data.cursor_storage_path,
            self.test.mock_data_path.parent,
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def _validate_config(self):
        """Validate critical configuration settings"""
        errors = []
        
        # Validate required settings for production
        if not self.test.test_mode:
            if not self.broker.api_key:
                errors.append("KITE_API_KEY is required for production")
            if not self.broker.api_secret:
                errors.append("KITE_API_SECRET is required for production")
            if not self.database.token:
                errors.append("INFLUXDB_TOKEN is required for production")
        
        # Validate data directories
        for path in [self.data.csv_data_root, self.data.json_snapshots_root]:
            if not path.exists() and not self.test.test_mode:
                errors.append(f"Data directory does not exist: {path}")
        
        if errors:
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary for serialization"""
        return {
            "environment": self.environment,
            "debug": self.debug,
            "log_level": self.log_level,
            "database": self.database.__dict__,
            "broker": self.broker.__dict__,
            "redis": self.redis.__dict__,
            "market": self.market.__dict__,
            "data": {k: str(v) if isinstance(v, Path) else v for k, v in self.data.__dict__.items()},
            "service": self.service.__dict__,
            "monitoring": self.monitoring.__dict__,
            "test": {k: str(v) if isinstance(v, Path) else v for k, v in self.test.__dict__.items()},
        }

# Global settings instance
settings = Settings()

def get_settings() -> Settings:
    """Get the global settings instance"""
    return settings

def reload_settings():
    """Reload settings from environment (useful for tests)"""
    global settings
    settings = Settings()
    return settings

def validate_startup_config():
    """Validate configuration at application startup"""
    try:
        settings._validate_config()
        logging.info(f"Configuration validated successfully for environment: {settings.environment}")
        return True
    except ValueError as e:
        logging.error(f"Configuration validation failed: {e}")
        return False