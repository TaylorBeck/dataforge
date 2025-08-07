# DataForge API - Deployment Guide

This guide covers various deployment options for the DataForge API.

## 🐳 Docker Deployment

### Quick Start with Docker Compose

1. **Clone and configure**:
```bash
git clone <repository>
cd dataforge
cp .env.example .env
# Edit .env with your API keys
```

2. **Start with Docker Compose**:
```bash
docker-compose up -d
```

3. **Check status**:
```bash
# View logs
docker-compose logs -f dataforge-api

# Check health
curl http://localhost:8000/api/health
```

### Manual Docker Build

```bash
# Build image
docker build -t dataforge-api .

# Run with Redis
docker network create dataforge-net
docker run -d --name redis --network dataforge-net redis:7-alpine
docker run -d --name dataforge-api \
  --network dataforge-net \
  -p 8000:8000 \
  -e REDIS_URL=redis://redis:6379/0 \
  -e OPENAI_API_KEY=your_key_here \
  dataforge-api
```

## ☁️ Cloud Deployment

### Railway

1. **Connect repository** to Railway
2. **Set environment variables**:
   - `OPENAI_API_KEY`
   - `REDIS_URL` (Railway provides Redis addon)
   - `DEBUG=false`

3. **Deploy**:
```bash
railway up
```

### Fly.io

1. **Install Fly CLI** and login
2. **Initialize app**:
```bash
fly launch
```

3. **Set secrets**:
```bash
fly secrets set OPENAI_API_KEY=your_key_here
fly secrets set REDIS_URL=redis://your-redis-url
```

4. **Deploy**:
```bash
fly deploy
```

### Render

1. **Connect repository** to Render
2. **Create web service** with:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

3. **Add Redis service** and set `REDIS_URL`

### Heroku

1. **Create app**:
```bash
heroku create your-dataforge-api
```

2. **Add Redis addon**:
```bash
heroku addons:create heroku-redis:mini
```

3. **Set config vars**:
```bash
heroku config:set OPENAI_API_KEY=your_key_here
heroku config:set DEBUG=false
```

4. **Deploy**:
```bash
git push heroku main
```

## 🖥️ VPS/Server Deployment

### Using Nginx + Gunicorn

1. **Install dependencies**:
```bash
sudo apt update
sudo apt install nginx python3-pip redis-server
```

2. **Setup application**:
```bash
git clone <repository> /opt/dataforge
cd /opt/dataforge
pip3 install -r requirements.txt
```

3. **Create systemd service** (`/etc/systemd/system/dataforge.service`):
```ini
[Unit]
Description=DataForge API
After=network.target redis.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/dataforge
Environment=PATH=/usr/bin:/usr/local/bin
Environment=PYTHONPATH=/opt/dataforge
Environment=OPENAI_API_KEY=your_key_here
Environment=REDIS_URL=redis://localhost:6379/0
Environment=DEBUG=false
ExecStart=/usr/local/bin/gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:8000
Restart=always

[Install]
WantedBy=multi-user.target
```

4. **Configure Nginx** (`/etc/nginx/sites-available/dataforge`):
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

5. **Enable and start**:
```bash
sudo systemctl enable dataforge
sudo systemctl start dataforge
sudo ln -s /etc/nginx/sites-available/dataforge /etc/nginx/sites-enabled/
sudo systemctl reload nginx
```

## 🔒 Production Security

### Environment Variables

```bash
# Required
OPENAI_API_KEY=your_production_key
REDIS_URL=redis://secure-redis:6379/0

# Security
DEBUG=false
API_TITLE="DataForge API"

# Performance
MAX_CONCURRENT_JOBS=20
MAX_SAMPLES_PER_REQUEST=100
```

### Nginx Security Headers

```nginx
# Add to your nginx config
add_header X-Frame-Options DENY;
add_header X-Content-Type-Options nosniff;
add_header X-XSS-Protection "1; mode=block";
add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload";
```

### Redis Security

```bash
# Redis configuration (redis.conf)
bind 127.0.0.1
requirepass your_redis_password
```

## 📊 Monitoring

### Health Checks

```bash
# Simple health check
curl -f http://your-api.com/api/health || exit 1

# Comprehensive check
curl -s http://your-api.com/api/stats | jq .
```

### Prometheus Metrics (Optional)

Add to your app:

```python
from prometheus_client import Counter, Histogram, generate_latest

REQUESTS_TOTAL = Counter('dataforge_requests_total', 'Total requests')
REQUEST_DURATION = Histogram('dataforge_request_duration_seconds', 'Request duration')

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    REQUEST_DURATION.observe(time.time() - start_time)
    REQUESTS_TOTAL.inc()
    return response

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

### Log Aggregation

```python
# Use structured logging
import structlog

logger = structlog.get_logger()
logger.info("Generation started", job_id=job_id, product=product)
```

## 🚀 Performance Tuning

### Gunicorn Configuration

```python
# gunicorn.conf.py
bind = "0.0.0.0:8000"
workers = 4
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 100
timeout = 300
keepalive = 5
```

### Redis Optimization

```bash
# Redis tuning
maxmemory 2gb
maxmemory-policy allkeys-lru
tcp-keepalive 60
```

### Database Connection Pooling

For larger deployments, consider PostgreSQL:

```python
# Replace Redis with PostgreSQL for job storage
DATABASE_URL=postgresql://user:pass@localhost/dataforge
```

## 🔄 CI/CD Pipeline

### GitHub Actions Example

```yaml
# .github/workflows/deploy.yml
name: Deploy DataForge API

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Run tests
        run: pytest
      
      - name: Deploy to production
        run: |
          # Your deployment script here
          echo "Deploying to production..."
```

## 🆘 Troubleshooting

### Common Issues

1. **Redis Connection Failed**
   ```bash
   # Check Redis status
   redis-cli ping
   
   # Check logs
   tail -f /var/log/redis/redis-server.log
   ```

2. **High Memory Usage**
   ```bash
   # Monitor Redis memory
   redis-cli info memory
   
   # Clear expired jobs
   curl -X POST http://localhost:8000/admin/cleanup
   ```

3. **Slow Response Times**
   ```bash
   # Check system resources
   htop
   
   # Monitor API metrics
   curl http://localhost:8000/api/stats
   ```

4. **API Key Issues**
   ```bash
   # Test LLM connection
   curl -X POST http://localhost:8000/api/test-llm
   ```

### Logs Location

- **Docker**: `docker logs dataforge-api`
- **Systemd**: `journalctl -u dataforge`
- **Application**: `tail -f dataforge.log`

## 📈 Scaling

### Horizontal Scaling

1. **Load Balancer**: Use Nginx/HAProxy
2. **Multiple Instances**: Run multiple API instances
3. **Shared Redis**: Use Redis Cluster or managed Redis
4. **Queue Workers**: Separate generation workers with Celery

### Vertical Scaling

1. **More RAM**: For Redis caching
2. **More CPU**: For concurrent processing
3. **Faster Storage**: For log performance

---

For more deployment options and advanced configurations, check the [main README](README.md) or open an issue on GitHub.