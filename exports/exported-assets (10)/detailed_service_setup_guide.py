#!/usr/bin/env python3
"""
OP TRADING PLATFORM - DETAILED SERVICE SETUP GUIDE
===================================================
Version: 3.1.2 - Step-by-Step Service Setup Instructions
Author: OP Trading Platform Team
Date: 2025-08-25 11:48 PM IST

COMPREHENSIVE SERVICE SETUP GUIDE
This guide provides detailed steps to set up all required services:
✓ InfluxDB 2.x with proper configuration
✓ Redis with optimized settings
✓ Prometheus for metrics collection  
✓ Grafana for visualization
✓ Troubleshooting common issues
"""

# ================================================================================================
# STEP-BY-STEP SERVICE SETUP INSTRUCTIONS
# ================================================================================================

print("""
🚀 OP TRADING PLATFORM - DETAILED SERVICE SETUP GUIDE
=====================================================

Since your setup is having issues with pip install and docker-compose, let's fix this step by step.

📋 SETUP ORDER:
1. Fix Python Dependencies
2. Create Working Docker Compose
3. Set up InfluxDB
4. Set up Redis  
5. Set up Prometheus
6. Set up Grafana
7. Validate All Services

════════════════════════════════════════════════════════════════════════════════════════════════

STEP 1: FIX PYTHON DEPENDENCIES
═══════════════════════════════════════════════════════════════════════════════════════════════

Issue: pip install -r requirements.txt is failing

SOLUTION A: Create Minimal Requirements File
--------------------------------------------
Create a new file called 'requirements-minimal.txt' with only essential packages:

fastapi==0.104.1
uvicorn[standard]==0.24.0
pandas==2.1.4
numpy==1.24.3
redis==5.0.1
influxdb-client==1.39.0
python-dotenv==1.0.0
requests==2.31.0
aiohttp==3.9.1
prometheus-client==0.19.0
psutil==5.9.6

Then install:
pip install --upgrade pip
pip install -r requirements-minimal.txt

SOLUTION B: Install Packages Individually
------------------------------------------
If above fails, install one by one:

pip install fastapi uvicorn pandas numpy redis influxdb-client python-dotenv requests aiohttp

════════════════════════════════════════════════════════════════════════════════════════════════

STEP 2: CREATE WORKING DOCKER COMPOSE
════════════════════════════════════════════════════════════════════════════════════════════════

Issue: docker-compose up is failing

Create a new file called 'docker-compose-simple.yml':

version: '3.8'

services:
  influxdb:
    image: influxdb:2.7-alpine
    container_name: op-influxdb
    restart: unless-stopped
    ports:
      - "8086:8086"
    environment:
      DOCKER_INFLUXDB_INIT_MODE: setup
      DOCKER_INFLUXDB_INIT_USERNAME: admin
      DOCKER_INFLUXDB_INIT_PASSWORD: adminpass123
      DOCKER_INFLUXDB_INIT_ORG: op-trading
      DOCKER_INFLUXDB_INIT_BUCKET: options-data
      DOCKER_INFLUXDB_INIT_RETENTION: 0s
      DOCKER_INFLUXDB_INIT_ADMIN_TOKEN: VFEhioeCi2vFCtv-dH_7Fe6gEgNtO-Tu7qcQW4WvIbAFQIdKGa_hDu4dxatOgwskZcva4CHkeOPbjkQwAvPyVg==
    volumes:
      - influxdb-data:/var/lib/influxdb2
    networks:
      - op-network

  redis:
    image: redis:7-alpine
    container_name: op-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    command: redis-server --save 60 1000 --loglevel warning --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis-data:/data
    networks:
      - op-network

  prometheus:
    image: prom/prometheus:v2.48.0
    container_name: op-prometheus
    restart: unless-stopped
    ports:
      - "9090:9090"
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=90d'
      - '--web.enable-lifecycle'
    volumes:
      - prometheus-data:/prometheus
    networks:
      - op-network

  grafana:
    image: grafana/grafana:10.2.2
    container_name: op-grafana
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: admin123
    volumes:
      - grafana-data:/var/lib/grafana
    networks:
      - op-network
    depends_on:
      - influxdb

volumes:
  influxdb-data:
  redis-data:
  prometheus-data:
  grafana-data:

networks:
  op-network:
    driver: bridge

════════════════════════════════════════════════════════════════════════════════════════════════

STEP 3: START SERVICES ONE BY ONE
════════════════════════════════════════════════════════════════════════════════════════════════

Commands to run (in PowerShell):

# Start InfluxDB first
docker-compose -f docker-compose-simple.yml up -d influxdb

# Wait 30 seconds, then check
Start-Sleep -Seconds 30
Invoke-WebRequest -Uri "http://localhost:8086/health" -TimeoutSec 10

# Start Redis
docker-compose -f docker-compose-simple.yml up -d redis

# Test Redis
docker exec op-redis redis-cli ping

# Start Prometheus
docker-compose -f docker-compose-simple.yml up -d prometheus

# Test Prometheus
Invoke-WebRequest -Uri "http://localhost:9090/-/healthy" -TimeoutSec 10

# Start Grafana
docker-compose -f docker-compose-simple.yml up -d grafana

# Test Grafana
Invoke-WebRequest -Uri "http://localhost:3000/api/health" -TimeoutSec 10

════════════════════════════════════════════════════════════════════════════════════════════════

STEP 4: DETAILED INFLUXDB SETUP
════════════════════════════════════════════════════════════════════════════════════════════════

A. Verify InfluxDB is Running:
   http://localhost:8086/health
   Should return: {"status":"pass"}

B. Access InfluxDB UI:
   1. Open: http://localhost:8086
   2. Login: admin / adminpass123
   3. You should see the OP Trading organization

C. Create Additional Buckets:
   PowerShell commands:

   $TOKEN = "VFEhioeCi2vFCtv-dH_7Fe6gEgNtO-Tu7qcQW4WvIbAFQIdKGa_hDu4dxatOgwskZcva4CHkeOPbjkQwAvPyVg=="
   $ORG = "op-trading"
   $URL = "http://localhost:8086"

   # Create participant-flows bucket
   $body = @{
       orgID = $ORG
       name = "participant-flows"
       description = "FII, DII, Pro, Client flow data"
       retentionRules = @(@{
           type = "expire"
           everySeconds = 0
       })
   } | ConvertTo-Json -Depth 3

   Invoke-RestMethod -Method POST -Uri "$URL/api/v2/buckets" -Headers @{Authorization="Token $TOKEN"} -Body $body -ContentType "application/json"

   # Create cash-flows bucket
   $body = @{
       orgID = $ORG
       name = "cash-flows"
       description = "Cash flow tracking data"
       retentionRules = @(@{
           type = "expire"
           everySeconds = 0
       })
   } | ConvertTo-Json -Depth 3

   Invoke-RestMethod -Method POST -Uri "$URL/api/v2/buckets" -Headers @{Authorization="Token $TOKEN"} -Body $body -ContentType "application/json"

D. Test Write/Read:
   # Write test data
   $ts = [int64]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds()) * 1000000000
   $testData = "test_measurement,host=test value=1 $ts"
   Invoke-RestMethod -Method POST -Uri "$URL/api/v2/write?org=$ORG&bucket=options-data&precision=ns" -Headers @{Authorization="Token $TOKEN"} -Body $testData -ContentType "text/plain"

   # Query test data
   $query = @"
   from(bucket: "options-data")
     |> range(start: -1h)
     |> filter(fn: (r) => r._measurement == "test_measurement")
     |> limit(n: 1)
"@
   Invoke-RestMethod -Method POST -Uri "$URL/api/v2/query?org=$ORG" -Headers @{Authorization="Token $TOKEN"; Accept="application/csv"} -Body (@{ query = $query } | ConvertTo-Json) -ContentType "application/json"

════════════════════════════════════════════════════════════════════════════════════════════════

STEP 5: DETAILED REDIS SETUP
════════════════════════════════════════════════════════════════════════════════════════════════

A. Verify Redis is Running:
   docker exec op-redis redis-cli ping
   Should return: PONG

B. Test Redis Operations:
   # Set test key
   docker exec op-redis redis-cli set test_key "test_value"

   # Get test key
   docker exec op-redis redis-cli get test_key

   # Check Redis info
   docker exec op-redis redis-cli info memory

C. Redis Configuration Check:
   docker exec op-redis redis-cli config get maxmemory
   docker exec op-redis redis-cli config get maxmemory-policy

D. Monitor Redis:
   docker exec op-redis redis-cli monitor

════════════════════════════════════════════════════════════════════════════════════════════════

STEP 6: DETAILED PROMETHEUS SETUP
════════════════════════════════════════════════════════════════════════════════════════════════

A. Verify Prometheus is Running:
   http://localhost:9090/-/healthy
   Should return: Prometheus is Healthy

B. Access Prometheus UI:
   1. Open: http://localhost:9090
   2. Check Status -> Targets
   3. Should see prometheus target as UP

C. Create Prometheus Config:
   Create folder: config/prometheus/
   Create file: config/prometheus/prometheus.yml

   global:
     scrape_interval: 15s

   scrape_configs:
     - job_name: 'prometheus'
       static_configs:
         - targets: ['localhost:9090']

     - job_name: 'op-trading-api'
       static_configs:
         - targets: ['host.docker.internal:8000']
       metrics_path: '/metrics'
       scrape_interval: 30s

D. Reload Prometheus Config:
   Invoke-RestMethod -Method POST -Uri "http://localhost:9090/-/reload"

E. Test Metrics Query:
   # Basic up query
   http://localhost:9090/api/v1/query?query=up

════════════════════════════════════════════════════════════════════════════════════════════════

STEP 7: DETAILED GRAFANA SETUP
════════════════════════════════════════════════════════════════════════════════════════════════

A. Verify Grafana is Running:
   http://localhost:3000/api/health
   Should return: {"database":"ok"}

B. Access Grafana UI:
   1. Open: http://localhost:3000
   2. Login: admin / admin123

C. Add InfluxDB Data Source:
   1. Go to Configuration -> Data Sources
   2. Click "Add data source"
   3. Select "InfluxDB"
   4. Configure:
      - Name: InfluxDB-OptionsData
      - URL: http://influxdb:8086
      - Database: options-data
      - Organization: op-trading
      - Token: VFEhioeCi2vFCtv-dH_7Fe6gEgNtO-Tu7qcQW4WvIbAFQIdKGa_hDu4dxatOgwskZcva4CHkeOPbjkQwAvPyVg==
   5. Click "Save & Test"

D. Add Prometheus Data Source:
   1. Add data source -> Prometheus
   2. URL: http://prometheus:9090
   3. Save & Test

E. Create Test Dashboard:
   1. Create -> Dashboard
   2. Add Panel
   3. Query: from(bucket: "options-data") |> range(start: -1h)
   4. Run Query

════════════════════════════════════════════════════════════════════════════════════════════════

STEP 8: TROUBLESHOOTING COMMON ISSUES
════════════════════════════════════════════════════════════════════════════════════════════════

Issue 1: Docker Compose Fails
------------------------------
Solution:
# Check Docker is running
docker version

# Check if ports are in use
netstat -an | findstr ":8086"
netstat -an | findstr ":6379"
netstat -an | findstr ":9090"
netstat -an | findstr ":3000"

# If ports are in use, change them in docker-compose-simple.yml

Issue 2: InfluxDB Won't Start
-----------------------------
Solution:
# Check logs
docker logs op-influxdb

# Remove and recreate
docker-compose -f docker-compose-simple.yml down
docker volume rm $(docker volume ls -q | findstr influxdb)
docker-compose -f docker-compose-simple.yml up -d influxdb

Issue 3: Redis Connection Refused
----------------------------------
Solution:
# Check Redis logs
docker logs op-redis

# Test connection
docker exec op-redis redis-cli ping

Issue 4: Grafana Can't Connect to InfluxDB
-------------------------------------------
Solution:
# Use container names in URLs
# InfluxDB URL should be: http://influxdb:8086 (not localhost:8086)
# Prometheus URL should be: http://prometheus:9090 (not localhost:9090)

Issue 5: Services Can't Communicate
------------------------------------
Solution:
# Check network
docker network ls
docker network inspect $(docker-compose -f docker-compose-simple.yml config | grep -A1 networks: | tail -1 | awk '{print $1}')

════════════════════════════════════════════════════════════════════════════════════════════════

STEP 9: FINAL VALIDATION
════════════════════════════════════════════════════════════════════════════════════════════════

Run these commands to validate everything is working:

# Check all containers
docker ps

# Check all services health
Invoke-WebRequest -Uri "http://localhost:8086/health"
docker exec op-redis redis-cli ping
Invoke-WebRequest -Uri "http://localhost:9090/-/healthy"
Invoke-WebRequest -Uri "http://localhost:3000/api/health"

# Check logs for errors
docker logs op-influxdb --tail 20
docker logs op-redis --tail 20
docker logs op-prometheus --tail 20
docker logs op-grafana --tail 20

SUCCESS INDICATORS:
✅ InfluxDB health returns {"status":"pass"}
✅ Redis ping returns PONG
✅ Prometheus healthy page loads
✅ Grafana login page loads
✅ All containers show as "Up" in docker ps

════════════════════════════════════════════════════════════════════════════════════════════════

STEP 10: NEXT STEPS AFTER SUCCESS
════════════════════════════════════════════════════════════════════════════════════════════════

1. Update your .env file with correct service URLs:
   INFLUXDB_URL=http://localhost:8086
   REDIS_HOST=localhost
   REDIS_PORT=6379

2. Test your Python application:
   python main.py --mode development

3. Access services:
   - API: http://localhost:8000
   - InfluxDB: http://localhost:8086
   - Grafana: http://localhost:3000
   - Prometheus: http://localhost:9090

════════════════════════════════════════════════════════════════════════════════════════════════

If you encounter any specific errors, share the exact error message and I'll provide targeted solutions!
""")