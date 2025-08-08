#!/usr/bin/env python3
"""
Example usage of the DataForge API.
This script demonstrates how to use the API endpoints.
"""
import asyncio
import time
import httpx
import json
from typing import Dict, Any


class DataForgeClient:
    """Simple client for the DataForge API."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        """Initialize the client."""
        self.base_url = base_url
        
    async def health_check(self) -> Dict[str, Any]:
        """Check API health."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/api/health")
            return response.json()
    
    async def generate_data(
        self, 
        product: str, 
        count: int = 5,
        version: str = "v1",
        temperature: float = 0.7
    ) -> str:
        """
        Start a generation job and return job ID.
        
        Args:
            product: Product or topic to generate data for
            count: Number of samples to generate
            version: Prompt template version
            temperature: LLM sampling temperature
            
        Returns:
            Job ID string
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "product": product,
                    "count": count,
                    "version": version,
                    "temperature": temperature
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"Generation failed: {response.text}")
            
            result = response.json()
            return result["job_id"]
    
    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get job status and results."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/api/result/{job_id}")
            
            if response.status_code == 404:
                raise Exception(f"Job {job_id} not found")
            elif response.status_code != 200:
                raise Exception(f"Status check failed: {response.text}")
            
            return response.json()
    
    async def wait_for_completion(
        self, 
        job_id: str, 
        timeout: int = 300,
        poll_interval: int = 2
    ) -> Dict[str, Any]:
        """
        Wait for job completion with polling.
        
        Args:
            job_id: Job ID to wait for
            timeout: Maximum wait time in seconds
            poll_interval: Polling interval in seconds
            
        Returns:
            Final job status
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            status = await self.get_job_status(job_id)
            
            print(f"Job {job_id} status: {status['status']}")
            if status.get('progress'):
                print(f"Progress: {status['progress']}%")
            
            if status['status'] in ['completed', 'error']:
                return status
            
            await asyncio.sleep(poll_interval)
        
        raise TimeoutError(f"Job {job_id} did not complete within {timeout} seconds")
    
    async def validate_request(self, **kwargs) -> Dict[str, Any]:
        """Validate a generation request without creating a job."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/validate",
                json=kwargs
            )
            return response.json()
    
    # Deprecated: /api/stats was removed


async def main():
    """Example usage of the DataForge API."""
    client = DataForgeClient()
    
    try:
        print("🔍 Checking API health...")
        health = await client.health_check()
        print(f"Health status: {health['status']}")
        print(f"Redis connected: {health['redis_connected']}")
        print()
        
        # Example 1: Simple generation
        print("🎯 Example 1: Generating support requests...")
        product = "mobile banking app login feature"
        count = 3
        
        # Validate request first
        validation = await client.validate_request(
            product=product,
            count=count,
            temperature=0.8
        )
        
        print(f"Request validation: {'✅ Valid' if validation['validation']['valid'] else '❌ Invalid'}")
        if validation['validation']['warnings']:
            print(f"Warnings: {validation['validation']['warnings']}")
        print(f"Estimated cost: ${validation['validation']['estimated_cost']:.4f}")
        print(f"Estimated duration: {validation['validation']['estimated_duration']:.1f}s")
        print()
        
        # Start generation
        job_id = await client.generate_data(
            product=product,
            count=count,
            temperature=0.8
        )
        
        print(f"Started generation job: {job_id}")
        
        # Wait for completion
        result = await client.wait_for_completion(job_id)
        
        if result['status'] == 'completed':
            print("\n✅ Generation completed!")
            samples = result['result']['samples']
            print(f"Generated {len(samples)} samples:")
            
            for i, sample in enumerate(samples, 1):
                print(f"\n--- Sample {i} ---")
                print(f"ID: {sample['id']}")
                print(f"Generated at: {sample['generated_at']}")
                print(f"Tokens: {sample['tokens_estimated']}")
                print(f"Text: {sample['text'][:200]}{'...' if len(sample['text']) > 200 else ''}")
            
            total_tokens = result['result']['total_tokens_estimated']
            print(f"\nTotal estimated tokens: {total_tokens}")
            
        else:
            print(f"\n❌ Generation failed: {result.get('error_message', 'Unknown error')}")
        
        print("\n" + "="*50)
        
        # Example 2: Batch generation with different parameters
        print("🎯 Example 2: Different product with higher creativity...")
        
        job_id2 = await client.generate_data(
            product="smart home thermostat connectivity issues",
            count=2,
            temperature=1.0  # Higher creativity
        )
        
        print(f"Started second job: {job_id2}")
        result2 = await client.wait_for_completion(job_id2)
        
        if result2['status'] == 'completed':
            print("\n✅ Second generation completed!")
            for i, sample in enumerate(result2['result']['samples'], 1):
                print(f"\n--- Sample {i} ---")
                print(f"Text: {sample['text'][:150]}{'...' if len(sample['text']) > 150 else ''}")
        
        # Stats endpoint removed; no final stats to fetch
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    print("\n🎉 Examples completed successfully!")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)