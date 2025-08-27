#!/usr/bin/env python3
"""
OP TRADING PLATFORM - SIMPLE SETUP SCRIPT
==========================================
Version: 3.1.1 - Simple One-Command Setup
Date: 2025-08-25 7:47 PM IST

SIMPLE SETUP APPROACH
If the interactive script is too complex, use this simple setup:

USAGE:
    python simple_setup.py production    # For production setup
    python simple_setup.py development   # For development setup  
    python simple_setup.py setup         # For first-time setup
"""

import sys
import os
import subprocess
from pathlib import Path

def create_project_structure():
    """Create essential project directories."""
    dirs = [
        "data/raw_snapshots/overview", "data/raw_snapshots/options",
        "logs/setup", "logs/application", "config/environments",
        "services/collection", "tests/unit"
    ]
    
    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        print(f"✅ Created: {dir_path}")

def create_env_file():
    """Create basic .env file."""
    env_content = """# OP Trading Platform Configuration
PYTHONPATH=${PWD}
DEPLOYMENT_MODE=development
LOG_LEVEL=INFO

# Kite Connect API (Update these!)
KITE_API_KEY=your_kite_api_key_here
KITE_API_SECRET=your_kite_api_secret_here

# Database
INFLUXDB_URL=http://localhost:8086
REDIS_HOST=localhost
REDIS_PORT=6379

# Features
ENABLE_PARTICIPANT_ANALYSIS=true
ENABLE_CASH_FLOW_TRACKING=true
"""
    
    with open('.env', 'w') as f:
        f.write(env_content)
    print("✅ Created .env file")

def create_docker_compose():
    """Create basic docker-compose.yml."""
    compose_content = """version: '3.8'
services:
  influxdb:
    image: influxdb:2.7-alpine
    ports:
      - "8086:8086"
    environment:
      DOCKER_INFLUXDB_INIT_MODE: setup
      DOCKER_INFLUXDB_INIT_USERNAME: admin
      DOCKER_INFLUXDB_INIT_PASSWORD: admin123
      DOCKER_INFLUXDB_INIT_ORG: op-trading
      DOCKER_INFLUXDB_INIT_BUCKET: options-data
    volumes:
      - influxdb-data:/var/lib/influxdb2

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  influxdb-data:
"""
    
    with open('docker-compose.yml', 'w') as f:
        f.write(compose_content)
    print("✅ Created docker-compose.yml")

def install_packages():
    """Install essential packages."""
    packages = [
        "fastapi", "uvicorn", "redis", "influxdb-client", 
        "python-dotenv", "pandas", "numpy", "aiohttp", "requests"
    ]
    
    for package in packages:
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", package], 
                         check=True, capture_output=True)
            print(f"✅ Installed: {package}")
        except subprocess.CalledProcessError:
            print(f"❌ Failed to install: {package}")

def start_services():
    """Start Docker services."""
    try:
        subprocess.run(["docker-compose", "up", "-d"], check=True)
        print("✅ Started Docker services")
    except subprocess.CalledProcessError:
        print("❌ Failed to start services")
        print("   Make sure Docker is running")

def main():
    """Simple setup based on mode."""
    if len(sys.argv) != 2:
        print("Usage: python simple_setup.py [production|development|setup]")
        sys.exit(1)
    
    mode = sys.argv[1].lower()
    
    print(f"🚀 OP Trading Platform - Simple {mode.title()} Setup")
    print("=" * 50)
    
    # Basic setup for all modes
    print("📁 Creating project structure...")
    create_project_structure()
    
    print("\n⚙️ Creating configuration...")
    create_env_file()
    create_docker_compose()
    
    if mode in ['production', 'development']:
        print("\n📦 Installing packages...")
        install_packages()
        
        print("\n🐳 Starting services...")
        start_services()
    
    print(f"\n✅ {mode.title()} setup completed!")
    print("\nNext steps:")
    print("1. Edit .env file with your Kite Connect credentials")
    if mode in ['production', 'development']:
        print("2. Run: python main.py")
        print("3. Access: http://localhost:8000/docs")
    else:
        print("2. Run production or development setup when ready")

if __name__ == "__main__":
    main()