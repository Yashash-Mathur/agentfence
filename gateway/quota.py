import time
import uuid
import aiosqlite


class QuotaExhaustedError(Exception):
    """Raised when request quota has been exceeded for the active window."""
    pass


class QuotaManager:
    """
    Atomic Request Quota Manager using SQLite BEGIN IMMEDIATE transactions.
    Eliminates race conditions and over-allocation during concurrent bursts.
    """

    @staticmethod
    def calculate_window_bucket(window_seconds: int, timestamp: float = None) -> int:
        ts = timestamp if timestamp is not None else time.time()
        return int(ts // window_seconds)

    @staticmethod
    async def try_reserve_quota(
        conn: aiosqlite.Connection,
        policy_id: str,
        max_requests: int,
        window_seconds: int,
    ) -> str:
        """
        Atomically checks remaining quota and reserves 1 request.
        Uses BEGIN IMMEDIATE to acquire the SQLite write lock upfront.
        """
        bucket = QuotaManager.calculate_window_bucket(window_seconds)
        reservation_id = str(uuid.uuid4())

        await conn.execute("BEGIN IMMEDIATE;")
        try:
            # Check currently used count in bucket
            async with conn.execute(
                """
                SELECT COALESCE(SUM(allocated_count), 0)
                FROM quota_reservations
                WHERE policy_id = ? AND window_bucket = ?;
                """,
                (policy_id, bucket),
            ) as cursor:
                row = await cursor.fetchone()
                current_count = row[0] if row else 0

            if current_count >= max_requests:
                await conn.execute("ROLLBACK;")
                raise QuotaExhaustedError(
                    f"Quota exhausted for policy '{policy_id}'. Used: {current_count}/{max_requests} in current window."
                )

            # Insert reservation
            await conn.execute(
                """
                INSERT INTO quota_reservations (reservation_id, policy_id, window_bucket, allocated_count)
                VALUES (?, ?, ?, 1);
                """,
                (reservation_id, policy_id, bucket),
            )
            await conn.execute("COMMIT;")
            return reservation_id

        except Exception:
            try:
                await conn.execute("ROLLBACK;")
            except Exception:
                pass
            raise

    @staticmethod
    async def release_reservation(
        conn: aiosqlite.Connection,
        reservation_id: str,
    ):
        """Releases a reservation if execution failed without consuming budget."""
        await conn.execute("BEGIN IMMEDIATE;")
        try:
            await conn.execute(
                "DELETE FROM quota_reservations WHERE reservation_id = ?;",
                (reservation_id,),
            )
            await conn.execute("COMMIT;")
        except Exception:
            await conn.execute("ROLLBACK;")
            raise
