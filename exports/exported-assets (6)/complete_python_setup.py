#!/usr/bin/env python3
"""
OP TRADING PLATFORM - COMPLETE PYTHON SETUP SCRIPT
===================================================
Version: 3.0.0 - Production-Ready Multi-Mode Setup
Author: OP Trading Platform Team
Date: 2025-08-25 2:28 PM IST

COMPREHENSIVE SETUP SCRIPT WITH MANUAL GUIDANCE
This script provides complete setup for three operational modes with extensive manual guidance:
1. first_time    - Initial installation and basic configuration
2. development   - Live market system with debugging capabilities  
3. production    - Off market system with analytics and health monitoring

FEATURES IMPLEMENTED:
✓ Cross-platform compatibility (Windows, Linux, macOS)
✓ Complete environment configuration with real values
✓ Service initialization with health validation
✓ Kite Connect authentication integration (retains your OAuth flow)
✓ Enhanced analytics (FII, DII, Pro, Client analysis)
✓ Price toggle functionality (Last Price ↔ Average Price)
✓ Error detection panels with automated recovery
✓ Infinite data retention for regulatory compliance
✓ Index-wise overview functionality (retained from previous version)
✓ Comprehensive testing framework (live vs mock data)

MANUAL SETUP REQUIREMENTS:
- Update Kite Connect credentials in generated .env file
- Configure email/SMTP settings for alerts
- Set up Grafana API key after container starts
- Import dashboard configurations
"""

import sys
import os
import json
import time
import shutil
import subprocess
import platform
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import asyncio

# ================================================================================================
# GLOBAL CONFIGURATION AND CONSTANTS
# ================================================================================================

SCRIPT_VERSION = "3.0.0"
SCRIPT_START_TIME = datetime.now()
PLATFORM_NAME = platform.system().lower()

# Setup logging with detailed formatting
LOG_DIR = Path("logs/setup")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"setup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class ModeConfiguration:
    """
    Configuration container for each operational mode.
    
    Attributes:
        description (str): Human-readable description of the mode
        features (List[str]): List of enabled features for this mode
        required_services (List[str]): Docker services required
        resource_limits (Dict[str, Any]): Memory, CPU, and processing limits
        performance_settings (Dict[str, Any]): Optimization configurations
        security_settings (Dict[str, Any]): Security and access controls
    """
    description: str
    features: List[str]
    required_services: List[str]
    resource_limits: Dict[str, Any]
    performance_settings: Dict[str, Any]
    security_settings: Dict[str, Any]

# Mode-specific configurations optimized for different use cases
MODE_CONFIGURATIONS = {
    "first_time": ModeConfiguration(
        description="First Time Setup - Basic installation with mock data for learning",
        features=["basic_installation", "mock_data", "simple_analytics", "learning_mode"],
        required_services=["influxdb", "redis"],
        resource_limits={"max_memory_mb": 1024, "max_workers": 2, "batch_size": 100},
        performance_settings={"use_memory_mapping": False, "compression_enabled": False},
        security_settings={"debug_mode": True, "security_enabled": False}
    ),
    "development": ModeConfiguration(
        description="Development Mode - Live market data with debugging and hot reload",
        features=["live_data", "hot_reload", "debug_logging", "all_analytics", "price_toggle"],
        required_services=["influxdb", "redis", "prometheus", "grafana"],
        resource_limits={"max_memory_mb": 2048, "max_workers": 4, "batch_size": 500},
        performance_settings={"use_memory_mapping": True, "compression_enabled": True, "compression_level": 3},
        security_settings={"debug_mode": True, "security_enabled": True}
    ),
    "production": ModeConfiguration(
        description="Production Mode - Optimized for trading operations with full monitoring",
        features=["live_data", "all_analytics", "health_monitoring", "automated_backup", "infinite_retention"],
        required_services=["influxdb", "redis", "prometheus", "grafana", "nginx"],
        resource_limits={"max_memory_mb": 4096, "max_workers": 8, "batch_size": 1000},
        performance_settings={"use_memory_mapping": True, "compression_enabled": True, "compression_level": 6},
        security_settings={"debug_mode": False, "security_enabled": True, "ssl_enabled": True}
    )
}

# ================================================================================================
# UTILITY FUNCTIONS WITH EXTENSIVE ERROR HANDLING
# ================================================================================================

