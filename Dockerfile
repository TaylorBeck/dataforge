FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies including curl for health checks
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create startup script
COPY start.sh .
RUN chmod +x start.sh

# Create non-root user and set permissions
RUN useradd -m -u 1000 dataforge && \
    chown -R dataforge:dataforge /app && \
    mkdir -p /tmp && \
    chown dataforge:dataforge /tmp
USER dataforge

# Expose port
EXPOSE 8000

# Health check - use simple endpoint and give more time for startup
HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the startup script
CMD ["./start.sh"]