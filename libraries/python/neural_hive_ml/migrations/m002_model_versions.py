"""Migration m002: Create model_versions collection.

Esta migration cria a coleção model_versions para rastrear
versões de modelos de aprovação com metadados e drift metrics.
"""

from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase


async def upgrade(db: AsyncIOMotorDatabase) -> None:
    """
    Criar coleção model_versions com índices.

    Args:
        db: Database Motor
    """
    collection = db.model_versions

    # Criar índices
    await collection.create_index([("version", 1)], unique=True)
    await collection.create_index([("stage", -1), ("created_at", -1)])
    await collection.create_index([("is_active", 1)])
    await collection.create_index([("created_at", -1)])
    await collection.create_index([("mlflow_run_id", 1)])

    print("Migration m002_upgrade: Coleção model_versions criada com 5 índices")


async def downgrade(db: AsyncIOMotorDatabase) -> None:
    """
    Remover coleção model_versions.

    Args:
        db: Database Motor
    """
    await db.model_versions.drop()
    print("Migration m002_downgrade: Coleção model_versions removida")


async def validate(db: AsyncIOMotorDatabase) -> bool:
    """
    Valida se migration foi aplicada.

    Args:
        db: Database Motor

    Returns:
        True se migration está aplicada
    """
    indexes = await db.model_versions.index_information()
    return len(indexes) >= 5  # _id + 4 índices criados


if __name__ == "__main__":
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    import os

    async def main():
        mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
        db_name = os.getenv("MONGODB_DBNAME", "neural_hive")

        client = AsyncIOMotorClient(mongodb_url)
        db = client[db_name]

        action = os.getenv("ACTION", "upgrade")

        if action == "upgrade":
            await upgrade(db)
        elif action == "downgrade":
            await downgrade(db)
        elif action == "validate":
            is_valid = await validate(db)
            print(f"Migration status: {'applied' if is_valid else 'not applied'}")

        client.close()

    asyncio.run(main())
