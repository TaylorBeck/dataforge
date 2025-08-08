"""
Main FastAPI application setup and configuration.
"""
import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi
from app.config import get_settings, validate_settings
from app.routers.generation import router as generation_router
from app.services.job_store import get_job_store

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("dataforge.log") if not get_settings().debug else logging.NullHandler()
    ]
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for startup and shutdown events.
    """
    logger.info("Starting DataForge API...")
    
    try:
        # Validate configuration
        validate_settings()
        
        # Initialize Celery job store (no-op but ensures Celery is reachable)
        job_store = get_job_store()
        # Optionally touch stats to ensure connectivity
        try:
            _ = job_store.get_stats()
            logger.info("Job store available")
        except Exception as e:
            logger.warning(f"Job store stats unavailable: {e}")
        
        logger.info("DataForge API startup complete")
        
        yield  # Application runs here
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise
    finally:
        # Cleanup on shutdown
        logger.info("Shutting down DataForge API...")
        # No legacy job manager to clean up
        logger.info("DataForge API shutdown complete")


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.
    
    Returns:
        Configured FastAPI application instance
    """
    settings = get_settings()
    
    # Create FastAPI app
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description=settings.api_description,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None
    )
    
    # CORS middleware
    allowed_origins = ["*"] if settings.debug else [
        "http://localhost:3000",
        "http://localhost:3001", 
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "https://healthcheck.railway.app"  # Allow Railway health checks
    ]
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["*"]
    )
    
    # Include routers
    app.include_router(generation_router)
    
    # Custom OpenAPI schema
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        
        openapi_schema = get_openapi(
            title=settings.api_title,
            version=settings.api_version,
            description=settings.api_description,
            routes=app.routes,
        )
        
        # Add custom info
        openapi_schema["info"]["x-logo"] = {
            "url": "https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png"
        }
        
        app.openapi_schema = openapi_schema
        return app.openapi_schema
    
    app.openapi = custom_openapi
    
    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Handle unexpected exceptions globally."""
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "type": "server_error"
            }
        )
    
    # Root endpoint
    @app.get("/", tags=["root"])
    async def root():
        """Root endpoint with API information."""
        return {
            "name": settings.api_title,
            "version": settings.api_version,
            "description": settings.api_description,
            "docs_url": "/docs" if settings.debug else "Documentation disabled in production",
            "health_url": "/api/health"
        }
    
    @app.get("/health", tags=["health"])
    async def simple_health():
        """Simple health endpoint for Railway load balancer."""
        return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
    
    # Middleware for request logging (in debug mode)
    if settings.debug:
        @app.middleware("http")
        async def log_requests(request: Request, call_next):
            """Log HTTP requests in debug mode."""
            start_time = asyncio.get_event_loop().time()
            
            # Log request
            logger.debug(f"Request: {request.method} {request.url}")
            
            # Process request
            response = await call_next(request)
            
            # Log response
            process_time = asyncio.get_event_loop().time() - start_time
            logger.debug(f"Response: {response.status_code} ({process_time:.3f}s)")
            
            return response
    
    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    
    # Run with uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
        access_log=settings.debug
    )