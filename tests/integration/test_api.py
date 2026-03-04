"""Integration tests for the dashboard API.

These tests require a running database. Skip if not available.
For CI, run with: docker compose up timescaledb -d && pytest tests/integration/
"""
import pytest

# These tests are skipped by default since they need a running DB
pytestmark = pytest.mark.skip(reason="Requires running TimescaleDB instance")


def test_health_endpoint():
    """Test the /api/health endpoint."""
    from httpx import AsyncClient
    from dashboard.api.main import app

    async def _test():
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"

    import asyncio
    asyncio.run(_test())
