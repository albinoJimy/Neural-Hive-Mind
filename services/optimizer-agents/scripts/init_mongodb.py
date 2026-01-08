#!/usr/bin/env python3
"""
Script para inicializar coleções e índices MongoDB para o Optimizer Agents.

Cria as coleções necessárias e configura índices para performance otimizada.
"""
import asyncio
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient


async def init_mongodb():
    """Inicializar coleções e índices MongoDB."""
    mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    database_name = os.getenv("MONGODB_DATABASE", "optimizer_agents")

    print(f"Conectando ao MongoDB: {mongodb_uri}")
    client = AsyncIOMotorClient(mongodb_uri)
    db = client[database_name]

    # Coleção: consensus_weights (pesos de consenso dos especialistas)
    print("Criando índices para consensus_weights...")
    await db.consensus_weights.create_index([("active", 1)])
    await db.consensus_weights.create_index([("last_updated_at", -1)])
    await db.consensus_weights.create_index([("optimization_id", 1)])
    await db.consensus_weights.create_index([("active", 1), ("last_updated_at", -1)])
    print("  - Índices criados: active, last_updated_at, optimization_id")

    # Coleção: weight_adjustments (histórico de ajustes de peso)
    print("Criando índices para weight_adjustments...")
    await db.weight_adjustments.create_index([("optimization_id", 1)], unique=True)
    await db.weight_adjustments.create_index([("adjusted_at", -1)])
    await db.weight_adjustments.create_index([("was_rolled_back", 1)])
    await db.weight_adjustments.create_index([("adjusted_at", -1), ("was_rolled_back", 1)])
    print("  - Índices criados: optimization_id (unique), adjusted_at, was_rolled_back")

    # Coleção: slo_configs (configurações de SLO por serviço)
    print("Criando índices para slo_configs...")
    await db.slo_configs.create_index([("service", 1)])
    await db.slo_configs.create_index([("active", 1)])
    await db.slo_configs.create_index([("last_updated_at", -1)])
    await db.slo_configs.create_index([("service", 1), ("active", 1)])
    await db.slo_configs.create_index([("optimization_id", 1)])
    print("  - Índices criados: service, active, last_updated_at, optimization_id")

    # Coleção: slo_adjustments (histórico de ajustes de SLO)
    print("Criando índices para slo_adjustments...")
    await db.slo_adjustments.create_index([("optimization_id", 1), ("service", 1)], unique=True)
    await db.slo_adjustments.create_index([("adjusted_at", -1)])
    await db.slo_adjustments.create_index([("service", 1)])
    await db.slo_adjustments.create_index([("was_rolled_back", 1)])
    await db.slo_adjustments.create_index([("service", 1), ("adjusted_at", -1)])
    print("  - Índices criados: (optimization_id, service) (unique), adjusted_at, service, was_rolled_back")

    # Coleção: slo_violations (registro de violações de SLO)
    print("Criando índices para slo_violations...")
    await db.slo_violations.create_index([("service", 1)])
    await db.slo_violations.create_index([("timestamp", -1)])
    await db.slo_violations.create_index([("service", 1), ("timestamp", -1)])
    await db.slo_violations.create_index([("violation_type", 1)])
    print("  - Índices criados: service, timestamp, violation_type")

    # Coleção: optimizations (otimizações gerais - já existente, garantir índices)
    print("Criando índices para optimizations...")
    await db.optimizations.create_index([("optimization_id", 1)], unique=True)
    await db.optimizations.create_index([("optimization_type", 1)])
    await db.optimizations.create_index([("target_component", 1)])
    await db.optimizations.create_index([("applied_at", -1)])
    await db.optimizations.create_index([("approval_status", 1)])
    print("  - Índices criados: optimization_id (unique), optimization_type, target_component, applied_at, approval_status")

    # Inserir dados iniciais de pesos padrão (se não existirem)
    existing_weights = await db.consensus_weights.find_one({"active": True})
    if not existing_weights:
        print("Inserindo pesos iniciais padrão...")
        await db.consensus_weights.insert_one({
            "optimization_id": "initial-default",
            "weights": {
                "technical": 0.20,
                "safety": 0.20,
                "business": 0.20,
                "ethical": 0.20,
                "legal": 0.20,
            },
            "previous_weights": {},
            "justification": "Pesos iniciais padrão",
            "last_updated_at": 0,
            "active": True,
        })
        print("  - Pesos iniciais inseridos")
    else:
        print("  - Pesos já existem, pulando inserção inicial")

    print("\nInicialização MongoDB concluída com sucesso!")
    client.close()


if __name__ == "__main__":
    asyncio.run(init_mongodb())
