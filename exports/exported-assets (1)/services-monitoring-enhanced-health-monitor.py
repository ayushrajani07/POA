"""
Enhanced health monitoring system with self-healing capabilities.
Provides comprehensive monitoring, alerting, and automatic recovery.
Significantly improved from the original health_monitor.py.
"""

import logging
import time
import asyncio
import psutil
import threading
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json
import sys
import os
import subprocess
from pathlib import Path
import smtplib
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart

# Import shared utilities
sys.path.append(str(Path(__file__).parent.parent.parent))

from shared.config.settings import get_settings
from shared.utils.time_utils import get_time_utils, TimeFormat
from shared.utils.coordination import get_redis_coordinator

logger = logging.getLogger(__name__)

class HealthStatus(Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"

class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"

@dataclass
class HealthMetric:
    """Individual health metric"""
    name: str
    value: float
    status: HealthStatus
    threshold_warning: float = 0
    threshold_critical: float = 0
    unit: str = ""
    timestamp: datetime = field(default_factory=lambda: get_time_utils().now_utc())
    message: str = ""

@dataclass
class ServiceHealth:
    """Overall service health status"""
    service_name: str
    status: HealthStatus
    metrics: Dict[str, HealthMetric] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=lambda: get_time_utils().now_utc())
    uptime_seconds: float = 0
    restart_count: int = 0
    error_count: int = 0
    last_error: str = ""
    
    def add_metric(self, metric: HealthMetric):
        """Add or update a health metric"""
        self.metrics[metric.name] = metric
        self.last_updated = get_time_utils().now_utc()
    
    def get_metric_value(self, name: str) -> Optional[float]:
        """Get value of a specific metric"""
        metric = self.metrics.get(name)
        return metric.value if metric else None
    
    def is_healthy(self) -> bool:
        """Check if service is healthy"""
        return self.status in [HealthStatus.HEALTHY, HealthStatus.WARNING]

@dataclass
class Alert:
    """System alert"""
    id: str
    service_name: str
    severity: AlertSeverity
    title: str
    description: str
    timestamp: datetime = field(default_factory=lambda: get_time_utils().now_utc())
    acknowledged: bool = False
    resolved: bool = False
    auto_resolved: bool = False
    recovery_action: str = ""

class HealthChecker:
    """Base class for health checkers"""
    
    def __init__(self, name: str):
        self.name = name
        self.settings = get_settings()
        self.time_utils = get_time_utils()
    
    def check(self) -> List[HealthMetric]:
        """Override this method in subclasses"""
        raise NotImplementedError

class SystemHealthChecker(HealthChecker):
    """System resource health checker"""
    
    def __init__(self):
        super().__init__("system")
    
    def check(self) -> List[HealthMetric]:
        """Check system resources"""
        metrics = []
        
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1.0)
        metrics.append(HealthMetric(
            name="cpu_usage_percent",
            value=cpu_percent,
            status=self._get_status(cpu_percent, 70, 90),
            threshold_warning=70,
            threshold_critical=90,
            unit="%",
            message=f"CPU usage at {cpu_percent:.1f}%"
        ))
        
        # Memory usage
        memory = psutil.virtual_memory()
        metrics.append(HealthMetric(
            name="memory_usage_percent",
            value=memory.percent,
            status=self._get_status(memory.percent, 80, 95),
            threshold_warning=80,
            threshold_critical=95,
            unit="%",
            message=f"Memory usage at {memory.percent:.1f}%"
        ))
        
        # Disk usage
        disk = psutil.disk_usage(self.settings.data.base_data_dir)
        disk_percent = (disk.used / disk.total) * 100
        metrics.append(HealthMetric(
            name="disk_usage_percent",
            value=disk_percent,
            status=self._get_status(disk_percent, 80, 95),
            threshold_warning=80,
            threshold_critical=95,
            unit="%",
            message=f"Disk usage at {disk_percent:.1f}%"
        ))
        
        # Available disk space
        available_gb = disk.free / (1024**3)
        metrics.append(HealthMetric(
            name="disk_available_gb",
            value=available_gb,
            status=self._get_status(available_gb, 5, 1, reverse=True),
            threshold_warning=5,
            threshold_critical=1,
            unit="GB",
            message=f"{available_gb:.1f}GB available"
        ))
        
        return metrics
    
    def _get_status(self, value: float, warning: float, critical: float, reverse: bool = False) -> HealthStatus:
        """Determine status based on thresholds"""
        if reverse:
            if value <= critical:
                return HealthStatus.CRITICAL
            elif value <= warning:
                return HealthStatus.WARNING
            else:
                return HealthStatus.HEALTHY
        else:
            if value >= critical:
                return HealthStatus.CRITICAL
            elif value >= warning:
                return HealthStatus.WARNING
            else:
                return HealthStatus.HEALTHY