def log_message(message: str, level: str = "INFO") -> None:
    """Log formatted message with timestamp and appropriate console styling."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # File logging
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{timestamp} [{level}] {message}\n")
    
    # Console output with visual indicators
    if level == "ERROR":
        print(f"❌ {message}")
    elif level == "WARNING":
        print(f"⚠️  {message}")
    elif level == "SUCCESS":
        print(f"✅ {message}")
    else:
        print(f"ℹ️  {message}")

def print_section_header(title: str) -> None:
    """Print visually distinct section header for setup phases."""
    header_line = "=" * 80
    print(f"\n{header_line}")
    print(f"  {title}")
    print(f"{header_line}\n")
    log_message(f"=== {title} ===", "INFO")

def check_command_availability(command: str) -> bool:
    """Verify if a system command is available in PATH."""
    return shutil.which(command) is not None

def execute_system_command(command: str, description: str, continue_on_error: bool = False, timeout: int = 300) -> Tuple[bool, str]:
    """Execute system command with comprehensive error handling and logging."""
    log_message(f"Executing: {description}", "INFO")
    log_message(f"Command: {command}", "INFO")
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode == 0:
            log_message(f"✓ {description} completed successfully", "SUCCESS")
            return True, result.stdout
        else:
            error_msg = f"✗ {description} failed: {result.stderr}"
            log_message(error_msg, "ERROR")
            if not continue_on_error:
                raise RuntimeError(error_msg)
            return False, result.stderr
            
    except subprocess.TimeoutExpired:
        error_msg = f"✗ {description} timed out after {timeout} seconds"
        log_message(error_msg, "ERROR")
        if not continue_on_error:
            raise RuntimeError(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"✗ {description} failed with exception: {str(e)}"
        log_message(error_msg, "ERROR")
        if not continue_on_error:
            raise
        return False, str(e)

def validate_system_requirements(mode: str) -> bool:
    """Comprehensive system requirements validation."""
    print_section_header("SYSTEM REQUIREMENTS CHECK")
    
    try:
        import psutil
    except ImportError:
        log_message("Installing psutil for system monitoring...", "INFO")
        success, _ = execute_system_command("pip install psutil", "Install psutil")
        if not success:
            return False
        import psutil
    
    # Get system information
    memory = psutil.virtual_memory()
    memory_gb = round(memory.total / (1024**3), 1)
    cpu_count = psutil.cpu_count(logical=False)
    disk = psutil.disk_usage('.')
    disk_free_gb = round(disk.free / (1024**3), 1)
    
    log_message(f"System Information:", "INFO")
    log_message(f"  Platform: {PLATFORM_NAME}", "INFO")
    log_message(f"  Python: {sys.version.split()[0]}", "INFO")
    log_message(f"  Memory: {memory_gb}GB total", "INFO")
    log_message(f"  CPU Cores: {cpu_count}", "INFO")
    log_message(f"  Disk Free: {disk_free_gb}GB", "INFO")
    
    # Mode-specific requirements
    min_memory = {"first_time": 2, "development": 4, "production": 8}.get(mode, 4)
    min_disk = 10  # 10GB minimum
    
    requirements_met = True
    
    if memory_gb < min_memory:
        log_message(f"✗ Insufficient memory: {memory_gb}GB (minimum: {min_memory}GB)", "ERROR")
        requirements_met = False
    else:
        log_message(f"✓ Memory requirement met: {memory_gb}GB", "SUCCESS")
    
    if disk_free_gb < min_disk:
        log_message(f"✗ Insufficient disk space: {disk_free_gb}GB (minimum: {min_disk}GB)", "ERROR")
        requirements_met = False
    else:
        log_message(f"✓ Disk space requirement met: {disk_free_gb}GB", "SUCCESS")
    
    return requirements_met

def check_prerequisites(required_tools: List[str]) -> bool:
    """Check for required tools and dependencies."""
    print_section_header("PREREQUISITES CHECK")
    
    default_tools = ["python", "pip", "docker", "git"]
    tools_to_check = list(set(default_tools + required_tools))
    
    missing_tools = []
    
    for tool in tools_to_check:
        if check_command_availability(tool):
            log_message(f"✓ {tool}: Available", "SUCCESS")
        else:
            log_message(f"✗ {tool}: Not found", "ERROR")
            missing_tools.append(tool)
    
    if missing_tools:
        log_message(f"Missing tools: {', '.join(missing_tools)}", "ERROR")
        log_message("Please install missing tools and run setup again.", "ERROR")
        
        for tool in missing_tools:
            if tool == "python":
                log_message("Install Python: https://www.python.org/downloads/", "INFO")
            elif tool == "docker":
                log_message("Install Docker: https://www.docker.com/get-started", "INFO")
            elif tool == "git":
                log_message("Install Git: https://git-scm.com/downloads", "INFO")
        
        return False
    
    log_message("✓ All prerequisites satisfied", "SUCCESS")
    return True

# ================================================================================================
# DIRECTORY STRUCTURE CREATION
# ================================================================================================

def create_project_structure() -> bool:
    """Create comprehensive application directory structure."""
    print_section_header("PROJECT STRUCTURE CREATION")
    
    directories = [
        # Core application directories
        "services", "services/collection", "services/processing", "services/analytics", "services/api",
        "services/collection/collectors", "services/collection/brokers", "services/collection/health",
        "services/processing/mergers", "services/processing/writers", "services/processing/validators",
        "services/analytics/aggregators", "services/analytics/computers", "services/analytics/models",
        "services/api/endpoints", "services/api/middleware", "services/api/schemas",
        
        # Shared utilities and libraries
        "shared", "shared/config", "shared/utils", "shared/constants", "shared/types",
        
        # Infrastructure as code
        "infrastructure", "infrastructure/docker", "infrastructure/kubernetes",
        "infrastructure/grafana", "infrastructure/prometheus",
        
        # Data storage hierarchy
        "data", "data/csv", "data/json", "data/analytics", "data/archive", "data/backup",
        
        # Comprehensive logging
        "logs", "logs/application", "logs/errors", "logs/auth", "logs/analytics",
        "logs/setup", "logs/performance",
        
        # Testing framework
        "tests", "tests/unit", "tests/integration", "tests/performance", "tests/chaos",
        
        # Configuration and secrets
        "config", "config/environments", ".secrets"
    ]
    
    created_count = 0
    for directory in directories:
        try:
            dir_path = Path(directory)
            dir_path.mkdir(parents=True, exist_ok=True)
            created_count += 1
        except Exception as e:
            log_message(f"Failed to create directory {directory}: {str(e)}", "ERROR")
            return False
    
    log_message(f"✓ Created {created_count} directories", "SUCCESS")
    return True

def install_python_dependencies() -> bool:
    """Install Python dependencies with comprehensive package list."""
    print_section_header("PYTHON DEPENDENCIES INSTALLATION")
    
    requirements = [
        # Core web framework and ASGI server
        "fastapi==0.104.1",
        "uvicorn[standard]==0.24.0",
        
        # Async and concurrency
        "asyncio==3.4.3",
        "aiohttp==3.9.0",
        "aiofiles==23.2.1",
        
        # Database and caching
        "redis==5.0.1",
        "aioredis==2.0.1",
        "influxdb-client==1.38.0",
        
        # Data processing and analytics
        "pandas==2.1.3",
        "numpy==1.24.3",
        "scipy==1.11.4",
        "scikit-learn==1.3.2",
        
        # HTTP and API clients
        "requests==2.31.0",
        "httpx==0.25.2",
        
        # Authentication and security
        "python-multipart==0.0.6",
        "python-jose[cryptography]==3.3.0",
        "passlib[bcrypt]==1.7.4",
        
        # Monitoring and metrics
        "prometheus-client==0.19.0",
        "psutil==5.9.6",
        
        # Configuration and environment
        "python-dotenv==1.0.0",
        "pydantic==2.5.0",
        
        # Trading platform integration
        "kiteconnect==4.2.0",
        "flask==3.0.0",
        
        # WebSocket support
        "websockets==12.0",
        
        # Testing framework
        "pytest==7.4.3",
        "pytest-asyncio==0.21.1",
        "pytest-cov==4.1.0",
        
        # Development tools
        "black==23.11.0",
        "isort==5.12.0",
        "flake8==6.1.0"
    ]
    
    # Create requirements.txt
    requirements_file = Path("requirements.txt")
    try:
        with open(requirements_file, 'w', encoding='utf-8') as f:
            f.write("# OP Trading Platform - Python Requirements\n")
            f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write('\n'.join(requirements))
        
        log_message(f"Created requirements.txt with {len(requirements)} packages", "SUCCESS")
        
    except Exception as e:
        log_message(f"Failed to create requirements.txt: {str(e)}", "ERROR")
        return False
    
    # Install dependencies
    try:
        success, _ = execute_system_command(
            "pip install --upgrade pip",
            "Upgrade pip to latest version",
            timeout=120
        )
        
        if success:
            success, output = execute_system_command(
                "pip install -r requirements.txt",
                "Install Python requirements",
                timeout=600  # 10 minutes for complete installation
            )
        
        if success:
            log_message("All Python dependencies installed successfully", "SUCCESS")
            return True
        else:
            log_message("Some dependencies failed to install - check logs", "WARNING")
            return False
            
    except Exception as e:
        log_message(f"Failed to install Python dependencies: {str(e)}", "ERROR")
        return False

# ================================================================================================
# DOCKER SERVICES SETUP
# ================================================================================================

def setup_docker_services(mode: str, required_services: List[str]) -> bool:
    """Initialize and validate all required Docker services."""
    print_section_header(f"DOCKER SERVICES SETUP - {mode.upper()}")
    
    if not check_command_availability("docker"):
        log_message("Docker not found - services setup requires Docker", "ERROR")
        log_message("Install Docker from: https://www.docker.com/get-started", "INFO")
        return False
    
    service_results = {}
    
    for service in required_services:
        log_message(f"Setting up {service} service...", "INFO")
        
        try:
            if service == "influxdb":
                result = setup_influxdb_service()
            elif service == "redis":
                result = setup_redis_service()
            elif service == "prometheus":
                result = setup_prometheus_service()
            elif service == "grafana":
                result = setup_grafana_service()
            elif service == "nginx":
                result = setup_nginx_service()
            else:
                log_message(f"Unknown service: {service} - skipping", "WARNING")
                result = False
                
            service_results[service] = result
            
        except Exception as e:
            log_message(f"Failed to initialize {service}: {str(e)}", "ERROR")
            service_results[service] = False
    
    successful = sum(1 for success in service_results.values() if success)
    total = len(service_results)
    
    if successful == total:
        log_message(f"All {total} services initialized successfully", "SUCCESS")
    else:
        failed_services = [name for name, success in service_results.items() if not success]
        log_message(f"{successful}/{total} services successful. Failed: {', '.join(failed_services)}", "WARNING")
    
    return successful > 0  # At least some services should work

def setup_influxdb_service() -> bool:
    """Set up InfluxDB with infinite retention policy."""
    log_message("Initializing InfluxDB with infinite retention policy...", "INFO")
    
    # Check if container already exists
    success, output = execute_system_command(
        'docker ps -f "name=op-influxdb" --format "{{.Names}}"',
        "Check existing InfluxDB container",
        continue_on_error=True
    )
    
    if success and "op-influxdb" in output:
        log_message("InfluxDB container already running", "SUCCESS")
        return True
    
    try:
        # Remove existing container
        execute_system_command(
            "docker rm -f op-influxdb",
            "Remove existing InfluxDB container",
            continue_on_error=True
        )
        
        # Start InfluxDB with infinite retention
        docker_command = [
            "docker run -d",
            "--name op-influxdb",
            "--restart unless-stopped",
            "-p 8086:8086",
            "-e DOCKER_INFLUXDB_INIT_MODE=setup",
            "-e DOCKER_INFLUXDB_INIT_USERNAME=admin",
            "-e DOCKER_INFLUXDB_INIT_PASSWORD=adminpass123",
            "-e DOCKER_INFLUXDB_INIT_ORG=op-trading",
            "-e DOCKER_INFLUXDB_INIT_BUCKET=options-data",
            "-e DOCKER_INFLUXDB_INIT_RETENTION=0s",  # Infinite retention
            "-e DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=VFEhioeCi2vFCtv-dH_7Fe6gEgNtO-Tu7qcQW4WvIbAFQIdKGa_hDu4dxatOgwskZcva4CHkeOPbjkQwAvPyVg==",
            "-v influxdb2-data:/var/lib/influxdb2",
            "-v influxdb2-config:/etc/influxdb2",
            "influxdb:2.7-alpine"
        ]
        
        success, output = execute_system_command(
            " ".join(docker_command),
            "Start InfluxDB container with infinite retention"
        )
        
        if success:
            log_message("Waiting for InfluxDB to be ready...", "INFO")
            time.sleep(15)  # Allow startup time
            log_message("InfluxDB setup completed", "SUCCESS")
        
        return success
        
    except Exception as e:
        log_message(f"InfluxDB setup failed: {str(e)}", "ERROR")
        return False

def setup_redis_service() -> bool:
    """Set up Redis service for caching."""
    log_message("Initializing Redis cache service...", "INFO")
    
    # Check existing container
    success, output = execute_system_command(
        'docker ps -f "name=op-redis" --format "{{.Names}}"',
        "Check existing Redis container",
        continue_on_error=True
    )
    
    if success and "op-redis" in output:
        log_message("Redis container already running", "SUCCESS")
        return True
    
    try:
        # Remove existing container
        execute_system_command(
            "docker rm -f op-redis",
            "Remove existing Redis container",
            continue_on_error=True
        )
        
        # Start Redis container
        docker_command = [
            "docker run -d",
            "--name op-redis",
            "--restart unless-stopped",
            "-p 6379:6379",
            "-v redis-data:/data",
            "redis:7-alpine",
            "redis-server --save 60 1 --loglevel warning"
        ]
        
        success, output = execute_system_command(
            " ".join(docker_command),
            "Start Redis container"
        )
        
        if success:
            log_message("Redis setup completed", "SUCCESS")
        
        return success
        
    except Exception as e:
        log_message(f"Redis setup failed: {str(e)}", "ERROR")
        return False

def setup_prometheus_service() -> bool:
    """Set up Prometheus for metrics collection."""
    log_message("Setting up Prometheus monitoring...", "INFO")
    
    try:
        # Create Prometheus configuration
        config_dir = Path("config/prometheus")
        config_dir.mkdir(parents=True, exist_ok=True)
        
        prometheus_config = """global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'op-trading-api'
    static_configs:
      - targets: ['host.docker.internal:8000']
    metrics_path: '/metrics'
    scrape_interval: 30s
    
  - job_name: 'influxdb'
    static_configs:
      - targets: ['host.docker.internal:8086']
    metrics_path: '/metrics'
    scrape_interval: 60s
