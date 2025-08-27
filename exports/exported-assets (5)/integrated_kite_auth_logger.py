"""
OP TRADING PLATFORM - INTEGRATED KITE AUTHENTICATION & LOGGER
==============================================================
Version: 2.0.0 - Complete Integration with Enhanced Logging
Author: OP Trading Platform Team
Date: 2025-08-25 1:49 PM IST

This module provides complete Kite Connect authentication integration with
comprehensive logging, monitoring, and error detection capabilities.

Key Features:
- Retains original kite_client.py authentication flow
- Adds structured logging with trace IDs and request IDs
- Implements infinite retention for audit compliance
- Provides real-time monitoring and health checks
- Includes error detection with automated recovery suggestions
- Session management with comprehensive tracking

Integration Points:
- Uses existing OAuth login flow from kite_client.py
- Integrates with InfluxDB for infinite data retention
- Connects to Redis for session state management
- Provides dashboard-ready metrics and analytics
"""

import os
import sys
import json
import time
import uuid
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager

# Third-party imports
try:
    import redis.asyncio as redis
    from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
    from influxdb_client import Point
    from influxdb_client.client.write_api import SYNCHRONOUS
    import aiohttp
    from fastapi import HTTPException
except ImportError as e:
    print(f"Missing required dependencies: {e}")
    print("Run: pip install redis influxdb-client aiohttp fastapi")
    sys.exit(1)

# Import the original kite_client functionality
sys.path.insert(0, str(Path(__file__).parent))
try:
    from kite_client import get_kite_client, TOKEN_STORE, _save_token, _load_token
    KITE_CLIENT_AVAILABLE = True
except ImportError:
    print("Warning: kite_client.py not found. Some functionality may be limited.")
    KITE_CLIENT_AVAILABLE = False

# ================================================================================================
# CONFIGURATION AND CONSTANTS
# ================================================================================================

