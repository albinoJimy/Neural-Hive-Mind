#!/usr/bin/env python3
"""
Script de promoção de modelo MLflow entre stages.

Promove modelo de Staging para Production após validação.
"""

import os
import sys
import argparse
import mlflow
from mlflow.tracking import MlflowClient
import structlog

logger = structlog.get_logger()


def promote_model(
    model_name: str,
    model_version: str,
    target_stage: str = 'Production',
    archive_existing: bool = True,
    tracking_uri: str = None
) -> bool:
    """
    Promove modelo para stage target.

    Args:
        model_name: Nome do modelo registrado
        model_version: Versão do modelo a promover
        target_stage: Stage destino (Staging, Production)
        archive_existing: Arquivar modelos existentes no stage target
        tracking_uri: URI do MLflow tracking server

    Returns:
        True se promoção foi bem-sucedida
    """
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)

    client = MlflowClient()

    try:
        logger.info(
            "Promoting model",
            model_name=model_name,
            version=model_version,
            target_stage=target_stage
        )

        # Arquivar modelos existentes no stage target se solicitado
        if archive_existing:
            existing_versions = client.get_latest_versions(
                name=model_name,
                stages=[target_stage]
            )

            for existing_version in existing_versions:
                logger.info(
                    "Archiving existing model",
                    version=existing_version.version,
                    stage=existing_version.current_stage
                )

                client.transition_model_version_stage(
                    name=model_name,
                    version=existing_version.version,
                    stage='Archived',
                    archive_existing_versions=False
                )

        # Promover nova versão
        client.transition_model_version_stage(
            name=model_name,
            version=model_version,
            stage=target_stage,
            archive_existing_versions=False  # Já arquivamos manualmente
        )

        logger.info(
            "Model promoted successfully",
            model_name=model_name,
            version=model_version,
            target_stage=target_stage
        )

        return True

    except Exception as e:
        logger.error(
            "Model promotion error",
            model_name=model_name,
            version=model_version,
            target_stage=target_stage,
            error=str(e)
        )
        return False


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(description='Promote MLflow model')
    parser.add_argument('--model-name', required=True, help='Model name')
    parser.add_argument('--model-version', required=True, help='Model version')
    parser.add_argument('--target-stage', default='Production', help='Target stage (default: Production)')
    parser.add_argument('--no-archive-existing', action='store_true', help='Do not archive existing models in target stage')
    parser.add_argument('--tracking-uri', default=os.getenv('MLFLOW_TRACKING_URI'), help='MLflow tracking URI')

    args = parser.parse_args()

    success = promote_model(
        model_name=args.model_name,
        model_version=args.model_version,
        target_stage=args.target_stage,
        archive_existing=not args.no_archive_existing,
        tracking_uri=args.tracking_uri
    )

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
