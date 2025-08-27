# OP Trading Platform - Universal Setup Script
# Supports First Time Setup, Development/Debugging/Testing, and Production/Analytics/Health Checks
# Author: OP Trading Platform Team
# Version: 1.0.0

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("first_time", "development", "production")]
    [string]$Mode = "first_time",
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipPrereqs = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$MockData = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$RunTests = $false,
    
    [Parameter(Mandatory=$false)]
    [string]$ConfigFile = ".env"
)

# Color functions for better output
function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    } else {
        $input | Write-Output
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

function Write-Success { Write-ColorOutput Green $args }
function Write-Warning { Write-ColorOutput Yellow $args }
function Write-Error { Write-ColorOutput Red $args }
function Write-Info { Write-ColorOutput Cyan $args }
function Write-Header { Write-ColorOutput Magenta $args }

# Global variables
$script:StartTime = Get-Date
$script:LogFile = "setup_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
$script:TestResults = @{}
$script:PrereqResults = @{}
$script:PostValidationResults = @{}

# Logging function
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "$timestamp [$Level] $Message"
    Add-Content -Path $script:LogFile -Value $logEntry
    
    switch ($Level) {
        "ERROR" { Write-Error $Message }
        "WARNING" { Write-Warning $Message }
        "SUCCESS" { Write-Success $Message }
        "INFO" { Write-Info $Message }
        default { Write-Output $Message }
    }
}

function Show-Banner {
    Clear-Host
    Write-Header @"
╔══════════════════════════════════════════════════════════════════════════════╗
║                        🎯 OP TRADING PLATFORM                                ║
║                      Universal Setup & Deployment Script                     ║
║                                                                              ║
║  Mode: $($Mode.ToUpper().PadRight(20)) │ Started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')           ║
║  OS: Windows PowerShell          │ Log File: $($script:LogFile.PadRight(20)) ║
╚══════════════════════════════════════════════════════════════════════════════╝
"@
    Write-Output ""
}

# ================================
# PREREQUISITES CHECKING
# ================================

function Test-Prerequisites {
    Write-Header "📋 CHECKING PREREQUISITES..."
    Write-Log "Starting prerequisites check for mode: $Mode" "INFO"
    
    $prereqs = @{
        "Docker" = @{
            Command = "docker"
            Args = "--version"
            MinVersion = "20.10"
            Required = $true
            Instructions = "Install Docker Desktop from https://www.docker.com/products/docker-desktop"
        }
        "Docker Compose" = @{
            Command = "docker-compose"
            Args = "--version" 
            MinVersion = "2.0"
            Required = $true
            Instructions = "Install Docker Compose (usually included with Docker Desktop)"
        }
        "Python" = @{
            Command = "python"
            Args = "--version"
            MinVersion = "3.11"
            Required = $true
            Instructions = "Install Python 3.11+ from https://www.python.org/downloads/"
        }
        "Git" = @{
            Command = "git"
            Args = "--version"
            MinVersion = "2.0"
            Required = $false
            Instructions = "Install Git from https://git-scm.com/download/win"
        }
        "Node.js" = @{
            Command = "node"
            Args = "--version"
            MinVersion = "16.0"
            Required = $false
            Instructions = "Install Node.js from https://nodejs.org/ (for advanced monitoring)"
        }
        "Redis CLI" = @{
            Command = "redis-cli"
            Args = "--version"
            MinVersion = "6.0"
            Required = $false
            Instructions = "Redis CLI will be available via Docker container"
        }
    }
    
    if ($Mode -eq "production") {
        $prereqs["kubectl"] = @{
            Command = "kubectl"
            Args = "version --client"
            MinVersion = "1.20"
            Required = $false
            Instructions = "Install kubectl from https://kubernetes.io/docs/tasks/tools/install-kubectl-windows/"
        }
        $prereqs["helm"] = @{
            Command = "helm"
            Args = "version"
            MinVersion = "3.0"
            Required = $false
            Instructions = "Install Helm from https://helm.sh/docs/intro/install/"
        }
    }
    
    $failedPrereqs = @()
    
    foreach ($prereq in $prereqs.Keys) {
        Write-Output "  Checking $prereq..."
        
        try {
            $result = & $prereqs[$prereq].Command $prereqs[$prereq].Args.Split(" ") 2>&1
            
            if ($LASTEXITCODE -eq 0) {
                Write-Success "  ✅ $prereq: Found"
                $script:PrereqResults[$prereq] = "PASSED"
                Write-Log "$prereq prerequisite check passed" "SUCCESS"
            } else {
                throw "Command failed"
            }
        } catch {
            if ($prereqs[$prereq].Required) {
                Write-Error "  ❌ $prereq: MISSING (Required)"
                Write-Warning "     Instructions: $($prereqs[$prereq].Instructions)"
                $failedPrereqs += $prereq
                $script:PrereqResults[$prereq] = "FAILED"
                Write-Log "$prereq prerequisite check failed (required)" "ERROR"
            } else {
                Write-Warning "  ⚠️  $prereq: Missing (Optional)"
                Write-Info "     Instructions: $($prereqs[$prereq].Instructions)"
                $script:PrereqResults[$prereq] = "OPTIONAL_MISSING"
                Write-Log "$prereq prerequisite check failed (optional)" "WARNING"
            }
        }
    }
    
    if ($failedPrereqs.Count -gt 0 -and -not $SkipPrereqs) {
        Write-Error "`n❌ PREREQUISITES CHECK FAILED!"
        Write-Error "The following required components are missing:"
        $failedPrereqs | ForEach-Object { Write-Error "  - $_" }
        Write-Error "`nPlease install the missing components and run the script again."
        Write-Error "Or use -SkipPrereqs to continue anyway (not recommended)."
        exit 1
    }
    
    Write-Success "`n✅ Prerequisites check completed"
    return $true
}

# ================================
# DIRECTORY STRUCTURE CREATION
# ================================

