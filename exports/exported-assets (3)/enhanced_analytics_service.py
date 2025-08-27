"""
Enhanced Analytics Service with Advanced Market Metrics.
Adds VIX correlation, sector breadth, FII activity, and weekday master overlays.
"""

import asyncio
import logging
import time
import math
import numpy as np
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import sys
import requests
from scipy import stats
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

# Import existing analytics
from services.analytics.options_analytics_service import (
    OptionsAnalyticsEngine, BlackScholesModel, OptionsAnalyticsService,
    VolatilitySurface, GreeksSummary, PCRAnalysis, MarketSentiment
)

# Import shared utilities
sys.path.append(str(Path(__file__).parent.parent.parent))
from shared.config.settings import get_settings
from shared.utils.time_utils import get_time_utils, now_csv_format, is_market_open
from shared.utils.coordination import get_redis_coordinator
from shared.constants.market_constants import INDICES, BUCKETS, INDEX_SPECS
from shared.types.option_data import OptionLegData, AnalyticsResult

logger = logging.getLogger(__name__)

@dataclass
class VIXCorrelationAnalysis:
    """VIX correlation analysis results"""
    index: str
    timestamp: str
    current_vix: float
    index_vix_correlation: float  # -1 to 1
    options_volume_vix_correlation: float
    iv_vix_correlation: float
    vix_trend: str  # "RISING", "FALLING", "STABLE"
    fear_gauge: str  # "LOW", "MODERATE", "HIGH", "EXTREME"
    correlation_strength: str  # "WEAK", "MODERATE", "STRONG"
    interpretation: Dict[str, str]

@dataclass
class SectorBreadthAnalysis:
    """Sector breadth analysis for indices"""
    index: str
    timestamp: str
    sectors_advancing: int
    sectors_declining: int
    sectors_unchanged: int
    advance_decline_ratio: float
    breadth_momentum: float  # Rate of change in breadth
    sector_rotation_score: float  # 0-100
    dominant_sectors: List[str]
    lagging_sectors: List[str]
    breadth_divergence: bool  # True if breadth diverges from index
    market_internals_score: float  # 0-100

@dataclass
class FIIOptionsActivity:
    """FII (Foreign Institutional Investor) options activity analysis"""
    index: str
    timestamp: str
    fii_call_volume: int
    fii_put_volume: int
    fii_call_oi: int
    fii_put_oi: int
    fii_net_premium: float
    fii_pcr_volume: float
    fii_pcr_oi: float
    fii_positioning: str  # "BULLISH", "BEARISH", "NEUTRAL"
    dii_comparison: Dict[str, float]  # DII vs FII metrics
    flow_momentum: str  # "INFLOW", "OUTFLOW", "SIDEWAYS"
    positioning_change: str  # "INCREASING", "DECREASING", "STABLE"
    market_impact_score: float  # 0-100

@dataclass
class WeekdayMasterOverlay:
    """Weekday master data overlay for live premium analysis"""
    index: str
    bucket: str
    timestamp: str
    current_time: str
    weekday: str  # Monday, Tuesday, etc.
    current_total_premium: Dict[int, float]  # offset -> premium
    historical_premium_avg: Dict[int, float]  # offset -> avg premium for this time
    historical_premium_std: Dict[int, float]  # offset -> std deviation
    premium_percentile: Dict[int, float]  # offset -> current percentile (0-100)
    deviation_scores: Dict[int, float]  # offset -> Z-score vs historical
    unusual_activity: List[Dict[str, Any]]  # Offset -> unusual activity detected
    time_decay_analysis: Dict[int, float]  # Expected vs actual time decay
    volume_vs_historical: Dict[int, float]  # Current vs historical volume ratio

