#!/usr/bin/env python3
"""
Gera background dataset para SHAP a partir de planos cognitivos históricos.

Uso:
    python generate_shap_background_dataset.py \
        --mongodb-uri mongodb://localhost:27017 \
        --database neural_hive \
        --collection cognitive_plans \
        --output-path /data/shap_background.parquet \
        --num-samples 1000 \
        --specialist-type technical
"""

import argparse
import sys
from pathlib import Path
import pandas as pd
from pymongo import MongoClient
import structlog
from typing import List, Dict, Any

# Adicionar path da biblioteca
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'libraries' / 'python'))

from neural_hive_specialists.feature_extraction.feature_extractor import FeatureExtractor

logger = structlog.get_logger()


def fetch_historical_plans(
    mongodb_uri: str,
    database: str,
    collection: str,
    num_samples: int,
    specialist_type: str = None
) -> List[Dict[str, Any]]:
    """
    Busca planos cognitivos históricos do MongoDB.

    Args:
        mongodb_uri: URI do MongoDB
        database: Nome do database
        collection: Nome da collection
        num_samples: Número de amostras a buscar
        specialist_type: Filtrar por tipo de especialista (opcional)

    Returns:
        Lista de planos cognitivos
    """
    logger.info(
        "Fetching historical plans",
        database=database,
        collection=collection,
        num_samples=num_samples
    )

    client = MongoClient(mongodb_uri)
    db = client[database]
    coll = db[collection]

    # Query
    query = {}
    if specialist_type:
        query['specialist_type'] = specialist_type

    # Buscar amostras aleatórias
    pipeline = [
        {'$match': query},
        {'$sample': {'size': num_samples}}
    ]

    plans = list(coll.aggregate(pipeline))

    logger.info("Plans fetched", count=len(plans))

    return plans


def extract_features_from_plans(
    plans: List[Dict[str, Any]],
    ontology_path: str = None
) -> pd.DataFrame:
    """
    Extrai features estruturadas de planos cognitivos.

    Args:
        plans: Lista de planos cognitivos
        ontology_path: Caminho para ontologias (opcional)

    Returns:
        DataFrame com features extraídas
    """
    logger.info("Extracting features from plans", num_plans=len(plans))

    # Inicializar feature extractor
    config = {
        'ontology_path': ontology_path,
        'embeddings_model': 'paraphrase-multilingual-MiniLM-L12-v2'
    }
    extractor = FeatureExtractor(config)

    # Extrair features de cada plano
    features_list = []
    for i, plan in enumerate(plans):
        try:
            features_result = extractor.extract_features(plan)
            aggregated_features = features_result['aggregated_features']
            features_list.append(aggregated_features)

            if (i + 1) % 100 == 0:
                logger.info(f"Processed {i + 1}/{len(plans)} plans")

        except Exception as e:
            logger.warning(
                "Failed to extract features from plan",
                plan_id=plan.get('plan_id'),
                error=str(e)
            )

    # Converter para DataFrame
    df = pd.DataFrame(features_list)

    logger.info(
        "Features extracted",
        num_samples=len(df),
        num_features=len(df.columns)
    )

    return df


def validate_background_dataset(df: pd.DataFrame) -> bool:
    """
    Valida background dataset.

    Args:
        df: DataFrame com features

    Returns:
        True se válido, False caso contrário
    """
    logger.info("Validating background dataset")

    # Verificações
    checks = []

    # 1. Número mínimo de amostras
    min_samples = 50
    if len(df) < min_samples:
        logger.error(f"Insufficient samples: {len(df)} < {min_samples}")
        checks.append(False)
    else:
        checks.append(True)

    # 2. Sem valores NaN
    nan_count = df.isna().sum().sum()
    if nan_count > 0:
        logger.warning(f"Dataset contains {nan_count} NaN values")
        # Preencher com 0
        df.fillna(0, inplace=True)
    checks.append(True)

    # 3. Variância mínima em features
    low_variance_features = []
    for col in df.columns:
        if df[col].var() < 0.001:
            low_variance_features.append(col)

    if low_variance_features:
        logger.warning(
            "Low variance features detected",
            features=low_variance_features
        )
    checks.append(True)

    # 4. Estatísticas descritivas
    logger.info("Dataset statistics:")
    logger.info(df.describe().to_string())

    is_valid = all(checks)
    logger.info("Validation complete", is_valid=is_valid)

    return is_valid


def save_background_dataset(df: pd.DataFrame, output_path: str):
    """
    Salva background dataset em formato Parquet.

    Args:
        df: DataFrame com features
        output_path: Caminho de saída
    """
    logger.info("Saving background dataset", output_path=output_path)

    # Criar diretório se não existir
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Salvar em Parquet (compressão eficiente)
    df.to_parquet(output_path, compression='snappy', index=False)

    # Estatísticas do arquivo
    file_size_mb = output_file.stat().st_size / (1024 * 1024)
    logger.info(
        "Background dataset saved",
        path=output_path,
        size_mb=round(file_size_mb, 2)
    )


def main():
    parser = argparse.ArgumentParser(
        description='Generate SHAP background dataset from historical cognitive plans'
    )
    parser.add_argument(
        '--mongodb-uri',
        required=True,
        help='MongoDB connection URI'
    )
    parser.add_argument(
        '--database',
        default='neural_hive',
        help='MongoDB database name'
    )
    parser.add_argument(
        '--collection',
        default='cognitive_plans',
        help='MongoDB collection name'
    )
    parser.add_argument(
        '--output-path',
        required=True,
        help='Output path for background dataset (Parquet)'
    )
    parser.add_argument(
        '--num-samples',
        type=int,
        default=1000,
        help='Number of samples to fetch'
    )
    parser.add_argument(
        '--specialist-type',
        help='Filter by specialist type (optional)'
    )
    parser.add_argument(
        '--ontology-path',
        help='Path to ontology directory (optional)'
    )

    args = parser.parse_args()

    # Configurar logging
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer()
        ]
    )

    try:
        # 1. Buscar planos históricos
        plans = fetch_historical_plans(
            args.mongodb_uri,
            args.database,
            args.collection,
            args.num_samples,
            args.specialist_type
        )

        if not plans:
            logger.error("No plans found")
            sys.exit(1)

        # 2. Extrair features
        df = extract_features_from_plans(plans, args.ontology_path)

        # 3. Validar dataset
        if not validate_background_dataset(df):
            logger.error("Background dataset validation failed")
            sys.exit(1)

        # 4. Salvar
        save_background_dataset(df, args.output_path)

        logger.info("Background dataset generation completed successfully")

    except Exception as e:
        logger.error("Background dataset generation failed", error=str(e), exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