class DatabaseHealthChecker(HealthChecker):
    """InfluxDB health checker"""
    
    def __init__(self):
        super().__init__("database")
        self.last_write_test = None
    
    def check(self) -> List[HealthMetric]:
        """Check database connectivity and performance"""
        metrics = []
        
        try:
            from influxdb_client import InfluxDBClient, Point
            
            # Test connection
            start_time = time.time()
            client = InfluxDBClient(
                url=self.settings.database.url,
                token=self.settings.database.token,
                org=self.settings.database.org,
                timeout=10
            )
            
            # Test ping
            health = client.health()
            connection_time = (time.time() - start_time) * 1000
            
            metrics.append(HealthMetric(
                name="connection_latency_ms",
                value=connection_time,
                status=self._get_latency_status(connection_time),
                threshold_warning=1000,
                threshold_critical=5000,
                unit="ms",
                message=f"Connection latency: {connection_time:.1f}ms"
            ))
            
            # Test write performance
            try:
                write_api = client.write_api()
                point = Point("health_check") \
                    .tag("test", "true") \
                    .field("value", 1) \
                    .time(self.time_utils.now_utc())
                
                write_start = time.time()
                write_api.write(bucket=self.settings.database.bucket, record=point)
                write_time = (time.time() - write_start) * 1000
                
                metrics.append(HealthMetric(
                    name="write_latency_ms",
                    value=write_time,
                    status=self._get_latency_status(write_time),
                    threshold_warning=2000,
                    threshold_critical=10000,
                    unit="ms",
                    message=f"Write latency: {write_time:.1f}ms"
                ))
                
                self.last_write_test = time.time()
                
            except Exception as e:
                metrics.append(HealthMetric(
                    name="write_success",
                    value=0,
                    status=HealthStatus.CRITICAL,
                    message=f"Write test failed: {str(e)[:100]}"
                ))
            
            # Test query performance
            try:
                query_api = client.query_api()
                query = f'''
                    from(bucket: "{self.settings.database.bucket}")
                    |> range(start: -5m)
                    |> filter(fn: (r) => r._measurement == "health_check")
                    |> limit(n: 1)
                '''
                
                query_start = time.time()
                result = query_api.query(query)
                query_time = (time.time() - query_start) * 1000
                
                metrics.append(HealthMetric(
                    name="query_latency_ms",
                    value=query_time,
                    status=self._get_latency_status(query_time),
                    threshold_warning=3000,
                    threshold_critical=15000,
                    unit="ms",
                    message=f"Query latency: {query_time:.1f}ms"
                ))
                
            except Exception as e:
                metrics.append(HealthMetric(
                    name="query_success",
                    value=0,
                    status=HealthStatus.CRITICAL,
                    message=f"Query test failed: {str(e)[:100]}"
                ))
            
            client.close()
            
        except Exception as e:
            metrics.append(HealthMetric(
                name="connection_success",
                value=0,
                status=HealthStatus.CRITICAL,
                message=f"Database connection failed: {str(e)[:100]}"
            ))
        
        return metrics
    
    def _get_latency_status(self, latency_ms: float) -> HealthStatus:
        """Get status based on latency"""
        if latency_ms > 5000:
            return HealthStatus.CRITICAL
        elif latency_ms > 1000:
            return HealthStatus.WARNING
        else:
            return HealthStatus.HEALTHY

