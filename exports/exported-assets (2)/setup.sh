#!/bin/bash

# OP Trading Platform - Complete System Setup Script
# Automates the entire deployment process from development to production

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="op-trading-platform"
VERSION="1.0.0"
ENVIRONMENT=${1:-development}  # development, staging, production

echo -e "${BLUE}🚀 OP Trading Platform - Complete System Setup${NC}"
echo -e "${BLUE}Version: $VERSION${NC}"
echo -e "${BLUE}Environment: $ENVIRONMENT${NC}"
echo ""

# Check prerequisites
check_prerequisites() {
    echo -e "${YELLOW}📋 Checking prerequisites...${NC}"
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Docker is not installed. Please install Docker first.${NC}"
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        echo -e "${RED}❌ Docker Compose is not installed. Please install Docker Compose first.${NC}"
        exit 1
    fi
    
    # Check Python (for local development)
    if [[ "$ENVIRONMENT" == "development" ]] && ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌ Python 3 is not installed. Please install Python 3.11+ first.${NC}"
        exit 1
    fi
    
    # Check Redis availability
    if ! command -v redis-cli &> /dev/null; then
        echo -e "${YELLOW}⚠️  Redis CLI not found. Will use Docker Redis.${NC}"
    fi
    
    echo -e "${GREEN}✅ Prerequisites check passed${NC}"
    echo ""
}

# Create directory structure
create_directory_structure() {
    echo -e "${YELLOW}📁 Creating directory structure...${NC}"
    
    # Main directories
    mkdir -p shared/{config,utils,constants,types}
    mkdir -p services/{collection,processing/{writers},analytics,api,monitoring}
    mkdir -p tests
    mkdir -p data/{csv_data,json_snapshots,analytics}
    mkdir -p logs
    mkdir -p infrastructure/{docker,kubernetes,monitoring,nginx,grafana}
    mkdir -p scripts
    
    # Create __init__.py files for Python packages
    find . -type d -name "*" | grep -E "(shared|services|tests)" | xargs -I {} touch {}/__init__.py
    
    echo -e "${GREEN}✅ Directory structure created${NC}"
    echo ""
}

# Setup environment configuration
setup_environment() {
    echo -e "${YELLOW}⚙️  Setting up environment configuration...${NC}"
    
    # Create .env file if it doesn't exist
    if [[ ! -f .env ]]; then
        cat > .env << EOF
# Environment Configuration
ENV=${ENVIRONMENT}
DEBUG=true
LOG_LEVEL=INFO

# Database Configuration
INFLUXDB_URL=http://localhost:8086
INFLUXDB_ORG=op-trading
INFLUXDB_BUCKET=options-data
INFLUXDB_TOKEN=your-influxdb-token

# Broker Configuration (UPDATE THESE!)
KITE_API_KEY=your-api-key
KITE_API_SECRET=your-api-secret
KITE_ACCESS_TOKEN=your-access-token

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# Data Paths
BASE_DATA_DIR=data
CSV_DATA_ROOT=data/csv_data
JSON_SNAPSHOTS_ROOT=data/raw_snapshots

# Performance Settings
PROCESSING_BATCH_SIZE=1000
PROCESSING_MAX_WORKERS=8
ENABLE_INCREMENTAL=true
USE_MEMORY_MAPPING=true
MAX_MEMORY_USAGE_MB=2048

# Monitoring & Self-Healing
HEALTH_CHECK_INTERVAL=30
AUTO_RESTART_ENABLED=true
MAX_RESTART_ATTEMPTS=3

# Email Alerts (Optional)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
ALERT_RECIPIENTS=admin@company.com

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4

# Collection Configuration
COLLECTION_LOOP_INTERVAL=30

# Analytics Configuration
ANALYTICS_STREAMING_ENABLED=true
ANALYTICS_EOD_ENABLED=true

# Grafana Configuration
GRAFANA_USER=admin
GRAFANA_PASSWORD=admin
EOF
        echo -e "${GREEN}✅ Created .env file - PLEASE UPDATE WITH YOUR ACTUAL CREDENTIALS${NC}"
    else
        echo -e "${GREEN}✅ .env file already exists${NC}"
    fi
    
    echo ""
}

