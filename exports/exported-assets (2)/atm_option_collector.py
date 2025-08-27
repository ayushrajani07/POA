"""
ATM Option Data Collector - High-performance market data collection service.
Integrates with broker APIs and coordinates data flow to processing services.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import aiohttp
import json
from pathlib import Path
import sys

# Import shared utilities
sys.path.append(str(Path(__file__).parent.parent.parent))

from shared.config.settings import get_settings
from shared.utils.time_utils import get_time_utils, now_csv_format, is_market_open
from shared.utils.coordination import get_redis_coordinator
from shared.constants.market_constants import INDICES, BUCKETS, STRIKE_OFFSETS
from shared.types.option_data import OptionLegData, CollectionResult
from services.processing.writers.consolidated_csv_writer import get_consolidated_writer

logger = logging.getLogger(__name__)

@dataclass
class InstrumentInfo:
    """Instrument metadata"""
    token: str
    tradingsymbol: str
    index: str
    bucket: str
    side: str
    strike: float
    expiry: str
    offset: int

class BrokerAPIClient:
    """High-performance broker API client with connection pooling"""
    
    def __init__(self):
        self.settings = get_settings()
        self.time_utils = get_time_utils()
        self.session: Optional[aiohttp.ClientSession] = None
        self.base_url = "https://api.kite.trade"
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = self.settings.broker.rate_limit_delay
        
        # Performance tracking
        self.request_count = 0
        self.error_count = 0
        self.avg_response_time = 0.0
    
    async def initialize(self):
        """Initialize HTTP session with optimized settings"""
        connector = aiohttp.TCPConnector(
            limit=100,  # Connection pool size
            limit_per_host=20,
            ttl_dns_cache=300,
            use_dns_cache=True,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )
        
        timeout = aiohttp.ClientTimeout(
            total=self.settings.broker.request_timeout,
            connect=10,
            sock_read=10
        )
        
        headers = {
            'X-Kite-Version': '3',
            'Authorization': f'token {self.settings.broker.api_key}:{self.settings.broker.access_token}',
            'User-Agent': 'OP-Trading-Platform/1.0'
        }
        
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=headers
        )
        
        logger.info("Broker API client initialized")
    
    async def close(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make rate-limited API request with retry logic"""
        if not self.session:
            await self.initialize()
        
        # Rate limiting
        now = time.time()
        time_since_last = now - self.last_request_time
        if time_since_last < self.min_request_interval:
            await asyncio.sleep(self.min_request_interval - time_since_last)
        
        url = f"{self.base_url}{endpoint}"
        retry_count = 0
        max_retries = self.settings.broker.max_retries
        
        while retry_count <= max_retries:
            try:
                start_time = time.time()
                self.last_request_time = start_time
                
                async with self.session.request(method, url, **kwargs) as response:
                    response_time = time.time() - start_time
                    self.request_count += 1
                    
                    # Update average response time
                    self.avg_response_time = (
                        (self.avg_response_time * (self.request_count - 1) + response_time) 
                        / self.request_count
                    )
                    
                    if response.status == 200:
                        data = await response.json()
                        if data.get('status') == 'success':
                            return data.get('data', {})
                        else:
                            raise Exception(f"API error: {data.get('message', 'Unknown error')}")
                    elif response.status == 429:  # Rate limit
                        retry_after = int(response.headers.get('Retry-After', 1))
                        logger.warning(f"Rate limited, waiting {retry_after} seconds")
                        await asyncio.sleep(retry_after)
                        retry_count += 1
                        continue
                    else:
                        response.raise_for_status()
            
            except asyncio.TimeoutError:
                logger.warning(f"Request timeout for {endpoint}, retry {retry_count + 1}")
                retry_count += 1
                if retry_count <= max_retries:
                    await asyncio.sleep(2 ** retry_count)  # Exponential backoff
            except Exception as e:
                self.error_count += 1
                logger.error(f"Request failed for {endpoint}: {e}")
                if retry_count >= max_retries:
                    raise
                retry_count += 1
                await asyncio.sleep(2 ** retry_count)
        
        raise Exception(f"Max retries exceeded for {endpoint}")
    
    async def get_quote(self, instruments: List[str]) -> Dict[str, Any]:
        """Get quotes for multiple instruments"""
        if not instruments:
            return {}
        
        # Batch instruments to avoid URL length limits
        batch_size = 200
        all_quotes = {}
        
        for i in range(0, len(instruments), batch_size):
            batch = instruments[i:i + batch_size]
            instruments_param = "&".join(f"i={instrument}" for instrument in batch)
            
            try:
                quotes = await self._make_request('GET', f'/quote?{instruments_param}')
                if isinstance(quotes, dict):
                    all_quotes.update(quotes)
            except Exception as e:
                logger.error(f"Failed to get quotes for batch {i//batch_size + 1}: {e}")
                # Continue with other batches
        
        return all_quotes
    
    async def get_instruments(self, exchange: str = "NFO") -> List[Dict[str, Any]]:
        """Get instrument master"""
        try:
            instruments = await self._make_request('GET', f'/instruments/{exchange}')
            return instruments if isinstance(instruments, list) else []
        except Exception as e:
            logger.error(f"Failed to get instruments: {e}")
            return []