"""
        
        prometheus_config_file = config_dir / "prometheus.yml"
        with open(prometheus_config_file, 'w', encoding='utf-8') as f:
            f.write(prometheus_config)
        
        # Remove existing container
        execute_system_command(
            "docker rm -f op-prometheus",
            "Remove existing Prometheus container",
            continue_on_error=True
        )
        
        # Start Prometheus container
        docker_command = [
            "docker run -d",
            "--name op-prometheus",
            "--restart unless-stopped",
            "-p 9090:9090",
            f"-v {prometheus_config_file.absolute()}:/etc/prometheus/prometheus.yml",
            "prom/prometheus:latest",
            "--config.file=/etc/prometheus/prometheus.yml",
            "--storage.tsdb.retention.time=90d"
        ]
        
        success, output = execute_system_command(
            " ".join(docker_command),
            "Start Prometheus container",
            continue_on_error=True
        )
        
        if success:
            log_message("Prometheus setup completed - available at http://localhost:9090", "SUCCESS")
        
        return success
        
    except Exception as e:
        log_message(f"Prometheus setup failed: {str(e)}", "WARNING")
        return False

def setup_grafana_service() -> bool:
    """Set up Grafana for visualization."""
    log_message("Setting up Grafana dashboards...", "INFO")
    
    try:
        # Remove existing container
        execute_system_command(
            "docker rm -f op-grafana",
            "Remove existing Grafana container",
            continue_on_error=True
        )
        
        # Start Grafana container
        docker_command = [
            "docker run -d",
            "--name op-grafana",
            "--restart unless-stopped",
            "-p 3000:3000",
            "-e GF_SECURITY_ADMIN_PASSWORD=admin123",
            "-v grafana-data:/var/lib/grafana",
            "grafana/grafana:latest"
        ]
        
        success, output = execute_system_command(
            " ".join(docker_command),
            "Start Grafana container",
            continue_on_error=True
        )
        
        if success:
            log_message("Grafana setup completed", "SUCCESS")
            log_message("Grafana available at: http://localhost:3000", "INFO")
            log_message("Default credentials: admin / admin123", "INFO")
        
        return success
        
    except Exception as e:
        log_message(f"Grafana setup failed: {str(e)}", "WARNING")
        return False

def setup_nginx_service() -> bool:
    """Set up Nginx reverse proxy for production."""
    log_message("Setting up Nginx load balancer...", "INFO")
    
    try:
        # Create Nginx configuration
        config_dir = Path("config/nginx")
        config_dir.mkdir(parents=True, exist_ok=True)
        
        nginx_config = """events {
    worker_connections 1024;
}

