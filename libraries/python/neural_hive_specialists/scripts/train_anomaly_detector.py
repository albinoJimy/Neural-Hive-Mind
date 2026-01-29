#!/usr/bin/env python3
"""
Script para treinar modelo de anomaly detection do Neural Hive.

Este script busca métricas históricas e treina um modelo Isolation Forest
para detectar anomalias em métricas de especialistas.

Uso:
    python train_anomaly_detector.py --window-days 30
    python train_anomaly_detector.py --specialist-type technical
    python train_anomaly_detector.py --contamination 0.05 --validate
"""
import argparse
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional


def load_config() -> Dict[str, Any]:
    """
    Carrega configuração de variáveis de ambiente.

    Returns:
        Dict com configuração
    """
    try:
        config = {
            # ClickHouse
            "clickhouse_uri": os.getenv("CLICKHOUSE_URI"),
            "clickhouse_database": os.getenv("CLICKHOUSE_DATABASE", "neural_hive"),
            # Anomaly Detection
            "anomaly_contamination": float(os.getenv("ANOMALY_CONTAMINATION", "0.1")),
            "anomaly_n_estimators": int(os.getenv("ANOMALY_N_ESTIMATORS", "100")),
            "anomaly_model_path": os.getenv(
                "ANOMALY_MODEL_PATH",
                "/data/models/anomaly_detector_{specialist_type}.pkl",
            ),
            "anomaly_training_window_days": int(
                os.getenv("ANOMALY_TRAINING_WINDOW_DAYS", "30")
            ),
        }

        return config

    except Exception as e:
        print(f"❌ ERRO ao carregar configuração: {e}", file=sys.stderr)
        sys.exit(1)