class InstrumentManager:
    """Manages instrument mapping and selection"""
    
    def __init__(self, broker_client: BrokerAPIClient):
        self.broker_client = broker_client
        self.redis_coord = get_redis_coordinator()
        self.time_utils = get_time_utils()
        
        # Cache instruments data
        self.instruments_cache: Dict[str, List[InstrumentInfo]] = {}
        self.last_cache_update = 0
        self.cache_ttl = 3600  # 1 hour
    
    async def load_instruments(self, force_refresh: bool = False) -> bool:
        """Load and cache instrument data"""
        now = time.time()
        
        # Check if cache is still valid
        if not force_refresh and (now - self.last_cache_update) < self.cache_ttl:
            if self.instruments_cache:
                return True
        
        try:
            # Try to load from Redis cache first
            if not force_refresh:
                cached_data = self.redis_coord.cache_get("instruments_master")
                if cached_data:
                    self.instruments_cache = self._parse_cached_instruments(cached_data)
                    self.last_cache_update = now
                    logger.info(f"Loaded {len(self.instruments_cache)} instrument groups from cache")
                    return True
            
            # Fetch fresh data from broker
            logger.info("Fetching fresh instrument data from broker...")
            raw_instruments = await self.broker_client.get_instruments("NFO")
            
            if not raw_instruments:
                logger.error("No instruments received from broker")
                return False
            
            # Parse and categorize instruments
            self.instruments_cache = self._parse_instruments(raw_instruments)
            
            # Cache for future use
            self.redis_coord.cache_set("instruments_master", self.instruments_cache, self.cache_ttl)
            self.last_cache_update = now
            
            total_instruments = sum(len(group) for group in self.instruments_cache.values())
            logger.info(f"Loaded {total_instruments} instruments across {len(self.instruments_cache)} groups")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load instruments: {e}")
            return False
    
    def _parse_instruments(self, raw_instruments: List[Dict[str, Any]]) -> Dict[str, List[InstrumentInfo]]:
        """Parse raw instruments into organized structure"""
        instruments = {}
        
        for raw_instrument in raw_instruments:
            try:
                # Skip non-option instruments
                if raw_instrument.get('instrument_type') not in ['CE', 'PE']:
                    continue
                
                # Extract instrument info
                name = raw_instrument.get('name', '').upper()
                if name not in INDICES:
                    continue
                
                expiry_str = raw_instrument.get('expiry', '')
                if not expiry_str:
                    continue
                
                strike = float(raw_instrument.get('strike', 0))
                if strike <= 0:
                    continue
                
                # Determine bucket based on expiry
                bucket = self._determine_bucket(expiry_str, name)
                if not bucket:
                    continue
                
                # Determine offset (simplified)
                offset = self._estimate_offset(strike, name)
                
                side = 'CALL' if raw_instrument.get('instrument_type') == 'CE' else 'PUT'
                
                instrument_info = InstrumentInfo(
                    token=str(raw_instrument.get('instrument_token', '')),
                    tradingsymbol=raw_instrument.get('tradingsymbol', ''),
                    index=name,
                    bucket=bucket,
                    side=side,
                    strike=strike,
                    expiry=expiry_str,
                    offset=offset
                )
                
                # Group by index-bucket-side
                key = f"{name}_{bucket}_{side}"
                if key not in instruments:
                    instruments[key] = []
                instruments[key].append(instrument_info)
                
            except Exception as e:
                logger.warning(f"Failed to parse instrument {raw_instrument}: {e}")
                continue
        
        # Sort instruments by strike in each group
        for key in instruments:
            instruments[key].sort(key=lambda x: x.strike)
        
        return instruments
    
    def _parse_cached_instruments(self, cached_data: Dict[str, Any]) -> Dict[str, List[InstrumentInfo]]:
        """Parse cached instruments data"""
        instruments = {}
        for key, instrument_list in cached_data.items():
            instruments[key] = [
                InstrumentInfo(**instrument_data) for instrument_data in instrument_list
            ]
        return instruments
    
    def _determine_bucket(self, expiry_str: str, index: str) -> Optional[str]:
        """Determine bucket based on expiry date"""
        try:
            expiry_date = datetime.strptime(expiry_str, '%Y-%m-%d').date()
            today = self.time_utils.get_current_date_ist()
            days_to_expiry = (expiry_date - today).days
            
            if days_to_expiry <= 7:
                return "this_week"
            elif days_to_expiry <= 14:
                return "next_week"
            elif days_to_expiry <= 35:
                return "this_month"
            elif days_to_expiry <= 65:
                return "next_month"
            else:
                return None  # Too far out
                
        except Exception:
            return None
    
    def _estimate_offset(self, strike: float, index: str) -> int:
        """Estimate strike offset (simplified - would need current ATM data)"""
        # This is a simplified estimation - in production, you'd use current ATM prices
        base_prices = {"NIFTY": 25000, "BANKNIFTY": 52000, "SENSEX": 82000}
        step_sizes = {"NIFTY": 50, "BANKNIFTY": 100, "SENSEX": 100}
        
        base_price = base_prices.get(index, 25000)
        step_size = step_sizes.get(index, 50)
        
        atm_strike = round(base_price / step_size) * step_size
        offset = int((strike - atm_strike) / step_size)
        
        # Limit to reasonable range
        return max(-10, min(10, offset))
    
    def get_instruments_for_collection(self, target_offsets: List[int] = None) -> List[InstrumentInfo]:
        """Get instruments that should be collected"""
        if not self.instruments_cache:
            return []
        
        if target_offsets is None:
            target_offsets = STRIKE_OFFSETS
        
        instruments_to_collect = []
        
        for key, instrument_list in self.instruments_cache.items():
            # Filter by target offsets
            for instrument in instrument_list:
                if instrument.offset in target_offsets:
                    instruments_to_collect.append(instrument)
        
        return instruments_to_collect

