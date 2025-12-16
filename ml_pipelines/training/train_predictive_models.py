#!/usr/bin/env python3
"""Pipeline de treinamento MLflow para modelos preditivos."""

import argparse
import asyncio
import logging
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List

import pandas as pd
import numpy as np
from motor.motor_asyncio import AsyncIOMotorClient
import mlflow
from mlflow.tracking import MlflowClient

# Adiciona path da biblioteca
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "libraries" / "python"))

from neural_hive_ml.predictive_models import (
    SchedulingPredictor,
    LoadPredictor,
    AnomalyDetector
)
from neural_hive_ml.predictive_models.model_registry import ModelRegistry

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PredictiveModelsTrainer:
    """Trainer centralizado para modelos preditivos."""

    def __init__(self, args):
        """Inicializa trainer com argumentos CLI."""
        self.args = args
        self.mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
        self.mlflow_uri = os.getenv('MLFLOW_TRACKING_URI', 'http://localhost:5000')
        self.clickhouse_host = os.getenv('CLICKHOUSE_HOST', 'localhost')
        self.clickhouse_port = int(os.getenv('CLICKHOUSE_PORT', '9000'))
        self.clickhouse_user = os.getenv('CLICKHOUSE_USER', 'default')
        self.clickhouse_password = os.getenv('CLICKHOUSE_PASSWORD', '')
        self.clickhouse_database = os.getenv('CLICKHOUSE_DATABASE', 'neural_hive')

        self.mongo_client = None
        self.clickhouse_client = None
        self.model_registry = None

    async def setup(self):
        """Configura conexões e registry."""
        logger.info("Configurando conexões...")

        # MongoDB
        self.mongo_client = AsyncIOMotorClient(self.mongodb_uri)
        self.db = self.mongo_client.neural_hive

        # ClickHouse (se disponível)
        try:
            from clickhouse_driver import Client as SyncClickHouseClient

            logger.info(f"Conectando ao ClickHouse: {self.clickhouse_host}:{self.clickhouse_port}")

            # Criar cliente ClickHouse de forma síncrona
            loop = asyncio.get_event_loop()
            self.clickhouse_client = await loop.run_in_executor(
                None,
                self._create_clickhouse_client
            )

            # Testar conexão
            result = await loop.run_in_executor(
                None,
                self.clickhouse_client.execute,
                "SELECT 1"
            )

            logger.info("ClickHouse conectado com sucesso")

        except Exception as e:
            logger.warning(f"ClickHouse não disponível: {e}, usando apenas MongoDB")
            self.clickhouse_client = None

        # MLflow
        mlflow.set_tracking_uri(self.mlflow_uri)
        self.model_registry = ModelRegistry(
            tracking_uri=self.mlflow_uri,
            experiment_prefix="neural-hive-ml"
        )

        logger.info("Setup concluído")

    def _create_clickhouse_client(self):
        """Cria cliente ClickHouse síncrono."""
        from clickhouse_driver import Client as SyncClickHouseClient

        return SyncClickHouseClient(
            host=self.clickhouse_host,
            port=self.clickhouse_port,
            user=self.clickhouse_user,
            password=self.clickhouse_password,
            database=self.clickhouse_database,
            connect_timeout=10,
            send_receive_timeout=30
        )

    async def train_scheduling_predictor(self) -> Dict[str, float]:
        """Treina SchedulingPredictor."""
        logger.info("=== Treinando SchedulingPredictor ===")

        try:
            # Carrega dados históricos
            training_data = await self._load_ticket_history()

            if len(training_data) < self.args.min_samples:
                raise ValueError(
                    f"Dados insuficientes: {len(training_data)} < {self.args.min_samples}"
                )

            # Configura modelo
            config = {
                'model_name': 'scheduling-predictor',
                'model_type': self.args.model_algorithm or 'xgboost',
                'hyperparameters': {
                    'max_depth': 6,
                    'learning_rate': 0.1,
                    'n_estimators': 100
                }
            }

            predictor = SchedulingPredictor(
                config=config,
                model_registry=self.model_registry
            )

            # Treina
            metrics = await predictor.train_model(
                training_data=training_data,
                enable_tuning=self.args.hyperparameter_tuning
            )

            logger.info(f"SchedulingPredictor treinado: {metrics}")

            # Promove se melhor
            if self.args.promote_if_better:
                await self._evaluate_and_promote(
                    model_name=f"scheduling-predictor-{config['model_type']}",
                    new_metrics=metrics,
                    metric_key='mae',
                    lower_is_better=True
                )

            return metrics

        except Exception as e:
            logger.error(f"Erro ao treinar SchedulingPredictor: {e}")
            raise

    async def train_load_predictor(self) -> Dict[str, Any]:
        """Treina LoadPredictor com dados reais do ClickHouse/MongoDB."""
        logger.info("=== Treinando LoadPredictor ===")

        try:
            # Escolhe data source (ClickHouse preferencial, fallback para MongoDB)
            data_source = self.clickhouse_client if self.clickhouse_client else self.db

            # Configura modelo
            config = {
                'model_name': 'load-predictor',
                'model_type': 'prophet',
                'forecast_horizons': [60, 360, 1440],
                'seasonality_mode': 'additive'
            }

            predictor = LoadPredictor(
                config=config,
                model_registry=self.model_registry,
                data_source=data_source  # Passa data source
            )

            # Carrega dados históricos reais
            training_data = await self._load_load_predictor_data()

            # Converte dataframe para lista de registros (timestamp, load) quando disponível
            training_records = []
            if training_data is not None and not training_data.empty:
                for _, row in training_data.iterrows():
                    ts = row['timestamp']
                    ts_iso = ts.isoformat() if hasattr(ts, 'isoformat') else str(ts)
                    training_records.append({
                        'timestamp': ts_iso,
                        'load': float(row['ticket_count'])
                    })

            if len(training_records) < self.args.min_samples:
                logger.warning(
                    f"Dados insuficientes para LoadPredictor: {len(training_records)} < {self.args.min_samples}, "
                    f"usando dados sintéticos"
                )
                # Treina com dados internos (sintéticos se necessário)
                all_metrics = await predictor.train_model(
                    training_window_days=self.args.training_window_days
                )
            else:
                logger.info(f"Treinando LoadPredictor com {len(training_records)} registros reais")
                # Treina com dados reais
                all_metrics = await predictor.train_model(
                    training_window_days=self.args.training_window_days,
                    training_data=training_records
                )

            logger.info(f"LoadPredictor treinado: {all_metrics}")

            # Promove se melhor (para cada horizonte)
            if self.args.promote_if_better:
                for horizon in [60, 360, 1440]:
                    model_name = f"load-predictor-{horizon}m"
                    metrics = all_metrics.get(f'{horizon}m', {})

                    await self._evaluate_and_promote(
                        model_name=model_name,
                        new_metrics=metrics,
                        metric_key='mape',
                        lower_is_better=True
                    )

            return all_metrics

        except Exception as e:
            logger.error(f"Erro ao treinar LoadPredictor: {e}")
            raise

    async def train_anomaly_detector(self) -> Dict[str, float]:
        """Treina AnomalyDetector."""
        logger.info("=== Treinando AnomalyDetector ===")

        try:
            # Carrega dados
            training_data = await self._load_ticket_history()

            if len(training_data) < self.args.min_samples:
                raise ValueError(
                    f"Dados insuficientes: {len(training_data)} < {self.args.min_samples}"
                )

            # Gera labels heurísticos (para treino semi-supervisionado)
            labels = self._generate_anomaly_labels(training_data)

            # Configura modelo
            model_type = self.args.model_algorithm or 'isolation_forest'
            config = {
                'model_name': 'anomaly-detector',
                'model_type': model_type,
                'contamination': 0.05
            }

            detector = AnomalyDetector(
                config=config,
                model_registry=self.model_registry
            )

            # Treina
            metrics = await detector.train_model(
                training_data=training_data,
                labels=labels
            )

            logger.info(f"AnomalyDetector treinado: {metrics}")

            # Promove se melhor
            if self.args.promote_if_better:
                await self._evaluate_and_promote(
                    model_name=f"anomaly-detector-{model_type}",
                    new_metrics=metrics,
                    metric_key='f1_score',
                    lower_is_better=False
                )

            return metrics

        except Exception as e:
            logger.error(f"Erro ao treinar AnomalyDetector: {e}")
            raise

    async def _load_ticket_history(self) -> pd.DataFrame:
        """Carrega histórico de tickets do MongoDB."""
        logger.info("Carregando histórico de tickets...")

        cutoff_date = datetime.now() - timedelta(days=self.args.training_window_days)
        cutoff_timestamp = cutoff_date.timestamp()

        # Query MongoDB
        cursor = self.db.execution_tickets.find({
            'status': 'COMPLETED',
            'completed_at': {'$gte': cutoff_timestamp},
            'actual_duration_ms': {'$exists': True, '$gt': 0}
        })

        records = []
        async for doc in cursor:
            record = {
                'ticket_id': str(doc.get('_id')),
                'type': doc.get('type', 'UNKNOWN'),
                'risk_weight': doc.get('risk_weight', 0),
                'capabilities': doc.get('capabilities', []),
                'qos': doc.get('qos', {}),
                'parameters': doc.get('parameters', {}),
                'timestamp': doc.get('created_at', datetime.now().timestamp()),
                'estimated_duration_ms': doc.get('estimated_duration_ms', 0),
                'actual_duration_ms': doc.get('actual_duration_ms', 0),
                'sla_timeout_ms': doc.get('sla_timeout_ms', 300000),
                'retry_count': doc.get('retry_count', 0),
                'status': doc.get('status')
            }
            records.append(record)

        df = pd.DataFrame(records)
        logger.info(f"Carregados {len(df)} tickets históricos")

        return df

    def _generate_anomaly_labels(self, df: pd.DataFrame) -> np.ndarray:
        """Gera labels de anomalia usando heurísticas."""
        labels = np.ones(len(df))  # 1 = normal

        # Marca anomalias baseado em regras
        for i, row in df.iterrows():
            capabilities_count = len(row.get('capabilities', []))
            risk_weight = row.get('risk_weight', 0)
            actual_duration = row.get('actual_duration_ms', 0)
            estimated_duration = row.get('estimated_duration_ms', 0)

            # Regra 1: Capabilities excessivas
            if capabilities_count > 12:
                labels[i] = -1

            # Regra 2: Duração muito diferente do estimado
            if estimated_duration > 0:
                ratio = actual_duration / estimated_duration
                if ratio > 3 or ratio < 0.3:
                    labels[i] = -1

            # Regra 3: Alto risco sem retries (suspeito)
            if risk_weight > 75 and row.get('retry_count', 0) == 0:
                labels[i] = -1

        anomaly_count = (labels == -1).sum()
        logger.info(f"Labels gerados: {anomaly_count} anomalias de {len(df)} tickets")

        return labels

    async def _evaluate_and_promote(
        self,
        model_name: str,
        new_metrics: Dict[str, float],
        metric_key: str,
        lower_is_better: bool
    ):
        """
        Compara novo modelo com produção e promove se melhor.

        Args:
            model_name: Nome do modelo
            new_metrics: Métricas do novo modelo
            metric_key: Métrica para comparação
            lower_is_better: Se True, valores menores são melhores
        """
        try:
            # Obtém métricas do modelo em produção
            prod_metadata = self.model_registry.get_model_metadata(
                model_name=model_name,
                stage="Production"
            )

            if not prod_metadata:
                logger.info(f"Nenhum modelo em produção para {model_name}, promovendo modelo mais recente")

                latest_versions = self.model_registry.client.get_latest_versions(
                    model_name,
                    stages=["None", "Staging"]
                )

                if not latest_versions:
                    logger.warning(f"Nenhuma versão encontrada para {model_name}")
                    return

                new_version = max(latest_versions, key=lambda v: v.creation_timestamp)

                self.model_registry.promote_model(
                    model_name=model_name,
                    version=str(new_version.version),
                    stage="Production"
                )
                logger.info(f"✅ Modelo {model_name} v{new_version.version} promovido para Production (primeiro modelo)")
                return

            prod_metric = prod_metadata.get('metrics', {}).get(metric_key)
            new_metric = new_metrics.get(metric_key)

            if prod_metric is None or new_metric is None:
                logger.warning(f"Métrica {metric_key} não encontrada, pulando promoção")
                return

            # Compara métricas
            improvement = 0.0
            if lower_is_better:
                improvement = (prod_metric - new_metric) / prod_metric
                should_promote = new_metric < prod_metric * 0.95  # 5% melhor
            else:
                improvement = (new_metric - prod_metric) / prod_metric
                should_promote = new_metric > prod_metric * 1.05  # 5% melhor

            logger.info(
                f"Comparação {model_name}: "
                f"Produção={prod_metric:.4f}, Novo={new_metric:.4f}, "
                f"Melhoria={improvement*100:.2f}%"
            )

            latest_versions = self.model_registry.client.get_latest_versions(
                model_name,
                stages=["None", "Staging"]
            )

            if not latest_versions:
                logger.warning(f"Nenhuma versão encontrada para {model_name}")
                return

            new_version = max(latest_versions, key=lambda v: v.creation_timestamp)

            if should_promote:
                logger.info(f"Promovendo {model_name} v{new_version.version} para Production")
                self.model_registry.promote_model(
                    model_name=model_name,
                    version=str(new_version.version),
                    stage="Production"
                )
                logger.info(f"✅ Modelo {model_name} v{new_version.version} promovido com sucesso")
            else:
                logger.info(f"Novo modelo não é significativamente melhor, mantendo Production")

        except Exception as e:
            logger.error(f"Erro ao avaliar/promover {model_name}: {e}")

    async def _load_load_predictor_data(self) -> pd.DataFrame:
        """
        Carrega dados de carga histórica do ClickHouse/MongoDB.

        Returns:
            DataFrame com timestamps e contagem de tickets por bucket de 5min
        """
        logger.info("Carregando dados de carga histórica...")

        cutoff_date = datetime.now() - timedelta(days=self.args.training_window_days)

        # Tenta ClickHouse primeiro
        if self.clickhouse_client:
            try:
                query = """
                SELECT
                    toStartOfInterval(completed_at, INTERVAL 5 MINUTE) as timestamp,
                    count(*) as ticket_count
                FROM execution_tickets
                WHERE status = 'COMPLETED'
                  AND completed_at >= %(cutoff)s
                GROUP BY timestamp
                ORDER BY timestamp
                """

                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    self.clickhouse_client.execute,
                    query,
                    {'cutoff': cutoff_date}
                )

                df = pd.DataFrame(result, columns=['timestamp', 'ticket_count'])
                logger.info(f"Carregados {len(df)} buckets de carga do ClickHouse")
                return df

            except Exception as e:
                logger.warning(f"Erro ao carregar do ClickHouse: {e}, tentando MongoDB")

        # Fallback para MongoDB
        cutoff_timestamp = cutoff_date.timestamp()

        pipeline = [
            {
                '$match': {
                    'status': 'COMPLETED',
                    'completed_at': {'$gte': cutoff_timestamp}
                }
            },
            {
                '$group': {
                    '_id': {
                        '$toDate': {
                            '$subtract': [
                                {'$multiply': ['$completed_at', 1000]},
                                {'$mod': [{'$multiply': ['$completed_at', 1000]}, 300000]}
                            ]
                        }
                    },
                    'ticket_count': {'$sum': 1}
                }
            },
            {
                '$sort': {'_id': 1}
            }
        ]

        cursor = self.db.execution_tickets.aggregate(pipeline)
        records = []
        async for doc in cursor:
            records.append({
                'timestamp': doc['_id'],
                'ticket_count': doc['ticket_count']
            })

        df = pd.DataFrame(records)
        logger.info(f"Carregados {len(df)} buckets de carga do MongoDB")
        return df

    async def cleanup(self):
        """Fecha conexões."""
        if self.clickhouse_client:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    self.clickhouse_client.disconnect
                )
                logger.info("ClickHouse client fechado")
            except Exception as e:
                logger.warning(f"Erro ao fechar ClickHouse client: {e}")

        if self.mongo_client:
            self.mongo_client.close()
            logger.info("MongoDB client fechado")


