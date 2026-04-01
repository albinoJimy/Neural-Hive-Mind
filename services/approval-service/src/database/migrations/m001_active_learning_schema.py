"""
Migration 001: Active Learning Schema

Cria coleções e índices para o sistema de Active Learning:
1. active_learning_queue - Fila de casos prioritários para revisão
2. Adiciona campos novos em specialist_feedback
3. Cria índices otimizados

Executar com:
    python -m src.database.migrations.001_active_learning_schema
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any

# Adicionar projeto ao path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from src.config.settings import get_settings


async def create_active_learning_queue_collection(client: AsyncIOMotorClient, db_name: str) -> None:
    """
    Cria coleção active_learning_queue com índices.

    Schema:
    - queue_id: str (unique)
    - plan_id: str (indexed)
    - intent_text: str (opcional)
    - intent_preview: str
    - information_value: float (0-1, indexed)
    - priority_reason: str
    - domain: str (opcional, indexed)
    - confidence: float (opcional, indexed)
    - predicted_decision: str (opcional)
    - status: str (pending|in_review|completed|cancelled, indexed)
    - assigned_to: str (opcional)
    - claimed_at: datetime (opcional)
    - expires_at: datetime (opcional, indexed para expiração)
    - completed_at: datetime (opcional)
    - feedback_id: str (opcional)
    - created_at: datetime
    - updated_at: datetime
    """
    db = client[db_name]
    collection = db["active_learning_queue"]

    # Índice único em queue_id
    await collection.create_index("queue_id", unique=True, name="idx_queue_id")

    # Índice em plan_id para lookup rápido
    await collection.create_index("plan_id", name="idx_plan_id")

    # Índice em status para filtrar casos pendentes/em revisão
    await collection.create_index("status", name="idx_status")

    # Índice composto para queries de fila ordenada
    await collection.create_index(
        [("status", 1), ("information_value", -1), ("created_at", 1)],
        name="idx_status_info_value_created",
    )

    # Índice em expires_at para limpeza de claims expirados
    await collection.create_index(
        "expires_at", name="idx_expires_at", expireAfterSeconds=3600  # TTL de 1 hora
    )

    # Índice em domain para análise de balanceamento
    await collection.create_index("domain", name="idx_domain")

    # Índice em confidence para análise de distribuição
    await collection.create_index("confidence", name="idx_confidence")

    # Índice em predicted_decision para análise de classes
    await collection.create_index("predicted_decision", name="idx_predicted_decision")

    print("✓ Coleção active_learning_queue criada com índices")


async def update_specialist_feedback_collection(client: AsyncIOMotorClient, db_name: str) -> None:
    """
    Adiciona campos novos em specialist_feedback para active learning.

    Campos adicionados:
    - balanced_dataset: bool (default=False)
        Marca se este feedback foi coletado via active learning
        para balancear o dataset

    - collection_method: str (opcional)
        Método de coleta: 'automatic', 'active_learning', 'manual'

    - information_value: float (opcional)
        Valor informacional calculado no momento da coleta (0-1)

    - priority_reason: str (opcional)
        Razão pela qual este caso foi priorizado para coleta
    """
    db = client[db_name]
    collection = db["specialist_feedback"]

    # Adicionar campo balanced_dataset com default False
    await collection.update_many(
        {"balanced_dataset": {"$exists": False}}, {"$set": {"balanced_dataset": False}}
    )

    # Adicionar índice em balanced_dataset para queries filtradas
    await collection.create_index("balanced_dataset", name="idx_balanced_dataset")

    # Adicionar índice em collection_method
    await collection.create_index("collection_method", name="idx_collection_method")

    # Adicionar índice composto para análise de dados balanceados
    await collection.create_index(
        [("balanced_dataset", 1), ("human_recommendation", 1)], name="idx_balanced_recommendation"
    )

    print("✓ Coleção specialist_feedback atualizada com campos de active learning")


async def verify_schema(client: AsyncIOMotorClient, db_name: str) -> Dict[str, Any]:
    """Verifica e retorna informações sobre o schema criado."""
    db = client[db_name]
    result = {"timestamp": datetime.now(timezone.utc).isoformat(), "collections": {}, "indexes": {}}

    # Verificar active_learning_queue
    if "active_learning_queue" in await db.list_collection_names():
        queue_collection = db["active_learning_queue"]
        result["collections"]["active_learning_queue"] = "exists"
        result["indexes"]["active_learning_queue"] = [
            idx["name"] for idx in await queue_collection.list_indexes()
        ]

    # Verificar specialist_feedback
    if "specialist_feedback" in await db.list_collection_names():
        feedback_collection = db["specialist_feedback"]
        result["collections"]["specialist_feedback"] = "exists"
        result["indexes"]["specialist_feedback"] = [
            idx["name"] for idx in await feedback_collection.list_indexes()
        ]

        # Contar documentos com balanced_dataset
        balanced_count = await feedback_collection.count_documents({"balanced_dataset": True})
        result["balanced_feedbacks_count"] = balanced_count

    return result


async def run_migration() -> None:
    """Executa a migration completa."""
    print("=" * 60)
    print("Migration 001: Active Learning Schema")
    print("=" * 60)

    settings = get_settings()

    # Conectar ao MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db_name = settings.mongodb_database

    print(f"\nConectado ao MongoDB: {settings.mongodb_uri}")
    print(f"Database: {db_name}\n")

    try:
        # Criar coleção active_learning_queue
        print("1. Criando coleção active_learning_queue...")
        await create_active_learning_queue_collection(client, db_name)

        # Atualizar specialist_feedback
        print("\n2. Atualizando coleção specialist_feedback...")
        await update_specialist_feedback_collection(client, db_name)

        # Verificar schema
        print("\n3. Verificando schema criado...")
        result = await verify_schema(client, db_name)

        print("\n" + "=" * 60)
        print("Migration concluída com sucesso!")
        print("=" * 60)
        print(f"\nColeções criadas/atualizadas:")
        for collection, status in result["collections"].items():
            print(f"  - {collection}: {status}")

        if "balanced_feedbacks_count" in result:
            print(f"\nFeedbacks balanceados: {result['balanced_feedbacks_count']}")

    except Exception as e:
        print(f"\n❌ Erro na migration: {e}")
        raise
    finally:
        client.close()
        print("\nConexão MongoDB encerrada.")


if __name__ == "__main__":
    asyncio.run(run_migration())