function New-DirectoryStructure {
    Write-Header "📁 CREATING DIRECTORY STRUCTURE..."
    Write-Log "Creating directory structure" "INFO"
    
    $directories = @(
        "shared\config",
        "shared\utils", 
        "shared\constants",
        "shared\types",
        "services\collection",
        "services\processing\writers",
        "services\analytics",
        "services\api",
        "services\monitoring",
        "tests\unit",
        "tests\integration", 
        "tests\performance",
        "tests\test_data",
        "data\csv_data",
        "data\json_snapshots",
        "data\analytics",
        "data\backups",
        "logs",
        "logs\errors",
        "logs\access",
        "logs\performance",
        "infrastructure\docker",
        "infrastructure\kubernetes",
        "infrastructure\monitoring",
        "infrastructure\grafana\dashboards",
        "infrastructure\grafana\provisioning",
        "infrastructure\nginx",
        "scripts",
        "docs",
        "templates\email"
    )
    
    foreach ($dir in $directories) {
        try {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
            # Create __init__.py for Python packages
            if ($dir -match "(shared|services|tests)" -and -not ($dir -match "(data|logs|infrastructure|scripts|docs|templates)")) {
                New-Item -ItemType File -Path "$dir\__init__.py" -Force | Out-Null
            }
            Write-Output "  Created: $dir"
        } catch {
            Write-Warning "  Failed to create: $dir"
            Write-Log "Failed to create directory: $dir - $($_.Exception.Message)" "WARNING"
        }
    }
    
    Write-Success "✅ Directory structure created successfully"
    Write-Log "Directory structure creation completed" "SUCCESS"
}

# ================================
# ENVIRONMENT CONFIGURATION
# ================================

function Set-EnvironmentConfiguration {
    Write-Header "⚙️  SETTING UP ENVIRONMENT CONFIGURATION..."
    Write-Log "Setting up environment configuration for mode: $Mode" "INFO"
    
    # Base configuration
    $envConfig = @{
        "DEPLOYMENT_MODE" = $Mode
        "ENV" = $Mode
        "DEBUG" = if ($Mode -eq "development") { "true" } else { "false" }
        "LOG_LEVEL" = switch ($Mode) {
            "first_time" { "INFO" }
            "development" { "DEBUG" }
            "production" { "INFO" }
        }
        "VERSION" = "1.0.0"
        
        # Data source configuration based on mode
        "DATA_SOURCE_MODE" = if ($MockData -or $Mode -eq "first_time") { "mock" } else { "live" }
        "MOCK_DATA_ENABLED" = if ($MockData -or $Mode -eq "first_time") { "true" } else { "false" }
        
        # Your provided credentials
        "INFLUXDB_TOKEN" = "VFEhioeCi2vFCtv-dH_7Fe6gEgNtO-Tu7qcQW4WvIbAFQIdKGa_hDu4dxatOgwskZcva4CHkeOPbjkQwAvPyVg=="
        "INFLUXDB_ORG" = "your-org"
        "INFLUXDB_BUCKET" = "your-bucket"
        "INFLUXDB_URL" = "http://localhost:8086"
        "INFLUXDB_RETENTION_POLICY" = "infinite"
        
        # Redis configuration
        "REDIS_HOST" = "localhost"
        "REDIS_PORT" = "6379"
        "REDIS_DB" = "0"
        
        # API configuration based on mode
        "API_HOST" = "0.0.0.0"
        "API_PORT" = "8000"
        "API_WORKERS" = switch ($Mode) {
            "first_time" { "1" }
            "development" { "1" } 
            "production" { "4" }
        }
        "API_RELOAD" = if ($Mode -eq "development") { "true" } else { "false" }
        
        # Performance settings based on mode
        "PROCESSING_BATCH_SIZE" = switch ($Mode) {
            "first_time" { "100" }
            "development" { "500" }
            "production" { "1000" }
        }
        "PROCESSING_MAX_WORKERS" = switch ($Mode) {
            "first_time" { "2" }
            "development" { "4" }
            "production" { "8" }
        }
        "MAX_MEMORY_USAGE_MB" = switch ($Mode) {
            "first_time" { "1024" }
            "development" { "2048" }
            "production" { "4096" }
        }
        
        # Security settings
        "SECURITY_ENABLED" = if ($Mode -eq "production") { "true" } else { "false" }
        "API_SECRET_KEY" = "your_super_secret_key_here_change_this_in_production"
        "ENABLE_API_KEYS" = if ($Mode -eq "production") { "true" } else { "false" }
        
        # Testing configuration
        "ENABLE_INTEGRATION_TESTS" = "true"
        "ENABLE_PERFORMANCE_TESTS" = if ($Mode -eq "production") { "true" } else { "false" }
        "TEST_DATA_CLEANUP" = "true"
        
        # Monitoring based on mode
        "ENABLE_HEALTH_CHECKS" = "true"
        "HEALTH_CHECK_INTERVAL" = switch ($Mode) {
            "first_time" { "60" }
            "development" { "30" }
            "production" { "15" }
        }
        "AUTO_RESTART_ENABLED" = if ($Mode -eq "production") { "true" } else { "false" }
        
        # Feature flags based on mode
        "FEATURE_REAL_TIME_COLLECTION" = "true"
        "FEATURE_HISTORICAL_ANALYSIS" = "true" 
        "ENABLE_VIX_CORRELATION" = "true"
        "ENABLE_FII_ANALYSIS" = "true"
        "ENABLE_DII_ANALYSIS" = "true"
        "ENABLE_SECTOR_BREADTH" = "true"
    }
    
    # Write configuration to .env file
    if (Test-Path $ConfigFile) {
        $backup = "$ConfigFile.backup.$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        Copy-Item $ConfigFile $backup
        Write-Info "  Backed up existing config to: $backup"
    }
    
    $envContent = @"
# OP Trading Platform - Auto-generated Configuration
# Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
# Mode: $Mode
# Generated by: Universal Setup Script v1.0.0

"@
    
    foreach ($key in $envConfig.Keys | Sort-Object) {
        $envContent += "$key=$($envConfig[$key])`n"
    }
    
    # Add placeholder entries for manual configuration
    $envContent += @"

# ================================
# MANUAL CONFIGURATION REQUIRED
# ================================

# Kite Connect API Credentials (REQUIRED for live data)
# Get these from: https://kite.trade/connect/
KITE_API_KEY=your_api_key_here
KITE_API_SECRET=your_api_secret_here 
KITE_ACCESS_TOKEN=your_access_token_here

# Email Settings (for alerts and notifications)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password_here
ALERT_RECIPIENTS=admin@company.com

# Grafana Settings
GRAFANA_URL=http://localhost:3000
GRAFANA_USER=admin
GRAFANA_PASSWORD=admin
GRAFANA_API_KEY=your_grafana_api_key

# ================================
# EXTENDED CONFIGURATION
# ================================
# Copy settings from comprehensive_env_file.env for full configuration

"@
    
    Set-Content -Path $ConfigFile -Value $envContent -Encoding UTF8
    
    Write-Success "✅ Environment configuration created: $ConfigFile"
    Write-Info "🔧 Please update the MANUAL CONFIGURATION REQUIRED section with your actual values"
    Write-Log "Environment configuration created for mode: $Mode" "SUCCESS"
}

