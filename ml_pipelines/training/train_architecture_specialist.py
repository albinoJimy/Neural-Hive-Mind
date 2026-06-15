#!/usr/bin/env python3
"""
Script de treino para Architecture Specialist ML Model.

Gera dataset sintético para especialista architecture com features:
- solid_compliance: Aderência aos princípios SOLID
- design_pattern_score: Uso adequado de design patterns
- coupling_score: Baixo acoplamento (high = bom)
- cohesion_score: Alta coesão (high = bom)
- separation_of_concerns: Separação de responsabilidades
- modularity_score: Modularidade do design

Target (y):
- approve=1: solid_compliance + design_pattern_score > 1.4 E coupling_score > 0.5
- reject=0: caso contrário
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Tuple
from contextlib import nullcontext
import structlog
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score, f1_score
import mlflow
import mlflow.sklearn

# Adicionar path para imports
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "libraries" / "python"))

logger = structlog.get_logger()


def generate_architecture_dataset(
    n_samples: int = 1000, random_seed: int = 42
) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Gera dataset sintético para especialista architecture.

    Args:
        n_samples: Numero de amostras
        random_seed: Semente aleatória para reproducibilidade

    Returns:
        Tuple com features (X) e target (y)
    """
    np.random.seed(random_seed)

    X = pd.DataFrame(
        {
            "solid_compliance": np.random.uniform(0, 1, n_samples),
            "design_pattern_score": np.random.uniform(0, 1, n_samples),
            "coupling_score": np.random.uniform(0, 1, n_samples),  # high = low coupling = bom
            "cohesion_score": np.random.uniform(0, 1, n_samples),  # high = alta coesão = bom
            "separation_of_concerns": np.random.uniform(0, 1, n_samples),
            "modularity_score": np.random.uniform(0, 1, n_samples),
        }
    )

    # Regra: approve se SOLID + design_patterns > 1.4 E baixo acoplamento (coupling > 0.5)
    y = (
        ((X["solid_compliance"] + X["design_pattern_score"]) > 1.4)
        & (X["coupling_score"] > 0.5)
        & (X["cohesion_score"] > 0.4)
    ).astype(int)

    logger.info(
        "architecture_dataset_generated",
        n_samples=n_samples,
        approve_ratio=y.mean(),
        reject_ratio=1 - y.mean(),
    )

    return X, y


def train_architecture_model(
    n_samples: int = 1000,
    test_size: float = 0.2,
    n_estimators: int = 100,
    max_depth: int = 5,
    random_seed: int = 42,
) -> GradientBoostingClassifier:
    """
    Treina modelo GradientBoosting para architecture specialist.

    Args:
        n_samples: Numero de amostras do dataset
        test_size: Proporção para teste
        n_estimators: Numero de estimadores do GradientBoosting
        max_depth: Profundidade máxima das árvores
        random_seed: Semente aleatória

    Returns:
        Modelo treinado
    """
    # Gerar dataset
    X, y = generate_architecture_dataset(n_samples, random_seed)

    # Split treino/teste
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_seed, stratify=y
    )

    logger.info(
        "train_test_split_done",
        train_size=len(X_train),
        test_size=len(X_test),
        train_distribution=y_train.mean(),
        test_distribution=y_test.mean(),
    )

    # Criar e treinar modelo
    model = GradientBoostingClassifier(
        n_estimators=n_estimators, max_depth=max_depth, random_state=random_seed
    )

    model.fit(X_train, y_train)

    # Avaliar
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)

    logger.info(
        "model_trained",
        accuracy=accuracy,
        f1_score=f1,
        feature_importances=dict(zip(X.columns, model.feature_importances_.tolist())),
    )

    print("\n=== Architecture Specialist - Classification Report ===")
    print(classification_report(y_test, y_pred, target_names=["reject", "approve"]))
    print("\n=== Feature Importances ===")
    for feature, importance in zip(X.columns, model.feature_importances_):
        print(f"{feature}: {importance:.4f}")

    return model


def main():
    """Função principal para execução via CLI."""
    parser = argparse.ArgumentParser(description="Treinar modelo ML para Architecture Specialist")
    parser.add_argument(
        "--n-samples", type=int, default=1000, help="Numero de amostras do dataset sintético"
    )
    parser.add_argument("--test-size", type=float, default=0.2, help="Proporção para teste (0-1)")
    parser.add_argument(
        "--n-estimators", type=int, default=100, help="Numero de estimadores do GradientBoosting"
    )
    parser.add_argument("--max-depth", type=int, default=5, help="Profundidade máxima das árvores")
    parser.add_argument("--random-seed", type=int, default=42, help="Semente aleatória")
    parser.add_argument("--mlflow-enabled", action="store_true", help="Habilitar logging no MLflow")
    parser.add_argument(
        "--experiment-name",
        type=str,
        default="architecture_specialist",
        help="Nome do experimento MLflow",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default="architecture-evaluator",
        help="Nome do modelo registrado no MLflow",
    )

    args = parser.parse_args()

    # Configurar MLflow se habilitado
    if args.mlflow_enabled:
        mlflow_tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
        mlflow.set_tracking_uri(mlflow_tracking_uri)
        mlflow.set_experiment(args.experiment_name)

        logger.info(
            "mlflow_configured", tracking_uri=mlflow_tracking_uri, experiment=args.experiment_name
        )

    # Iniciar run MLflow
    with mlflow.start_run() if args.mlflow_enabled else nullcontext():
        # Treinar modelo
        model = train_architecture_model(
            n_samples=args.n_samples,
            test_size=args.test_size,
            n_estimators=args.n_estimators,
            max_depth=args.max_depth,
            random_seed=args.random_seed,
        )

        # Log parâmetros e métricas no MLflow
        if args.mlflow_enabled:
            mlflow.log_params(
                {
                    "n_samples": args.n_samples,
                    "test_size": args.test_size,
                    "n_estimators": args.n_estimators,
                    "max_depth": args.max_depth,
                    "random_seed": args.random_seed,
                }
            )

            # Re-calcular métricas para logging
            X, y = generate_architecture_dataset(args.n_samples, args.random_seed)
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=args.test_size, random_state=args.random_seed, stratify=y
            )
            y_pred = model.predict(X_test)

            mlflow.log_metrics(
                {"accuracy": accuracy_score(y_test, y_pred), "f1_score": f1_score(y_test, y_pred)}
            )

            # Log feature importances
            for feature, importance in zip(
                [
                    "solid_compliance",
                    "design_pattern_score",
                    "coupling_score",
                    "cohesion_score",
                    "separation_of_concerns",
                    "modularity_score",
                ],
                model.feature_importances_,
            ):
                mlflow.log_metric(f"feature_importance_{feature}", importance)

            # Log e registrar modelo
            mlflow.sklearn.log_model(
                model, "architecture_specialist_model", registered_model_name=args.model_name
            )

            logger.info(
                "model_registered_in_mlflow",
                model_name=args.model_name,
                run_id=mlflow.active_run().info.run_id,
            )

    print("\n=== Treino Architecture Specialist concluído ===")
    if args.mlflow_enabled:
        print(f"Modelo registrado como: {args.model_name}")
    else:
        print("Modelo treinado em memória (MLflow desabilitado)")


if __name__ == "__main__":
    main()
