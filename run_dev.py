#!/usr/bin/env python3
"""
Development runner script for DataForge API.
This script sets up the development environment and starts the server.
"""
import os
import sys
import subprocess
import time
from pathlib import Path


def check_redis():
    """Check if Redis is running."""
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        return True
    except (redis.ConnectionError, ModuleNotFoundError):
        return False


def start_redis_docker():
    """Start Redis using Docker."""
    print("🐳 Starting Redis with Docker...")
    try:
        subprocess.run([
            "docker", "run", "-d", 
            "--name", "dataforge-redis",
            "-p", "6379:6379",
            "redis:7-alpine"
        ], check=True)
        
        # Wait for Redis to start
        print("⏳ Waiting for Redis to start...")
        for i in range(10):
            if check_redis():
                print("✅ Redis is running!")
                return True
            time.sleep(1)
        
        print("❌ Redis failed to start")
        return False
        
    except subprocess.CalledProcessError as e:
        if "already in use" in str(e) or "name is already in use" in str(e):
            print("📦 Redis container already exists, starting it...")
            try:
                subprocess.run(["docker", "start", "dataforge-redis"], check=True)
                time.sleep(2)
                if check_redis():
                    print("✅ Redis is running!")
                    return True
            except subprocess.CalledProcessError:
                pass
        
        print("❌ Failed to start Redis with Docker")
        return False


def setup_environment():
    """Set up development environment."""
    print("🔧 Setting up development environment...")
    
    # Create .env file if it doesn't exist
    env_path = Path(".env")
    env_example_path = Path(".env.example")
    
    if not env_path.exists() and env_example_path.exists():
        print("📝 Creating .env file from example...")
        env_path.write_text(env_example_path.read_text())
    
    # Set development environment variables
    os.environ["DEBUG"] = "true"
    os.environ["SKIP_VALIDATION"] = "true"  # Skip API key validation for demo
    os.environ["DEFAULT_LLM_PROVIDER"] = "mock"  # Use mock LLM by default
    
    print("✅ Environment configured for development")


def install_dependencies():
    """Install Python dependencies."""
    print("📦 Installing dependencies...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], 
                      check=True)
        print("✅ Dependencies installed")
        return True
    except subprocess.CalledProcessError:
        print("❌ Failed to install dependencies")
        return False


def run_server():
    """Run the FastAPI development server."""
    print("🚀 Starting DataForge API server...")
    print("📖 API documentation will be available at: http://localhost:8000/docs")
    print("🔍 Health check: http://localhost:8000/api/health")
    print("📊 System stats: http://localhost:8000/api/stats")
    print()
    print("Press Ctrl+C to stop the server")
    print("="*50)
    
    try:
        subprocess.run([
            sys.executable, "-m", "uvicorn", 
            "app.main:app",
            "--reload",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--log-level", "info"
        ])
    except KeyboardInterrupt:
        print("\n👋 Server stopped")


def main():
    """Main development setup and run function."""
    print("🔨 DataForge API - Development Setup")
    print("="*50)
    
    # Setup environment
    setup_environment()
    
    # Install dependencies
    if not install_dependencies():
        return 1
    
    # Check/start Redis
    if not check_redis():
        print("🔴 Redis not running")
        
        # Try to start with Docker
        if not start_redis_docker():
            print()
            print("❌ Could not start Redis automatically.")
            print("Please start Redis manually:")
            print("  - Using Docker: docker run -d -p 6379:6379 redis:7-alpine")
            print("  - Using local Redis: redis-server")
            print("  - Or set DEFAULT_LLM_PROVIDER=mock to run without Redis")
            
            response = input("\nContinue without Redis? (y/N): ")
            if response.lower() != 'y':
                return 1
            
            print("⚠️  Running without Redis - job persistence disabled")
            os.environ["REDIS_URL"] = "redis://nonexistent:6379/0"
    else:
        print("✅ Redis is already running")
    
    print()
    
    # Run the server
    run_server()
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)