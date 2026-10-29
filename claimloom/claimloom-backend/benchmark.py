import time
import httpx
import numpy as np
import asyncio

async def fetch_scan(client, url, payload):
    start = time.time()
    try:
        resp = await client.post(url, json=payload, timeout=10.0)
        return time.time() - start if resp.status_code == 200 else None
    except Exception:
        return None

async def run_benchmark():
    print("Initiating p50/p95 Latency Benchmark (50 concurrent requests)...")
    url = "http://localhost:8000/api/scan-text"
    payload = {"text": "Checking the 110 km battery range specification.", "channel": "general"}
    
    async with httpx.AsyncClient() as client:
        tasks = [fetch_scan(client, url, payload) for _ in range(50)]
        times = await asyncio.gather(*tasks)
        
    valid_times = [t for t in times if t is not None]
    
    if not valid_times:
        print("Error: No successful responses. Ensure Pratik's FastAPI server is running on port 8000.")
        return

    p50 = np.percentile(valid_times, 50) * 1000
    p95 = np.percentile(valid_times, 95) * 1000
    
    print("\n=== Benchmark Results ===")
    print(f"Successful Requests: {len(valid_times)}/50")
    print(f"p50 Latency (Median):  {p50:.2f} ms")
    print(f"p95 Latency (Tail):    {p95:.2f} ms")
    print("=========================")

if __name__ == "__main__":
    asyncio.run(run_benchmark())