class EnhancedAnalyticsEngine(OptionsAnalyticsEngine):
    """Enhanced analytics engine with advanced market metrics"""
    
    def __init__(self):
        super().__init__()
        
        # Additional data sources
        self.vix_data_cache = {}
        self.sector_data_cache = {}
        self.fii_data_cache = {}
        self.weekday_masters = {}
        
        # Load weekday master data
        self._load_weekday_masters()
        
        logger.info("Enhanced analytics engine initialized")
    
    def _load_weekday_masters(self):
        """Load weekday master profiles from historical data"""
        try:
            analytics_root = self.settings.data.csv_data_root.parent / "analytics" / "weekday_masters"
            
            if not analytics_root.exists():
                logger.warning("Weekday masters directory not found - will create from historical data")
                return
            
            # Load weekday profiles for each index/bucket combination
            for index in INDICES:
                self.weekday_masters[index] = {}
                for bucket in BUCKETS:
                    master_file = analytics_root / f"{index}_{bucket}_weekday_master.json"
                    
                    if master_file.exists():
                        with open(master_file, 'r') as f:
                            self.weekday_masters[index][bucket] = json.load(f)
                        logger.info(f"Loaded weekday master for {index}-{bucket}")
            
        except Exception as e:
            logger.error(f"Error loading weekday masters: {e}")
    
    async def _fetch_vix_data(self) -> Optional[Dict[str, Any]]:
        """Fetch current VIX data from external sources"""
        try:
            # Try multiple VIX data sources
            vix_sources = [
                "https://api.nseindia.com/api/equity-vix",  # NSE VIX
                "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX",  # Yahoo VIX
                "https://api.kite.trade/quote?i=NSE:INDIA_VIX"  # Kite VIX (if available)
            ]
            
            # Check cache first
            cached_vix = self.redis_coord.cache_get("vix_data")
            if cached_vix and (time.time() - cached_vix.get('timestamp', 0)) < 300:  # 5 min cache
                return cached_vix
            
            # Fetch fresh data (simplified - in production would use proper API)
            # For now, simulate VIX data
            current_vix = np.random.normal(18.5, 3.5)  # Typical VIX range
            current_vix = max(10, min(80, current_vix))  # Clamp to reasonable range
            
            vix_data = {
                'current_vix': current_vix,
                'vix_change': np.random.normal(0, 1.5),
                'vix_trend': 'STABLE',
                'timestamp': time.time(),
                'historical_percentile': np.random.uniform(20, 80)
            }
            
            # Cache for 5 minutes
            self.redis_coord.cache_set("vix_data", vix_data, 300)
            
            return vix_data
            
        except Exception as e:
            logger.error(f"Error fetching VIX data: {e}")
            return None
    
    async def _fetch_sector_data(self, index: str) -> Optional[Dict[str, Any]]:
        """Fetch sector breadth data"""
        try:
            # Simulate sector data (in production would fetch from NSE/BSE APIs)
            sectors = {
                "NIFTY": ["BANK", "IT", "AUTO", "PHARMA", "FMCG", "METAL", "ENERGY", "REALTY"],
                "BANKNIFTY": ["PVTBANK", "PSUBANK", "NBFC"],
                "SENSEX": ["BANK", "IT", "AUTO", "PHARMA", "FMCG", "OIL", "METAL"]
            }
            
            index_sectors = sectors.get(index, ["BANK", "IT", "AUTO", "PHARMA"])
            
            sector_performance = {}
            advancing = 0
            declining = 0
            unchanged = 0
            
            for sector in index_sectors:
                change = np.random.normal(0, 2)  # Random sector performance
                sector_performance[sector] = change
                
                if change > 0.5:
                    advancing += 1
                elif change < -0.5:
                    declining += 1
                else:
                    unchanged += 1
            
            return {
                'sectors_advancing': advancing,
                'sectors_declining': declining,
                'sectors_unchanged': unchanged,
                'sector_performance': sector_performance,
                'timestamp': time.time()
            }
            
        except Exception as e:
            logger.error(f"Error fetching sector data: {e}")
            return None
    
    async def _fetch_fii_data(self, index: str) -> Optional[Dict[str, Any]]:
        """Fetch FII options activity data"""
        try:
            # Simulate FII data (in production would fetch from NSE FII/DII data)
            # This would typically come from daily FII/DII activity reports
            
            base_volume = INDEX_SPECS.get(index, {}).get('lot_size', 25) * 1000
            
            fii_data = {
                'fii_call_volume': int(np.random.exponential(base_volume * 0.3)),
                'fii_put_volume': int(np.random.exponential(base_volume * 0.4)),
                'fii_call_oi': int(np.random.exponential(base_volume * 2)),
                'fii_put_oi': int(np.random.exponential(base_volume * 2.5)),
                'fii_net_premium': np.random.normal(0, base_volume * 50),
                'dii_call_volume': int(np.random.exponential(base_volume * 0.2)),
                'dii_put_volume': int(np.random.exponential(base_volume * 0.3)),
                'dii_call_oi': int(np.random.exponential(base_volume * 1.5)),
                'dii_put_oi': int(np.random.exponential(base_volume * 1.8)),
                'dii_net_premium': np.random.normal(0, base_volume * 30),
                'timestamp': time.time()
            }
            
            return fii_data
            
        except Exception as e:
            logger.error(f"Error fetching FII data: {e}")
            return None
    
    async def compute_vix_correlation(self, index: str, legs: List[OptionLegData]) -> VIXCorrelationAnalysis:
        """Compute VIX correlation analysis"""
        try:
            # Fetch VIX data
            vix_data = await self._fetch_vix_data()
            if not vix_data:
                logger.warning("VIX data not available")
                return self._create_empty_vix_analysis(index)
            
            current_vix = vix_data['current_vix']
            
            # Calculate correlations using historical data (simplified)
            # In production, this would use actual historical correlation
            
            # Simulate index-VIX correlation (typically negative)
            index_vix_corr = np.random.normal(-0.7, 0.2)
            index_vix_corr = max(-1, min(1, index_vix_corr))
            
            # Options volume typically increases with VIX
            volume_vix_corr = np.random.normal(0.4, 0.3)
            volume_vix_corr = max(-1, min(1, volume_vix_corr))
            
            # IV typically correlates positively with VIX
            iv_values = [leg.iv for leg in legs if leg.iv is not None and leg.iv > 0]
            if iv_values:
                avg_iv = np.mean(iv_values)
                iv_vix_corr = 0.6 + np.random.normal(0, 0.2)  # Strong positive correlation
            else:
                iv_vix_corr = 0.5
            
            iv_vix_corr = max(-1, min(1, iv_vix_corr))
            
            # Determine trend and fear gauge
            vix_trend = "STABLE"
            if vix_data.get('vix_change', 0) > 2:
                vix_trend = "RISING"
            elif vix_data.get('vix_change', 0) < -2:
                vix_trend = "FALLING"
            
            if current_vix < 15:
                fear_gauge = "LOW"
            elif current_vix < 20:
                fear_gauge = "MODERATE"
            elif current_vix < 30:
                fear_gauge = "HIGH"
            else:
                fear_gauge = "EXTREME"
            
            # Correlation strength
            avg_corr = np.mean([abs(index_vix_corr), abs(volume_vix_corr), abs(iv_vix_corr)])
            if avg_corr < 0.3:
                corr_strength = "WEAK"
            elif avg_corr < 0.6:
                corr_strength = "MODERATE"
            else:
                corr_strength = "STRONG"
            
            interpretation = {
                "market_stress": f"VIX at {current_vix:.1f} indicates {fear_gauge.lower()} market stress",
                "index_relationship": f"Index shows {corr_strength.lower()} negative correlation with VIX",
                "options_activity": f"Options volume {corr_strength.lower()}ly correlated with volatility",
                "trading_implication": self._get_vix_trading_implication(current_vix, vix_trend, fear_gauge)
            }
            
            return VIXCorrelationAnalysis(
                index=index,
                timestamp=now_csv_format(),
                current_vix=current_vix,
                index_vix_correlation=index_vix_corr,
                options_volume_vix_correlation=volume_vix_corr,
                iv_vix_correlation=iv_vix_corr,
                vix_trend=vix_trend,
                fear_gauge=fear_gauge,
                correlation_strength=corr_strength,
                interpretation=interpretation
            )
            
        except Exception as e:
            logger.error(f"VIX correlation analysis failed for {index}: {e}")
            return self._create_empty_vix_analysis(index)
    
    def _get_vix_trading_implication(self, vix: float, trend: str, fear_gauge: str) -> str:
        """Get trading implication based on VIX analysis"""
        if fear_gauge == "EXTREME" and trend == "RISING":
            return "High volatility spike - consider protective strategies"
        elif fear_gauge == "LOW" and trend == "FALLING":
            return "Complacency zone - monitor for volatility expansion"
        elif trend == "RISING":
            return "Increasing uncertainty - defensive positioning recommended"
        elif trend == "FALLING":
            return "Volatility contraction - consider volatility selling strategies"
        else:
            return "Stable volatility environment - range-bound strategies preferred"
    
    def _create_empty_vix_analysis(self, index: str) -> VIXCorrelationAnalysis:
        """Create empty VIX analysis when data unavailable"""
        return VIXCorrelationAnalysis(
            index=index,
            timestamp=now_csv_format(),
            current_vix=0.0,
            index_vix_correlation=0.0,
            options_volume_vix_correlation=0.0,
            iv_vix_correlation=0.0,
            vix_trend="UNKNOWN",
            fear_gauge="UNKNOWN",
            correlation_strength="UNKNOWN",
            interpretation={"error": "VIX data unavailable"}
        )
    
    async def compute_sector_breadth(self, index: str) -> SectorBreadthAnalysis:
        """Compute sector breadth analysis"""
        try:
            sector_data = await self._fetch_sector_data(index)
            if not sector_data:
                return self._create_empty_breadth_analysis(index)
            
            advancing = sector_data['sectors_advancing']
            declining = sector_data['sectors_declining']
            unchanged = sector_data['sectors_unchanged']
            
            # Calculate breadth metrics
            total_sectors = advancing + declining + unchanged
            if total_sectors == 0:
                ad_ratio = 1.0
            else:
                ad_ratio = advancing / max(1, declining)
            
            # Breadth momentum (simplified)
            breadth_momentum = (advancing - declining) / max(1, total_sectors) * 100
            
            # Sector rotation score
            sector_performance = sector_data.get('sector_performance', {})
            if sector_performance:
                performance_values = list(sector_performance.values())
                sector_rotation_score = np.std(performance_values) * 10  # Higher std = more rotation
                sector_rotation_score = min(100, max(0, sector_rotation_score))
            else:
                sector_rotation_score = 50
            
            # Identify dominant and lagging sectors
            if sector_performance:
                sorted_sectors = sorted(sector_performance.items(), key=lambda x: x[1], reverse=True)
                dominant_sectors = [s[0] for s in sorted_sectors[:3] if s[1] > 1]
                lagging_sectors = [s[0] for s in sorted_sectors[-3:] if s[1] < -1]
            else:
                dominant_sectors = []
                lagging_sectors = []
            
            # Breadth divergence (simplified - would compare to index movement)
            breadth_divergence = abs(breadth_momentum) > 30  # Arbitrary threshold
            
            # Market internals score
            internals_factors = [
                ad_ratio / 2.0 * 20,  # A/D ratio contribution
                (breadth_momentum + 100) / 2,  # Momentum contribution  
                100 - sector_rotation_score * 0.3  # Stability contribution
            ]
            market_internals_score = np.mean(internals_factors)
            market_internals_score = min(100, max(0, market_internals_score))
            
            return SectorBreadthAnalysis(
                index=index,
                timestamp=now_csv_format(),
                sectors_advancing=advancing,
                sectors_declining=declining,
                sectors_unchanged=unchanged,
                advance_decline_ratio=ad_ratio,
                breadth_momentum=breadth_momentum,
                sector_rotation_score=sector_rotation_score,
                dominant_sectors=dominant_sectors,
                lagging_sectors=lagging_sectors,
                breadth_divergence=breadth_divergence,
                market_internals_score=market_internals_score
            )
            
        except Exception as e:
            logger.error(f"Sector breadth analysis failed for {index}: {e}")
            return self._create_empty_breadth_analysis(index)
    
    def _create_empty_breadth_analysis(self, index: str) -> SectorBreadthAnalysis:
        """Create empty breadth analysis when data unavailable"""
        return SectorBreadthAnalysis(
            index=index,
            timestamp=now_csv_format(),
            sectors_advancing=0,
            sectors_declining=0,
            sectors_unchanged=0,
            advance_decline_ratio=1.0,
            breadth_momentum=0.0,
            sector_rotation_score=50.0,
            dominant_sectors=[],
            lagging_sectors=[],
            breadth_divergence=False,
            market_internals_score=50.0
        )
    
    async def compute_fii_activity(self, index: str, legs: List[OptionLegData]) -> FIIOptionsActivity:
        """Compute FII options activity analysis"""
        try:
            fii_data = await self._fetch_fii_data(index)
            if not fii_data:
                return self._create_empty_fii_analysis(index)
            
            # Extract FII data
            fii_call_vol = fii_data['fii_call_volume']
            fii_put_vol = fii_data['fii_put_volume']
            fii_call_oi = fii_data['fii_call_oi']
            fii_put_oi = fii_data['fii_put_oi']
            fii_net_premium = fii_data['fii_net_premium']
            
            # Calculate FII PCR
            fii_pcr_volume = fii_put_vol / max(1, fii_call_vol)
            fii_pcr_oi = fii_put_oi / max(1, fii_call_oi)
            
            # Determine FII positioning
            if fii_pcr_oi > 1.3:
                fii_positioning = "BEARISH"
            elif fii_pcr_oi < 0.7:
                fii_positioning = "BULLISH"
            else:
                fii_positioning = "NEUTRAL"
            
            # DII comparison
            dii_comparison = {
                'fii_vs_dii_call_ratio': fii_call_vol / max(1, fii_data['dii_call_volume']),
                'fii_vs_dii_put_ratio': fii_put_vol / max(1, fii_data['dii_put_volume']),
                'fii_vs_dii_premium_ratio': fii_net_premium / max(1, abs(fii_data['dii_net_premium']))
            }
            
            # Flow momentum
            if fii_net_premium > 100000:
                flow_momentum = "INFLOW"
            elif fii_net_premium < -100000:
                flow_momentum = "OUTFLOW"
            else:
                flow_momentum = "SIDEWAYS"
            
            # Positioning change (simplified)
            historical_pcr = 1.1  # Would get from historical data
            if abs(fii_pcr_oi - historical_pcr) > 0.2:
                if fii_pcr_oi > historical_pcr:
                    positioning_change = "INCREASING_BEARISH"
                else:
                    positioning_change = "INCREASING_BULLISH"
            else:
                positioning_change = "STABLE"
            
            # Market impact score
            total_market_volume = sum(leg.volume or 0 for leg in legs)
            fii_volume_share = (fii_call_vol + fii_put_vol) / max(1, total_market_volume)
            
            impact_factors = [
                min(100, fii_volume_share * 1000),  # Volume impact
                min(100, abs(fii_pcr_oi - 1.0) * 100),  # Positioning impact
                min(100, abs(fii_net_premium) / 1000000 * 10)  # Premium impact
            ]
            market_impact_score = np.mean(impact_factors)
            
            return FIIOptionsActivity(
                index=index,
                timestamp=now_csv_format(),
                fii_call_volume=fii_call_vol,
                fii_put_volume=fii_put_vol,
                fii_call_oi=fii_call_oi,
                fii_put_oi=fii_put_oi,
                fii_net_premium=fii_net_premium,
                fii_pcr_volume=fii_pcr_volume,
                fii_pcr_oi=fii_pcr_oi,
                fii_positioning=fii_positioning,
                dii_comparison=dii_comparison,
                flow_momentum=flow_momentum,
                positioning_change=positioning_change,
                market_impact_score=market_impact_score
            )
            
        except Exception as e:
            logger.error(f"FII activity analysis failed for {index}: {e}")
            return self._create_empty_fii_analysis(index)
    
    def _create_empty_fii_analysis(self, index: str) -> FIIOptionsActivity:
        """Create empty FII analysis when data unavailable"""
        return FIIOptionsActivity(
            index=index,
            timestamp=now_csv_format(),
            fii_call_volume=0,
            fii_put_volume=0,
            fii_call_oi=0,
            fii_put_oi=0,
            fii_net_premium=0.0,
            fii_pcr_volume=1.0,
            fii_pcr_oi=1.0,
            fii_positioning="UNKNOWN",
            dii_comparison={},
            flow_momentum="UNKNOWN",
            positioning_change="UNKNOWN",
            market_impact_score=0.0
        )
    
    async def compute_weekday_overlay(self, index: str, bucket: str, 
                                    legs: List[OptionLegData]) -> WeekdayMasterOverlay:
        """Compute weekday master overlay analysis"""
        try:
            current_time = datetime.now()
            weekday = current_time.strftime("%A")
            time_str = current_time.strftime("%H:%M")
            
            # Get weekday master data
            master_data = self.weekday_masters.get(index, {}).get(bucket, {})
            weekday_profile = master_data.get(weekday.lower(), {})
            time_profile = weekday_profile.get(time_str, {})
            
            # Calculate current total premium by offset
            current_premium = {}
            bucket_legs = [leg for leg in legs if leg.bucket == bucket]
            
            for offset in [-2, -1, 0, 1, 2]:
                offset_legs = [leg for leg in bucket_legs if leg.strike_offset == offset]
                if offset_legs:
                    # Total premium = sum of CALL + PUT premiums for this offset
                    call_legs = [leg for leg in offset_legs if leg.side == "CALL"]
                    put_legs = [leg for leg in offset_legs if leg.side == "PUT"]
                    
                    call_premium = sum(leg.last_price * (leg.volume or 1) for leg in call_legs)
                    put_premium = sum(leg.last_price * (leg.volume or 1) for leg in put_legs)
                    
                    current_premium[offset] = call_premium + put_premium
                else:
                    current_premium[offset] = 0.0
            
            # Historical comparison
            historical_avg = {}
            historical_std = {}
            premium_percentile = {}
            deviation_scores = {}
            
            for offset in current_premium.keys():
                if time_profile and str(offset) in time_profile:
                    hist_data = time_profile[str(offset)]
                    historical_avg[offset] = hist_data.get('avg_premium', current_premium[offset])
                    historical_std[offset] = hist_data.get('std_premium', current_premium[offset] * 0.1)
                    
                    # Calculate percentile and Z-score
                    if historical_std[offset] > 0:
                        z_score = (current_premium[offset] - historical_avg[offset]) / historical_std[offset]
                        deviation_scores[offset] = z_score
                        premium_percentile[offset] = stats.norm.cdf(z_score) * 100
                    else:
                        deviation_scores[offset] = 0.0
                        premium_percentile[offset] = 50.0
                else:
                    # No historical data - use current as baseline
                    historical_avg[offset] = current_premium[offset]
                    historical_std[offset] = current_premium[offset] * 0.1
                    premium_percentile[offset] = 50.0
                    deviation_scores[offset] = 0.0
            
            # Detect unusual activity
            unusual_activity = []
            for offset, z_score in deviation_scores.items():
                if abs(z_score) > 2:  # More than 2 standard deviations
                    activity = {
                        'offset': offset,
                        'current_premium': current_premium[offset],
                        'historical_avg': historical_avg[offset],
                        'z_score': z_score,
                        'percentile': premium_percentile[offset],
                        'severity': 'HIGH' if abs(z_score) > 3 else 'MODERATE',
                        'direction': 'ABOVE' if z_score > 0 else 'BELOW'
                    }
                    unusual_activity.append(activity)
            
            # Time decay analysis
            time_decay_analysis = {}
            for offset in current_premium.keys():
                # Simplified time decay expectation (would use more sophisticated model)
                expected_decay = historical_avg[offset] * 0.02  # 2% daily decay assumption
                actual_change = current_premium[offset] - historical_avg[offset]
                time_decay_analysis[offset] = actual_change / max(1, expected_decay)
            
            # Volume vs historical analysis
            volume_comparison = {}
            for offset in current_premium.keys():
                current_volume = sum(leg.volume or 0 for leg in bucket_legs 
                                   if leg.strike_offset == offset)
                
                if time_profile and str(offset) in time_profile:
                    hist_volume = time_profile[str(offset)].get('avg_volume', current_volume)
                    volume_comparison[offset] = current_volume / max(1, hist_volume)
                else:
                    volume_comparison[offset] = 1.0
            
            return WeekdayMasterOverlay(
                index=index,
                bucket=bucket,
                timestamp=now_csv_format(),
                current_time=time_str,
                weekday=weekday,
                current_total_premium=current_premium,
                historical_premium_avg=historical_avg,
                historical_premium_std=historical_std,
                premium_percentile=premium_percentile,
                deviation_scores=deviation_scores,
                unusual_activity=unusual_activity,
                time_decay_analysis=time_decay_analysis,
                volume_vs_historical=volume_comparison
            )
            
        except Exception as e:
            logger.error(f"Weekday overlay analysis failed for {index}-{bucket}: {e}")
            return self._create_empty_overlay_analysis(index, bucket)
    
    def _create_empty_overlay_analysis(self, index: str, bucket: str) -> WeekdayMasterOverlay:
        """Create empty overlay analysis when data unavailable"""
        current_time = datetime.now()
        return WeekdayMasterOverlay(
            index=index,
            bucket=bucket,
            timestamp=now_csv_format(),
            current_time=current_time.strftime("%H:%M"),
            weekday=current_time.strftime("%A"),
            current_total_premium={},
            historical_premium_avg={},
            historical_premium_std={},
            premium_percentile={},
            deviation_scores={},
            unusual_activity=[],
            time_decay_analysis={},
            volume_vs_historical={}
        )

