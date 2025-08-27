# OP TRADING PLATFORM - COMPREHENSIVE TROUBLESHOOTING GUIDE
# Version: 1.0.0 - Complete System Troubleshooting
# Last Updated: 2025-08-25 11:40 AM IST

This guide provides comprehensive troubleshooting solutions for all components of the OP Trading Platform, including setup issues, runtime problems, and recovery procedures.

## 📋 TABLE OF CONTENTS

1. [Quick Diagnostic Commands](#quick-diagnostic-commands)
2. [Setup & Installation Issues](#setup--installation-issues) 
3. [Authentication & Kite Connect Issues](#authentication--kite-connect-issues)
4. [Database & Storage Issues](#database--storage-issues)
5. [Service & Network Issues](#service--network-issues)
6. [Performance & Memory Issues](#performance--memory-issues)
7. [Enhanced Features Issues](#enhanced-features-issues)
8. [Dashboard & Monitoring Issues](#dashboard--monitoring-issues)
9. [Data Recovery Procedures](#data-recovery-procedures)
10. [Production Issues](#production-issues)
11. [Common Error Messages](#common-error-messages)
12. [Emergency Recovery](#emergency-recovery)

## 🔍 QUICK DIAGNOSTIC COMMANDS

### System Status Check
```powershell
# Check all services status
docker ps -a

# Check logs for errors
Get-Content logs\*.log | Select-String "ERROR" | Select-Object -Last 10

# Test environment configuration
python -c "from shared.config.settings import get_settings; print('Config OK')"

# Check system resources
Get-WmiObject -Class Win32_OperatingSystem | Select-Object FreePhysicalMemory,TotalVisibleMemorySize
```

### Quick Service Tests
```powershell
# Test InfluxDB
Invoke-WebRequest -Uri "http://localhost:8086/ping" -UseBasicParsing

# Test Redis
docker exec op-redis redis-cli ping

# Test API Health
Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing
```

## 🚀 SETUP & INSTALLATION ISSUES

### Issue: PowerShell Setup Script Fails with Permission Denied
**Symptoms:** 
- Script execution blocked
- "Execution of scripts is disabled on this system"

**Solution:**
```powershell
# Check current execution policy
Get-ExecutionPolicy

# Set execution policy (run as Administrator)
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser

# Alternative: Bypass policy for single script
PowerShell.exe -ExecutionPolicy Bypass -File setup.ps1 -Mode development
```

### Issue: Docker Services Won't Start
**Symptoms:**
- Container startup failures
- Port binding errors
- Volume mount failures

**Diagnosis & Solutions:**

1. **Check Docker Status:**
```powershell
# Verify Docker is running
docker version

# Check Docker service
Get-Service *docker*
```

2. **Port Conflicts:**
```powershell
# Check what's using ports
netstat -ano | findstr :8086
netstat -ano | findstr :6379
netstat -ano | findstr :3000

# Kill processes using required ports
taskkill /PID <PID_NUMBER> /F
```

3. **Fix Volume Permissions:**
```powershell
# Create volumes explicitly
docker volume create influxdb2-data
docker volume create redis-data
docker volume create grafana-data

# Remove and recreate containers
docker rm -f op-influxdb op-redis op-grafana
# Re-run setup script
```

### Issue: Python Dependencies Installation Fails
**Symptoms:**
- pip install errors
- Module not found errors
- Version conflicts

**Solutions:**

1. **Update pip and setuptools:**
```cmd
python -m pip install --upgrade pip setuptools wheel
```

2. **Use virtual environment:**
```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

3. **Fix specific package issues:**
```cmd
# For Windows compilation issues
pip install --upgrade setuptools-scm
pip install --only-binary=all -r requirements.txt

# Alternative installation
pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r requirements.txt
```

### Issue: Prerequisites Check Fails
**Symptoms:**
- Missing tools detected
- Version compatibility issues

**Solutions:**

1. **Install Missing Python:**
   - Download from: https://www.python.org/downloads/
   - Choose "Add Python to PATH" during installation
   - Verify: `python --version`

2. **Install Docker Desktop:**
   - Download from: https://www.docker.com/products/docker-desktop
   - Ensure WSL2 is enabled on Windows
   - Verify: `docker --version`

3. **Install Git:**
   - Download from: https://git-scm.com/downloads
   - Verify: `git --version`

## 🔐 AUTHENTICATION & KITE CONNECT ISSUES

### Issue: Kite Connect Authentication Fails
**Symptoms:**
- "Invalid API credentials" errors
- Authentication token expired
- Login redirects don't work

**Diagnosis & Solutions:**

1. **Verify API Credentials:**
```python
# Test basic API key format
api_key = "your_api_key"
if len(api_key) != 8:
    print("❌ API Key should be 8 characters")
else:
    print("✅ API Key format correct")
```

2. **Get New API Key:**
   - Go to https://kite.trade/connect/
   - Login with Zerodha account
   - Create new app or regenerate keys
   - Update .env file

3. **Authentication Flow Issues:**
```python
# Run interactive authentication
python services/collection/integrated_kite_auth_logger.py --login

# Check authentication status
python services/collection/integrated_kite_auth_logger.py --status

# Clear cached sessions
python services/collection/integrated_kite_auth_logger.py --logout
```

### Issue: Authentication Logging Not Working
**Symptoms:**
- No authentication logs in dashboard
- Missing authentication events
- Redis authentication data not found

**Solutions:**

1. **Check Redis Connection:**
```python
import redis
try:
    r = redis.Redis(host='localhost', port=6379, db=0)
    r.ping()
    print("✅ Redis connected")
except:
    print("❌ Redis connection failed")
```

2. **Verify Authentication Logger:**
```python
# Test authentication logger directly
from services.collection.integrated_kite_auth_logger import IntegratedAuthLogger
import asyncio

async def test_auth_logger():
    logger = IntegratedAuthLogger()
    await logger.log_authentication_event({
        'event_id': 'test-123',
        'event_type': 'TEST_EVENT',
        'timestamp': '2025-08-25T11:40:00',
        'success': True
    })
    print("✅ Authentication logging works")

asyncio.run(test_auth_logger())
```

3. **Check Authentication Metrics:**
```python
# Get authentication dashboard data
python -c "
from services.collection.integrated_kite_auth_logger import IntegratedKiteAuthManager
import asyncio
async def test():
    manager = IntegratedKiteAuthManager()
    data = await manager.get_auth_dashboard_data()
    print(data)
asyncio.run(test())
"
```

## 💾 DATABASE & STORAGE ISSUES

### Issue: InfluxDB Connection Failures
**Symptoms:**
- "Connection refused" errors
- Data not being saved
- InfluxDB container not running

**Diagnosis & Solutions:**

1. **Check InfluxDB Container:**
```powershell
# Check container status
docker ps | findstr influx

# View container logs
docker logs op-influxdb

# Restart container
docker restart op-influxdb
```

2. **Test InfluxDB Connection:**
```python
from influxdb_client import InfluxDBClient
import os

client = InfluxDBClient(
    url="http://localhost:8086",
    token=os.getenv('INFLUXDB_TOKEN'),
    org=os.getenv('INFLUXDB_ORG')
)

try:
    health = client.health()
    print(f"✅ InfluxDB Health: {health.status}")
except Exception as e:
    print(f"❌ InfluxDB Error: {e}")
```

3. **Fix InfluxDB Data Issues:**
```powershell
# Check InfluxDB data volume
docker volume inspect influxdb2-data

# Backup and recreate if corrupted
docker run --rm -v influxdb2-data:/source -v ${PWD}/backup:/backup alpine tar czf /backup/influxdb_backup.tar.gz -C /source .

# Remove corrupted volume
docker volume rm influxdb2-data

# Recreate container
docker run -d --name op-influxdb -p 8086:8086 -v influxdb2-data:/var/lib/influxdb2 influxdb:2.7-alpine
```

### Issue: Redis Connection Issues
**Symptoms:**
- Redis connection timeouts
- Cache not working
- Redis container crashes

**Solutions:**

1. **Check Redis Status:**
```powershell
# Check container
docker ps | findstr redis

# Check logs
docker logs op-redis

# Check memory usage
docker stats op-redis --no-stream
```

2. **Test Redis Functionality:**
```python
import redis
import json

r = redis.Redis(host='localhost', port=6379, db=0)

# Test basic operations
r.set('test_key', 'test_value')
value = r.get('test_key')
print(f"✅ Redis test: {value}")

# Test JSON operations
data = {'test': True, 'timestamp': '2025-08-25'}
r.set('test_json', json.dumps(data))
retrieved = json.loads(r.get('test_json'))
print(f"✅ Redis JSON: {retrieved}")
```

3. **Fix Redis Memory Issues:**
```powershell
# Increase Redis memory limit
docker rm -f op-redis
docker run -d --name op-redis -p 6379:6379 --memory=1g -v redis-data:/data redis:7-alpine redis-server --maxmemory 800mb --save 60 1
```

### Issue: Infinite Retention Not Working
**Symptoms:**
- Data being deleted automatically
- Retention policy not applied
- Historical data missing

**Solutions:**

1. **Verify InfluxDB Retention Policy:**
```python
from influxdb_client import InfluxDBClient
from influxdb_client.client.buckets_api import BucketsApi

client = InfluxDBClient(url="http://localhost:8086", token="your_token", org="your_org")
buckets_api = BucketsApi(client)

# Check bucket retention
buckets = buckets_api.find_buckets()
for bucket in buckets.buckets:
    print(f"Bucket: {bucket.name}, Retention: {bucket.retention_rules}")
```

2. **Update Retention Policy:**
```python
# Set infinite retention
bucket = buckets_api.find_bucket_by_name("your-bucket")
bucket.retention_rules = []  # Empty rules = infinite retention
buckets_api.update_bucket(bucket)
print("✅ Infinite retention policy set")
```

3. **Check Environment Configuration:**
```powershell
# Verify .env settings
Get-Content .env | Select-String "RETENTION"

# Should show:
# INFLUXDB_RETENTION_POLICY=infinite
# DATA_RETENTION_POLICY=infinite
```

## 🌐 SERVICE & NETWORK ISSUES

### Issue: API Server Won't Start
**Symptoms:**
- "Address already in use" errors
- FastAPI startup failures
- Import errors

**Solutions:**

1. **Check Port Usage:**
```powershell
# Find what's using port 8000
netstat -ano | findstr :8000

# Kill the process if needed
taskkill /PID <PID_NUMBER> /F
```

2. **Test API Startup:**
```cmd
# Start API directly for debugging
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Check for import errors
python -c "import main; print('✅ Main module loads')"
```

3. **Fix Import Issues:**
```python
# Check Python path
import sys
print("Python path:", sys.path)

# Add current directory to path
sys.path.insert(0, '.')

# Test imports
try:
    from shared.config.settings import get_settings
    from services.analytics.complete_analytics_service import CompleteAnalyticsService
    print("✅ All imports successful")
except ImportError as e:
    print(f"❌ Import error: {e}")
```

### Issue: Network Connectivity Problems
**Symptoms:**
- External API timeouts
- DNS resolution failures
- SSL certificate errors

**Solutions:**

1. **Test Internet Connectivity:**
```powershell
# Test basic connectivity
Test-NetConnection google.com -Port 80

# Test DNS resolution
Resolve-DnsName api.kite.trade

# Test Kite API
Invoke-WebRequest -Uri "https://api.kite.trade" -UseBasicParsing
```

2. **Fix SSL Issues:**
```python
import ssl
import requests

# Disable SSL verification for testing (NOT for production)
requests.packages.urllib3.disable_warnings()
response = requests.get('https://api.kite.trade', verify=False)
print(f"Status: {response.status_code}")
```

3. **Configure Proxy (if needed):**
```powershell
# Set proxy environment variables
$env:HTTP_PROXY = "http://proxy.company.com:8080"
$env:HTTPS_PROXY = "http://proxy.company.com:8080"

# Test with proxy
Invoke-WebRequest -Uri "https://api.kite.trade" -Proxy "http://proxy.company.com:8080"
```

## ⚡ PERFORMANCE & MEMORY ISSUES

### Issue: High Memory Usage
**Symptoms:**
- System becoming slow
- Out of memory errors
- Application crashes

**Diagnosis & Solutions:**

1. **Monitor Memory Usage:**
```python
import psutil
import os

# Check current process memory
process = psutil.Process(os.getpid())
memory_info = process.memory_info()
print(f"RSS: {memory_info.rss / 1024 / 1024:.1f} MB")
print(f"VMS: {memory_info.vms / 1024 / 1024:.1f} MB")

# Check system memory
memory = psutil.virtual_memory()
print(f"Available: {memory.available / 1024 / 1024:.1f} MB")
print(f"Usage: {memory.percent}%")
```

2. **Optimize Memory Settings:**
```env
# Update .env file
MAX_MEMORY_USAGE_MB=2048
CSV_BUFFER_SIZE=4096
JSON_BUFFER_SIZE=8192
PROCESSING_BATCH_SIZE=500
PROCESSING_MAX_WORKERS=4
```

3. **Clear Memory Leaks:**
```python
# Force garbage collection
import gc
gc.collect()

# Clear Redis cache
import redis
r = redis.Redis()
r.flushdb()  # Clear current database
```

### Issue: Poor Performance
**Symptoms:**
- Slow response times
- High CPU usage
- Timeouts

**Solutions:**

1. **Profile Performance:**
```python
import time
import cProfile

def profile_function():
    # Your code here
    start_time = time.time()
    # ... perform operations ...
    end_time = time.time()
    print(f"Operation took: {end_time - start_time:.2f} seconds")

# Run with profiler
cProfile.run('profile_function()')
```

2. **Optimize Database Queries:**
```python
# Use batch operations
from influxdb_client import Point
from influxdb_client.client.write_api import SYNCHRONOUS

# Batch write points
points = []
for i in range(1000):
    point = Point("measurement").tag("tag", "value").field("value", i)
    points.append(point)

write_api.write(bucket="bucket", record=points)
```

3. **Optimize Processing:**
```env
# Tune performance settings
PROCESSING_BATCH_SIZE=1000
USE_MEMORY_MAPPING=true
COMPRESSION_ENABLED=false  # For real-time processing
PARALLEL_PROCESSING=true
```

## 🚀 ENHANCED FEATURES ISSUES

### Issue: FII/DII/Pro/Client Analysis Not Working
**Symptoms:**
- Participant data shows zeros
- Analysis panels empty
- "Data unavailable" errors

**Solutions:**

1. **Check Feature Flags:**
```env
# Verify .env settings
ENABLE_FII_ANALYSIS=true
ENABLE_DII_ANALYSIS=true
ENABLE_PRO_TRADER_ANALYSIS=true
ENABLE_CLIENT_ANALYSIS=true
```

2. **Test Participant Analysis:**
```python
from services.analytics.complete_analytics_service import CompleteAnalyticsService
import asyncio

async def test_participant_analysis():
    service = CompleteAnalyticsService()
    data = await service.get_complete_analytics_data("NIFTY", include_errors=True)
    
    if 'all_participant_activity' in data:
        print("✅ Participant analysis working")
        print(f"FII Net Premium: {data['all_participant_activity']['fii_net_premium']}")
    else:
        print("❌ Participant analysis not found")

asyncio.run(test_participant_analysis())
```

3. **Debug Data Source:**
```python
# Check if mock data is generating participant data
from services.analytics.complete_analytics_service import CompleteAnalyticsEngine

engine = CompleteAnalyticsEngine()
participant_data = await engine._fetch_all_participant_data("NIFTY")
print(f"Participant data: {participant_data}")
```

### Issue: Price Toggle Functionality Not Working
**Symptoms:**
- Toggle doesn't switch between last/average price
- Historical price data missing
- Price efficiency scores not updating

**Solutions:**

1. **Check Price Toggle Settings:**
```env
ENABLE_PRICE_TOGGLE=true
ENABLE_AVERAGE_PRICE_CALCULATION=true
DEFAULT_PRICE_MODE=LAST_PRICE
```

2. **Verify Average Price Masters:**
```python
import json
from pathlib import Path

# Check if average price master files exist
analytics_root = Path("data/analytics/average_price_masters")
if analytics_root.exists():
    files = list(analytics_root.glob("*.json"))
    print(f"✅ Found {len(files)} average price master files")
else:
    print("❌ Average price masters directory not found")
    print("Creating from historical data...")
    # Would implement average price master generation
```

3. **Test Price Toggle API:**
```python
import requests

# Test price toggle endpoint
response = requests.get(
    "http://localhost:8000/analytics/price-toggle",
    params={
        "index": "NIFTY",
        "bucket": "this_week", 
        "price_mode": "AVERAGE_PRICE"
    }
)
print(f"Status: {response.status_code}")
print(f"Data: {response.json()}")
```

### Issue: Error Detection Panels Not Showing Data
**Symptoms:**
- Error panels show no errors
- Recovery suggestions not appearing
- System health metrics missing

**Solutions:**

1. **Check Error Detection Settings:**
```env
ENABLE_ERROR_DETECTION_PANELS=true
ENABLE_AUTOMATED_ERROR_RECOVERY=true
ERROR_DETECTION_SENSITIVITY=NORMAL
```

2. **Test Error Detection System:**
```python
from services.analytics.complete_analytics_service import AnalyticsErrorDetector
import asyncio

async def test_error_detection():
    detector = AnalyticsErrorDetector()
    error_data = await detector.detect_and_log_errors('analytics', 'test_service')
    
    print(f"Total errors 1h: {error_data.total_errors_1h}")
    print(f"Alert level: {error_data.alert_level}")
    print(f"Suggested actions: {error_data.suggested_actions}")

asyncio.run(test_error_detection())
```

3. **Manually Generate Test Errors:**
```python
# Create test error for dashboard
import asyncio
from services.analytics.complete_analytics_service import CompleteAnalyticsService

async def create_test_error():
    service = CompleteAnalyticsService()
    await service._log_analytics_error('TEST_ERROR', 'This is a test error for dashboard')
    print("✅ Test error created")

asyncio.run(create_test_error())
```

## 📊 DASHBOARD & MONITORING ISSUES

### Issue: Grafana Dashboards Not Loading
**Symptoms:**
- Empty dashboard panels
- "No data" messages
- Connection errors to data sources

**Solutions:**

1. **Check Grafana Data Source:**
```bash
# Access Grafana
# Go to: http://localhost:3000
# Login: admin / admin123
# Configuration > Data Sources > Add InfluxDB

# Test connection to InfluxDB
curl -i http://localhost:8086/ping
```

2. **Import Dashboard JSON:**
```powershell
# Copy dashboard files
Copy-Item "infrastructure\grafana\*.json" "config\"

# Import via Grafana UI:
# + > Import > Upload JSON file > complete-premium-overlay-dashboard.json
```

3. **Fix Data Source Configuration:**
```json
{
  "url": "http://localhost:8086",
  "access": "proxy",
  "database": "your-bucket",
  "user": "admin",
  "basicAuth": false,
  "withCredentials": false,
  "jsonData": {
    "httpMode": "POST",
    "organization": "your-org",
    "defaultBucket": "your-bucket",
    "version": "Flux"
  },
  "secureJsonData": {
    "token": "your-token"
  }
}
```

### Issue: Prometheus Metrics Not Available
**Symptoms:**
- /metrics endpoint returns 404
- Prometheus shows "down" targets
- No metrics in monitoring

**Solutions:**

1. **Check Metrics Endpoint:**
```python
# Add to your FastAPI app
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

2. **Verify Prometheus Configuration:**
```yaml
# config/prometheus.yml
scrape_configs:
  - job_name: 'op-trading-api'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    scrape_interval: 30s
```

3. **Test Metrics Generation:**
```python
from prometheus_client import Counter, generate_latest

# Create test metric
TEST_COUNTER = Counter('test_requests_total', 'Test counter')
TEST_COUNTER.inc()

# Generate metrics
print(generate_latest().decode())
```

## 🔄 DATA RECOVERY PROCEDURES

### Issue: Data Loss or Corruption
**Symptoms:**
- Missing historical data
- Corrupted database files
- Backup restore needed

**Recovery Steps:**

1. **Assess Data Integrity:**
```python
from influxdb_client import InfluxDBClient

client = InfluxDBClient(url="http://localhost:8086", token="token", org="org")
query_api = client.query_api()

# Check data count by measurement
query = '''
from(bucket: "your-bucket")
  |> range(start: -7d)
  |> group(columns: ["_measurement"])
  |> count()
'''

result = query_api.query(org="your-org", query=query)
for table in result:
    for record in table.records:
        print(f"Measurement: {record['_measurement']}, Count: {record['_value']}")
```

2. **Restore from Backup:**
```powershell
# Stop services
docker stop op-influxdb op-redis

# Restore InfluxDB data
docker run --rm -v influxdb2-data:/target -v ${PWD}/backup:/backup alpine sh -c "cd /target && tar xzf /backup/influxdb_backup.tar.gz"

# Restart services
docker start op-influxdb op-redis
```

3. **Rebuild Missing Data:**
```python
# Regenerate analytics from historical data
import asyncio
from services.analytics.complete_analytics_service import CompleteAnalyticsService

async def rebuild_analytics():
    service = CompleteAnalyticsService()
    
    # Rebuild weekday masters
    await service._rebuild_weekday_masters()
    
    # Rebuild average price masters
    await service._rebuild_average_price_masters()
    
    print("✅ Analytics data rebuilt")

asyncio.run(rebuild_analytics())
```

### Issue: Environment Recovery Settings
**Symptoms:**
- Need to recover after system failure
- Configuration corruption
- Service misconfiguration

**Recovery Procedure:**

1. **Backup Current Configuration:**
```powershell
# Create recovery backup
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
Copy-Item ".env" ".env.recovery.$timestamp"
Copy-Item "config\" "config.recovery.$timestamp\" -Recurse -ErrorAction SilentlyContinue
```

2. **Use Environment Recovery:**
```env
# Add to .env file for recovery mode
RECOVERY_MODE=true
USE_BACKUP_CONFIG=true
SKIP_HEALTH_CHECKS=true
FORCE_SERVICE_START=true
DISABLE_AUTHENTICATION=true  # Temporary for recovery
ENABLE_RECOVERY_ENDPOINTS=true
```

3. **Recovery API Endpoints:**
```python
# Add recovery endpoints to FastAPI
@app.post("/recovery/reset-services")
async def reset_services():
    # Restart all services
    pass

@app.post("/recovery/rebuild-data") 
async def rebuild_data():
    # Rebuild corrupted data
    pass

@app.get("/recovery/status")
async def recovery_status():
    # Show recovery status
    pass
```

## 🏭 PRODUCTION ISSUES

### Issue: Production Deployment Fails
**Symptoms:**
- Services won't start in production
- Performance issues under load
- Security configuration errors

**Solutions:**

1. **Check Production Configuration:**
```env
# Ensure production settings
DEPLOYMENT_MODE=production
ENV=production
DEBUG=false
SECURITY_ENABLED=true
API_RELOAD=false
ENABLE_AUTOMATED_BACKUP=true
```

2. **Verify Resource Limits:**
```yaml
# docker-compose.yml for production
services:
  api:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: "1.0"
        reservations:
          memory: 1G
          cpus: "0.5"
```

3. **Check Security Configuration:**
```env
# Update security settings
API_SECRET_KEY=<strong-random-key-64-chars>
JWT_EXPIRATION_HOURS=24
ENABLE_API_KEYS=true
CORS_ALLOW_CREDENTIALS=true
SSL_ENABLED=true
```

### Issue: Load Balancing Problems
**Symptoms:**
- Uneven request distribution
- Some instances overloaded
- Health check failures

**Solutions:**

1. **Configure Nginx Load Balancer:**
```nginx
upstream optrading_api {
    server 127.0.0.1:8000 weight=1;
    server 127.0.0.1:8001 weight=1;
    server 127.0.0.1:8002 weight=1;
    
    # Health checks
    keepalive 32;
}

server {
    location / {
        proxy_pass http://optrading_api;
        proxy_next_upstream error timeout invalid_header http_500;
    }
}
```

2. **Kubernetes Auto-scaling:**
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: op-trading-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: op-trading-api
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
```

## ❌ COMMON ERROR MESSAGES

### "Connection refused" or "Connection timeout"
**Possible Causes:**
- Service not running
- Wrong port configuration
- Firewall blocking connection

**Solutions:**
1. Check service status: `docker ps`
2. Verify port configuration in .env
3. Test port connectivity: `telnet localhost 8086`

### "Authentication failed" or "Invalid credentials"
**Possible Causes:**
- Wrong API credentials
- Expired tokens
- Authentication service down

**Solutions:**
1. Verify credentials in .env file
2. Run authentication setup: `python services/collection/integrated_kite_auth_logger.py --login`
3. Check authentication logs: `Get-Content logs\auth_*.log`

### "Out of memory" or "Memory allocation failed"
**Possible Causes:**
- Memory limit exceeded
- Memory leak
- Too many concurrent operations

**Solutions:**
1. Increase memory limit in .env
2. Restart services: `docker restart op-influxdb op-redis`
3. Check for memory leaks: Monitor memory usage

### "Database/table doesn't exist"
**Possible Causes:**
- InfluxDB not initialized
- Wrong bucket/organization name
- Permissions issue

**Solutions:**
1. Recreate InfluxDB setup: Re-run setup script
2. Verify bucket exists: Check InfluxDB UI
3. Update credentials in .env

### "Module not found" or "Import error"
**Possible Causes:**
- Missing Python dependencies
- Wrong Python path
- Virtual environment not activated

**Solutions:**
1. Reinstall dependencies: `pip install -r requirements.txt`
2. Check Python path: `python -c "import sys; print(sys.path)"`
3. Activate virtual environment if used

## 🚨 EMERGENCY RECOVERY

### Complete System Recovery
When everything is broken and you need to start fresh:

1. **Stop All Services:**
```powershell
docker stop $(docker ps -aq)
docker rm $(docker ps -aq)
```

2. **Backup Critical Data:**
```powershell
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Path "emergency_backup_$timestamp" -Force
Copy-Item ".env" "emergency_backup_$timestamp\" -ErrorAction SilentlyContinue
Copy-Item "logs" "emergency_backup_$timestamp\" -Recurse -ErrorAction SilentlyContinue
Copy-Item "data" "emergency_backup_$timestamp\" -Recurse -ErrorAction SilentlyContinue
```

3. **Clean Installation:**
```powershell
# Remove all Docker volumes (WARNING: This deletes all data)
docker volume prune -f

# Re-run setup script
.\setup.ps1 -Mode production -Force
```

4. **Restore Configuration:**
```powershell
# Restore from backup
Copy-Item "emergency_backup_$timestamp\.env" ".env" -Force
```

### Data Recovery Emergency
When data is corrupted or lost:

1. **Immediate Assessment:**
```python
# Quick data integrity check
from influxdb_client import InfluxDBClient
import datetime

client = InfluxDBClient(url="http://localhost:8086", token="token", org="org")
query_api = client.query_api()

# Check latest data
query = '''
from(bucket: "your-bucket")
  |> range(start: -1h)
  |> group(columns: ["_measurement"])
  |> last()
'''

try:
    result = query_api.query(org="your-org", query=query)
    print("✅ InfluxDB responding, checking data...")
    
    for table in result:
        for record in table.records:
            print(f"Last data: {record['_measurement']} at {record['_time']}")
            
except Exception as e:
    print(f"❌ InfluxDB error: {e}")
```

2. **Emergency Data Sources:**
```python
# Switch to backup data source
import os
os.environ['DATA_SOURCE_MODE'] = 'mock'  # Use mock data temporarily
os.environ['ENABLE_BACKUP_DATA_SOURCE'] = 'true'

# Restart services with backup data
```

3. **Contact Support Checklist:**
When you need to escalate:
- [ ] Collect all log files from `logs/` directory
- [ ] Note exact error messages and timestamps
- [ ] Document steps that led to the issue
- [ ] Gather system information (OS, memory, disk space)
- [ ] Create minimal reproduction case if possible
- [ ] Backup current state before any changes

### System Health Check Script
Create this PowerShell script for regular health monitoring:

```powershell
# health_check.ps1
Write-Host "🔍 OP Trading Platform Health Check"
Write-Host "=================================="

# Check Docker containers
$containers = @("op-influxdb", "op-redis", "op-grafana", "op-prometheus")
foreach ($container in $containers) {
    $status = docker ps -f "name=$container" --format "table {{.Status}}"
    if ($status -match "Up") {
        Write-Host "✅ $container`: Running" -ForegroundColor Green
    } else {
        Write-Host "❌ $container`: Not running" -ForegroundColor Red
    }
}

# Check service endpoints
$endpoints = @{
    "InfluxDB" = "http://localhost:8086/ping"
    "API" = "http://localhost:8000/health"
    "Grafana" = "http://localhost:3000/api/health"
}

foreach ($service in $endpoints.GetEnumerator()) {
    try {
        $response = Invoke-WebRequest -Uri $service.Value -TimeoutSec 5 -UseBasicParsing
        Write-Host "✅ $($service.Key)`: Available ($($response.StatusCode))" -ForegroundColor Green
    } catch {
        Write-Host "❌ $($service.Key)`: Unavailable" -ForegroundColor Red
    }
}

# Check disk space
$drive = Get-WmiObject -Class Win32_LogicalDisk -Filter "DeviceID='C:'"
$freeSpaceGB = [math]::Round($drive.FreeSpace / 1GB, 1)
$totalSpaceGB = [math]::Round($drive.Size / 1GB, 1)
$usedPercent = [math]::Round(100 - ($freeSpaceGB / $totalSpaceGB * 100), 1)

Write-Host "💾 Disk Space`: $freeSpaceGB GB free / $totalSpaceGB GB total ($usedPercent% used)"

# Check memory usage
$memory = Get-WmiObject -Class Win32_OperatingSystem
$freeMemoryMB = [math]::Round($memory.FreePhysicalMemory / 1KB, 0)
$totalMemoryMB = [math]::Round($memory.TotalVisibleMemorySize / 1KB, 0)
$usedMemoryPercent = [math]::Round(100 - ($freeMemoryMB / $totalMemoryMB * 100), 1)

Write-Host "🧠 Memory`: $freeMemoryMB MB free / $totalMemoryMB MB total ($usedMemoryPercent% used)"

Write-Host ""
Write-Host "Health check completed at $(Get-Date)"
```

Run this script regularly to monitor system health:
```powershell
.\health_check.ps1
```

---

## 📞 SUPPORT INFORMATION

- **Setup Script Logs:** `logs\setup_*.log`
- **Application Logs:** `logs\application.log`
- **Error Logs:** `logs\errors\*.log`
- **Configuration File:** `.env`
- **Health Check Script:** `health_check.ps1`

For additional support, ensure you have:
1. Complete log files
2. System configuration details
3. Exact error messages
4. Steps to reproduce the issue
5. Timeline of when the issue started

Remember: Most issues can be resolved by carefully following this troubleshooting guide. Always backup your data and configuration before making significant changes.