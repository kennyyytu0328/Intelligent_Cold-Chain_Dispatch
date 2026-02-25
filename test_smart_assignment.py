#!/usr/bin/env python
"""
Quick test script for Smart Assignment API.

Tests the recommendation endpoints without needing frontend UI.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx


BASE_URL = "http://localhost:8000/api/v1"
USERNAME = "admin"
PASSWORD = "admin123"


async def get_token() -> str:
    """Login and get JWT token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/auth/login",
            data={"username": USERNAME, "password": PASSWORD},
        )
        if resp.status_code != 200:
            print(f"❌ Login failed: {resp.status_code}")
            print(resp.text)
            sys.exit(1)

        token = resp.json()["access_token"]
        print("✅ Login successful")
        return token


async def test_preview(token: str):
    """Test POST /recommendations/preview endpoint."""
    print("\n" + "="*60)
    print("TEST 1: Preview Recommendation (Ad-hoc Coordinates)")
    print("="*60)

    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "stop_coordinates": [
            {"latitude": 25.033, "longitude": 121.565},
            {"latitude": 25.047, "longitude": 121.517},
            {"latitude": 25.020, "longitude": 121.540},
        ],
        "top_k": 5,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BASE_URL}/recommendations/preview",
            headers=headers,
            json=payload,
        )

    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ Preview successful")
        print(f"   Route signature: {data.get('route_signature', [])}")
        print(f"   Recommendations: {len(data.get('recommendations', []))}")

        for i, rec in enumerate(data.get("recommendations", [])[:3], 1):
            print(f"\n   #{i} {rec['license_plate']}")
            print(f"      Driver: {rec.get('driver_name', 'N/A')}")
            print(f"      Affinity: {rec['affinity_score']}")
            print(f"      Confidence: {rec['confidence']}")
            print(f"      Cells analyzed: {len(rec.get('cell_details', []))}")
    elif resp.status_code == 404:
        print(f"⚠️  No available vehicles found (404)")
        print("   This is expected if you haven't created vehicles yet")
    else:
        print(f"❌ Preview failed: {resp.status_code}")
        print(resp.text)


async def test_route_recommendation(token: str):
    """Test GET /recommendations/{route_id} endpoint."""
    print("\n" + "="*60)
    print("TEST 2: Route Recommendation")
    print("="*60)

    # First, try to get a route from the system
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Get routes
        routes_resp = await client.get(f"{BASE_URL}/routes", headers=headers)

        if routes_resp.status_code != 200:
            print("⚠️  Could not fetch routes - skipping route recommendation test")
            return

        routes_data = routes_resp.json()
        routes = routes_data.get("items", [])

        if not routes:
            print("⚠️  No routes found in system - skipping route recommendation test")
            print("   Create a route via /api/v1/optimization first")
            return

        # Find a route with route_signature
        test_route = None
        for route in routes:
            if route.get("route_signature"):
                test_route = route
                break

        if not test_route:
            print("⚠️  No routes with route_signature found")
            print("   Run an optimization job or use backfill script")
            return

        route_id = test_route["id"]
        print(f"   Testing with route: {test_route.get('route_code', route_id)}")

        # Test recommendation
        rec_resp = await client.get(
            f"{BASE_URL}/recommendations/{route_id}",
            headers=headers,
            params={"top_k": 5},
        )

        if rec_resp.status_code == 200:
            data = rec_resp.json()
            print(f"✅ Route recommendation successful")
            print(f"   Route signature: {len(data.get('route_signature', []))} cells")
            print(f"   Recommendations: {len(data.get('recommendations', []))}")

            for i, rec in enumerate(data.get("recommendations", [])[:3], 1):
                print(f"\n   #{i} {rec['license_plate']}")
                print(f"      Affinity: {rec['affinity_score']} ({rec['confidence']})")
        elif rec_resp.status_code == 422:
            print(f"⚠️  Route has invalid signature (422)")
        elif rec_resp.status_code == 404:
            print(f"⚠️  No vehicles or route not found (404)")
        else:
            print(f"❌ Failed: {rec_resp.status_code}")
            print(rec_resp.text)


async def test_admin_recalculate(token: str):
    """Test POST /recommendations/admin/recalculate endpoint."""
    print("\n" + "="*60)
    print("TEST 3: Admin Recalculate (Stub)")
    print("="*60)

    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BASE_URL}/recommendations/admin/recalculate",
            headers=headers,
        )

    if resp.status_code == 202:
        data = resp.json()
        print(f"✅ Recalculate queued (stub)")
        print(f"   Message: {data.get('message')}")
    else:
        print(f"❌ Failed: {resp.status_code}")
        print(resp.text)


async def main():
    """Run all tests."""
    print("🚀 Testing Smart Assignment API")
    print(f"   Base URL: {BASE_URL}")
    print(f"   Username: {USERNAME}")

    try:
        # Login
        token = await get_token()

        # Run tests
        await test_preview(token)
        await test_route_recommendation(token)
        await test_admin_recalculate(token)

        print("\n" + "="*60)
        print("✅ All tests completed")
        print("="*60)

    except httpx.ConnectError:
        print("\n❌ Cannot connect to API")
        print("   Make sure the backend is running: uvicorn app.main:app --reload --port 8000")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