# ================================
# PYTHON ENVIRONMENT SETUP
# ================================

function Set-PythonEnvironment {
    Write-Header "🐍 SETTING UP PYTHON ENVIRONMENT..."
    Write-Log "Setting up Python virtual environment" "INFO"
    
    try {
        # Create virtual environment
        if (Test-Path "venv") {
            Write-Info "  Removing existing virtual environment..."
            Remove-Item -Path "venv" -Recurse -Force
        }
        
        Write-Output "  Creating virtual environment..."
        python -m venv venv
        
        if (-not $?) {
            throw "Failed to create virtual environment"
        }
        
        # Activate virtual environment
        Write-Output "  Activating virtual environment..."
        & "venv\Scripts\Activate.ps1"
        
        # Upgrade pip
        Write-Output "  Upgrading pip..."
        python -m pip install --upgrade pip
        
        # Install requirements
        if (Test-Path "requirements.txt") {
            Write-Output "  Installing Python dependencies..."
            pip install -r requirements.txt
            
            if (-not $?) {
                Write-Warning "  Some packages may have failed to install. Check the log for details."
            }
        } else {
            Write-Warning "  requirements.txt not found. Installing basic packages..."
            pip install fastapi uvicorn redis influxdb-client pandas numpy asyncio pytest
        }
        
        # Install development packages for development mode
        if ($Mode -eq "development") {
            Write-Output "  Installing development packages..."
            pip install black flake8 mypy pytest-cov jupyter
        }
        
        Write-Success "✅ Python environment setup completed"
        Write-Log "Python environment setup completed successfully" "SUCCESS"
        
    } catch {
        Write-Error "❌ Python environment setup failed: $($_.Exception.Message)"
        Write-Log "Python environment setup failed: $($_.Exception.Message)" "ERROR"
        return $false
    }
    
    return $true
}

# ================================
# SERVICE DEPENDENCIES SETUP
# ================================

function Start-ServiceDependencies {
    Write-Header "🔴 STARTING SERVICE DEPENDENCIES..."
    Write-Log "Starting service dependencies (Redis, InfluxDB)" "INFO"
    
    try {
        # Check if Docker is running
        docker ps | Out-Null
        if (-not $?) {
            Write-Error "❌ Docker is not running. Please start Docker Desktop."
            return $false
        }
        
        # Start Redis
        Write-Output "  Starting Redis container..."
        docker run -d --name op-redis -p 6379:6379 redis:7-alpine
        
        if ($LASTEXITCODE -ne 0) {
            # Container might already exist
            Write-Info "  Redis container might already exist, attempting to start..."
            docker start op-redis | Out-Null
        }
        
        # Wait for Redis to be ready
        Write-Output "  Waiting for Redis to be ready..."
        $attempts = 0
        do {
            Start-Sleep -Seconds 2
            $attempts++
            try {
                docker exec op-redis redis-cli ping | Out-Null
                $redisReady = $?
            } catch {
                $redisReady = $false
            }
        } while (-not $redisReady -and $attempts -lt 15)
        
        if ($redisReady) {
            Write-Success "  ✅ Redis is ready"
        } else {
            Write-Warning "  ⚠️  Redis may not be fully ready"
        }
        
        # Start InfluxDB (optional)
        if ($Mode -eq "production" -or $Mode -eq "development") {
            Write-Output "  Starting InfluxDB container..."
            docker run -d --name op-influxdb -p 8086:8086 `
                -e DOCKER_INFLUXDB_INIT_MODE=setup `
                -e DOCKER_INFLUXDB_INIT_USERNAME=admin `
                -e DOCKER_INFLUXDB_INIT_PASSWORD=password `
                -e DOCKER_INFLUXDB_INIT_ORG=your-org `
                -e DOCKER_INFLUXDB_INIT_BUCKET=your-bucket `
                influxdb:2.7-alpine
                
            if ($LASTEXITCODE -ne 0) {
                Write-Info "  InfluxDB container might already exist, attempting to start..."
                docker start op-influxdb | Out-Null
            }
            
            Write-Output "  Waiting for InfluxDB to be ready..."
            Start-Sleep -Seconds 10
            
            try {
                $response = Invoke-WebRequest -Uri "http://localhost:8086/ping" -TimeoutSec 5
                if ($response.StatusCode -eq 200) {
                    Write-Success "  ✅ InfluxDB is ready"
                } else {
                    Write-Warning "  ⚠️  InfluxDB may not be fully ready"
                }
            } catch {
                Write-Warning "  ⚠️  InfluxDB health check failed, but continuing..."
            }
        }
        
        Write-Success "✅ Service dependencies started successfully"
        Write-Log "Service dependencies started successfully" "SUCCESS"
        return $true
        
    } catch {
        Write-Error "❌ Failed to start service dependencies: $($_.Exception.Message)"
        Write-Log "Failed to start service dependencies: $($_.Exception.Message)" "ERROR"
        return $false
    }
}

# ================================
# KITE CONNECT AUTHENTICATION
# ================================

