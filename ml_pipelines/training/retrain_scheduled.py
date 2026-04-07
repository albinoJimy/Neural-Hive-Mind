#!/usr/bin/env python3
"""
Retreinamento Programado do Modelo ML

Este script deve ser executado periodicamente (semanalmente) para
retreinar o modelo com novos dados coletados.

Uso:
    python3 retrain_scheduled.py [--min-samples N] [--auto-deploy]

Argumentos:
    --min-samples N: Numero minimo de novas amostras para retreinar (default: 20)
    --auto-deploy: Automaticamente fazer deploy do novo modelo se metrics melhorarem
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pymongo import MongoClient

# Configurações
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/?authSource=admin",
)
DATABASE = "neural_hive"
MODEL_VERSION_PREFIX = "v7"


def check_new_samples(min_samples: int = 20) -> dict:
    """Verifica quantas novas amostras estão disponíveis."""
    client = MongoClient(MONGO_URI)
    db = client[DATABASE]

    # Total de feedbacks com NLP
    total_with_nlp = db["specialist_feedback"].count_documents(
        {"nlp_features": {"$exists": True, "$ne": {}}}
    )

    # Feedbacks treinados (armazenados em metadata)
    trained_metadata = db["model_metadata"].find_one({"type": "approval_model"})
    trained_count = trained_metadata.get("training_samples", 0) if trained_metadata else 0

    new_samples = total_with_nlp - trained_count

    return {
        "total_with_nlp": total_with_nlp,
        "trained_count": trained_count,
        "new_samples": new_samples,
        "should_retrain": new_samples >= min_samples,
    }


def get_retraining_summary() -> dict:
    """Retorna resumo do status de retraining."""
    client = MongoClient(MONGO_URI)
    db = client[DATABASE]

    # Contar feedbacks por decisao
    pipeline = [
        {"$match": {"nlp_features": {"$exists": True}, "final_decision": {"$ne": None, "$ne": ""}}},
        {"$group": {"_id": "$final_decision", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]

    distribution = {}
    for doc in db["specialist_feedback"].aggregate(pipeline):
        distribution[doc["_id"]] = doc["count"]

    # Ultimo modelo treinado
    last_model = db["model_metadata"].find_one(
        {"type": "approval_model"}, sort=[("trained_at", -1)]
    )

    return {
        "distribution": distribution,
        "total_samples": sum(distribution.values()),
        "last_model": {
            "version": last_model.get("version"),
            "trained_at": last_model.get("trained_at"),
            "f1_score": last_model.get("metrics", {}).get("f1_score"),
        }
        if last_model
        else None,
    }


def main():
    parser = argparse.ArgumentParser(description="Retreinamento programado do modelo ML")
    parser.add_argument(
        "--min-samples", type=int, default=20, help="Numero minimo de novas amostras"
    )
    parser.add_argument(
        "--auto-deploy",
        action="store_true",
        help="Automaticamente fazer deploy se metrics melhorarem",
    )
    parser.add_argument("--dry-run", action="store_true", help="Apenas verificar sem retreinar")
    args = parser.parse_args()

    print("=" * 60)
    print("RETRAINING PROGRAMADO - Modelo de Aprovacao")
    print("=" * 60)
    print(f"Data: {datetime.now().isoformat()}")
    print()

    # Verificar novas amostras
    sample_status = check_new_samples(args.min_samples)
    summary = get_retraining_summary()

    print("Status Atual:")
    print(f"  Total com NLP: {sample_status['total_with_nlp']}")
    print(f"  Treinados: {sample_status['trained_count']}")
    print(f"  Novas: {sample_status['new_samples']}")
    print()

    print("Distribuicao por decisao:")
    for decision, count in summary.get("distribution", {}).items():
        print(f"  {decision}: {count}")
    print()

    last_model = summary.get("last_model")
    if last_model:
        print(f"Ultimo Modelo: {last_model.get('version', 'unknown')}")
        print(f"  Treinado em: {last_model.get('trained_at', 'unknown')}")
        print(f"  F1-Score: {last_model.get('f1_score', 'unknown')}")
    else:
        print("Ultimo Modelo: Nenhum modelo treinado ainda")
    print()

    if not sample_status["should_retrain"]:
        print(f"NAO HA NOVAS AMOSTAS SUFICIENTES")
        print(f"Minimo necessario: {args.min_samples}")
        print(f"Novas amostras: {sample_status['new_samples']}")
        print()
        print("Proximo retraining sera verificado na proxima execucao.")
        return 0

    if args.dry_run:
        print("DRY RUN: Retreinamento seria executado.")
        print(f"  Novas amostras: {sample_status['new_samples']}")
        print()
        print("Para executar o retraining, remova --dry-run:")
        print("  python3 retrain_scheduled.py --min-samples {}".format(args.min_samples))
        return 0

    # Executar retraining
    print("=" * 60)
    print("EXECUTANDO RETRAINING")
    print("=" * 60)
    print()

    # Executar retraining usando subprocess para limpar o ambiente
    try:
        import subprocess

        script_path = os.path.join(os.path.dirname(__file__), "retrain_v7_approval.py")

        cmd = [sys.executable, script_path, "--min-samples", str(args.min_samples)]
        if args.dry_run:
            cmd.append("--dry-run")

        print("Executando:", " ".join(cmd))
        print()

        result = subprocess.run(cmd, check=True, capture_output=False)

        if result.returncode == 0:
            print()
            print("=" * 60)
            print("RETRAINING CONCLUIDO COM SUCESSO")
            print("=" * 60)
            print()
            print("Proximos passos:")
            print("1. Verificar as metricas do novo modelo")
            print("2. Comparar com o modelo em producao")
            print("3. Se metrics melhorarem, fazer deploy:")
            print("   - Atualizar Dockerfile")
            print("   - Commit e push para acionar CI/CD")
            return 0
        else:
            return result.returncode

    except FileNotFoundError:
        print(f"ERRO: Script de retraining nao encontrado: {script_path}")
        return 1
    except Exception as e:
        print(f"ERRO: Falha no retraining: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
