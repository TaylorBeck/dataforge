# DataForge API - Quick Start Guide

Get the DataForge API up and running in minutes for testing with Postman or building a frontend.

## 🚀 Quick Setup (5 minutes)

### 1. **Automated Setup**
```bash
# Run the automated setup script
python setup_dev.py
```

This will:
- ✅ Check Python version and dependencies
- ✅ Install missing packages
- ✅ Create environment file
- ✅ Start Redis (if Docker available)
- ✅ Test basic functionality

### 2. **Manual Setup** (if automated setup fails)

**Install dependencies:**
```bash
pip install -r requirements.txt
```

**Create environment file:**
```bash
cp .env.example .env
# Edit .env to add your API keys (optional for testing)
```

**Start Redis:**
```bash
# Option 1: Docker (recommended)
docker run -d -p 6379:6379 redis:7-alpine

# Option 2: Local Redis
redis-server

# Option 3: Skip Redis (uses in-memory storage)
# No action needed - API will use fallback storage
```

### 3. **Start the API**
```bash
# Development server with auto-reload
python run_dev.py

# Or manually:
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

You should see:
```
🚀 DataForge API startup complete
📖 API docs: http://localhost:8000/docs
🔍 Health check: http://localhost:8000/api/health
```

## 🧪 Testing Options

### Option 1: Automated Test Suite
```bash
# Run comprehensive workflow tests
python test_workflow.py
```

This tests all endpoints and the complete generation workflow.

### Option 2: Postman Collection

1. **Import collection:** `DataForge_API.postman_collection.json`
2. **Import environment:** `postman_environment.json`
3. **Test endpoints** starting with "Health Check"

### Option 3: Interactive API Docs
Visit **http://localhost:8000/docs** for interactive Swagger documentation.

### Option 4: Manual Testing
```bash
# Health check
curl http://localhost:8000/api/health

# Create generation job
curl -X POST "http://localhost:8000/api/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "product": "mobile banking app",
    "count": 3,
    "temperature": 0.7
  }'

# Check job status (replace with actual job_id)
curl "http://localhost:8000/api/result/YOUR_JOB_ID"
```

### Option 5: Python Client Example
```bash
# Run the example usage script
python example_usage.py
```

## 📝 Quick Test Workflow

1. **Health Check** → `/api/health`
2. **Create Job** → `/api/generate` 
3. **Check Status** → `/api/result/{job_id}`
4. **Get Results** → Same endpoint when completed

## 🎯 Ready-to-Use API Endpoints

| Endpoint | Method | Purpose |
|----------|---------|---------|
| `/api/health` | GET | Check API health |
| `/api/stats` | GET | System statistics |
| `/api/generate` | POST | Create generation job |
| `/api/result/{job_id}` | GET | Get job status/results |
| `/api/validate` | POST | Validate request |
| `/api/test-llm` | POST | Test LLM connection |
| `/docs` | GET | Interactive API docs |

## 🔧 Configuration for Testing

The API works out-of-the-box with these defaults:

- **LLM Provider:** Mock (no API keys needed)
- **Storage:** Redis (falls back to memory if unavailable)
- **CORS:** Enabled for all origins in debug mode
- **Rate Limiting:** Disabled
- **Authentication:** None required

## 🛠️ Frontend Integration

### JavaScript/TypeScript Example
```javascript
// Create generation job
const response = await fetch('http://localhost:8000/api/generate', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    product: 'mobile app',
    count: 5,
    temperature: 0.7
  })
});

const { job_id } = await response.json();

// Poll for results
const pollForResults = async (jobId) => {
  while (true) {
    const statusResponse = await fetch(`http://localhost:8000/api/result/${jobId}`);
    const status = await statusResponse.json();
    
    if (status.status === 'completed') {
      return status.result.samples;
    } else if (status.status === 'error') {
      throw new Error(status.error_message);
    }
    
    await new Promise(resolve => setTimeout(resolve, 1000)); // Wait 1s
  }
};

const samples = await pollForResults(job_id);
```

### React Hook Example
```jsx
const useDataForge = () => {
  const [loading, setLoading] = useState(false);
  const [samples, setSamples] = useState([]);

  const generateSamples = async (product, count = 5) => {
    setLoading(true);
    try {
      // Create job
      const response = await fetch('http://localhost:8000/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product, count })
      });
      
      const { job_id } = await response.json();
      
      // Poll for completion
      const poll = async () => {
        const statusResponse = await fetch(`http://localhost:8000/api/result/${job_id}`);
        const status = await statusResponse.json();
        
        if (status.status === 'completed') {
          setSamples(status.result.samples);
          setLoading(false);
        } else if (status.status === 'error') {
          throw new Error(status.error_message);
        } else {
          setTimeout(poll, 1000);
        }
      };
      
      poll();
      
    } catch (error) {
      console.error('Generation failed:', error);
      setLoading(false);
    }
  };

  return { generateSamples, loading, samples };
};
```

## 🔑 Adding Real LLM Providers

To use real LLM providers instead of the mock:

### OpenAI
```bash
# Add to .env file
OPENAI_API_KEY=sk-your-key-here
DEFAULT_LLM_PROVIDER=openai
```

### Anthropic
```bash
# Add to .env file  
ANTHROPIC_API_KEY=your-key-here
DEFAULT_LLM_PROVIDER=anthropic
```

## 🐛 Troubleshooting

### API won't start
```bash
# Check dependencies
python setup_dev.py

# Check imports
python -c "from app.main import app; print('OK')"
```

### Redis connection issues
```bash
# Test Redis connection
python -c "import redis; redis.Redis().ping(); print('Redis OK')"

# Or run without Redis (uses memory storage)
export DEFAULT_LLM_PROVIDER=mock
```

### Generation jobs stuck
```bash
# Check LLM connection
curl -X POST http://localhost:8000/api/test-llm

# View system stats
curl http://localhost:8000/api/stats
```

### CORS issues
```bash
# Ensure DEBUG=true in .env for development
echo "DEBUG=true" >> .env
```

## 🎉 You're Ready!

The API is now ready for:
- ✅ **Postman testing** with the provided collection
- ✅ **Frontend development** with CORS enabled
- ✅ **Production deployment** when you add real API keys
- ✅ **Custom integrations** using the documented endpoints

Start with the `/api/health` endpoint to verify everything is working, then try creating your first generation job!

---

**Need help?** Check the [full README](README.md) or [extensions guide](EXTENSIONS.md) for advanced configuration.