class PipelineHealthChecker(HealthChecker):
    """Pipeline data flow health checker"""
    
    def __init__(self):
        super().__init__("pipeline")
        self.redis_coord = get_redis_coordinator()
    
    def check(self) -> List[HealthMetric]:
        """Check pipeline health and data flow"""
        metrics = []
        
        # Check Redis coordination
        try:
            redis_healthy = self.redis_coord.ping()
            metrics.append(HealthMetric(
                name="redis_connection",
                value=1.0 if redis_healthy else 0.0,
                status=HealthStatus.HEALTHY if redis_healthy else HealthStatus.CRITICAL,
                message="Redis connection OK" if redis_healthy else "Redis connection failed"
            ))
        except Exception as e:
            metrics.append(HealthMetric(
                name="redis_connection",
                value=0.0,
                status=HealthStatus.CRITICAL,
                message=f"Redis error: {str(e)[:100]}"
            ))
        
        # Check active services
        try:
            active_services = self.redis_coord.get_active_services()
            metrics.append(HealthMetric(
                name="active_services_count",
                value=len(active_services),
                status=HealthStatus.HEALTHY if len(active_services) > 0 else HealthStatus.WARNING,
                message=f"{len(active_services)} active services: {', '.join(active_services[:3])}"
            ))
        except Exception as e:
            metrics.append(HealthMetric(
                name="active_services_count",
                value=0,
                status=HealthStatus.WARNING,
                message=f"Could not get active services: {str(e)[:50]}"
            ))
        
        # Check data freshness
        self._check_data_freshness(metrics)
        
        # Check file system health
        self._check_file_system_health(metrics)
        
        return metrics
    
    def _check_data_freshness(self, metrics: List[HealthMetric]):
        """Check how fresh the data is"""
        try:
            from influxdb_client import InfluxDBClient
            
            client = InfluxDBClient(
                url=self.settings.database.url,
                token=self.settings.database.token,
                org=self.settings.database.org
            )
            
            query_api = client.query_api()
            
            # Check latest data point
            query = f'''
                from(bucket: "{self.settings.database.bucket}")
                |> range(start: -1h)
                |> filter(fn: (r) => r._measurement == "atm_option_quote" or r._measurement == "index_overview")
                |> group()
                |> last()
            '''
            
            result = query_api.query(query)
            
            if result:
                latest_time = None
                for table in result:
                    for row in table.records:
                        if latest_time is None or row.get_time() > latest_time:
                            latest_time = row.get_time()
                
                if latest_time:
                    now = self.time_utils.now_utc()
                    data_age = (now - latest_time).total_seconds()
                    
                    status = HealthStatus.HEALTHY
                    if data_age > 300:  # 5 minutes
                        status = HealthStatus.WARNING
                    if data_age > 900:  # 15 minutes
                        status = HealthStatus.CRITICAL
                    
                    metrics.append(HealthMetric(
                        name="data_freshness_seconds",
                        value=data_age,
                        status=status,
                        threshold_warning=300,
                        threshold_critical=900,
                        unit="seconds",
                        message=f"Latest data is {data_age:.0f} seconds old"
                    ))
                else:
                    metrics.append(HealthMetric(
                        name="data_freshness_seconds",
                        value=9999,
                        status=HealthStatus.CRITICAL,
                        message="No recent data found"
                    ))
            else:
                metrics.append(HealthMetric(
                    name="data_freshness_seconds",
                    value=9999,
                    status=HealthStatus.CRITICAL,
                    message="No data found in database"
                ))
            
            client.close()
            
        except Exception as e:
            metrics.append(HealthMetric(
                name="data_freshness_check",
                value=0,
                status=HealthStatus.WARNING,
                message=f"Could not check data freshness: {str(e)[:100]}"
            ))
    
    def _check_file_system_health(self, metrics: List[HealthMetric]):
        """Check file system health"""
        try:
            # Check CSV data directory
            csv_dir = self.settings.data.csv_data_root
            if csv_dir.exists():
                # Count recent files
                recent_files = 0
                cutoff_time = time.time() - 3600  # 1 hour ago
                
                for file_path in csv_dir.rglob("*.csv"):
                    if file_path.stat().st_mtime > cutoff_time:
                        recent_files += 1
                
                metrics.append(HealthMetric(
                    name="recent_csv_files_count",
                    value=recent_files,
                    status=HealthStatus.HEALTHY if recent_files > 0 else HealthStatus.WARNING,
                    message=f"{recent_files} CSV files modified in last hour"
                ))
            else:
                metrics.append(HealthMetric(
                    name="csv_directory_exists",
                    value=0,
                    status=HealthStatus.CRITICAL,
                    message=f"CSV data directory not found: {csv_dir}"
                ))
                
        except Exception as e:
            metrics.append(HealthMetric(
                name="filesystem_check",
                value=0,
                status=HealthStatus.WARNING,
                message=f"Filesystem check failed: {str(e)[:100]}"
            ))