# Setup Python virtual environment
setup_python_env() {
    if [[ "$ENVIRONMENT" == "development" ]]; then
        echo -e "${YELLOW}🐍 Setting up Python virtual environment...${NC}"
        
        if [[ ! -d venv ]]; then
            python3 -m venv venv
            echo -e "${GREEN}✅ Virtual environment created${NC}"
        fi
        
        source venv/bin/activate
        
        # Install dependencies
        if [[ -f requirements.txt ]]; then
            pip install --upgrade pip
            pip install -r requirements.txt
            echo -e "${GREEN}✅ Python dependencies installed${NC}"
        else
            echo -e "${YELLOW}⚠️  requirements.txt not found - creating basic version${NC}"
            create_requirements_file
            pip install -r requirements.txt
        fi
        
        echo ""
    fi
}

# Create requirements.txt
create_requirements_file() {
    cat > requirements.txt << 'EOF'
# Core dependencies
influxdb-client>=1.37.0
redis>=4.5.0
aiofiles>=23.1.0
pandas>=2.0.0
numpy>=1.24.0
psutil>=5.9.0
pytz>=2023.3
python-dotenv>=1.0.0
pydantic>=2.0.0

# API dependencies
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
python-multipart

# Analytics dependencies
scipy>=1.10.0
scikit-learn>=1.3.0

# Testing dependencies
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0
hypothesis>=6.82.0

# Development dependencies
black>=23.0.0
flake8>=6.0.0
mypy>=1.5.0

# HTTP client
aiohttp>=3.8.0
EOF
}

# Start Redis (if needed)
start_redis() {
    echo -e "${YELLOW}🔴 Starting Redis...${NC}"
    
    # Check if Redis is already running
    if redis-cli ping &>/dev/null; then
        echo -e "${GREEN}✅ Redis is already running${NC}"
    else
        # Try to start Redis with Docker
        if docker ps --filter "name=redis" --format "table {{.Names}}" | grep -q "redis"; then
            echo -e "${GREEN}✅ Redis container already running${NC}"
        else
            echo -e "${YELLOW}🚀 Starting Redis container...${NC}"
            docker run -d --name redis -p 6379:6379 redis:7-alpine
            sleep 5
            
            if redis-cli ping &>/dev/null; then
                echo -e "${GREEN}✅ Redis started successfully${NC}"
            else
                echo -e "${RED}❌ Failed to start Redis${NC}"
                exit 1
            fi
        fi
    fi
    
    echo ""
}

# Run tests
run_tests() {
    if [[ "$ENVIRONMENT" == "development" ]]; then
        echo -e "${YELLOW}🧪 Running tests...${NC}"
        
        if [[ -d tests ]] && [[ -f tests/comprehensive_test_framework.py ]]; then
            if [[ -f venv/bin/activate ]]; then
                source venv/bin/activate
            fi
            
            python -m pytest tests/comprehensive_test_framework.py -v
            
            if [[ $? -eq 0 ]]; then
                echo -e "${GREEN}✅ All tests passed${NC}"
            else
                echo -e "${YELLOW}⚠️  Some tests failed - continuing anyway${NC}"
            fi
        else
            echo -e "${YELLOW}⚠️  Test files not found - skipping tests${NC}"
        fi
        
        echo ""
    fi
}

# Build Docker images
build_docker_images() {
    echo -e "${YELLOW}🐳 Building Docker images...${NC}"
    
    # Build services
    services=("api" "collection" "processing" "analytics" "monitoring")
    
    for service in "${services[@]}"; do
        echo -e "${BLUE}Building $service service...${NC}"
        docker build --target ${service}-service -t op-trading/${service}:${VERSION} .
        docker tag op-trading/${service}:${VERSION} op-trading/${service}:latest
        echo -e "${GREEN}✅ Built $service service${NC}"
    done
    
    echo ""
}

# Deploy services
deploy_services() {
    echo -e "${YELLOW}🚀 Deploying services...${NC}"
    
    case "$ENVIRONMENT" in
        "development")
            docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
            ;;
        "production")
            docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
            ;;
        *)
            docker-compose up -d
            ;;
    esac
    
    echo -e "${GREEN}✅ Services deployed${NC}"
    echo ""
}

# Wait for services to be ready
wait_for_services() {
    echo -e "${YELLOW}⏳ Waiting for services to be ready...${NC}"
    
    max_attempts=30
    attempt=1
    
    while [[ $attempt -le $max_attempts ]]; do
        if curl -f http://localhost:8000/health &>/dev/null; then
            echo -e "${GREEN}✅ All services are ready${NC}"
            return 0
        fi
        
        echo -n "."
        sleep 2
        ((attempt++))
    done
    
    echo -e "${YELLOW}⚠️  Services may not be fully ready, continuing...${NC}"
    echo ""
}

