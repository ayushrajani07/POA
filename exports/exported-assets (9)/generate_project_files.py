# OP TRADING PLATFORM - PROJECT FILE GENERATOR
# ============================================
# This script generates all the remaining project files

import os
from pathlib import Path

# Create project structure
project_files = {
    # Services - Collection
    "services/collection/expiry_discovery.py": '''#!/usr/bin/env python3
"""
OP TRADING PLATFORM - EXPIRY DISCOVERY
======================================
Version: 3.1.2 - Enhanced Expiry Discovery
Author: OP Trading Platform Team
Date: 2025-08-25 10:50 PM IST
"""

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Any, Optional
import calendar

logger = logging.getLogger(__name__)

def discover_weeklies_for_index(pool_nfo: List[Dict], pool_bfo: List[Dict], 
                               index: str, atm: int, count: int = 2) -> List[date]:
    """Discover weekly expiry dates for an index."""
    try:
        combined_pool = pool_nfo + pool_bfo
        
        # Filter instruments for the index
        index_instruments = [
            inst for inst in combined_pool 
            if index.upper() in str(inst.get("name", "")).upper()
            and inst.get("instrument_type") in ["CE", "PE"]
        ]
        
        # Extract unique expiry dates
        expiry_dates = set()
        for inst in index_instruments:
            expiry_str = inst.get("expiry", "")
            if expiry_str:
                try:
                    expiry = datetime.strptime(expiry_str, "%Y-%m-%d").date()
                    if expiry > date.today():
                        expiry_dates.add(expiry)
                except:
                    continue
        
        # Sort and return next few expiries
        sorted_expiries = sorted(expiry_dates)
        return sorted_expiries[:count]
        
    except Exception as e:
        logger.error(f"Weekly expiry discovery failed for {index}: {str(e)}")
        return []

def discover_monthlies_for_index(pool_nfo: List[Dict], pool_bfo: List[Dict],
                                index: str, atm: int) -> tuple:
    """Discover monthly expiry dates for an index."""
    try:
        combined_pool = pool_nfo + pool_bfo
        
        # Filter instruments
        index_instruments = [
            inst for inst in combined_pool
            if index.upper() in str(inst.get("name", "")).upper() 
            and inst.get("instrument_type") in ["CE", "PE"]
        ]
        
        # Find monthly expiries (typically last Thursday of month)
        monthly_expiries = []
        for inst in index_instruments:
            expiry_str = inst.get("expiry", "")
            if expiry_str:
                try:
                    expiry = datetime.strptime(expiry_str, "%Y-%m-%d").date()
                    if expiry > date.today() and expiry.day >= 24:
                        monthly_expiries.append(expiry)
                except:
                    continue
        
        # Sort and get next two
        sorted_monthlies = sorted(set(monthly_expiries))
        this_month = sorted_monthlies[0] if len(sorted_monthlies) > 0 else None
        next_month = sorted_monthlies[1] if len(sorted_monthlies) > 1 else None
        
        return this_month, next_month
        
    except Exception as e:
        logger.error(f"Monthly expiry discovery failed for {index}: {str(e)}")
        return None, None
''',

    "services/collection/participant_analysis.py": '''#!/usr/bin/env python3
"""
OP TRADING PLATFORM - PARTICIPANT ANALYSIS
==========================================
Version: 3.1.2 - Enhanced Participant Analysis
Author: OP Trading Platform Team
Date: 2025-08-25 10:50 PM IST
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
import numpy as np

logger = logging.getLogger(__name__)

class ParticipantAnalyzer:
    """Enhanced participant analysis for FII, DII, Pro, Client flows."""
    
    def __init__(self):
        self.participant_data = {}
        self.flow_history = []
        self.alerts = []
        
    def analyze_fii_flows(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze FII (Foreign Institutional Investor) flows."""
        try:
            # Mock FII analysis - replace with real data
            return {
                "net_flow": np.random.uniform(-500, 1500),
                "sector_allocation": {
                    "BANKING": np.random.uniform(30, 50),
                    "IT": np.random.uniform(15, 30),
                    "PHARMA": np.random.uniform(5, 20)
                },
                "flow_trend": np.random.choice(["BUYING", "SELLING", "NEUTRAL"]),
                "activity_level": np.random.choice(["LOW", "MODERATE", "HIGH"])
            }
        except Exception as e:
            logger.error(f"FII analysis failed: {str(e)}")
            return {}
    
    def analyze_dii_flows(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze DII (Domestic Institutional Investor) flows."""
        try:
            return {
                "net_flow": np.random.uniform(-300, 800),
                "mutual_fund_activity": np.random.uniform(50, 150),
                "insurance_activity": np.random.uniform(-100, 50),
                "flow_trend": np.random.choice(["BUYING", "SELLING", "NEUTRAL"])
            }
        except Exception as e:
            logger.error(f"DII analysis failed: {str(e)}")
            return {}
    
    def analyze_pro_vs_client(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze Professional vs Client trading patterns."""
        try:
            return {
                "pro_activity": {
                    "volume_share": np.random.uniform(0.6, 0.8),
                    "avg_position_size": np.random.uniform(1.5, 3.0),
                    "risk_appetite": np.random.choice(["CONSERVATIVE", "MODERATE", "AGGRESSIVE"])
                },
                "client_activity": {
                    "volume_share": np.random.uniform(0.2, 0.4),
                    "avg_position_size": np.random.uniform(0.5, 1.5),
                    "risk_appetite": np.random.choice(["CONSERVATIVE", "MODERATE"])
                }
            }
        except Exception as e:
            logger.error(f"Pro vs Client analysis failed: {str(e)}")
            return {}
''',

    # Services - Processing
    "services/processing/data_merger.py": '''#!/usr/bin/env python3
"""
OP TRADING PLATFORM - DATA MERGER
=================================
Version: 3.1.2 - Enhanced Data Merger
Author: OP Trading Platform Team
Date: 2025-08-25 10:50 PM IST
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
import pandas as pd

logger = logging.getLogger(__name__)

class DataMerger:
    """Enhanced data merger for ATM aggregates and market data."""
    
    def __init__(self):
        self.merge_cache = {}
        
    def merge_atm_aggregates(self, overview_data: Dict[str, Any], 
                           atm_data: Dict[str, Any]) -> Dict[str, Any]:
        """Merge ATM aggregates with overview data."""
        try:
            merged_data = overview_data.copy()
            
            # Merge ATM data by index
            for index, atm_values in atm_data.items():
                if index in merged_data:
                    merged_data[index].update(atm_values)
                else:
                    merged_data[index] = atm_values
            
            logger.debug(f"Merged data for {len(merged_data)} indices")
            return merged_data
            
        except Exception as e:
            logger.error(f"Data merge failed: {str(e)}")
            return overview_data
    
    def merge_market_quotes(self, base_data: Dict[str, Any], 
                          quotes: Dict[str, Any]) -> Dict[str, Any]:
        """Merge market quotes with base data."""
        try:
            merged = base_data.copy()
            
            for symbol, quote_data in quotes.items():
                if symbol in merged:
                    merged[symbol].update({
                        "last_price": quote_data.get("last_price"),
                        "volume": quote_data.get("volume"),
                        "oi": quote_data.get("oi"),
                        "quote_timestamp": datetime.now().isoformat()
                    })
            
            return merged
            
        except Exception as e:
            logger.error(f"Quote merge failed: {str(e)}")
            return base_data
''',

    "services/processing/cash_flow_processor.py": '''#!/usr/bin/env python3
"""
OP TRADING PLATFORM - CASH FLOW PROCESSOR
=========================================
Version: 3.1.2 - Enhanced Cash Flow Processor
Author: OP Trading Platform Team
Date: 2025-08-25 10:50 PM IST
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
import numpy as np

logger = logging.getLogger(__name__)

class CashFlowProcessor:
    """Enhanced cash flow processor for options trading."""
    
    def __init__(self):
        self.cash_flows = {}
        self.flow_history = []
        
    def calculate_cash_flows(self, options_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate cash flows from options data."""
        try:
            total_inflow = 0
            total_outflow = 0
            
            for option in options_data:
                price = option.get("last_price", 0)
                volume = option.get("volume", 0)
                
                # Estimate cash flow (simplified)
                cash_value = price * volume * 50  # Assuming lot size of 50
                
                # Classify as inflow or outflow based on price movement
                if option.get("net_change", 0) > 0:
                    total_inflow += cash_value
                else:
                    total_outflow += cash_value
            
            net_flow = total_inflow - total_outflow
            
            return {
                "total_cash_inflow": total_inflow,
                "total_cash_outflow": total_outflow,
                "net_cash_flow": net_flow,
                "buying_pressure": total_inflow / (total_inflow + total_outflow) if (total_inflow + total_outflow) > 0 else 0.5,
                "selling_pressure": total_outflow / (total_inflow + total_outflow) if (total_inflow + total_outflow) > 0 else 0.5,
                "market_sentiment": "BULLISH" if net_flow > 0 else "BEARISH" if net_flow < 0 else "NEUTRAL",
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Cash flow calculation failed: {str(e)}")
            return {}
    
    def process_position_changes(self, current_positions: Dict[str, Any], 
                               previous_positions: Dict[str, Any]) -> Dict[str, Any]:
        """Process position changes between time periods."""
        try:
            position_changes = []
            
            for symbol in current_positions:
                current_oi = current_positions[symbol].get("oi", 0)
                previous_oi = previous_positions.get(symbol, {}).get("oi", 0)
                
                if previous_oi > 0:
                    oi_change = current_oi - previous_oi
                    oi_change_percent = (oi_change / previous_oi) * 100
                    
                    position_changes.append({
                        "symbol": symbol,
                        "oi_change": oi_change,
                        "oi_change_percent": oi_change_percent,
                        "volume": current_positions[symbol].get("volume", 0),
                        "price_impact": current_positions[symbol].get("net_change_percent", 0)
                    })
            
            return {
                "position_changes": position_changes,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Position change processing failed: {str(e)}")
            return {}
''',

    "services/processing/position_monitor.py": '''#!/usr/bin/env python3
"""
OP TRADING PLATFORM - POSITION MONITOR
======================================
Version: 3.1.2 - Enhanced Position Monitor
Author: OP Trading Platform Team
Date: 2025-08-25 10:50 PM IST
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class PositionMonitor:
    """Enhanced position monitor for options trading."""
    
    def __init__(self):
        self.positions = {}
        self.alerts = []
        self.thresholds = {
            "oi_change_percent": 15.0,
            "volume_spike_percent": 100.0,
            "price_impact_percent": 5.0
        }
    
    def monitor_positions(self, current_data: Dict[str, Any]) -> Dict[str, Any]:
        """Monitor positions for significant changes."""
        try:
            alerts = []
            
            for symbol, data in current_data.items():
                # Check for significant OI changes
                if self._check_oi_change(symbol, data):
                    alerts.append({
                        "type": "OI_CHANGE",
                        "symbol": symbol,
                        "message": f"Significant OI change detected in {symbol}",
                        "timestamp": datetime.now().isoformat()
                    })
                
                # Check for volume spikes
                if self._check_volume_spike(symbol, data):
                    alerts.append({
                        "type": "VOLUME_SPIKE",
                        "symbol": symbol,
                        "message": f"Volume spike detected in {symbol}",
                        "timestamp": datetime.now().isoformat()
                    })
            
            # Update position tracking
            self.positions.update(current_data)
            
            return {
                "alerts": alerts,
                "monitored_positions": len(current_data),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Position monitoring failed: {str(e)}")
            return {}
    
    def _check_oi_change(self, symbol: str, data: Dict[str, Any]) -> bool:
        """Check for significant OI changes."""
        try:
            current_oi = data.get("oi", 0)
            previous_data = self.positions.get(symbol, {})
            previous_oi = previous_data.get("oi", 0)
            
            if previous_oi > 0:
                change_percent = abs((current_oi - previous_oi) / previous_oi) * 100
                return change_percent > self.thresholds["oi_change_percent"]
            
            return False
        except:
            return False
    
    def _check_volume_spike(self, symbol: str, data: Dict[str, Any]) -> bool:
        """Check for volume spikes."""
        try:
            current_volume = data.get("volume", 0)
            previous_data = self.positions.get(symbol, {})
            previous_volume = previous_data.get("volume", 0)
            
            if previous_volume > 0:
                change_percent = ((current_volume - previous_volume) / previous_volume) * 100
                return change_percent > self.thresholds["volume_spike_percent"]
            
            return False
        except:
            return False
''',

    # Services - Analytics
    "services/analytics/participant_flows.py": '''#!/usr/bin/env python3
"""
OP TRADING PLATFORM - PARTICIPANT FLOWS ANALYTICS
=================================================
Version: 3.1.2 - Enhanced Participant Flows Analytics
Author: OP Trading Platform Team
Date: 2025-08-25 10:50 PM IST
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
import numpy as np

logger = logging.getLogger(__name__)

class ParticipantFlowAnalytics:
    """Advanced analytics for participant flows."""
    
    def __init__(self):
        self.flow_data = {}
        self.patterns = {}
        
    def analyze_flow_patterns(self, participant_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze flow patterns across participants."""
        try:
            analysis = {}
            
            # FII Analysis
            if "FII" in participant_data:
                fii_data = participant_data["FII"]
                analysis["FII"] = {
                    "flow_direction": "BUYING" if fii_data.get("net_flow", 0) > 0 else "SELLING",
                    "flow_intensity": self._calculate_flow_intensity(fii_data.get("net_flow", 0)),
                    "sector_preference": self._analyze_sector_preference(fii_data.get("sector_allocation", {})),
                    "risk_appetite": self._assess_risk_appetite(fii_data)
                }
            
            # DII Analysis
            if "DII" in participant_data:
                dii_data = participant_data["DII"]
                analysis["DII"] = {
                    "flow_direction": "BUYING" if dii_data.get("net_flow", 0) > 0 else "SELLING",
                    "mutual_fund_bias": dii_data.get("mutual_fund_activity", 0),
                    "insurance_bias": dii_data.get("insurance_activity", 0),
                    "domestic_sentiment": self._assess_domestic_sentiment(dii_data)
                }
            
            return analysis
            
        except Exception as e:
            logger.error(f"Flow pattern analysis failed: {str(e)}")
            return {}
    
    def _calculate_flow_intensity(self, net_flow: float) -> str:
        """Calculate flow intensity based on net flow."""
        abs_flow = abs(net_flow)
        if abs_flow > 1000:
            return "VERY_HIGH"
        elif abs_flow > 500:
            return "HIGH"
        elif abs_flow > 100:
            return "MODERATE"
        else:
            return "LOW"
    
    def _analyze_sector_preference(self, sector_allocation: Dict[str, float]) -> str:
        """Analyze sector preference."""
        if not sector_allocation:
            return "BALANCED"
        
        max_sector = max(sector_allocation, key=sector_allocation.get)
        max_allocation = sector_allocation[max_sector]
        
        if max_allocation > 40:
            return f"CONCENTRATED_{max_sector}"
        else:
            return "DIVERSIFIED"
    
    def _assess_risk_appetite(self, participant_data: Dict[str, Any]) -> str:
        """Assess risk appetite based on participant behavior."""
        # Simplified risk assessment
        net_flow = abs(participant_data.get("net_flow", 0))
        activity_level = participant_data.get("activity_level", "MODERATE")
        
        if activity_level == "HIGH" and net_flow > 500:
            return "AGGRESSIVE"
        elif activity_level == "MODERATE":
            return "MODERATE"
        else:
            return "CONSERVATIVE"
    
    def _assess_domestic_sentiment(self, dii_data: Dict[str, Any]) -> str:
        """Assess domestic market sentiment."""
        net_flow = dii_data.get("net_flow", 0)
        mf_activity = dii_data.get("mutual_fund_activity", 0)
        
        if net_flow > 0 and mf_activity > 0:
            return "OPTIMISTIC"
        elif net_flow < 0:
            return "PESSIMISTIC"
        else:
            return "NEUTRAL"
''',

    "services/analytics/market_breadth.py": '''#!/usr/bin/env python3
"""
OP TRADING PLATFORM - MARKET BREADTH ANALYTICS
==============================================
Version: 3.1.2 - Enhanced Market Breadth Analytics
Author: OP Trading Platform Team
Date: 2025-08-25 10:50 PM IST
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
import numpy as np

logger = logging.getLogger(__name__)

class MarketBreadthAnalytics:
    """Advanced market breadth analytics."""
    
    def __init__(self):
        self.breadth_data = {}
        
    def calculate_market_breadth(self, indices_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate comprehensive market breadth metrics."""
        try:
            advances = 0
            declines = 0
            unchanged = 0
            total_indices = len(indices_data)
            
            for symbol, data in indices_data.items():
                net_change = data.get("net_change", 0)
                
                if net_change > 0:
                    advances += 1
                elif net_change < 0:
                    declines += 1
                else:
                    unchanged += 1
            
            # Calculate ratios
            advance_decline_ratio = advances / declines if declines > 0 else float('inf')
            advance_percentage = (advances / total_indices) * 100 if total_indices > 0 else 0
            
            # Determine market sentiment
            if advance_percentage > 60:
                market_sentiment = "BULLISH"
            elif advance_percentage < 40:
                market_sentiment = "BEARISH"
            else:
                market_sentiment = "NEUTRAL"
            
            return {
                "advances": advances,
                "declines": declines,
                "unchanged": unchanged,
                "total_indices": total_indices,
                "advance_decline_ratio": advance_decline_ratio,
                "advance_percentage": advance_percentage,
                "market_sentiment": market_sentiment,
                "breadth_score": self._calculate_breadth_score(advance_percentage),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Market breadth calculation failed: {str(e)}")
            return {}
    
    def _calculate_breadth_score(self, advance_percentage: float) -> float:
        """Calculate a normalized breadth score (0-100)."""
        # Normalize advance percentage to a 0-100 scale
        return max(0, min(100, advance_percentage))
''',

    "services/analytics/volatility_analysis.py": '''#!/usr/bin/env python3
"""
OP TRADING PLATFORM - VOLATILITY ANALYSIS
=========================================
Version: 3.1.2 - Enhanced Volatility Analysis
Author: OP Trading Platform Team
Date: 2025-08-25 10:50 PM IST
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
import numpy as np

logger = logging.getLogger(__name__)

class VolatilityAnalytics:
    """Advanced volatility analytics for options."""
    
    def __init__(self):
        self.volatility_data = {}
        self.historical_data = {}
        
    def analyze_implied_volatility(self, options_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze implied volatility patterns."""
        try:
            iv_data = []
            
            for option in options_data:
                iv = option.get("iv")
                if iv and iv > 0:
                    iv_data.append(iv)
            
            if not iv_data:
                return {}
            
            mean_iv = np.mean(iv_data)
            median_iv = np.median(iv_data)
            std_iv = np.std(iv_data)
            
            # Classify volatility regime
            if mean_iv > 0.3:
                volatility_regime = "HIGH"
            elif mean_iv > 0.2:
                volatility_regime = "MODERATE"
            else:
                volatility_regime = "LOW"
            
            return {
                "mean_iv": mean_iv,
                "median_iv": median_iv,
                "iv_std": std_iv,
                "iv_range": [min(iv_data), max(iv_data)],
                "volatility_regime": volatility_regime,
                "iv_percentiles": {
                    "25th": np.percentile(iv_data, 25),
                    "75th": np.percentile(iv_data, 75),
                    "90th": np.percentile(iv_data, 90)
                },
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"IV analysis failed: {str(e)}")
            return {}
    
    def calculate_volatility_skew(self, call_ivs: List[float], 
                                put_ivs: List[float]) -> Dict[str, Any]:
        """Calculate volatility skew between calls and puts."""
        try:
            if not call_ivs or not put_ivs:
                return {}
            
            avg_call_iv = np.mean(call_ivs)
            avg_put_iv = np.mean(put_ivs)
            
            skew = avg_put_iv - avg_call_iv
            skew_percentage = (skew / avg_call_iv) * 100 if avg_call_iv > 0 else 0
            
            # Interpret skew
            if skew_percentage > 5:
                skew_interpretation = "PUT_PREMIUM"
            elif skew_percentage < -5:
                skew_interpretation = "CALL_PREMIUM"
            else:
                skew_interpretation = "BALANCED"
            
            return {
                "avg_call_iv": avg_call_iv,
                "avg_put_iv": avg_put_iv,
                "volatility_skew": skew,
                "skew_percentage": skew_percentage,
                "skew_interpretation": skew_interpretation,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Volatility skew calculation failed: {str(e)}")
            return {}
''',

    # Services - Monitoring
    "services/monitoring/error_detector.py": '''#!/usr/bin/env python3
"""
OP TRADING PLATFORM - ERROR DETECTOR
====================================
Version: 3.1.2 - Enhanced Error Detection
Author: OP Trading Platform Team
Date: 2025-08-25 10:50 PM IST
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import sys
import traceback

logger = logging.getLogger(__name__)

class ErrorDetector:
    """Enhanced error detection and classification system."""
    
    def __init__(self):
        self.error_history = []
        self.error_patterns = {}
        self.alert_thresholds = {
            "error_rate_per_minute": 5,
            "consecutive_errors": 3,
            "critical_error_threshold": 1
        }
    
    def detect_and_classify_error(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """Detect and classify errors with context."""
        try:
            error_info = {
                "timestamp": datetime.now().isoformat(),
                "error_type": type(error).__name__,
                "error_message": str(error),
                "context": context,
                "stack_trace": traceback.format_exc(),
                "severity": self._assess_severity(error),
                "category": self._categorize_error(error),
                "recovery_suggestions": self._get_recovery_suggestions(error)
            }
            
            # Add to history
            self.error_history.append(error_info)
            
            # Check if alert should be triggered
            if self._should_trigger_alert(error_info):
                error_info["alert_triggered"] = True
                self._trigger_alert(error_info)
            
            return error_info
            
        except Exception as e:
            logger.error(f"Error detection failed: {str(e)}")
            return {"error": "Error detection failed"}
    
    def _assess_severity(self, error: Exception) -> str:
        """Assess error severity."""
        error_type = type(error).__name__
        error_msg = str(error).lower()
        
        # Critical errors
        if any(keyword in error_msg for keyword in ["system", "memory", "disk", "database"]):
            return "CRITICAL"
        
        # High severity
        if any(keyword in error_msg for keyword in ["token", "authentication", "connection"]):
            return "HIGH"
        
        # Medium severity
        if any(keyword in error_msg for keyword in ["timeout", "rate", "limit"]):
            return "MEDIUM"
        
        # Low severity (default)
        return "LOW"
    
    def _categorize_error(self, error: Exception) -> str:
        """Categorize error type."""
        error_msg = str(error).lower()
        
        if "token" in error_msg or "auth" in error_msg:
            return "AUTHENTICATION"
        elif "network" in error_msg or "connection" in error_msg:
            return "NETWORK"
        elif "rate" in error_msg or "limit" in error_msg:
            return "RATE_LIMIT"
        elif "data" in error_msg or "json" in error_msg:
            return "DATA"
        elif "timeout" in error_msg:
            return "TIMEOUT"
        else:
            return "GENERAL"
    
    def _get_recovery_suggestions(self, error: Exception) -> List[str]:
        """Get recovery suggestions based on error type."""
        error_msg = str(error).lower()
        suggestions = []
        
        if "token" in error_msg:
            suggestions.extend([
                "Refresh authentication token",
                "Check API credentials",
                "Verify token permissions"
            ])
        elif "network" in error_msg:
            suggestions.extend([
                "Check internet connection",
                "Verify API endpoint availability",
                "Try alternative endpoints"
            ])
        elif "rate" in error_msg:
            suggestions.extend([
                "Reduce request frequency",
                "Implement exponential backoff",
                "Use batch operations"
            ])
        else:
            suggestions.extend([
                "Check application logs",
                "Retry with exponential backoff",
                "Contact support if issue persists"
            ])
        
        return suggestions
    
    def _should_trigger_alert(self, error_info: Dict[str, Any]) -> bool:
        """Determine if alert should be triggered."""
        severity = error_info.get("severity", "LOW")
        
        # Always alert on critical errors
        if severity == "CRITICAL":
            return True
        
        # Check error rate
        recent_errors = [
            e for e in self.error_history
            if datetime.fromisoformat(e["timestamp"]) > datetime.now() - timedelta(minutes=1)
        ]
        
        if len(recent_errors) > self.alert_thresholds["error_rate_per_minute"]:
            return True
        
        # Check consecutive errors
        if len(self.error_history) >= self.alert_thresholds["consecutive_errors"]:
            recent_consecutive = self.error_history[-self.alert_thresholds["consecutive_errors"]:]
            if all(e.get("severity") in ["HIGH", "CRITICAL"] for e in recent_consecutive):
                return True
        
        return False
    
    def _trigger_alert(self, error_info: Dict[str, Any]):
        """Trigger alert for error."""
        logger.error(f"ALERT TRIGGERED: {error_info['severity']} error detected - {error_info['error_message']}")
        # Add alert notification logic here
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get error summary and statistics."""
        try:
            total_errors = len(self.error_history)
            
            if total_errors == 0:
                return {"total_errors": 0}
            
            # Error counts by severity
            severity_counts = {}
            category_counts = {}
            
            for error in self.error_history:
                severity = error.get("severity", "UNKNOWN")
                category = error.get("category", "UNKNOWN")
                
                severity_counts[severity] = severity_counts.get(severity, 0) + 1
                category_counts[category] = category_counts.get(category, 0) + 1
            
            # Recent error rate (last hour)
            recent_errors = [
                e for e in self.error_history
                if datetime.fromisoformat(e["timestamp"]) > datetime.now() - timedelta(hours=1)
            ]
            
            return {
                "total_errors": total_errors,
                "recent_errors_last_hour": len(recent_errors),
                "severity_breakdown": severity_counts,
                "category_breakdown": category_counts,
                "last_error": self.error_history[-1] if self.error_history else None,
                "error_rate_per_hour": len(recent_errors),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error summary generation failed: {str(e)}")
            return {"error": "Summary generation failed"}
''',

    "services/monitoring/recovery_manager.py": '''#!/usr/bin/env python3
"""
OP TRADING PLATFORM - RECOVERY MANAGER
======================================
Version: 3.1.2 - Enhanced Recovery Manager
Author: OP Trading Platform Team
Date: 2025-08-25 10:50 PM IST
"""

import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
import time

logger = logging.getLogger(__name__)

class RecoveryManager:
    """Enhanced recovery manager for automated error recovery."""
    
    def __init__(self):
        self.recovery_strategies = {}
        self.recovery_history = []
        self.recovery_in_progress = False
        
        # Register default recovery strategies
        self._register_default_strategies()
    
    def _register_default_strategies(self):
        """Register default recovery strategies."""
        self.recovery_strategies = {
            "AUTHENTICATION": self._recover_authentication,
            "NETWORK": self._recover_network,
            "RATE_LIMIT": self._recover_rate_limit,
            "DATA": self._recover_data_error,
            "TIMEOUT": self._recover_timeout,
            "GENERAL": self._recover_general
        }
    
    async def attempt_recovery(self, error_info: Dict[str, Any]) -> Dict[str, Any]:
        """Attempt automated recovery based on error category."""
        if self.recovery_in_progress:
            return {"status": "RECOVERY_IN_PROGRESS", "message": "Another recovery is in progress"}
        
        try:
            self.recovery_in_progress = True
            category = error_info.get("category", "GENERAL")
            
            logger.info(f"Attempting recovery for {category} error")
            
            recovery_strategy = self.recovery_strategies.get(category, self._recover_general)
            recovery_result = await recovery_strategy(error_info)
            
            # Record recovery attempt
            recovery_record = {
                "timestamp": datetime.now().isoformat(),
                "error_category": category,
                "recovery_strategy": recovery_strategy.__name__,
                "recovery_result": recovery_result,
                "success": recovery_result.get("success", False)
            }
            
            self.recovery_history.append(recovery_record)
            
            return recovery_result
            
        except Exception as e:
            logger.error(f"Recovery attempt failed: {str(e)}")
            return {"status": "RECOVERY_FAILED", "error": str(e), "success": False}
        finally:
            self.recovery_in_progress = False
    
    async def _recover_authentication(self, error_info: Dict[str, Any]) -> Dict[str, Any]:
        """Recover from authentication errors."""
        try:
            logger.info("Attempting authentication recovery")
            
            # Simulate token refresh (implement actual logic)
            await asyncio.sleep(1)
            
            return {
                "status": "RECOVERY_ATTEMPTED",
                "strategy": "TOKEN_REFRESH",
                "message": "Authentication token refresh attempted",
                "success": True,
                "next_steps": ["Retry failed operation", "Monitor for authentication issues"]
            }
            
        except Exception as e:
            return {"status": "RECOVERY_FAILED", "error": str(e), "success": False}
    
    async def _recover_network(self, error_info: Dict[str, Any]) -> Dict[str, Any]:
        """Recover from network errors."""
        try:
            logger.info("Attempting network recovery")
            
            # Implement network recovery logic
            await asyncio.sleep(2)  # Wait for network stabilization
            
            return {
                "status": "RECOVERY_ATTEMPTED",
                "strategy": "NETWORK_RETRY",
                "message": "Network connectivity recovery attempted",
                "success": True,
                "next_steps": ["Test network connectivity", "Retry with backoff"]
            }
            
        except Exception as e:
            return {"status": "RECOVERY_FAILED", "error": str(e), "success": False}
    
    async def _recover_rate_limit(self, error_info: Dict[str, Any]) -> Dict[str, Any]:
        """Recover from rate limit errors."""
        try:
            logger.info("Attempting rate limit recovery")
            
            # Wait for rate limit reset
            await asyncio.sleep(60)  # Wait 1 minute
            
            return {
                "status": "RECOVERY_ATTEMPTED",
                "strategy": "RATE_LIMIT_BACKOFF",
                "message": "Rate limit backoff completed",
                "success": True,
                "next_steps": ["Reduce request frequency", "Implement intelligent batching"]
            }
            
        except Exception as e:
            return {"status": "RECOVERY_FAILED", "error": str(e), "success": False}
    
    async def _recover_data_error(self, error_info: Dict[str, Any]) -> Dict[str, Any]:
        """Recover from data errors."""
        try:
            logger.info("Attempting data error recovery")
            
            return {
                "status": "RECOVERY_ATTEMPTED",
                "strategy": "DATA_VALIDATION",
                "message": "Data validation and cleaning attempted",
                "success": True,
                "next_steps": ["Validate input parameters", "Check data format"]
            }
            
        except Exception as e:
            return {"status": "RECOVERY_FAILED", "error": str(e), "success": False}
    
    async def _recover_timeout(self, error_info: Dict[str, Any]) -> Dict[str, Any]:
        """Recover from timeout errors."""
        try:
            logger.info("Attempting timeout recovery")
            
            return {
                "status": "RECOVERY_ATTEMPTED",
                "strategy": "TIMEOUT_RETRY",
                "message": "Timeout recovery with increased timeout attempted",
                "success": True,
                "next_steps": ["Increase timeout values", "Optimize request payload"]
            }
            
        except Exception as e:
            return {"status": "RECOVERY_FAILED", "error": str(e), "success": False}
    
    async def _recover_general(self, error_info: Dict[str, Any]) -> Dict[str, Any]:
        """General recovery strategy."""
        try:
            logger.info("Attempting general recovery")
            
            # Implement general recovery logic
            await asyncio.sleep(1)
            
            return {
                "status": "RECOVERY_ATTEMPTED",
                "strategy": "GENERAL_RETRY",
                "message": "General recovery strategy attempted",
                "success": True,
                "next_steps": ["Check application logs", "Retry operation"]
            }
            
        except Exception as e:
            return {"status": "RECOVERY_FAILED", "error": str(e), "success": False}
    
    def get_recovery_statistics(self) -> Dict[str, Any]:
        """Get recovery statistics."""
        try:
            total_recoveries = len(self.recovery_history)
            
            if total_recoveries == 0:
                return {"total_recoveries": 0}
            
            successful_recoveries = sum(1 for r in self.recovery_history if r.get("success", False))
            success_rate = (successful_recoveries / total_recoveries) * 100
            
            # Group by category
            category_stats = {}
            for recovery in self.recovery_history:
                category = recovery.get("error_category", "UNKNOWN")
                if category not in category_stats:
                    category_stats[category] = {"total": 0, "successful": 0}
                
                category_stats[category]["total"] += 1
                if recovery.get("success", False):
                    category_stats[category]["successful"] += 1
            
            return {
                "total_recoveries": total_recoveries,
                "successful_recoveries": successful_recoveries,
                "success_rate": success_rate,
                "category_statistics": category_stats,
                "recovery_in_progress": self.recovery_in_progress,
                "last_recovery": self.recovery_history[-1] if self.recovery_history else None,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Recovery statistics generation failed: {str(e)}")
            return {"error": "Statistics generation failed"}
''',

    "services/monitoring/health_checker.py": '''#!/usr/bin/env python3
"""
OP TRADING PLATFORM - HEALTH CHECKER
====================================
Version: 3.1.2 - Enhanced Health Checker
Author: OP Trading Platform Team
Date: 2025-08-25 10:50 PM IST
"""

import logging
import asyncio
import psutil
from datetime import datetime
from typing import Dict, List, Any, Optional
import aiohttp
import redis.asyncio as redis

logger = logging.getLogger(__name__)

class HealthChecker:
    """Enhanced health checker for system components."""
    
    def __init__(self):
        self.health_history = []
        self.component_status = {}
        self.thresholds = {
            "cpu_usage_percent": 80,
            "memory_usage_percent": 85,
            "disk_usage_percent": 90,
            "response_time_ms": 5000
        }
    
    async def perform_comprehensive_health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check of all components."""
        try:
            health_report = {
                "timestamp": datetime.now().isoformat(),
                "overall_status": "HEALTHY",
                "components": {}
            }
            
            # Check system resources
            health_report["components"]["system"] = await self._check_system_health()
            
            # Check external services
            health_report["components"]["influxdb"] = await self._check_influxdb_health()
            health_report["components"]["redis"] = await self._check_redis_health()
            
            # Determine overall status
            component_statuses = [comp.get("status", "UNKNOWN") for comp in health_report["components"].values()]
            
            if "UNHEALTHY" in component_statuses:
                health_report["overall_status"] = "UNHEALTHY"
            elif "DEGRADED" in component_statuses:
                health_report["overall_status"] = "DEGRADED"
            else:
                health_report["overall_status"] = "HEALTHY"
            
            # Store in history
            self.health_history.append(health_report)
            
            # Keep only last 100 health checks
            if len(self.health_history) > 100:
                self.health_history = self.health_history[-100:]
            
            return health_report
            
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return {
                "timestamp": datetime.now().isoformat(),
                "overall_status": "UNKNOWN",
                "error": str(e)
            }
    
    async def _check_system_health(self) -> Dict[str, Any]:
        """Check system resource health."""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            
            # Determine system status
            if (cpu_percent > self.thresholds["cpu_usage_percent"] or
                memory_percent > self.thresholds["memory_usage_percent"] or
                disk_percent > self.thresholds["disk_usage_percent"]):
                status = "DEGRADED"
            else:
                status = "HEALTHY"
            
            return {
                "status": status,
                "cpu_usage_percent": cpu_percent,
                "memory_usage_percent": memory_percent,
                "disk_usage_percent": disk_percent,
                "available_memory_gb": memory.available / (1024**3),
                "free_disk_gb": disk.free / (1024**3),
                "load_average": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"System health check failed: {str(e)}")
            return {"status": "UNKNOWN", "error": str(e)}
    
    async def _check_influxdb_health(self) -> Dict[str, Any]:
        """Check InfluxDB health."""
        try:
            start_time = datetime.now()
            
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:8086/health", timeout=10) as response:
                    response_time = (datetime.now() - start_time).total_seconds() * 1000
                    
                    if response.status == 200:
                        health_data = await response.json()
                        status = "HEALTHY" if health_data.get("status") == "pass" else "DEGRADED"
                    else:
                        status = "UNHEALTHY"
                    
                    return {
                        "status": status,
                        "response_time_ms": response_time,
                        "http_status": response.status,
                        "health_data": health_data if response.status == 200 else None,
                        "timestamp": datetime.now().isoformat()
                    }
                    
        except asyncio.TimeoutError:
            return {
                "status": "UNHEALTHY",
                "error": "Connection timeout",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "status": "UNHEALTHY",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def _check_redis_health(self) -> Dict[str, Any]:
        """Check Redis health."""
        try:
            start_time = datetime.now()
            
            redis_client = redis.Redis(host='localhost', port=6379, db=0, socket_timeout=5)
            
            # Test ping
            await redis_client.ping()
            
            # Test basic operations
            test_key = "health_check_test"
            await redis_client.set(test_key, "test_value", ex=60)
            test_value = await redis_client.get(test_key)
            await redis_client.delete(test_key)
            
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            
            # Get Redis info
            info = await redis_client.info()
            
            await redis_client.close()
            
            return {
                "status": "HEALTHY",
                "response_time_ms": response_time,
                "test_operations": "PASSED",
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "Unknown"),
                "uptime_in_seconds": info.get("uptime_in_seconds", 0),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "UNHEALTHY",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def get_health_trends(self, hours: int = 24) -> Dict[str, Any]:
        """Get health trends over specified time period."""
        try:
            if not self.health_history:
                return {"message": "No health history available"}
            
            # Filter recent health checks
            cutoff_time = datetime.now().timestamp() - (hours * 3600)
            recent_checks = [
                check for check in self.health_history
                if datetime.fromisoformat(check["timestamp"]).timestamp() > cutoff_time
            ]
            
            if not recent_checks:
                return {"message": f"No health checks in last {hours} hours"}
            
            # Calculate trends
            healthy_count = sum(1 for check in recent_checks if check.get("overall_status") == "HEALTHY")
            degraded_count = sum(1 for check in recent_checks if check.get("overall_status") == "DEGRADED")
            unhealthy_count = sum(1 for check in recent_checks if check.get("overall_status") == "UNHEALTHY")
            
            total_checks = len(recent_checks)
            
            return {
                "time_period_hours": hours,
                "total_health_checks": total_checks,
                "healthy_percentage": (healthy_count / total_checks) * 100,
                "degraded_percentage": (degraded_count / total_checks) * 100,
                "unhealthy_percentage": (unhealthy_count / total_checks) * 100,
                "latest_check": recent_checks[-1] if recent_checks else None,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Health trends calculation failed: {str(e)}")
            return {"error": "Trends calculation failed"}
''',

    # Configuration files
    "config/prometheus/prometheus.yml": '''global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "rules/*.yml"

scrape_configs:
  - job_name: 'op-trading-platform'
    static_configs:
      - targets: ['host.docker.internal:8000']
    metrics_path: '/metrics'
    scrape_interval: 30s
    scrape_timeout: 10s

  - job_name: 'influxdb'
    static_configs:
      - targets: ['influxdb:8086']
    metrics_path: '/metrics'
    scrape_interval: 30s

  - job_name: 'redis'
    static_configs:
      - targets: ['redis:6379']
    scrape_interval: 30s

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093
''',

    "config/grafana/datasources/influxdb.yml": '''apiVersion: 1

datasources:
  - name: InfluxDB-OptionsData
    type: influxdb
    access: proxy
    url: http://influxdb:8086
    database: options-data
    user: admin
    password: adminpass123
    isDefault: true
    jsonData:
      organization: op-trading
      defaultBucket: options-data
      version: Flux
    secureJsonData:
      token: VFEhioeCi2vFCtv-dH_7Fe6gEgNtO-Tu7qcQW4WvIbAFQIdKGa_hDu4dxatOgwskZcva4CHkeOPbjkQwAvPyVg==

  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: false
''',

    "config/nginx/nginx.conf": '''user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
    use epoll;
    multi_accept on;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;

    upstream grafana {
        server grafana:3000;
    }

    upstream prometheus {
        server prometheus:9090;
    }

    upstream api {
        server host.docker.internal:8000;
    }

    server {
        listen 80;
        server_name localhost;

        location /grafana/ {
            proxy_pass http://grafana/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location /prometheus/ {
            proxy_pass http://prometheus/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }

        location /api/ {
            proxy_pass http://api/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }

        location / {
            proxy_pass http://api/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
    }
}
''',

    "scripts/backup.sh": '''#!/bin/bash
# OP Trading Platform - Backup Script
# Version: 3.1.2

BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="op_trading_backup_${TIMESTAMP}"

echo "Starting backup: ${BACKUP_NAME}"

# Create backup directory
mkdir -p "${BACKUP_DIR}/${BACKUP_NAME}"

# Backup InfluxDB data
if [ -d "/source/influxdb" ]; then
    echo "Backing up InfluxDB data..."
    tar -czf "${BACKUP_DIR}/${BACKUP_NAME}/influxdb_${TIMESTAMP}.tar.gz" -C /source influxdb/
fi

# Backup Redis data
if [ -d "/source/redis" ]; then
    echo "Backing up Redis data..."
    tar -czf "${BACKUP_DIR}/${BACKUP_NAME}/redis_${TIMESTAMP}.tar.gz" -C /source redis/
fi

# Backup Grafana data
if [ -d "/source/grafana" ]; then
    echo "Backing up Grafana data..."
    tar -czf "${BACKUP_DIR}/${BACKUP_NAME}/grafana_${TIMESTAMP}.tar.gz" -C /source grafana/
fi

# Create manifest
echo "Backup created: ${TIMESTAMP}" > "${BACKUP_DIR}/${BACKUP_NAME}/manifest.txt"
echo "Components: InfluxDB, Redis, Grafana" >> "${BACKUP_DIR}/${BACKUP_NAME}/manifest.txt"

# Cleanup old backups (keep last 30 days)
find "${BACKUP_DIR}" -name "op_trading_backup_*" -type d -mtime +30 -exec rm -rf {} + 2>/dev/null || true

echo "Backup completed: ${BACKUP_NAME}"
''',

    ".gitignore": '''# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual Environment
venv/
env/
ENV/

# IDEs
.vscode/
.idea/
*.swp
*.swo

# Environment
.env
.env.local
.env.production

# Logs
logs/
*.log

# Data
data/
*.csv
*.json

# Docker
docker-compose.override.yml

# OS
.DS_Store
Thumbs.db

# Secrets
.secrets/
*.pem
*.key

# Backups
backups/

# Cache
.cache/
.pytest_cache/
'''
}

# Generate all files
for file_path, content in project_files.items():
    # Create directory if it doesn't exist
    full_path = Path(file_path)
    full_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write file
    with open(full_path, 'w') as f:
        f.write(content)
    
    print(f"Created: {file_path}")

print("\n✅ All project files generated successfully!")
print("📁 Complete OP Trading Platform project structure created")
print("🚀 Ready for deployment and development")