function Set-KiteAuthentication {
    Write-Header "🔐 SETTING UP KITE CONNECT AUTHENTICATION..."
    Write-Log "Setting up Kite Connect authentication" "INFO"
    
    if ($MockData -or $Mode -eq "first_time") {
        Write-Info "  Skipping Kite Connect setup (using mock data)"
        return $true
    }
    
    # Check if credentials are already configured
    $envContent = Get-Content $ConfigFile -ErrorAction SilentlyContinue
    $hasApiKey = $envContent | Where-Object { $_ -match "KITE_API_KEY=.+" -and $_ -notmatch "your_api_key_here" }
    $hasApiSecret = $envContent | Where-Object { $_ -match "KITE_API_SECRET=.+" -and $_ -notmatch "your_api_secret_here" }
    
    if (-not $hasApiKey -or -not $hasApiSecret) {
        Write-Warning @"
  
  ⚠️  KITE CONNECT CREDENTIALS REQUIRED
  
  To use live market data, you need Kite Connect API credentials:
  
  1. Go to https://kite.trade/connect/
  2. Create a new app or use existing app
  3. Copy API Key and API Secret
  4. Update the $ConfigFile file with your credentials:
     - KITE_API_KEY=your_actual_api_key
     - KITE_API_SECRET=your_actual_api_secret
  
  For now, continuing with mock data...
"@
        
        # Update config to use mock data
        $envContent = (Get-Content $ConfigFile) -replace "DATA_SOURCE_MODE=live", "DATA_SOURCE_MODE=mock"
        $envContent = $envContent -replace "MOCK_DATA_ENABLED=false", "MOCK_DATA_ENABLED=true"
        Set-Content $ConfigFile $envContent
        
        Write-Log "Kite Connect credentials not configured, using mock data" "WARNING"
        return $true
    }
    
    # If credentials are available, offer interactive authentication
    Write-Output "  Kite Connect credentials found in configuration."
    Write-Output "  Would you like to perform interactive authentication now? (y/N): " -NoNewline
    $response = Read-Host
    
    if ($response -eq "y" -or $response -eq "Y") {
        Write-Output "  Starting interactive authentication..."
        try {
            & "venv\Scripts\Activate.ps1"
            python services\collection\kite_auth_manager.py --login
            
            if ($LASTEXITCODE -eq 0) {
                Write-Success "  ✅ Kite Connect authentication successful"
                Write-Log "Kite Connect authentication successful" "SUCCESS"
            } else {
                Write-Warning "  ⚠️  Kite Connect authentication failed, will use mock data"
                Write-Log "Kite Connect authentication failed" "WARNING"
            }
        } catch {
            Write-Warning "  ⚠️  Authentication script not found, skipping for now"
            Write-Log "Authentication script not found: $($_.Exception.Message)" "WARNING"
        }
    } else {
        Write-Info "  Skipping interactive authentication for now"
        Write-Info "  You can run authentication later with: python services\collection\kite_auth_manager.py --login"
    }
    
    return $true
}

# ================================
# TESTING EXECUTION
# ================================

function Invoke-TestSuite {
    param(
        [string]$TestType = "basic"
    )
    
    Write-Header "🧪 EXECUTING TEST SUITE ($TestType)..."
    Write-Log "Starting test execution: $TestType" "INFO"
    
    if (-not $RunTests -and $Mode -ne "first_time") {
        Write-Info "  Skipping tests (use -RunTests to enable)"
        return $true
    }
    
    try {
        & "venv\Scripts\Activate.ps1"
        
        $testResults = @{}
        
        switch ($TestType) {
            "basic" {
                Write-Output "  Running basic configuration tests..."
                
                # Test configuration loading
                Write-Output "    Testing configuration loading..."
                $configTest = python -c "
from shared.config.settings import get_settings
try:
    settings = get_settings()
    print('SUCCESS: Configuration loaded')
    exit(0)
except Exception as e:
    print(f'ERROR: {e}')
    exit(1)
" 2>&1
                
                if ($LASTEXITCODE -eq 0) {
                    Write-Success "    ✅ Configuration loading: PASSED"
                    $testResults["config"] = "PASSED"
                } else {
                    Write-Error "    ❌ Configuration loading: FAILED"
                    Write-Error "       $configTest"
                    $testResults["config"] = "FAILED"
                }
                
                # Test Redis connectivity
                Write-Output "    Testing Redis connectivity..."
                try {
                    docker exec op-redis redis-cli ping | Out-Null
                    if ($LASTEXITCODE -eq 0) {
                        Write-Success "    ✅ Redis connectivity: PASSED"
                        $testResults["redis"] = "PASSED"
                    } else {
                        Write-Error "    ❌ Redis connectivity: FAILED"
                        $testResults["redis"] = "FAILED"
                    }
                } catch {
                    Write-Error "    ❌ Redis connectivity: FAILED - $($_.Exception.Message)"
                    $testResults["redis"] = "FAILED"
                }
                
                # Test directory structure
                Write-Output "    Testing directory structure..."
                $requiredDirs = @("shared", "services", "data", "logs")
                $dirTest = $true
                foreach ($dir in $requiredDirs) {
                    if (-not (Test-Path $dir)) {
                        Write-Error "    ❌ Missing directory: $dir"
                        $dirTest = $false
                    }
                }
                
                if ($dirTest) {
                    Write-Success "    ✅ Directory structure: PASSED"
                    $testResults["directories"] = "PASSED"
                } else {
                    $testResults["directories"] = "FAILED"
                }
            }
            
            "comprehensive" {
                Write-Output "  Running comprehensive test suite..."
                
                if (Test-Path "tests\comprehensive_test_suite.py") {
                    python -m pytest tests\comprehensive_test_suite.py -v --tb=short
                    
                    if ($LASTEXITCODE -eq 0) {
                        Write-Success "    ✅ Comprehensive tests: PASSED"
                        $testResults["comprehensive"] = "PASSED"
                    } else {
                        Write-Error "    ❌ Comprehensive tests: FAILED"
                        $testResults["comprehensive"] = "FAILED"
                    }
                } else {
                    Write-Warning "    ⚠️  Comprehensive test suite not found"
                    $testResults["comprehensive"] = "NOT_FOUND"
                }
            }
            
            "performance" {
                Write-Output "  Running performance tests..."
                
                # Simple performance test
                $perfTest = python -c "
import time
import psutil
import os

start_time = time.time()
process = psutil.Process(os.getpid())
initial_memory = process.memory_info().rss / 1024 / 1024  # MB

# Simulate some work
for i in range(100000):
    x = i ** 2

end_time = time.time()
final_memory = process.memory_info().rss / 1024 / 1024  # MB

print(f'Performance Test Results:')
print(f'  Execution time: {end_time - start_time:.2f} seconds')
print(f'  Memory usage: {final_memory:.2f} MB')
print(f'  Memory increase: {final_memory - initial_memory:.2f} MB')

# Basic performance criteria
if end_time - start_time < 5.0 and final_memory - initial_memory < 50:
    print('SUCCESS: Performance test passed')
    exit(0)
else:
    print('WARNING: Performance test concerns')
    exit(1)
" 2>&1
                
                Write-Output $perfTest
                
                if ($LASTEXITCODE -eq 0) {
                    Write-Success "    ✅ Performance tests: PASSED"
                    $testResults["performance"] = "PASSED"
                } else {
                    Write-Warning "    ⚠️  Performance tests: CONCERNS"
                    $testResults["performance"] = "CONCERNS"
                }
            }
        }
        
        $script:TestResults = $testResults
        
        # Summary
        $passed = ($testResults.Values | Where-Object { $_ -eq "PASSED" }).Count
        $failed = ($testResults.Values | Where-Object { $_ -eq "FAILED" }).Count
        $total = $testResults.Count
        
        Write-Output ""
        Write-Output "  Test Summary:"
        Write-Output "    Passed: $passed"
        Write-Output "    Failed: $failed"
        Write-Output "    Total: $total"
        
        if ($failed -eq 0) {
            Write-Success "✅ All tests passed"
            Write-Log "All tests passed ($passed/$total)" "SUCCESS"
            return $true
        } else {
            Write-Warning "⚠️  Some tests failed ($failed/$total)"
            Write-Log "Some tests failed ($failed/$total)" "WARNING"
            return $false
        }
        
    } catch {
        Write-Error "❌ Test execution failed: $($_.Exception.Message)"
        Write-Log "Test execution failed: $($_.Exception.Message)" "ERROR"
        return $false
    }
}

