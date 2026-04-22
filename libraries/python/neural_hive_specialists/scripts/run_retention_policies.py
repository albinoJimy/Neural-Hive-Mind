#!/usr/bin/env python3
"""
Script para executar políticas de retenção do Neural Hive.

Este script deve ser executado periodicamente (via CronJob) para aplicar
políticas de retenção de dados conforme LGPD/GDPR.

Uso:
    python run_retention_policies.py
    python run_retention_policies.py --dry-run
    python run_retention_policies.py --policy-name high_risk_extended
"""
import argparse
import os
import sys
import time
from datetime import UTC, datetime


def load_config():
    """Carrega configuração de variáveis de ambiente."""
    # Usar configuração simplificada para script standalone
    # Não usar SpecialistConfig completo que requer muitos campos

    class SimpleConfig:
        """Configuração simplificada para script de retenção."""

        def __init__(self):
            # MongoDB
            self.mongodb_uri = os.getenv("MONGODB_URI")
            if not self.mongodb_uri:
                raise ValueError("MONGODB_URI é obrigatório")

            self.mongodb_database = os.getenv("MONGODB_DATABASE", "neural_hive")

            # Compliance flags
            self.enable_pii_detection = os.getenv("ENABLE_PII_DETECTION", "true").lower() == "true"
            self.enable_field_encryption = (
                os.getenv("ENABLE_FIELD_ENCRYPTION", "true").lower() == "true"
            )
            self.enable_audit_logging = os.getenv("ENABLE_AUDIT_LOGGING", "true").lower() == "true"

            # Encryption
            self.encryption_key_path = os.getenv("ENCRYPTION_KEY_PATH")

            # Retention
            self.enable_automated_retention = (
                os.getenv("ENABLE_AUTOMATED_RETENTION", "true").lower() == "true"
            )
            self.default_retention_days = int(os.getenv("DEFAULT_RETENTION_DAYS", "365"))

            # PII detection (valores padrão)
            self.pii_detection_languages = ["pt", "en"]
            self.pii_entities_to_detect = [
                "PERSON",
                "EMAIL_ADDRESS",
                "PHONE_NUMBER",
                "CREDIT_CARD",
                "IBAN_CODE",
                "IP_ADDRESS",
                "US_SSN",
                "CPF",
            ]
            self.pii_anonymization_strategy = os.getenv("PII_ANONYMIZATION_STRATEGY", "replace")

            # Fields to encrypt (padrão)
            self.fields_to_encrypt = [
                "correlation_id",
                "trace_id",
                "span_id",
                "intent_id",
            ]
            self.encryption_algorithm = os.getenv("ENCRYPTION_ALGORITHM", "fernet")

            # Audit log
            self.audit_log_collection = os.getenv("AUDIT_LOG_COLLECTION", "compliance_audit_log")
            self.audit_log_retention_days = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "730"))

    try:
        config = SimpleConfig()
        return config
    except Exception as e:
        print(f"ERRO ao carregar configuração: {e}", file=sys.stderr)
        print("\nVariáveis de ambiente necessárias:", file=sys.stderr)
        print("  - MONGODB_URI", file=sys.stderr)
        print("  - MONGODB_DATABASE (opcional, default: neural_hive)", file=sys.stderr)
        sys.exit(1)


def initialize_compliance_components(config):
    """
    Inicializa componentes de compliance (PIIDetector, FieldEncryptor).

    Args:
        config: SpecialistConfig

    Returns:
        Tupla (pii_detector, field_encryptor)
    """
    pii_detector = None
    field_encryptor = None

    # Inicializar PIIDetector se habilitado
    if config.enable_pii_detection:
        try:
            from neural_hive_specialists.compliance import PIIDetector

            pii_detector = PIIDetector(config)
            print("✅ PIIDetector inicializado")
        except Exception as e:
            print(f"⚠️  PIIDetector não disponível: {e}", file=sys.stderr)

    # Inicializar FieldEncryptor se habilitado
    if config.enable_field_encryption:
        try:
            from neural_hive_specialists.compliance import FieldEncryptor

            field_encryptor = FieldEncryptor(config)
            print("✅ FieldEncryptor inicializado")
        except Exception as e:
            print(f"⚠️  FieldEncryptor não disponível: {e}", file=sys.stderr)

    return pii_detector, field_encryptor


