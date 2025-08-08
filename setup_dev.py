#!/usr/bin/env python3
"""
Development setup script for DataForge API.
This script handles dependency installation, environment setup, and service verification.
"""
import os
import sys
import subprocess
import time
import json
from pathlib import Path
from typing import Dict, Any, List


class DevSetup:
    """Development environment setup manager."""
    
    def __init__(self):
        self.project_root = Path.cwd()
        self.env_file = self.project_root / ".env"
        self.requirements_file = self.project_root / "requirements.txt"
        self.redis_container_name = "dataforge-redis"
        
    def print_banner(self):
        """Print setup banner."""
        print("🔨" + "="*60)
        print("🚀 DataForge API - Development Setup")
        print("🔨" + "="*60)
        print()
    
    def check_python_version(self) -> bool:
        """Check if Python version is compatible."""
        version = sys.version_info
        print(f"🐍 Python version: {version.major}.{version.minor}.{version.micro}")
        
        if version.major != 3 or version.minor < 8:
            print("❌ Python 3.8+ is required")
            return False
        
        print("✅ Python version is compatible")
        return True
    
    def check_dependencies(self) -> List[str]:
        """Check which dependencies are missing."""
        missing = []
        
        try:
            import fastapi
            print("✅ FastAPI available")
        except ImportError:
            missing.append("fastapi")
            print("❌ FastAPI not installed")
        
        try:
            import uvicorn
            print("✅ Uvicorn available")
        except ImportError:
            missing.append("uvicorn")
            print("❌ Uvicorn not installed")
        
        try:
            import redis
            print("✅ Redis client available")
        except ImportError:
            missing.append("redis")
            print("❌ Redis client not installed")
        
        try:
            import pydantic
            print("✅ Pydantic available")
        except ImportError:
            missing.append("pydantic")
            print("❌ Pydantic not installed")
        
        try:
            import jinja2
            print("✅ Jinja2 available")
        except ImportError:
            missing.append("jinja2")
            print("❌ Jinja2 not installed")
        
        return missing
    
    def install_dependencies(self) -> bool:
        """Install Python dependencies."""
        if not self.requirements_file.exists():
            print("❌ requirements.txt not found")
            return False
        
        print("📦 Installing dependencies...")
        try:
            subprocess.run([
                sys.executable, "-m", "pip", "install", "-r", str(self.requirements_file)
            ], check=True, capture_output=True, text=True)
            print("✅ Dependencies installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install dependencies: {e}")
            print(f"Error output: {e.stderr}")
            return False
    
    def setup_environment(self) -> bool:
        """Set up environment file."""
        if not self.env_file.exists():
            env_example = self.project_root / ".env.example"
            if env_example.exists():
                print("📝 Creating .env from example...")
                self.env_file.write_text(env_example.read_text())
            else:
                print("📝 Creating basic .env file...")
                env_content = """# DataForge API Configuration
DEBUG=true
DEFAULT_LLM_PROVIDER=mock
REDIS_URL=redis://localhost:6379/0
SKIP_VALIDATION=true
API_TITLE=DataForge API
API_VERSION=1.0.0
MAX_SAMPLES_PER_REQUEST=20
MAX_CONCURRENT_JOBS=5

# Add your API keys here when ready:
# OPENAI_API_KEY=your_key_here
# ANTHROPIC_API_KEY=your_key_here
"""
                self.env_file.write_text(env_content)
            
            print("✅ Environment file created")
        else:
            print("✅ Environment file already exists")
        
        return True
    
    def check_docker(self) -> bool:
        """Check if Docker is available."""
        try:
            result = subprocess.run(
                ["docker", "--version"], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            if result.returncode == 0:
                print(f"✅ Docker available: {result.stdout.strip()}")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        print("❌ Docker not available")
        return False
    
    def check_redis_connection(self) -> bool:
        """Check if Redis is accessible."""
        try:
            import redis
            r = redis.Redis(host='localhost', port=6379, db=0, socket_timeout=2)
            r.ping()
            print("✅ Redis is running and accessible")
            return True
        except Exception as e:
            print(f"❌ Redis not accessible: {e}")
            return False
    
    def start_redis_docker(self) -> bool:
        """Start Redis using Docker."""
        if not self.check_docker():
            return False
        
        print("🐳 Starting Redis with Docker...")
        
        # Check if container already exists
        try:
            result = subprocess.run([
                "docker", "ps", "-a", "--filter", f"name={self.redis_container_name}", "--format", "{{.Names}}"
            ], capture_output=True, text=True)
            
            if self.redis_container_name in result.stdout:
                print("📦 Redis container exists, starting it...")
                subprocess.run(["docker", "start", self.redis_container_name], check=True)
            else:
                print("📦 Creating new Redis container...")
                subprocess.run([
                    "docker", "run", "-d",
                    "--name", self.redis_container_name,
                    "-p", "6379:6379",
                    "redis:7-alpine"
                ], check=True)
            
            # Wait for Redis to be ready
            print("⏳ Waiting for Redis to be ready...")
            for i in range(15):
                if self.check_redis_connection():
                    return True
                time.sleep(1)
                print(f"   Attempt {i+1}/15...")
            
            print("❌ Redis failed to start properly")
            return False
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to start Redis: {e}")
            return False
    
    def test_app_imports(self) -> bool:
        """Test if the app can be imported."""
        print("🧪 Testing application imports...")
        
        try:
            from app.config import get_settings
            print("✅ Config import successful")
        except Exception as e:
            print(f"❌ Config import failed: {e}")
            return False
        
        try:
            from app.main import app
            print("✅ Main app import successful")
        except Exception as e:
            print(f"❌ Main app import failed: {e}")
            return False
        
        try:
            from app.utils.llm_client import get_llm_client
            print("✅ LLM client import successful")
        except Exception as e:
            print(f"❌ LLM client import failed: {e}")
            return False
        
        return True
    
    def test_basic_functionality(self) -> bool:
        """Test basic app functionality."""
        print("🧪 Testing basic functionality...")
        
        try:
            # Set environment for testing
            os.environ["DEBUG"] = "true"
            os.environ["DEFAULT_LLM_PROVIDER"] = "mock"
            os.environ["SKIP_VALIDATION"] = "true"
            
            from app.config import get_settings
            settings = get_settings()
            print(f"✅ Settings loaded: {settings.api_title}")
            
            from app.utils.llm_client import get_llm_client
            client = get_llm_client("mock")
            print("✅ Mock LLM client created")
            
            # Test template service
            from app.services.prompt_service import get_template_service
            template_service = get_template_service()
            templates = template_service.list_templates()
            print(f"✅ Found {len(templates)} templates")
            
            return True
            
        except Exception as e:
            print(f"❌ Basic functionality test failed: {e}")
            return False
    
    def get_startup_instructions(self, redis_running: bool) -> str:
        """Get startup instructions based on setup state."""
        instructions = []
        
        instructions.append("🚀 Setup complete! Here's how to start the API:")
        instructions.append("")
        
        if not redis_running:
            instructions.append("⚠️  Redis is not running. You have these options:")
            instructions.append("   1. Start with Docker: docker run -d -p 6379:6379 redis:7-alpine")
            instructions.append("   2. Install and start Redis locally")
            instructions.append("   3. Continue without Redis (jobs won't persist)")
            instructions.append("")
        
        instructions.append("🎯 Start the API server:")
        instructions.append("   python run_dev.py")
        instructions.append("   # OR")
        instructions.append("   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")
        instructions.append("")
        instructions.append("📖 Once running, visit:")
        instructions.append("   • API docs: http://localhost:8000/docs")
        instructions.append("   • Health check: http://localhost:8000/api/health")
    # /api/stats removed
        instructions.append("")
        instructions.append("🧪 Test with the example script:")
        instructions.append("   python example_usage.py")
        
        return "\n".join(instructions)
    
    def run_setup(self) -> bool:
        """Run the complete setup process."""
        self.print_banner()
        
        # Check Python version
        if not self.check_python_version():
            return False
        
        print()
        print("📋 Checking dependencies...")
        missing_deps = self.check_dependencies()
        
        if missing_deps:
            print(f"\n📦 Missing dependencies: {', '.join(missing_deps)}")
            install = input("Install missing dependencies? (y/N): ").lower()
            if install == 'y':
                if not self.install_dependencies():
                    return False
                print("\n✅ Dependencies installed, re-checking...")
                missing_deps = self.check_dependencies()
                if missing_deps:
                    print(f"❌ Still missing: {', '.join(missing_deps)}")
                    return False
            else:
                print("❌ Cannot continue without dependencies")
                return False
        
        print()
        print("📝 Setting up environment...")
        if not self.setup_environment():
            return False
        
        print()
        print("🔍 Checking Redis...")
        redis_running = self.check_redis_connection()
        
        if not redis_running:
            start_redis = input("Redis not running. Try to start with Docker? (y/N): ").lower()
            if start_redis == 'y':
                redis_running = self.start_redis_docker()
        
        print()
        if not self.test_app_imports():
            return False
        
        print()
        if not self.test_basic_functionality():
            return False
        
        print()
        print("="*60)
        print(self.get_startup_instructions(redis_running))
        print("="*60)
        
        return True


def main():
    """Main setup function."""
    setup = DevSetup()
    success = setup.run_setup()
    
    if success:
        print("\n🎉 Setup completed successfully!")
        return 0
    else:
        print("\n💥 Setup failed. Check the errors above.")
        return 1


if __name__ == "__main__":
    exit(main())