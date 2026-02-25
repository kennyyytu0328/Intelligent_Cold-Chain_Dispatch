# -*- coding: utf-8 -*-
"""
Manual test script for the production affinity pipeline.

Logs in, finds a SCHEDULED route, marks it COMPLETED,
then checks that VehicleHexAffinity and RouteHexStat rows were created/updated.

Usage (from project root):
    python scripts/test_affinity_pipeline.py
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import httpx
import psycopg2
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────
API_BASE = "http://localhost:8000/api/v1"
USERNAME = "admin"
PASSWORD = "admin123"

DB_CONFIG = {
    "host": "localhost",
    "port": 5433,   # dev compose uses 5433
    "dbname": "iccdds",
    "user": "iccdds",
    "password": "aigVvI8JkVzbB8qHHubezUW63pi3H3MPpLfNQgeehwY=",
}

OK  = "[OK]"
ERR = "[ERR]"
WARN = "[WARN]"


def login(client):
    resp = client.post(
        f"{API_BASE}/auth/token",
        data={"username": USERNAME, "password": PASSWORD},
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    print(f"{OK} Logged in as {USERNAME}")
    return token


def find_route(client, token):
    """Find any route that is not yet COMPLETED."""
    headers = {"Authorization": f"Bearer {token}"}

    for status in ("SCHEDULED", "IN_PROGRESS", "PLANNING"):
        resp = client.get(f"{API_BASE}/routes", params={"status": status}, headers=headers)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if items:
            print(f"{OK} Found {len(items)} route(s) with status={status}")
            return items[0], headers

    print(f"{ERR} No routes found. Run an optimization first.")
    return None, None


def patch_stops_with_arrival(client, route_id, headers):
    """Set actual_arrival_at on stops so on_time_rate is meaningful."""
    resp = client.get(f"{API_BASE}/routes/{route_id}", headers=headers)
    resp.raise_for_status()
    stops = resp.json().get("stops", [])

    if not stops:
        print("  (no stops to patch)")
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    for stop in stops:
        client.patch(
            f"{API_BASE}/routes/{route_id}/stops/{stop['id']}",
            json={"actual_arrival_at": now_iso, "delivery_status": "COMPLETED"},
            headers=headers,
        )
    print(f"  {OK} Patched {len(stops)} stop(s) with actual_arrival_at")


def mark_completed(client, route_id, headers):
    resp = client.patch(
        f"{API_BASE}/routes/{route_id}/status",
        params={"status": "COMPLETED"},
        headers=headers,
    )
    resp.raise_for_status()
    result = resp.json()
    print(f"{OK} Route {route_id[:8]}... -> status={result['status']}")
    return result


def check_db(route_id, vehicle_id):
    """Query DB directly to verify affinity rows were written."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # Check actual_success_score on route
        cur.execute("SELECT actual_success_score FROM routes WHERE id = %s", (route_id,))
        row = cur.fetchone()
        score = row[0] if row else None
        print(f"\n  Route.actual_success_score = {score}")

        # Check VehicleHexAffinity rows
        cur.execute(
            """
            SELECT h3_index, affinity_score, sample_size, avg_on_time_rate, avg_temp_compliance_rate
            FROM vehicle_hex_affinities
            WHERE vehicle_id = %s
            ORDER BY updated_at DESC
            LIMIT 10
            """,
            (vehicle_id,),
        )
        affinities = cur.fetchall()
        if affinities:
            print(f"\n  VehicleHexAffinity rows for vehicle {vehicle_id[:8]}...:")
            print(f"  {'H3 Cell':<20} {'Score':>6} {'N':>4} {'OnTime':>7} {'TempOK':>7}")
            print(f"  {'-' * 50}")
            for h3, sc, n, ot, tc in affinities:
                print(f"  {h3:<20} {float(sc):>6.3f} {n:>4} {float(ot or 0):>7.3f} {float(tc or 0):>7.3f}")
        else:
            print(f"  {WARN} No VehicleHexAffinity rows found for this vehicle")
            print("  (route may have no route_signature — run backfill_route_signatures.py first)")

        # Check RouteHexStat rows
        cur.execute(
            "SELECT h3_index, total_deliveries FROM route_hex_stats ORDER BY updated_at DESC LIMIT 10"
        )
        stats = cur.fetchall()
        if stats:
            print(f"\n  RouteHexStat rows (most recent):")
            for h3, total in stats:
                print(f"  {h3:<20} deliveries={total}")
        else:
            print(f"\n  {WARN} No RouteHexStat rows found")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"\n  {ERR} DB check failed: {e}")
        print("  Is Docker running? Try: docker-compose -f docker-compose.dev.yml up -d")


def main():
    print("=" * 55)
    print("  Affinity Pipeline Manual Test")
    print("=" * 55)

    with httpx.Client(timeout=10) as client:
        # Step 1: Login
        try:
            token = login(client)
        except Exception as e:
            print(f"{ERR} Login failed: {e}")
            print("  Is the API running? Try: uvicorn app.main:app --reload --port 8000")
            sys.exit(1)

        # Step 2: Find a route
        route, headers = find_route(client, token)
        if not route:
            sys.exit(1)

        route_id = route["id"]
        vehicle_id = route["vehicle_id"]
        sig = route.get("route_signature") or []
        print(f"  Route:     {route.get('route_code')} ({route_id[:8]}...)")
        print(f"  Vehicle:   {vehicle_id[:8]}...")
        print(f"  Signature: {sig[:3]}{'...' if len(sig) > 3 else ''} ({len(sig)} cells)")

        if not sig:
            print(f"\n  {WARN} Route has no route_signature — affinity cells won't be updated.")
            print("  Run: python scripts/backfill_route_signatures.py")

        # Step 3: Patch stops with arrival times (best-effort, skip on error)
        print("\nPatching stops with arrival times...")
        try:
            patch_stops_with_arrival(client, route_id, headers)
        except Exception as e:
            print(f"  {WARN} Could not patch stops ({type(e).__name__}) — skipping.")
            print("  Stops will have no actual_arrival_at; on_time_rate will be 0.")

        # Step 4: Mark COMPLETED (triggers affinity pipeline)
        print("\nMarking route COMPLETED (triggers affinity pipeline)...")
        mark_completed(client, route_id, headers)

        # Step 5: Check DB
        print("\nChecking database for affinity updates...")
        check_db(route_id, vehicle_id)

    print("\n" + "=" * 55)
    print("  Done!")
    print("=" * 55)


if __name__ == "__main__":
    main()
