#!/usr/bin/env python3
"""
Script de treinamento do modelo SHAP para Explainability API.

Coleta decisões históricas do MongoDB e treina modelo sklearn
para cálculo de SHAP values.

EPIC-204-01: Modelo ML para SHAP

Usage:
    python -m ml.shap_training
    python -m ml.shap_training --min-samples 50 --output models/shap_model_v1.joblib
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

import structlog

# Adicionar src ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.mongodb_client import MongoDBClient
from src.models.shap_model import ModelTrainer

logger = structlog.get_logger(__name__)


async def collect_historical_decisions(
    mongo_client: MongoDBClient, limit: int = 1000
) -> list[dict[str, Any]]:
    """
    Coleta decisões históricas do MongoDB.

    Args:
        mongo_client: Cliente MongoDB
        limit: Número máximo de decisões a coletar

    Returns:
        Lista de decisões (dicionários)
    """
    logger.info("collecting_historical_decisions", limit=limit)

    try:
        # Buscar decisões da coleção de aprovações
        decisions = await mongo_client.get_recent_decisions(limit=limit)

        logger.info("decisions_collected", count=len(decisions), source="mongodb")

        return decisions

    except Exception as e:
        logger.error("failed_to_collect_decisions", error=str(e))
        # Retornar lista vazia em caso de erro
        return []


async def train_shap_model(
    decisions: list[dict[str, Any]],
    model_type: str = "random_forest",
    target_accuracy: float = 0.7,
    output_path: str = "models/shap_model_v1.joblib",
) -> dict[str, Any]:
    """
    Treina modelo SHAP com decisões históricas.

    Args:
        decisions: Lista de decisões históricas
        model_type: Tipo de modelo ('random_forest' ou 'gradient_boosting')
        target_accuracy: Acurácia alvo para validação
        output_path: Caminho para salvar o modelo

    Returns:
        Dicionário com resultados do treinamento
    """
    logger.info(
        "starting_shap_model_training",
        samples=len(decisions),
        model_type=model_type,
        target_accuracy=target_accuracy,
    )

    # Criar diretório de saída se não existir
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Inicializar treinador
    trainer = ModelTrainer(model_type=model_type, min_samples=10, target_accuracy=target_accuracy)

    # Treinar modelo
    result = trainer.train_from_decisions(decisions)

    if result["success"]:
        # Salvar modelo
        trainer.save_trained_model(output_path)

        logger.info(
            "shap_model_trained_successfully",
            output_path=output_path,
            metrics=result.get("metrics"),
            feature_importance=result.get("feature_importance"),
        )

        result["model_path"] = output_path
    else:
        logger.error("shap_model_training_failed", error=result.get("error", "Unknown error"))

    return result


def generate_synthetic_decisions(n_samples: int = 100) -> list[dict[str, Any]]:
    """
    Gera decisões sintéticas para teste/demo.

    Args:
        n_samples: Número de decisões sintéticas

    Returns:
        Lista de decisões sintéticas
    """
    import random

    decisions = []
    for i in range(n_samples):
        # Decisão baseada em regras simples para criar padrão
        confidence = random.random()
        risk = random.random()
        divergence = random.random()

        # Regra: alta confiança + baixo risco = approve
        final_decision = "approve" if (confidence - risk) > 0 else "reject"

        decision = {
            "decision_id": f"synthetic_{i}",
            "plan_id": f"plan_{i}",
            "intent_id": f"intent_{i}",
            "final_decision": final_decision,
            "aggregated_confidence": confidence,
            "aggregated_risk": risk,
            "specialist_votes": [
                {
                    "specialist_type": "business",
                    "confidence_score": confidence + random.uniform(-0.1, 0.1),
                    "risk_score": risk + random.uniform(-0.1, 0.1),
                    "processing_time_ms": random.randint(100, 5000),
                    "seniority_multiplier": random.choice([0.5, 0.75, 1.0, 1.5, 2.0]),
                },
                {
                    "specialist_type": "technical",
                    "confidence_score": confidence + random.uniform(-0.1, 0.1),
                    "risk_score": risk + random.uniform(-0.1, 0.1),
                    "processing_time_ms": random.randint(100, 5000),
                    "seniority_multiplier": random.choice([0.5, 0.75, 1.0, 1.5, 2.0]),
                },
            ],
            "consensus_metrics": {
                "divergence_score": divergence,
                "unanimous": random.random() > 0.5,
                "bayesian_confidence": confidence,
                "voting_confidence": confidence,
            },
        }
        decisions.append(decision)

    return decisions


async def main():
    """Função principal do script de treinamento."""
    parser = argparse.ArgumentParser(description="Treina modelo SHAP para Explainability API")
    parser.add_argument(
        "--min-samples", type=int, default=50, help="Número mínimo de amostras para treinamento"
    )
    parser.add_argument(
        "--max-samples", type=int, default=1000, help="Número máximo de amostras para coletar"
    )
    parser.add_argument(
        "--model-type",
        type=str,
        default="random_forest",
        choices=["random_forest", "gradient_boosting"],
        help="Tipo de modelo a treinar",
    )
    parser.add_argument(
        "--target-accuracy", type=float, default=0.7, help="Acurácia alvo para validação"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="models/shap_model_v1.joblib",
        help="Caminho para salvar o modelo",
    )
    parser.add_argument(
        "--use-synthetic",
        action="store_true",
        help="Usar dados sintéticos em vez de buscar do MongoDB",
    )
    parser.add_argument(
        "--synthetic-samples", type=int, default=100, help="Número de amostras sintéticas a gerar"
    )

    args = parser.parse_args()

    logger.info(
        "shap_training_script_started",
        min_samples=args.min_samples,
        max_samples=args.max_samples,
        model_type=args.model_type,
        target_accuracy=args.target_accuracy,
        output=args.output,
        use_synthetic=args.use_synthetic,
    )

    # Coletar decisões
    if args.use_synthetic:
        logger.info("using_synthetic_data", samples=args.synthetic_samples)
        decisions = generate_synthetic_decisions(args.synthetic_samples)
    else:
        mongo_client = MongoDBClient()
        await mongo_client.connect()
        decisions = await collect_historical_decisions(mongo_client, limit=args.max_samples)
        await mongo_client.close()

    # Validar quantidade mínima
    if len(decisions) < args.min_samples:
        logger.warning(
            "insufficient_samples",
            collected=len(decisions),
            required=args.min_samples,
            msg="using_synthetic_fallback",
        )
        # Complementar com sintéticos se necessário
        synthetic = generate_synthetic_decisions(args.min_samples - len(decisions))
        decisions.extend(synthetic)

    # Treinar modelo
    result = await train_shap_model(
        decisions=decisions,
        model_type=args.model_type,
        target_accuracy=args.target_accuracy,
        output_path=args.output,
    )

    # Exibir resultado
    print("\n" + "=" * 60)
    print("SHAP Model Training Results")
    print("=" * 60)

    if result["success"]:
        print("✅ Model trained successfully!")
        print(f"   Accuracy: {result['metrics']['accuracy']:.4f}")
        print(f"   Samples: {result['metrics']['samples']}")
        print(f"   Approval rate: {result['metrics']['approval_rate']:.2%}")
        print(f"   Model saved: {result['model_path']}")

        print("\nFeature Importance:")
        for feat, imp in sorted(
            result["feature_importance"].items(), key=lambda x: x[1], reverse=True
        ):
            print(f"   - {feat}: {imp:.4f}")

        if result.get("meets_target"):
            print(f"\n✅ Meets target accuracy ({args.target_accuracy:.2%})")
        else:
            print(f"\n⚠️  Below target accuracy ({args.target_accuracy:.2%})")

    else:
        print(f"❌ Training failed: {result.get('error', 'Unknown error')}")

    print("=" * 60 + "\n")

    # Exit code baseado no sucesso
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    asyncio.run(main())