async def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description="Pipeline de treinamento de modelos preditivos"
    )

    parser.add_argument(
        '--model-type',
        choices=['scheduling', 'load', 'anomaly', 'all'],
        default='all',
        help='Tipo de modelo a treinar'
    )

    parser.add_argument(
        '--training-window-days',
        type=int,
        default=540,
        help='Janela de dados para treinamento (dias)'
    )

    parser.add_argument(
        '--model-algorithm',
        choices=['xgboost', 'lightgbm', 'prophet', 'arima', 'isolation_forest', 'autoencoder'],
        help='Algoritmo específico a usar'
    )

    parser.add_argument(
        '--hyperparameter-tuning',
        action='store_true',
        help='Ativa otimização de hiperparâmetros com Optuna'
    )

    parser.add_argument(
        '--promote-if-better',
        action='store_true',
        help='Promove para Production se métricas melhorarem >5%%'
    )

    parser.add_argument(
        '--min-samples',
        type=int,
        default=1000,
        help='Número mínimo de amostras para treinamento'
    )

    args = parser.parse_args()

    # Inicializa trainer
    trainer = PredictiveModelsTrainer(args)

    try:
        await trainer.setup()

        results = {}

        # Treina modelos conforme especificado
        if args.model_type in ['scheduling', 'all']:
            results['scheduling'] = await trainer.train_scheduling_predictor()

        if args.model_type in ['load', 'all']:
            results['load'] = await trainer.train_load_predictor()

        if args.model_type in ['anomaly', 'all']:
            results['anomaly'] = await trainer.train_anomaly_detector()

        # Sumário
        logger.info("=== TREINAMENTO CONCLUÍDO ===")
        for model_type, metrics in results.items():
            logger.info(f"{model_type}: {metrics}")

        logger.info("Pipeline de treinamento finalizado com sucesso")
        return 0

    except Exception as e:
        logger.error(f"Erro no pipeline de treinamento: {e}", exc_info=True)
        return 1

    finally:
        await trainer.cleanup()


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