def apply_retention_policies(config, dry_run=False, policy_name=None):
    """
    Aplica políticas de retenção.

    Args:
        config: SpecialistConfig
        dry_run: Se True, simula execução sem modificar dados
        policy_name: Nome de política específica (opcional)

    Returns:
        Estatísticas de execução
    """
    from neural_hive_specialists.ledger import RetentionManager

    # Inicializar componentes de compliance
    pii_detector, field_encryptor = initialize_compliance_components(config)

    # Construir configuração do RetentionManager
    retention_config = {
        "mongodb_uri": config.mongodb_uri,
        "mongodb_database": config.mongodb_database,
        "retention_policies": [],  # Usar políticas padrão
    }

    # Inicializar RetentionManager
    try:
        retention_manager = RetentionManager(
            config=retention_config,
            pii_detector=pii_detector,
            field_encryptor=field_encryptor,
        )
        print("✅ RetentionManager inicializado")
    except Exception as e:
        print(f"ERRO ao inicializar RetentionManager: {e}", file=sys.stderr)
        sys.exit(1)

    # Executar políticas
    print(f"\n{'🔍 [DRY RUN]' if dry_run else '🚀'} Aplicando políticas de retenção...")
    print(f"⏰ Timestamp: {datetime.now(UTC).isoformat()}Z\n")

    if dry_run:
        print("⚠️  Modo DRY RUN: nenhum dado será modificado\n")
        # Em modo dry run, apenas simular
        stats = {
            "documents_processed": 0,
            "documents_masked": 0,
            "documents_deleted": 0,
            "errors": 0,
        }
        print("   (Implementar lógica de dry run aqui)")
        return stats
    else:
        start_time = time.time()

        try:
            stats = retention_manager.apply_retention_policies()
            duration = time.time() - start_time

            print("\n✅ Políticas aplicadas com sucesso!")
            print(f"⏱️  Duração: {duration:.2f}s")
            print("\n📊 Estatísticas:")
            print(f"   Documentos processados: {stats.get('documents_processed', 0)}")
            print(f"   Documentos mascarados:  {stats.get('documents_masked', 0)}")
            print(f"   Documentos deletados:   {stats.get('documents_deleted', 0)}")
            print(f"   Erros:                  {stats.get('errors', 0)}")

            return stats

        except Exception as e:
            print(f"\n❌ ERRO ao aplicar políticas: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc()
            sys.exit(1)


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description="Executa políticas de retenção do Neural Hive",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Executar políticas de retenção
  python run_retention_policies.py

  # Simular execução (dry run)
  python run_retention_policies.py --dry-run

  # Executar política específica
  python run_retention_policies.py --policy-name high_risk_extended

  # Verbose mode
  python run_retention_policies.py --verbose

Variáveis de ambiente necessárias:
  MONGODB_URI              - URI de conexão MongoDB
  MONGODB_DATABASE         - Nome do database (default: neural_hive)
  ENABLE_PII_DETECTION     - Habilitar detecção de PII (default: true)
  ENABLE_FIELD_ENCRYPTION  - Habilitar criptografia (default: true)
  ENCRYPTION_KEY_PATH      - Path para chave de criptografia

Agendamento (Kubernetes CronJob):
  Veja: k8s/cronjobs/retention-policy-job.yaml
  Schedule recomendado: diariamente às 2h UTC (0 2 * * *)
        """,
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="Simular execução sem modificar dados"
    )

    parser.add_argument("--policy-name", type=str, help="Executar apenas política específica")

    parser.add_argument("--verbose", action="store_true", help="Logging detalhado")

    args = parser.parse_args()

    # Configurar logging
    if args.verbose:
        import structlog

        structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(10))  # DEBUG level

    # Carregar configuração
    print("📝 Carregando configuração...")
    config = load_config()

    # Aplicar políticas
    stats = apply_retention_policies(config, dry_run=args.dry_run, policy_name=args.policy_name)

    # Exit code baseado em erros
    exit_code = 0 if stats.get("errors", 0) == 0 else 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
