import httpx
import asyncio
import os

async def test_auth():
    url = "http://127.0.0.1:8001"
    
    # Try /health (should be public)
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{url}/health")
            print(f"Public /health: {resp.status_code} {resp.json()}")
        except Exception as e:
            print(f"Error connecting to {url}/health: {e}")
            return

        # Try /stats without auth (should be 401)
        resp = await client.get(f"{url}/stats")
        print(f"Protected /stats (no auth): {resp.status_code}")
        
        # Try /stats with WRONG auth
        resp = await client.get(f"{url}/stats", auth=("wrong", "wrong"))
        print(f"Protected /stats (wrong auth): {resp.status_code}")

        # Try /stats with CORRECT auth (default)
        resp = await client.get(f"{url}/stats", auth=("admin", "admin"))
        print(f"Protected /stats (correct auth): {resp.status_code}")

if __name__ == "__main__":
    asyncio.run(test_auth())
