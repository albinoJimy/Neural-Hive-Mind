"""
Migration m003: Create insights collections with indexes and TTL.
"""
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient


async def upgrade(client: AsyncIOMotorClient, database: str) -> None:
    """Create insights and time_series_cache collections with indexes."""
    db = client[database]

    # Create insights collection
    insights = db.insights

    # Create indexes for insights
    insights_indexes = [
        ([("insight_id", 1)], {"unique": True, "name": "insight_id_unique"}),
        ([("analysis_type", 1), ("created_at", -1)], {"name": "analysis_type_created_idx"}),
        ([("metadata.source", 1), ("metadata.source_id", 1)], {"name": "source_idx"}),
        ([("tags", 1)], {"name": "tags_idx"}),
        ([("status", 1), ("created_at", -1)], {"name": "status_created_idx"}),
    ]

    for keys, options in insights_indexes:
        try:
            await insights.create_index(keys, **options)
        except Exception as e:
            print(f"Warning: Failed to create index {keys}: {e}")

    # TTL index - 90 days
    try:
        await insights.create_index(
            [("expires_at", 1)],
            expireAfterSeconds=0,
            name="expires_at_ttl"
        )
    except Exception as e:
        print(f"Warning: Failed to create TTL index: {e}")

    # Create time_series_cache collection
    ts_cache = db.time_series_cache

    # Create indexes for time_series_cache
    ts_cache_indexes = [
        ([("cache_key", 1)], {"unique": True, "name": "cache_key_unique"}),
    ]

    for keys, options in ts_cache_indexes:
        try:
            await ts_cache.create_index(keys, **options)
        except Exception as e:
            print(f"Warning: Failed to create index {keys}: {e}")

    # TTL index - 24 hours
    try:
        await ts_cache.create_index(
            [("expires_at", 1)],
            expireAfterSeconds=0,
            name="expires_at_ttl"
        )
    except Exception as e:
        print(f"Warning: Failed to create TTL index: {e}")

    print("Migration m003: Insights collections created successfully")


async def downgrade(client: AsyncIOMotorClient, database: str) -> None:
    """Drop insights collections."""
    db = client[database]

    try:
        await db.insights.drop()
    except Exception:
        pass

    try:
        await db.time_series_cache.drop()
    except Exception:
        pass

    print("Migration m003: Insights collections dropped")
