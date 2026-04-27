"""Migration m002: Criar coleção ab_test_results para persistência de A/B Testing."""

import logging
from datetime import datetime, timezone

UTC = UTC  # type: ignore
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)


async def upgrade(
    mongo_client: AsyncIOMotorClient, database_name: str = "neural_hive"
) -> dict[str, Any]:
    """
    Criar coleção ab_test_results com índices.

    Args:
        mongo_client: Cliente Motor MongoDB
        database_name: Nome do database

    Returns:
        Dict com resultado da migration
    """
    db = mongo_client[database_name]

    # Verificar se coleção já existe
    existing_collections = await db.list_collection_names()
    if "ab_test_results" in existing_collections:
        logger.info("Collection ab_test_results already exists")
        return {
            "status": "skipped",
            "reason": "Collection already exists",
            "collection": "ab_test_results",
        }

    # Criar coleção
    await db.create_collection("ab_test_results")
    logger.info("Collection ab_test_results created")

    # Criar índices conforme especificado no EPIC-202-01
    indexes = [
        [("experiment_id", 1)],  # 202.03
        [("created_at", -1)],  # 202.04
        [("status", 1), ("created_at", -1)],  # 202.05
        [("statistical_recommendation", 1)],  # 202.06
    ]

    index_names = []
    for index_keys in indexes:
        name = f"idx_{'_'.join(k[0] for k in index_keys)}"
        await db.ab_test_results.create_index(index_keys, name=name)
        index_names.append(name)
        logger.info(f"Index {name} created")

    return {
        "status": "success",
        "collection": "ab_test_results",
        "indexes_created": index_names,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def downgrade(
    mongo_client: AsyncIOMotorClient, database_name: str = "neural_hive"
) -> dict[str, Any]:
    """
    Remover coleção ab_test_results.

    Args:
        mongo_client: Cliente Motor MongoDB
        database_name: Nome do database

    Returns:
        Dict com resultado da rollback
    """
    db = mongo_client[database_name]

    # Verificar se coleção existe
    existing_collections = await db.list_collection_names()
    if "ab_test_results" not in existing_collections:
        logger.info("Collection ab_test_results does not exist")
        return {
            "status": "skipped",
            "reason": "Collection does not exist",
            "collection": "ab_test_results",
        }

    # Dropar coleção
    await db.ab_test_results.drop()
    logger.info("Collection ab_test_results dropped")

    return {
        "status": "success",
        "collection": "ab_test_results",
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
    collection_exists = "ab_test_results" in existing_collections

    if not collection_exists:
        return {
            "valid": False,
            "reason": "Collection ab_test_results does not exist",
        }

    # Verificar índices
    expected_indexes = {
        "idx_experiment_id",
        "idx_created_at",
        "idx_status_created_at",
        "idx_statistical_recommendation",
    }

    actual_indexes = await db.ab_test_results.index_information()
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
    logger.info(f"Running migration m002_ab_test_results action={action}")

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
