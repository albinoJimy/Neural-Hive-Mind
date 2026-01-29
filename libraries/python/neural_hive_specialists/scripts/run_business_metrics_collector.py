#!/usr/bin/env python3
"""
Script para executar coleta de business metrics do Neural Hive.

Este script deve ser executado periodicamente (via CronJob) para coletar
métricas de negócio correlacionando opiniões com decisões de consenso.

Uso:
    python run_business_metrics_collector.py
    python run_business_metrics_collector.py --dry-run
    python run_business_metrics_collector.py --window-hours 48
    python run_business_metrics_collector.py --specialist-type technical
"""
import argparse
import os
import sys
import time
from datetime import datetime
from typing import Dict, Any


def load_config() -> Dict[str, Any]:
    """
    Carrega configuração de variáveis de ambiente.

    Returns:
        Dict com configuração
    """
    try:
        config = {
            # MongoDB Ledger
            "mongodb_uri": os.getenv("MONGODB_URI"),
            "mongodb_database": os.getenv("MONGODB_DATABASE", "neural_hive"),
            # MongoDB Consensus
            "consensus_mongodb_uri": os.getenv("CONSENSUS_MONGODB_URI")
            or os.getenv("MONGODB_URI"),
            "consensus_mongodb_database": os.getenv(
                "CONSENSUS_MONGODB_DATABASE", "neural_hive"
            ),
            "consensus_collection_name": os.getenv(
                "CONSENSUS_COLLECTION_NAME", "consensus_decisions"
            ),
            # Business Metrics
            "enable_business_metrics": os.getenv(
                "ENABLE_BUSINESS_METRICS", "true"
            ).lower()
            == "true",
            "business_metrics_window_hours": int(
                os.getenv("BUSINESS_METRICS_WINDOW_HOURS", "24")
            ),
            # Business Value Tracking
            "enable_business_value_tracking": os.getenv(
                "ENABLE_BUSINESS_VALUE_TRACKING", "false"
            ).lower()
            == "true",
            "execution_ticket_api_url": os.getenv("EXECUTION_TICKET_API_URL"),
            # Anomaly Detection
            "enable_anomaly_detection": os.getenv(
                "ENABLE_ANOMALY_DETECTION", "true"
            ).lower()
            == "true",
            "anomaly_contamination": float(os.getenv("ANOMALY_CONTAMINATION", "0.1")),
            "anomaly_n_estimators": int(os.getenv("ANOMALY_N_ESTIMATORS", "100")),
            "anomaly_model_path": os.getenv(
                "ANOMALY_MODEL_PATH",
                "/data/models/anomaly_detector_{specialist_type}.pkl",
            ),
            "anomaly_alert_threshold": float(
                os.getenv("ANOMALY_ALERT_THRESHOLD", "-0.3")
            ),
            # ClickHouse (opcional)
            "clickhouse_uri": os.getenv("CLICKHOUSE_URI"),
            "clickhouse_database": os.getenv("CLICKHOUSE_DATABASE", "neural_hive"),
            "enable_metrics_history": os.getenv(
                "ENABLE_METRICS_HISTORY", "false"
            ).lower()
            == "true",
            # Prometheus Pushgateway (opcional)
            "pushgateway_url": os.getenv("PUSHGATEWAY_URL"),
        }

        # Validar campos obrigatórios
        if not config["mongodb_uri"]:
            raise ValueError("MONGODB_URI é obrigatório")

        return config

    except Exception as e:
        print(f"❌ ERRO ao carregar configuração: {e}", file=sys.stderr)
        print("\n📋 Variáveis de ambiente necessárias:", file=sys.stderr)
        print("  ✅ MONGODB_URI - URI do MongoDB do ledger", file=sys.stderr)
        print(
            "  ⚙️  CONSENSUS_MONGODB_URI - URI do MongoDB do consensus (opcional, usa MONGODB_URI se não fornecido)",
            file=sys.stderr,
        )
        print(
            "  ⚙️  BUSINESS_METRICS_WINDOW_HOURS - Janela de análise em horas (default: 24)",
            file=sys.stderr,
        )
        sys.exit(1)


