import asyncio
import os
import pytest
import pytest_asyncio
from storage.database import get_db_connection, init_schema
from gateway.quota import QuotaManager, QuotaExhaustedError

TEST_DB = "test_quota_concurrent.db"


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except OSError:
            pass
    await init_schema(TEST_DB)
    yield
    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_atomic_quota_limits_concurrent_burst():
    # Allow exactly 5 requests
    max_requests = 5
    policy_id = "test-concurrent-pol"
    window_seconds = 3600

    async def attempt_reserve():
        conn = await get_db_connection(TEST_DB)
        try:
            res_id = await QuotaManager.try_reserve_quota(
                conn, policy_id, max_requests, window_seconds
            )
            return True, res_id
        except QuotaExhaustedError:
            return False, None
        finally:
            await conn.close()

    # Launch 20 simultaneous concurrent reservation attempts
    results = await asyncio.gather(*[attempt_reserve() for _ in range(20)])

    successes = [r for r in results if r[0] is True]
    exhaustions = [r for r in results if r[0] is False]

    # Invariant: exactly 5 succeed, exactly 15 are blocked
    assert len(successes) == 5
    assert len(exhaustions) == 15
