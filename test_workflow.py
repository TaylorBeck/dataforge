#!/usr/bin/env python3
"""
Full workflow test for DataForge API.
This script tests the complete generation workflow from job creation to result retrieval.
"""
import asyncio
import os
import sys
import time
import json
from typing import Dict, Any
import httpx


class WorkflowTester:
    """Test the complete DataForge API workflow."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        """Initialize workflow tester."""
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
        
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.client.aclose()
    
    def print_section(self, title: str):
        """Print section header."""
        print(f"\n{'='*60}")
        print(f"🧪 {title}")
        print(f"{'='*60}")
    
    def print_result(self, success: bool, message: str):
        """Print test result."""
        icon = "✅" if success else "❌"
        print(f"{icon} {message}")
    
    async def test_health_check(self) -> bool:
        """Test health check endpoint."""
        self.print_section("Health Check")
        
        try:
            response = await self.client.get(f"{self.base_url}/api/health")
            
            if response.status_code == 200:
                data = response.json()
                self.print_result(True, f"Health check passed: {data['status']}")
                self.print_result(True, f"Redis connected: {data['redis_connected']}")
                return True
            else:
                self.print_result(False, f"Health check failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.print_result(False, f"Health check error: {e}")
            return False
    
    async def test_system_stats(self) -> bool:
        """Test system stats endpoint."""
        self.print_section("System Statistics")
        
        try:
            response = await self.client.get(f"{self.base_url}/api/stats")
            
            if response.status_code == 200:
                data = response.json()
                self.print_result(True, "System stats retrieved")
                print(f"   🔧 LLM Provider: {data.get('llm', {}).get('provider', 'unknown')}")
                print(f"   📊 Active Jobs: {data.get('jobs', {}).get('active_jobs', 0)}")
                print(f"   🎯 Max Samples: {data.get('limits', {}).get('max_samples_per_request', 'unknown')}")
                return True
            else:
                self.print_result(False, f"Stats failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.print_result(False, f"Stats error: {e}")
            return False
    
    async def test_llm_connection(self) -> bool:
        """Test LLM connection."""
        self.print_section("LLM Connection Test")
        
        try:
            response = await self.client.post(f"{self.base_url}/api/test-llm")
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', {})
                health_ok = results.get('health_check', False)
                generation_ok = results.get('generation_test', False)
                
                self.print_result(health_ok, f"LLM health check: {health_ok}")
                self.print_result(generation_ok, f"LLM generation test: {generation_ok}")
                
                if 'test_response' in results:
                    print(f"   📝 Test response: {results['test_response'][:100]}...")
                
                return health_ok and generation_ok
            else:
                self.print_result(False, f"LLM test failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.print_result(False, f"LLM test error: {e}")
            return False
    
    async def test_validation(self) -> bool:
        """Test request validation."""
        self.print_section("Request Validation")
        
        # Test valid request
        try:
            valid_request = {
                "product": "test product",
                "count": 3,
                "temperature": 0.7
            }
            
            response = await self.client.post(
                f"{self.base_url}/api/validate",
                json=valid_request
            )
            
            if response.status_code == 200:
                data = response.json()
                validation = data.get('validation', {})
                self.print_result(validation.get('valid', False), "Valid request validation")
                
                if 'estimated_cost' in validation:
                    print(f"   💰 Estimated cost: ${validation['estimated_cost']:.4f}")
                if 'estimated_duration' in validation:
                    print(f"   ⏱️  Estimated duration: {validation['estimated_duration']}s")
                    
            else:
                self.print_result(False, f"Validation failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.print_result(False, f"Validation error: {e}")
            return False
        
        # Test invalid request
        try:
            invalid_request = {
                "product": "",  # Empty product should fail
                "count": 1000   # Too many samples should fail
            }
            
            response = await self.client.post(
                f"{self.base_url}/api/generate",
                json=invalid_request
            )
            
            if response.status_code in [400, 422]:
                self.print_result(True, "Invalid request properly rejected")
            else:
                self.print_result(False, f"Invalid request not rejected: {response.status_code}")
                
        except Exception as e:
            self.print_result(False, f"Invalid request test error: {e}")
            return False
        
        return True
    
    async def test_generation_workflow(self) -> bool:
        """Test the complete generation workflow."""
        self.print_section("Generation Workflow")
        
        # Create generation job
        generation_request = {
            "product": "mobile banking app login feature",
            "count": 3,
            "version": "v1",
            "temperature": 0.8
        }
        
        try:
            self.print_result(True, "Creating generation job...")
            response = await self.client.post(
                f"{self.base_url}/api/generate",
                json=generation_request
            )
            
            if response.status_code != 200:
                self.print_result(False, f"Job creation failed: {response.status_code}")
                print(f"   Error: {response.text}")
                return False
            
            job_data = response.json()
            job_id = job_data['job_id']
            self.print_result(True, f"Job created: {job_id}")
            
        except Exception as e:
            self.print_result(False, f"Job creation error: {e}")
            return False
        
        # Poll for completion
        self.print_result(True, "Polling for completion...")
        max_attempts = 30  # 30 seconds timeout
        attempt = 0
        
        while attempt < max_attempts:
            try:
                response = await self.client.get(f"{self.base_url}/api/result/{job_id}")
                
                if response.status_code != 200:
                    self.print_result(False, f"Status check failed: {response.status_code}")
                    return False
                
                status_data = response.json()
                status = status_data['status']
                progress = status_data.get('progress')
                
                print(f"   📊 Status: {status}" + (f" ({progress}%)" if progress else ""))
                
                if status == "completed":
                    self.print_result(True, "Generation completed!")
                    
                    # Validate results
                    result = status_data.get('result')
                    if result:
                        samples = result.get('samples', [])
                        total_samples = result.get('total_samples', 0)
                        total_tokens = result.get('total_tokens_estimated', 0)
                        
                        self.print_result(True, f"Generated {total_samples} samples")
                        self.print_result(True, f"Total tokens: {total_tokens}")
                        
                        # Show sample content
                        for i, sample in enumerate(samples[:2], 1):  # Show first 2
                            print(f"   📝 Sample {i}: {sample['text'][:100]}...")
                        
                        return True
                    else:
                        self.print_result(False, "No results in completed job")
                        return False
                
                elif status == "error":
                    error_msg = status_data.get('error_message', 'Unknown error')
                    self.print_result(False, f"Generation failed: {error_msg}")
                    return False
                
                # Wait before next poll
                await asyncio.sleep(1)
                attempt += 1
                
            except Exception as e:
                self.print_result(False, f"Status polling error: {e}")
                return False
        
        self.print_result(False, "Generation timed out")
        return False
    
    async def test_multiple_templates(self) -> bool:
        """Test generation with different templates."""
        self.print_section("Multiple Template Test")
        
        # Test different products to exercise template variety
        test_products = [
            "wireless headphones",
            "project management software", 
            "smart home thermostat"
        ]
        
        job_ids = []
        
        # Create multiple jobs
        for product in test_products:
            try:
                request = {
                    "product": product,
                    "count": 1,
                    "temperature": 0.6
                }
                
                response = await self.client.post(
                    f"{self.base_url}/api/generate",
                    json=request
                )
                
                if response.status_code == 200:
                    job_id = response.json()['job_id']
                    job_ids.append(job_id)
                    self.print_result(True, f"Created job for {product}")
                else:
                    self.print_result(False, f"Failed to create job for {product}")
                    
            except Exception as e:
                self.print_result(False, f"Error creating job for {product}: {e}")
        
        # Wait for all to complete
        if job_ids:
            self.print_result(True, f"Waiting for {len(job_ids)} jobs to complete...")
            await asyncio.sleep(5)  # Give them time to process
            
            completed = 0
            for job_id in job_ids:
                try:
                    response = await self.client.get(f"{self.base_url}/api/result/{job_id}")
                    if response.status_code == 200:
                        status = response.json()['status']
                        if status == "completed":
                            completed += 1
                        
                except Exception:
                    pass
            
            self.print_result(True, f"{completed}/{len(job_ids)} jobs completed")
            return completed > 0
        
        return False
    
    async def test_error_handling(self) -> bool:
        """Test error handling scenarios."""
        self.print_section("Error Handling")
        
        # Test non-existent job
        try:
            response = await self.client.get(f"{self.base_url}/api/result/non-existent-job")
            
            if response.status_code == 404:
                self.print_result(True, "Non-existent job properly returns 404")
            else:
                self.print_result(False, f"Non-existent job returned: {response.status_code}")
                
        except Exception as e:
            self.print_result(False, f"Non-existent job test error: {e}")
            return False
        
        return True
    
    async def run_all_tests(self) -> bool:
        """Run all workflow tests."""
        print("🚀 DataForge API - Workflow Test Suite")
        print(f"🎯 Testing against: {self.base_url}")
        
        tests = [
            ("Health Check", self.test_health_check),
            ("System Stats", self.test_system_stats),
            ("LLM Connection", self.test_llm_connection),
            ("Request Validation", self.test_validation),
            ("Generation Workflow", self.test_generation_workflow),
            ("Multiple Templates", self.test_multiple_templates),
            ("Error Handling", self.test_error_handling)
        ]
        
        results = []
        start_time = time.time()
        
        for test_name, test_func in tests:
            try:
                success = await test_func()
                results.append((test_name, success))
            except Exception as e:
                print(f"❌ {test_name} failed with exception: {e}")
                results.append((test_name, False))
        
        # Print summary
        end_time = time.time()
        print(f"\n{'='*60}")
        print("📋 Test Results Summary")
        print(f"{'='*60}")
        
        passed = 0
        for test_name, success in results:
            icon = "✅" if success else "❌"
            print(f"{icon} {test_name}")
            if success:
                passed += 1
        
        print(f"\n📊 Results: {passed}/{len(results)} tests passed")
        print(f"⏱️  Duration: {end_time - start_time:.1f} seconds")
        
        if passed == len(results):
            print("\n🎉 All tests passed! API is ready for use.")
            return True
        else:
            print(f"\n⚠️  {len(results) - passed} tests failed. Check the API setup.")
            return False


async def main():
    """Run the workflow test."""
    base_url = os.getenv("DATAFORGE_URL", "http://localhost:8000")
    
    async with WorkflowTester(base_url) as tester:
        success = await tester.run_all_tests()
        return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)