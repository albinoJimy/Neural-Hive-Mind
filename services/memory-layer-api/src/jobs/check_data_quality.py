#!/usr/bin/env python3
"""
Job de verificação de qualidade de dados

Verifica a qualidade dos dados armazenados no MongoDB e registra métricas.
Roda como CronJob a cada 6 horas.

As regras de qualidade são carregadas do arquivo YAML montado em /etc/memory-layer/policies/quality-rules.yaml
"""

import asyncio
import os
import sys
import structlog
import yaml
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

# Adiciona o diretório raiz ao path para importações
sys.path.insert(0, '/app')

from src.clients.mongodb_client import MongoDBClient
from src.config.settings import Settings
from src.services.data_quality_monitor import QUALITY_SCORE_GAUGE


logger = structlog.get_logger(__name__)

# Caminho padrão do arquivo de regras de qualidade
DEFAULT_QUALITY_RULES_PATH = '/etc/memory-layer/policies/quality-rules.yaml'


def load_quality_rules(rules_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Carrega regras de qualidade do arquivo YAML

    Args:
        rules_path: Caminho do arquivo de regras (usa env var ou padrão se não fornecido)

    Returns:
        Dicionário com as regras de qualidade
    """
    if rules_path is None:
        rules_path = os.getenv('QUALITY_RULES_FILE', DEFAULT_QUALITY_RULES_PATH)

    rules_file = Path(rules_path)

    if not rules_file.exists():
        logger.warning(
            "Arquivo de regras de qualidade não encontrado, usando valores padrão",
            path=rules_path
        )
        return get_default_quality_rules()

    try:
        with open(rules_file, 'r') as f:
            rules = yaml.safe_load(f)
            logger.info("Regras de qualidade carregadas do arquivo", path=rules_path)
            return rules
    except Exception as e:
        logger.error(
            "Erro ao carregar regras de qualidade, usando valores padrão",
            path=rules_path,
            error=str(e)
        )
        return get_default_quality_rules()


def get_default_quality_rules() -> Dict[str, Any]:
    """Retorna regras de qualidade padrão como fallback"""
    return {
        'version': '1.0',
        'rules': {
            'completeness': {
                'enabled': True,
                'threshold': 0.95,
                'required_fields': ['intent_id', 'timestamp', 'source']
            },
            'accuracy': {
                'enabled': True,
                'threshold': 0.95
            },
            'freshness': {
                'enabled': True,
                'max_age_hours': 24
            }
        }
    }


class DataQualityChecker:
    """Verificador de qualidade de dados"""

    def __init__(self, settings: Settings, rules: Optional[Dict[str, Any]] = None):
        self.settings = settings
        self.mongodb_client = None
        self.clickhouse_client = None
        self.sample_size = int(os.getenv('SAMPLE_SIZE', '1000'))

        # Configurações de detecção de anomalias
        self.enable_anomaly_detection = os.getenv('ENABLE_ANOMALY_DETECTION', 'false').lower() == 'true'
        self.anomaly_window_hours = int(os.getenv('ANOMALY_WINDOW_HOURS', '24'))
        self.anomaly_baseline_days = int(os.getenv('ANOMALY_BASELINE_DAYS', '7'))

        # Carrega regras do arquivo YAML ou usa as fornecidas
        self.rules = rules if rules is not None else load_quality_rules()

        # Extrai thresholds das regras carregadas
        rules_config = self.rules.get('rules', {})

        self.completeness_threshold = rules_config.get('completeness', {}).get(
            'threshold',
            self.settings.completeness_threshold
        )
        self.accuracy_threshold = rules_config.get('accuracy', {}).get(
            'threshold',
            self.settings.accuracy_threshold
        )
        self.freshness_threshold_hours = rules_config.get('freshness', {}).get(
            'max_age_hours',
            self.settings.freshness_threshold_hours
        )
        self.required_fields = rules_config.get('completeness', {}).get(
            'required_fields',
            ['intent_id', 'timestamp', 'source']
        )

        # Calcula quality_threshold como média dos thresholds (convertido para porcentagem)
        self.quality_threshold = (
            (self.completeness_threshold + self.accuracy_threshold) / 2
        ) * 100

        logger.info(
            "DataQualityChecker inicializado com regras",
            completeness_threshold=self.completeness_threshold,
            accuracy_threshold=self.accuracy_threshold,
            freshness_threshold_hours=self.freshness_threshold_hours,
            quality_threshold=self.quality_threshold,
            rules_version=self.rules.get('version', 'unknown')
        )

    async def initialize(self):
        """Inicializa o cliente MongoDB"""
        logger.info("Inicializando cliente MongoDB...")

        self.mongodb_client = MongoDBClient(
            uri=self.settings.mongodb_uri,
            database=self.settings.mongodb_database
        )
        await self.mongodb_client.initialize()

        logger.info("Cliente MongoDB inicializado com sucesso")

    async def check_completeness(self, collection: str, required_fields: List[str]) -> Dict:
        """
        Verifica completude dos dados

        Args:
            collection: Nome da coleção
            required_fields: Campos obrigatórios

        Returns:
            Métricas de completude
        """
        logger.info(f"Verificando completude em {collection}...")

        # Busca amostra de documentos
        documents = await self.mongodb_client.find(
            collection=collection,
            filter={},
            limit=self.sample_size,
            sort=[('timestamp', -1)]  # Mais recentes primeiro
        )

        if not documents:
            return {
                'completeness_score': 0.0,
                'total_documents': 0,
                'missing_fields': {}
            }

        # Verifica campos faltantes
        missing_counts = {field: 0 for field in required_fields}
        total_docs = len(documents)

        for doc in documents:
            for field in required_fields:
                if field not in doc or doc[field] is None or doc[field] == '':
                    missing_counts[field] += 1

        # Calcula score de completude
        total_checks = len(required_fields) * total_docs
        total_missing = sum(missing_counts.values())
        completeness_score = ((total_checks - total_missing) / total_checks) * 100

        result = {
            'completeness_score': round(completeness_score, 2),
            'total_documents': total_docs,
            'missing_fields': {
                field: {
                    'count': count,
                    'percentage': round((count / total_docs) * 100, 2)
                }
                for field, count in missing_counts.items()
                if count > 0
            }
        }

        logger.info(
            f"Completude verificada",
            collection=collection,
            score=result['completeness_score']
        )

        return result

    async def check_freshness(self, collection: str) -> Dict:
        """
        Verifica frescor dos dados

        Args:
            collection: Nome da coleção

        Returns:
            Métricas de frescor
        """
        logger.info(f"Verificando frescor em {collection}...")

        # Calcula threshold de frescor usando valor carregado das regras
        freshness_cutoff = datetime.utcnow() - timedelta(
            hours=self.freshness_threshold_hours
        )

        # Conta documentos recentes vs antigos
        total_docs = await self.mongodb_client.count_documents(
            collection=collection,
            filter={}
        )

        fresh_docs = await self.mongodb_client.count_documents(
            collection=collection,
            filter={'timestamp': {'$gte': freshness_cutoff}}
        )

        if total_docs == 0:
            freshness_score = 0.0
        else:
            freshness_score = (fresh_docs / total_docs) * 100

        result = {
            'freshness_score': round(freshness_score, 2),
            'total_documents': total_docs,
            'fresh_documents': fresh_docs,
            'stale_documents': total_docs - fresh_docs,
            'threshold_hours': self.freshness_threshold_hours
        }

        logger.info(
            f"Frescor verificado",
            collection=collection,
            score=result['freshness_score']
        )

        return result

    async def check_consistency(self, collection: str) -> Dict:
        """
        Verifica consistência dos dados

        Args:
            collection: Nome da coleção

        Returns:
            Métricas de consistência
        """
        logger.info(f"Verificando consistência em {collection}...")

        # Busca amostra de documentos
        documents = await self.mongodb_client.find(
            collection=collection,
            filter={},
            limit=self.sample_size
        )

        if not documents:
            return {
                'consistency_score': 0.0,
                'total_documents': 0,
                'issues': []
            }

        # Verifica inconsistências comuns
        issues = []
        inconsistent_count = 0

        for doc in documents:
            # Verifica timestamp válido
            if 'timestamp' in doc:
                if isinstance(doc['timestamp'], datetime):
                    if doc['timestamp'] > datetime.utcnow():
                        inconsistent_count += 1
                        issues.append({
                            'type': 'future_timestamp',
                            'field': 'timestamp'
                        })

            # Verifica IDs duplicados (exemplo)
            # Adicione mais verificações conforme necessário

        total_docs = len(documents)
        consistency_score = ((total_docs - inconsistent_count) / total_docs) * 100

        result = {
            'consistency_score': round(consistency_score, 2),
            'total_documents': total_docs,
            'inconsistent_documents': inconsistent_count,
            'issues_sample': issues[:10]  # Primeiros 10 issues
        }

        logger.info(
            f"Consistência verificada",
            collection=collection,
            score=result['consistency_score']
        )

        return result

    async def save_quality_metrics(self, collection: str, metrics: Dict, anomalies: List[Dict] = None):
        """
        Salva métricas de qualidade no MongoDB e publica para Prometheus

        Args:
            collection: Coleção verificada
            metrics: Métricas coletadas
            anomalies: Lista de anomalias detectadas (opcional)
        """
        overall_score = round(
            (metrics['completeness']['completeness_score'] +
             metrics['freshness']['freshness_score'] +
             metrics['consistency']['consistency_score']) / 3,
            2
        )

        quality_doc = {
            'collection': collection,
            'timestamp': datetime.utcnow(),
            'metrics': metrics,
            'overall_score': overall_score,
            'anomalies': anomalies or []
        }

        await self.mongodb_client.insert_one(
            collection='data_quality_metrics',
            document=quality_doc
        )

        # Publica métrica para Prometheus (normaliza para 0-1)
        QUALITY_SCORE_GAUGE.labels(data_type=collection).set(overall_score / 100.0)

        logger.info(
            "Métricas de qualidade salvas",
            collection=collection,
            overall_score=quality_doc['overall_score'],
            anomalies_count=len(anomalies) if anomalies else 0
        )

    async def check_collection(self, collection: str, required_fields: List[str]) -> Dict:
        """
        Verifica qualidade de uma coleção

        Args:
            collection: Nome da coleção
            required_fields: Campos obrigatórios

        Returns:
            Métricas completas de qualidade
        """
        logger.info(f"Verificando qualidade de {collection}...")

        # Executa todas as verificações
        completeness = await self.check_completeness(collection, required_fields)
        freshness = await self.check_freshness(collection)
        consistency = await self.check_consistency(collection)

        metrics = {
            'completeness': completeness,
            'freshness': freshness,
            'consistency': consistency
        }

        # Detecta anomalias se habilitado
        anomalies = []
        if self.enable_anomaly_detection:
            from src.services.data_quality_monitor import DataQualityMonitor

            monitor = DataQualityMonitor(
                self.mongodb_client,
                self.settings,
                clickhouse_client=self.clickhouse_client
            )

            for metric_name in ['completeness_score', 'freshness_score', 'consistency_score']:
                detected = await monitor.detect_anomalies(
                    data_type=collection,
                    metric=metric_name,
                    window_hours=self.anomaly_window_hours,
                    baseline_days=self.anomaly_baseline_days
                )
                anomalies.extend(detected)

            if anomalies:
                logger.warning(
                    "Anomalias detectadas",
                    collection=collection,
                    count=len(anomalies)
                )

        # Salva métricas com anomalias
        await self.save_quality_metrics(collection, metrics, anomalies)

        return metrics

    async def run(self):
        """Executa verificação de qualidade em todas as coleções"""
        try:
            await self.initialize()

            # Define coleções e campos obrigatórios
            # Usa required_fields das regras carregadas como padrão
            default_required = self.required_fields
            collections_config = {
                'operational_context': default_required + ['context'] if 'context' not in default_required else default_required,
                'data_lineage': ['entity_id', 'operation', 'timestamp'],
                'data_quality_metrics': ['collection', 'metrics', 'timestamp']
            }

            all_passed = True
            results = {}

            for collection, required_fields in collections_config.items():
                metrics = await self.check_collection(collection, required_fields)

                # Verifica se passou nos thresholds
                overall_score = round(
                    (metrics['completeness']['completeness_score'] +
                     metrics['freshness']['freshness_score'] +
                     metrics['consistency']['consistency_score']) / 3,
                    2
                )

                passed = overall_score >= self.quality_threshold
                results[collection] = {
                    'overall_score': overall_score,
                    'passed': passed
                }

                if not passed:
                    all_passed = False
                    logger.warning(
                        f"Qualidade abaixo do threshold",
                        collection=collection,
                        score=overall_score,
                        threshold=self.quality_threshold
                    )

            logger.info(
                "Verificação de qualidade completa",
                collections_checked=len(results),
                all_passed=all_passed,
                results=results
            )

            if not all_passed:
                logger.warning("Algumas coleções não passaram no threshold de qualidade")

        except Exception as e:
            logger.error("Erro ao verificar qualidade dos dados", error=str(e))
            raise

        finally:
            # Cleanup
            if self.mongodb_client:
                await self.mongodb_client.close()


async def main():
    """Função principal"""
    # Configura logging
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer()
        ]
    )

    logger.info("Iniciando job de verificação de qualidade de dados")

    # Carrega configurações
    settings = Settings()

    # Executa verificação
    checker = DataQualityChecker(settings)
    await checker.run()

    logger.info("Job de verificação de qualidade concluído com sucesso")


if __name__ == "__main__":
    asyncio.run(main())