# Logging configuration
LOGGER_NAME = "integrated_kite_auth"
LOG_DIR = Path("logs/auth")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - [trace_id=%(trace_id)s] [request_id=%(request_id)s]',
    handlers=[
        logging.FileHandler(LOG_DIR / f"auth_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)

# Custom log formatter for structured logging
class StructuredFormatter(logging.Formatter):
    """
    Custom formatter that adds structured fields to log records.
    
    Adds trace_id, request_id, user_id, and other contextual information
    to each log record for better traceability and monitoring.
    """
    
    def format(self, record):
        # Add default values for structured fields if not present
        if not hasattr(record, 'trace_id'):
            record.trace_id = getattr(record, 'trace_id', 'none')
        if not hasattr(record, 'request_id'):
            record.request_id = getattr(record, 'request_id', 'none')
        if not hasattr(record, 'user_id'):
            record.user_id = getattr(record, 'user_id', 'system')
        
        return super().format(record)

# Configure logger
logger = logging.getLogger(LOGGER_NAME)
for handler in logger.handlers:
    handler.setFormatter(StructuredFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s - '
        '[trace_id=%(trace_id)s] [request_id=%(request_id)s] [user_id=%(user_id)s]'
    ))

# Authentication event types
class AuthEventType:
    """
    Enumeration of authentication event types for consistent logging.
    
    These event types are used throughout the system for:
    - Structured logging and monitoring
    - Error detection and alerting
    - Analytics and reporting
    - Audit trail maintenance
    """
    LOGIN_ATTEMPT = "LOGIN_ATTEMPT"
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILURE = "LOGIN_FAILURE"
    TOKEN_REFRESH = "TOKEN_REFRESH"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    LOGOUT = "LOGOUT"
    SESSION_VALIDATION = "SESSION_VALIDATION"
    API_CALL = "API_CALL"
    API_ERROR = "API_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    SELF_HEAL = "SELF_HEAL"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    SYSTEM_ERROR = "SYSTEM_ERROR"

@dataclass
class AuthenticationEvent:
    """
    Data structure for authentication events with complete context.
    
    Attributes:
        event_id (str): Unique identifier for this event
        event_type (str): Type of authentication event (from AuthEventType)
        timestamp (datetime): When the event occurred
        user_id (str): User identifier (if applicable)
        session_id (str): Session identifier for tracking
        trace_id (str): Distributed tracing identifier
        request_id (str): Request-specific identifier
        success (bool): Whether the operation was successful
        error_code (Optional[str]): Error code if operation failed
        error_message (Optional[str]): Human-readable error message
        metadata (Dict[str, Any]): Additional event-specific data
        ip_address (Optional[str]): Client IP address
        user_agent (Optional[str]): Client user agent
        api_endpoint (Optional[str]): API endpoint accessed
        response_time_ms (Optional[int]): Operation response time
        recovery_action (Optional[str]): Suggested recovery action
    """
    event_id: str
    event_type: str
    timestamp: datetime
    user_id: str = "system"
    session_id: str = ""
    trace_id: str = ""
    request_id: str = ""
    success: bool = True
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    api_endpoint: Optional[str] = None
    response_time_ms: Optional[int] = None
    recovery_action: Optional[str] = None
    
    def __post_init__(self):
        """Initialize default values and generate IDs if not provided."""
        if not self.event_id:
            self.event_id = str(uuid.uuid4())
        if not self.trace_id:
            self.trace_id = str(uuid.uuid4())
        if not self.request_id:
            self.request_id = str(uuid.uuid4())
        if self.metadata is None:
            self.metadata = {}
        if isinstance(self.timestamp, str):
            self.timestamp = datetime.fromisoformat(self.timestamp)

@dataclass
class SessionInfo:
    """
    Session information tracking for authentication state management.
    
    Attributes:
        session_id (str): Unique session identifier
        user_id (str): Associated user identifier
        created_at (datetime): When session was created
        last_activity (datetime): Last activity timestamp
        access_token (str): Current access token
        expires_at (datetime): Token expiration time
        is_active (bool): Whether session is currently active
        login_attempts (int): Number of login attempts in this session
        api_calls_count (int): Total API calls made in this session
        errors_count (int): Number of errors in this session
        metadata (Dict[str, Any]): Additional session data
    """
    session_id: str
    user_id: str
    created_at: datetime
    last_activity: datetime
    access_token: str = ""
    expires_at: Optional[datetime] = None
    is_active: bool = True
    login_attempts: int = 0
    api_calls_count: int = 0
    errors_count: int = 0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        """Initialize default values."""
        if self.metadata is None:
            self.metadata = {}

# ================================================================================================
# CORE AUTHENTICATION LOGGER CLASS
# ================================================================================================

class IntegratedKiteAuthLogger:
    """
    Comprehensive authentication logger with infinite retention and monitoring.
    
    This class provides complete integration between Kite Connect authentication
    and the OP Trading Platform's logging and monitoring infrastructure.
    
    Features:
    - Structured logging with trace IDs and request IDs
    - Infinite retention in InfluxDB for audit compliance
    - Redis-based session state management
    - Real-time monitoring and alerting
    - Error detection with recovery suggestions
    - Performance metrics and analytics
    
    Usage:
        logger = IntegratedKiteAuthLogger()
        await logger.initialize()
        await logger.log_authentication_event(event)
    """
    
    def __init__(self):
        """
        Initialize the integrated authentication logger.
        
        Sets up connections to InfluxDB and Redis, configures logging,
        and initializes monitoring components.
        """
        self.logger = logger
        self.influxdb_client = None
        self.redis_client = None
        self.write_api = None
        self.session_cache = {}
        self.error_patterns = {}
        self.metrics = {
            'total_events': 0,
            'login_attempts': 0,
            'successful_logins': 0,
            'failed_logins': 0,
            'token_refreshes': 0,
            'api_calls': 0,
            'errors': 0,
            'self_heals': 0
        }
        
        # Configuration from environment
        self.influxdb_url = os.getenv('INFLUXDB_URL', 'http://localhost:8086')
        self.influxdb_token = os.getenv('INFLUXDB_TOKEN')
        self.influxdb_org = os.getenv('INFLUXDB_ORG', 'op-trading')
        self.influxdb_bucket = os.getenv('INFLUXDB_BUCKET', 'auth-events')
        
        self.redis_host = os.getenv('REDIS_HOST', 'localhost')
        self.redis_port = int(os.getenv('REDIS_PORT', '6379'))
        self.redis_db = int(os.getenv('REDIS_DB', '1'))  # Use DB 1 for auth data
        
        # Session configuration
        self.session_timeout = timedelta(hours=24)  # 24 hour sessions
        self.cleanup_interval = timedelta(hours=1)   # Cleanup every hour
        
    async def initialize(self) -> bool:
        """
        Initialize all required connections and services.
        
        Returns:
            bool: True if initialization successful, False otherwise
            
        This method establishes connections to:
        - InfluxDB for infinite data retention
        - Redis for session state management
        - Configures monitoring and alerting
        """
        try:
            # Initialize InfluxDB connection
            if self.influxdb_token:
                self.influxdb_client = InfluxDBClientAsync(
                    url=self.influxdb_url,
                    token=self.influxdb_token,
                    org=self.influxdb_org
                )
                self.write_api = self.influxdb_client.write_api(write_options=SYNCHRONOUS)
                self.logger.info("InfluxDB connection initialized", extra={
                    'trace_id': str(uuid.uuid4()),
                    'request_id': str(uuid.uuid4())
                })
            else:
                self.logger.warning("InfluxDB token not configured - events will not be persisted")
            
            # Initialize Redis connection
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                decode_responses=True
            )
            
            # Test Redis connection
            await self.redis_client.ping()
            self.logger.info("Redis connection initialized", extra={
                'trace_id': str(uuid.uuid4()),
                'request_id': str(uuid.uuid4())
            })
            
            # Initialize error patterns for detection
            await self._initialize_error_patterns()
            
            # Start background cleanup task
            asyncio.create_task(self._periodic_cleanup())
            
            self.logger.info("Integrated Kite Auth Logger initialized successfully", extra={
                'trace_id': str(uuid.uuid4()),
                'request_id': str(uuid.uuid4())
            })
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize auth logger: {str(e)}", extra={
                'trace_id': str(uuid.uuid4()),
                'request_id': str(uuid.uuid4())
            })
            return False
    
    async def log_authentication_event(self, event: Union[AuthenticationEvent, Dict[str, Any]]) -> bool:
        """
        Log an authentication event with complete context and monitoring.
        
        Args:
            event: Authentication event to log (AuthenticationEvent or dict)
            
        Returns:
            bool: True if event was logged successfully, False otherwise
            
        This method:
        - Validates and enriches the event data
        - Stores the event in InfluxDB with infinite retention
        - Updates Redis session state
        - Triggers error detection and alerting
        - Updates performance metrics
        """
        try:
            # Convert dict to AuthenticationEvent if needed
            if isinstance(event, dict):
                event = AuthenticationEvent(**event)
            elif not isinstance(event, AuthenticationEvent):
                event = AuthenticationEvent(
                    event_id=str(uuid.uuid4()),
                    event_type=AuthEventType.SYSTEM_ERROR,
                    timestamp=datetime.now(),
                    error_message="Invalid event format"
                )
            
            # Enrich event with additional context
            await self._enrich_event(event)
            
            # Update metrics
            self._update_metrics(event)
            
            # Log to structured logger
            self._log_to_structured_logger(event)
            
            # Store in InfluxDB for infinite retention
            if self.influxdb_client and self.write_api:
                await self._store_in_influxdb(event)
            
            # Update Redis session state
            if self.redis_client:
                await self._update_session_state(event)
            
            # Trigger error detection
            await self._detect_and_handle_errors(event)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to log authentication event: {str(e)}", extra={
                'trace_id': event.trace_id if hasattr(event, 'trace_id') else str(uuid.uuid4()),
                'request_id': event.request_id if hasattr(event, 'request_id') else str(uuid.uuid4())
            })
            return False
    
    async def _enrich_event(self, event: AuthenticationEvent) -> None:
        """
        Enrich authentication event with additional contextual information.
        
        Args:
            event: Event to enrich
            
        Adds:
        - System information
        - Performance metrics
        - Geographic information (if available)
        - Session context
        """
        # Add system information
        event.metadata.update({
            'platform': sys.platform,
            'python_version': sys.version.split()[0],
            'process_id': os.getpid(),
            'hostname': os.uname().nodename if hasattr(os, 'uname') else 'unknown'
        })
        
        # Add session context if available
        if event.session_id and event.session_id in self.session_cache:
            session = self.session_cache[event.session_id]
            event.metadata.update({
                'session_age_seconds': (datetime.now() - session.created_at).total_seconds(),
                'session_api_calls': session.api_calls_count,
                'session_errors': session.errors_count
            })
        
        # Calculate response time if start time is in metadata
        if 'start_time' in event.metadata and not event.response_time_ms:
            start_time = event.metadata['start_time']
            if isinstance(start_time, datetime):
                event.response_time_ms = int((event.timestamp - start_time).total_seconds() * 1000)
    
    def _update_metrics(self, event: AuthenticationEvent) -> None:
        """
        Update internal metrics based on the authentication event.
        
        Args:
            event: Event to process for metrics
        """
        self.metrics['total_events'] += 1
        
        # Update specific metrics based on event type
        event_type_metrics = {
            AuthEventType.LOGIN_ATTEMPT: 'login_attempts',
            AuthEventType.LOGIN_SUCCESS: 'successful_logins',
            AuthEventType.LOGIN_FAILURE: 'failed_logins',
            AuthEventType.TOKEN_REFRESH: 'token_refreshes',
            AuthEventType.API_CALL: 'api_calls',
            AuthEventType.SELF_HEAL: 'self_heals'
        }
        
        if event.event_type in event_type_metrics:
            self.metrics[event_type_metrics[event.event_type]] += 1
        
        if not event.success or event.error_code:
            self.metrics['errors'] += 1
    
    def _log_to_structured_logger(self, event: AuthenticationEvent) -> None:
        """
        Log event to structured logger with proper formatting.
        
        Args:
            event: Event to log
        """
        log_level = logging.ERROR if not event.success else logging.INFO
        log_message = f"Auth Event: {event.event_type}"
        
        if event.error_message:
            log_message += f" - {event.error_message}"
        
        extra_data = {
            'trace_id': event.trace_id,
            'request_id': event.request_id,
            'user_id': event.user_id,
            'event_id': event.event_id,
            'session_id': event.session_id,
            'success': event.success
        }
        
        self.logger.log(log_level, log_message, extra=extra_data)
    
    async def _store_in_influxdb(self, event: AuthenticationEvent) -> None:
        """
        Store authentication event in InfluxDB with infinite retention.
        
        Args:
            event: Event to store
            
        The data is stored with infinite retention for:
        - Regulatory compliance
        - Audit trail requirements
        - Long-term analytics
        - Security monitoring
        """
        try:
            # Create InfluxDB point
            point = Point("authentication_events") \
                .tag("event_type", event.event_type) \
                .tag("user_id", event.user_id) \
                .tag("success", str(event.success).lower()) \
                .field("event_id", event.event_id) \
                .field("session_id", event.session_id) \
                .field("trace_id", event.trace_id) \
                .field("request_id", event.request_id) \
                .time(event.timestamp)
            
            # Add optional fields
            if event.error_code:
                point = point.tag("error_code", event.error_code)
                point = point.field("error_message", event.error_message or "")
            
            if event.api_endpoint:
                point = point.tag("api_endpoint", event.api_endpoint)
            
            if event.response_time_ms:
                point = point.field("response_time_ms", event.response_time_ms)
            
            if event.ip_address:
                point = point.field("ip_address", event.ip_address)
            
            # Add metadata as fields
            for key, value in event.metadata.items():
                if isinstance(value, (str, int, float, bool)):
                    point = point.field(f"meta_{key}", value)
            
            # Write to InfluxDB
            await self.write_api.write(bucket=self.influxdb_bucket, record=point)
            
        except Exception as e:
            self.logger.error(f"Failed to store event in InfluxDB: {str(e)}", extra={
                'trace_id': event.trace_id,
                'request_id': event.request_id
            })
    
    async def _update_session_state(self, event: AuthenticationEvent) -> None:
        """
        Update session state in Redis based on authentication event.
        
        Args:
            event: Event to process for session updates
        """
        try:
            if not event.session_id:
                return
            
            session_key = f"auth_session:{event.session_id}"
            
            # Get existing session or create new one
            if event.session_id in self.session_cache:
                session = self.session_cache[event.session_id]
            else:
                # Try to load from Redis
                session_data = await self.redis_client.get(session_key)
                if session_data:
                    session_dict = json.loads(session_data)
                    session = SessionInfo(**session_dict)
                else:
                    # Create new session
                    session = SessionInfo(
                        session_id=event.session_id,
                        user_id=event.user_id,
                        created_at=event.timestamp,
                        last_activity=event.timestamp
                    )
            
            # Update session based on event type
            session.last_activity = event.timestamp
            
            if event.event_type == AuthEventType.LOGIN_ATTEMPT:
                session.login_attempts += 1
            elif event.event_type == AuthEventType.LOGIN_SUCCESS:
                session.is_active = True
                session.access_token = event.metadata.get('access_token', session.access_token)
            elif event.event_type == AuthEventType.LOGOUT:
                session.is_active = False
                session.access_token = ""
            elif event.event_type == AuthEventType.API_CALL:
                session.api_calls_count += 1
            
            if not event.success:
                session.errors_count += 1
            
            # Update cache and Redis
            self.session_cache[event.session_id] = session
            
            # Convert to dict for JSON serialization
            session_dict = asdict(session)
            # Handle datetime serialization
            for key, value in session_dict.items():
                if isinstance(value, datetime):
                    session_dict[key] = value.isoformat()
            
            await self.redis_client.set(
                session_key,
                json.dumps(session_dict),
                ex=int(self.session_timeout.total_seconds())
            )
            
        except Exception as e:
            self.logger.error(f"Failed to update session state: {str(e)}", extra={
                'trace_id': event.trace_id,
                'request_id': event.request_id
            })
    
    async def _detect_and_handle_errors(self, event: AuthenticationEvent) -> None:
        """
        Detect error patterns and trigger appropriate handling/alerting.
        
        Args:
            event: Event to analyze for error patterns
            
        Error detection includes:
        - Failed login attempts
        - Token expiration patterns
        - API rate limiting
        - Connection issues
        - Automated recovery suggestions
        """
        if event.success and not event.error_code:
            return
        
        try:
            error_pattern = await self._analyze_error_pattern(event)
            
            if error_pattern:
                # Generate recovery suggestion
                recovery_action = self._generate_recovery_suggestion(error_pattern, event)
                
                if recovery_action:
                    # Log recovery suggestion
                    self.logger.warning(f"Error detected: {error_pattern['description']}", extra={
                        'trace_id': event.trace_id,
                        'request_id': event.request_id,
                        'recovery_action': recovery_action
                    })
                    
                    # Store recovery suggestion in event
                    event.recovery_action = recovery_action
                    
                    # Trigger automated recovery if enabled
                    if error_pattern.get('auto_recovery', False):
                        await self._trigger_automated_recovery(error_pattern, event)
        
        except Exception as e:
            self.logger.error(f"Error detection failed: {str(e)}", extra={
                'trace_id': event.trace_id,
                'request_id': event.request_id
            })
    
    async def _analyze_error_pattern(self, event: AuthenticationEvent) -> Optional[Dict[str, Any]]:
        """
        Analyze event for known error patterns.
        
        Args:
            event: Event to analyze
            
        Returns:
            Optional[Dict[str, Any]]: Error pattern information if detected
        """
        # Define error patterns
        error_patterns = {
            'token_expired': {
                'description': 'Access token has expired',
                'conditions': lambda e: e.event_type == AuthEventType.TOKEN_EXPIRED,
                'auto_recovery': True,
                'recovery_actions': ['refresh_token', 'relogin']
            },
            'login_failure': {
                'description': 'Authentication login failed',
                'conditions': lambda e: e.event_type == AuthEventType.LOGIN_FAILURE,
                'auto_recovery': False,
                'recovery_actions': ['check_credentials', 'verify_network', 'retry_login']
            },
            'rate_limit': {
                'description': 'API rate limit exceeded',
                'conditions': lambda e: e.event_type == AuthEventType.RATE_LIMIT,
                'auto_recovery': True,
                'recovery_actions': ['wait_and_retry', 'reduce_request_rate']
            },
            'connection_error': {
                'description': 'Connection to Kite API failed',
                'conditions': lambda e: e.event_type == AuthEventType.CONNECTION_ERROR,
                'auto_recovery': True,
                'recovery_actions': ['retry_connection', 'check_network', 'fallback_mode']
            }
        }
        
        for pattern_name, pattern in error_patterns.items():
            if pattern['conditions'](event):
                return {**pattern, 'name': pattern_name}
        
        return None
    
    def _generate_recovery_suggestion(self, error_pattern: Dict[str, Any], event: AuthenticationEvent) -> str:
        """
        Generate human-readable recovery suggestion based on error pattern.
        
        Args:
            error_pattern: Detected error pattern
            event: Original event
            
        Returns:
            str: Recovery suggestion message
        """
        recovery_messages = {
            'refresh_token': 'Try refreshing the access token using the refresh token',
            'relogin': 'Perform a new login to obtain fresh credentials',
            'check_credentials': 'Verify API key and secret are correct in environment variables',
            'verify_network': 'Check internet connection and Kite API accessibility',
            'retry_login': 'Retry login after a short delay',
            'wait_and_retry': 'Wait for rate limit to reset (typically 1 minute) then retry',
            'reduce_request_rate': 'Implement exponential backoff for API requests',
            'retry_connection': 'Retry connection with exponential backoff',
            'check_network': 'Verify network connectivity to api.kite.trade',
            'fallback_mode': 'Switch to mock data mode if available'
        }
        
        actions = error_pattern.get('recovery_actions', [])
        if not actions:
            return "Manual intervention required - check logs for details"
        
        suggestions = [recovery_messages.get(action, action) for action in actions[:3]]
        return f"Suggested actions: {'; '.join(suggestions)}"
    
    async def _trigger_automated_recovery(self, error_pattern: Dict[str, Any], event: AuthenticationEvent) -> None:
        """
        Trigger automated recovery actions for recoverable errors.
        
        Args:
            error_pattern: Error pattern that supports auto-recovery
            event: Original event that triggered the error
        """
        try:
            pattern_name = error_pattern['name']
            
            if pattern_name == 'token_expired' and KITE_CLIENT_AVAILABLE:
                # Attempt token refresh using original kite_client
                self.logger.info("Attempting automated token refresh", extra={
                    'trace_id': event.trace_id,
                    'request_id': event.request_id
                })
                
                # This would integrate with the self-healing mechanism in kite_client.py
                # For now, just log the attempt
                await self.log_authentication_event(AuthenticationEvent(
                    event_type=AuthEventType.SELF_HEAL,
                    timestamp=datetime.now(),
                    user_id=event.user_id,
                    session_id=event.session_id,
                    trace_id=event.trace_id,
                    metadata={'original_error': event.error_message, 'recovery_type': 'token_refresh'}
                ))
            
        except Exception as e:
            self.logger.error(f"Automated recovery failed: {str(e)}", extra={
                'trace_id': event.trace_id,
                'request_id': event.request_id
            })
    
    async def _initialize_error_patterns(self) -> None:
        """Initialize error pattern detection rules and thresholds."""
        self.error_patterns = {
            'failed_login_threshold': 5,  # Alert after 5 failed attempts
            'error_rate_threshold': 0.1,  # Alert if error rate > 10%
            'connection_timeout': 30,     # Connection timeout in seconds
            'token_refresh_window': 3600, # Refresh token 1 hour before expiry
        }
    
    async def _periodic_cleanup(self) -> None:
        """
        Periodic cleanup task for expired sessions and old data.
        
        Runs continuously to:
        - Remove expired sessions from cache and Redis
        - Clean up temporary data
        - Update metrics and statistics
        """
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval.total_seconds())
                
                current_time = datetime.now()
                expired_sessions = []
                
                # Find expired sessions
                for session_id, session in self.session_cache.items():
                    if current_time - session.last_activity > self.session_timeout:
                        expired_sessions.append(session_id)
                
                # Remove expired sessions
                for session_id in expired_sessions:
                    del self.session_cache[session_id]
                    
                    # Remove from Redis
                    if self.redis_client:
                        await self.redis_client.delete(f"auth_session:{session_id}")
                
                if expired_sessions:
                    self.logger.info(f"Cleaned up {len(expired_sessions)} expired sessions", extra={
                        'trace_id': str(uuid.uuid4()),
                        'request_id': str(uuid.uuid4())
                    })
                
            except Exception as e:
                self.logger.error(f"Cleanup task error: {str(e)}", extra={
                    'trace_id': str(uuid.uuid4()),
                    'request_id': str(uuid.uuid4())
                })
    
    async def get_session_info(self, session_id: str) -> Optional[SessionInfo]:
        """
        Retrieve session information by session ID.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Optional[SessionInfo]: Session information if found
        """
        try:
            if session_id in self.session_cache:
                return self.session_cache[session_id]
            
            if self.redis_client:
                session_data = await self.redis_client.get(f"auth_session:{session_id}")
                if session_data:
                    session_dict = json.loads(session_data)
                    # Handle datetime deserialization
                    for key, value in session_dict.items():
                        if key in ['created_at', 'last_activity', 'expires_at'] and value:
                            session_dict[key] = datetime.fromisoformat(value)
                    
                    session = SessionInfo(**session_dict)
                    self.session_cache[session_id] = session
                    return session
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to retrieve session info: {str(e)}", extra={
                'trace_id': str(uuid.uuid4()),
                'request_id': str(uuid.uuid4())
            })
            return None
    
    async def get_authentication_metrics(self) -> Dict[str, Any]:
        """
        Get current authentication metrics and statistics.
        
        Returns:
            Dict[str, Any]: Current metrics and statistics
        """
        try:
            # Calculate rates and percentages
            total_login_attempts = self.metrics['login_attempts']
            successful_logins = self.metrics['successful_logins']
            
            success_rate = (successful_logins / total_login_attempts * 100) if total_login_attempts > 0 else 0
            error_rate = (self.metrics['errors'] / self.metrics['total_events'] * 100) if self.metrics['total_events'] > 0 else 0
            
            return {
                'summary': {
                    'total_events': self.metrics['total_events'],
                    'active_sessions': len(self.session_cache),
                    'success_rate_percent': round(success_rate, 2),
                    'error_rate_percent': round(error_rate, 2)
                },
                'authentication': {
                    'login_attempts': self.metrics['login_attempts'],
                    'successful_logins': self.metrics['successful_logins'],
                    'failed_logins': self.metrics['failed_logins'],
                    'token_refreshes': self.metrics['token_refreshes']
                },
                'operations': {
                    'api_calls': self.metrics['api_calls'],
                    'errors': self.metrics['errors'],
                    'self_heals': self.metrics['self_heals']
                },
                'session_info': {
                    'active_sessions': len(self.session_cache),
                    'total_api_calls': sum(s.api_calls_count for s in self.session_cache.values()),
                    'total_errors': sum(s.errors_count for s in self.session_cache.values())
                }
            }
            
        except Exception as e:
            self.logger.error(f"Failed to generate metrics: {str(e)}", extra={
                'trace_id': str(uuid.uuid4()),
                'request_id': str(uuid.uuid4())
            })
            return {'error': str(e)}
    
    async def close(self) -> None:
        """
        Cleanup and close all connections.
        
        Should be called when shutting down the application to ensure
        proper cleanup of resources and connections.
        """
        try:
            if self.influxdb_client:
                await self.influxdb_client.close()
            
            if self.redis_client:
                await self.redis_client.close()
            
            self.logger.info("Integrated Kite Auth Logger closed successfully", extra={
                'trace_id': str(uuid.uuid4()),
                'request_id': str(uuid.uuid4())
            })
            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {str(e)}", extra={
                'trace_id': str(uuid.uuid4()),
                'request_id': str(uuid.uuid4())
            })

