#!/usr/bin/env python3
"""
Script para treinar todos os modelos ML de especialistas de uma vez.

Executa os scripts de treino para:
- Business Specialist
- Technical Specialist
- Architecture Specialist
- Behavior Specialist
- Evolution Specialist
"""

import argparse
import os
import sys
import subprocess
from pathlib import Path
from typing import List, Dict
import structlog

logger = structlog.get_logger()

# Diretório de scripts de treino
TRAINING_DIR = Path(__file__).parent

# Configurações dos especialistas
SPECIALIST_CONFIGS: List[Dict[str, str]] = [
    {
        "name": "Business",
        "script": "train_business_specialist.py",
        "model_name": "BusinessSpecialistModel",
        "experiment": "business_specialist"
    },
    {
        "name": "Technical",
        "script": "train_technical_specialist.py",
        "model_name": "TechnicalSpecialistModel",
        "experiment": "technical_specialist"
    },
    {
        "name": "Architecture",
        "script": "train_architecture_specialist.py",
        "model_name": "ArchitectureSpecialistModel",
        "experiment": "architecture_specialist"
    },
    {
        "name": "Behavior",
        "script": "train_behavior_specialist.py",
        "model_name": "BehaviorSpecialistModel",
        "experiment": "behavior_specialist"
    },
    {
        "name": "Evolution",
        "script": "train_evolution_specialist.py",
        "model_name": "EvolutionSpecialistModel",
        "experiment": "evolution_specialist"
    },
]


def train_specialist(
    script_name: str,
    mlflow_enabled: bool = True,
    n_samples: int = 1000,
    n_estimators: int = 100,
    max_depth: int = 5
) -> bool:
    """
    Executa script de treino de um especialista.

    Args:
        script_name: Nome do script de treino
        mlflow_enabled: Habilitar MLflow
        n_samples: Número de amostras
        n_estimators: Número de estimadores
        max_depth: Profundidade máxima

    Returns:
        True se bem-sucedido, False caso contrário
    """
    script_path = TRAINING_DIR / script_name

    if not script_path.exists():
        logger.error("script_not_found", script=str(script_path))
        return False

    cmd = [
        sys.executable,
        str(script_path),
        "--n-samples", str(n_samples),
        "--n-estimators", str(n_estimators),
        "--max-depth", str(max_depth)
    ]

    if mlflow_enabled:
        cmd.append("--mlflow-enabled")

    logger.info("training_specialist", script=script_name)

    try:
        result = subprocess.run(
            cmd,
            cwd=str(TRAINING_DIR),
            capture_output=True,
            text=True,
            timeout=300  # 5 minutos max por especialista
        )

        if result.returncode == 0:
            logger.info(
                "specialist_training_succeeded",
                script=script_name,
                output=result.stdout[-500:]  # Ultimas 500 chars
            )
            return True
        else:
            logger.error(
                "specialist_training_failed",
                script=script_name,
                returncode=result.returncode,
                stderr=result.stderr
            )
            return False

    except subprocess.TimeoutExpired:
        logger.error("training_timeout", script=script_name)
        return False
    except Exception as e:
        logger.error("training_error", script=script_name, error=str(e))
        return False


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description="Treinar todos os modelos ML de especialistas"
    )
    parser.add_argument(
        "--specialists",
        type=str,
        nargs="*",
        choices=["business", "technical", "architecture", "behavior", "evolution", "all"],
        default=["all"],
        help="Especialistas para treinar (default: all)"
    )
    parser.add_argument(
        "--mlflow-enabled",
        action="store_true",
        help="Habilitar logging no MLflow"
    )
    parser.add_argument(
        "--n-samples",
        type=int,
        default=1000,
        help="Numero de amostras do dataset sintético"
    )
    parser.add_argument(
        "--n-estimators",
        type=int,
        default=100,
        help="Numero de estimadores do GradientBoosting"
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=5,
        help="Profundidade máxima das árvores"
    )

    args = parser.parse_args()

    # Verificar MLflow
    if args.mlflow_enabled:
        mlflow_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
        logger.info("mlflow_enabled", tracking_uri=mlflow_uri)
    else:
        logger.warning("mlflow_disabled", reason="use --mlflow-enabled to enable")

    # Determinar quais especialistas treinar
    to_train = []
    if "all" in args.specialists:
        to_train = SPECIALIST_CONFIGS
    else:
        for spec_name in args.specialists:
            for config in SPECIALIST_CONFIGS:
                if config["name"].lower() == spec_name:
                    to_train.append(config)
                    break

    print(f"\n=== Treinando {len(to_train)} modelo(s) de especialista(s) ===\n")

    results = {}
    for config in to_train:
        print(f"\n--- Treinando {config['name']} Specialist ---")
        success = train_specialist(
            config["script"],
            args.mlflow_enabled,
            args.n_samples,
            args.n_estimators,
            args.max_depth
        )
        results[config["name"]] = success

        status = "✓ SUCESSO" if success else "✗ FALHOU"
        print(f"{status}: {config['name']} Specialist\n")

    # Resumo
    print("\n" + "=" * 60)
    print("RESUMO DO TREINAMENTO")
    print("=" * 60)

    for name, success in results.items():
        status = "✓" if success else "✗"
        print(f"{status} {name} Specialist")

    succeeded = sum(1 for s in results.values() if s)
    total = len(results)

    print(f"\nTotal: {succeeded}/{total} bem-sucedidos")

    if succeeded == total:
        print("\nTodos os modelos treinados com sucesso!")
        return 0
    else:
        print(f"\nAtenção: {total - succeeded} modelo(s) falhou/aram")
        return 1


if __name__ == "__main__":
    sys.exit(main())
