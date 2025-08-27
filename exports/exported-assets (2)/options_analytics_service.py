"""
Options Analytics Service - Real-time and batch analytics computation.
Provides aggregations, derivatives pricing models, and market insights.
"""

import asyncio
import logging
import time
import math
import numpy as np
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional, Tuple, Callable
from dataclasses import dataclass, asdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import json
import sys
from scipy import stats
from scipy.optimize import brentq

# Import shared utilities
sys.path.append(str(Path(__file__).parent.parent.parent))

from shared.config.settings import get_settings
from shared.utils.time_utils import get_time_utils, now_csv_format, is_market_open
from shared.utils.coordination import get_redis_coordinator, get_file_coordinator
from shared.constants.market_constants import INDICES, BUCKETS, STRIKE_OFFSETS, INDEX_SPECS
from shared.types.option_data import (
    OptionLegData, MergedOptionData, AnalyticsResult, HealthMetric, ServiceHealth
)
from services.processing.writers.consolidated_csv_writer import get_consolidated_writer

logger = logging.getLogger(__name__)

@dataclass
class VolatilitySurface:
    """Implied volatility surface data"""
    index: str
    timestamp: str
    expiries: List[str]
    strikes: List[float] 
    iv_matrix: List[List[float]]  # [expiry][strike] -> iv
    atm_strikes: Dict[str, float]  # expiry -> atm_strike

@dataclass
class GreeksSummary:
    """Aggregated Greeks summary"""
    index: str
    bucket: str
    timestamp: str
    total_delta: float
    total_gamma: float
    total_theta: float
    total_vega: float
    net_delta_call: float
    net_delta_put: float
    gamma_exposure: float
    vega_exposure: float

@dataclass
class PCRAnalysis:
    """Put-Call Ratio analysis"""
    index: str
    bucket: str
    timestamp: str
    pcr_volume: float
    pcr_oi: float
    pcr_premium: float
    call_volume: int
    put_volume: int
    call_oi: int
    put_oi: int
    interpretation: str

@dataclass
class StrikewiseAnalysis:
    """Strike-wise option analysis"""
    index: str
    bucket: str
    timestamp: str
    strike: float
    strike_offset: int
    call_data: Dict[str, Any]
    put_data: Dict[str, Any]
    total_premium: float
    volume_ratio: float
    oi_ratio: float
    pain_score: float

@dataclass
class MarketSentiment:
    """Market sentiment indicators"""
    index: str
    timestamp: str
    sentiment_score: float  # -100 to +100
    fear_greed_index: float # 0 to 100
    volatility_regime: str  # "LOW", "NORMAL", "HIGH"
    trend_direction: str    # "BULLISH", "BEARISH", "NEUTRAL"
    confidence_level: float # 0 to 1
    indicators: Dict[str, float]

