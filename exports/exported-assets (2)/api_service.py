"""
FastAPI REST API service for the OP trading platform.
Provides endpoints for data access, analytics, and system monitoring.
"""

import asyncio
import logging
import time
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
import json
import sys

from fastapi import FastAPI, HTTPException, Depends, Query, Path as PathParam, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
import uvicorn

# Import shared utilities
sys.path.append(str(Path(__file__).parent.parent.parent))

from shared.config.settings import get_settings
from shared.utils.time_utils import get_time_utils, now_csv_format, is_market_open
from shared.utils.coordination import get_redis_coordinator
from shared.constants.market_constants import INDICES, BUCKETS, STRIKE_OFFSETS, INDEX_SPECS
from shared.types.option_data import (
    OptionLegData, MergedOptionData, ServiceHealth, Alert, APIResponse
)
from services.processing.writers.consolidated_csv_writer import get_consolidated_writer

# Pydantic models for API
class HealthResponse(BaseModel):
    service_name: str
    status: str
    uptime_seconds: float
    last_updated: str
    metrics: Dict[str, Any] = {}
    version: str = "1.0.0"

class OptionLegResponse(BaseModel):
    ts: str
    index: str
    bucket: str
    expiry: str
    side: str
    atm_strike: float
    strike: float
    strike_offset: int
    last_price: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[int] = None
    oi: Optional[int] = None
    iv: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None

class OptionChainResponse(BaseModel):
    index: str
    bucket: str
    timestamp: str
    atm_strike: float
    legs: List[OptionLegResponse]
    total_legs: int

class AnalyticsResponse(BaseModel):
    index: str
    analytics_type: str
    timestamp: str
    data: Dict[str, Any]
    computation_time_ms: Optional[int] = None

class SystemStatsResponse(BaseModel):
    timestamp: str
    services: Dict[str, HealthResponse]
    system_metrics: Dict[str, Any]
    alerts: List[Dict[str, Any]]

class MarketStatusResponse(BaseModel):
    status: str  # OPEN, CLOSED, PRE_MARKET, POST_MARKET
    is_open: bool
    next_open: Optional[str] = None
    session_remaining_minutes: Optional[int] = None
    timestamp: str

# API Configuration
logger = logging.getLogger(__name__)
settings = get_settings()
time_utils = get_time_utils()
redis_coord = get_redis_coordinator()
security = HTTPBearer(auto_error=False)