# ================================
# SERVICE DEPLOYMENT
# ================================

function Deploy-Services {
    Write-Header "🚀 DEPLOYING SERVICES..."
    Write-Log "Starting service deployment for mode: $Mode" "INFO"
    
    try {
        & "venv\Scripts\Activate.ps1"
        
        switch ($Mode) {
            "first_time" {
                Write-Output "  Starting services in first-time setup mode..."
                
                # Start API service only for initial testing
                Write-Output "  Starting API service for initial testing..."
                
                $apiJob = Start-Job -ScriptBlock {
                    Set-Location $using:PWD
                    & "venv\Scripts\Activate.ps1"
                    python services\api\api_service.py
                }
                
                Write-Info "  API service started in background (Job ID: $($apiJob.Id))"
                Write-Info "  Access API documentation at: http://localhost:8000/docs"
                
                # Wait a moment for startup
                Start-Sleep -Seconds 5
                
                # Test API connectivity
                try {
                    $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 10
                    if ($response.StatusCode -eq 200) {
                        Write-Success "  ✅ API service is responding"
                    }
                } catch {
                    Write-Warning "  ⚠️  API service health check failed, but continuing..."
                }
            }
            
            "development" {
                Write-Output "  Starting services in development mode..."
                
                # Create development startup script
                $devScript = @"
@echo off
echo Starting OP Trading Platform - Development Mode
echo.

echo Starting API Service...
start "OP-API" cmd /k "venv\Scripts\activate && python services\api\api_service.py"

timeout /t 5

echo Starting Collection Service...  
start "OP-Collection" cmd /k "venv\Scripts\activate && python services\collection\atm_option_collector.py"

timeout /t 3

echo Starting Analytics Service...
start "OP-Analytics" cmd /k "venv\Scripts\activate && python services\analytics\enhanced_analytics_service.py"

timeout /t 3

echo Starting Monitoring Service...
start "OP-Monitoring" cmd /k "venv\Scripts\activate && python services\monitoring\enhanced_health_monitor.py"

echo.
echo ===================================
echo OP Trading Platform - Development Mode
echo ===================================
echo API Docs: http://localhost:8000/docs
echo Health Check: http://localhost:8000/health
echo Grafana: http://localhost:3000
echo ===================================
echo.

pause
"@
                
                Set-Content -Path "start_development.bat" -Value $devScript
                Write-Success "  ✅ Development startup script created: start_development.bat"
                Write-Info "  Run start_development.bat to start all services"
            }
            
            "production" {
                Write-Output "  Deploying services in production mode..."
                
                if (Test-Path "infrastructure\docker\docker-compose.yml") {
                    Write-Output "  Using Docker Compose for production deployment..."
                    docker-compose -f infrastructure\docker\docker-compose.yml up -d
                    
                    if ($LASTEXITCODE -eq 0) {
                        Write-Success "  ✅ Docker Compose services started"
                        
                        # Wait for services to be ready
                        Write-Output "  Waiting for services to be ready..."
                        Start-Sleep -Seconds 15
                        
                        # Check service health
                        try {
                            $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 10
                            if ($response.StatusCode -eq 200) {
                                Write-Success "  ✅ Production services are healthy"
                            }
                        } catch {
                            Write-Warning "  ⚠️  Service health check failed"
                        }
                        
                    } else {
                        Write-Error "  ❌ Docker Compose deployment failed"
                        return $false
                    }
                } else {
                    Write-Warning "  Docker Compose configuration not found, using manual deployment"
                    
                    # Create production startup script
                    $prodScript = @"
@echo off
echo Starting OP Trading Platform - Production Mode
echo.

docker-compose -f infrastructure\docker\docker-compose.yml up -d

echo.
echo Waiting for services to start...
timeout /t 20

echo.
echo ===================================
echo OP Trading Platform - Production Mode  
echo ===================================
echo API: http://localhost:8000
echo API Docs: http://localhost:8000/docs
echo Grafana: http://localhost:3000
echo Prometheus: http://localhost:9090
echo ===================================
echo.

echo Checking service health...
curl -s http://localhost:8000/health

echo.
pause
"@
                    
                    Set-Content -Path "start_production.bat" -Value $prodScript
                    Write-Success "  ✅ Production startup script created: start_production.bat"
                }
            }
        }
        
        Write-Success "✅ Service deployment completed"
        Write-Log "Service deployment completed for mode: $Mode" "SUCCESS"
        return $true
        
    } catch {
        Write-Error "❌ Service deployment failed: $($_.Exception.Message)"
        Write-Log "Service deployment failed: $($_.Exception.Message)" "ERROR"
        return $false
    }
}

# ================================
# POST-INITIALIZATION VALIDATION
# ================================

