FROM python:3.11-slim

WORKDIR /app

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

# Environment variables for headless mode
ENV HEADLESS=1
ENV GUI_MODE=browser
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import requests; r = requests.get('http://localhost:5466/api/health'); exit(0 if r.status_code == 200 else 1)" || exit 1

# Run in headless mode
CMD ["python", "start_gui.py", "--headless"]
