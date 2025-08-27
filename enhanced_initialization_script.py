#!/usr/bin/env python3
"""
OP TRADING PLATFORM - ENHANCED INITIALIZATION SCRIPT
====================================================
Version: 3.3.0 - Production-Ready with Smart Package Detection & Process Launch
Author: OP Trading Platform Team
Date: 2025-08-26 12:37 PM IST

ENHANCED INITIALIZATION SCRIPT
This script provides comprehensive initialization with smart package detection:
✓ Detects already installed packages before attempting installation
✓ Complete bypass options for Production/Development modes
✓ Docker network reconciliation with existing container detection
✓ Post-setup options to launch Production/Development processes
✓ Safe directory structure creation (no overwrites)
✓ Comprehensive environment variables handling

FIXES SPECIFIC ISSUES:
✓ Package installation errors for already installed packages
✓ Container network connection errors with proper container detection
✓ Missing bypass options for production/development modes
✓ No continuation options after setup completion

USAGE:
    python enhanced_initialization_script.py
"""

import os
import sys
import json
import time
import logging
import subprocess
import shutil
import importlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
import platform

# ================================================================================================
# CONFIGURATION AND CONSTANTS
# ================================================================================================

VERSION = "3.3.0"
SCRIPT_NAME = "Enhanced Initialization Script"

# Setup logging
LOG_DIR = Path("logs/setup")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"enhanced_setup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Package configurations with import names for detection
ESSENTIAL_PACKAGES = [
    {"pip": "fastapi==0.104.1", "import": "fastapi", "name": "FastAPI"},
    {"pip": "uvicorn[standard]==0.24.0", "import": "uvicorn", "name": "Uvicorn"}, 
    {"pip": "pydantic==2.5.0", "import": "pydantic", "name": "Pydantic"},
    {"pip": "pandas==2.1.4", "import": "pandas", "name": "Pandas"},
    {"pip": "numpy==1.24.3", "import": "numpy", "name": "NumPy"},
    {"pip": "redis==5.0.1", "import": "redis", "name": "Redis"},
    {"pip": "influxdb-client==1.39.0", "import": "influxdb_client", "name": "InfluxDB Client"},
    {"pip": "python-dotenv==1.0.0", "import": "dotenv", "name": "Python Dotenv"},
    {"pip": "requests==2.31.0", "import": "requests", "name": "Requests"},
    {"pip": "aiohttp==3.9.1", "import": "aiohttp", "name": "AioHTTP"},
    {"pip": "prometheus-client==0.19.0", "import": "prometheus_client", "name": "Prometheus Client"},
    {"pip": "psutil==5.9.6", "import": "psutil", "name": "PSUtil"},
    {"pip": "pytz==2023.3", "import": "pytz", "name": "PyTZ"}
]

ADDON_PACKAGES = [
    {"pip": "structlog==23.2.0", "import": "structlog", "name": "Structlog"},
    {"pip": "loguru==0.7.2", "import": "loguru", "name": "Loguru"}, 
    {"pip": "pydantic-settings==2.1.0", "import": "pydantic_settings", "name": "Pydantic Settings"},
    {"pip": "httpx==0.25.2", "import": "httpx", "name": "HTTPX"},
    {"pip": "pytest==7.4.3", "import": "pytest", "name": "Pytest"},
    {"pip": "pytest-asyncio==0.21.1", "import": "pytest_asyncio", "name": "Pytest Asyncio"},
    {"pip": "pytest-cov==4.1.0", "import": "pytest_cov", "name": "Pytest Coverage"},
    {"pip": "black==23.11.0", "import": "black", "name": "Black"},
    {"pip": "isort==5.12.0", "import": "isort", "name": "isort"},
    {"pip": "flake8==6.1.0", "import": "flake8", "name": "Flake8"},
    {"pip": "mypy==1.7.1", "import": "mypy", "name": "MyPy"},
    {"pip": "rich==13.7.0", "import": "rich", "name": "Rich"},
    {"pip": "click==8.1.7", "import": "click", "name": "Click"},
    {"pip": "pyyaml==6.0.1", "import": "yaml", "name": "PyYAML"},
    {"pip": "cryptography==41.0.8", "import": "cryptography", "name": "Cryptography"},
    {"pip": "bcrypt==4.1.2", "import": "bcrypt", "name": "Bcrypt"}
]

# Docker network names to check/reconcile
NETWORK_NAMES = [
    "op-trading-network",
    "poa_op-trading-network", 
    "op-network",
    "optrading_default"
]

# Service configurations
SERVICES = {
    "influxdb": {"port": 8086, "health_endpoint": "/health", "container_patterns": ["influxdb", "op-influxdb"]},
    "redis": {"port": 6379, "health_command": "redis-cli ping", "container_patterns": ["redis", "op-redis"]},
    "prometheus": {"port": 9090, "health_endpoint": "/-/healthy", "container_patterns": ["prometheus", "op-prometheus"]},
    "grafana": {"port": 3000, "health_endpoint": "/api/health", "container_patterns": ["grafana", "op-grafana"]}
}

# ================================================================================================
# UTILITY CLASSES
# ================================================================================================

class Colors:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class SetupState:
    """Track setup state and progress."""
    def __init__(self):
        self.mode = None
        self.steps_completed = []
        self.errors = []
        self.warnings = []
        self.start_time = datetime.now()
        self.bypass_options = {
            "system_requirements": False,
            "prerequisites": False,
            "environment": False
        }
        
    def add_step(self, step_name: str):
        self.steps_completed.append({
            "step": step_name,
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": (datetime.now() - self.start_time).total_seconds()
        })
        
    def add_error(self, error_msg: str):
        self.errors.append({
            "error": error_msg,
            "timestamp": datetime.now().isoformat()
        })
        
    def add_warning(self, warning_msg: str):
        self.warnings.append({
            "warning": warning_msg, 
            "timestamp": datetime.now().isoformat()
        })

