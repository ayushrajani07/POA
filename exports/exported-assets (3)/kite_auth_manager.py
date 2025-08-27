"""
Kite Connect Authentication and Session Management.
Handles login, request tokens, access tokens, and session management for Zerodha Kite API.
"""

import hashlib
import requests
import json
import time
import logging
import webbrowser
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import urllib.parse
from dataclasses import dataclass
import sys

# Import shared utilities
sys.path.append(str(Path(__file__).parent.parent.parent))

from shared.config.settings import get_settings
from shared.utils.time_utils import get_time_utils, now_csv_format
from shared.utils.coordination import get_redis_coordinator

logger = logging.getLogger(__name__)

@dataclass
class KiteSession:
    """Kite session information"""
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
    
    @property
    def is_valid(self) -> bool:
        """Check if session is still valid"""
        return datetime.now() < self.expires_at
    
    @property
    def time_to_expiry(self) -> timedelta:
        """Get time remaining until expiry"""
        return self.expires_at - datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            'user_id': self.user_id,
            'access_token': self.access_token,
            'refresh_token': self.refresh_token,
            'login_time': self.login_time.isoformat(),
            'expires_at': self.expires_at.isoformat(),
            'api_key': self.api_key,
            'enctoken': self.enctoken,
            'public_token': self.public_token,
            'user_name': self.user_name,
            'user_shortname': self.user_shortname,
            'email': self.email,
            'broker': self.broker
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
            api_key=data['api_key'],
            enctoken=data.get('enctoken'),
            public_token=data.get('public_token'),
            user_name=data.get('user_name'),
            user_shortname=data.get('user_shortname'),
            email=data.get('email'),
            broker=data.get('broker', 'ZERODHA')
        )

class KiteAuthenticationError(Exception):
    """Custom exception for Kite authentication errors"""
    pass