function Test-PostInitialization {
    Write-Header "✅ POST-INITIALIZATION VALIDATION..."
    Write-Log "Starting post-initialization validation" "INFO"
    
    $validationResults = @{}
    
    # Test 1: Configuration validation
    Write-Output "  Validating configuration..."
    try {
        & "venv\Scripts\Activate.ps1"
        $configValid = python -c "
from shared.config.settings import get_settings
try:
    settings = get_settings()
    print(f'Environment: {settings.environment}')
    print(f'Debug: {settings.debug}')
    print('Configuration is valid')
    exit(0)
except Exception as e:
    print(f'Configuration error: {e}')
    exit(1)
" 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Success "    ✅ Configuration: VALID"
            $validationResults["configuration"] = "VALID"
        } else {
            Write-Error "    ❌ Configuration: INVALID"
            Write-Error "       $configValid"
            $validationResults["configuration"] = "INVALID"
        }
    } catch {
        Write-Error "    ❌ Configuration validation failed: $($_.Exception.Message)"
        $validationResults["configuration"] = "ERROR"
    }
    
    # Test 2: Service connectivity
    Write-Output "  Testing service connectivity..."
    
    # Redis connectivity
    try {
        docker exec op-redis redis-cli ping | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Success "    ✅ Redis: CONNECTED"
            $validationResults["redis"] = "CONNECTED"
        } else {
            Write-Error "    ❌ Redis: NOT_CONNECTED" 
            $validationResults["redis"] = "NOT_CONNECTED"
        }
    } catch {
        Write-Error "    ❌ Redis: ERROR"
        $validationResults["redis"] = "ERROR"
    }
    
    # API service (if running)
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 5 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            Write-Success "    ✅ API Service: HEALTHY"
            $validationResults["api"] = "HEALTHY"
        } else {
            Write-Warning "    ⚠️  API Service: NOT_RESPONDING"
            $validationResults["api"] = "NOT_RESPONDING"
        }
    } catch {
        Write-Info "    ℹ️  API Service: NOT_STARTED (expected for first_time mode)"
        $validationResults["api"] = "NOT_STARTED"
    }
    
    # Test 3: File system validation
    Write-Output "  Validating file system..."
    $requiredPaths = @("data", "logs", "shared", "services")
    $fsValid = $true
    
    foreach ($path in $requiredPaths) {
        if (Test-Path $path) {
            Write-Success "    ✅ Path exists: $path"
        } else {
            Write-Error "    ❌ Missing path: $path"
            $fsValid = $false
        }
    }
    
    $validationResults["filesystem"] = if ($fsValid) { "VALID" } else { "INVALID" }
    
    # Test 4: Python environment
    Write-Output "  Validating Python environment..."
    try {
        & "venv\Scripts\Activate.ps1"
        python -c "
import sys
import pkg_resources

print(f'Python version: {sys.version}')

required_packages = ['fastapi', 'redis', 'pandas', 'numpy']
missing_packages = []

for package in required_packages:
    try:
        pkg_resources.get_distribution(package)
        print(f'✅ {package}: installed')
    except pkg_resources.DistributionNotFound:
        print(f'❌ {package}: missing')
        missing_packages.append(package)

if not missing_packages:
    print('All required packages are installed')
    exit(0)
else:
    print(f'Missing packages: {missing_packages}')
    exit(1)
" 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Success "    ✅ Python environment: VALID"
            $validationResults["python"] = "VALID"
        } else {
            Write-Warning "    ⚠️  Python environment: INCOMPLETE"
            $validationResults["python"] = "INCOMPLETE"
        }
    } catch {
        Write-Error "    ❌ Python environment validation failed"
        $validationResults["python"] = "ERROR"
    }
    
    $script:PostValidationResults = $validationResults
    
    # Summary
    $valid = ($validationResults.Values | Where-Object { $_ -in @("VALID", "HEALTHY", "CONNECTED") }).Count
    $invalid = ($validationResults.Values | Where-Object { $_ -in @("INVALID", "ERROR", "NOT_CONNECTED") }).Count
    $warnings = ($validationResults.Values | Where-Object { $_ -in @("INCOMPLETE", "NOT_RESPONDING", "NOT_STARTED") }).Count
    $total = $validationResults.Count
    
    Write-Output ""
    Write-Output "  Validation Summary:"
    Write-Output "    Valid: $valid"
    Write-Output "    Invalid: $invalid"
    Write-Output "    Warnings: $warnings"
    Write-Output "    Total: $total"
    
    if ($invalid -eq 0) {
        Write-Success "✅ Post-initialization validation passed"
        Write-Log "Post-initialization validation passed ($valid/$total valid, $warnings warnings)" "SUCCESS"
        return $true
    } else {
        Write-Error "❌ Post-initialization validation failed"
        Write-Log "Post-initialization validation failed ($invalid/$total invalid)" "ERROR"
        return $false
    }
}

# ================================
# MONITORING SETUP
# ================================

function Set-MonitoringDashboards {
    Write-Header "📊 SETTING UP MONITORING DASHBOARDS..."
    Write-Log "Setting up monitoring dashboards" "INFO"
    
    if ($Mode -eq "first_time") {
        Write-Info "  Skipping monitoring setup for first-time mode"
        return $true
    }
    
    try {
        # Start Grafana (if not already running)
        Write-Output "  Starting Grafana..."
        docker run -d --name op-grafana -p 3000:3000 `
            -e GF_SECURITY_ADMIN_USER=admin `
            -e GF_SECURITY_ADMIN_PASSWORD=admin `
            -v grafana-data:/var/lib/grafana `
            grafana/grafana:latest
        
        if ($LASTEXITCODE -ne 0) {
            Write-Info "  Grafana container might already exist, attempting to start..."
            docker start op-grafana | Out-Null
        }
        
        # Start Prometheus (if production mode)
        if ($Mode -eq "production") {
            Write-Output "  Starting Prometheus..."
            
            # Create basic Prometheus config
            $prometheusConfig = @"
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'op-trading'
    static_configs:
      - targets: ['host.docker.internal:8080']
"@
            
            New-Item -ItemType Directory -Path "infrastructure\monitoring" -Force | Out-Null
            Set-Content -Path "infrastructure\monitoring\prometheus.yml" -Value $prometheusConfig
            
            docker run -d --name op-prometheus -p 9090:9090 `
                -v "${PWD}\infrastructure\monitoring\prometheus.yml:/etc/prometheus/prometheus.yml" `
                prom/prometheus:latest
                
            if ($LASTEXITCODE -ne 0) {
                Write-Info "  Prometheus container might already exist, attempting to start..."
                docker start op-prometheus | Out-Null
            }
        }
        
        # Wait for Grafana to be ready
        Write-Output "  Waiting for Grafana to be ready..."
        Start-Sleep -Seconds 15
        
        # Test Grafana connectivity
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:3000" -TimeoutSec 10
            if ($response.StatusCode -eq 200) {
                Write-Success "  ✅ Grafana is ready at: http://localhost:3000"
                Write-Info "     Default credentials: admin/admin"
            }
        } catch {
            Write-Warning "  ⚠️  Grafana health check failed"
        }
        
        if ($Mode -eq "production") {
            try {
                $response = Invoke-WebRequest -Uri "http://localhost:9090" -TimeoutSec 10
                if ($response.StatusCode -eq 200) {
                    Write-Success "  ✅ Prometheus is ready at: http://localhost:9090"
                }
            } catch {
                Write-Warning "  ⚠️  Prometheus health check failed"
            }
        }
        
        Write-Success "✅ Monitoring dashboards setup completed"
        Write-Log "Monitoring dashboards setup completed" "SUCCESS"
        return $true
        
    } catch {
        Write-Error "❌ Monitoring setup failed: $($_.Exception.Message)"
        Write-Log "Monitoring setup failed: $($_.Exception.Message)" "ERROR"
        return $false
    }
}