class BlackScholesModel:
    """Black-Scholes option pricing model"""
    
    @staticmethod
    def d1(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Calculate d1 parameter"""
        if T <= 0 or sigma <= 0:
            return 0.0
        return (math.log(S/K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    
    @staticmethod
    def d2(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Calculate d2 parameter"""
        if T <= 0 or sigma <= 0:
            return 0.0
        return BlackScholesModel.d1(S, K, T, r, sigma) - sigma * math.sqrt(T)
    
    @staticmethod
    def call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Calculate call option theoretical price"""
        try:
            if T <= 0:
                return max(0, S - K)
            
            d1 = BlackScholesModel.d1(S, K, T, r, sigma)
            d2 = BlackScholesModel.d2(S, K, T, r, sigma)
            
            call = S * stats.norm.cdf(d1) - K * math.exp(-r * T) * stats.norm.cdf(d2)
            return max(0, call)
        except Exception:
            return 0.0
    
    @staticmethod
    def put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Calculate put option theoretical price"""
        try:
            if T <= 0:
                return max(0, K - S)
            
            d1 = BlackScholesModel.d1(S, K, T, r, sigma)
            d2 = BlackScholesModel.d2(S, K, T, r, sigma)
            
            put = K * math.exp(-r * T) * stats.norm.cdf(-d2) - S * stats.norm.cdf(-d1)
            return max(0, put)
        except Exception:
            return 0.0
    
    @staticmethod
    def delta(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> float:
        """Calculate option delta"""
        try:
            if T <= 0:
                if option_type.upper() == "CALL":
                    return 1.0 if S > K else 0.0
                else:
                    return -1.0 if S < K else 0.0
            
            d1 = BlackScholesModel.d1(S, K, T, r, sigma)
            
            if option_type.upper() == "CALL":
                return stats.norm.cdf(d1)
            else:
                return stats.norm.cdf(d1) - 1.0
        except Exception:
            return 0.0
    
    @staticmethod
    def gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Calculate option gamma"""
        try:
            if T <= 0 or sigma <= 0:
                return 0.0
            
            d1 = BlackScholesModel.d1(S, K, T, r, sigma)
            return stats.norm.pdf(d1) / (S * sigma * math.sqrt(T))
        except Exception:
            return 0.0
    
    @staticmethod
    def vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Calculate option vega"""
        try:
            if T <= 0:
                return 0.0
            
            d1 = BlackScholesModel.d1(S, K, T, r, sigma)
            return S * stats.norm.pdf(d1) * math.sqrt(T) / 100  # Per 1% change
        except Exception:
            return 0.0
    
    @staticmethod
    def theta(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> float:
        """Calculate option theta"""
        try:
            if T <= 0:
                return 0.0
            
            d1 = BlackScholesModel.d1(S, K, T, r, sigma)
            d2 = BlackScholesModel.d2(S, K, T, r, sigma)
            
            if option_type.upper() == "CALL":
                theta = (-S * stats.norm.pdf(d1) * sigma / (2 * math.sqrt(T))
                        - r * K * math.exp(-r * T) * stats.norm.cdf(d2))
            else:
                theta = (-S * stats.norm.pdf(d1) * sigma / (2 * math.sqrt(T))
                        + r * K * math.exp(-r * T) * stats.norm.cdf(-d2))
            
            return theta / 365  # Per day
        except Exception:
            return 0.0
    
    @staticmethod
    def implied_volatility(market_price: float, S: float, K: float, T: float, 
                          r: float, option_type: str, max_iterations: int = 100) -> float:
        """Calculate implied volatility using Newton-Raphson method"""
        try:
            if T <= 0 or market_price <= 0:
                return 0.0
            
            # Initial guess
            sigma = 0.2
            
            for i in range(max_iterations):
                if option_type.upper() == "CALL":
                    price = BlackScholesModel.call_price(S, K, T, r, sigma)
                else:
                    price = BlackScholesModel.put_price(S, K, T, r, sigma)
                
                vega = BlackScholesModel.vega(S, K, T, r, sigma)
                
                if abs(vega) < 1e-6:
                    break
                
                sigma_new = sigma - (price - market_price) / vega
                
                if abs(sigma_new - sigma) < 1e-6:
                    return max(0.001, sigma_new)
                
                sigma = max(0.001, min(5.0, sigma_new))  # Clamp between 0.1% and 500%
            
            return max(0.001, sigma)
        except Exception:
            return 0.2  # Default fallback

class OptionsAnalyticsEngine:
    """Core analytics computation engine"""
    
    def __init__(self):
        self.settings = get_settings()
        self.time_utils = get_time_utils()
        self.redis_coord = get_redis_coordinator()
        self.csv_writer = get_consolidated_writer()
        
        # Risk-free rate (simplified - would come from bond data)
        self.risk_free_rate = 0.06  # 6% annual
        
        # Performance tracking
        self.computation_stats = {
            'total_computations': 0,
            'successful_computations': 0,
            'failed_computations': 0,
            'avg_computation_time': 0.0,
            'last_error': None
        }
    
    async def load_option_data(self, index: str, date_filter: date = None) -> List[OptionLegData]:
        """Load option data for analysis"""
        try:
            date_str = (date_filter or date.today()).isoformat()
            
            # Read from CSV files
            csv_root = self.settings.data.csv_data_root
            option_legs = []
            
            for bucket in BUCKETS:
                for offset in STRIKE_OFFSETS:
                    offset_str = f"atm_p{offset}" if offset > 0 else ("atm" if offset == 0 else f"atm_m{abs(offset)}")
                    
                    csv_file = csv_root / index / bucket / offset_str / f"{date_str}_legs.csv"
                    
                    if csv_file.exists():
                        # Use consolidated writer's incremental reading
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
                                logger.warning(f"Failed to parse row in {csv_file}: {e}")
                                continue
            
            logger.info(f"Loaded {len(option_legs)} option legs for {index} on {date_str}")
            return option_legs
            
        except Exception as e:
            logger.error(f"Failed to load option data for {index}: {e}")
            return []
    
    async def compute_implied_volatility_surface(self, index: str, 
                                               spot_price: float,
                                               legs: List[OptionLegData]) -> VolatilitySurface:
        """Compute implied volatility surface"""
        try:
            # Group data by expiry and strike
            expiry_data = {}
            for leg in legs:
                if leg.iv is None or leg.iv <= 0:
                    continue
                
                if leg.expiry not in expiry_data:
                    expiry_data[leg.expiry] = {}
                
                if leg.strike not in expiry_data[leg.expiry]:
                    expiry_data[leg.expiry][leg.strike] = {}
                
                expiry_data[leg.expiry][leg.strike][leg.side] = leg.iv
            
            # Build surface matrices
            expiries = sorted(expiry_data.keys())
            all_strikes = set()
            for expiry_strikes in expiry_data.values():
                all_strikes.update(expiry_strikes.keys())
            strikes = sorted(all_strikes)
            
            # Create IV matrix
            iv_matrix = []
            atm_strikes = {}
            
            for expiry in expiries:
                iv_row = []
                atm_strikes[expiry] = spot_price  # Simplified ATM calculation
                
                for strike in strikes:
                    if strike in expiry_data.get(expiry, {}):
                        # Average CALL and PUT IVs if both exist
                        strike_ivs = expiry_data[expiry][strike]
                        if 'CALL' in strike_ivs and 'PUT' in strike_ivs:
                            iv = (strike_ivs['CALL'] + strike_ivs['PUT']) / 2
                        elif 'CALL' in strike_ivs:
                            iv = strike_ivs['CALL']
                        elif 'PUT' in strike_ivs:
                            iv = strike_ivs['PUT']
                        else:
                            iv = 0.0
                    else:
                        iv = 0.0  # Missing data
                    
                    iv_row.append(iv)
                
                iv_matrix.append(iv_row)
            
            return VolatilitySurface(
                index=index,
                timestamp=now_csv_format(),
                expiries=expiries,
                strikes=strikes,
                iv_matrix=iv_matrix,
                atm_strikes=atm_strikes
            )
            
        except Exception as e:
            logger.error(f"Failed to compute IV surface for {index}: {e}")
            return VolatilitySurface(index, now_csv_format(), [], [], [], {})
    
    async def compute_greeks_summary(self, index: str, bucket: str, 
                                   legs: List[OptionLegData]) -> GreeksSummary:
        """Compute aggregated Greeks summary"""
        try:
            # Filter legs by bucket
            bucket_legs = [leg for leg in legs if leg.bucket == bucket]
            
            if not bucket_legs:
                return GreeksSummary(
                    index=index, bucket=bucket, timestamp=now_csv_format(),
                    total_delta=0, total_gamma=0, total_theta=0, total_vega=0,
                    net_delta_call=0, net_delta_put=0, gamma_exposure=0, vega_exposure=0
                )
            
            # Aggregate Greeks
            total_delta = 0
            total_gamma = 0
            total_theta = 0
            total_vega = 0
            net_delta_call = 0
            net_delta_put = 0
            gamma_exposure = 0
            vega_exposure = 0
            
            for leg in bucket_legs:
                # Weight by volume if available
                weight = max(1, leg.volume or 1)
                lot_size = INDEX_SPECS.get(index, {}).get('lot_size', 1)
                position_size = weight * lot_size
                
                if leg.delta is not None:
                    delta_contribution = leg.delta * position_size
                    total_delta += delta_contribution
                    
                    if leg.side == 'CALL':
                        net_delta_call += delta_contribution
                    else:
                        net_delta_put += delta_contribution
                
                if leg.gamma is not None:
                    gamma_contribution = leg.gamma * position_size
                    total_gamma += gamma_contribution
                    gamma_exposure += abs(gamma_contribution) * leg.last_price
                
                if leg.theta is not None:
                    total_theta += leg.theta * position_size
                
                if leg.vega is not None:
                    vega_contribution = leg.vega * position_size
                    total_vega += vega_contribution
                    vega_exposure += abs(vega_contribution)
            
            return GreeksSummary(
                index=index,
                bucket=bucket,
                timestamp=now_csv_format(),
                total_delta=total_delta,
                total_gamma=total_gamma,
                total_theta=total_theta,
                total_vega=total_vega,
                net_delta_call=net_delta_call,
                net_delta_put=net_delta_put,
                gamma_exposure=gamma_exposure,
                vega_exposure=vega_exposure
            )
            
        except Exception as e:
            logger.error(f"Failed to compute Greeks summary for {index}-{bucket}: {e}")
            return GreeksSummary(
                index, bucket, now_csv_format(), 0, 0, 0, 0, 0, 0, 0, 0
            )
    
    async def compute_pcr_analysis(self, index: str, bucket: str, 
                                 legs: List[OptionLegData]) -> PCRAnalysis:
        """Compute Put-Call Ratio analysis"""
        try:
            # Filter and separate CALL/PUT data
            bucket_legs = [leg for leg in legs if leg.bucket == bucket]
            call_legs = [leg for leg in bucket_legs if leg.side == 'CALL']
            put_legs = [leg for leg in bucket_legs if leg.side == 'PUT']
            
            # Calculate totals
            call_volume = sum(leg.volume or 0 for leg in call_legs)
            put_volume = sum(leg.volume or 0 for leg in put_legs)
            call_oi = sum(leg.oi or 0 for leg in call_legs)
            put_oi = sum(leg.oi or 0 for leg in put_legs)
            
            call_premium = sum(leg.last_price * (leg.volume or 1) for leg in call_legs)
            put_premium = sum(leg.last_price * (leg.volume or 1) for leg in put_legs)
            
            # Calculate ratios
            pcr_volume = put_volume / call_volume if call_volume > 0 else float('inf')
            pcr_oi = put_oi / call_oi if call_oi > 0 else float('inf')
            pcr_premium = put_premium / call_premium if call_premium > 0 else float('inf')
            
            # Interpret PCR
            if pcr_oi > 1.5:
                interpretation = "BEARISH_EXTREME"
            elif pcr_oi > 1.2:
                interpretation = "BEARISH"
            elif pcr_oi > 0.8:
                interpretation = "NEUTRAL"
            elif pcr_oi > 0.5:
                interpretation = "BULLISH"
            else:
                interpretation = "BULLISH_EXTREME"
            
            return PCRAnalysis(
                index=index,
                bucket=bucket,
                timestamp=now_csv_format(),
                pcr_volume=pcr_volume,
                pcr_oi=pcr_oi,
                pcr_premium=pcr_premium,
                call_volume=call_volume,
                put_volume=put_volume,
                call_oi=call_oi,
                put_oi=put_oi,
                interpretation=interpretation
            )
            
        except Exception as e:
            logger.error(f"Failed to compute PCR analysis for {index}-{bucket}: {e}")
            return PCRAnalysis(
                index, bucket, now_csv_format(), 0, 0, 0, 0, 0, 0, 0, "UNKNOWN"
            )
    
    async def compute_max_pain(self, index: str, bucket: str, 
                             legs: List[OptionLegData],
                             spot_price: float) -> float:
        """Compute max pain strike price"""
        try:
            bucket_legs = [leg for leg in legs if leg.bucket == bucket]
            
            if not bucket_legs:
                return spot_price
            
            # Get unique strikes
            strikes = sorted(set(leg.strike for leg in bucket_legs))
            
            min_pain = float('inf')
            max_pain_strike = spot_price
            
            # Calculate pain for each strike
            for test_strike in strikes:
                pain = 0.0
                
                for leg in bucket_legs:
                    if leg.oi is None or leg.oi <= 0:
                        continue
                    
                    if leg.side == 'CALL' and test_strike > leg.strike:
                        # Call ITM
                        pain += leg.oi * (test_strike - leg.strike)
                    elif leg.side == 'PUT' and test_strike < leg.strike:
                        # Put ITM
                        pain += leg.oi * (leg.strike - test_strike)
                
                if pain < min_pain:
                    min_pain = pain
                    max_pain_strike = test_strike
            
            return max_pain_strike
            
        except Exception as e:
            logger.error(f"Failed to compute max pain for {index}-{bucket}: {e}")
            return spot_price
    
    async def compute_market_sentiment(self, index: str, legs: List[OptionLegData],
                                     spot_price: float) -> MarketSentiment:
        """Compute overall market sentiment indicators"""
        try:
            indicators = {}
            
            # 1. Put-Call Ratio sentiment
            call_volume = sum(leg.volume or 0 for leg in legs if leg.side == 'CALL')
            put_volume = sum(leg.volume or 0 for leg in legs if leg.side == 'PUT')
            pcr = put_volume / call_volume if call_volume > 0 else 1.0
            
            pcr_sentiment = max(-50, min(50, (1 - pcr) * 50))  # -50 to +50
            indicators['pcr_sentiment'] = pcr_sentiment
            
            # 2. Volatility sentiment (fear/greed)
            avg_iv = np.mean([leg.iv for leg in legs if leg.iv is not None and leg.iv > 0])
            if not np.isnan(avg_iv):
                # Normal IV around 15-20%, high fear > 30%
                vol_sentiment = max(0, min(100, (30 - avg_iv * 100) / 15 * 100))
                indicators['volatility_fear'] = 100 - vol_sentiment  # Higher IV = more fear
            else:
                indicators['volatility_fear'] = 50
            
            # 3. Skew sentiment
            atm_legs = [leg for leg in legs if abs(leg.strike_offset) <= 1]
            otm_legs = [leg for leg in legs if abs(leg.strike_offset) >= 2]
            
            if atm_legs and otm_legs:
                atm_iv = np.mean([leg.iv for leg in atm_legs if leg.iv is not None])
                otm_iv = np.mean([leg.iv for leg in otm_legs if leg.iv is not None])
                
                if not (np.isnan(atm_iv) or np.isnan(otm_iv)):
                    skew = (otm_iv - atm_iv) * 100
                    skew_sentiment = max(-25, min(25, -skew))  # Negative skew = bearish
                    indicators['skew_sentiment'] = skew_sentiment
                else:
                    indicators['skew_sentiment'] = 0
            else:
                indicators['skew_sentiment'] = 0
            
            # 4. Volume sentiment
            total_volume = sum(leg.volume or 0 for leg in legs)
            avg_volume = self._get_historical_avg_volume(index)  # Would need historical data
            
            if avg_volume > 0:
                volume_ratio = total_volume / avg_volume
                volume_sentiment = max(-20, min(20, (volume_ratio - 1) * 20))
                indicators['volume_sentiment'] = volume_sentiment
            else:
                indicators['volume_sentiment'] = 0
            
            # Combine sentiments
            sentiment_score = (
                indicators['pcr_sentiment'] * 0.3 +
                (100 - indicators['volatility_fear'] - 50) * 0.25 +
                indicators['skew_sentiment'] * 0.25 +
                indicators['volume_sentiment'] * 0.2
            )
            
            # Classify sentiment
            if sentiment_score > 20:
                trend = "BULLISH"
            elif sentiment_score < -20:
                trend = "BEARISH"
            else:
                trend = "NEUTRAL"
            
            # Volatility regime
            if indicators['volatility_fear'] > 70:
                vol_regime = "HIGH"
            elif indicators['volatility_fear'] < 30:
                vol_regime = "LOW"
            else:
                vol_regime = "NORMAL"
            
            return MarketSentiment(
                index=index,
                timestamp=now_csv_format(),
                sentiment_score=sentiment_score,
                fear_greed_index=indicators['volatility_fear'],
                volatility_regime=vol_regime,
                trend_direction=trend,
                confidence_level=min(1.0, total_volume / max(1000, avg_volume)),
                indicators=indicators
            )
            
        except Exception as e:
            logger.error(f"Failed to compute market sentiment for {index}: {e}")
            return MarketSentiment(
                index, now_csv_format(), 0, 50, "NORMAL", "NEUTRAL", 0.5, {}
            )
    
    def _get_historical_avg_volume(self, index: str) -> float:
        """Get historical average volume (placeholder)"""
        # This would query historical data in production
        base_volumes = {"NIFTY": 50000, "BANKNIFTY": 30000, "SENSEX": 10000}
        return base_volumes.get(index, 25000)
    
    async def save_analytics_results(self, analytics_data: Dict[str, Any], 
                                   analytics_type: str) -> bool:
        """Save analytics results to files"""
        try:
            timestamp = now_csv_format()
            date_str = datetime.now().date().isoformat()
            
            # Save to analytics directory
            analytics_root = self.settings.data.csv_data_root.parent / "analytics"
            analytics_file = analytics_root / analytics_type / f"{date_str}_{analytics_type}.json"
            
            analytics_file.parent.mkdir(parents=True, exist_ok=True)
            
            output_data = {
                'timestamp': timestamp,
                'analytics_type': analytics_type,
                'data': analytics_data,
                'metadata': {
                    'computation_time': datetime.now().isoformat(),
                    'version': '1.0.0'
                }
            }
            
            with open(analytics_file, 'w') as f:
                json.dump(output_data, f, indent=2, default=str)
            
            logger.info(f"Saved {analytics_type} analytics to {analytics_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save analytics results: {e}")
            return False

class OptionsAnalyticsService:
    """Main analytics service orchestrator"""
    
    def __init__(self):
        self.settings = get_settings()
        self.time_utils = get_time_utils()
        self.redis_coord = get_redis_coordinator()
        self.analytics_engine = OptionsAnalyticsEngine()
        
        # Service state
        self.is_running = False
        self.service_start_time = None
        
        # Performance metrics
        self.service_stats = {
            'analytics_computed': 0,
            'successful_computations': 0,
            'failed_computations': 0,
            'avg_computation_time': 0.0,
            'last_error': None
        }
    
    async def start_service(self):
        """Start the analytics service"""
        if self.is_running:
            logger.warning("Analytics service already running")
            return
        
        self.is_running = True
        self.service_start_time = time.time()
        
        logger.info("Starting options analytics service...")
        await self._update_service_health("RUNNING")
        
        try:
            while self.is_running:
                if is_market_open():
                    # Real-time analytics during market hours
                    await self._run_realtime_analytics()
                    await asyncio.sleep(60)  # Every minute
                else:
                    # EOD analytics after market close
                    await self._run_eod_analytics()
                    await asyncio.sleep(300)  # Every 5 minutes when market closed
                    
        except Exception as e:
            logger.error(f"Analytics service error: {e}")
            await self._update_service_health("ERROR", str(e))
        finally:
            self.is_running = False
            await self._update_service_health("STOPPED")
    
    async def stop_service(self):
        """Stop the analytics service"""
        logger.info("Stopping analytics service...")
        self.is_running = False
    
    async def _run_realtime_analytics(self):
        """Run real-time analytics computations"""
        computation_start = time.time()
        
        try:
            for index in INDICES:
                # Load recent data
                legs = await self.analytics_engine.load_option_data(index)
                
                if not legs:
                    logger.warning(f"No data available for {index}")
                    continue
                
                # Get spot price (simplified - would come from index data)
                spot_price = self._estimate_spot_price(index, legs)
                
                # Compute analytics
                analytics_results = {}
                
                # Greeks summary for each bucket
                for bucket in BUCKETS:
                    greeks = await self.analytics_engine.compute_greeks_summary(
                        index, bucket, legs
                    )
                    analytics_results[f'greeks_{bucket}'] = asdict(greeks)
                    
                    # PCR analysis
                    pcr = await self.analytics_engine.compute_pcr_analysis(
                        index, bucket, legs
                    )
                    analytics_results[f'pcr_{bucket}'] = asdict(pcr)
                    
                    # Max pain
                    max_pain = await self.analytics_engine.compute_max_pain(
                        index, bucket, legs, spot_price
                    )
                    analytics_results[f'max_pain_{bucket}'] = max_pain
                
                # Market sentiment
                sentiment = await self.analytics_engine.compute_market_sentiment(
                    index, legs, spot_price
                )
                analytics_results['market_sentiment'] = asdict(sentiment)
                
                # IV surface
                iv_surface = await self.analytics_engine.compute_implied_volatility_surface(
                    index, spot_price, legs
                )
                analytics_results['iv_surface'] = asdict(iv_surface)
                
                # Save results
                await self.analytics_engine.save_analytics_results(
                    analytics_results, f"realtime_{index.lower()}"
                )
                
                # Publish analytics event
                await self._publish_analytics_event(index, analytics_results)
            
            # Update stats
            computation_time = (time.time() - computation_start) * 1000
            self.service_stats['analytics_computed'] += 1
            self.service_stats['successful_computations'] += 1
            self.service_stats['avg_computation_time'] = (
                (self.service_stats['avg_computation_time'] * 
                 (self.service_stats['analytics_computed'] - 1) + computation_time)
                / self.service_stats['analytics_computed']
            )
            
            logger.info(f"Completed real-time analytics in {computation_time:.1f}ms")
            
        except Exception as e:
            logger.error(f"Real-time analytics failed: {e}")
            self.service_stats['failed_computations'] += 1
            self.service_stats['last_error'] = str(e)
            await self._update_service_health("WARNING", str(e))
    
    async def _run_eod_analytics(self):
        """Run end-of-day analytics computations"""
        try:
            logger.info("Running EOD analytics...")
            
            yesterday = date.today() - timedelta(days=1)
            
            for index in INDICES:
                # Load full day data
                legs = await self.analytics_engine.load_option_data(index, yesterday)
                
                if not legs:
                    continue
                
                # Comprehensive EOD analysis
                eod_results = {
                    'date': yesterday.isoformat(),
                    'index': index,
                    'total_legs': len(legs),
                    'unique_strikes': len(set(leg.strike for leg in legs)),
                    'total_volume': sum(leg.volume or 0 for leg in legs),
                    'total_oi': sum(leg.oi or 0 for leg in legs),
                    'avg_iv': np.mean([leg.iv for leg in legs if leg.iv is not None])
                }
                
                # Save EOD results
                await self.analytics_engine.save_analytics_results(
                    eod_results, f"eod_{index.lower()}"
                )
            
            logger.info("EOD analytics completed")
            
        except Exception as e:
            logger.error(f"EOD analytics failed: {e}")
    
    def _estimate_spot_price(self, index: str, legs: List[OptionLegData]) -> float:
        """Estimate current spot price from option data"""
        # Simple estimation using ATM strikes
        atm_legs = [leg for leg in legs if leg.strike_offset == 0]
        if atm_legs:
            return atm_legs[0].atm_strike
        
        # Fallback to typical ranges
        typical_ranges = INDEX_SPECS.get(index, {}).get('typical_range', (25000, 25000))
        return (typical_ranges[0] + typical_ranges[1]) / 2
    
    async def _publish_analytics_event(self, index: str, analytics_data: Dict[str, Any]):
        """Publish analytics computation event"""
        try:
            event_data = {
                'event_type': 'analytics_computed',
                'index': index,
                'timestamp': self.time_utils.get_metadata_timestamp(),
                'analytics_types': list(analytics_data.keys()),
                'computation_stats': self.service_stats
            }
            
            self.redis_coord.publish_message("analytics_events", event_data)
            
        except Exception as e:
            logger.warning(f"Failed to publish analytics event: {e}")
    
    async def _update_service_health(self, status: str, error: str = None):
        """Update service health status"""
        try:
            health_data = {
                'service_name': 'analytics',
                'status': status,
                'uptime_seconds': time.time() - self.service_start_time if self.service_start_time else 0,
                'is_running': self.is_running,
                'stats': self.service_stats,
                'analytics_engine_stats': self.analytics_engine.computation_stats
            }
            
            if error:
                health_data['last_error'] = error
            
            self.redis_coord.set_service_health('analytics', health_data)
            
        except Exception as e:
            logger.warning(f"Failed to update service health: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        return {
            'service_stats': self.service_stats,
            'is_running': self.is_running,
            'uptime_seconds': time.time() - self.service_start_time if self.service_start_time else 0,
            'analytics_engine_stats': self.analytics_engine.computation_stats
        }

# Service entry point
async def main():
    """Main service entry point"""
    import signal
    
    service = OptionsAnalyticsService()
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        asyncio.create_task(service.stop_service())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start service
    await service.start_service()
    return 0

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    exit_code = asyncio.run(main())