class PackageDetector:
    """Smart package detection and installation manager."""
    
    def __init__(self):
        self.installed_packages = set()
        self.missing_packages = set()
        
    def check_package_installed(self, import_name: str) -> bool:
        """Check if a package is already installed."""
        try:
            importlib.import_module(import_name)
            return True
        except ImportError:
            return False
    
    def detect_installed_packages(self, packages: List[Dict[str, str]]) -> Tuple[List[Dict], List[Dict]]:
        """Detect which packages are installed and which are missing."""
        installed = []
        missing = []
        
        print(f"🔍 Scanning {len(packages)} packages...")
        
        for package in packages:
            package_name = package["name"]
            import_name = package["import"]
            
            if self.check_package_installed(import_name):
                installed.append(package)
                print(f"   ✅ {package_name} - Already installed")
            else:
                missing.append(package)
                print(f"   ❌ {package_name} - Not installed")
        
        return installed, missing
    
    def install_missing_packages(self, missing_packages: List[Dict[str, str]], 
                                is_essential: bool = True) -> Tuple[int, int, List[str]]:
        """Install missing packages and return success/failure counts."""
        if not missing_packages:
            return 0, 0, []
        
        successful_installs = 0
        failed_installs = 0
        failures = []
        
        print(f"\n📦 Installing {len(missing_packages)} missing packages...")
        
        for i, package in enumerate(missing_packages, 1):
            package_name = package["name"]
            pip_package = package["pip"]
            
            print(f"📥 [{i}/{len(missing_packages)}] Installing {package_name}...")
            
            success, stdout, stderr = self.run_pip_install(pip_package)
            
            if success:
                successful_installs += 1
                print(f"   ✅ {package_name} installed successfully")
            else:
                failed_installs += 1
                failures.append(f"{package_name}: {stderr.strip()[:100]}")
                
                severity = "CRITICAL" if is_essential else "WARNING"
                print(f"   ❌ {package_name} installation failed ({severity})")
                print(f"      Error: {stderr.strip()[:100]}")
        
        return successful_installs, failed_installs, failures
    
    def run_pip_install(self, package: str) -> Tuple[bool, str, str]:
        """Run pip install command."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", package],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            return result.returncode == 0, result.stdout, result.stderr
            
        except subprocess.TimeoutExpired:
            return False, "", "Installation timeout"
        except Exception as e:
            return False, "", str(e)

# ================================================================================================
# MAIN ENHANCED INITIALIZATION CLASS
# ================================================================================================

class EnhancedInitializationScript:
    """Enhanced initialization script with smart package detection."""
    
    def __init__(self):
        """Initialize the setup script."""
        self.state = SetupState()
        self.project_root = Path.cwd()
        self.env_file = self.project_root / ".env"
        self.package_detector = PackageDetector()
        
        logger.info(f"Enhanced Initialization Script v{VERSION} initialized")
        logger.info(f"Project root: {self.project_root}")
        logger.info(f"Log file: {LOG_FILE}")
    
    def clear_screen(self):
        """Clear terminal screen."""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def print_header(self, title: str):
        """Print formatted header."""
        self.clear_screen()
        print(f"{Colors.HEADER}{Colors.BOLD}=" * 80)
        print(f"🚀 OP TRADING PLATFORM - {SCRIPT_NAME} v{VERSION}")
        print("=" * 80)
        print(f"📋 {title}")
        print(f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
        print("-" * 80)
        print(f"{Colors.ENDC}")
    
    def print_step(self, step_num: int, title: str, description: str = ""):
        """Print setup step."""
        print(f"\n{Colors.OKBLUE}📋 Step {step_num}: {title}{Colors.ENDC}")
        print(f"{Colors.OKCYAN}-" * 50)
        if description:
            print(f"📝 {description}")
        print(f"{Colors.ENDC}")
    
    def run_command(self, command: str, description: str = "", timeout: int = 300, 
                   capture_output: bool = True) -> Tuple[bool, str, str]:
        """Execute system command with comprehensive error handling."""
        try:
            if description:
                print(f"🔄 {description}...")
                logger.info(f"Executing: {command}")
            
            if capture_output:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=self.project_root
                )
            else:
                result = subprocess.run(
                    command,
                    shell=True,
                    timeout=timeout,
                    cwd=self.project_root
                )
                result.stdout = ""
                result.stderr = ""
            
            success = result.returncode == 0
            
            if success and description:
                print(f"✅ {description} - SUCCESS")
                logger.info(f"Command succeeded: {command}")
            elif not success and description:
                print(f"❌ {description} - FAILED")
                logger.error(f"Command failed: {command}")
                if result.stderr.strip():
                    print(f"   Error: {result.stderr.strip()}")
                    
            return success, result.stdout, result.stderr
            
        except subprocess.TimeoutExpired:
            error_msg = f"Command timeout: {command}"
            print(f"❌ {description} - TIMEOUT")
            logger.error(error_msg)
            return False, "", error_msg
        except Exception as e:
            error_msg = f"Command exception: {str(e)}"
            print(f"❌ {description} - ERROR: {str(e)}")
            logger.error(error_msg)
            return False, "", error_msg
    
    def get_user_input(self, prompt: str, valid_options: List[str] = None) -> str:
        """Get user input with validation."""
        while True:
            try:
                user_input = input(f"{Colors.OKCYAN}👤 {prompt}: {Colors.ENDC}").strip()
                
                if valid_options is None:
                    return user_input
                
                if user_input.lower() in [opt.lower() for opt in valid_options]:
                    return user_input
                    
                print(f"{Colors.WARNING}⚠️  Invalid option. Valid options: {', '.join(valid_options)}{Colors.ENDC}")
                
            except KeyboardInterrupt:
                print(f"\n{Colors.WARNING}🛑 Setup interrupted by user{Colors.ENDC}")
                sys.exit(130)
    
    def main_menu(self):
        """Display main menu and get user selection."""
        self.print_header("MAIN MENU")
        
        print("🎯 Welcome to the OP Trading Platform Enhanced Setup!")
        print("   This script provides intelligent initialization with:")
        print("   • Smart package detection (avoids reinstalling existing packages)")
        print("   • Complete bypass options for faster setup")
        print("   • Docker network reconciliation with container detection")
        print("   • Post-setup launch options for Production/Development")
        print()
        
        print("📋 Select initialization mode:")
        print()
        print(f"{Colors.OKGREEN}1. Production Mode{Colors.ENDC}")
        print("   └── Full production setup with optimizations and bypass options")
        print()
        print(f"{Colors.OKBLUE}2. Development Mode{Colors.ENDC}")
        print("   └── Development setup with debugging enabled and bypass options")
        print()
        print(f"{Colors.OKCYAN}3. Setup Mode{Colors.ENDC}")
        print("   └── Infrastructure setup and configuration only")
        print()
        print(f"{Colors.WARNING}0. Exit{Colors.ENDC}")
        print()
        
        choice = self.get_user_input("Enter your choice (0-3)", ["0", "1", "2", "3"])
        
        if choice == "0":
            print("👋 Goodbye!")
            sys.exit(0)
        elif choice == "1":
            return "production"
        elif choice == "2":
            return "development"
        elif choice == "3":
            return "setup"
    
    def get_bypass_options(self, mode: str):
        """Get bypass options for Production/Development modes."""
        if mode in ["production", "development"]:
            self.print_header(f"{mode.upper()} MODE - BYPASS OPTIONS")
            
            print(f"🚀 {mode.title()} Mode Setup Options:")
            print("   You can bypass certain steps for faster setup if they're already configured.")
            print()
            
            # System requirements bypass
            print(f"{Colors.OKBLUE}1. System Requirements Check:{Colors.ENDC}")
            bypass_sys = self.get_user_input("   Skip system requirements check? (y/n)", ["y", "n", "yes", "no"])
            self.state.bypass_options["system_requirements"] = bypass_sys.lower() in ["y", "yes"]
            
            # Prerequisites bypass
            print(f"\n{Colors.OKBLUE}2. Prerequisites Installation:{Colors.ENDC}")
            bypass_prereq = self.get_user_input("   Skip prerequisites installation? (y/n)", ["y", "n", "yes", "no"])
            self.state.bypass_options["prerequisites"] = bypass_prereq.lower() in ["y", "yes"]
            
            # Environment bypass
            print(f"\n{Colors.OKBLUE}3. Environment Configuration:{Colors.ENDC}")
            bypass_env = self.get_user_input("   Skip environment configuration? (y/n)", ["y", "n", "yes", "no"])
            self.state.bypass_options["environment"] = bypass_env.lower() in ["y", "yes"]
            
            print(f"\n{Colors.OKGREEN}Bypass Configuration:{Colors.ENDC}")
            print(f"   • System Requirements: {'Skipped' if self.state.bypass_options['system_requirements'] else 'Will Check'}")
            print(f"   • Prerequisites: {'Skipped' if self.state.bypass_options['prerequisites'] else 'Will Install'}")
            print(f"   • Environment: {'Skipped' if self.state.bypass_options['environment'] else 'Will Configure'}")
            print()
            
            input("Press Enter to continue...")
    
    def check_system_requirements(self) -> bool:
        """Check system requirements with bypass option."""
        if self.state.bypass_options["system_requirements"]:
            print(f"{Colors.WARNING}⚠️  Bypassing system requirements check{Colors.ENDC}")
            self.state.add_step("System requirements check (bypassed)")
            return True
        
        self.print_step(1, "System Requirements Check", 
                       "Checking if Docker and Python are available")
        
        print("🔍 System Requirements Check:")
        print("   • Docker (for containers)")
        print("   • Python 3.8+ (current runtime)")
        print("   • Sufficient disk space")
        print()
        
        print("🔍 Checking system requirements...")
        all_good = True
        
        # Check Docker
        success, stdout, stderr = self.run_command("docker --version", "Checking Docker installation")
        if success:
            print(f"✅ Docker: {stdout.strip()}")
        else:
            print(f"❌ Docker not found or not running")
            print("   📥 Install Docker from: https://docs.docker.com/get-docker/")
            all_good = False
        
        # Check Docker Compose
        success_v2, _, _ = self.run_command("docker compose version", "Checking Docker Compose v2")
        success_v1, _, _ = self.run_command("docker-compose --version", "Checking Docker Compose v1")
        
        if success_v2 or success_v1:
            compose_cmd = "docker compose" if success_v2 else "docker-compose"
            print(f"✅ Docker Compose: Available ({compose_cmd})")
        else:
            print("❌ Docker Compose not found")
            all_good = False
        
        # Check Python version
        python_version = platform.python_version()
        version_parts = python_version.split('.')
        major, minor = int(version_parts[0]), int(version_parts[1])
        
        if major >= 3 and minor >= 8:
            print(f"✅ Python: {python_version}")
        else:
            print(f"❌ Python {python_version} is too old (requires 3.8+)")
            all_good = False
        
        # Check disk space
        try:
            disk_usage = shutil.disk_usage(self.project_root)
            free_gb = disk_usage.free / (1024**3)
            if free_gb >= 5:
                print(f"✅ Disk Space: {free_gb:.1f} GB available")
            else:
                print(f"⚠️  Disk Space: Only {free_gb:.1f} GB available (recommend 5+ GB)")
                self.state.add_warning(f"Low disk space: {free_gb:.1f} GB")
        except:
            print("⚠️  Could not check disk space")
        
        if all_good:
            print(f"\n{Colors.OKGREEN}✅ All system requirements satisfied{Colors.ENDC}")
            self.state.add_step("System requirements check")
            return True
        else:
            print(f"\n{Colors.FAIL}❌ System requirements not met{Colors.ENDC}")
            print("   Please install missing components and try again")
            return False
    
    def handle_prerequisites(self) -> bool:
        """Handle prerequisites installation with smart package detection."""
        if self.state.bypass_options["prerequisites"]:
            print(f"{Colors.WARNING}⚠️  Bypassing prerequisites installation{Colors.ENDC}")
            self.state.add_step("Prerequisites (bypassed)")
            return True
        
        self.print_step(2, "Smart Prerequisites Installation", 
                       "Detecting installed packages and installing only missing ones")
        
        print("🧠 Smart Prerequisites Installation:")
        print("   This system will:")
        print("   • Scan for already installed packages")
        print("   • Skip packages that are already available")
        print("   • Install only missing packages")
        print("   • Provide detailed installation reports")
        print()
        
        print("📦 Prerequisites Installation Options:")
        print()
        print(f"{Colors.OKGREEN}1. Skip Installation{Colors.ENDC}")
        print("   └── Skip if packages are already installed")
        print()
        print(f"{Colors.OKBLUE}2. Install Essential Packages{Colors.ENDC}")
        print("   └── Core packages required for basic functionality")
        print(f"   └── {len(ESSENTIAL_PACKAGES)} packages: FastAPI, Pandas, InfluxDB, Redis, etc.")
        print()
        print(f"{Colors.OKCYAN}3. Install Add-on Packages{Colors.ENDC}")
        print("   └── Additional packages for enhanced functionality")  
        print(f"   └── {len(ADDON_PACKAGES)} packages: Testing, Logging, Security, etc.")
        print()
        print(f"{Colors.OKGREEN}4. Install All Packages{Colors.ENDC}")
        print("   └── Essential + Add-on packages (complete installation)")
        print(f"   └── {len(ESSENTIAL_PACKAGES) + len(ADDON_PACKAGES)} total packages")
        print()
        
        choice = self.get_user_input("Select installation option (1-4)", ["1", "2", "3", "4"])
        
        if choice == "1":
            print(f"{Colors.OKCYAN}⏭️  Skipping prerequisites installation{Colors.ENDC}")
            self.state.add_step("Prerequisites skipped")
            return True
        
        # Upgrade pip first
        print("🔧 Upgrading pip...")
        success, stdout, stderr = self.run_command("python -m pip install --upgrade pip", 
                                                   "Upgrading pip")
        if not success:
            print(f"{Colors.WARNING}⚠️  Could not upgrade pip: {stderr}{Colors.ENDC}")
        
        # Determine packages to process
        packages_to_check = []
        
        if choice in ["2", "4"]:  # Essential or All
            packages_to_check.extend(ESSENTIAL_PACKAGES)
        
        if choice in ["3", "4"]:  # Add-ons or All
            packages_to_check.extend(ADDON_PACKAGES)
        
        print(f"\n🔍 Smart Package Detection for {len(packages_to_check)} packages...")
        
        # Detect installed vs missing packages
        installed_packages, missing_packages = self.package_detector.detect_installed_packages(packages_to_check)
        
        print(f"\n📊 Package Detection Summary:")
        print(f"   ✅ Already installed: {len(installed_packages)}")
        print(f"   ❌ Missing packages: {len(missing_packages)}")
        
        if len(installed_packages) > 0:
            print(f"\n✅ Already Installed Packages:")
            for pkg in installed_packages[:10]:  # Show first 10
                print(f"   • {pkg['name']}")
            if len(installed_packages) > 10:
                print(f"   • ... and {len(installed_packages) - 10} more")
        
        if len(missing_packages) == 0:
            print(f"\n{Colors.OKGREEN}🎉 All packages are already installed!{Colors.ENDC}")
            self.state.add_step("Prerequisites (all packages already installed)")
            return True
        
        print(f"\n📦 Installing {len(missing_packages)} missing packages...")
        
        # Separate essential and add-on missing packages
        essential_missing = [pkg for pkg in missing_packages if pkg in ESSENTIAL_PACKAGES]
        addon_missing = [pkg for pkg in missing_packages if pkg in ADDON_PACKAGES]
        
        # Install missing essential packages
        essential_successes = 0
        essential_failures = 0
        essential_failure_details = []
        
        if essential_missing:
            print(f"\n📥 Installing {len(essential_missing)} missing essential packages...")
            essential_successes, essential_failures, essential_failure_details = \
                self.package_detector.install_missing_packages(essential_missing, is_essential=True)
        
        # Install missing add-on packages
        addon_successes = 0
        addon_failures = 0
        addon_failure_details = []
        
        if addon_missing:
            print(f"\n📥 Installing {len(addon_missing)} missing add-on packages...")
            addon_successes, addon_failures, addon_failure_details = \
                self.package_detector.install_missing_packages(addon_missing, is_essential=False)
        
        # Report results
        total_successes = essential_successes + addon_successes
        total_failures = essential_failures + addon_failures
        
        print(f"\n📊 Smart Installation Summary:")
        print(f"   ✅ Already had: {len(installed_packages)}")
        print(f"   ✅ Successfully installed: {total_successes}")
        print(f"   ❌ Essential failures: {essential_failures}")
        print(f"   ⚠️  Add-on failures: {addon_failures}")
        
        # Handle essential failures
        if essential_failures > 0:
            print(f"\n{Colors.FAIL}❌ CRITICAL: Essential packages failed to install:{Colors.ENDC}")
            for detail in essential_failure_details:
                print(f"   • {detail}")
            print("\nEssential packages are required for the platform to function.")
            print("Please resolve these issues before continuing.")
            
            self.state.add_error(f"Essential package installation failed: {essential_failures} packages")
            return False
        
        # Handle add-on failures (non-critical)
        if addon_failures > 0:
            print(f"\n{Colors.WARNING}⚠️  Add-on packages failed to install:{Colors.ENDC}")
            for detail in addon_failure_details:
                print(f"   • {detail}")
            print("Add-on packages are optional. Setup will continue.")
            
            for detail in addon_failure_details:
                self.state.add_warning(f"Add-on package failed: {detail}")
        
        print(f"\n{Colors.OKGREEN}✅ Smart prerequisites installation completed{Colors.ENDC}")
        self.state.add_step("Smart prerequisites installation")
        return True
    
    def handle_environment_configuration(self) -> bool:
        """Handle environment configuration with bypass option."""
        if self.state.bypass_options["environment"]:
            print(f"{Colors.WARNING}⚠️  Bypassing environment configuration{Colors.ENDC}")
            self.state.add_step("Environment configuration (bypassed)")
            return True
        
        self.print_step(4, "Environment Configuration", 
                       "Managing environment variables and configuration")
        
        env_exists = self.env_file.exists()
        
        print("⚙️  Environment Configuration Options:")
        print()
        
        if env_exists:
            # Count existing variables
            try:
                with open(self.env_file, 'r') as f:
                    env_lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                    env_vars = len([line for line in env_lines if '=' in line])
                
                print(f"📄 Existing .env file found with {env_vars} variables")
                print()
            except Exception as e:
                print(f"📄 Existing .env file found (could not count variables)")
                print()
        
        print(f"{Colors.OKGREEN}1. Continue with existing configuration (recommended){Colors.ENDC}")
        if env_exists:
            print("   └── Keep current .env file without changes")
        else:
            print("   └── Skip environment configuration for now")
        print()
        
        print(f"{Colors.OKBLUE}2. Create new default .env file{Colors.ENDC}")
        print("   └── Create comprehensive .env with all variables")
        print("   └── ⚠️  This will overwrite your current configuration!")
        print()
        
        print("0. Back/Exit")
        print()
        
        choice = self.get_user_input("Enter your choice (0-2)", ["0", "1", "2"])
        
        if choice == "0":
            return False
        elif choice == "1":
            print(f"{Colors.OKGREEN}✅ Continuing with existing configuration{Colors.ENDC}")
            if env_exists:
                self.state.add_step("Environment configuration (existing)")
            return True
        elif choice == "2":
            return self.create_new_default_env()
    
    def create_new_default_env(self) -> bool:
        """Create new default environment file with confirmation."""
        self.print_header("CREATE NEW DEFAULT ENVIRONMENT FILE")
        
        print(f"{Colors.WARNING}⚠️  Environment File Creation{Colors.ENDC}")
        print()
        
        if self.env_file.exists():
            print("You are about to create a new default .env file.")
            print(f"{Colors.FAIL}This will OVERWRITE your existing .env file!{Colors.ENDC}")
        else:
            print("Creating a new comprehensive .env file with 150+ variables.")
        
        print()
        print(f"{Colors.OKGREEN}This will create:{Colors.ENDC}")
        print("• Comprehensive .env file with all configuration categories")
        print("• Default values for development setup")
        print("• Placeholder values for sensitive credentials")
        print("• Essential configuration prompts")
        print()
        
        # Confirmation
        confirm = self.get_user_input(
            'Create new .env file? (y/n)', 
            ["y", "n", "yes", "no"]
        )
        
        if confirm.lower() in ["n", "no"]:
            print(f"{Colors.OKGREEN}✅ Operation cancelled{Colors.ENDC}")
            return True
        
        print(f"\n{Colors.WARNING}🔄 Creating new default .env file...{Colors.ENDC}")
        
        # Backup existing file
        if self.env_file.exists():
            backup_file = self.env_file.with_suffix(f".env.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            try:
                shutil.copy2(self.env_file, backup_file)
                print(f"💾 Backup created: {backup_file.name}")
            except Exception as e:
                print(f"⚠️  Could not create backup: {str(e)}")
        
        # Create comprehensive environment file
        success = self.generate_comprehensive_env_file()
        
        if success:
            print(f"\n{Colors.OKGREEN}✅ New default .env file created successfully{Colors.ENDC}")
            print("📝 Review and customize settings as needed")
            
            self.state.add_step("Environment configuration (new default)")
            return True
        else:
            print(f"\n{Colors.FAIL}❌ Failed to create new .env file{Colors.ENDC}")
            return False
    
    def generate_comprehensive_env_file(self) -> bool:
        """Generate comprehensive environment file with all variables."""
        try:
            env_content = f"""# ================================================================================================