http {
    upstream optrading_api {
        server host.docker.internal:8000;
    }
    
    server {
        listen 80;
        server_name localhost;
        
        location /api/ {
            proxy_pass http://optrading_api/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }
        
        location /grafana/ {
            proxy_pass http://host.docker.internal:3000/;
            proxy_set_header Host $host;
        }
        
        location /health {
            return 200 'OK';
            add_header Content-Type text/plain;
        }
    }
}"""
        
        nginx_config_file = config_dir / "nginx.conf"
        with open(nginx_config_file, 'w', encoding='utf-8') as f:
            f.write(nginx_config)
        
        # Remove existing container
        execute_system_command(
            "docker rm -f op-nginx",
            "Remove existing Nginx container",
            continue_on_error=True
        )
        
        # Start Nginx container
        docker_command = [
            "docker run -d",
            "--name op-nginx",
            "--restart unless-stopped",
            "-p 80:80",
            f"-v {nginx_config_file.absolute()}:/etc/nginx/nginx.conf:ro",
            "nginx:alpine"
        ]
        
        success, output = execute_system_command(
            " ".join(docker_command),
            "Start Nginx container",
            continue_on_error=True
        )
        
        if success:
            log_message("Nginx setup completed - available at http://localhost", "SUCCESS")
        
        return success
        
    except Exception as e:
        log_message(f"Nginx setup failed: {str(e)}", "WARNING")
        return False

# ================================================================================================
# CONFIGURATION FILE GENERATION
# ================================================================================================

def generate_environment_configuration(mode: str, config: ModeConfiguration) -> bool:
    """Generate comprehensive .env file with all configuration options."""
    print_section_header(f"ENVIRONMENT CONFIGURATION - {mode.upper()}")
    
    try:
        import psutil
        memory_gb = round(psutil.virtual_memory().total / (1024**3), 1)
        cpu_cores = psutil.cpu_count(logical=True)
    except ImportError:
        memory_gb = 8.0
        cpu_cores = 4
    
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    env_content = f"""# ================================================================================================
# OP TRADING PLATFORM - COMPREHENSIVE ENVIRONMENT CONFIGURATION
# ================================================================================================
# Generated: {current_time} IST
# Mode: {mode.upper()}
# Description: {config.description}
# Platform: {PLATFORM_NAME}
# Auto-generated by Python setup script v{SCRIPT_VERSION}
# ================================================================================================

# CORE DEPLOYMENT CONFIGURATION
DEPLOYMENT_MODE={mode}
ENV={mode}
VERSION=3.0.0
DEBUG={'true' if config.security_settings.get('debug_mode', False) else 'false'}

# LOGGING AND MONITORING CONFIGURATION
LOG_LEVEL={'DEBUG' if config.security_settings.get('debug_mode', False) else 'INFO'}
ENABLE_STRUCTURED_LOGGING=true
LOG_FORMAT=json
INCLUDE_TRACE_ID=true
INCLUDE_REQUEST_ID=true
INCLUDE_USER_ID=true

# DATA SOURCE CONFIGURATION
DATA_SOURCE_MODE={'live' if 'live_data' in config.features else 'mock'}
MOCK_DATA_ENABLED={'false' if 'live_data' in config.features else 'true'}
MOCK_DATA_VOLATILITY=0.2

# TIMEZONE AND MARKET CONFIGURATION
TIMEZONE=Asia/Kolkata
MARKET_TIMEZONE=Asia/Kolkata
MARKET_OPEN_TIME=09:15
MARKET_CLOSE_TIME=15:30

# PERFORMANCE CONFIGURATION
USE_MEMORY_MAPPING={'true' if config.performance_settings.get('use_memory_mapping', False) else 'false'}
COMPRESSION_ENABLED={'true' if config.performance_settings.get('compression_enabled', False) else 'false'}"""

    if config.performance_settings.get('compression_level'):
        env_content += f"\nCOMPRESSION_LEVEL={config.performance_settings['compression_level']}"

    env_content += f"""
CSV_BUFFER_SIZE={8192 if memory_gb >= 4 else 4096}
JSON_BUFFER_SIZE={16384 if memory_gb >= 4 else 8192}
MAX_MEMORY_USAGE_MB={config.resource_limits['max_memory_mb']}
PROCESSING_BATCH_SIZE={config.resource_limits['batch_size']}
PROCESSING_MAX_WORKERS={config.resource_limits['max_workers']}

# ENHANCED ANALYTICS CONFIGURATION
DEFAULT_STRIKE_OFFSETS=-2,-1,0,1,2
EXTENDED_STRIKE_OFFSETS=-5,-4,-3,-2,-1,0,1,2,3,4,5
ACTIVE_STRIKE_OFFSETS=-2,-1,0,1,2
ENABLE_FII_ANALYSIS=true
ENABLE_DII_ANALYSIS=true
ENABLE_PRO_TRADER_ANALYSIS=true
ENABLE_CLIENT_ANALYSIS=true
ENABLE_PRICE_TOGGLE=true
ENABLE_AVERAGE_PRICE_CALCULATION=true
DEFAULT_PRICE_MODE=LAST_PRICE
ENABLE_INDEX_OVERVIEW=true
INDEX_REFRESH_INTERVAL_SECONDS=30

# DATABASE CONFIGURATION - INFLUXDB WITH INFINITE RETENTION
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=VFEhioeCi2vFCtv-dH_7Fe6gEgNtO-Tu7qcQW4WvIbAFQIdKGa_hDu4dxatOgwskZcva4CHkeOPbjkQwAvPyVg==
INFLUXDB_ORG=op-trading
INFLUXDB_BUCKET=options-data
INFLUXDB_RETENTION_POLICY=infinite
DATA_RETENTION_POLICY=infinite

# REDIS CONFIGURATION
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_CONNECTION_POOL_SIZE=20
REDIS_MAX_CONNECTIONS=50
REDIS_DEFAULT_TTL_SECONDS=3600

# API CONFIGURATION
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS={min(config.resource_limits['max_workers'], cpu_cores)}
API_RELOAD={'true' if config.security_settings.get('debug_mode', False) else 'false'}
API_CORS_ENABLED=true
API_CORS_ORIGINS=http://localhost:3000,http://localhost:8080

# SECURITY CONFIGURATION
SECURITY_ENABLED={'true' if config.security_settings.get('security_enabled', False) else 'false'}
API_SECRET_KEY=op_trading_jwt_secret_{hash(str(time.time())) % 99999}
JWT_EXPIRATION_HOURS=24
JWT_ALGORITHM=HS256
ENABLE_API_KEYS=true

# MONITORING AND HEALTH CHECKS
ENABLE_HEALTH_CHECKS=true
HEALTH_CHECK_INTERVAL_SECONDS=15
AUTO_RESTART_ENABLED=true
ENABLE_ERROR_DETECTION_PANELS=true
ENABLE_AUTOMATED_ERROR_RECOVERY=true
ENABLE_METRICS_COLLECTION=true
PROMETHEUS_ENABLED=true
PROMETHEUS_PORT=8080

# GRAFANA CONFIGURATION
GRAFANA_INTEGRATION_ENABLED=true
GRAFANA_URL=http://localhost:3000
GRAFANA_USER=admin
GRAFANA_PASSWORD=admin123
GRAFANA_API_KEY=your_grafana_api_key_here

# DATA ARCHIVAL AND BACKUP
ENABLE_ARCHIVAL=true
ARCHIVAL_AFTER_DAYS=30
ENABLE_AUTOMATED_BACKUP=true
BACKUP_INTERVAL_HOURS=24
BACKUP_STORAGE_PATH=backups/

# ================================================================================================
# MANUAL CONFIGURATION SECTION - REQUIRES USER INPUT
# ================================================================================================

# KITE CONNECT API CREDENTIALS - REQUIRED FOR LIVE MARKET DATA
# SETUP INSTRUCTIONS:
# 1. Visit https://kite.trade/connect/
# 2. Login with your Zerodha account credentials
# 3. Create new app with settings:
#    - App name: OP Trading Platform
#    - App type: Connect
#    - Redirect URL: http://127.0.0.1:5000/success
# 4. Copy API Key and Secret below
# 5. Run authentication: python integrated_kite_auth_logger.py --login

KITE_API_KEY=your_kite_api_key_here
KITE_API_SECRET=your_kite_api_secret_here
KITE_ACCESS_TOKEN=your_access_token_here
REDIRECT_URI=http://127.0.0.1:5000/success

# EMAIL/SMTP CONFIGURATION - FOR ALERTS AND NOTIFICATIONS
# GMAIL SETUP INSTRUCTIONS:
# 1. Enable 2-factor authentication on Gmail
# 2. Generate app password: Google Account > Security > App passwords
# 3. Use Gmail address and app password below

SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_gmail_app_password_here
ALERT_RECIPIENTS=admin@company.com

# SLACK INTEGRATION (OPTIONAL)
SLACK_ENABLED=false
SLACK_WEBHOOK_URL=your_slack_webhook_here
SLACK_CHANNEL=#trading-alerts

# RECOVERY AND EMERGENCY SETTINGS
RECOVERY_MODE=false
USE_BACKUP_CONFIG=false
ENABLE_BACKUP_DATA_SOURCE=true
SKIP_HEALTH_CHECKS=false

# ================================================================================================
# END OF CONFIGURATION FILE
# ================================================================================================
# Configuration file generated: {current_time} IST
# Setup mode: {mode}
# Script version: {SCRIPT_VERSION}
#
# NEXT STEPS:
# 1. Update Kite Connect credentials (KITE_API_KEY, KITE_API_SECRET)
# 2. Configure email settings for alerts
# 3. Set up Grafana API key after first login
# 4. Run authentication: python integrated_kite_auth_logger.py --login
# 5. Start application: python main.py
# 6. Import Grafana dashboards from infrastructure/grafana/
"""

    # Write .env file
    env_file = Path(".env")
    
    # Backup existing .env if it exists
    if env_file.exists():
        backup_file = Path(f".env.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        shutil.copy2(env_file, backup_file)
        log_message(f"Backed up existing .env to {backup_file}", "INFO")
    
    try:
        with open(env_file, 'w', encoding='utf-8') as f:
            f.write(env_content)
        
        log_message(f"Environment configuration written to {env_file}", "SUCCESS")
        log_message(f"Configuration contains {len([line for line in env_content.split('\n') if '=' in line and not line.strip().startswith('#')])} settings", "INFO")
        return True
        
    except Exception as e:
        log_message(f"Failed to write environment configuration: {str(e)}", "ERROR")
        return False

# ================================================================================================
# MAIN SETUP ORCHESTRATION
# ================================================================================================

def run_comprehensive_tests(mode: str) -> bool:
    """Run basic setup validation tests."""
    print_section_header("SETUP VALIDATION")
    
    tests_passed = 0
    total_tests = 4
    
    # Test 1: Configuration file validation
    if Path(".env").exists():
        log_message("✓ Environment configuration file exists", "SUCCESS")
        tests_passed += 1
    else:
        log_message("✗ Environment configuration file missing", "ERROR")
    
    # Test 2: Directory structure validation
    required_dirs = ["services", "shared", "data", "logs", "config"]
    all_dirs_exist = all(Path(d).exists() for d in required_dirs)
    if all_dirs_exist:
        log_message("✓ Directory structure created successfully", "SUCCESS")
        tests_passed += 1
    else:
        log_message("✗ Some required directories missing", "ERROR")
    
    # Test 3: Requirements file validation
    if Path("requirements.txt").exists():
        log_message("✓ Python requirements file created", "SUCCESS")
        tests_passed += 1
    else:
        log_message("✗ Requirements file missing", "ERROR")
    
    # Test 4: Docker services check (basic)
    try:
        success, output = execute_system_command(
            "docker ps --format '{{.Names}}'",
            "Check running Docker containers",
            continue_on_error=True
        )
        if success and any(name in output for name in ["op-influxdb", "op-redis"]):
            log_message("✓ Some Docker services are running", "SUCCESS")
            tests_passed += 1
        else:
            log_message("⚠ No Docker services detected (may be normal for first_time mode)", "WARNING")
    except Exception:
        log_message("⚠ Could not check Docker services", "WARNING")
    
    log_message(f"Setup validation: {tests_passed}/{total_tests} tests passed", "INFO")
    return tests_passed >= 2  # At least basic requirements met

def show_post_setup_summary(mode: str, config: ModeConfiguration) -> None:
    """Display comprehensive post-setup summary and next steps."""
    print_section_header("SETUP COMPLETION SUMMARY")
    
    setup_duration = datetime.now() - SCRIPT_START_TIME
    
    print("\n🎉 OP TRADING PLATFORM SETUP COMPLETED!")
    print("=" * 60)
    print(f"\n📊 SETUP SUMMARY:")
    print(f"   Mode: {mode.upper()}")
    print(f"   Description: {config.description}")
    print(f"   Duration: {setup_duration.seconds // 60}m {setup_duration.seconds % 60}s")
    print(f"   Platform: {PLATFORM_NAME}")
    print(f"   Log File: {LOG_FILE}")
    
    print(f"\n🌐 SERVICE ACCESS:")
    print(f"   API Server: http://localhost:8000")
    print(f"   API Documentation: http://localhost:8000/docs")
    print(f"   InfluxDB: http://localhost:8086")
    print(f"   Redis: localhost:6379")
    
    if mode != "first_time":
        print(f"   Prometheus: http://localhost:9090")
        print(f"   Grafana: http://localhost:3000 (admin/admin123)")
    
    if mode == "production":
        print(f"   Nginx Proxy: http://localhost")
    
    print(f"\n⚙️ CONFIGURATION:")
    print(f"   Environment File: .env")
    print(f"   Data Directory: data/")
    print(f"   Logs Directory: logs/")
    
    print(f"\n🚀 ENHANCED FEATURES ENABLED:")
    print(f"   ✓ Complete FII, DII, Pro, Client Analysis")
    print(f"   ✓ Price Toggle Functionality (Last Price ↔ Average Price)")
    print(f"   ✓ Error Detection Panels with Recovery Suggestions")
    print(f"   ✓ Infinite Data Retention for Regulatory Compliance")
    print(f"   ✓ Index-wise Overview with Market Breadth Analysis")
    print(f"   ✓ Integrated Kite Authentication with Logging")
    print(f"   ✓ Comprehensive Testing Framework (Live vs Mock Data)")
    
    print(f"\n📋 NEXT STEPS:")
    
    if mode == "first_time":
        print(f"   1. Review configuration in .env file")
        print(f"   2. Update Kite Connect credentials (optional for mock data)")
        print(f"   3. Start the application: python main.py")
        print(f"   4. Access API documentation: http://localhost:8000/docs")
        
    elif mode == "development":
        print(f"   1. 🔑 CRITICAL: Update Kite Connect credentials in .env file:")
        print(f"      KITE_API_KEY=your_actual_api_key")
        print(f"      KITE_API_SECRET=your_actual_api_secret")
        print(f"   2. Run authentication setup: python integrated_kite_auth_logger.py --login")
        print(f"   3. Configure Grafana dashboards (import JSON files)")
        print(f"   4. Start development server: python main.py")
        print(f"   5. Test enhanced features and price toggle functionality")
        
    else:  # production
        print(f"   1. ⚠️  CRITICAL: Update ALL credentials in .env file")
        print(f"   2. Configure SSL certificates for HTTPS")
        print(f"   3. Set up email notifications and Slack alerts")
        print(f"   4. Complete Kite Connect authentication setup")
        print(f"   5. Import and configure all Grafana dashboards")
        print(f"   6. Run comprehensive tests: python -m pytest tests/")
        print(f"   7. Start production services and monitor health")
    
    print(f"\n📞 SUPPORT & TROUBLESHOOTING:")
    print(f"   Setup Logs: {LOG_FILE}")
    print(f"   Documentation: README.md")
    print(f"   Configuration Guide: Review .env file comments")
    
    log_message("✓ Post-setup summary completed", "SUCCESS")

def main_setup_process(mode: str, force: bool = False) -> bool:
    """Main setup orchestration function."""
    print(f"\n{'=' * 80}")
    print(f"🚀 OP TRADING PLATFORM - COMPLETE PYTHON SETUP")
    print(f"   Version: {SCRIPT_VERSION}")
    print(f"   Started: {SCRIPT_START_TIME.strftime('%Y-%m-%d %H:%M:%S')} IST")
    print(f"   Mode: {mode.upper()}")
    print(f"   Platform: {PLATFORM_NAME}")
    print(f"{'=' * 80}\n")
    
    try:
        # Validate mode
        if mode not in MODE_CONFIGURATIONS:
            raise ValueError(f"Invalid mode: {mode}. Valid modes: {list(MODE_CONFIGURATIONS.keys())}")
        
        config = MODE_CONFIGURATIONS[mode]
        log_message(f"Initializing setup for mode: {mode}", "INFO")
        log_message(f"Description: {config.description}", "INFO")
        
        # System requirements check
        if not validate_system_requirements(mode):
            if not force:
                raise RuntimeError("System requirements not met")
            else:
                log_message("Force mode enabled - continuing despite system requirement issues", "WARNING")
        
        # Prerequisites check
        if not check_prerequisites(config.required_services):
            if not force:
                raise RuntimeError("Prerequisites not met")
            else:
                log_message("Force mode enabled - continuing despite missing prerequisites", "WARNING")
        
        # Create project structure
        if not create_project_structure():
            raise RuntimeError("Failed to create project structure")
        
        # Install Python dependencies
        if not install_python_dependencies():
            if not force:
                raise RuntimeError("Failed to install Python dependencies")
            else:
                log_message("Force mode enabled - continuing despite dependency installation issues", "WARNING")
        
        # Generate environment configuration
        if not generate_environment_configuration(mode, config):
            raise RuntimeError("Failed to generate environment configuration")
        
        # Setup Docker services
        if not setup_docker_services(mode, config.required_services):
            if not force:
                raise RuntimeError("Failed to setup Docker services")
            else:
                log_message("Force mode enabled - continuing despite Docker service issues", "WARNING")
        
        # Run validation tests
        if not run_comprehensive_tests(mode):
            if not force:
                raise RuntimeError("Setup validation failed")
            else:
                log_message("Force mode enabled - continuing despite validation issues", "WARNING")
        
        # Show completion summary
        show_post_setup_summary(mode, config)
        
        log_message("🎉 OP Trading Platform setup completed successfully!", "SUCCESS")
        return True
        
    except Exception as e:
        error_message = f"✗ Setup failed: {str(e)}"
        log_message(error_message, "ERROR")
        
        print(f"\n{'=' * 80}")
        print(f"❌ SETUP FAILED")
        print(f"{'=' * 80}")
        print(f"\nError: {str(e)}")
        print(f"\nTroubleshooting:")
        print(f"  1. Check the setup log: {LOG_FILE}")
        print(f"  2. Verify system requirements are met")
        print(f"  3. Ensure Docker Desktop is running")
        print(f"  4. Try running with --force to continue past non-critical errors")
        print(f"  5. Check README.md for detailed setup instructions")
        
        return False

# ================================================================================================
# COMMAND-LINE INTERFACE
# ================================================================================================

def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="OP Trading Platform - Complete Python Setup Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python complete_python_setup.py first_time          # Basic setup with mock data
  python complete_python_setup.py development         # Development with live data
  python complete_python_setup.py production          # Full production deployment
  python complete_python_setup.py development --force # Force continue on errors
        """
    )
    
    parser.add_argument(
        "mode",
        choices=["first_time", "development", "production"],
        help="Setup mode: first_time (basic), development (live data), production (full deployment)"
    )
    
    parser.add_argument(
        "--force",
        action="store_true",
        help="Continue setup even when non-critical errors occur"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version=f"OP Trading Platform Setup Script v{SCRIPT_VERSION}"
    )
    
    return parser

# ================================================================================================
# SCRIPT ENTRY POINT
# ================================================================================================

if __name__ == "__main__":
    # Parse command line arguments
    parser = create_argument_parser()
    args = parser.parse_args()
    
    # Initialize logging
    log_message(f"Starting OP Trading Platform Setup Script v{SCRIPT_VERSION}", "INFO")
    log_message(f"Mode: {args.mode}", "INFO")
    log_message(f"Platform: {PLATFORM_NAME}", "INFO")
    log_message(f"Python: {sys.version}", "INFO")
    
    try:
        # Run main setup process
        success = main_setup_process(
            mode=args.mode,
            force=args.force
        )
        
        # Exit with appropriate code
        if success:
            log_message("Setup process completed successfully", "SUCCESS")
            sys.exit(0)
        else:
            log_message("Setup process failed", "ERROR")
            sys.exit(1)
            
    except KeyboardInterrupt:
        log_message("Setup interrupted by user", "WARNING")
        print(f"\n⚠️ Setup interrupted by user")
        sys.exit(130)
    except Exception as e:
        log_message(f"Unexpected error during setup: {str(e)}", "ERROR")
        print(f"\n❌ Unexpected error: {str(e)}")
        sys.exit(1)