class ATMOptionCollector:
    """Main collection service orchestrator"""
    
    def __init__(self):
        self.settings = get_settings()
        self.time_utils = get_time_utils()
        self.redis_coord = get_redis_coordinator()
        
        # Initialize components
        self.broker_client = BrokerAPIClient()
        self.instrument_manager = InstrumentManager(self.broker_client)
        self.csv_writer = get_consolidated_writer()
        
        # Collection state
        self.is_collecting = False
        self.collection_start_time = None
        self.last_collection_time = 0
        
        # Performance metrics
        self.collection_stats = {
            'total_collections': 0,
            'successful_collections': 0,
            'failed_collections': 0,
            'total_legs_collected': 0,
            'avg_collection_time': 0.0,
            'last_error': None
        }
    
    async def initialize(self):
        """Initialize the collection service"""
        logger.info("Initializing ATM Option Collector...")
        
        try:
            # Initialize broker client
            await self.broker_client.initialize()
            
            # Load instruments
            success = await self.instrument_manager.load_instruments()
            if not success:
                raise Exception("Failed to load instruments")
            
            # Register service health
            await self._update_service_health("INITIALIZING")
            
            logger.info("ATM Option Collector initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize collector: {e}")
            await self._update_service_health("FAILED", str(e))
            return False
    
    async def start_collection(self):
        """Start the collection loop"""
        if self.is_collecting:
            logger.warning("Collection already running")
            return
        
        self.is_collecting = True
        self.collection_start_time = time.time()
        
        logger.info("Starting option data collection...")
        await self._update_service_health("RUNNING")
        
        try:
            while self.is_collecting:
                if is_market_open():
                    await self._collect_market_data()
                else:
                    logger.info("Market closed, skipping collection")
                    await asyncio.sleep(60)  # Check again in 1 minute
                    continue
                
                # Wait for next collection interval
                interval = self.settings.service.collection_loop_interval
                await asyncio.sleep(interval)
                
        except Exception as e:
            logger.error(f"Collection loop error: {e}")
            await self._update_service_health("ERROR", str(e))
        finally:
            self.is_collecting = False
            await self._update_service_health("STOPPED")
    
    async def stop_collection(self):
        """Stop the collection loop"""
        logger.info("Stopping option data collection...")
        self.is_collecting = False
        await self.broker_client.close()
    
    async def _collect_market_data(self) -> CollectionResult:
        """Collect market data for current minute"""
        collection_start = time.time()
        
        try:
            # Get instruments to collect
            instruments = self.instrument_manager.get_instruments_for_collection()
            if not instruments:
                logger.warning("No instruments found for collection")
                return CollectionResult(
                    success=False,
                    legs_collected=0,
                    processing_time_ms=0,
                    error_message="No instruments available"
                )
            
            # Prepare instrument tokens for API call
            tokens = [inst.token for inst in instruments if inst.token]
            if not tokens:
                logger.warning("No valid tokens for collection")
                return CollectionResult(success=False, legs_collected=0)
            
            # Get market quotes
            quotes = await self.broker_client.get_quote(tokens)
            if not quotes:
                logger.warning("No quotes received from broker")
                return CollectionResult(success=False, legs_collected=0)
            
            # Convert quotes to OptionLegData
            option_legs = self._convert_quotes_to_legs(instruments, quotes)
            
            if not option_legs:
                logger.warning("No option legs created from quotes")
                return CollectionResult(success=False, legs_collected=0)
            
            # Process and store data
            write_result = await self.csv_writer.process_and_write(
                option_legs, 
                write_legs=True, 
                write_merged=True, 
                write_json=False  # Disable JSON for performance
            )
            
            # Update metrics
            collection_time = (time.time() - collection_start) * 1000
            self.collection_stats['total_collections'] += 1
            self.collection_stats['successful_collections'] += 1
            self.collection_stats['total_legs_collected'] += len(option_legs)
            
            # Update average collection time
            total_collections = self.collection_stats['total_collections']
            self.collection_stats['avg_collection_time'] = (
                (self.collection_stats['avg_collection_time'] * (total_collections - 1) + collection_time)
                / total_collections
            )
            
            self.last_collection_time = time.time()
            
            logger.info(f"Collected {len(option_legs)} legs in {collection_time:.1f}ms")
            
            # Publish collection event
            await self._publish_collection_event(option_legs)
            
            return CollectionResult(
                success=True,
                legs_collected=len(option_legs),
                processing_time_ms=int(collection_time),
                files_updated=write_result.get('files_updated', 0)
            )
            
        except Exception as e:
            logger.error(f"Collection failed: {e}")
            self.collection_stats['failed_collections'] += 1
            self.collection_stats['last_error'] = str(e)
            await self._update_service_health("ERROR", str(e))
            
            return CollectionResult(
                success=False,
                legs_collected=0,
                processing_time_ms=int((time.time() - collection_start) * 1000),
                error_message=str(e)
            )
    
    def _convert_quotes_to_legs(self, instruments: List[InstrumentInfo], 
                               quotes: Dict[str, Any]) -> List[OptionLegData]:
        """Convert broker quotes to OptionLegData objects"""
        option_legs = []
        current_time = now_csv_format()
        
        for instrument in instruments:
            if instrument.token not in quotes:
                continue
            
            quote = quotes[instrument.token]
            
            try:
                # Extract quote data
                last_price = float(quote.get('last_price', 0))
                if last_price <= 0:
                    continue
                
                # Calculate ATM strike (simplified)
                base_prices = {"NIFTY": 25000, "BANKNIFTY": 52000, "SENSEX": 82000}
                atm_strike = base_prices.get(instrument.index, 25000)
                
                option_leg = OptionLegData(
                    ts=current_time,
                    index=instrument.index,
                    bucket=instrument.bucket,
                    expiry=instrument.expiry,
                    side=instrument.side,
                    atm_strike=float(atm_strike),
                    strike=instrument.strike,
                    strike_offset=instrument.offset,
                    last_price=last_price,
                    bid=float(quote.get('depth', {}).get('buy', [{}])[0].get('price', 0) or 0),
                    ask=float(quote.get('depth', {}).get('sell', [{}])[0].get('price', 0) or 0),
                    volume=int(quote.get('volume', 0)),
                    oi=int(quote.get('oi', 0)),
                    # Greeks would come from different API calls in real implementation
                )
                
                option_legs.append(option_leg)
                
            except Exception as e:
                logger.warning(f"Failed to convert quote for {instrument.tradingsymbol}: {e}")
                continue
        
        return option_legs
    
    async def _publish_collection_event(self, option_legs: List[OptionLegData]):
        """Publish collection event for other services"""
        try:
            event_data = {
                'event_type': 'data_collected',
                'timestamp': self.time_utils.get_metadata_timestamp(),
                'legs_count': len(option_legs),
                'indices': list(set(leg.index for leg in option_legs)),
                'collection_stats': self.collection_stats
            }
            
            self.redis_coord.publish_message("data_collection_events", event_data)
            
        except Exception as e:
            logger.warning(f"Failed to publish collection event: {e}")
    
    async def _update_service_health(self, status: str, error: str = None):
        """Update service health status"""
        try:
            health_data = {
                'service_name': 'collection',
                'status': status,
                'uptime_seconds': time.time() - self.collection_start_time if self.collection_start_time else 0,
                'is_collecting': self.is_collecting,
                'last_collection_time': self.last_collection_time,
                'stats': self.collection_stats,
                'broker_stats': {
                    'request_count': self.broker_client.request_count,
                    'error_count': self.broker_client.error_count,
                    'avg_response_time': self.broker_client.avg_response_time
                }
            }
            
            if error:
                health_data['last_error'] = error
            
            self.redis_coord.set_service_health('collection', health_data)
            
        except Exception as e:
            logger.warning(f"Failed to update service health: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get collection statistics"""
        return {
            'collection_stats': self.collection_stats,
            'is_collecting': self.is_collecting,
            'uptime_seconds': time.time() - self.collection_start_time if self.collection_start_time else 0,
            'broker_stats': {
                'request_count': self.broker_client.request_count,
                'error_count': self.broker_client.error_count,
                'avg_response_time': self.broker_client.avg_response_time
            }
        }

# Service entry point
async def main():
    """Main service entry point"""
    import signal
    
    collector = ATMOptionCollector()
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        asyncio.create_task(collector.stop_collection())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Initialize and start collection
    if await collector.initialize():
        await collector.start_collection()
    else:
        logger.error("Failed to initialize collection service")
        return 1
    
    return 0

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    exit_code = asyncio.run(main())