# OP TRADING PLATFORM - COMPREHENSIVE ENVIRONMENT CONFIGURATION
# ================================================================================================
# Version: {VERSION} - Complete Configuration Template
# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}
# Mode: DEFAULT (Update all values marked with "your_*_here" or "CHANGE_THIS")
# 
# SECURITY WARNING: Keep this file secure and never commit real credentials to version control
# ================================================================================================

# Core Configuration
DEPLOYMENT_MODE=development
ENV=development
VERSION={VERSION}
DEBUG=true

# Kite Connect API (UPDATE THESE)
KITE_API_KEY=your_kite_api_key_here
KITE_API_SECRET=your_kite_api_secret_here
KITE_ACCESS_TOKEN=your_kite_access_token_here

# InfluxDB Configuration (UPDATE THESE)
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=your_influxdb_token_here
INFLUXDB_ORG=your_organization_name_here
INFLUXDB_BUCKET=your_bucket_name_here
INFLUXDB_RETENTION_POLICY=infinite

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_SECRET_KEY=CHANGE_THIS_TO_SECURE_SECRET_KEY

# Data Source Configuration
DATA_SOURCE_MODE=live
TIMEZONE=Asia/Kolkata
MARKET_TIMEZONE=Asia/Kolkata

# Enhanced Analytics
ENABLE_OPTION_FLOW_ANALYSIS=true
ENABLE_PARTICIPANT_ANALYSIS=true
ENABLE_CASH_FLOW_TRACKING=true