class AlertManager:
    """Manages alerts and notifications"""
    
    def __init__(self):
        self.settings = get_settings()
        self.time_utils = get_time_utils()
        self.alerts: Dict[str, Alert] = {}
        self.alert_history: List[Alert] = []
        
        # Email configuration (if available)
        self.smtp_server = os.getenv("SMTP_SERVER")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.alert_recipients = os.getenv("ALERT_RECIPIENTS", "").split(",")
    
    def create_alert(self, service_name: str, severity: AlertSeverity, 
                    title: str, description: str) -> Alert:
        """Create a new alert"""
        alert_id = f"{service_name}_{severity.value}_{int(time.time())}"
        
        alert = Alert(
            id=alert_id,
            service_name=service_name,
            severity=severity,
            title=title,
            description=description
        )
        
        self.alerts[alert_id] = alert
        self.alert_history.append(alert)
        
        # Send notification
        self._send_notification(alert)
        
        return alert
    
    def resolve_alert(self, alert_id: str, auto_resolved: bool = False):
        """Resolve an alert"""
        if alert_id in self.alerts:
            alert = self.alerts[alert_id]
            alert.resolved = True
            alert.auto_resolved = auto_resolved
            
            logger.info(f"Alert resolved: {alert.title} ({'auto' if auto_resolved else 'manual'})")
            del self.alerts[alert_id]
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all active (unresolved) alerts"""
        return list(self.alerts.values())
    
    def get_critical_alerts(self) -> List[Alert]:
        """Get critical alerts only"""
        return [alert for alert in self.alerts.values() 
                if alert.severity in [AlertSeverity.CRITICAL, AlertSeverity.EMERGENCY]]
    
    def _send_notification(self, alert: Alert):
        """Send alert notification"""
        # Log alert
        logger.warning(f"ALERT [{alert.severity.value.upper()}] {alert.title}: {alert.description}")
        
        # Send email if configured
        if self.smtp_server and self.smtp_user and self.alert_recipients:
            try:
                self._send_email_alert(alert)
            except Exception as e:
                logger.error(f"Failed to send email alert: {e}")
        
        # Send to Redis for other services
        try:
            redis_coord = get_redis_coordinator()
            redis_coord.publish_message("system_alerts", {
                "alert_id": alert.id,
                "service": alert.service_name,
                "severity": alert.severity.value,
                "title": alert.title,
                "description": alert.description,
                "timestamp": alert.timestamp.isoformat()
            })
        except Exception as e:
            logger.error(f"Failed to publish alert to Redis: {e}")
    
    def _send_email_alert(self, alert: Alert):
        """Send email notification"""
        if not self.alert_recipients or not self.alert_recipients[0]:
            return
        
        msg = MimeMultipart()
        msg['From'] = self.smtp_user
        msg['To'] = ', '.join(self.alert_recipients)
        msg['Subject'] = f"[OP Trading System] {alert.severity.value.upper()}: {alert.title}"
        
        body = f"""
        Alert Details:
        - Service: {alert.service_name}
        - Severity: {alert.severity.value.upper()}
        - Title: {alert.title}
        - Description: {alert.description}
        - Time: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}
        
        This is an automated alert from the OP Trading System.
        """
        
        msg.attach(MimeText(body, 'plain'))
        
        server = smtplib.SMTP(self.smtp_server, self.smtp_port)
        server.starttls()
        server.login(self.smtp_user, self.smtp_password)
        server.send_message(msg)
        server.quit()

class SelfHealingManager:
    """Manages self-healing and recovery actions"""
    
    def __init__(self, alert_manager: AlertManager):
        self.alert_manager = alert_manager
        self.settings = get_settings()
        self.time_utils = get_time_utils()
        self.recovery_actions: Dict[str, Callable] = {}
        self.restart_counts: Dict[str, int] = {}
        self.last_restart: Dict[str, float] = {}
        
        # Register recovery actions
        self._register_recovery_actions()
    
    def _register_recovery_actions(self):
        """Register available recovery actions"""
        self.recovery_actions.update({
            "restart_service": self._restart_service,
            "cleanup_disk_space": self._cleanup_disk_space,
            "clear_redis_locks": self._clear_redis_locks,
            "restart_database_connection": self._restart_database_connection,
            "archive_old_data": self._archive_old_data,
        })
    
    def attempt_recovery(self, service_health: ServiceHealth) -> bool:
        """Attempt automatic recovery based on service health"""
        if not self.settings.monitoring.auto_restart_enabled:
            return False
        
        recovery_attempted = False
        
        # Check for critical issues and attempt recovery
        for metric_name, metric in service_health.metrics.items():
            if metric.status == HealthStatus.CRITICAL:
                recovery_action = self._determine_recovery_action(metric_name, metric)
                
                if recovery_action and self._can_attempt_recovery(service_health.service_name):
                    logger.info(f"Attempting recovery action '{recovery_action}' for {service_health.service_name}")
                    
                    try:
                        success = self.recovery_actions[recovery_action](service_health, metric)
                        if success:
                            recovery_attempted = True
                            
                            # Create recovery alert
                            self.alert_manager.create_alert(
                                service_health.service_name,
                                AlertSeverity.INFO,
                                f"Auto-recovery attempted",
                                f"Successfully executed recovery action: {recovery_action} for metric: {metric_name}"
                            )
                        else:
                            # Recovery failed
                            self.alert_manager.create_alert(
                                service_health.service_name,
                                AlertSeverity.CRITICAL,
                                f"Auto-recovery failed",
                                f"Failed to execute recovery action: {recovery_action} for metric: {metric_name}"
                            )
                    
                    except Exception as e:
                        logger.error(f"Recovery action failed: {e}")
                        self.alert_manager.create_alert(
                            service_health.service_name,
                            AlertSeverity.CRITICAL,
                            f"Recovery action error",
                            f"Error during recovery action {recovery_action}: {str(e)[:200]}"
                        )
        
        return recovery_attempted
    
    def _determine_recovery_action(self, metric_name: str, metric: HealthMetric) -> Optional[str]:
        """Determine appropriate recovery action for a metric"""
        recovery_map = {
            "disk_usage_percent": "cleanup_disk_space",
            "disk_available_gb": "archive_old_data",
            "connection_success": "restart_database_connection",
            "redis_connection": "clear_redis_locks",
            "data_freshness_seconds": "restart_service",
            "memory_usage_percent": "restart_service"
        }
        
        return recovery_map.get(metric_name)
    
    def _can_attempt_recovery(self, service_name: str) -> bool:
        """Check if recovery can be attempted for a service"""
        max_attempts = self.settings.monitoring.max_restart_attempts
        cooldown = self.settings.monitoring.restart_cooldown
        
        # Check restart count
        restart_count = self.restart_counts.get(service_name, 0)
        if restart_count >= max_attempts:
            return False
        
        # Check cooldown period
        last_restart = self.last_restart.get(service_name, 0)
        if time.time() - last_restart < cooldown:
            return False
        
        return True
    
    def _restart_service(self, service_health: ServiceHealth, metric: HealthMetric) -> bool:
        """Restart a service (placeholder - would need actual service management)"""
        # This would typically interface with systemd, docker, or process manager
        logger.info(f"Would restart service: {service_health.service_name}")
        
        # Update restart tracking
        self.restart_counts[service_health.service_name] = \
            self.restart_counts.get(service_health.service_name, 0) + 1
        self.last_restart[service_health.service_name] = time.time()
        
        # For now, just log the action
        return True
    
    def _cleanup_disk_space(self, service_health: ServiceHealth, metric: HealthMetric) -> bool:
        """Clean up disk space by removing old files"""
        try:
            settings = self.settings
            cleaned_bytes = 0
            
            # Remove old JSON snapshots if archival is enabled
            if settings.data.enable_archival:
                json_root = settings.data.json_snapshots_root
                cutoff_time = time.time() - (settings.data.archival_days * 24 * 3600)
                
                for json_file in json_root.rglob("*.json"):
                    if json_file.stat().st_mtime < cutoff_time:
                        file_size = json_file.stat().st_size
                        json_file.unlink()
                        cleaned_bytes += file_size
                
                # Compress remaining files
                for json_file in json_root.rglob("*.json"):
                    if json_file.stat().st_size > 1024 * 1024:  # > 1MB
                        import gzip
                        with open(json_file, 'rb') as f_in:
                            with gzip.open(f"{json_file}.gz", 'wb') as f_out:
                                f_out.write(f_in.read())
                        json_file.unlink()
            
            logger.info(f"Cleaned up {cleaned_bytes / (1024*1024):.1f} MB of disk space")
            return cleaned_bytes > 0
            
        except Exception as e:
            logger.error(f"Disk cleanup failed: {e}")
            return False
    
    def _clear_redis_locks(self, service_health: ServiceHealth, metric: HealthMetric) -> bool:
        """Clear expired Redis locks"""
        try:
            redis_coord = get_redis_coordinator()
            
            # Get all lock keys
            lock_keys = redis_coord.redis_client.keys("lock:*")
            expired_locks = 0
            
            for key in lock_keys:
                ttl = redis_coord.redis_client.ttl(key)
                if ttl == -1:  # No TTL set, might be stuck
                    redis_coord.redis_client.delete(key)
                    expired_locks += 1
            
            logger.info(f"Cleared {expired_locks} expired Redis locks")
            return expired_locks > 0
            
        except Exception as e:
            logger.error(f"Redis lock cleanup failed: {e}")
            return False
    
    def _restart_database_connection(self, service_health: ServiceHealth, metric: HealthMetric) -> bool:
        """Restart database connection (placeholder)"""
        # This would typically recreate connection pools
        logger.info("Would restart database connection")
        return True
    
    def _archive_old_data(self, service_health: ServiceHealth, metric: HealthMetric) -> bool:
        """Archive old data to free up space"""
        try:
            # Move old CSV files to archive directory
            csv_root = self.settings.data.csv_data_root
            archive_root = csv_root.parent / "archive"
            archive_root.mkdir(exist_ok=True)
            
            cutoff_time = time.time() - (7 * 24 * 3600)  # 7 days
            archived_files = 0
            
            for csv_file in csv_root.rglob("*.csv"):
                if csv_file.stat().st_mtime < cutoff_time:
                    archive_path = archive_root / csv_file.relative_to(csv_root)
                    archive_path.parent.mkdir(parents=True, exist_ok=True)
                    csv_file.rename(archive_path)
                    archived_files += 1
            
            logger.info(f"Archived {archived_files} old CSV files")
            return archived_files > 0
            
        except Exception as e:
            logger.error(f"Data archival failed: {e}")
            return False

class EnhancedHealthMonitor:
    """Enhanced health monitoring system with self-healing"""
    
    def __init__(self):
        self.settings = get_settings()
        self.time_utils = get_time_utils()
        self.redis_coord = get_redis_coordinator()
        
        # Initialize components
        self.alert_manager = AlertManager()
        self.healing_manager = SelfHealingManager(self.alert_manager)
        
        # Initialize health checkers
        self.checkers = {
            "system": SystemHealthChecker(),
            "database": DatabaseHealthChecker(),
            "pipeline": PipelineHealthChecker()
        }
        
        # Service health tracking
        self.service_health: Dict[str, ServiceHealth] = {}
        self.monitoring_active = False
        self.monitoring_thread = None
        
        # Performance tracking
        self.check_duration_history = []
        self.last_check_time = None
    
    def start_monitoring(self):
        """Start continuous health monitoring"""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        
        logger.info("Enhanced health monitoring started")
    
    def stop_monitoring(self):
        """Stop health monitoring"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        
        logger.info("Health monitoring stopped")
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring_active:
            try:
                start_time = time.time()
                
                # Run health checks
                self.run_health_checks()
                
                # Attempt self-healing if needed
                self._attempt_self_healing()
                
                # Update performance tracking
                check_duration = time.time() - start_time
                self.check_duration_history.append(check_duration)
                if len(self.check_duration_history) > 100:
                    self.check_duration_history.pop(0)
                
                self.last_check_time = time.time()
                
                # Sleep until next check
                time.sleep(self.settings.monitoring.health_check_interval)
                
            except Exception as e:
                logger.error(f"Health monitoring loop error: {e}")
                time.sleep(10)  # Back off on error
    
    def run_health_checks(self) -> Dict[str, ServiceHealth]:
        """Run all health checks and return service health status"""
        
        for service_name, checker in self.checkers.items():
            try:
                # Run health check
                metrics = checker.check()
                
                # Create or update service health
                if service_name not in self.service_health:
                    self.service_health[service_name] = ServiceHealth(
                        service_name=service_name,
                        status=HealthStatus.UNKNOWN
                    )
                
                service = self.service_health[service_name]
                
                # Update metrics
                for metric in metrics:
                    service.add_metric(metric)
                
                # Determine overall service status
                service.status = self._determine_service_status(metrics)
                
                # Check for alerts
                self._check_for_alerts(service, metrics)
                
                # Update service health in Redis
                self._update_service_health_in_redis(service)
                
            except Exception as e:
                logger.error(f"Health check failed for {service_name}: {e}")
                
                # Create error service health
                if service_name not in self.service_health:
                    self.service_health[service_name] = ServiceHealth(
                        service_name=service_name,
                        status=HealthStatus.CRITICAL
                    )
                
                self.service_health[service_name].status = HealthStatus.CRITICAL
                self.service_health[service_name].last_error = str(e)
                self.service_health[service_name].error_count += 1
        
        return self.service_health
    
    def _determine_service_status(self, metrics: List[HealthMetric]) -> HealthStatus:
        """Determine overall service status from metrics"""
        if not metrics:
            return HealthStatus.UNKNOWN
        
        has_critical = any(m.status == HealthStatus.CRITICAL for m in metrics)
        has_warning = any(m.status == HealthStatus.WARNING for m in metrics)
        
        if has_critical:
            return HealthStatus.CRITICAL
        elif has_warning:
            return HealthStatus.WARNING
        else:
            return HealthStatus.HEALTHY
    
    def _check_for_alerts(self, service: ServiceHealth, metrics: List[HealthMetric]):
        """Check metrics for alert conditions"""
        for metric in metrics:
            if metric.status == HealthStatus.CRITICAL:
                # Create critical alert
                alert_id = f"{service.service_name}_{metric.name}_critical"
                if alert_id not in self.alert_manager.alerts:
                    self.alert_manager.create_alert(
                        service.service_name,
                        AlertSeverity.CRITICAL,
                        f"Critical metric: {metric.name}",
                        f"{metric.message}. Value: {metric.value}{metric.unit}"
                    )
            
            elif metric.status == HealthStatus.WARNING:
                # Create warning alert
                alert_id = f"{service.service_name}_{metric.name}_warning"
                if alert_id not in self.alert_manager.alerts:
                    self.alert_manager.create_alert(
                        service.service_name,
                        AlertSeverity.WARNING,
                        f"Warning metric: {metric.name}",
                        f"{metric.message}. Value: {metric.value}{metric.unit}"
                    )
            
            else:
                # Resolve any existing alerts for this metric
                for alert_id in list(self.alert_manager.alerts.keys()):
                    if metric.name in alert_id and service.service_name in alert_id:
                        self.alert_manager.resolve_alert(alert_id, auto_resolved=True)
    
    def _attempt_self_healing(self):
        """Attempt self-healing for unhealthy services"""
        for service in self.service_health.values():
            if service.status == HealthStatus.CRITICAL:
                recovery_attempted = self.healing_manager.attempt_recovery(service)
                if recovery_attempted:
                    service.restart_count += 1
    
    def _update_service_health_in_redis(self, service: ServiceHealth):
        """Update service health status in Redis"""
        try:
            health_data = {
                "service_name": service.service_name,
                "status": service.status.value,
                "last_updated": service.last_updated.isoformat(),
                "uptime_seconds": service.uptime_seconds,
                "restart_count": service.restart_count,
                "error_count": service.error_count,
                "metrics": {
                    name: {
                        "value": metric.value,
                        "status": metric.status.value,
                        "unit": metric.unit,
                        "message": metric.message
                    }
                    for name, metric in service.metrics.items()
                }
            }
            
            self.redis_coord.set_service_health(service.service_name, health_data)
            
        except Exception as e:
            logger.error(f"Failed to update service health in Redis: {e}")
    
    def get_system_overview(self) -> Dict[str, Any]:
        """Get comprehensive system health overview"""
        overview = {
            "timestamp": self.time_utils.get_metadata_timestamp(),
            "overall_status": self._get_overall_status(),
            "services": {},
            "alerts": {
                "active": len(self.alert_manager.get_active_alerts()),
                "critical": len(self.alert_manager.get_critical_alerts())
            },
            "performance": {
                "last_check_duration": self.check_duration_history[-1] if self.check_duration_history else 0,
                "avg_check_duration": sum(self.check_duration_history) / len(self.check_duration_history) if self.check_duration_history else 0,
                "last_check_time": self.last_check_time
            }
        }
        
        # Add service details
        for service_name, service in self.service_health.items():
            overview["services"][service_name] = {
                "status": service.status.value,
                "last_updated": service.last_updated.isoformat(),
                "metrics_count": len(service.metrics),
                "restart_count": service.restart_count,
                "error_count": service.error_count
            }
        
        return overview
    
    def _get_overall_status(self) -> str:
        """Get overall system status"""
        if not self.service_health:
            return HealthStatus.UNKNOWN.value
        
        statuses = [service.status for service in self.service_health.values()]
        
        if any(status == HealthStatus.CRITICAL for status in statuses):
            return HealthStatus.CRITICAL.value
        elif any(status == HealthStatus.WARNING for status in statuses):
            return HealthStatus.WARNING.value
        else:
            return HealthStatus.HEALTHY.value

