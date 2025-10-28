#!/usr/bin/env python3
"""
Script para executar políticas de retenção do Neural Hive Mind.

Este script é usado pelo CronJob Kubernetes para executar políticas
de retenção periodicamente.

Uso:
    python scripts/run_retention_policies.py
    python scripts/run_retention_policies.py --dry-run
    python scripts/run_retention_policies.py --policy-name high_risk_extended
"""
import os
import sys
import argparse
import time
import structlog
from datetime import datetime

# Adicionar path do módulo
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'libraries', 'python'))

from neural_hive_specialists.config import SpecialistConfig
from neural_hive_specialists.ledger.retention_manager import RetentionManager
from neural_hive_specialists.compliance import PIIDetector, FieldEncryptor

# Configurar logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


def run_retention_policies(dry_run: bool = False, policy_name: str = None, verbose: bool = False):
    """
    Executa políticas de retenção.

    Args:
        dry_run: Simular execução sem modificar dados
        policy_name: Nome de política específica (None para todas)
        verbose: Logging detalhado
    """
    try:
        logger.info(
            "Iniciando execução de políticas de retenção",
            dry_run=dry_run,
            policy_name=policy_name,
            timestamp=datetime.utcnow().isoformat()
        )

        # Carregar configuração
        config = SpecialistConfig()

        # Validar configuração necessária
        if not config.mongodb_uri:
            logger.error("MONGODB_URI não configurado")
            return 1

        # Inicializar componentes de compliance
        pii_detector = None
        field_encryptor = None

        if config.enable_pii_detection:
            try:
                pii_detector = PIIDetector(config)
                logger.info("PIIDetector inicializado")
            except Exception as e:
                logger.warning("Falha ao inicializar PIIDetector", error=str(e))

        if config.enable_field_encryption:
            try:
                field_encryptor = FieldEncryptor(config)
                logger.info("FieldEncryptor inicializado")
            except Exception as e:
                logger.warning("Falha ao inicializar FieldEncryptor", error=str(e))

        # Inicializar RetentionManager
        retention_config = {
            'mongodb_uri': config.mongodb_uri,
            'mongodb_database': config.mongodb_database,
            'retention_policies': []  # Usar políticas padrão
        }

        retention_manager = RetentionManager(
            retention_config,
            pii_detector=pii_detector,
            field_encryptor=field_encryptor
        )

        logger.info(
            "RetentionManager inicializado",
            policies_count=len(retention_manager.policies),
            has_pii_detector=pii_detector is not None,
            has_field_encryptor=field_encryptor is not None
        )

        # Dry-run
        if dry_run:
            logger.info("MODO DRY-RUN: Nenhuma modificação será feita")
            # Simular execução
            status = retention_manager.get_retention_status()
            logger.info(
                "Status de retenção (dry-run)",
                **status
            )
            print(f"\n✓ Dry-run concluído com sucesso")
            print(f"  Total de documentos: {status.get('total_documents', 0)}")
            print(f"  Documentos expirados: {status.get('expired_documents', 0)}")
            print(f"  Documentos mascarados: {status.get('masked_documents', 0)}")
            return 0

        # Executar políticas
        start_time = time.time()

        if policy_name:
            logger.info(f"Executando política específica: {policy_name}")
            # Filtrar políticas
            matching_policies = [p for p in retention_manager.policies if p.name == policy_name]
            if not matching_policies:
                logger.error(f"Política não encontrada: {policy_name}")
                return 1
            retention_manager.policies = matching_policies

        stats = retention_manager.apply_retention_policies()

        duration = time.time() - start_time

        logger.info(
            "Políticas de retenção executadas",
            **stats,
            duration_seconds=duration
        )

        # Exibir resumo
        print(f"\n✓ Políticas de retenção executadas com sucesso")
        print(f"  Documentos processados: {stats['documents_processed']}")
        print(f"  Documentos mascarados: {stats['documents_masked']}")
        print(f"  Documentos deletados: {stats['documents_deleted']}")
        print(f"  Erros: {stats['errors']}")
        print(f"  Duração: {duration:.2f}s")

        # Push métricas para Prometheus Pushgateway (opcional)
        pushgateway_url = os.getenv('PROMETHEUS_PUSHGATEWAY_URL')
        if pushgateway_url:
            try:
                from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

                registry = CollectorRegistry()

                gauge_processed = Gauge(
                    'retention_documents_processed_total',
                    'Total de documentos processados',
                    registry=registry
                )
                gauge_processed.set(stats['documents_processed'])

                gauge_masked = Gauge(
                    'retention_documents_masked_total',
                    'Total de documentos mascarados',
                    registry=registry
                )
                gauge_masked.set(stats['documents_masked'])

                gauge_deleted = Gauge(
                    'retention_documents_deleted_total',
                    'Total de documentos deletados',
                    registry=registry
                )
                gauge_deleted.set(stats['documents_deleted'])

                gauge_duration = Gauge(
                    'retention_execution_duration_seconds',
                    'Duração de execução',
                    registry=registry
                )
                gauge_duration.set(duration)

                push_to_gateway(
                    pushgateway_url,
                    job='retention_policy_job',
                    registry=registry
                )

                logger.info("Métricas enviadas para Pushgateway", url=pushgateway_url)

            except Exception as e:
                logger.warning("Falha ao enviar métricas para Pushgateway", error=str(e))

        return 0 if stats['errors'] == 0 else 1

    except Exception as e:
        logger.error("Erro fatal ao executar políticas de retenção", error=str(e), exc_info=True)
        print(f"\n❌ Erro: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description='Executa políticas de retenção do Neural Hive Mind',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Executar todas as políticas
  python scripts/run_retention_policies.py

  # Modo dry-run (sem modificar dados)
  python scripts/run_retention_policies.py --dry-run

  # Executar política específica
  python scripts/run_retention_policies.py --policy-name high_risk_extended

  # Logging detalhado
  python scripts/run_retention_policies.py --verbose

Variáveis de Ambiente:
  MONGODB_URI                  - URI do MongoDB (obrigatório)
  MONGODB_DATABASE             - Nome do database (default: neural_hive)
  ENABLE_PII_DETECTION         - Habilitar detecção PII (default: true)
  ENABLE_FIELD_ENCRYPTION      - Habilitar criptografia (default: true)
  ENCRYPTION_KEY_PATH          - Caminho da chave de criptografia
  PROMETHEUS_PUSHGATEWAY_URL   - URL do Pushgateway (opcional)

Exit Codes:
  0 - Sucesso (sem erros)
  1 - Erro (falhas durante execução)
        """
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simular execução sem modificar dados'
    )

    parser.add_argument(
        '--policy-name',
        type=str,
        help='Nome de política específica para executar'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Logging detalhado'
    )

    args = parser.parse_args()

    # Executar
    exit_code = run_retention_policies(
        dry_run=args.dry_run,
        policy_name=args.policy_name,
        verbose=args.verbose
    )

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