# Initialize FastAPI
app = FastAPI(
    title="OP Trading Platform API",
    description="REST API for accessing options trading data and analytics",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

# API Key authentication (simplified)
async def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify API key for authentication"""
    if settings.environment == "development":
        return True  # Skip auth in development
    
    if not credentials:
        raise HTTPException(status_code=401, detail="API key required")
    
    # In production, verify against stored API keys
    valid_keys = ["your-api-key-here"]  # Would come from database/config
    
    if credentials.credentials not in valid_keys:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return True

class APIService:
    """Main API service class"""
    
    def __init__(self):
        self.settings = get_settings()
        self.csv_writer = get_consolidated_writer()
        self.request_count = 0
        self.error_count = 0
        self.start_time = time.time()
    
    async def load_option_data(self, index: str, bucket: str = None, 
                             date_filter: date = None) -> List[OptionLegData]:
        """Load option data from CSV files"""
        try:
            date_str = (date_filter or date.today()).isoformat()
            csv_root = self.settings.data.csv_data_root
            option_legs = []
            
            buckets_to_load = [bucket] if bucket else BUCKETS
            
            for bucket_name in buckets_to_load:
                for offset in STRIKE_OFFSETS:
                    offset_str = f"atm_p{offset}" if offset > 0 else ("atm" if offset == 0 else f"atm_m{abs(offset)}")
                    
                    csv_file = csv_root / index / bucket_name / offset_str / f"{date_str}_legs.csv"
                    
                    if csv_file.exists():
                        rows = self.csv_writer.read_file_incrementally(csv_file, 0)
                        
                        for row in rows:
                            try:
                                leg = OptionLegData(
                                    ts=row['ts'],
                                    index=row['index'],
                                    bucket=row['bucket'],
                                    expiry=row['expiry'],
                                    side=row['side'],
                                    atm_strike=float(row['atm_strike']),
                                    strike=float(row['strike']),
                                    strike_offset=int(row['strike_offset']),
                                    last_price=float(row['last_price']),
                                    bid=float(row.get('bid', 0)) if row.get('bid') else None,
                                    ask=float(row.get('ask', 0)) if row.get('ask') else None,
                                    volume=int(row.get('volume', 0)) if row.get('volume') else None,
                                    oi=int(row.get('oi', 0)) if row.get('oi') else None,
                                    iv=float(row.get('iv', 0)) if row.get('iv') else None,
                                    delta=float(row.get('delta', 0)) if row.get('delta') else None,
                                    gamma=float(row.get('gamma', 0)) if row.get('gamma') else None,
                                    theta=float(row.get('theta', 0)) if row.get('theta') else None,
                                    vega=float(row.get('vega', 0)) if row.get('vega') else None
                                )
                                option_legs.append(leg)
                            except Exception as e:
                                logger.warning(f"Failed to parse row: {e}")
                                continue
            
            return option_legs
            
        except Exception as e:
            logger.error(f"Failed to load option data: {e}")
            return []
    
    async def load_analytics_data(self, analytics_type: str, 
                                index: str = None) -> Dict[str, Any]:
        """Load analytics data from files"""
        try:
            date_str = date.today().isoformat()
            analytics_root = self.settings.data.csv_data_root.parent / "analytics"
            
            if index:
                analytics_file = analytics_root / analytics_type / f"{date_str}_{analytics_type}_{index.lower()}.json"
            else:
                analytics_file = analytics_root / analytics_type / f"{date_str}_{analytics_type}.json"
            
            if analytics_file.exists():
                with open(analytics_file, 'r') as f:
                    return json.load(f)
            
            return {}
            
        except Exception as e:
            logger.error(f"Failed to load analytics data: {e}")
            return {}

# Global API service instance
api_service = APIService()

# API Routes

@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint"""
    return {
        "service": "OP Trading Platform API",
        "version": "1.0.0",
        "status": "running",
        "timestamp": now_csv_format()
    }

@app.get("/health", response_model=SystemStatsResponse)
async def get_system_health(_: bool = Depends(verify_api_key)):
    """Get system health status"""
    try:
        api_service.request_count += 1
        
        # Get service health from Redis
        services = {}
        for service_name in ['collection', 'processing', 'analytics', 'monitoring']:
            health_data = redis_coord.get_service_health(service_name)
            if health_data:
                services[service_name] = HealthResponse(
                    service_name=service_name,
                    status=health_data.get('status', 'UNKNOWN'),
                    uptime_seconds=health_data.get('uptime_seconds', 0),
                    last_updated=health_data.get('timestamp', now_csv_format()),
                    metrics=health_data.get('metrics', {}),
                    version=health_data.get('version', '1.0.0')
                )
        
        # System metrics
        system_metrics = {
            "api_requests": api_service.request_count,
            "api_errors": api_service.error_count,
            "api_uptime_seconds": time.time() - api_service.start_time,
            "market_status": time_utils.get_market_status(),
            "is_market_open": is_market_open(),
            "active_services": len(services)
        }
        
        # Get active alerts (simplified)
        alerts = []  # Would load from alert system
        
        return SystemStatsResponse(
            timestamp=now_csv_format(),
            services=services,
            system_metrics=system_metrics,
            alerts=alerts
        )
        
    except Exception as e:
        api_service.error_count += 1
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/market-status", response_model=MarketStatusResponse)
async def get_market_status():
    """Get current market status"""
    try:
        market_status = time_utils.get_market_status()
        is_open = is_market_open()
        
        # Calculate session remaining time
        session_remaining = None
        if is_open:
            now = time_utils.now_ist()
            market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
            if now < market_close:
                session_remaining = int((market_close - now).total_seconds() / 60)
        
        return MarketStatusResponse(
            status=market_status,
            is_open=is_open,
            session_remaining_minutes=session_remaining,
            timestamp=now_csv_format()
        )
        
    except Exception as e:
        logger.error(f"Market status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/indices", response_model=List[str])
async def get_supported_indices():
    """Get list of supported indices"""
    return INDICES

@app.get("/indices/{index}/specs", response_model=Dict[str, Any])
async def get_index_specs(index: str = PathParam(..., description="Index symbol")):
    """Get specifications for an index"""
    if index.upper() not in INDICES:
        raise HTTPException(status_code=404, detail="Index not found")
    
    return INDEX_SPECS.get(index.upper(), {})

@app.get("/option-chain/{index}", response_model=OptionChainResponse)
async def get_option_chain(
    index: str = PathParam(..., description="Index symbol"),
    bucket: str = Query("this_week", description="Expiry bucket"),
    date_filter: Optional[str] = Query(None, description="Date filter (YYYY-MM-DD)"),
    _: bool = Depends(verify_api_key)
):
    """Get option chain for an index"""
    try:
        api_service.request_count += 1
        
        if index.upper() not in INDICES:
            raise HTTPException(status_code=404, detail="Index not found")
        
        if bucket not in BUCKETS:
            raise HTTPException(status_code=400, detail="Invalid bucket")
        
        # Parse date filter
        date_obj = None
        if date_filter:
            try:
                date_obj = datetime.strptime(date_filter, '%Y-%m-%d').date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format")
        
        # Load option data
        legs = await api_service.load_option_data(index.upper(), bucket, date_obj)
        
        if not legs:
            raise HTTPException(status_code=404, detail="No data found")
        
        # Convert to response format
        response_legs = [
            OptionLegResponse(**leg.to_dict()) for leg in legs
        ]
        
        # Calculate ATM strike
        atm_strike = legs[0].atm_strike if legs else 0.0
        
        return OptionChainResponse(
            index=index.upper(),
            bucket=bucket,
            timestamp=now_csv_format(),
            atm_strike=atm_strike,
            legs=response_legs,
            total_legs=len(response_legs)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        api_service.error_count += 1
        logger.error(f"Option chain request failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/option-data/{index}/latest", response_model=List[OptionLegResponse])
async def get_latest_option_data(
    index: str = PathParam(..., description="Index symbol"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    side: Optional[str] = Query(None, description="Option side (CALL/PUT)"),
    _: bool = Depends(verify_api_key)
):
    """Get latest option data for an index"""
    try:
        api_service.request_count += 1
        
        if index.upper() not in INDICES:
            raise HTTPException(status_code=404, detail="Index not found")
        
        if side and side.upper() not in ['CALL', 'PUT']:
            raise HTTPException(status_code=400, detail="Invalid option side")
        
        # Load recent data
        legs = await api_service.load_option_data(index.upper())
        
        # Filter by side if specified
        if side:
            legs = [leg for leg in legs if leg.side.upper() == side.upper()]
        
        # Sort by timestamp and limit
        legs.sort(key=lambda x: x.ts, reverse=True)
        legs = legs[:limit]
        
        return [OptionLegResponse(**leg.to_dict()) for leg in legs]
        
    except HTTPException:
        raise
    except Exception as e:
        api_service.error_count += 1
        logger.error(f"Latest option data request failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/analytics/{analytics_type}", response_model=AnalyticsResponse)
async def get_analytics(
    analytics_type: str = PathParam(..., description="Analytics type"),
    index: Optional[str] = Query(None, description="Index symbol"),
    _: bool = Depends(verify_api_key)
):
    """Get analytics data"""
    try:
        api_service.request_count += 1
        
        if index and index.upper() not in INDICES:
            raise HTTPException(status_code=404, detail="Index not found")
        
        # Load analytics data
        analytics_data = await api_service.load_analytics_data(
            analytics_type, index.upper() if index else None
        )
        
        if not analytics_data:
            raise HTTPException(status_code=404, detail="Analytics data not found")
        
        return AnalyticsResponse(
            index=index.upper() if index else "ALL",
            analytics_type=analytics_type,
            timestamp=analytics_data.get('timestamp', now_csv_format()),
            data=analytics_data.get('data', {}),
            computation_time_ms=analytics_data.get('metadata', {}).get('computation_time_ms')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        api_service.error_count += 1
        logger.error(f"Analytics request failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/analytics/{index}/greeks", response_model=Dict[str, Any])
async def get_greeks_summary(
    index: str = PathParam(..., description="Index symbol"),
    bucket: str = Query("this_week", description="Expiry bucket"),
    _: bool = Depends(verify_api_key)
):
    """Get Greeks summary for an index and bucket"""
    try:
        api_service.request_count += 1
        
        if index.upper() not in INDICES:
            raise HTTPException(status_code=404, detail="Index not found")
        
        if bucket not in BUCKETS:
            raise HTTPException(status_code=400, detail="Invalid bucket")
        
        # Load analytics data
        analytics_data = await api_service.load_analytics_data(
            f"realtime_{index.lower()}", index.upper()
        )
        
        greeks_key = f'greeks_{bucket}'
        if greeks_key not in analytics_data.get('data', {}):
            raise HTTPException(status_code=404, detail="Greeks data not found")
        
        return analytics_data['data'][greeks_key]
        
    except HTTPException:
        raise
    except Exception as e:
        api_service.error_count += 1
        logger.error(f"Greeks summary request failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/analytics/{index}/pcr", response_model=Dict[str, Any])
async def get_pcr_analysis(
    index: str = PathParam(..., description="Index symbol"),
    bucket: str = Query("this_week", description="Expiry bucket"),
    _: bool = Depends(verify_api_key)
):
    """Get Put-Call Ratio analysis"""
    try:
        api_service.request_count += 1
        
        if index.upper() not in INDICES:
            raise HTTPException(status_code=404, detail="Index not found")
        
        if bucket not in BUCKETS:
            raise HTTPException(status_code=400, detail="Invalid bucket")
        
        # Load analytics data
        analytics_data = await api_service.load_analytics_data(
            f"realtime_{index.lower()}", index.upper()
        )
        
        pcr_key = f'pcr_{bucket}'
        if pcr_key not in analytics_data.get('data', {}):
            raise HTTPException(status_code=404, detail="PCR data not found")
        
        return analytics_data['data'][pcr_key]
        
    except HTTPException:
        raise
    except Exception as e:
        api_service.error_count += 1
        logger.error(f"PCR analysis request failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/analytics/{index}/sentiment", response_model=Dict[str, Any])
async def get_market_sentiment(
    index: str = PathParam(..., description="Index symbol"),
    _: bool = Depends(verify_api_key)
):
    """Get market sentiment analysis"""
    try:
        api_service.request_count += 1
        
        if index.upper() not in INDICES:
            raise HTTPException(status_code=404, detail="Index not found")
        
        # Load analytics data
        analytics_data = await api_service.load_analytics_data(
            f"realtime_{index.lower()}", index.upper()
        )
        
        if 'market_sentiment' not in analytics_data.get('data', {}):
            raise HTTPException(status_code=404, detail="Sentiment data not found")
        
        return analytics_data['data']['market_sentiment']
        
    except HTTPException:
        raise
    except Exception as e:
        api_service.error_count += 1
        logger.error(f"Market sentiment request failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/data/refresh", response_model=Dict[str, str])
async def trigger_data_refresh(
    background_tasks: BackgroundTasks,
    _: bool = Depends(verify_api_key)
):
    """Trigger data refresh (async)"""
    try:
        # Publish refresh event to Redis
        event_data = {
            'event_type': 'data_refresh_requested',
            'timestamp': time_utils.get_metadata_timestamp(),
            'requested_by': 'api'
        }
        
        redis_coord.publish_message("system_events", event_data)
        
        return {
            "status": "refresh_triggered",
            "message": "Data refresh request published",
            "timestamp": now_csv_format()
        }
        
    except Exception as e:
        logger.error(f"Data refresh trigger failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# WebSocket endpoint for real-time data (placeholder)
@app.websocket("/ws/realtime/{index}")
async def websocket_realtime_data(websocket, index: str):
    """WebSocket endpoint for real-time data streaming"""
    await websocket.accept()
    
    try:
        if index.upper() not in INDICES:
            await websocket.send_json({"error": "Invalid index"})
            return
        
        # In production, this would stream real-time data
        while True:
            # Mock data for now
            await websocket.send_json({
                "index": index.upper(),
                "timestamp": now_csv_format(),
                "data": "real-time data would go here"
            })
            await asyncio.sleep(5)
            
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await websocket.close()

# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "message": "The requested resource was not found",
            "timestamp": now_csv_format()
        }
    )

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error", 
            "message": "An internal error occurred",
            "timestamp": now_csv_format()
        }
    )

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """API startup initialization"""
    logger.info("Starting OP Trading Platform API...")
    
    # Update service health
    health_data = {
        'service_name': 'api',
        'status': 'RUNNING',
        'uptime_seconds': 0,
        'version': '1.0.0',
        'endpoints': len(app.routes)
    }
    redis_coord.set_service_health('api', health_data)
    
    logger.info("API service started successfully")

@app.on_event("shutdown")
async def shutdown_event():
    """API shutdown cleanup"""
    logger.info("Shutting down OP Trading Platform API...")
    
    # Update service health
    health_data = {
        'service_name': 'api',
        'status': 'STOPPED',
        'uptime_seconds': time.time() - api_service.start_time
    }
    redis_coord.set_service_health('api', health_data)

# Main entry point
def create_app():
    """Create FastAPI application"""
    return app

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run the API server
    uvicorn.run(
        "services.api.main:app",
        host=settings.service.api_host,
        port=settings.service.api_port,
        workers=settings.service.api_workers,
        reload=settings.debug,
        log_level="info"
    )