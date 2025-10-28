#!/usr/bin/env python3
"""
Script de validação de modelo MLflow com gates de qualidade.

Verifica métricas de precision, recall e outras antes de promover modelo.
"""

import os
import sys
import argparse
import mlflow
from mlflow.tracking import MlflowClient
import structlog

logger = structlog.get_logger()


def validate_model(
    model_name: str,
    model_version: str,
    min_precision: float = 0.7,
    min_recall: float = 0.7,
    min_f1: float = 0.7,
    tracking_uri: str = None
) -> bool:
    """
    Valida métricas de modelo.

    Args:
        model_name: Nome do modelo registrado
        model_version: Versão do modelo a validar
        min_precision: Precisão mínima requerida
        min_recall: Recall mínimo requerido
        min_f1: F1-score mínimo requerido
        tracking_uri: URI do MLflow tracking server

    Returns:
        True se modelo passa nas validações
    """
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)

    client = MlflowClient()

    try:
        # Buscar versão do modelo
        model_version_details = client.get_model_version(
            name=model_name,
            version=model_version
        )

        run_id = model_version_details.run_id

        logger.info(
            "Validating model",
            model_name=model_name,
            version=model_version,
            run_id=run_id
        )

        # Buscar métricas do run
        run = client.get_run(run_id)
        metrics = run.data.metrics

        logger.info("Model metrics", metrics=metrics)

        # Validar métricas
        precision = metrics.get('precision', 0.0)
        recall = metrics.get('recall', 0.0)
        f1_score = metrics.get('f1_score', 0.0)

        validations = {
            'precision': (precision, min_precision),
            'recall': (recall, min_recall),
            'f1_score': (f1_score, min_f1)
        }

        failed_validations = []

        for metric_name, (actual, threshold) in validations.items():
            if actual < threshold:
                failed_validations.append({
                    'metric': metric_name,
                    'actual': actual,
                    'threshold': threshold
                })
                logger.warning(
                    f"{metric_name} below threshold",
                    metric=metric_name,
                    actual=actual,
                    threshold=threshold
                )

        if failed_validations:
            logger.error(
                "Model validation failed",
                failed_validations=failed_validations
            )
            return False

        logger.info(
            "Model validation passed",
            model_name=model_name,
            version=model_version,
            precision=precision,
            recall=recall,
            f1_score=f1_score
        )

        return True

    except Exception as e:
        logger.error(
            "Model validation error",
            model_name=model_name,
            version=model_version,
            error=str(e)
        )
        return False


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(description='Validate MLflow model')
    parser.add_argument('--model-name', required=True, help='Model name')
    parser.add_argument('--model-version', required=True, help='Model version')
    parser.add_argument('--min-precision', type=float, default=0.7, help='Minimum precision')
    parser.add_argument('--min-recall', type=float, default=0.7, help='Minimum recall')
    parser.add_argument('--min-f1', type=float, default=0.7, help='Minimum F1 score')
    parser.add_argument('--tracking-uri', default=os.getenv('MLFLOW_TRACKING_URI'), help='MLflow tracking URI')

    args = parser.parse_args()

    success = validate_model(
        model_name=args.model_name,
        model_version=args.model_version,
        min_precision=args.min_precision,
        min_recall=args.min_recall,
        min_f1=args.min_f1,
        tracking_uri=args.tracking_uri
    )

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