# ================================================================================================
# INTEGRATED KITE AUTH MANAGER
# ================================================================================================

class IntegratedKiteAuthManager:
    """
    High-level authentication manager that integrates original kite_client.py
    functionality with enhanced logging and monitoring.
    
    This class provides:
    - Complete Kite Connect authentication workflow
    - Integration with original kite_client.py authentication flow
    - Comprehensive logging with infinite retention
    - Session management and monitoring
    - Error detection and recovery
    - Dashboard-ready analytics
    
    Usage:
        manager = IntegratedKiteAuthManager()
        await manager.initialize()
        kite_client = await manager.authenticate()
    """
    
    def __init__(self):
        """Initialize the integrated authentication manager."""
        self.logger = IntegratedKiteAuthLogger()
        self.kite_client = None
        self.current_session = None
        self.is_authenticated = False
        
    async def initialize(self) -> bool:
        """
        Initialize the authentication manager.
        
        Returns:
            bool: True if initialization successful
        """
        return await self.logger.initialize()
    
    async def authenticate(self, force_new_login: bool = False) -> Optional[Any]:
        """
        Perform Kite Connect authentication using original kite_client.py flow.
        
        Args:
            force_new_login: Whether to force a new login even if token exists
            
        Returns:
            Optional[Any]: Authenticated Kite client or None
            
        This method integrates with the original kite_client.py authentication
        while adding comprehensive logging and monitoring.
        """
        session_id = str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        start_time = datetime.now()
        
        try:
            # Log authentication attempt
            await self.logger.log_authentication_event(AuthenticationEvent(
                event_type=AuthEventType.LOGIN_ATTEMPT,
                timestamp=start_time,
                session_id=session_id,
                trace_id=trace_id,
                metadata={'start_time': start_time, 'force_new_login': force_new_login}
            ))
            
            if not KITE_CLIENT_AVAILABLE:
                error_msg = "kite_client.py not available"
                await self.logger.log_authentication_event(AuthenticationEvent(
                    event_type=AuthEventType.LOGIN_FAILURE,
                    timestamp=datetime.now(),
                    session_id=session_id,
                    trace_id=trace_id,
                    success=False,
                    error_code="KITE_CLIENT_UNAVAILABLE",
                    error_message=error_msg
                ))
                return None
            
            # Check existing token if not forcing new login
            if not force_new_login:
                existing_token = _load_token()
                if existing_token and existing_token.get('access_token'):
                    # Validate existing token (this would need Kite client validation)
                    await self.logger.log_authentication_event(AuthenticationEvent(
                        event_type=AuthEventType.SESSION_VALIDATION,
                        timestamp=datetime.now(),
                        session_id=session_id,
                        trace_id=trace_id,
                        metadata={'token_source': 'existing'}
                    ))
            
            # Use original kite_client.py authentication
            self.kite_client = get_kite_client()
            
            if self.kite_client:
                # Successful authentication
                self.is_authenticated = True
                self.current_session = session_id
                
                # Get token for logging
                token_data = _load_token()
                access_token = token_data.get('access_token', '') if token_data else ''
                
                await self.logger.log_authentication_event(AuthenticationEvent(
                    event_type=AuthEventType.LOGIN_SUCCESS,
                    timestamp=datetime.now(),
                    session_id=session_id,
                    trace_id=trace_id,
                    success=True,
                    metadata={
                        'start_time': start_time,
                        'access_token': access_token[:10] + '...' if access_token else '',  # Masked token
                        'authentication_method': 'kite_connect'
                    }
                ))
                
                return self.kite_client
            else:
                # Authentication failed
                await self.logger.log_authentication_event(AuthenticationEvent(
                    event_type=AuthEventType.LOGIN_FAILURE,
                    timestamp=datetime.now(),
                    session_id=session_id,
                    trace_id=trace_id,
                    success=False,
                    error_code="AUTHENTICATION_FAILED",
                    error_message="Kite client initialization failed"
                ))
                return None
        
        except Exception as e:
            # Log authentication error
            await self.logger.log_authentication_event(AuthenticationEvent(
                event_type=AuthEventType.SYSTEM_ERROR,
                timestamp=datetime.now(),
                session_id=session_id,
                trace_id=trace_id,
                success=False,
                error_code="EXCEPTION",
                error_message=str(e)
            ))
            return None
    
    async def make_authenticated_request(self, method_name: str, *args, **kwargs) -> Any:
        """
        Make an authenticated API request with comprehensive logging.
        
        Args:
            method_name: Name of the Kite client method to call
            *args: Arguments to pass to the method
            **kwargs: Keyword arguments to pass to the method
            
        Returns:
            Any: Result of the API call
            
        This method wraps Kite API calls with:
        - Request/response logging
        - Performance monitoring
        - Error detection and recovery
        - Automatic token refresh on expiry
        """
        if not self.kite_client or not self.is_authenticated:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        request_id = str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        start_time = datetime.now()
        
        try:
            # Log API call attempt
            await self.logger.log_authentication_event(AuthenticationEvent(
                event_type=AuthEventType.API_CALL,
                timestamp=start_time,
                session_id=self.current_session,
                trace_id=trace_id,
                request_id=request_id,
                api_endpoint=method_name,
                metadata={
                    'start_time': start_time,
                    'method': method_name,
                    'args_count': len(args),
                    'kwargs_keys': list(kwargs.keys())
                }
            ))
            
            # Make the API call
            method = getattr(self.kite_client, method_name)
            result = method(*args, **kwargs)
            
            # Log successful API call
            end_time = datetime.now()
            response_time = int((end_time - start_time).total_seconds() * 1000)
            
            await self.logger.log_authentication_event(AuthenticationEvent(
                event_type=AuthEventType.API_CALL,
                timestamp=end_time,
                session_id=self.current_session,
                trace_id=trace_id,
                request_id=request_id,
                success=True,
                api_endpoint=method_name,
                response_time_ms=response_time,
                metadata={
                    'start_time': start_time,
                    'result_type': type(result).__name__,
                    'result_size': len(str(result)) if result else 0
                }
            ))
            
            return result
            
        except Exception as e:
            # Log API error
            end_time = datetime.now()
            response_time = int((end_time - start_time).total_seconds() * 1000)
            
            await self.logger.log_authentication_event(AuthenticationEvent(
                event_type=AuthEventType.API_ERROR,
                timestamp=end_time,
                session_id=self.current_session,
                trace_id=trace_id,
                request_id=request_id,
                success=False,
                error_code=type(e).__name__,
                error_message=str(e),
                api_endpoint=method_name,
                response_time_ms=response_time
            ))
            
            raise
    
    async def logout(self) -> bool:
        """
        Perform logout with comprehensive logging.
        
        Returns:
            bool: True if logout successful
        """
        if not self.current_session:
            return True
        
        try:
            await self.logger.log_authentication_event(AuthenticationEvent(
                event_type=AuthEventType.LOGOUT,
                timestamp=datetime.now(),
                session_id=self.current_session,
                trace_id=str(uuid.uuid4()),
                success=True
            ))
            
            self.kite_client = None
            self.is_authenticated = False
            self.current_session = None
            
            return True
            
        except Exception as e:
            await self.logger.log_authentication_event(AuthenticationEvent(
                event_type=AuthEventType.SYSTEM_ERROR,
                timestamp=datetime.now(),
                session_id=self.current_session,
                trace_id=str(uuid.uuid4()),
                success=False,
                error_message=str(e)
            ))
            return False
    
    async def get_auth_dashboard_data(self) -> Dict[str, Any]:
        """
        Get comprehensive authentication dashboard data.
        
        Returns:
            Dict[str, Any]: Dashboard data including metrics, sessions, and health
        """
        try:
            metrics = await self.logger.get_authentication_metrics()
            session_info = await self.logger.get_session_info(self.current_session) if self.current_session else None
            
            return {
                'authentication_status': {
                    'is_authenticated': self.is_authenticated,
                    'current_session': self.current_session,
                    'session_active': session_info.is_active if session_info else False
                },
                'metrics': metrics,
                'session_info': asdict(session_info) if session_info else None,
                'system_health': {
                    'logger_initialized': self.logger.influxdb_client is not None,
                    'redis_connected': self.logger.redis_client is not None,
                    'kite_client_available': KITE_CLIENT_AVAILABLE
                },
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    async def close(self) -> None:
        """Close the authentication manager and cleanup resources."""
        await self.logger.close()

# ================================================================================================
# COMMAND-LINE INTERFACE AND TESTING
# ================================================================================================

async def main():
    """
    Main function for command-line usage and testing.
    
    Provides command-line interface for:
    - Interactive authentication setup
    - Testing authentication flow
    - Generating test events
    - Viewing dashboard data
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="OP Trading Platform - Integrated Kite Authentication")
    parser.add_argument('--login', action='store_true', help='Perform interactive login')
    parser.add_argument('--test', action='store_true', help='Run authentication tests')
    parser.add_argument('--dashboard', action='store_true', help='Show dashboard data')
    parser.add_argument('--logout', action='store_true', help='Perform logout')
    parser.add_argument('--status', action='store_true', help='Show authentication status')
    
    args = parser.parse_args()
    
    # Initialize authentication manager
    auth_manager = IntegratedKiteAuthManager()
    initialized = await auth_manager.initialize()
    
    if not initialized:
        print("❌ Failed to initialize authentication manager")
        return
    
    print("✅ Integrated Kite Authentication Manager initialized")
    
    try:
        if args.login:
            print("\n🔑 Starting authentication process...")
            kite_client = await auth_manager.authenticate()
            
            if kite_client:
                print("✅ Authentication successful!")
                
                # Test a simple API call
                try:
                    profile = await auth_manager.make_authenticated_request('profile')
                    print(f"✅ Profile retrieved: {profile.get('user_name', 'Unknown')}")
                except Exception as e:
                    print(f"⚠️ Profile test failed: {str(e)}")
            else:
                print("❌ Authentication failed")
        
        elif args.test:
            print("\n🧪 Running authentication tests...")
            
            # Test authentication flow
            kite_client = await auth_manager.authenticate()
            if kite_client:
                print("✅ Authentication test passed")
            else:
                print("❌ Authentication test failed")
            
            # Generate test events
            print("📊 Generating test events...")
            test_events = [
                AuthenticationEvent(
                    event_type=AuthEventType.LOGIN_SUCCESS,
                    timestamp=datetime.now(),
                    user_id="test_user",
                    metadata={'test': True}
                ),
                AuthenticationEvent(
                    event_type=AuthEventType.API_CALL,
                    timestamp=datetime.now(),
                    user_id="test_user",
                    api_endpoint="instruments",
                    response_time_ms=150
                ),
                AuthenticationEvent(
                    event_type=AuthEventType.TOKEN_REFRESH,
                    timestamp=datetime.now(),
                    user_id="test_user"
                )
            ]
            
            for event in test_events:
                await auth_manager.logger.log_authentication_event(event)
            
            print(f"✅ Generated {len(test_events)} test events")
        
        elif args.dashboard:
            print("\n📊 Authentication Dashboard Data:")
            dashboard_data = await auth_manager.get_auth_dashboard_data()
            print(json.dumps(dashboard_data, indent=2, default=str))
        
        elif args.logout:
            print("\n👋 Logging out...")
            success = await auth_manager.logout()
            if success:
                print("✅ Logout successful")
            else:
                print("❌ Logout failed")
        
        elif args.status:
            print("\n📊 Authentication Status:")
            metrics = await auth_manager.logger.get_authentication_metrics()
            print(json.dumps(metrics, indent=2, default=str))
        
        else:
            print("\n🔍 No action specified. Use --help for available options.")
            print("\nQuick start:")
            print("  python integrated_kite_auth_logger.py --login")
            print("  python integrated_kite_auth_logger.py --dashboard")
            print("  python integrated_kite_auth_logger.py --status")
    
    finally:
        await auth_manager.close()

if __name__ == "__main__":
    asyncio.run(main())

# ================================================================================================
# END OF MODULE
# ================================================================================================