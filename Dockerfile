FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HEADLESS=1 \
    GUI_MODE=browser \
    ASCEND_PORT=5466

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p /app/data /app/rpc_artwork_cache

# Expose dashboard port
EXPOSE 5466

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, requests; port = os.environ.get('ASCEND_PORT') or os.environ.get('DASHBOARD_PORT') or '5466'; r = requests.get(f'http://127.0.0.1:{port}/api/health', timeout=3); exit(0 if r.status_code == 200 else 1)" || exit 1

# Run in headless mode
CMD ["python", "start_gui.py", "--headless"]