def initialize_metrics_registry():
    """
    Inicializa registry de SpecialistMetrics para todos os especialistas.

    Returns:
        Dict mapeando specialist_type para SpecialistMetrics
    """
    from neural_hive_specialists.metrics import SpecialistMetrics

    specialist_types = [
        "technical",
        "business",
        "behavior",
        "evolution",
        "architecture",
    ]
    metrics_registry = {}

    for specialist_type in specialist_types:
        metrics_registry[specialist_type] = SpecialistMetrics(
            specialist_type=specialist_type
        )

    print(f"✅ Metrics registry initialized for {len(specialist_types)} specialists")

    return metrics_registry


def initialize_business_metrics_collector(
    config: Dict[str, Any], metrics_registry: Dict
):
    """
    Inicializa BusinessMetricsCollector.

    Args:
        config: Configuração
        metrics_registry: Registry de métricas

    Returns:
        BusinessMetricsCollector instance
    """
    from neural_hive_specialists.observability import BusinessMetricsCollector

    collector = BusinessMetricsCollector(
        config=config, metrics_registry=metrics_registry
    )

    print("✅ BusinessMetricsCollector initialized")

    return collector


def initialize_anomaly_detector(config: Dict[str, Any]):
    """
    Inicializa AnomalyDetector.

    Args:
        config: Configuração

    Returns:
        AnomalyDetector instance ou None se desabilitado
    """
    if not config.get("enable_anomaly_detection"):
        print("⚠️  Anomaly detection disabled")
        return None

    from neural_hive_specialists.observability import AnomalyDetector

    detector = AnomalyDetector(config=config)

    print("✅ AnomalyDetector initialized")

    return detector


def build_anomaly_features(metrics_summary: Dict[str, Any]) -> Dict[str, float]:
    """
    Constrói dict completo de features para AnomalyDetector.

    Args:
        metrics_summary: Summary de métricas do SpecialistMetrics

    Returns:
        Dict com features esperadas pelo AnomalyDetector
    """
    business_metrics = metrics_summary.get("business_metrics", {})

    # Mapear campos para nomes esperados pelo AnomalyDetector
    features = {
        "consensus_agreement_rate": business_metrics.get(
            "consensus_agreement_rate", 0.0
        ),
        "false_positive_rate": business_metrics.get("false_positive_rate", 0.0),
        "false_negative_rate": business_metrics.get("false_negative_rate", 0.0),
        "avg_confidence_score": metrics_summary.get(
            "accuracy_score", 0.0
        ),  # accuracy_score é proxy de confidence
        "avg_risk_score": 0.0,  # Não disponível no summary, usar 0.0
        "avg_processing_time_ms": metrics_summary.get("avg_processing_time_ms", 0.0),
        "evaluation_count": metrics_summary.get("total_evaluations", 0),
        "precision": business_metrics.get("precision", 0.0),
        "recall": business_metrics.get("recall", 0.0),
    }

    return features


