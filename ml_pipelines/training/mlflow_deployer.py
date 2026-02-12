#!/usr/bin/env python3
"""
MLflow Deployment Helper para Neural Hive-Mind (Passo 5.5)

Gerencia deployment de modelos ML no MLflow:
- Registra modelos treinados no MLflow Model Registry
- Promove modelos entre staging (teste) e production
- Configura aliases para versionamento
- Gerencia transições de modelos com A/B testing

Uso:
    # Registrar novo modelo
    python mlflow_deployer.py --register --model-path /path/to/model.pkl \
        --model-type business --run-id abc123

    # Promover para produção
    python mlflow_deployer.py --promote --model-type business \
        --model-version v12 --target-stage Production

    # Listar modelos
    python mlflow_deployer.py --list --model-type business

    # Rollback para versão anterior
    python mlflow_deployer.py --rollback --model-type business \
        --target-version v11
"""

import argparse
import asyncio
import json
import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import tempfile
import shutil

import mlflow
import mlflow.sklearn
from mlflow.tracking import MlflowClient
import structlog

logger = structlog.get_logger(__name__)


class MLflowDeployer:
    """
    Gerencia deployment de modelos no MLflow.

    Fluxo de Deployment:
    1. Modelo treinado é registrado com run_id único
    2. Criado como modelo registrado no Model Registry
    3. Inicia em stage 'Staging'
    4. A/B testing é configurado com 10% de tráfego
    5. Se aprovado, promovido para 'Production'
    6. Versão anterior arquivada em 'Archived'
    """

    # Model Registry Configuration
    MODEL_REGISTRY_NAME = "neural-hive-specialists"
    STAGES = ["Staging", "Production", "Archived"]

    # A/B Testing Configuration
    DEFAULT_AB_TEST_CONFIG = {
        "traffic_percentage": 10.0,
        "min_samples": 1000,
        "duration_hours": 72,
        "success_threshold": 0.02
    }

    def __init__(
        self,
        mlflow_tracking_uri: str = None,
        experiment_name: str = "specialist_training"
    ):
        """
        Inicializa MLflow deployer.

        Args:
            mlflow_tracking_uri: URI do MLflow tracking server
            experiment_name: Nome do experimento MLflow
        """
        self.mlflow_tracking_uri = mlflow_tracking_uri or os.getenv(
            'MLFLOW_TRACKING_URI',
            'http://mlflow.mlflow.svc.cluster.local:5000'
        )
        self.experiment_name = experiment_name

        # Configurar MLflow
        mlflow.set_tracking_uri(self.mlflow_tracking_uri)
        self.client = MlflowClient(self.mlflow_tracking_uri)

        logger.info(
            "mlflow_deployer_initialized",
            tracking_uri=self.mlflow_tracking_uri,
            experiment_name=experiment_name
        )

    def register_model(
        self,
        model_path: str,
        model_type: str,
        run_id: str,
        model_metrics: Dict[str, float] = None,
        model_params: Dict[str, Any] = None,
        tags: Dict[str, str] = None
    ) -> str:
        """
        Registra modelo treinado no MLflow Model Registry.

        Args:
            model_path: Caminho para o arquivo do modelo (.pkl)
            model_type: Tipo do especialista (business, technical, etc.)
            run_id: ID do run MLflow que treinou o modelo
            model_metrics: Métricas do modelo (accuracy, f1, etc.)
            model_params: Hiperparâmetros do modelo
            tags: Tags adicionais para o modelo

        Returns:
            model_version: Versão do modelo registrado
        """
        logger.info(
            "registering_model",
            model_type=model_type,
            model_path=model_path,
            run_id=run_id
        )

        # Criar nome do modelo registrado
        registered_model_name = f"{self.MODEL_REGISTRY_NAME}_{model_type}"

        # Carregar modelo para obter informações
        import joblib
        model = joblib.load(model_path)

        # Criar modelo URI no MLflow
        model_uri = f"runs:/{run_id}/model"

        # Logar modelo no run (se já não estiver logado)
        with mlflow.start_run(run_id=run_id):
            mlflow.sklearn.log_model(
                sk_model=model,
                artifact_path="model",
                registered_model_name=registered_model_name
            )

        # Obter versão do modelo
        model_version = self.client.get_latest_versions(
            name=registered_model_name,
            stages=["None"]
        )[0].version

        # Adicionar tags e métricas
        if tags:
            self.client.set_model_version_tag(
                name=registered_model_name,
                version=model_version,
                key="registered_at",
                value=datetime.utcnow().isoformat()
            )
            for key, value in tags.items():
                self.client.set_model_version_tag(
                    name=registered_model_name,
                    version=model_version,
                    key=key,
                    value=value
                )

        # Adicionar métricas ao run
        if model_metrics:
            with mlflow.start_run(run_id=run_id):
                for metric_name, metric_value in model_metrics.items():
                    mlflow.log_metric(metric_name, metric_value)

        # Adicionar parâmetros ao run
        if model_params:
            with mlflow.start_run(run_id=run_id):
                for param_name, param_value in model_params.items():
                    mlflow.log_param(param_name, str(param_value))

        logger.info(
            "model_registered",
            model_type=model_type,
            model_version=model_version,
            registered_model_name=registered_model_name
        )

        return model_version

    def promote_model(
        self,
        model_type: str,
        model_version: str,
        target_stage: str = "Production"
    ) -> bool:
        """
        Promove modelo para stage específico.

        Args:
            model_type: Tipo do especialista
            model_version: Versão do modelo (e.g., "12")
            target_stage: Stage alvo (Staging, Production, Archived)

        Returns:
            True se promoção bem-sucedida
        """
        registered_model_name = f"{self.MODEL_REGISTRY_NAME}_{model_type}"

        logger.info(
            "promoting_model",
            model_type=model_type,
            model_version=model_version,
            target_stage=target_stage
        )

        try:
            # Arquivar versão atual em Production se promovendo para Production
            if target_stage == "Production":
                self._archive_current_production(model_type)

            # Promover modelo
            self.client.transition_model_version_stage(
                name=registered_model_name,
                version=model_version,
                stage=target_stage,
                archive_existing_versions=False
            )

            # Adicionar timestamp de promoção
            self.client.set_model_version_tag(
                name=registered_model_name,
                version=model_version,
                key=f"promoted_to_{target_stage.lower()}",
                value=datetime.utcnow().isoformat()
            )

            logger.info(
                "model_promoted",
                model_type=model_type,
                model_version=model_version,
                target_stage=target_stage
            )

            return True

        except Exception as e:
            logger.error(
                "model_promotion_failed",
                model_type=model_type,
                model_version=model_version,
                error=str(e)
            )
            return False

    def _archive_current_production(self, model_type: str):
        """Arquiva versão atual em Production."""
        registered_model_name = f"{self.MODEL_REGISTRY_NAME}_{model_type}"

        try:
            current_versions = self.client.get_latest_versions(
                name=registered_model_name,
                stages=["Production"]
            )

            for version_info in current_versions:
                self.client.transition_model_version_stage(
                    name=registered_model_name,
                    version=version_info.version,
                    stage="Archived"
                )
                logger.info(
                    "archived_previous_production",
                    model_type=model_type,
                    archived_version=version_info.version
                )

        except Exception as e:
            logger.warning(f"Erro ao arquivar produção anterior: {e}")

    def list_models(self, model_type: str = None) -> List[Dict[str, Any]]:
        """
        Lista modelos registrados.

        Args:
            model_type: Filtrar por tipo (opcional)

        Returns:
            Lista de modelos com informações
        """
        models = []

        if model_type:
            model_names = [f"{self.MODEL_REGISTRY_NAME}_{model_type}"]
        else:
            model_names = [
                name for name in self.client.search_registered_models()
                if name.name.startswith(self.MODEL_REGISTRY_NAME)
            ]

        for model_info in model_names:
            name = model_info.name if isinstance(model_info, str) else model_info.name
            specialist_type = name.replace(f"{self.MODEL_REGISTRY_NAME}_", "")

            versions = self.client.get_latest_versions(name=name)

            for version_info in versions:
                models.append({
                    'specialist_type': specialist_type,
                    'model_name': name,
                    'version': version_info.version,
                    'stage': version_info.current_stage,
                    'status': version_info.status,
                    'creation_timestamp': version_info.creation_timestamp
                })

        return models

    def rollback_model(
        self,
        model_type: str,
        target_version: str
    ) -> bool:
        """
        Rollback para versão anterior.

        Args:
            model_type: Tipo do especialista
            target_version: Versão alvo para rollback

        Returns:
            True se rollback bem-sucedido
        """
        registered_model_name = f"{self.MODEL_REGISTRY_NAME}_{model_type}"

        logger.info(
            "rolling_back_model",
            model_type=model_type,
            target_version=target_version
        )

        try:
            # Arquivar Production atual
            self._archive_current_production(model_type)

            # Promover versão alvo para Production
            self.client.transition_model_version_stage(
                name=registered_model_name,
                version=target_version,
                stage="Production"
            )

            # Adicionar tag de rollback
            self.client.set_model_version_tag(
                name=registered_model_name,
                version=target_version,
                key="rollback",
                value=datetime.utcnow().isoformat()
            )

            logger.info(
                "model_rollback_completed",
                model_type=model_type,
                target_version=target_version
            )

            return True

        except Exception as e:
            logger.error(
                "model_rollback_failed",
                model_type=model_type,
                target_version=target_version,
                error=str(e)
            )
            return False

    def get_production_model_uri(self, model_type: str) -> Optional[str]:
        """
        Obtém URI do modelo em produção.

        Args:
            model_type: Tipo do especialista

        Returns:
            URI do modelo ou None se não existe
        """
        registered_model_name = f"{self.MODEL_REGISTRY_NAME}_{model_type}"

        try:
            versions = self.client.get_latest_versions(
                name=registered_model_name,
                stages=["Production"]
            )

            if versions:
                return f"models:/{registered_model_name}/Production"

            return None

        except Exception:
            return None

    def create_model_alias(
        self,
        model_type: str,
        alias: str,
        model_version: str
    ) -> bool:
        """
        Cria alias para versão de modelo (para A/B testing).

        Args:
            model_type: Tipo do especialista
            alias: Nome do alias (e.g., "ab-test-v12", "candidate")
            model_version: Versão do modelo

        Returns:
            True se alias criado
        """
        registered_model_name = f"{self.MODEL_REGISTRY_NAME}_{model_type}"

        try:
            # MLflow usa tags para aliases
            self.client.set_model_version_tag(
                name=registered_model_name,
                version=model_version,
                key=f"alias_{alias}",
                value=datetime.utcnow().isoformat()
            )

            logger.info(
                "model_alias_created",
                model_type=model_type,
                alias=alias,
                model_version=model_version
            )

            return True

        except Exception as e:
            logger.error(f"Erro ao criar alias: {e}")
            return False

    def get_model_by_alias(self, model_type: str, alias: str) -> Optional[str]:
        """
        Obtém versão do modelo por alias.

        Args:
            model_type: Tipo do especialista
            alias: Nome do alias

        Returns:
            Versão do modelo ou None
        """
        registered_model_name = f"{self.MODEL_REGISTRY_NAME}_{model_type}"

        try:
            versions = self.client.get_latest_versions(registered_model_name)

            for version_info in versions:
                tags = self.client.get_model_version(
                    name=registered_model_name,
                    version=version_info.version
                ).tags

                if tags and f"alias_{alias}" in tags:
                    return version_info.version

            return None

        except Exception:
            return None