# Global health monitor instance
enhanced_monitor = EnhancedHealthMonitor()

def get_enhanced_monitor() -> EnhancedHealthMonitor:
    """Get the global enhanced health monitor"""
    return enhanced_monitor

# CLI interface for health monitoring
def main():
    """CLI interface for enhanced health monitoring"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Enhanced Health Monitor")
    parser.add_argument("--start", action="store_true", help="Start continuous monitoring")
    parser.add_argument("--check", action="store_true", help="Run one-time health check")
    parser.add_argument("--status", action="store_true", help="Show system status")
    parser.add_argument("--alerts", action="store_true", help="Show active alerts")
    
    args = parser.parse_args()
    
    monitor = get_enhanced_monitor()
    
    if args.start:
        print("Starting enhanced health monitoring...")
        monitor.start_monitoring()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping monitoring...")
            monitor.stop_monitoring()
    
    elif args.check:
        print("Running health check...")
        health = monitor.run_health_checks()
        for service_name, service in health.items():
            print(f"\n{service_name.upper()}: {service.status.value}")
            for metric_name, metric in service.metrics.items():
                print(f"  {metric_name}: {metric.value}{metric.unit} ({metric.status.value})")
    
    elif args.status:
        overview = monitor.get_system_overview()
        print(f"\nSystem Status: {overview['overall_status'].upper()}")
        print(f"Active Alerts: {overview['alerts']['active']} (Critical: {overview['alerts']['critical']})")
        print(f"Last Check: {overview['performance']['last_check_duration']:.2f}s ago")
        
        for service_name, service in overview['services'].items():
            print(f"\n{service_name}: {service['status']}")
    
    elif args.alerts:
        alerts = monitor.alert_manager.get_active_alerts()
        if alerts:
            print(f"\nActive Alerts ({len(alerts)}):")
            for alert in alerts:
                print(f"  [{alert.severity.value.upper()}] {alert.title}")
                print(f"    Service: {alert.service_name}")
                print(f"    Time: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print("\nNo active alerts")
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()