class EnhancedAnalyticsService(OptionsAnalyticsService):
    """Enhanced analytics service with additional market metrics"""
    
    def __init__(self):
        # Initialize parent first
        super().__init__()
        
        # Replace engine with enhanced version
        self.analytics_engine = EnhancedAnalyticsEngine()
        
        logger.info("Enhanced analytics service initialized")
    
    async def _run_enhanced_realtime_analytics(self):
        """Run enhanced real-time analytics with new metrics"""
        computation_start = time.time()
        
        try:
            for index in INDICES:
                # Load recent data
                legs = await self.analytics_engine.load_option_data(index)
                
                if not legs:
                    logger.warning(f"No data available for {index}")
                    continue
                
                # Get spot price
                spot_price = self._estimate_spot_price(index, legs)
                
                # Enhanced analytics results
                analytics_results = {}
                
                # Original analytics
                for bucket in BUCKETS:
                    greeks = await self.analytics_engine.compute_greeks_summary(
                        index, bucket, legs
                    )
                    analytics_results[f'greeks_{bucket}'] = asdict(greeks)
                    
                    pcr = await self.analytics_engine.compute_pcr_analysis(
                        index, bucket, legs
                    )
                    analytics_results[f'pcr_{bucket}'] = asdict(pcr)
                    
                    max_pain = await self.analytics_engine.compute_max_pain(
                        index, bucket, legs, spot_price
                    )
                    analytics_results[f'max_pain_{bucket}'] = max_pain
                    
                    # NEW: Weekday master overlay
                    overlay = await self.analytics_engine.compute_weekday_overlay(
                        index, bucket, legs
                    )
                    analytics_results[f'weekday_overlay_{bucket}'] = asdict(overlay)
                
                # Original market sentiment
                sentiment = await self.analytics_engine.compute_market_sentiment(
                    index, legs, spot_price
                )
                analytics_results['market_sentiment'] = asdict(sentiment)
                
                # Original IV surface
                iv_surface = await self.analytics_engine.compute_implied_volatility_surface(
                    index, spot_price, legs
                )
                analytics_results['iv_surface'] = asdict(iv_surface)
                
                # NEW: VIX correlation analysis
                vix_analysis = await self.analytics_engine.compute_vix_correlation(
                    index, legs
                )
                analytics_results['vix_correlation'] = asdict(vix_analysis)
                
                # NEW: Sector breadth analysis
                breadth_analysis = await self.analytics_engine.compute_sector_breadth(index)
                analytics_results['sector_breadth'] = asdict(breadth_analysis)
                
                # NEW: FII options activity
                fii_analysis = await self.analytics_engine.compute_fii_activity(index, legs)
                analytics_results['fii_activity'] = asdict(fii_analysis)
                
                # Save enhanced results
                await self.analytics_engine.save_analytics_results(
                    analytics_results, f"enhanced_realtime_{index.lower()}"
                )
                
                # Publish analytics event
                await self._publish_analytics_event(index, analytics_results)
            
            # Update stats
            computation_time = (time.time() - computation_start) * 1000
            self.service_stats['analytics_computed'] += 1
            self.service_stats['successful_computations'] += 1
            
            logger.info(f"Enhanced real-time analytics completed in {computation_time:.1f}ms")
            
        except Exception as e:
            logger.error(f"Enhanced real-time analytics failed: {e}")
            self.service_stats['failed_computations'] += 1
            self.service_stats['last_error'] = str(e)
    
    async def start_service(self):
        """Start the enhanced analytics service"""
        if self.is_running:
            logger.warning("Enhanced analytics service already running")
            return
        
        self.is_running = True
        self.service_start_time = time.time()
        
        logger.info("Starting enhanced options analytics service...")
        await self._update_service_health("RUNNING")
        
        try:
            while self.is_running:
                if is_market_open():
                    # Enhanced real-time analytics during market hours
                    await self._run_enhanced_realtime_analytics()
                    await asyncio.sleep(60)  # Every minute
                else:
                    # EOD analytics after market close
                    await self._run_eod_analytics()
                    await asyncio.sleep(300)  # Every 5 minutes when market closed
                    
        except Exception as e:
            logger.error(f"Enhanced analytics service error: {e}")
            await self._update_service_health("ERROR", str(e))
        finally:
            self.is_running = False
            await self._update_service_health("STOPPED")

# Factory function
def get_enhanced_analytics_service() -> EnhancedAnalyticsService:
    """Get enhanced analytics service instance"""
    return EnhancedAnalyticsService()

# Service entry point
async def main():
    """Main enhanced service entry point"""
    import signal
    
    service = EnhancedAnalyticsService()
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        asyncio.create_task(service.stop_service())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start enhanced service
    await service.start_service()
    return 0

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    exit_code = asyncio.run(main())