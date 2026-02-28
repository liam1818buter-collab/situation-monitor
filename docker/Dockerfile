# Multi-stage build for Situation Monitor
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Download spaCy model (optional - for NLP features)
RUN python -m spacy download en_core_web_sm || true

# Production stage
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user for security
RUN groupadd -r smuser && useradd -r -g smuser smuser

# Create app directories
RUN mkdir -p /app /app/data /app/logs /app/config && \
    chown -R smuser:smuser /app

WORKDIR /app

# Copy application code
COPY --chown=smuser:smuser situation_monitor/ ./situation_monitor/
COPY --chown=smuser:smuser config/ ./config/
COPY --chown=smuser:smuser scripts/ ./scripts/

# Switch to non-root user
USER smuser

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SM_DATA_DIR=/app/data \
    SM_LOG_DIR=/app/logs \
    SM_CONFIG_DIR=/app/config \
    SM_ENVIRONMENT=production \
    SM_LOG_LEVEL=INFO \
    SM_LOG_FORMAT=json \
    PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import asyncio; from situation_monitor.core.models import SystemHealth; print('OK')" || exit 1

# Expose port for dashboard
EXPOSE 8501

# Default command
CMD ["python", "-m", "situation_monitor.dashboard.app"]
