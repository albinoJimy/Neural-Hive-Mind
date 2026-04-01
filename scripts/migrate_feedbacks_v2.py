#!/usr/bin/env python3
"""
Script de migração para enriquecer feedbacks existentes com dados da opinião.

Migra feedbacks da versão 1.0.0 para 2.0.0 do schema, adicionando:
- opinion_recommendation
- opinion_confidence
- opinion_risk
- reasoning_factors
- cognitive_plan_snapshot
- intent_id
- trace_id
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from pymongo import MongoClient, UpdateOne
from tqdm import tqdm

# Configurações
MONGODB_URI = "mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin"
DB_NAME = "neural_hive"
FEEDBACK_COLLECTION = "specialist_feedback"
OPINIONS_COLLECTION = "specialist_opinions"

BATCH_SIZE = 100
DRY_RUN = False  # Set to True para teste sem modificar


def get_opinions_map(client, db):
    """Constroi mapa de opinion_id -> dados da opinião."""
    print(f"📂 Buscando todas as opiniões de {OPINIONS_COLLECTION}...")

    opinions_col = db[OPINIONS_COLLECTION]
    opinions_map = {}

    # Buscar todos os campos necessários
    cursor = opinions_col.find(
        {},
        {
            "_id": 0,
            "opinion_id": 1,
            "plan_id": 1,
            "specialist_type": 1,
            "intent_id": 1,
            "trace_id": 1,
            "opinion.recommendation": 1,
            "opinion.confidence_score": 1,
            "opinion.risk_score": 1,
            "opinion.reasoning_factors": 1,
            "cognitive_plan": 1,
        }
    )

    for opinion in cursor:
        opinions_map[opinion["opinion_id"]] = opinion

    print(f"✅ Carregadas {len(opinions_map)} opiniões")
    return opinions_map


def migrate_feedbacks(client, db, opinions_map):
    """Migra feedbacks para enriquecer com dados da opinião."""
    print(f"\n📊 Migrando feedbacks de {FEEDBACK_COLLECTION}...")

    feedbacks_col = db[FEEDBACK_COLLECTION]

    # Contar feedbacks que precisam de migração
    total = feedbacks_col.count_documents({
        "$or": [
            {"opinion_recommendation": {"$exists": False}},
            {"opinion_confidence": {"$exists": False}},
            {"intent_id": {"$exists": False}}
        ]
    })

    if total == 0:
        print("✅ Todos os feedbacks já estão enriquecidos!")
        return 0, 0

    print(f"📋 {total} feedbacks para migrar")

    # Buscar feedbacks que precisam de migração
    cursor = feedbacks_col.find({
        "$or": [
            {"opinion_recommendation": {"$exists": False}},
            {"opinion_confidence": {"$exists": False}},
            {"intent_id": {"$exists": False}}
        ]
    })

    bulk_updates = []
    migrated = 0
    skipped = 0

    for feedback in tqdm(cursor, total=total, desc="Migrando"):
        opinion_id = feedback.get("opinion_id")

        if not opinion_id or opinion_id not in opinions_map:
            skipped += 1
            continue

        opinion = opinions_map[opinion_id]
        opinion_data = opinion.get("opinion", {})

        # Construir update
        update_doc = {
            "$set": {
                "schema_version": "2.0.0",
                "migrated_at": datetime.now(timezone.utc),
            }
        }

        # Adicionar campos se não existirem
        if "opinion_recommendation" not in feedback:
            update_doc["$set"]["opinion_recommendation"] = opinion_data.get("recommendation")

        if "opinion_confidence" not in feedback:
            update_doc["$set"]["opinion_confidence"] = opinion_data.get("confidence_score")

        if "opinion_risk" not in feedback:
            update_doc["$set"]["opinion_risk"] = opinion_data.get("risk_score")

        if "reasoning_factors" not in feedback:
            update_doc["$set"]["reasoning_factors"] = opinion_data.get("reasoning_factors", [])

        if "cognitive_plan_snapshot" not in feedback:
            update_doc["$set"]["cognitive_plan_snapshot"] = opinion.get("cognitive_plan", {})

        if "intent_id" not in feedback:
            update_doc["$set"]["intent_id"] = opinion.get("intent_id")

        if "trace_id" not in feedback:
            update_doc["$set"]["trace_id"] = opinion.get("trace_id")

        # Marcar como não auto-gerado e não balanceado (feedbacks reais)
        if "auto_generated" not in feedback:
            update_doc["$set"]["auto_generated"] = False

        if "balanced_dataset" not in feedback:
            update_doc["$set"]["balanced_dataset"] = False

        if "manual_review" not in feedback:
            update_doc["$set"]["manual_review"] = True

        bulk_updates.append(
            UpdateOne({"_id": feedback["_id"]}, update_doc)
        )

        migrated += 1

        # Executar em batches
        if len(bulk_updates) >= BATCH_SIZE:
            if not DRY_RUN:
                result = feedbacks_col.bulk_write(bulk_updates)
            else:
                result = type('obj', (object,), {'modified_count': len(bulk_updates)})()
            bulk_updates = []
            print(f"  ✓ Batch de {BATCH_SIZE} processado")

    # Executar batch final
    if bulk_updates and not DRY_RUN:
        feedbacks_col.bulk_write(bulk_updates)

    return migrated, skipped


def verify_migration(client, db):
    """Verifica se a migração foi bem-sucedida."""
    print(f"\n🔍 Verificando migração...")

    feedbacks_col = db[FEEDBACK_COLLECTION]

    # Contar feedbacks enriquecidos
    enriched = feedbacks_col.count_documents({
        "opinion_recommendation": {"$exists": True},
        "opinion_confidence": {"$exists": True},
        "intent_id": {"$exists": True}
    })

    total = feedbacks_col.estimated_document_count()

    print(f"📊 Status:")
    print(f"  Total de feedbacks: {total}")
    print(f"  Feedbacks enriquecidos: {enriched}")
    print(f"  Coverage: {enriched/total*100:.1f}%")

    # Amostra de feedback enriquecido
    sample = feedbacks_col.find_one({
        "opinion_recommendation": {"$exists": True}
    })

    if sample:
        print(f"\n📄 Amostra de feedback enriquecido:")
        print(f"  schema_version: {sample.get('schema_version')}")
        print(f"  opinion_recommendation: {sample.get('opinion_recommendation')}")
        print(f"  opinion_confidence: {sample.get('opinion_confidence')}")
        print(f"  intent_id: {sample.get('intent_id', 'N/A')[:20]}...")


def main():
    print("=" * 60)
    print("MIGRAÇÃO DE FEEDBACKS v1.0.0 → v2.0.0")
    print("=" * 60)
    print(f"MongoDB: mongodb.mongodb-cluster.svc.cluster.local:27017")
    print(f"Database: {DB_NAME}")
    print(f"DRY_RUN: {DRY_RUN}")
    print("=" * 60)

    # Conectar
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000)
    db = client[DB_NAME]

    try:
        # Ping
        client.admin.command('ping')
        print("✅ Conectado ao MongoDB\n")

        # Carregar mapa de opiniões
        opinions_map = get_opinions_map(client, db)

        # Migrar feedbacks
        migrated, skipped = migrate_feedbacks(client, db, opinions_map)

        print(f"\n📊 Resultado:")
        print(f"  Migrados: {migrated}")
        print(f"  Pulados (opinião não encontrada): {skipped}")

        # Verificar
        verify_migration(client, db)

        print("\n✅ Migração concluída!")

    except Exception as e:
        print(f"\n❌ Erro na migração: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main()