def fetch_historical_metrics_from_clickhouse(
    clickhouse_uri: str,
    clickhouse_database: str,
    window_days: int,
    specialist_type: Optional[str] = None,
) -> List[Dict[str, float]]:
    """
    Busca métricas históricas do ClickHouse.

    Args:
        clickhouse_uri: URI do ClickHouse
        clickhouse_database: Database
        window_days: Janela de dados (dias)
        specialist_type: Filtrar por especialista (opcional)

    Returns:
        Lista de dicts com métricas
    """
    try:
        from clickhouse_driver import Client

        client = Client.from_url(clickhouse_uri)

        cutoff_date = datetime.now() - timedelta(days=window_days)

        query = """
        SELECT
            specialist_type,
            consensus_agreement_rate,
            false_positive_rate,
            false_negative_rate,
            avg_confidence_score,
            avg_risk_score,
            avg_processing_time_ms,
            evaluation_count,
            precision,
            recall,
            timestamp
        FROM {database}.business_metrics_history
        WHERE timestamp >= %(cutoff_date)s
        """

        if specialist_type:
            query += " AND specialist_type = %(specialist_type)s"

        query += " ORDER BY timestamp ASC"

        params = {"cutoff_date": cutoff_date, "specialist_type": specialist_type}

        results = client.execute(query.format(database=clickhouse_database), params)

        metrics_list = []
        for row in results:
            metrics = {
                "specialist_type": row[0],
                "consensus_agreement_rate": row[1],
                "false_positive_rate": row[2],
                "false_negative_rate": row[3],
                "avg_confidence_score": row[4],
                "avg_risk_score": row[5],
                "avg_processing_time_ms": row[6],
                "evaluation_count": row[7],
                "precision": row[8],
                "recall": row[9],
            }
            metrics_list.append(metrics)

        print(f"✅ Fetched {len(metrics_list)} historical samples from ClickHouse")

        return metrics_list

    except ImportError:
        print(
            "❌ clickhouse-driver não instalado. Instale com: pip install clickhouse-driver",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(f"❌ ERRO ao buscar métricas do ClickHouse: {e}", file=sys.stderr)
        sys.exit(1)


def generate_synthetic_metrics(num_samples: int = 500) -> List[Dict[str, float]]:
    """
    Gera métricas sintéticas para demonstração.

    Args:
        num_samples: Número de amostras

    Returns:
        Lista de métricas sintéticas
    """
    import numpy as np

    print(f"⚠️  Gerando {num_samples} métricas sintéticas (ClickHouse não disponível)")

    metrics_list = []

    for _ in range(num_samples):
        # Métricas "normais"
        metrics = {
            "consensus_agreement_rate": np.random.normal(0.85, 0.05),
            "false_positive_rate": np.random.normal(0.10, 0.03),
            "false_negative_rate": np.random.normal(0.08, 0.03),
            "avg_confidence_score": np.random.normal(0.82, 0.08),
            "avg_risk_score": np.random.normal(0.15, 0.05),
            "avg_processing_time_ms": np.random.normal(120, 30),
            "evaluation_count": np.random.randint(50, 200),
            "precision": np.random.normal(0.88, 0.05),
            "recall": np.random.normal(0.86, 0.05),
        }

        # Clampar valores
        for key in metrics:
            if key in [
                "consensus_agreement_rate",
                "false_positive_rate",
                "false_negative_rate",
                "avg_confidence_score",
                "avg_risk_score",
                "precision",
                "recall",
            ]:
                metrics[key] = max(0.0, min(1.0, metrics[key]))
            elif key == "avg_processing_time_ms":
                metrics[key] = max(0, metrics[key])
            elif key == "evaluation_count":
                metrics[key] = max(1, metrics[key])

        metrics_list.append(metrics)

    return metrics_list


def train_anomaly_detector(
    config: Dict[str, Any],
    metrics_history: List[Dict[str, float]],
    specialist_type: str,
    validate: bool = False,
) -> bool:
    """
    Treina modelo de anomaly detection.

    Args:
        config: Configuração
        metrics_history: Histórico de métricas
        specialist_type: Tipo do especialista
        validate: Se deve validar após treinamento

    Returns:
        True se treinamento bem-sucedido
    """
    from neural_hive_specialists.observability import AnomalyDetector

    print(f"\n🤖 Treinando modelo para: {specialist_type}")
    print(f"📊 Amostras: {len(metrics_history)}")
    print(f"⚙️  Contamination: {config['anomaly_contamination']}")
    print(f"🌳 N Estimators: {config['anomaly_n_estimators']}")

    detector = AnomalyDetector(config=config)

    success = detector.train_on_historical_data(
        metrics_history=metrics_history, specialist_type=specialist_type
    )

    if not success:
        print("❌ Treinamento falhou")
        return False

    print("✅ Treinamento concluído com sucesso")

    # Validação (opcional)
    if validate and len(metrics_history) > 100:
        print("\n🔍 Validando modelo...")

        # Usar últimas 20% de amostras para validação
        val_size = len(metrics_history) // 5
        val_samples = metrics_history[-val_size:]

        anomaly_count = 0

        for sample in val_samples:
            result = detector.detect_anomalies(sample)
            if result.get("is_anomaly"):
                anomaly_count += 1

        anomaly_percentage = (anomaly_count / val_size) * 100

        print(
            f"📊 Validação: {anomaly_count}/{val_size} amostras detectadas como anomalias ({anomaly_percentage:.1f}%)"
        )

        if abs(anomaly_percentage - (config["anomaly_contamination"] * 100)) > 10:
            print(
                f"⚠️  Taxa de anomalias diferente do contamination configurado ({config['anomaly_contamination'] * 100}%)"
            )

    return True


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description="Treina modelo de anomaly detection do Neural Hive"
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=30,
        help="Janela de dados históricos (em dias, default: 30)",
    )
    parser.add_argument(
        "--specialist-type",
        type=str,
        help="Treinar para especialista específico (default: todos)",
    )
    parser.add_argument(
        "--contamination",
        type=float,
        help="Contamination parameter (0.0-0.5, default: 0.1)",
    )
    parser.add_argument(
        "--n-estimators", type=int, help="Número de árvores (default: 100)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="/data/models",
        help="Diretório de saída para modelos",
    )
    parser.add_argument("--clickhouse-uri", type=str, help="URI do ClickHouse")
    parser.add_argument(
        "--validate", action="store_true", help="Executar validação após treinamento"
    )
    parser.add_argument(
        "--use-synthetic",
        action="store_true",
        help="Usar métricas sintéticas (para demonstração)",
    )

    args = parser.parse_args()

    print("🚀 Iniciando treinamento de anomaly detector...")
    print(f"⏰ Timestamp: {datetime.now().isoformat()}")

    # Carregar configuração
    config = load_config()

    # Override com argumentos CLI
    if args.contamination:
        config["anomaly_contamination"] = args.contamination

    if args.n_estimators:
        config["anomaly_n_estimators"] = args.n_estimators

    if args.clickhouse_uri:
        config["clickhouse_uri"] = args.clickhouse_uri

    if args.output_dir:
        config[
            "anomaly_model_path"
        ] = f"{args.output_dir}/anomaly_detector_{{specialist_type}}.pkl"

    # Buscar métricas históricas
    if args.use_synthetic or not config.get("clickhouse_uri"):
        metrics_history = generate_synthetic_metrics(num_samples=500)
    else:
        metrics_history = fetch_historical_metrics_from_clickhouse(
            clickhouse_uri=config["clickhouse_uri"],
            clickhouse_database=config["clickhouse_database"],
            window_days=args.window_days,
            specialist_type=args.specialist_type,
        )

    if not metrics_history:
        print("❌ Nenhuma métrica histórica disponível", file=sys.stderr)
        sys.exit(1)

    # Especialistas a treinar
    if args.specialist_type:
        specialist_types = [args.specialist_type]
    else:
        specialist_types = [
            "technical",
            "business",
            "behavior",
            "evolution",
            "architecture",
        ]

    # Treinar modelo para cada especialista
    success_count = 0

    for specialist_type in specialist_types:
        # Filtrar métricas do especialista (se usando ClickHouse)
        if not args.use_synthetic and "specialist_type" in metrics_history[0]:
            specialist_metrics = [
                m
                for m in metrics_history
                if m.get("specialist_type") == specialist_type
            ]
        else:
            specialist_metrics = metrics_history

        if not specialist_metrics:
            print(f"⚠️  Sem métricas para {specialist_type}, pulando...")
            continue

        success = train_anomaly_detector(
            config=config,
            metrics_history=specialist_metrics,
            specialist_type=specialist_type,
            validate=args.validate,
        )

        if success:
            success_count += 1

    print(
        f"\n✅ Treinamento concluído: {success_count}/{len(specialist_types)} especialistas"
    )

    if success_count == len(specialist_types):
        print("\n🎉 Todos os modelos treinados com sucesso!")
        return 0
    elif success_count > 0:
        print(f"\n⚠️  Alguns modelos falharam: {len(specialist_types) - success_count}")
        return 1
    else:
        print("\n❌ Nenhum modelo foi treinado com sucesso")
        return 1


if __name__ == "__main__":
    sys.exit(main())
