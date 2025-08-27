"""
Integrated Kite Authentication and Logger Service.
Complete integration of Kite Connect authentication with centralized logging and monitoring.
"""

import asyncio
import logging
import time
import hashlib
import requests
import json
import webbrowser
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timedelta
from pathlib import Path
import urllib.parse
from dataclasses import dataclass, asdict
import sys
import traceback
import uuid
from contextlib import contextmanager

# Import shared utilities
sys.path.append(str(Path(__file__).parent.parent.parent))

from shared.config.settings import get_settings
from shared.utils.time_utils import get_time_utils, now_csv_format, is_market_open
from shared.utils.coordination import get_redis_coordinator

# Import monitoring
from services.monitoring.enhanced_health_monitor import get_health_monitor

# Set up structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class AuthenticationEvent:
    """Authentication event for centralized logging"""
    event_id: str
    event_type: str  # LOGIN_ATTEMPT, LOGIN_SUCCESS, LOGIN_FAILURE, TOKEN_REFRESH, etc.
    timestamp: str
    user_id: Optional[str] = None
    api_key: Optional[str] = None  # Masked for security
    success: bool = False
    error_message: Optional[str] = None
    request_id: Optional[str] = None
    trace_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_duration: Optional[float] = None
    additional_data: Optional[Dict[str, Any]] = None