def push_metrics_to_gateway(config: Dict[str, Any], metrics_registry: Dict):
    """
    Envia métricas para Prometheus Pushgateway.

    Args:
        config: Configuração
        metrics_registry: Registry de métricas
    """
    pushgateway_url = config.get("pushgateway_url")

    if not pushgateway_url:
        return

    try:
        from prometheus_client import push_to_gateway
        from prometheus_client import REGISTRY

        push_to_gateway(
            pushgateway_url, job="business_metrics_collector", registry=REGISTRY
        )

        print(f"✅ Metrics pushed to gateway: {pushgateway_url}")

    except Exception as e:
        print(f"⚠️  Failed to push metrics to gateway: {e}", file=sys.stderr)


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description="Executa coleta de business metrics do Neural Hive"
    )
    parser.add_argument(
        "--window-hours",
        type=int,
        help="Janela de tempo para análise (em horas, default: 24)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Simula execução sem atualizar métricas"
    )
    parser.add_argument(
        "--specialist-type",
        type=str,
        help="Executar apenas para especialista específico",
    )
    parser.add_argument(
        "--enable-anomaly-detection",
        action="store_true",
        default=True,
        help="Habilitar detecção de anomalias (default: True)",
    )
    parser.add_argument("--verbose", action="store_true", help="Logging detalhado")
    parser.add_argument(
        "--pushgateway-url", type=str, help="URL do Prometheus Pushgateway (opcional)"
    )

    args = parser.parse_args()

    # Configurar logging
    if args.verbose:
        import structlog
        import logging

        logging.basicConfig(level=logging.DEBUG)
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG)
        )

    print("🚀 Iniciando coleta de business metrics...")
    print(f"⏰ Timestamp: {datetime.now().isoformat()}")

    # Carregar configuração
    config = load_config()

    # Override com argumentos CLI
    if args.window_hours:
        config["business_metrics_window_hours"] = args.window_hours

    if args.pushgateway_url:
        config["pushgateway_url"] = args.pushgateway_url

    if args.dry_run:
        print("\n🔍 MODO DRY-RUN: Simulando execução sem atualizar métricas\n")

    # Inicializar componentes
    print("\n📊 Inicializando componentes...")
    metrics_registry = initialize_metrics_registry()
    collector = initialize_business_metrics_collector(config, metrics_registry)
    anomaly_detector = (
        initialize_anomaly_detector(config) if args.enable_anomaly_detection else None
    )

    # Executar coleta
    print(
        f"\n🔄 Coletando métricas (janela: {config['business_metrics_window_hours']}h)..."
    )

    start_time = time.time()

    try:
        if args.dry_run:
            print("⚠️  Dry-run mode - skipping actual collection")
            result = {
                "status": "dry_run",
                "window_hours": config["business_metrics_window_hours"],
            }
        else:
            result = collector.collect_business_metrics(
                window_hours=config["business_metrics_window_hours"]
            )

        duration = time.time() - start_time

        # Log resultado
        print(f"\n✅ Coleta concluída em {duration:.2f}s")
        print(f"📊 Status: {result.get('status')}")

        if result.get("status") == "success":
            print(f"  📝 Opiniões processadas: {result.get('opinions_processed', 0)}")
            print(f"  🎯 Decisões processadas: {result.get('decisions_processed', 0)}")
            print(f"  🔗 Correlações criadas: {result.get('correlations_created', 0)}")
            print(
                f"  👥 Especialistas atualizados: {result.get('specialists_updated', 0)}"
            )

        # Detecção de anomalias
        if anomaly_detector and not args.dry_run and result.get("status") == "success":
            print("\n🔍 Detectando anomalias...")

            for specialist_type, metrics in metrics_registry.items():
                if args.specialist_type and specialist_type != args.specialist_type:
                    continue

                # Carregar modelo para o especialista
                if not anomaly_detector.is_trained:
                    print(f"⏳ Carregando modelo de anomalia para {specialist_type}...")
                    model_loaded = anomaly_detector.load_model_for_specialist(
                        specialist_type
                    )
                    if not model_loaded:
                        print(
                            f"⚠️  Modelo não encontrado para {specialist_type}, pulando detecção de anomalias"
                        )
                        continue

                # Extrair métricas atuais
                summary = metrics.get_summary()
                business_metrics = summary.get("business_metrics", {})

                if not business_metrics:
                    continue

                # Construir features completas para detecção
                anomaly_features = build_anomaly_features(summary)

                # Detectar anomalias
                detection_result = anomaly_detector.detect_anomalies(anomaly_features)

                if detection_result.get("is_anomaly"):
                    severity = detection_result["severity"]
                    anomaly_score = detection_result["anomaly_score"]
                    anomalous_features = detection_result.get("anomalous_features", [])

                    print(f"\n⚠️  ANOMALIA DETECTADA - {specialist_type}")
                    print(f"  🎯 Severidade: {severity}")
                    print(f"  📉 Anomaly Score: {anomaly_score:.3f}")
                    print(f"  🔍 Features anômalas: {', '.join(anomalous_features)}")

                    # Incrementar métrica de anomalia
                    metrics.increment_anomaly_detected(severity=severity)
                else:
                    print(f"✅ Nenhuma anomalia detectada - {specialist_type}")

        # Push para Pushgateway
        if not args.dry_run:
            push_metrics_to_gateway(config, metrics_registry)

        print(f"\n✅ Business metrics collection completed successfully!")

        return 0

    except Exception as e:
        print(f"\n❌ ERRO durante coleta: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1

    finally:
        # Fechar conexões
        if hasattr(collector, "close"):
            collector.close()


if __name__ == "__main__":
    sys.exit(main())