class KiteConnect:
    """
    Enhanced Kite Connect client with authentication management.
    Handles the complete OAuth flow for Zerodha Kite API.
    """
    
    # Kite Connect API endpoints
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
        Initialize Kite Connect client
        
        Args:
            api_key: Kite Connect app API key
            api_secret: Kite Connect app secret (required for generating access token)
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
        
        # Session management
        self.session_key = f"kite_session:{api_key}"
        self._load_cached_session()
        
        logger.info(f"KiteConnect initialized with API key: {api_key[:8]}...")
    
    def _load_cached_session(self) -> bool:
        """Load cached session from Redis"""
        try:
            cached_data = self.redis_coord.cache_get(self.session_key)
            if cached_data:
                self.session_data = KiteSession.from_dict(cached_data)
                if self.session_data.is_valid:
                    self.access_token = self.session_data.access_token
                    logger.info("Loaded valid cached session")
                    return True
                else:
                    logger.warning("Cached session expired")
                    self.redis_coord.cache_delete(self.session_key)
            
            return False
            
        except Exception as e:
            logger.error(f"Error loading cached session: {e}")
            return False
    
    def _save_session(self, session: KiteSession):
        """Save session to Redis cache"""
        try:
            self.session_data = session
            self.access_token = session.access_token
            
            # Cache until expiry
            ttl_seconds = int(session.time_to_expiry.total_seconds())
            self.redis_coord.cache_set(self.session_key, session.to_dict(), ttl_seconds)
            
            logger.info(f"Session cached for user {session.user_id}")
            
        except Exception as e:
            logger.error(f"Error saving session: {e}")
    
    def get_login_url(self) -> str:
        """
        Generate login URL for Kite Connect OAuth flow
        
        Returns:
            Login URL that user needs to visit
        """
        params = {
            "api_key": self.api_key,
            "v": 3,
        }
        
        login_url = f"{self._login_url}?{urllib.parse.urlencode(params)}"
        logger.info(f"Generated login URL: {login_url}")
        
        return login_url
    
    def open_login_url(self) -> str:
        """
        Open login URL in default browser
        
        Returns:
            Login URL
        """
        login_url = self.get_login_url()
        
        try:
            webbrowser.open(login_url)
            logger.info("Opened login URL in browser")
        except Exception as e:
            logger.warning(f"Could not open browser: {e}")
            print(f"\nPlease visit this URL to login:\n{login_url}\n")
        
        return login_url
    
    def generate_session(self, request_token: str, api_secret: str = None) -> KiteSession:
        """
        Generate access token and create session from request token
        
        Args:
            request_token: Request token obtained after login
            api_secret: API secret (if not provided during initialization)
            
        Returns:
            KiteSession object with access token and user info
            
        Raises:
            KiteAuthenticationError: If authentication fails
        """
        if not api_secret:
            api_secret = self.api_secret
            
        if not api_secret:
            raise KiteAuthenticationError("API secret is required to generate session")
        
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
        
        try:
            response = self.session.post(url, data=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("status") != "success":
                raise KiteAuthenticationError(f"Token generation failed: {result.get('message', 'Unknown error')}")
            
            data = result["data"]
            
            # Create session object
            session = KiteSession(
                user_id=data["user_id"],
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token", ""),
                login_time=datetime.now(),
                expires_at=datetime.now() + timedelta(hours=24),  # Kite tokens valid for 24 hours
                api_key=self.api_key,
                enctoken=data.get("enctoken"),
                public_token=data.get("public_token"),
                user_name=data.get("user_name"),
                user_shortname=data.get("user_shortname"),
                email=data.get("email")
            )
            
            # Save session
            self._save_session(session)
            
            logger.info(f"Session generated successfully for user: {session.user_id}")
            return session
            
        except requests.exceptions.RequestException as e:
            raise KiteAuthenticationError(f"Network error during token generation: {e}")
        except json.JSONDecodeError as e:
            raise KiteAuthenticationError(f"Invalid response format: {e}")
        except Exception as e:
            raise KiteAuthenticationError(f"Unexpected error: {e}")
    
    def invalidate_access_token(self, access_token: str = None) -> bool:
        """
        Invalidate access token
        
        Args:
            access_token: Token to invalidate (uses current if not specified)
            
        Returns:
            True if successful
        """
        if not access_token:
            access_token = self.access_token
            
        if not access_token:
            logger.warning("No access token to invalidate")
            return False
        
        url = f"{self._root_url}{self._routes['api.token.invalidate']}"
        headers = {
            "X-Kite-Version": "3",
            "Authorization": f"token {self.api_key}:{access_token}"
        }
        
        try:
            response = self.session.delete(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Clear cached session
            self.redis_coord.cache_delete(self.session_key)
            self.session_data = None
            self.access_token = None
            
            logger.info("Access token invalidated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error invalidating token: {e}")
            return False
    
    def renew_access_token(self, refresh_token: str = None, api_secret: str = None) -> Optional[str]:
        """
        Renew access token using refresh token
        
        Args:
            refresh_token: Refresh token (uses cached if available)
            api_secret: API secret
            
        Returns:
            New access token or None if renewal failed
        """
        if not refresh_token and self.session_data:
            refresh_token = self.session_data.refresh_token
            
        if not api_secret:
            api_secret = self.api_secret
            
        if not refresh_token or not api_secret:
            logger.error("Refresh token and API secret required for renewal")
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
        
        try:
            response = self.session.post(url, data=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("status") != "success":
                logger.error(f"Token renewal failed: {result.get('message')}")
                return None
            
            new_access_token = result["data"]["access_token"]
            
            # Update session
            if self.session_data:
                self.session_data.access_token = new_access_token
                self.session_data.expires_at = datetime.now() + timedelta(hours=24)
                self._save_session(self.session_data)
            
            self.access_token = new_access_token
            
            logger.info("Access token renewed successfully")
            return new_access_token
            
        except Exception as e:
            logger.error(f"Error renewing token: {e}")
            return None
    
    def get_profile(self) -> Optional[Dict[str, Any]]:
        """
        Get user profile information
        
        Returns:
            User profile dict or None if failed
        """
        if not self.access_token:
            logger.error("No access token available")
            return None
        
        url = f"{self._root_url}{self._routes['user.profile']}"
        headers = {
            "X-Kite-Version": "3",
            "Authorization": f"token {self.api_key}:{self.access_token}"
        }
        
        try:
            response = self.session.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("status") != "success":
                logger.error(f"Profile fetch failed: {result.get('message')}")
                return None
            
            return result["data"]
            
        except Exception as e:
            logger.error(f"Error fetching profile: {e}")
            return None
    
    def is_session_valid(self) -> bool:
        """
        Check if current session is valid
        
        Returns:
            True if session is valid and active
        """
        if not self.access_token or not self.session_data:
            return False
        
        if not self.session_data.is_valid:
            return False
        
        # Verify with API call
        try:
            profile = self.get_profile()
            return profile is not None
            
        except Exception:
            return False
    
    def ensure_valid_session(self) -> bool:
        """
        Ensure we have a valid session, attempt renewal if needed
        
        Returns:
            True if valid session is available
        """
        if self.is_session_valid():
            return True
        
        # Try to renew if we have refresh token
        if self.session_data and self.session_data.refresh_token:
            logger.info("Attempting to renew expired session")
            renewed = self.renew_access_token()
            if renewed:
                return True
        
        # Session cannot be renewed
        logger.warning("Session expired and cannot be renewed - manual login required")
        return False
    
    def get_session_status(self) -> Dict[str, Any]:
        """
        Get current session status information
        
        Returns:
            Session status dict
        """
        status = {
            "has_api_key": bool(self.api_key),
            "has_api_secret": bool(self.api_secret),
            "has_access_token": bool(self.access_token),
            "has_session_data": bool(self.session_data),
            "is_valid": False,
            "user_id": None,
            "expires_at": None,
            "time_to_expiry": None
        }
        
        if self.session_data:
            status.update({
                "is_valid": self.session_data.is_valid,
                "user_id": self.session_data.user_id,
                "expires_at": self.session_data.expires_at.isoformat(),
                "time_to_expiry": str(self.session_data.time_to_expiry)
            })
        
        return status

class KiteAuthManager:
    """
    High-level authentication manager for Kite Connect.
    Handles the complete authentication workflow with user interaction.
    """
    
    def __init__(self, api_key: str = None, api_secret: str = None):
        """
        Initialize authentication manager
        
        Args:
            api_key: Kite Connect API key (from settings if not provided)
            api_secret: Kite Connect API secret (from settings if not provided)
        """
        settings = get_settings()
        
        self.api_key = api_key or settings.broker.api_key
        self.api_secret = api_secret or settings.broker.api_secret
        
        if not self.api_key:
            raise ValueError("API key is required")
        
        self.kite = KiteConnect(self.api_key, self.api_secret)
        
        logger.info("Kite authentication manager initialized")
    
    def interactive_login(self) -> Optional[KiteSession]:
        """
        Perform interactive login process
        
        Returns:
            KiteSession if successful, None otherwise
        """
        try:
            # Check if we already have a valid session
            if self.kite.is_session_valid():
                logger.info("Using existing valid session")
                return self.kite.session_data
            
            print("\n" + "="*60)
            print("🔐 KITE CONNECT AUTHENTICATION REQUIRED")
            print("="*60)
            
            # Step 1: Open login URL
            print("\n1️⃣  Opening Kite Connect login page...")
            login_url = self.kite.open_login_url()
            
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
            
            # Step 3: Generate session
            print("\n🔄 Generating access token...")
            session = self.kite.generate_session(request_token, self.api_secret)
            
            # Step 4: Verify session
            print("✅ Verifying session...")
            profile = self.kite.get_profile()
            
            if profile:
                print("\n✅ Authentication successful!")
                print(f"   👤 User: {profile.get('user_name', session.user_id)}")
                print(f"   📧 Email: {profile.get('email', 'N/A')}")
                print(f"   ⏰ Token valid until: {session.expires_at}")
                print(f"   🔑 Access token: {session.access_token[:20]}...")
                
                return session
            else:
                print("❌ Session verification failed")
                return None
                
        except KiteAuthenticationError as e:
            print(f"❌ Authentication error: {e}")
            return None
        except KeyboardInterrupt:
            print("\n⚠️  Authentication cancelled by user")
            return None
        except Exception as e:
            print(f"❌ Unexpected error during authentication: {e}")
            logger.error(f"Interactive login error: {e}")
            return None
    
    def auto_authenticate(self) -> bool:
        """
        Attempt automatic authentication using cached session or environment tokens
        
        Returns:
            True if authentication successful
        """
        try:
            # Check for existing valid session
            if self.kite.is_session_valid():
                logger.info("Using existing valid session")
                return True
            
            # Check for access token in environment/settings
            settings = get_settings()
            if settings.broker.access_token:
                logger.info("Trying access token from settings")
                self.kite.access_token = settings.broker.access_token
                
                if self.kite.is_session_valid():
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
    
    def get_authenticated_client(self) -> Optional[KiteConnect]:
        """
        Get authenticated Kite Connect client
        
        Returns:
            Authenticated KiteConnect client or None
        """
        if self.auto_authenticate():
            return self.kite
        
        # Try interactive login
        print("\n🔐 Automatic authentication failed. Manual login required.")
        session = self.interactive_login()
        
        if session:
            return self.kite
        
        return None
    
    def logout(self) -> bool:
        """
        Logout and invalidate current session
        
        Returns:
            True if successful
        """
        try:
            success = self.kite.invalidate_access_token()
            if success:
                print("✅ Logged out successfully")
                logger.info("User logged out")
            return success
            
        except Exception as e:
            logger.error(f"Logout error: {e}")
            return False

# Convenience functions for easy integration

def get_kite_client(interactive: bool = True) -> Optional[KiteConnect]:
    """
    Get authenticated Kite Connect client
    
    Args:
        interactive: Whether to allow interactive login if needed
        
    Returns:
        Authenticated KiteConnect client or None
    """
    try:
        manager = KiteAuthManager()
        
        if interactive:
            return manager.get_authenticated_client()
        else:
            return manager.kite if manager.auto_authenticate() else None
            
    except Exception as e:
        logger.error(f"Error getting Kite client: {e}")
        return None

def interactive_kite_login() -> Optional[KiteSession]:
    """
    Perform interactive Kite Connect login
    
    Returns:
        KiteSession if successful
    """
    try:
        manager = KiteAuthManager()
        return manager.interactive_login()
        
    except Exception as e:
        logger.error(f"Interactive login error: {e}")
        return None

def check_kite_session() -> Dict[str, Any]:
    """
    Check current Kite Connect session status
    
    Returns:
        Session status dictionary
    """
    try:
        settings = get_settings()
        kite = KiteConnect(settings.broker.api_key, settings.broker.api_secret)
        return kite.get_session_status()
        
    except Exception as e:
        logger.error(f"Session check error: {e}")
        return {"error": str(e)}

# CLI interface for standalone authentication
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Kite Connect Authentication CLI")
    parser.add_argument("--login", action="store_true", help="Perform interactive login")
    parser.add_argument("--status", action="store_true", help="Check session status")
    parser.add_argument("--logout", action="store_true", help="Logout and invalidate session")
    parser.add_argument("--api-key", help="API key (optional)")
    parser.add_argument("--api-secret", help="API secret (optional)")
    
    args = parser.parse_args()
    
    try:
        if args.login:
            session = interactive_kite_login()
            if session:
                print(f"\n✅ Login successful for user: {session.user_id}")
            else:
                print("\n❌ Login failed")
                sys.exit(1)
                
        elif args.status:
            status = check_kite_session()
            print("\n📊 Session Status:")
            for key, value in status.items():
                print(f"   {key}: {value}")
                
        elif args.logout:
            manager = KiteAuthManager(args.api_key, args.api_secret)
            if manager.logout():
                print("\n✅ Logout successful")
            else:
                print("\n❌ Logout failed")
                
        else:
            # Default: try to get authenticated client
            client = get_kite_client()
            if client:
                profile = client.get_profile()
                print(f"\n✅ Authenticated as: {profile.get('user_name', 'Unknown')}")
            else:
                print("\n❌ Authentication failed")
                
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)