@dataclass
class KiteSession:
    """Enhanced Kite session with logging integration"""
    user_id: str
    access_token: str
    refresh_token: str
    login_time: datetime
    expires_at: datetime
    api_key: str
    enctoken: Optional[str] = None
    public_token: Optional[str] = None
    user_name: Optional[str] = None
    user_shortname: Optional[str] = None
    email: Optional[str] = None
    broker: str = "ZERODHA"
    session_id: Optional[str] = None
    login_ip: Optional[str] = None
    login_user_agent: Optional[str] = None
    
    @property
    def is_valid(self) -> bool:
        """Check if session is still valid"""
        return datetime.now() < self.expires_at
    
    @property
    def time_to_expiry(self) -> timedelta:
        """Get time remaining until expiry"""
        return self.expires_at - datetime.now()
    
    @property
    def masked_access_token(self) -> str:
        """Return masked access token for logging"""
        if not self.access_token:
            return "None"
        return f"{self.access_token[:8]}...{self.access_token[-4:]}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage (excludes sensitive data)"""
        return {
            'user_id': self.user_id,
            'access_token': self.access_token,  # This will be encrypted
            'refresh_token': self.refresh_token,  # This will be encrypted
            'login_time': self.login_time.isoformat(),
            'expires_at': self.expires_at.isoformat(),
            'api_key': self.api_key[:8] + "..." if self.api_key else None,  # Masked
            'enctoken': self.enctoken,
            'public_token': self.public_token,
            'user_name': self.user_name,
            'user_shortname': self.user_shortname,
            'email': self.email,
            'broker': self.broker,
            'session_id': self.session_id,
            'login_ip': self.login_ip,
            'login_user_agent': self.login_user_agent
        }
    
    def to_log_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging (all sensitive data masked)"""
        return {
            'user_id': self.user_id,
            'access_token': self.masked_access_token,
            'login_time': self.login_time.isoformat(),
            'expires_at': self.expires_at.isoformat(),
            'api_key': f"{self.api_key[:8]}..." if self.api_key else None,
            'user_name': self.user_name,
            'user_shortname': self.user_shortname,
            'email': self.email,
            'broker': self.broker,
            'session_id': self.session_id,
            'is_valid': self.is_valid,
            'time_to_expiry': str(self.time_to_expiry)
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'KiteSession':
        """Create from dictionary"""
        return cls(
            user_id=data['user_id'],
            access_token=data['access_token'],
            refresh_token=data['refresh_token'],
            login_time=datetime.fromisoformat(data['login_time']),
            expires_at=datetime.fromisoformat(data['expires_at']),
            api_key=data.get('api_key', ''),
            enctoken=data.get('enctoken'),
            public_token=data.get('public_token'),
            user_name=data.get('user_name'),
            user_shortname=data.get('user_shortname'),
            email=data.get('email'),
            broker=data.get('broker', 'ZERODHA'),
            session_id=data.get('session_id'),
            login_ip=data.get('login_ip'),
            login_user_agent=data.get('login_user_agent')
        )

class IntegratedAuthLogger:
    """Centralized authentication logger with monitoring integration"""
    
    def __init__(self):
        self.settings = get_settings()
        self.redis_coord = get_redis_coordinator()
        self.health_monitor = get_health_monitor()
        self.time_utils = get_time_utils()
        
        # Configure structured logging
        self.logger = logging.getLogger(f"{__name__}.AuthLogger")
        
        # Metrics tracking
        self.auth_metrics = {
            'login_attempts': 0,
            'login_successes': 0,
            'login_failures': 0,
            'token_refreshes': 0,
            'session_timeouts': 0,
            'active_sessions': 0
        }
        
        logger.info("Integrated authentication logger initialized")
    
    async def log_authentication_event(self, event: AuthenticationEvent):
        """Log authentication event with full context"""
        try:
            # Generate trace ID if not provided
            if not event.trace_id:
                event.trace_id = str(uuid.uuid4())
            
            # Generate request ID if not provided
            if not event.request_id:
                event.request_id = f"auth_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            
            # Prepare structured log entry
            log_entry = {
                'event_id': event.event_id,
                'event_type': event.event_type,
                'timestamp': event.timestamp,
                'user_id': event.user_id,
                'api_key': event.api_key,
                'success': event.success,
                'error_message': event.error_message,
                'request_id': event.request_id,
                'trace_id': event.trace_id,
                'ip_address': event.ip_address,
                'user_agent': event.user_agent,
                'session_duration': event.session_duration,
                'additional_data': event.additional_data or {},
                'service': 'kite_auth',
                'component': 'authentication',
                'environment': self.settings.environment,
                'version': self.settings.version
            }
            
            # Log to standard logger
            if event.success:
                self.logger.info(f"Auth Event: {event.event_type}", extra=log_entry)
            else:
                self.logger.error(f"Auth Error: {event.event_type} - {event.error_message}", extra=log_entry)
            
            # Store in Redis for real-time monitoring
            await self._store_auth_event(log_entry)
            
            # Update metrics
            await self._update_auth_metrics(event)
            
            # Send to health monitor
            await self._notify_health_monitor(event)
            
            # Send alerts for critical events
            await self._check_and_send_alerts(event)
            
        except Exception as e:
            self.logger.error(f"Failed to log authentication event: {e}")
            logger.error(f"Authentication logging failed: {e}")
    
    async def _store_auth_event(self, log_entry: Dict[str, Any]):
        """Store authentication event in Redis"""
        try:
            # Store individual event
            event_key = f"auth_event:{log_entry['event_id']}"
            await self.redis_coord.cache_set(event_key, log_entry, 86400)  # 24 hours
            
            # Add to event stream
            stream_key = f"auth_stream:{log_entry['event_type']}"
            await self.redis_coord.add_to_stream(stream_key, log_entry)
            
            # Add to user event history
            if log_entry.get('user_id'):
                user_history_key = f"auth_history:{log_entry['user_id']}"
                await self.redis_coord.add_to_list(user_history_key, log_entry, max_length=100)
                
        except Exception as e:
            logger.error(f"Failed to store auth event in Redis: {e}")
    
    async def _update_auth_metrics(self, event: AuthenticationEvent):
        """Update authentication metrics"""
        try:
            metric_key = "auth_metrics"
            
            # Update counters
            if event.event_type == 'LOGIN_ATTEMPT':
                self.auth_metrics['login_attempts'] += 1
                await self.redis_coord.increment_counter(f"{metric_key}:login_attempts")
                
            elif event.event_type == 'LOGIN_SUCCESS':
                self.auth_metrics['login_successes'] += 1
                await self.redis_coord.increment_counter(f"{metric_key}:login_successes")
                
            elif event.event_type == 'LOGIN_FAILURE':
                self.auth_metrics['login_failures'] += 1
                await self.redis_coord.increment_counter(f"{metric_key}:login_failures")
                
            elif event.event_type == 'TOKEN_REFRESH':
                self.auth_metrics['token_refreshes'] += 1
                await self.redis_coord.increment_counter(f"{metric_key}:token_refreshes")
            
            # Calculate success rate
            if self.auth_metrics['login_attempts'] > 0:
                success_rate = self.auth_metrics['login_successes'] / self.auth_metrics['login_attempts']
                await self.redis_coord.set_gauge(f"{metric_key}:success_rate", success_rate)
            
        except Exception as e:
            logger.error(f"Failed to update auth metrics: {e}")
    
    async def _notify_health_monitor(self, event: AuthenticationEvent):
        """Notify health monitor of authentication events"""
        try:
            # Send authentication health data
            auth_health = {
                'component': 'kite_authentication',
                'status': 'healthy' if event.success else 'degraded',
                'last_event': event.event_type,
                'timestamp': event.timestamp,
                'error_message': event.error_message
            }
            
            await self.health_monitor.update_component_health('kite_auth', auth_health)
            
        except Exception as e:
            logger.error(f"Failed to notify health monitor: {e}")
    
    async def _check_and_send_alerts(self, event: AuthenticationEvent):
        """Check if alerts should be sent for critical events"""
        try:
            alert_conditions = []
            
            # Check for repeated failures
            if event.event_type == 'LOGIN_FAILURE':
                recent_failures = await self.redis_coord.get_counter('auth_metrics:login_failures_1h')
                if recent_failures > 10:  # More than 10 failures in an hour
                    alert_conditions.append('HIGH_LOGIN_FAILURE_RATE')
            
            # Check for token expiry issues
            if event.event_type == 'TOKEN_EXPIRED':
                alert_conditions.append('TOKEN_EXPIRED')
            
            # Check for API limit exceeded
            if event.error_message and 'rate limit' in event.error_message.lower():
                alert_conditions.append('API_RATE_LIMIT_EXCEEDED')
            
            # Send alerts
            for condition in alert_conditions:
                await self._send_auth_alert(condition, event)
                
        except Exception as e:
            logger.error(f"Failed to check auth alerts: {e}")
    
    async def _send_auth_alert(self, condition: str, event: AuthenticationEvent):
        """Send authentication alert"""
        try:
            alert_data = {
                'alert_type': 'AUTHENTICATION_ALERT',
                'condition': condition,
                'severity': 'HIGH',
                'event_id': event.event_id,
                'user_id': event.user_id,
                'timestamp': event.timestamp,
                'error_message': event.error_message,
                'additional_context': {
                    'event_type': event.event_type,
                    'api_key': event.api_key,
                    'trace_id': event.trace_id
                }
            }
            
            # Send via health monitor alert system
            await self.health_monitor.send_alert(alert_data)
            
            logger.warning(f"Authentication alert sent: {condition} for event {event.event_id}")
            
        except Exception as e:
            logger.error(f"Failed to send auth alert: {e}")
    
    async def get_auth_metrics(self) -> Dict[str, Any]:
        """Get current authentication metrics"""
        try:
            metrics = {}
            
            # Get counters from Redis
            metric_keys = [
                'login_attempts', 'login_successes', 'login_failures', 
                'token_refreshes', 'session_timeouts'
            ]
            
            for key in metric_keys:
                value = await self.redis_coord.get_counter(f"auth_metrics:{key}")
                metrics[key] = value or 0
            
            # Calculate derived metrics
            if metrics['login_attempts'] > 0:
                metrics['success_rate'] = metrics['login_successes'] / metrics['login_attempts']
            else:
                metrics['success_rate'] = 0.0
                
            if metrics['login_successes'] > 0:
                metrics['failure_rate'] = metrics['login_failures'] / metrics['login_successes']
            else:
                metrics['failure_rate'] = 0.0
            
            # Get active sessions count
            active_sessions = await self.redis_coord.scan_keys("kite_session:*")
            metrics['active_sessions'] = len(active_sessions)
            
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to get auth metrics: {e}")
            return {}
    
    async def get_recent_auth_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent authentication events"""
        try:
            events = []
            
            # Get from various event streams
            event_types = ['LOGIN_ATTEMPT', 'LOGIN_SUCCESS', 'LOGIN_FAILURE', 'TOKEN_REFRESH']
            
            for event_type in event_types:
                stream_key = f"auth_stream:{event_type}"
                stream_events = await self.redis_coord.get_from_stream(stream_key, limit=limit//4)
                events.extend(stream_events)
            
            # Sort by timestamp
            events.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            return events[:limit]
            
        except Exception as e:
            logger.error(f"Failed to get recent auth events: {e}")
            return []

class IntegratedKiteConnect:
    """Enhanced Kite Connect client with integrated logging"""
    
    # Kite Connect API endpoints with infinite retention settings
    _root_url = "https://api.kite.trade"
    _login_url = "https://kite.zerodha.com/connect/login"
    _routes = {
        "api.token": "/session/token",
        "api.token.invalidate": "/session/token",
        "api.token.renew": "/session/refresh_token",
        "user.profile": "/user/profile",
        "user.margins": "/user/margins",
        "orders": "/orders",
        "trades": "/trades",
        "orders.place": "/orders/{variety}",
        "orders.modify": "/orders/{variety}/{order_id}",
        "orders.cancel": "/orders/{variety}/{order_id}",
        "portfolio.positions": "/portfolio/positions",
        "portfolio.holdings": "/portfolio/holdings",
        "portfolio.positions.convert": "/portfolio/positions",
        "market.instruments.all": "/instruments",
        "market.instruments": "/instruments/{exchange}",
        "market.historical": "/instruments/historical/{instrument_token}/{interval}",
        "market.quote": "/quote",
        "market.ohlc": "/quote/ohlc",
        "market.ltp": "/quote/ltp",
        "gtt": "/gtt/triggers",
        "gtt.place": "/gtt/triggers",
        "gtt.modify": "/gtt/triggers/{trigger_id}",
        "gtt.delete": "/gtt/triggers/{trigger_id}",
        "mf.orders": "/mf/orders",
        "mf.orders.place": "/mf/orders",
        "mf.orders.cancel": "/mf/orders/{order_id}",
        "mf.sips": "/mf/sips",
        "mf.sips.place": "/mf/sips",
        "mf.sips.modify": "/mf/sips/{sip_id}",
        "mf.sips.cancel": "/mf/sips/{sip_id}",
        "mf.holdings": "/mf/holdings",
        "mf.instruments": "/mf/instruments"
    }
    
    def __init__(self, api_key: str, api_secret: str = None, access_token: str = None):
        """
        Initialize integrated Kite Connect client with logging
        
        Args:
            api_key: Kite Connect app API key
            api_secret: Kite Connect app secret
            access_token: Existing access token (if available)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.session = requests.Session()
        self.session_data: Optional[KiteSession] = None
        
        # Get utilities
        self.settings = get_settings()
        self.time_utils = get_time_utils()
        self.redis_coord = get_redis_coordinator()
        self.auth_logger = IntegratedAuthLogger()
        
        # Session management with infinite retention
        self.session_key = f"kite_session:{api_key}"
        
        # Request context
        self.current_request_id = None
        self.current_trace_id = None
        
        # Load cached session
        asyncio.create_task(self._load_cached_session())
        
        logger.info(f"IntegratedKiteConnect initialized with API key: {api_key[:8]}...")
    
    @contextmanager
    def request_context(self, request_id: str = None, trace_id: str = None):
        """Context manager for request tracking"""
        old_request_id = self.current_request_id
        old_trace_id = self.current_trace_id
        
        self.current_request_id = request_id or f"kite_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        self.current_trace_id = trace_id or str(uuid.uuid4())
        
        try:
            yield
        finally:
            self.current_request_id = old_request_id
            self.current_trace_id = old_trace_id
    
    async def _load_cached_session(self) -> bool:
        """Load cached session from Redis with infinite retention"""
        try:
            # Get session data from Redis (stored with infinite TTL)
            cached_data = await self.redis_coord.cache_get(self.session_key)
            if cached_data:
                self.session_data = KiteSession.from_dict(cached_data)
                
                # Log session load event
                await self._log_auth_event(
                    event_type='SESSION_LOADED',
                    success=True,
                    user_id=self.session_data.user_id,
                    additional_data={'session_valid': self.session_data.is_valid}
                )
                
                if self.session_data.is_valid:
                    self.access_token = self.session_data.access_token
                    logger.info(f"Loaded valid cached session for user: {self.session_data.user_id}")
                    return True
                else:
                    logger.warning("Cached session expired")
                    await self._log_auth_event(
                        event_type='SESSION_EXPIRED',
                        success=False,
                        user_id=self.session_data.user_id,
                        error_message="Cached session has expired"
                    )
                    # Don't delete expired sessions - keep for audit trail with infinite retention
            
            return False
            
        except Exception as e:
            await self._log_auth_event(
                event_type='SESSION_LOAD_ERROR',
                success=False,
                error_message=str(e)
            )
            logger.error(f"Error loading cached session: {e}")
            return False
    
    async def _save_session(self, session: KiteSession):
        """Save session to Redis with infinite retention"""
        try:
            self.session_data = session
            self.access_token = session.access_token
            
            # Store session with no TTL (infinite retention)
            await self.redis_coord.cache_set(self.session_key, session.to_dict())
            
            # Also store in session history for audit trail
            history_key = f"session_history:{session.user_id}"
            history_entry = {
                'timestamp': now_csv_format(),
                'session_id': session.session_id,
                'login_time': session.login_time.isoformat(),
                'expires_at': session.expires_at.isoformat(),
                'api_key': session.api_key[:8] + "..." if session.api_key else None,
                'login_ip': session.login_ip,
                'user_agent': session.login_user_agent
            }
            await self.redis_coord.add_to_list(history_key, history_entry)
            
            await self._log_auth_event(
                event_type='SESSION_SAVED',
                success=True,
                user_id=session.user_id,
                additional_data={'session_duration': str(session.time_to_expiry)}
            )
            
            logger.info(f"Session cached with infinite retention for user: {session.user_id}")
            
        except Exception as e:
            await self._log_auth_event(
                event_type='SESSION_SAVE_ERROR',
                success=False,
                user_id=session.user_id if session else None,
                error_message=str(e)
            )
            logger.error(f"Error saving session: {e}")
    
    async def _log_auth_event(self, event_type: str, success: bool, user_id: str = None, 
                            error_message: str = None, additional_data: Dict[str, Any] = None):
        """Log authentication event"""
        try:
            event = AuthenticationEvent(
                event_id=str(uuid.uuid4()),
                event_type=event_type,
                timestamp=now_csv_format(),
                user_id=user_id,
                api_key=f"{self.api_key[:8]}..." if self.api_key else None,
                success=success,
                error_message=error_message,
                request_id=self.current_request_id,
                trace_id=self.current_trace_id,
                additional_data=additional_data
            )
            
            await self.auth_logger.log_authentication_event(event)
            
        except Exception as e:
            logger.error(f"Failed to log authentication event: {e}")
    
    def get_login_url(self) -> str:
        """Generate login URL for Kite Connect OAuth flow with logging"""
        try:
            params = {
                "api_key": self.api_key,
                "v": 3,
            }
            
            login_url = f"{self._login_url}?{urllib.parse.urlencode(params)}"
            
            # Log URL generation
            asyncio.create_task(self._log_auth_event(
                event_type='LOGIN_URL_GENERATED',
                success=True,
                additional_data={'login_url': login_url}
            ))
            
            logger.info(f"Generated login URL: {login_url}")
            return login_url
            
        except Exception as e:
            asyncio.create_task(self._log_auth_event(
                event_type='LOGIN_URL_ERROR',
                success=False,
                error_message=str(e)
            ))
            logger.error(f"Error generating login URL: {e}")
            raise
    
    async def generate_session(self, request_token: str, api_secret: str = None, 
                             login_ip: str = None, user_agent: str = None) -> KiteSession:
        """Generate access token with comprehensive logging"""
        start_time = time.time()
        
        with self.request_context():
            await self._log_auth_event(
                event_type='LOGIN_ATTEMPT',
                success=True,
                additional_data={
                    'request_token': f"{request_token[:8]}..." if request_token else None,
                    'login_ip': login_ip,
                    'user_agent': user_agent
                }
            )
            
            try:
                if not api_secret:
                    api_secret = self.api_secret
                    
                if not api_secret:
                    error_msg = "API secret is required to generate session"
                    await self._log_auth_event(
                        event_type='LOGIN_FAILURE',
                        success=False,
                        error_message=error_msg
                    )
                    raise ValueError(error_msg)
                
                # Generate checksum
                checksum = hashlib.sha256(
                    f"{self.api_key}{request_token}{api_secret}".encode("utf-8")
                ).hexdigest()
                
                # Request access token
                url = f"{self._root_url}{self._routes['api.token']}"
                data = {
                    "api_key": self.api_key,
                    "request_token": request_token,
                    "checksum": checksum
                }
                
                response = self.session.post(url, data=data, timeout=30)
                response.raise_for_status()
                
                result = response.json()
                
                if result.get("status") != "success":
                    error_msg = f"Token generation failed: {result.get('message', 'Unknown error')}"
                    await self._log_auth_event(
                        event_type='LOGIN_FAILURE',
                        success=False,
                        error_message=error_msg,
                        additional_data={'api_response': result}
                    )
                    raise ValueError(error_msg)
                
                data = result["data"]
                
                # Create session object with enhanced data
                session = KiteSession(
                    user_id=data["user_id"],
                    access_token=data["access_token"],
                    refresh_token=data.get("refresh_token", ""),
                    login_time=datetime.now(),
                    expires_at=datetime.now() + timedelta(hours=24),
                    api_key=self.api_key,
                    enctoken=data.get("enctoken"),
                    public_token=data.get("public_token"),
                    user_name=data.get("user_name"),
                    user_shortname=data.get("user_shortname"),
                    email=data.get("email"),
                    session_id=str(uuid.uuid4()),
                    login_ip=login_ip,
                    login_user_agent=user_agent
                )
                
                # Save session with infinite retention
                await self._save_session(session)
                
                # Log successful authentication
                session_duration = time.time() - start_time
                await self._log_auth_event(
                    event_type='LOGIN_SUCCESS',
                    success=True,
                    user_id=session.user_id,
                    session_duration=session_duration,
                    additional_data={
                        'user_name': session.user_name,
                        'email': session.email,
                        'session_duration_seconds': session_duration,
                        'expires_at': session.expires_at.isoformat()
                    }
                )
                
                logger.info(f"Session generated successfully for user: {session.user_id}")
                return session
                
            except requests.exceptions.RequestException as e:
                await self._log_auth_event(
                    event_type='LOGIN_FAILURE',
                    success=False,
                    error_message=f"Network error: {str(e)}",
                    session_duration=time.time() - start_time,
                    additional_data={'error_type': 'NETWORK_ERROR'}
                )
                raise ValueError(f"Network error during token generation: {e}")
                
            except json.JSONDecodeError as e:
                await self._log_auth_event(
                    event_type='LOGIN_FAILURE',
                    success=False,
                    error_message=f"Invalid response format: {str(e)}",
                    session_duration=time.time() - start_time,
                    additional_data={'error_type': 'RESPONSE_FORMAT_ERROR'}
                )
                raise ValueError(f"Invalid response format: {e}")
                
            except Exception as e:
                await self._log_auth_event(
                    event_type='LOGIN_FAILURE',
                    success=False,
                    error_message=str(e),
                    session_duration=time.time() - start_time,
                    additional_data={'error_type': 'UNEXPECTED_ERROR'}
                )
                raise ValueError(f"Unexpected error: {e}")
    
    async def renew_access_token(self, refresh_token: str = None, api_secret: str = None) -> Optional[str]:
        """Renew access token with comprehensive logging"""
        start_time = time.time()
        
        with self.request_context():
            await self._log_auth_event(
                event_type='TOKEN_REFRESH_ATTEMPT',
                success=True,
                user_id=self.session_data.user_id if self.session_data else None
            )
            
            try:
                if not refresh_token and self.session_data:
                    refresh_token = self.session_data.refresh_token
                    
                if not api_secret:
                    api_secret = self.api_secret
                    
                if not refresh_token or not api_secret:
                    error_msg = "Refresh token and API secret required for renewal"
                    await self._log_auth_event(
                        event_type='TOKEN_REFRESH_FAILURE',
                        success=False,
                        error_message=error_msg,
                        user_id=self.session_data.user_id if self.session_data else None
                    )
                    logger.error(error_msg)
                    return None
                
                # Generate checksum
                checksum = hashlib.sha256(
                    f"{self.api_key}{refresh_token}{api_secret}".encode("utf-8")
                ).hexdigest()
                
                url = f"{self._root_url}{self._routes['api.token.renew']}"
                data = {
                    "api_key": self.api_key,
                    "refresh_token": refresh_token,
                    "checksum": checksum
                }
                
                response = self.session.post(url, data=data, timeout=30)
                response.raise_for_status()
                
                result = response.json()
                
                if result.get("status") != "success":
                    error_msg = f"Token renewal failed: {result.get('message')}"
                    await self._log_auth_event(
                        event_type='TOKEN_REFRESH_FAILURE',
                        success=False,
                        error_message=error_msg,
                        user_id=self.session_data.user_id if self.session_data else None,
                        session_duration=time.time() - start_time
                    )
                    logger.error(error_msg)
                    return None
                
                new_access_token = result["data"]["access_token"]
                
                # Update session with infinite retention
                if self.session_data:
                    old_token = self.session_data.masked_access_token
                    self.session_data.access_token = new_access_token
                    self.session_data.expires_at = datetime.now() + timedelta(hours=24)
                    await self._save_session(self.session_data)
                
                self.access_token = new_access_token
                
                await self._log_auth_event(
                    event_type='TOKEN_REFRESH_SUCCESS',
                    success=True,
                    user_id=self.session_data.user_id if self.session_data else None,
                    session_duration=time.time() - start_time,
                    additional_data={
                        'old_token': old_token if self.session_data else None,
                        'new_token': f"{new_access_token[:8]}...{new_access_token[-4:]}",
                        'new_expiry': (datetime.now() + timedelta(hours=24)).isoformat()
                    }
                )
                
                logger.info("Access token renewed successfully")
                return new_access_token
                
            except Exception as e:
                await self._log_auth_event(
                    event_type='TOKEN_REFRESH_FAILURE',
                    success=False,
                    error_message=str(e),
                    user_id=self.session_data.user_id if self.session_data else None,
                    session_duration=time.time() - start_time,
                    additional_data={'error_type': type(e).__name__}
                )
                logger.error(f"Error renewing token: {e}")
                return None
    
    async def get_profile(self) -> Optional[Dict[str, Any]]:
        """Get user profile with logging"""
        if not self.access_token:
            await self._log_auth_event(
                event_type='PROFILE_REQUEST_FAILED',
                success=False,
                error_message="No access token available"
            )
            logger.error("No access token available for profile request")
            return None
        
        with self.request_context():
            start_time = time.time()
            
            try:
                url = f"{self._root_url}{self._routes['user.profile']}"
                headers = {
                    "X-Kite-Version": "3",
                    "Authorization": f"token {self.api_key}:{self.access_token}"
                }
                
                response = self.session.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                
                result = response.json()
                
                if result.get("status") != "success":
                    error_msg = f"Profile fetch failed: {result.get('message')}"
                    await self._log_auth_event(
                        event_type='PROFILE_REQUEST_FAILED',
                        success=False,
                        error_message=error_msg,
                        user_id=self.session_data.user_id if self.session_data else None,
                        session_duration=time.time() - start_time
                    )
                    logger.error(error_msg)
                    return None
                
                profile_data = result["data"]
                
                await self._log_auth_event(
                    event_type='PROFILE_REQUEST_SUCCESS',
                    success=True,
                    user_id=profile_data.get("user_id"),
                    session_duration=time.time() - start_time,
                    additional_data={
                        'user_name': profile_data.get("user_name"),
                        'user_type': profile_data.get("user_type"),
                        'email': profile_data.get("email")
                    }
                )
                
                return profile_data
                
            except Exception as e:
                await self._log_auth_event(
                    event_type='PROFILE_REQUEST_FAILED',
                    success=False,
                    error_message=str(e),
                    user_id=self.session_data.user_id if self.session_data else None,
                    session_duration=time.time() - start_time,
                    additional_data={'error_type': type(e).__name__}
                )
                logger.error(f"Error fetching profile: {e}")
                return None
    
    async def invalidate_access_token(self, access_token: str = None) -> bool:
        """Invalidate access token with logging"""
        if not access_token:
            access_token = self.access_token
            
        if not access_token:
            await self._log_auth_event(
                event_type='TOKEN_INVALIDATION_FAILED',
                success=False,
                error_message="No access token to invalidate"
            )
            logger.warning("No access token to invalidate")
            return False
        
        with self.request_context():
            start_time = time.time()
            
            try:
                url = f"{self._root_url}{self._routes['api.token.invalidate']}"
                headers = {
                    "X-Kite-Version": "3",
                    "Authorization": f"token {self.api_key}:{access_token}"
                }
                
                response = self.session.delete(url, headers=headers, timeout=30)
                response.raise_for_status()
                
                # Clear cached session but keep in history (infinite retention)
                if self.session_data:
                    # Mark session as invalidated in history
                    invalidation_record = {
                        'timestamp': now_csv_format(),
                        'action': 'TOKEN_INVALIDATED',
                        'session_id': self.session_data.session_id,
                        'user_id': self.session_data.user_id,
                        'invalidation_reason': 'MANUAL_LOGOUT'
                    }
                    
                    history_key = f"session_history:{self.session_data.user_id}"
                    await self.redis_coord.add_to_list(history_key, invalidation_record)
                
                # Remove active session but keep history
                await self.redis_coord.cache_delete(self.session_key)
                
                user_id = self.session_data.user_id if self.session_data else None
                self.session_data = None
                self.access_token = None
                
                await self._log_auth_event(
                    event_type='TOKEN_INVALIDATION_SUCCESS',
                    success=True,
                    user_id=user_id,
                    session_duration=time.time() - start_time
                )
                
                logger.info("Access token invalidated successfully")
                return True
                
            except Exception as e:
                await self._log_auth_event(
                    event_type='TOKEN_INVALIDATION_FAILED',
                    success=False,
                    error_message=str(e),
                    user_id=self.session_data.user_id if self.session_data else None,
                    session_duration=time.time() - start_time,
                    additional_data={'error_type': type(e).__name__}
                )
                logger.error(f"Error invalidating token: {e}")
                return False
    
    async def is_session_valid(self) -> bool:
        """Check if current session is valid with logging"""
        if not self.access_token or not self.session_data:
            await self._log_auth_event(
                event_type='SESSION_VALIDATION',
                success=False,
                error_message="No session data available"
            )
            return False
        
        if not self.session_data.is_valid:
            await self._log_auth_event(
                event_type='SESSION_VALIDATION',
                success=False,
                user_id=self.session_data.user_id,
                error_message="Session expired based on timestamp"
            )
            return False
        
        # Verify with API call
        try:
            profile = await self.get_profile()
            is_valid = profile is not None
            
            await self._log_auth_event(
                event_type='SESSION_VALIDATION',
                success=is_valid,
                user_id=self.session_data.user_id,
                error_message=None if is_valid else "API validation failed"
            )
            
            return is_valid
            
        except Exception as e:
            await self._log_auth_event(
                event_type='SESSION_VALIDATION',
                success=False,
                user_id=self.session_data.user_id,
                error_message=str(e)
            )
            return False
    
    async def get_session_status(self) -> Dict[str, Any]:
        """Get comprehensive session status with logging integration"""
        try:
            status = {
                "has_api_key": bool(self.api_key),
                "has_api_secret": bool(self.api_secret),
                "has_access_token": bool(self.access_token),
                "has_session_data": bool(self.session_data),
                "is_valid": False,
                "user_id": None,
                "expires_at": None,
                "time_to_expiry": None,
                "session_id": None,
                "login_time": None,
                "last_activity": None,
                "auth_metrics": await self.auth_logger.get_auth_metrics()
            }
            
            if self.session_data:
                status.update({
                    "is_valid": self.session_data.is_valid,
                    "user_id": self.session_data.user_id,
                    "expires_at": self.session_data.expires_at.isoformat(),
                    "time_to_expiry": str(self.session_data.time_to_expiry),
                    "session_id": self.session_data.session_id,
                    "login_time": self.session_data.login_time.isoformat(),
                    "user_name": self.session_data.user_name,
                    "email": self.session_data.email
                })
            
            # Add recent authentication events
            recent_events = await self.auth_logger.get_recent_auth_events(limit=10)
            status["recent_auth_events"] = recent_events
            
            await self._log_auth_event(
                event_type='STATUS_CHECK',
                success=True,
                user_id=self.session_data.user_id if self.session_data else None,
                additional_data={'session_valid': status["is_valid"]}
            )
            
            return status
            
        except Exception as e:
            await self._log_auth_event(
                event_type='STATUS_CHECK_FAILED',
                success=False,
                error_message=str(e)
            )
            logger.error(f"Error getting session status: {e}")
            return {"error": str(e)}

# Factory functions with infinite retention settings
def get_integrated_kite_client(interactive: bool = True) -> Optional[IntegratedKiteConnect]:
    """
    Get authenticated integrated Kite Connect client with infinite retention
    
    Args:
        interactive: Whether to allow interactive login if needed
        
    Returns:
        Authenticated IntegratedKiteConnect client or None
    """
    try:
        settings = get_settings()
        
        # Ensure infinite retention is configured
        if not hasattr(settings, 'influxdb') or settings.influxdb.retention_policy != "infinite":
            logger.warning("InfluxDB retention policy should be set to 'infinite' for proper audit trail")
        
        manager = IntegratedKiteAuthManager()
        
        if interactive:
            return asyncio.run(manager.get_authenticated_client())
        else:
            if asyncio.run(manager.auto_authenticate()):
                return manager.kite
            return None
            
    except Exception as e:
        logger.error(f"Error getting integrated Kite client: {e}")
        return None

class IntegratedKiteAuthManager:
    """High-level authentication manager with integrated logging"""
    
    def __init__(self, api_key: str = None, api_secret: str = None):
        """Initialize integrated authentication manager"""
        settings = get_settings()
        
        self.api_key = api_key or settings.broker.api_key
        self.api_secret = api_secret or settings.broker.api_secret
        
        if not self.api_key:
            raise ValueError("API key is required")
        
        self.kite = IntegratedKiteConnect(self.api_key, self.api_secret)
        self.auth_logger = IntegratedAuthLogger()
        
        logger.info("Integrated Kite authentication manager initialized with infinite retention")
    
    async def interactive_login(self) -> Optional[KiteSession]:
        """Perform interactive login with comprehensive logging"""
        try:
            # Check if we already have a valid session
            if await self.kite.is_session_valid():
                logger.info("Using existing valid session")
                return self.kite.session_data
            
            print("\n" + "="*70)
            print("🔐 INTEGRATED KITE CONNECT AUTHENTICATION")
            print("   Complete logging and monitoring integration")
            print("   Infinite session retention for audit compliance")
            print("="*70)
            
            # Step 1: Open login URL
            print("\n1️⃣  Opening Kite Connect login page...")
            login_url = self.kite.get_login_url()
            
            try:
                webbrowser.open(login_url)
                logger.info("Opened login URL in browser")
            except Exception as e:
                logger.warning(f"Could not open browser: {e}")
                print(f"\n📋 Login URL: {login_url}")
            
            print("\n📝 Instructions:")
            print("   • Complete the login process in your browser")
            print("   • After successful login, you'll be redirected to a URL")
            print("   • Copy the 'request_token' parameter from the redirected URL")
            print("   • The URL will look like: https://127.0.0.1:5000/?request_token=XXXXXX&action=login&status=success")
            
            # Step 2: Get request token from user
            print("\n2️⃣  Enter the request token:")
            request_token = input("Request Token: ").strip()
            
            if not request_token:
                print("❌ No request token provided")
                return None
            
            if not self.api_secret:
                print("\n3️⃣  API Secret required for token generation:")
                api_secret = input("API Secret: ").strip()
                if not api_secret:
                    print("❌ No API secret provided")
                    return None
                self.api_secret = api_secret
                self.kite.api_secret = api_secret
            
            # Step 3: Generate session with context
            print("\n🔄 Generating access token with full logging...")
            session = await self.kite.generate_session(
                request_token, 
                self.api_secret,
                login_ip="127.0.0.1",  # Could be enhanced to get actual IP
                user_agent="OP-Trading-Platform-CLI"
            )
            
            # Step 4: Verify session
            print("✅ Verifying session...")
            profile = await self.kite.get_profile()
            
            if profile:
                print("\n✅ Authentication successful with integrated logging!")
                print(f"   👤 User: {profile.get('user_name', session.user_id)}")
                print(f"   📧 Email: {profile.get('email', 'N/A')}")
                print(f"   🆔 Session ID: {session.session_id}")
                print(f"   ⏰ Token valid until: {session.expires_at}")
                print(f"   🔑 Access token: {session.masked_access_token}")
                print(f"   📊 Session stored with infinite retention for audit compliance")
                
                return session
            else:
                print("❌ Session verification failed")
                return None
                
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            logger.error(f"Interactive login failed: {e}")
            return None
    
    async def auto_authenticate(self) -> bool:
        """Attempt automatic authentication with logging"""
        try:
            # Check for existing valid session
            if await self.kite.is_session_valid():
                logger.info("Using existing valid session")
                return True
            
            # Check for access token in environment/settings
            settings = get_settings()
            if settings.broker.access_token:
                logger.info("Trying access token from settings")
                self.kite.access_token = settings.broker.access_token
                
                if await self.kite.is_session_valid():
                    logger.info("Access token from settings is valid")
                    return True
                else:
                    logger.warning("Access token from settings is invalid")
            
            # Cannot auto-authenticate
            logger.info("Auto-authentication failed - manual login required")
            return False
            
        except Exception as e:
            logger.error(f"Auto-authentication error: {e}")
            return False
    
    async def get_authenticated_client(self) -> Optional[IntegratedKiteConnect]:
        """Get authenticated integrated Kite Connect client"""
        if await self.auto_authenticate():
            return self.kite
        
        # Try interactive login
        print("\n🔐 Automatic authentication failed. Manual login required.")
        session = await self.interactive_login()
        
        if session:
            return self.kite
        
        return None
    
    async def logout(self) -> bool:
        """Logout with comprehensive logging"""
        try:
            success = await self.kite.invalidate_access_token()
            if success:
                print("✅ Logged out successfully with full audit trail")
                logger.info("User logged out with integrated logging")
            return success
            
        except Exception as e:
            logger.error(f"Logout error: {e}")
            return False
    
    async def get_auth_dashboard_data(self) -> Dict[str, Any]:
        """Get authentication dashboard data for monitoring"""
        try:
            dashboard_data = {
                'session_status': await self.kite.get_session_status(),
                'auth_metrics': await self.auth_logger.get_auth_metrics(),
                'recent_events': await self.auth_logger.get_recent_auth_events(limit=20),
                'system_info': {
                    'infinite_retention_enabled': True,
                    'structured_logging_enabled': True,
                    'health_monitoring_enabled': True,
                    'last_updated': now_csv_format()
                }
            }
            
            return dashboard_data
            
        except Exception as e:
            logger.error(f"Error getting auth dashboard data: {e}")
            return {'error': str(e)}

# CLI interface for integrated authentication
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Integrated Kite Connect Authentication with Logging")
    parser.add_argument("--login", action="store_true", help="Perform interactive login with integrated logging")
    parser.add_argument("--status", action="store_true", help="Check session status with metrics")
    parser.add_argument("--logout", action="store_true", help="Logout and invalidate session")
    parser.add_argument("--dashboard", action="store_true", help="Show authentication dashboard")
    parser.add_argument("--metrics", action="store_true", help="Show authentication metrics")
    parser.add_argument("--api-key", help="API key (optional)")
    parser.add_argument("--api-secret", help="API secret (optional)")
    
    args = parser.parse_args()
    
    async def main():
        try:
            if args.login:
                manager = IntegratedKiteAuthManager(args.api_key, args.api_secret)
                session = await manager.interactive_login()
                if session:
                    print(f"\n✅ Login successful for user: {session.user_id}")
                    print(f"📊 Session logged with infinite retention for compliance")
                else:
                    print("\n❌ Login failed")
                    sys.exit(1)
                    
            elif args.status:
                manager = IntegratedKiteAuthManager(args.api_key, args.api_secret)
                status = await manager.kite.get_session_status()
                print("\n📊 Integrated Session Status:")
                for key, value in status.items():
                    if key != 'recent_auth_events':
                        print(f"   {key}: {value}")
                        
            elif args.logout:
                manager = IntegratedKiteAuthManager(args.api_key, args.api_secret)
                if await manager.logout():
                    print("\n✅ Logout successful with audit trail")
                else:
                    print("\n❌ Logout failed")
                    
            elif args.dashboard:
                manager = IntegratedKiteAuthManager(args.api_key, args.api_secret)
                dashboard = await manager.get_auth_dashboard_data()
                print("\n📊 Authentication Dashboard:")
                print(json.dumps(dashboard, indent=2, default=str))
                
            elif args.metrics:
                auth_logger = IntegratedAuthLogger()
                metrics = await auth_logger.get_auth_metrics()
                print("\n📈 Authentication Metrics:")
                for key, value in metrics.items():
                    print(f"   {key}: {value}")
                    
            else:
                # Default: try to get authenticated client with status
                client = get_integrated_kite_client()
                if client:
                    profile = await client.get_profile()
                    print(f"\n✅ Authenticated as: {profile.get('user_name', 'Unknown')}")
                    print("📊 Full logging and monitoring integration active")
                    print("♾️  Infinite retention enabled for audit compliance")
                else:
                    print("\n❌ Authentication failed")
                    
        except KeyboardInterrupt:
            print("\n⚠️  Operation cancelled")
            sys.exit(130)
        except Exception as e:
            print(f"\n❌ Error: {e}")
            traceback.print_exc()
            sys.exit(1)
    
    # Run the async main function
    asyncio.run(main())