# ================================
# FINAL SUMMARY AND NEXT STEPS
# ================================

function Show-Summary {
    $endTime = Get-Date
    $duration = $endTime - $script:StartTime
    
    Write-Header "🎉 SETUP COMPLETED!"
    
    Write-Output @"

╔══════════════════════════════════════════════════════════════════════════════╗
║                           📋 SETUP SUMMARY                                   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Mode: $($Mode.ToUpper().PadRight(20)) │ Duration: $($duration.ToString("mm\:ss").PadRight(20))      ║
║  Status: COMPLETED               │ Log File: $($script:LogFile.PadRight(20))      ║
╚══════════════════════════════════════════════════════════════════════════════╝

"@
    
    # Prerequisites Summary
    Write-Output "📋 Prerequisites Check:"
    foreach ($prereq in $script:PrereqResults.Keys) {
        $status = $script:PrereqResults[$prereq]
        $icon = switch ($status) {
            "PASSED" { "✅" }
            "FAILED" { "❌" }
            "OPTIONAL_MISSING" { "⚠️ " }
        }
        Write-Output "   $icon $prereq : $status"
    }
    
    # Test Results Summary
    if ($script:TestResults.Count -gt 0) {
        Write-Output "`n🧪 Test Results:"
        foreach ($test in $script:TestResults.Keys) {
            $status = $script:TestResults[$test]
            $icon = switch ($status) {
                "PASSED" { "✅" }
                "FAILED" { "❌" }
                "NOT_FOUND" { "⚠️ " }
                "CONCERNS" { "⚠️ " }
            }
            Write-Output "   $icon $test : $status"
        }
    }
    
    # Validation Results Summary
    if ($script:PostValidationResults.Count -gt 0) {
        Write-Output "`n✅ Post-Validation:"
        foreach ($validation in $script:PostValidationResults.Keys) {
            $status = $script:PostValidationResults[$validation]
            $icon = switch ($status) {
                "VALID" { "✅" }
                "HEALTHY" { "✅" }
                "CONNECTED" { "✅" }
                "INVALID" { "❌" }
                "ERROR" { "❌" }
                "NOT_CONNECTED" { "❌" }
                "INCOMPLETE" { "⚠️ " }
                "NOT_RESPONDING" { "⚠️ " }
                "NOT_STARTED" { "ℹ️ " }
            }
            Write-Output "   $icon $validation : $status"
        }
    }
    
    # Service URLs
    Write-Output "`n🌐 Service URLs:"
    Write-Output "   📚 API Documentation: http://localhost:8000/docs"
    Write-Output "   ❤️  Health Check: http://localhost:8000/health"
    Write-Output "   📊 Grafana Dashboard: http://localhost:3000 (admin/admin)"
    
    if ($Mode -eq "production") {
        Write-Output "   📈 Prometheus: http://localhost:9090"
        Write-Output "   🗄️  InfluxDB: http://localhost:8086"
    }
    
    # Next Steps
    Write-Output "`n📚 Next Steps:"
    
    switch ($Mode) {
        "first_time" {
            Write-Output @"
   1. 📝 Update $ConfigFile with your actual Kite Connect API credentials
   2. 🔐 Run interactive authentication: python services\collection\kite_auth_manager.py --login
   3. 🚀 Start development mode: .\setup.ps1 development
   4. 📖 Read the documentation in the docs folder
   5. 🧪 Run comprehensive tests: python -m pytest tests\comprehensive_test_suite.py
"@
        }
        
        "development" {
            Write-Output @"
   1. 🚀 Run start_development.bat to start all services
   2. 📊 Monitor system health at http://localhost:8000/health
   3. 🔍 View logs in the logs folder
   4. 🧪 Run tests regularly: python -m pytest tests/
   5. 📈 Check Grafana dashboards for real-time data
"@
        }
        
        "production" {
            Write-Output @"
   1. 🚀 Services are running via Docker Compose
   2. 📊 Monitor all dashboards for system health
   3. 🔔 Configure email alerts in $ConfigFile
   4. 💾 Set up regular data backups
   5. 📈 Review performance metrics regularly
   6. 🔒 Review and update security settings
"@
        }
    }
    
    # Important Files
    Write-Output "`n📁 Important Files:"
    Write-Output "   ⚙️  Configuration: $ConfigFile"
    Write-Output "   📝 Setup Log: $script:LogFile"
    Write-Output "   🐍 Python Environment: venv\"
    Write-Output "   📊 Data Directory: data\"
    Write-Output "   📜 Logs Directory: logs\"
    
    if ($Mode -ne "first_time") {
        if ($Mode -eq "development") {
            Write-Output "   🚀 Development Launcher: start_development.bat"
        } else {
            Write-Output "   🚀 Production Launcher: start_production.bat"
        }
    }
    
    # Warnings and Recommendations
    if ($Mode -eq "production") {
        Write-Output "`n⚠️  Production Checklist:"
        Write-Output "   🔐 Update all default passwords and API keys"
        Write-Output "   🔒 Enable HTTPS and SSL certificates" 
        Write-Output "   📧 Configure email alerts and notification recipients"
        Write-Output "   💾 Set up automated backups"
        Write-Output "   🏗️  Consider Kubernetes deployment for high availability"
        Write-Output "   📊 Set up log aggregation and monitoring"
    }
    
    Write-Output ""
    Write-Success "🎉 OP Trading Platform setup completed successfully!"
    Write-Output "💡 For help and troubleshooting, check the setup log file: $script:LogFile"
    Write-Output ""
    
    # Final logging
    Write-Log "Setup completed successfully for mode: $Mode in $($duration.ToString("mm\:ss"))" "SUCCESS"
}

# ================================
# TROUBLESHOOTING SECTION
# ================================

