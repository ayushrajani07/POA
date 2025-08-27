# Multi-stage Docker build for OP Trading Platform services
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN groupadd -r app && useradd -r -g app app

# Set work directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Development stage
FROM base as development

# Install development dependencies
RUN pip install --no-cache-dir \
    pytest \
    pytest-asyncio \
    pytest-cov \
    black \
    flake8 \
    mypy

# Copy source code
COPY . .

# Change ownership
RUN chown -R app:app /app

USER app

# Development command
CMD ["python", "-m", "pytest", "-v"]

# Production base
FROM base as production-base

# Copy source code
COPY shared/ ./shared/
COPY services/ ./services/
COPY tests/ ./tests/
COPY *.py ./

# Change ownership  
RUN chown -R app:app /app

USER app

# Collection service
FROM production-base as collection-service

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["python", "services/collection/atm_option_collector.py"]

# Processing service
FROM production-base as processing-service

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "from shared.utils.coordination import get_redis_coordinator; print('OK' if get_redis_coordinator().ping() else 'FAIL')"

CMD ["python", "services/processing/main.py"]

# Analytics service  
FROM production-base as analytics-service

# Install additional analytics dependencies
RUN pip install --no-cache-dir \
    numpy \
    pandas \
    scipy \
    scikit-learn

EXPOSE 8003

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "from services.analytics.options_analytics_service import OptionsAnalyticsService; print('OK')"

CMD ["python", "services/analytics/options_analytics_service.py"]

# API service
FROM production-base as api-service

# Install API dependencies
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    python-multipart

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "services.api.api_service:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

# Monitoring service
FROM production-base as monitoring-service

EXPOSE 8004

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "from services.monitoring.enhanced_health_monitor import get_enhanced_monitor; print('OK' if get_enhanced_monitor().check_system_health() else 'FAIL')"

CMD ["python", "services/monitoring/enhanced_health_monitor.py", "--start"]

# All-in-one development image
FROM production-base as all-services

# Install all dependencies
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    numpy \
    pandas \
    scipy \
    scikit-learn \
    pytest \
    pytest-asyncio

EXPOSE 8000 8001 8002 8003 8004

# Default to API service for development
CMD ["uvicorn", "services.api.api_service:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]