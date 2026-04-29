"""Migration m001: Criar coleção optimization_recommendations."""

import logging
from datetime import datetime, timezone

UTC = timezone.utc  # type: ignore
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)


async def upgrade(
    mongo_client: AsyncIOMotorClient, database_name: str = "neural_hive"
) -> dict[str, Any]:
    """
    Criar coleção optimization_recommendations com índices.

    Args:
        mongo_client: Cliente Motor MongoDB
        database_name: Nome do database

    Returns:
        Dict com resultado da migration
    """
    db = mongo_client[database_name]

    # Verificar se coleção já existe
    existing_collections = await db.list_collection_names()
    if "optimization_recommendations" in existing_collections:
        logger.info("Collection optimization_recommendations already exists")
        return {
            "status": "skipped",
            "reason": "Collection already exists",
            "collection": "optimization_recommendations",
        }

    # Criar coleção
    await db.create_collection("optimization_recommendations")
    logger.info("Collection optimization_recommendations created")

    # Criar índices
    indexes = [
        [("ticket_id", 1)],
        [("workflow_id", 1), ("created_at", -1)],
        [("status", 1), ("created_at", -1)],
        [("recommendations.status", 1), ("recommendations.auto_apply", 1)],
        [("performance_analysis.bottlenecks.issue", 1)],
        [("recommendations.target_type", 1), ("status", 1)],
    ]

    index_names = []
    for index_keys in indexes:
        name = f"idx_{'_'.join(k[0] for k in index_keys)}"
        await db.optimization_recommendations.create_index(index_keys, name=name)
        index_names.append(name)
        logger.info(f"Index {name} created")

    return {
        "status": "success",
        "collection": "optimization_recommendations",
        "indexes_created": index_names,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def downgrade(
    mongo_client: AsyncIOMotorClient, database_name: str = "neural_hive"
) -> dict[str, Any]:
    """
    Remover coleção optimization_recommendations.

    Args:
        mongo_client: Cliente Motor MongoDB
        database_name: Nome do database

    Returns:
        Dict com resultado da rollback
    """
    db = mongo_client[database_name]

    # Verificar se coleção existe
    existing_collections = await db.list_collection_names()
    if "optimization_recommendations" not in existing_collections:
        logger.info("Collection optimization_recommendations does not exist")
        return {
            "status": "skipped",
            "reason": "Collection does not exist",
            "collection": "optimization_recommendations",
        }

    # Dropar coleção
    await db.optimization_recommendations.drop()
    logger.info("Collection optimization_recommendations dropped")

    return {
        "status": "success",
        "collection": "optimization_recommendations",
        "dropped_at": datetime.now(timezone.utc).isoformat(),
    }


async def validate(
    mongo_client: AsyncIOMotorClient, database_name: str = "neural_hive"
) -> dict[str, Any]:
    """
    Valida se a migration foi aplicada corretamente.

    Args:
        mongo_client: Cliente Motor MongoDB
        database_name: Nome do database

    Returns:
        Dict com resultado da validação
    """
    db = mongo_client[database_name]

    # Verificar se coleção existe
    existing_collections = await db.list_collection_names()
    collection_exists = "optimization_recommendations" in existing_collections

    if not collection_exists:
        return {
            "valid": False,
            "reason": "Collection optimization_recommendations does not exist",
        }

    # Verificar índices
    expected_indexes = {
        "idx_ticket_id",
        "idx_workflow_id_created_at",
        "idx_status_created_at",
        "idx_pending_auto_apply",
        "idx_bottleneck_issues",
        "idx_target_type_status",
    }

    actual_indexes = await db.optimization_recommendations.index_information()
    actual_index_names = set(name for name, _ in actual_indexes.items() if name != "_id_")

    missing_indexes = expected_indexes - actual_index_names

    return {
        "valid": len(missing_indexes) == 0,
        "collection_exists": collection_exists,
        "expected_indexes": len(expected_indexes),
        "actual_indexes": len(actual_index_names),
        "missing_indexes": list(missing_indexes) if missing_indexes else [],
    }


async def run_migration(
    mongo_client: AsyncIOMotorClient,
    database_name: str = "neural_hive",
    action: str = "upgrade",
) -> dict[str, Any]:
    """
    Executa migration.

    Args:
        mongo_client: Cliente Motor MongoDB
        database_name: Nome do database
        action: 'upgrade', 'downgrade', ou 'validate'

    Returns:
        Dict com resultado da operação
    """
    logger.info(f"Running migration m001_optimization_recommendations action={action}")

    if action == "upgrade":
        return await upgrade(mongo_client, database_name)
    elif action == "downgrade":
        return await downgrade(mongo_client, database_name)
    elif action == "validate":
        return await validate(mongo_client, database_name)
    else:
        return {
            "status": "error",
            "reason": f"Unknown action: {action}",
        }


# CLI para executar migration standalone
if __name__ == "__main__":
    import asyncio
    import sys

    async def main():
        from src.config.settings import get_settings

        settings = get_settings()
        client = AsyncIOMotorClient(settings.mongodb_url)

        action = sys.argv[1] if len(sys.argv) > 1 else "upgrade"

        result = await run_migration(client, settings.mongodb_database_name, action)

        print(f"Migration result: {result}")

        client.close()

    asyncio.run(main())