function Show-TroubleshootingHelp {
    param([string]$Issue = "")
    
    Write-Header "🔧 TROUBLESHOOTING COMMON ISSUES"
    
    $troubleshooting = @{
        "docker_not_running" = @{
            "Problem" = "Docker commands fail with 'Docker daemon not running'"
            "Solution" = @"
1. Start Docker Desktop application
2. Wait for Docker to fully start (usually 30-60 seconds)
3. Verify with: docker ps
4. If still failing, restart Docker Desktop
"@
        }
        
        "port_in_use" = @{
            "Problem" = "Port already in use errors (8000, 3000, 6379)"
            "Solution" = @"
1. Find process using port: netstat -ano | findstr :8000
2. Kill process: taskkill /PID <PID_NUMBER> /F
3. Or use different port in $ConfigFile
4. For Docker containers: docker ps and docker stop <container_name>
"@
        }
        
        "python_module_not_found" = @{
            "Problem" = "ModuleNotFoundError or import errors"
            "Solution" = @"
1. Ensure virtual environment is activated: venv\Scripts\Activate.ps1
2. Reinstall requirements: pip install -r requirements.txt
3. Check Python path: python -c "import sys; print(sys.path)"
4. Add project root to Python path if needed
"@
        }
        
        "redis_connection_failed" = @{
            "Problem" = "Redis connection refused or timeout"
            "Solution" = @"
1. Check Redis container: docker ps | grep redis
2. Start Redis if not running: docker start op-redis
3. Test connectivity: docker exec op-redis redis-cli ping
4. Check Redis logs: docker logs op-redis
5. Verify port 6379 is available: netstat -ano | findstr :6379
"@
        }
        
        "kite_auth_failed" = @{
            "Problem" = "Kite Connect authentication failures"
            "Solution" = @"
1. Verify API credentials in $ConfigFile
2. Check API key and secret are correct (no extra spaces)
3. Ensure Kite Connect app is active in Kite portal
4. Run interactive auth: python services\collection\kite_auth_manager.py --login
5. Check if using correct redirect URL in Kite app settings
"@
        }
        
        "permission_denied" = @{
            "Problem" = "Permission denied errors when creating files/folders"
            "Solution" = @"
1. Run PowerShell as Administrator
2. Check Windows permissions on project folder
3. Temporarily disable antivirus if interfering
4. Use different location (not Program Files or System folders)
"@
        }
        
        "high_memory_usage" = @{
            "Problem" = "System running out of memory"
            "Solution" = @"
1. Reduce MAX_MEMORY_USAGE_MB in $ConfigFile
2. Decrease PROCESSING_BATCH_SIZE
3. Reduce number of PROCESSING_MAX_WORKERS
4. Enable compression: COMPRESSION_ENABLED=true
5. Monitor memory usage via Task Manager
"@
        }
        
        "services_not_responding" = @{
            "Problem" = "Services start but don't respond to health checks"
            "Solution" = @"
1. Check service logs in logs/ folder
2. Verify environment configuration
3. Test individual service startup manually
4. Check Windows Firewall isn't blocking ports
5. Ensure all dependencies (Redis, InfluxDB) are running
"@
        }
    }
    
    if ($Issue -ne "") {
        if ($troubleshooting.ContainsKey($Issue)) {
            Write-Output "Problem: $($troubleshooting[$Issue].Problem)"
            Write-Output "Solution:"
            Write-Output $troubleshooting[$Issue].Solution
        } else {
            Write-Warning "Unknown issue: $Issue"
            Write-Output "Available issues: $($troubleshooting.Keys -join ', ')"
        }
    } else {
        foreach ($issue in $troubleshooting.Keys) {
            Write-Output "🔧 $($troubleshooting[$issue].Problem)"
            Write-Output "   Solution: See help with: .\setup.ps1 -Mode troubleshoot -Issue $issue"
            Write-Output ""
        }
    }
    
    Write-Output "📞 Additional Help:"
    Write-Output "   📜 Check setup log: $script:LogFile" 
    Write-Output "   📊 System status: docker ps"
    Write-Output "   📋 Container logs: docker logs <container_name>"
    Write-Output "   🔍 Port usage: netstat -ano | findstr :<port>"
    Write-Output "   💾 Disk space: Get-WmiObject -Class Win32_LogicalDisk"
}

# ================================
# MAIN EXECUTION FLOW
# ================================

function Main {
    try {
        Show-Banner
        
        # Handle special modes
        if ($Mode -eq "troubleshoot") {
            Show-TroubleshootingHelp -Issue $Issue
            return
        }
        
        # Prerequisites check
        if (-not $SkipPrereqs) {
            if (-not (Test-Prerequisites)) {
                exit 1
            }
        } else {
            Write-Warning "⚠️  Skipping prerequisites check (not recommended)"
        }
        
        # Directory structure
        New-DirectoryStructure
        
        # Environment configuration
        Set-EnvironmentConfiguration
        
        # Python environment setup
        if (-not (Set-PythonEnvironment)) {
            Write-Error "❌ Python environment setup failed. Cannot continue."
            exit 1
        }
        
        # Start service dependencies
        if (-not (Start-ServiceDependencies)) {
            Write-Warning "⚠️  Service dependencies setup failed, but continuing..."
        }
        
        # Kite Connect authentication setup
        Set-KiteAuthentication
        
        # Run tests based on mode
        $testType = switch ($Mode) {
            "first_time" { "basic" }
            "development" { "comprehensive" }
            "production" { "performance" }
        }
        
        Invoke-TestSuite -TestType $testType
        
        # Deploy services
        Deploy-Services
        
        # Set up monitoring (for development and production)
        if ($Mode -ne "first_time") {
            Set-MonitoringDashboards
        }
        
        # Post-initialization validation
        Test-PostInitialization
        
        # Show final summary
        Show-Summary
        
    } catch {
        Write-Error "❌ Setup failed with error: $($_.Exception.Message)"
        Write-Log "Setup failed with error: $($_.Exception.Message)" "ERROR"
        Write-Output "📜 Check the setup log for detailed error information: $script:LogFile"
        exit 1
    }
}

# ================================
# SCRIPT ENTRY POINT
# ================================

# Validate parameters
if ($Mode -notin @("first_time", "development", "production", "troubleshoot")) {
    Write-Error "Invalid mode: $Mode. Valid modes: first_time, development, production, troubleshoot"
    exit 1
}

# Initialize logging
Write-Log "OP Trading Platform Setup Started - Mode: $Mode" "INFO"

# Run main function
Main