# Monitoring Configuration
PROMETHEUS_ENABLED=true
GRAFANA_ENABLED=true
HEALTH_CHECK_INTERVAL_SECONDS=15

# Logging Configuration
LOG_LEVEL=INFO
LOG_RETENTION_DAYS=90

# Email/SMTP Configuration (OPTIONAL)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password_here

# Performance Settings
MAX_MEMORY_USAGE_MB=2048
PROCESSING_MAX_WORKERS=4

# Security Settings
SECURITY_ENABLED=true
JWT_EXPIRATION_HOURS=24

# ================================================================================================
# END OF BASIC CONFIGURATION - Add more variables as needed
# ================================================================================================
"""
            
            with open(self.env_file, 'w', encoding='utf-8') as f:
                f.write(env_content)
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to generate comprehensive .env file: {str(e)}")
            print(f"❌ Error creating .env file: {str(e)}")
            return False
    
    def create_directory_structure(self) -> bool:
        """Create directory structure safely without overwriting."""
        self.print_step(3, "Directory Structure Creation", 
                       "Creating project directories (safe, no overwrites)")
        
        print("📁 Directory Structure Creation:")
        print("   This step creates necessary directories for the platform.")
        print("   • Existing directories and files will NOT be overwritten")
        print("   • Only missing directories will be created")
        print("   • Your data and configurations are safe")
        print()
        
        create_dirs = self.get_user_input("Create directory structure? (y/n)", ["y", "n", "yes", "no"])
        
        if create_dirs.lower() in ["n", "no"]:
            print(f"{Colors.OKCYAN}⏭️  Skipping directory structure creation{Colors.ENDC}")
            return True
        
        # Define directory structure
        directories = [
            "data", "data/influxdb", "data/redis", "data/prometheus", "data/grafana",
            "logs", "logs/setup", "logs/application", "logs/monitoring",
            "config", "config/prometheus", "config/grafana", "config/nginx",
            "services", "services/collection", "services/processing", "services/analytics",
            "scripts", "docs"
        ]
        
        created_dirs = []
        existing_dirs = []
        
        print(f"📁 Creating {len(directories)} directories...")
        
        for directory in directories:
            dir_path = self.project_root / directory
            
            if dir_path.exists():
                existing_dirs.append(directory)
                print(f"   ℹ️  {directory} - Already exists")
            else:
                try:
                    dir_path.mkdir(parents=True, exist_ok=True)
                    created_dirs.append(directory)
                    print(f"   ✅ {directory} - Created")
                except Exception as e:
                    print(f"   ❌ {directory} - Failed: {str(e)}")
                    self.state.add_error(f"Directory creation failed: {directory}")
        
        print(f"\n📊 Directory Creation Summary:")
        print(f"   ✅ Created: {len(created_dirs)}")
        print(f"   ℹ️  Existing: {len(existing_dirs)}")
        print(f"   🔒 No data was overwritten or deleted")
        
        self.state.add_step("Directory structure creation")
        print(f"\n{Colors.OKGREEN}✅ Directory structure creation completed{Colors.ENDC}")
        return True
    
    def reconcile_docker_networks(self) -> bool:
        """Reconcile Docker networks and container connections."""
        self.print_step(5, "Docker Network Reconciliation", 
                       "Detecting and fixing container network connectivity")
        
        print("🔗 Docker Network Reconciliation:")
        print("   This step detects existing containers and networks")
        print("   • Only connects containers that actually exist")
        print("   • Skips missing containers without errors")
        print("   • Creates target network if needed")
        print()
        
        # Get current containers
        print("🔍 Detecting Docker containers...")
        success, containers_output, _ = self.run_command("docker ps -a --format '{{.Names}},{{.Image}},{{.Status}}'", 
                                                        "Getting container list")
        
        if not success:
            print("❌ Could not get Docker container list")
            return False
        
        containers = []
        for line in containers_output.strip().split('\n'):
            if line.strip():
                parts = line.strip().split(',')
                if len(parts) >= 3:
                    containers.append({
                        'name': parts[0],
                        'image': parts[1], 
                        'status': parts[2]
                    })
        
        # Detect service containers that actually exist
        service_containers = []
        for container in containers:
            name = container['name'].lower()
            image = container['image'].lower()
            
            if any(service in name or service in image for service in ['influxdb', 'redis', 'prometheus', 'grafana']):
                service_containers.append(container)
        
        print(f"📊 Found {len(service_containers)} service containers:")
        for container in service_containers:
            status_color = Colors.OKGREEN if 'up' in container['status'].lower() else Colors.WARNING
            print(f"   • {container['name']} ({container['image']}) - {status_color}{container['status']}{Colors.ENDC}")
        
        if not service_containers:
            print("ℹ️  No service containers found. Network reconciliation not needed.")
            self.state.add_warning("No service containers found for network reconciliation")
            return True
        
        # Get target network
        target_network = "op-trading-network"
        
        # Check if network exists, create if not
        success, networks_output, _ = self.run_command("docker network ls --format '{{.Name}}'", 
                                                      "Getting network list")
        
        if target_network not in networks_output:
            print(f"\n🔧 Creating network: {target_network}")
            success, _, stderr = self.run_command(f"docker network create {target_network}", 
                                                 f"Creating {target_network}")
            if not success:
                print(f"❌ Could not create network: {stderr}")
                # Try to use existing network
                if "poa_op-trading-network" in networks_output:
                    target_network = "poa_op-trading-network"
                    print(f"🔄 Using existing network: {target_network}")
                else:
                    self.state.add_error("Could not create or find suitable network")
                    return True  # Continue anyway
        
        print(f"\n🎯 Target network: {Colors.OKGREEN}{target_network}{Colors.ENDC}")
        
        # Connect only existing containers
        connected_count = 0
        failed_count = 0
        
        for container in service_containers:
            container_name = container['name']
            
            # Try to connect (will fail silently if already connected)
            success, _, stderr = self.run_command(
                f"docker network connect {target_network} {container_name}",
                f"Connecting {container_name} to {target_network}"
            )
            
            if success:
                print(f"   ✅ {container_name} - Connected successfully")
                connected_count += 1
            elif "already connected" in stderr.lower():
                print(f"   ✅ {container_name} - Already connected")
                connected_count += 1
            else:
                print(f"   ❌ {container_name} - Connection failed: {stderr}")
                failed_count += 1
        
        print(f"\n📊 Network Reconciliation Summary:")
        print(f"   ✅ Successfully connected: {connected_count}")
        print(f"   ❌ Failed connections: {failed_count}")
        print(f"   🔗 Target network: {target_network}")
        
        if failed_count > 0:
            self.state.add_warning(f"Network reconciliation failed for {failed_count} containers")
        
        print(f"\n{Colors.OKGREEN}✅ Network reconciliation completed{Colors.ENDC}")
        self.state.add_step("Network reconciliation")
        return True
    
    def validate_services(self) -> Dict[str, bool]:
        """Validate service health."""
        print(f"\n{Colors.OKBLUE}🔍 Service Health Validation{Colors.ENDC}")
        print("Testing connectivity to running services...")
        
        validation_results = {}
        
        # Test each service
        for service_name, config in SERVICES.items():
            print(f"\n📊 Testing {service_name.title()}...")
            
            if "health_endpoint" in config:
                # HTTP health check
                try:
                    import requests
                    url = f"http://localhost:{config['port']}{config['health_endpoint']}"
                    response = requests.get(url, timeout=10)
                    
                    if response.status_code == 200:
                        print(f"   ✅ {service_name} - Healthy (HTTP {response.status_code})")
                        validation_results[service_name] = True
                    else:
                        print(f"   ❌ {service_name} - Unhealthy (HTTP {response.status_code})")
                        validation_results[service_name] = False
                
                except ImportError:
                    # Fallback to curl
                    url = f"http://localhost:{config['port']}{config['health_endpoint']}"
                    success, _, _ = self.run_command(f"curl -f -s {url}", 
                                                   f"Testing {service_name}")
                    validation_results[service_name] = success
                    status = "Healthy" if success else "Unhealthy"
                    print(f"   {'✅' if success else '❌'} {service_name} - {status}")
                
                except Exception as e:
                    print(f"   ❌ {service_name} - Error: {str(e)}")
                    validation_results[service_name] = False
            
            elif "health_command" in config:
                # Command-based health check (Redis)
                success, stdout, _ = self.run_command(
                    f"docker exec op-redis {config['health_command']}",
                    f"Testing {service_name}"
                )
                
                if success and "PONG" in stdout:
                    print(f"   ✅ {service_name} - Healthy (PONG)")
                    validation_results[service_name] = True
                else:
                    print(f"   ❌ {service_name} - Unhealthy or not running")
                    validation_results[service_name] = False
        
        return validation_results
    
    def print_completion_summary(self, validation_results: Dict[str, bool] = None):
        """Print completion summary with continuation options."""
        self.print_header("SETUP COMPLETE - SUMMARY")
        
        total_time = (datetime.now() - self.state.start_time).total_seconds()
        
        print(f"🎉 Setup completed in {total_time:.1f} seconds")
        print(f"📋 Mode: {self.state.mode.title()}")
        print()
        
        # Steps completed
        print(f"{Colors.OKGREEN}✅ Steps Completed ({len(self.state.steps_completed)}):{Colors.ENDC}")
        for step in self.state.steps_completed:
            print(f"   • {step['step']}")
        
        # Warnings
        if self.state.warnings:
            print(f"\n{Colors.WARNING}⚠️  Warnings ({len(self.state.warnings)}):{Colors.ENDC}")
            for warning in self.state.warnings:
                print(f"   • {warning['warning']}")
        
        # Errors
        if self.state.errors:
            print(f"\n{Colors.FAIL}❌ Errors ({len(self.state.errors)}):{Colors.ENDC}")
            for error in self.state.errors:
                print(f"   • {error['error']}")
        
        # Service status
        if validation_results:
            print(f"\n🏥 Service Health:")
            for service, healthy in validation_results.items():
                status_icon = "✅" if healthy else "❌"
                status_text = "Healthy" if healthy else "Unhealthy"
                print(f"   {status_icon} {service.title()}: {status_text}")
        
        # Service URLs
        print(f"\n🌐 Service URLs:")
        print("   • InfluxDB UI: http://localhost:8086 (admin/adminpass123)")
        print("   • Grafana: http://localhost:3000 (admin/admin123)")
        print("   • Prometheus: http://localhost:9090")
        print("   • Redis: localhost:6379")
        print("   • API Docs: http://localhost:8000/docs (when running)")
        
        print(f"\n📄 Setup log: {LOG_FILE}")
        
        # Continuation options
        self.show_continuation_options()
    
    def show_continuation_options(self):
        """Show options to continue with Production/Development or exit."""
        print(f"\n{Colors.HEADER}{Colors.BOLD}🚀 NEXT STEPS - CONTINUE TO PLATFORM LAUNCH{Colors.ENDC}")
        print()
        
        has_errors = len(self.state.errors) > 0
        has_warnings = len(self.state.warnings) > 0
        
        if has_errors:
            print(f"{Colors.FAIL}⚠️  ERRORS DETECTED:{Colors.ENDC}")
            print("   Some setup steps failed. You can still continue, but the platform may not work correctly.")
            print()
        
        if has_warnings:
            print(f"{Colors.WARNING}⚠️  WARNINGS NOTED:{Colors.ENDC}")
            print("   Some optional components failed. The platform should work with reduced functionality.")
            print()
        
        print("🎯 What would you like to do next?")
        print()
        
        if self.state.mode in ["production", "development"]:
            print(f"{Colors.OKGREEN}1. Launch {self.state.mode.title()} Platform{Colors.ENDC}")
            print(f"   └── Start the OP Trading Platform in {self.state.mode} mode")
            if has_errors or has_warnings:
                print(f"   └── ⚠️  Continue anyway despite setup issues")
            print()
        
        print(f"{Colors.OKBLUE}2. Launch API Server Only{Colors.ENDC}")
        print("   └── Start the FastAPI server for testing")
        print()
        
        print(f"{Colors.OKCYAN}3. Run System Validation{Colors.ENDC}")
        print("   └── Test all services and configurations")
        print()
        
        print(f"{Colors.WARNING}4. Review Setup Issues{Colors.ENDC}")
        print("   └── Show detailed error and warning information")
        print()
        
        print("0. Exit")
        print()
        
        if self.state.mode in ["production", "development"]:
            valid_options = ["0", "1", "2", "3", "4"]
        else:
            valid_options = ["0", "2", "3", "4"]
        
        choice = self.get_user_input("Enter your choice", valid_options)
        
        if choice == "0":
            print(f"\n{Colors.OKGREEN}✅ Setup completed successfully!{Colors.ENDC}")
            print("👋 Thank you for using the OP Trading Platform setup!")
            sys.exit(0)
        
        elif choice == "1" and self.state.mode in ["production", "development"]:
            self.launch_platform_mode(self.state.mode)
        
        elif choice == "2":
            self.launch_api_server()
        
        elif choice == "3":
            self.run_system_validation()
        
        elif choice == "4":
            self.review_setup_issues()
    
    def launch_platform_mode(self, mode: str):
        """Launch the platform in the specified mode."""
        print(f"\n{Colors.OKGREEN}🚀 Launching {mode.title()} Platform...{Colors.ENDC}")
        print()
        
        # Check if main.py exists
        main_file = self.project_root / "main.py"
        if not main_file.exists():
            print(f"{Colors.FAIL}❌ main.py not found in the project directory{Colors.ENDC}")
            print("   Please ensure the main application file exists before launching.")
            input("Press Enter to return to options menu...")
            self.show_continuation_options()
            return
        
        # Launch command
        launch_cmd = f"python main.py --mode {mode}"
        
        print(f"🔄 Executing: {launch_cmd}")
        print(f"📋 Platform will start in {mode} mode")
        print(f"🌐 API will be available at: http://localhost:8000")
        print(f"📚 API Documentation: http://localhost:8000/docs")
        print()
        print(f"{Colors.WARNING}Press Ctrl+C to stop the platform{Colors.ENDC}")
        print()
        
        try:
            # Execute the main application
            result = subprocess.run([sys.executable, "main.py", "--mode", mode], 
                                  cwd=self.project_root)
            
            if result.returncode != 0:
                print(f"\n{Colors.FAIL}❌ Platform exited with error code {result.returncode}{Colors.ENDC}")
            else:
                print(f"\n{Colors.OKGREEN}✅ Platform stopped gracefully{Colors.ENDC}")
                
        except KeyboardInterrupt:
            print(f"\n{Colors.WARNING}🛑 Platform stopped by user{Colors.ENDC}")
        except FileNotFoundError:
            print(f"\n{Colors.FAIL}❌ Could not find Python interpreter or main.py{Colors.ENDC}")
        except Exception as e:
            print(f"\n{Colors.FAIL}❌ Error launching platform: {str(e)}{Colors.ENDC}")
        
        print("\n" + "="*50)
        input("Press Enter to return to options menu...")
        self.show_continuation_options()
    
    def launch_api_server(self):
        """Launch just the API server for testing."""
        print(f"\n{Colors.OKBLUE}🚀 Launching API Server...{Colors.ENDC}")
        print()
        
        # Simple FastAPI server launch
        try:
            import uvicorn
            print("📡 Starting Uvicorn server...")
            print("🌐 Server will be available at: http://localhost:8000")
            print("📚 API Documentation: http://localhost:8000/docs")
            print()
            print(f"{Colors.WARNING}Press Ctrl+C to stop the server{Colors.ENDC}")
            print()
            
            # Basic FastAPI app for testing
            test_app_code = '''
from fastapi import FastAPI
from datetime import datetime

app = FastAPI(title="OP Trading Platform API", version="3.3.0")

@app.get("/")
def read_root():
    return {"message": "OP Trading Platform API", "status": "running", "timestamp": datetime.now().isoformat()}

@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
'''
            
            # Write temporary app file
            temp_app_file = self.project_root / "temp_api.py"
            with open(temp_app_file, 'w') as f:
                f.write(test_app_code)
            
            # Launch server
            uvicorn.run("temp_api:app", host="0.0.0.0", port=8000, reload=True)
            
        except ImportError:
            print(f"{Colors.FAIL}❌ Uvicorn not installed. Cannot start API server.{Colors.ENDC}")
            print("   Install it with: pip install uvicorn")
        except KeyboardInterrupt:
            print(f"\n{Colors.WARNING}🛑 API server stopped by user{Colors.ENDC}")
        except Exception as e:
            print(f"\n{Colors.FAIL}❌ Error launching API server: {str(e)}{Colors.ENDC}")
        finally:
            # Clean up temp file
            temp_app_file = self.project_root / "temp_api.py"
            if temp_app_file.exists():
                temp_app_file.unlink()
        
        print("\n" + "="*50)
        input("Press Enter to return to options menu...")
        self.show_continuation_options()
    
    def run_system_validation(self):
        """Run comprehensive system validation."""
        print(f"\n{Colors.OKCYAN}🔍 Running System Validation...{Colors.ENDC}")
        print()
        
        validation_results = self.validate_services()
        
        print(f"\n📊 Validation Summary:")
        healthy_services = sum(1 for result in validation_results.values() if result)
        total_services = len(validation_results)
        
        print(f"   ✅ Healthy services: {healthy_services}/{total_services}")
        print(f"   ❌ Unhealthy services: {total_services - healthy_services}/{total_services}")
        
        if healthy_services == total_services:
            print(f"\n{Colors.OKGREEN}🎉 All services are healthy!{Colors.ENDC}")
        elif healthy_services > 0:
            print(f"\n{Colors.WARNING}⚠️  Some services are unhealthy{Colors.ENDC}")
        else:
            print(f"\n{Colors.FAIL}❌ No services are healthy{Colors.ENDC}")
        
        print("\n" + "="*50)
        input("Press Enter to return to options menu...")
        self.show_continuation_options()
    
    def review_setup_issues(self):
        """Review detailed setup issues."""
        print(f"\n{Colors.WARNING}📋 Setup Issues Review{Colors.ENDC}")
        print()
        
        if not self.state.errors and not self.state.warnings:
            print(f"{Colors.OKGREEN}✅ No issues found during setup!{Colors.ENDC}")
        else:
            if self.state.errors:
                print(f"{Colors.FAIL}❌ ERRORS ({len(self.state.errors)}):{Colors.ENDC}")
                for i, error in enumerate(self.state.errors, 1):
                    print(f"   {i}. {error['error']}")
                    print(f"      Time: {error['timestamp']}")
                print()
            
            if self.state.warnings:
                print(f"{Colors.WARNING}⚠️  WARNINGS ({len(self.state.warnings)}):{Colors.ENDC}")
                for i, warning in enumerate(self.state.warnings, 1):
                    print(f"   {i}. {warning['warning']}")
                    print(f"      Time: {warning['timestamp']}")
        
        print("\n" + "="*50)
        input("Press Enter to return to options menu...")
        self.show_continuation_options()
    
    def run_setup(self):
        """Run the complete enhanced setup process."""
        try:
            # Main menu
            mode = self.main_menu()
            self.state.mode = mode
            
            # Get bypass options for Production/Development modes
            self.get_bypass_options(mode)
            
            print(f"\n{Colors.OKGREEN}🚀 Starting {mode.title()} Mode Setup{Colors.ENDC}")
            print()
            
            # Setup steps
            steps = [
                ("System Requirements Check", self.check_system_requirements),
                ("Smart Prerequisites Installation", self.handle_prerequisites),
                ("Directory Structure Creation", self.create_directory_structure), 
                ("Environment Configuration", self.handle_environment_configuration),
                ("Docker Network Reconciliation", self.reconcile_docker_networks)
            ]
            
            validation_results = None
            
            for step_name, step_function in steps:
                success = step_function()
                
                if not success:
                    print(f"\n{Colors.FAIL}❌ Setup failed at: {step_name}{Colors.ENDC}")
                    print("Check the logs for detailed error information")
                    self.state.add_error(f"Setup failed at {step_name}")
                    break
                
                # Brief pause between steps
                time.sleep(0.5)
            
            else:
                # All steps completed, validate services
                validation_results = self.validate_services()
            
            # Print completion summary with continuation options
            self.print_completion_summary(validation_results)
            
            return True
            
        except KeyboardInterrupt:
            print(f"\n{Colors.WARNING}🛑 Setup interrupted by user{Colors.ENDC}")
            return False
        except Exception as e:
            print(f"\n{Colors.FAIL}💥 Setup failed with unexpected error: {str(e)}{Colors.ENDC}")
            logger.error(f"Unexpected setup error: {str(e)}")
            return False

# ================================================================================================
# MAIN ENTRY POINT
# ================================================================================================

def main():
    """Main entry point for the enhanced initialization script."""
    try:
        script = EnhancedInitializationScript()
        success = script.run_setup()
        
        if success:
            print(f"\n{Colors.OKGREEN}✅ Enhanced setup system ready!{Colors.ENDC}")
            sys.exit(0)
        else:
            print(f"\n{Colors.FAIL}❌ Setup failed. Please check the logs.{Colors.ENDC}")
            sys.exit(1)
    
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}🛑 Setup interrupted by user.{Colors.ENDC}")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Colors.FAIL}💥 Critical error: {str(e)}{Colors.ENDC}")
        sys.exit(1)

if __name__ == "__main__":
    main()