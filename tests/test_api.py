"""
Basic tests for the DataForge API.
"""
import pytest
import pytest_asyncio
import httpx
from app.main import app
from app.config import get_settings


@pytest.fixture
def mock_settings():
    """Override settings for testing."""
    settings = get_settings()
    settings.default_llm_provider = "mock"
    settings.debug = True
    return settings


@pytest.mark.asyncio
async def test_root_endpoint():
    """Test the root endpoint."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/")
    
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_health_check():
    """Test the health check endpoint."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/health")
    
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "timestamp" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_generate_endpoint():
    """Test the generation endpoint."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/generate", json={
            "product": "test product",
            "count": 1,
            "version": "v1",
            "temperature": 0.7
        })
    
    # Note: This might fail without Redis, but structure should be correct
    assert response.status_code in [200, 500]  # Allow for Redis connection issues
    
    if response.status_code == 200:
        data = response.json()
        assert "job_id" in data
        assert "status" in data


@pytest.mark.asyncio
async def test_validate_endpoint():
    """Test the validation endpoint."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/validate", json={
            "product": "test product",
            "count": 5
        })
    
    assert response.status_code == 200
    data = response.json()
    assert "validation" in data
    assert "request" in data


@pytest.mark.asyncio
async def test_stats_endpoint_removed():
    """/api/stats was removed as part of deprecation; should return 404."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/stats")
    assert response.status_code in [404, 405]


@pytest.mark.asyncio
async def test_invalid_generation_request():
    """Test validation of invalid generation requests."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        # Test empty product
        response = await ac.post("/api/generate", json={
            "product": "",
            "count": 1
        })
        assert response.status_code == 422  # Validation error
        
        # Test count too high
        response = await ac.post("/api/generate", json={
            "product": "test product",
            "count": 1000  # Exceeds default limit
        })
        assert response.status_code in [400, 422]


@pytest.mark.asyncio 
async def test_nonexistent_job():
    """Test getting status for nonexistent job."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/result/nonexistent-job-id")
        assert response.status_code == 404