# Show service status
show_service_status() {
    echo -e "${YELLOW}📊 Service Status:${NC}"
    echo ""
    
    # Show Docker containers
    docker-compose ps
    echo ""
    
    # Show service URLs
    echo -e "${BLUE}🌐 Service URLs:${NC}"
    echo -e "  API Service: http://localhost:8000"
    echo -e "  API Docs: http://localhost:8000/docs"
    echo -e "  Grafana: http://localhost:3000 (admin/admin)"
    echo -e "  InfluxDB: http://localhost:8086"
    echo -e "  Prometheus: http://localhost:9090"
    echo ""
    
    # Test API endpoint
    if curl -f http://localhost:8000/health &>/dev/null; then
        echo -e "${GREEN}✅ API is responding${NC}"
        
        # Show health status
        echo -e "${BLUE}🏥 System Health:${NC}"
        curl -s http://localhost:8000/health | python3 -m json.tool | head -20
    else
        echo -e "${YELLOW}⚠️  API is not responding yet${NC}"
    fi
    
    echo ""
}

# Create useful scripts
create_scripts() {
    echo -e "${YELLOW}📝 Creating utility scripts...${NC}"
    
    # Create management script
    cat > scripts/manage.sh << 'EOF'
#!/bin/bash

# OP Trading Platform Management Script

case "$1" in
    "start")
        echo "Starting all services..."
        docker-compose up -d
        ;;
    "stop")
        echo "Stopping all services..."
        docker-compose down
        ;;
    "restart")
        echo "Restarting all services..."
        docker-compose restart
        ;;
    "logs")
        service=${2:-api}
        echo "Showing logs for $service..."
        docker-compose logs -f $service
        ;;
    "health")
        echo "Checking system health..."
        curl -s http://localhost:8000/health | python3 -m json.tool
        ;;
    "test")
        echo "Running tests..."
        python -m pytest tests/ -v
        ;;
    "backup")
        echo "Creating data backup..."
        tar -czf backup-$(date +%Y%m%d_%H%M%S).tar.gz data/
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|logs [service]|health|test|backup}"
        exit 1
        ;;
esac
EOF
    
    chmod +x scripts/manage.sh
    
    # Create development script
    cat > scripts/dev.sh << 'EOF'
#!/bin/bash

# Development helper script

case "$1" in
    "setup")
        echo "Setting up development environment..."
        python3 -m venv venv
        source venv/bin/activate
        pip install -r requirements.txt
        ;;
    "run-api")
        echo "Running API in development mode..."
        source venv/bin/activate
        uvicorn services.api.api_service:app --host 0.0.0.0 --port 8000 --reload
        ;;
    "run-collection")
        echo "Running collection service..."
        source venv/bin/activate
        python services/collection/atm_option_collector.py
        ;;
    "run-analytics")
        echo "Running analytics service..."
        source venv/bin/activate
        python services/analytics/options_analytics_service.py
        ;;
    "format")
        echo "Formatting code..."
        source venv/bin/activate
        black .
        ;;
    "lint")
        echo "Linting code..."
        source venv/bin/activate
        flake8 .
        ;;
    *)
        echo "Usage: $0 {setup|run-api|run-collection|run-analytics|format|lint}"
        exit 1
        ;;
esac
EOF
    
    chmod +x scripts/dev.sh
    
    echo -e "${GREEN}✅ Utility scripts created${NC}"
    echo ""
}

# Main execution
main() {
    echo -e "${BLUE}Starting OP Trading Platform setup for $ENVIRONMENT environment...${NC}"
    echo ""
    
    check_prerequisites
    create_directory_structure
    setup_environment
    setup_python_env
    start_redis
    run_tests
    
    if [[ "$ENVIRONMENT" != "development" ]]; then
        build_docker_images
        deploy_services
        wait_for_services
    fi
    
    create_scripts
    show_service_status
    
    echo -e "${GREEN}🎉 OP Trading Platform setup completed successfully!${NC}"
    echo ""
    echo -e "${BLUE}📚 Next Steps:${NC}"
    echo -e "1. Update .env file with your actual broker API credentials"
    echo -e "2. For development: ./scripts/dev.sh run-api"
    echo -e "3. For production: ./scripts/manage.sh start"
    echo -e "4. Access API docs at: http://localhost:8000/docs"
    echo -e "5. Monitor system at: http://localhost:3000 (Grafana)"
    echo ""
    echo -e "${YELLOW}⚠️  Important: Update your .env file with real API keys before running in production!${NC}"
    echo ""
}

# Run main function
main "$@"