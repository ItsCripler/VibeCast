"""Show a lost update and the atomic counter update used by VibeCast rollups."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import psycopg
from app.config import settings

COUNTER_NAME = "concurrency-demo"


def dsn() -> str:
    return settings.database_migration_url.replace("postgresql+psycopg://", "postgresql://", 1)


def set_value(value: int) -> None:
    with psycopg.connect(dsn()) as conn:
        conn.execute(
            "INSERT INTO demo_counters (name, value) VALUES (%s, %s) "
            "ON CONFLICT (name) DO UPDATE SET value = EXCLUDED.value",
            (COUNTER_NAME, value),
        )


def read_value() -> int:
    with psycopg.connect(dsn()) as conn:
        return conn.execute("SELECT value FROM demo_counters WHERE name = %s", (COUNTER_NAME,)).fetchone()[0]


def unsafe_increment(barrier: Barrier) -> None:
    with psycopg.connect(dsn()) as conn:
        stale_value = conn.execute(
            "SELECT value FROM demo_counters WHERE name = %s", (COUNTER_NAME,)
        ).fetchone()[0]
        barrier.wait(timeout=10)
        conn.execute("UPDATE demo_counters SET value = %s WHERE name = %s",
                     (stale_value + 1, COUNTER_NAME))


def atomic_increment(barrier: Barrier) -> None:
    with psycopg.connect(dsn()) as conn:
        barrier.wait(timeout=10)
        conn.execute("UPDATE demo_counters SET value = value + 1 WHERE name = %s", (COUNTER_NAME,))


def run_pair(operation) -> None:
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(operation, barrier) for _ in range(2)]
        for future in futures:
            future.result()


def main() -> None:
    with psycopg.connect(dsn()) as conn:
        conn.execute("SELECT 1 FROM demo_counters WHERE name = %s", (COUNTER_NAME,))
    set_value(0)
    run_pair(unsafe_increment)
    unsafe_result = read_value()
    set_value(0)
    run_pair(atomic_increment)
    atomic_result = read_value()
    print(f"Two stale read/modify/write transactions: {unsafe_result} (expected 1)")
    print(f"Two atomic database increments: {atomic_result} (expected 2)")
    if unsafe_result != 1 or atomic_result != 2:
        raise SystemExit("Concurrency demonstration produced an unexpected result")


if __name__ == "__main__":
    main()