def main():
    """Função principal para CLI."""
    parser = argparse.ArgumentParser(
        description="MLflow Deployment Helper"
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest='action', required=True)

    # Register
    register_parser = subparsers.add_parser('register', help='Registrar modelo')
    register_parser.add_argument('--model-path', type=str, required=True)
    register_parser.add_argument('--model-type', type=str, required=True,
                                 choices=['business', 'technical', 'behavior', 'evolution', 'architecture'])
    register_parser.add_argument('--run-id', type=str, required=True)
    register_parser.add_argument('--metrics', type=str, help='JSON com métricas')
    register_parser.add_argument('--params', type=str, help='JSON com parâmetros')

    # Promote
    promote_parser = subparsers.add_parser('promote', help='Promover modelo')
    promote_parser.add_argument('--model-type', type=str, required=True,
                                choices=['business', 'technical', 'behavior', 'evolution', 'architecture'])
    promote_parser.add_argument('--model-version', type=str, required=True)
    promote_parser.add_argument('--target-stage', type=str, default='Production',
                                choices=['Staging', 'Production', 'Archived'])

    # List
    list_parser = subparsers.add_parser('list', help='Listar modelos')
    list_parser.add_argument('--model-type', type=str,
                             choices=['business', 'technical', 'behavior', 'evolution', 'architecture'])

    # Rollback
    rollback_parser = subparsers.add_parser('rollback', help='Rollback de modelo')
    rollback_parser.add_argument('--model-type', type=str, required=True,
                                 choices=['business', 'technical', 'behavior', 'evolution', 'architecture'])
    rollback_parser.add_argument('--target-version', type=str, required=True)

    # Alias
    alias_parser = subparsers.add_parser('alias', help='Criar alias de modelo')
    alias_parser.add_argument('--model-type', type=str, required=True,
                              choices=['business', 'technical', 'behavior', 'evolution', 'architecture'])
    alias_parser.add_argument('--alias', type=str, required=True)
    alias_parser.add_argument('--model-version', type=str, required=True)

    args = parser.parse_args()

    # Inicializar deployer
    deployer = MLflowDeployer()

    # Executar ação
    if args.action == 'register':
        metrics = json.loads(args.metrics) if args.metrics else None
        params = json.loads(args.params) if args.params else None

        version = deployer.register_model(
            model_path=args.model_path,
            model_type=args.model_type,
            run_id=args.run_id,
            model_metrics=metrics,
            model_params=params
        )
        print(f"Modelo registrado: versão {version}")

    elif args.action == 'promote':
        success = deployer.promote_model(
            model_type=args.model_type,
            model_version=args.model_version,
            target_stage=args.target_stage
        )
        if success:
            print(f"Modelo {args.model_type} v{args.model_version} promovido para {args.target_stage}")
        else:
            print("Falha na promoção")
            sys.exit(1)

    elif args.action == 'list':
        models = deployer.list_models(args.model_type)
        print("\nModelos Registrados:")
        print("-" * 80)
        for model in models:
            print(f"{model['specialist_type']:15} v{model['version']:5} {model['stage']:12} {model['status']}")
        print("-" * 80)

    elif args.action == 'rollback':
        success = deployer.rollback_model(
            model_type=args.model_type,
            target_version=args.target_version
        )
        if success:
            print(f"Rollback para versão {args.target_version} concluído")
        else:
            print("Falha no rollback")
            sys.exit(1)

    elif args.action == 'alias':
        success = deployer.create_model_alias(
            model_type=args.model_type,
            alias=args.alias,
            model_version=args.model_version
        )
        if success:
            print(f"Alias '{args.alias}' criado para versão {args.model_version}")
        else:
            print("Falha ao criar alias")
            sys.exit(1)


if __name__ == '__main__':
    main()
