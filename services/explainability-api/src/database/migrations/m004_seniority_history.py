"""
Migration 004: Seniority History Collection

Cria colecao seniority_history para tracking de mudancas de senioridade:

Schema:
- specialist_id: str (indexed with changed_at)
- domain: str (indexed with changed_at)
- seniority_level: str (trainee|junior|mid_level|senior|expert)
- changed_at: datetime (indexed)
- changed_by: str (user or system that triggered change)
- previous_level: str (opcional)
- reason: str (opcional)

Executar com:
    python -m src.database.migrations.m004_seniority_history
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone

# Adicionar projeto ao path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
import structlog

logger = structlog.get_logger(__name__)


async def upgrade(mongo_client: AsyncIOMotorClient, db_name: str = "neural_hive") -> None:
    """
    Create seniority_history collection with indexes.

    Cria colecao e 3 indices otimizados:
    1. specialist_id + changed_at (para historico de um especialista)
    2. domain + changed_at (para historico por dominio)
    3. changed_at (para consultas temporais)
    """
    db = mongo_client[db_name]

    logger.info("migration_m004_start", collection="seniority_history")

    # Create collection
    await db.create_collection("seniority_history")

    # Get collection reference
    collection = db["seniority_history"]

    # Create index for specialist history (most common query)
    await collection.create_index(
        [("specialist_id", 1), ("changed_at", -1)], name="specialist_id_1_changed_at_-1"
    )

    # Create index for domain history
    await collection.create_index(
        [("domain", 1), ("changed_at", -1)], name="domain_1_changed_at_-1"
    )

    # Create index for temporal queries
    await collection.create_index([("changed_at", 1)], name="changed_at_1")

    logger.info("migration_m004_complete", collection="seniority_history", indexes=3)


async def downgrade(mongo_client: AsyncIOMotorClient, db_name: str = "neural_hive") -> None:
    """
    Drop seniority_history collection.

    ATENCAO: Esta operacao ira apagar todo o historico de senioridade.
    """
    db = mongo_client[db_name]
    await db.drop_collection("seniority_history")
    logger.info("migration_m004_downgrade_complete", collection="seniority_history")


async def verify_schema(client: AsyncIOMotorClient, db_name: str = "neural_hive"):
    """Verifica e retorna informacoes sobre o schema criado."""
    db = client[db_name]
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "collection_exists": False,
        "indexes": [],
    }

    if "seniority_history" in await db.list_collection_names():
        result["collection_exists"] = True
        collection = db["seniority_history"]
        result["indexes"] = [idx["name"] for idx in await collection.list_indexes()]

    return result


async def run_migration() -> None:
    """Executa a migration completa."""
    print("=" * 60)
    print("Migration 004: Seniority History Collection")
    print("=" * 60)

    # Para testes, podemos usar um client mock
    # Em producao, usar settings reais
    try:
        from src.config.settings import get_settings

        settings = get_settings()
        mongo_uri = settings.mongodb_uri
        database = settings.mongodb_database or "neural_hive"
    except ImportError:
        # Fallback para testes
        mongo_uri = "mongodb://localhost:27017"
        database = "neural_hive"

    # Conectar ao MongoDB
    client = AsyncIOMotorClient(mongo_uri)

    print(f"\nConectado ao MongoDB: {mongo_uri}")
    print(f"Database: {database}\n")

    try:
        # Executar upgrade
        print("1. Criando colecao seniority_history...")
        await upgrade(client, database)

        # Verificar schema
        print("\n2. Verificando schema criado...")
        result = await verify_schema(client, database)

        print("\n" + "=" * 60)
        print("Migration concluida com sucesso!")
        print("=" * 60)
        print(f"\nColecao: {'seniority_history' if result['collection_exists'] else 'N/A'}")
        print(f"Indices criados: {len(result['indexes'])}")
        for idx in result["indexes"]:
            print(f"  - {idx}")

    except Exception as e:
        print(f"\n Erro na migration: {e}")
        raise
    finally:
        client.close()
        print("\nConexao MongoDB encerrada.")


if __name__ == "__main__":
    asyncio.run(run_migration())
