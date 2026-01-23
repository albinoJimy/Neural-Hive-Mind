#!/usr/bin/env python3
"""
Pipeline MLflow para re-treinamento de modelos de especialistas com feedback humano.

Este script carrega dataset base, enriquece com feedback, treina modelo,
avalia performance e promove para produção se melhor que baseline.
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta
from importlib import util
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import structlog
import pandas as pd
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    precision_score, recall_score, f1_score, accuracy_score, confusion_matrix,
    brier_score_loss, log_loss
)
import mlflow
import mlflow.sklearn
import mlflow.pyfunc
from mlflow.models.signature import infer_signature
from pymongo import MongoClient
import joblib
import tempfile
from motor.motor_asyncio import AsyncIOMotorClient

# Importar wrapper probabilístico
from probabilistic_wrapper import ProbabilisticModelWrapper

# Importar ModelAuditLogger para auditoria de ciclo de vida
try:
    sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..', '..', 'services', 'orchestrator-dynamic', 'src')))
    from ml.model_audit_logger import ModelAuditLogger, AuditEventContext
    _MODEL_AUDIT_LOGGER_AVAILABLE = True
except ImportError:
    _MODEL_AUDIT_LOGGER_AVAILABLE = False
    ModelAuditLogger = None
    AuditEventContext = None

# Importar RealDataCollector para dados reais
try:
    from real_data_collector import RealDataCollector, InsufficientDataError, FeatureExtractionError
    _REAL_DATA_COLLECTOR_AVAILABLE = True
except ImportError:
    _REAL_DATA_COLLECTOR_AVAILABLE = False
    InsufficientDataError = Exception
    FeatureExtractionError = Exception

# Importar DataQualityValidator para validação avançada
try:
    from data_quality_validator import DataQualityValidator
    _DATA_QUALITY_VALIDATOR_AVAILABLE = True
except ImportError:
    _DATA_QUALITY_VALIDATOR_AVAILABLE = False

# Importar PreRetrainingValidator para validação de pré-requisitos
try:
    from pre_retraining_validator import PreRetrainingValidator, ValidationFailedError
    _PRE_RETRAINING_VALIDATOR_AVAILABLE = True
except ImportError:
    _PRE_RETRAINING_VALIDATOR_AVAILABLE = False
    ValidationFailedError = Exception

# Importar schema de features centralizado
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..', '..', 'libraries', 'python')))
from feature_store.feature_definitions import get_feature_names, get_feature_schema

# Importar FeatureExtractor para extração de features de feedback
try:
    from neural_hive_specialists.feature_extraction.feature_extractor import FeatureExtractor
    _FEATURE_EXTRACTOR_AVAILABLE = True
except ImportError:
    _FEATURE_EXTRACTOR_AVAILABLE = False

logger = structlog.get_logger()
REPO_ROOT = Path(__file__).resolve().parents[2]


class AuditLoggerConfig:
    """Configuração mínima para ModelAuditLogger no pipeline de treinamento."""

    def __init__(self, environment: str = 'development'):
        self.ml_audit_log_collection = 'model_audit_log'
        self.ml_audit_retention_days = 365
        self.ml_audit_enabled = True
        self.environment = environment


def create_audit_logger() -> Optional[Any]:
    """
    Cria instância de ModelAuditLogger para auditoria do pipeline de treinamento.

    Returns:
        ModelAuditLogger ou None se não disponível
    """
    if not _MODEL_AUDIT_LOGGER_AVAILABLE:
        logger.warning('model_audit_logger_not_available')
        return None

    try:
        mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
        mongodb_database = os.getenv('MONGODB_DATABASE', 'neural_hive')
        environment = os.getenv('ENVIRONMENT', 'development')

        # Criar cliente MongoDB assíncrono
        mongodb_client = AsyncIOMotorClient(mongodb_uri)
        mongodb_client.db = mongodb_client[mongodb_database]

        config = AuditLoggerConfig(environment=environment)
        audit_logger = ModelAuditLogger(
            mongodb_client=mongodb_client,
            config=config,
            metrics=None  # Sem métricas Prometheus no pipeline de treinamento
        )

        logger.info('audit_logger_created_for_training_pipeline')
        return audit_logger

    except Exception as e:
        logger.warning('audit_logger_creation_failed', error=str(e))
        return None


async def log_audit_event(audit_logger, method_name: str, **kwargs) -> Optional[str]:
    """
    Helper assíncrono para logging de evento de auditoria.

    Args:
        audit_logger: Instância de ModelAuditLogger
        method_name: Nome do método a chamar (ex: 'log_training_started')
        **kwargs: Argumentos para o método

    Returns:
        audit_id ou None
    """
    if audit_logger is None:
        return None

    try:
        method = getattr(audit_logger, method_name)
        return await method(**kwargs)
    except Exception as e:
        logger.warning(
            'audit_event_logging_failed',
            method=method_name,
            error=str(e)
        )
        return None


def _load_service_config_class(module_name: str, file_path: Path, class_name: str):
    """Carrega classe de configuração de service sem poluir sys.path global."""
    spec = util.spec_from_file_location(module_name, file_path)
    module = util.module_from_spec(spec)
    assert spec and spec.loader  # para mypy/linters
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return getattr(module, class_name)


def _resolve_setting_value(value: Any) -> Any:
    """Extrai valor bruto de FieldInfo ou retorna valor diretamente."""
    if hasattr(value, "default"):
        return getattr(value, "default")
    return value


TechnicalSpecialistConfig = _load_service_config_class(
    "specialist_technical_config",
    REPO_ROOT / "services" / "specialist-technical" / "src" / "config.py",
    "TechnicalSpecialistConfig"
)
EvolutionSpecialistConfig = _load_service_config_class(
    "specialist_evolution_config",
    REPO_ROOT / "services" / "specialist-evolution" / "src" / "config.py",
    "EvolutionSpecialistConfig"
)

SPECIALIST_REGISTRY_MAP: Dict[str, Dict[str, str]] = {
    "technical": {
        "model_name": _resolve_setting_value(TechnicalSpecialistConfig.mlflow_model_name),
        "experiment_name": _resolve_setting_value(TechnicalSpecialistConfig.mlflow_experiment_name),
        "stage": _resolve_setting_value(getattr(TechnicalSpecialistConfig, "mlflow_model_stage", "Production"))
    },
    "evolution": {
        "model_name": _resolve_setting_value(EvolutionSpecialistConfig.mlflow_model_name),
        "experiment_name": _resolve_setting_value(EvolutionSpecialistConfig.mlflow_experiment_name),
        "stage": _resolve_setting_value(getattr(EvolutionSpecialistConfig, "mlflow_model_stage", "Production"))
    }
}


def validate_registry_alignment(specialist_type: str) -> Dict[str, str]:
    """
    Garante alinhamento entre nomes de modelo/experimento do pipeline e dos services.
    """
    if specialist_type not in SPECIALIST_REGISTRY_MAP:
        raise ValueError(
            f"Unsupported specialist_type '{specialist_type}'. "
            f"Allowed values: {list(SPECIALIST_REGISTRY_MAP.keys())}"
        )

    entry = SPECIALIST_REGISTRY_MAP[specialist_type]
    derived_model_name = f"{specialist_type}-evaluator"
    derived_experiment_name = f"{specialist_type}-specialist"

    if entry["model_name"] != derived_model_name or entry["experiment_name"] != derived_experiment_name:
        raise ValueError(
            f"Config drift detected for '{specialist_type}': "
            f"model_name={entry['model_name']} (expected {derived_model_name}), "
            f"experiment_name={entry['experiment_name']} (expected {derived_experiment_name}). "
            f"Abortando treinamento para evitar registro inconsistente."
        )

    return entry


def parse_args():
    """Parse argumentos CLI."""
    parser = argparse.ArgumentParser(
        description="Treinar modelo de especialista com feedback humano"
    )
    parser.add_argument(
        '--specialist-type',
        type=str,
        required=True,
        help="Tipo do especialista"
    )
    parser.add_argument(
        '--feedback-count',
        type=int,
        default=0,
        help="Quantidade de feedbacks disponíveis (informativo)"
    )
    parser.add_argument(
        '--window-days',
        type=int,
        default=30,
        help="Janela de feedbacks a incluir"
    )
    parser.add_argument(
        '--min-feedback-quality',
        type=float,
        default=0.5,
        help="Rating mínimo para incluir feedback"
    )
    parser.add_argument(
        '--model-type',
        type=str,
        default='random_forest',
        choices=['random_forest', 'gradient_boosting', 'neural_network'],
        help="Tipo de modelo a treinar"
    )
    parser.add_argument(
        '--hyperparameter-tuning',
        type=str,
        default='false',
        choices=['true', 'false'],
        help="Habilitar tuning de hiperparâmetros"
    )
    parser.add_argument(
        '--promote-if-better',
        type=str,
        default='true',
        choices=['true', 'false'],
        help="Promover automaticamente se melhor que baseline"
    )
    parser.add_argument(
        '--allow-synthetic-fallback',
        type=str,
        default='auto',
        choices=['true', 'false', 'auto'],
        help="Permitir fallback para dados sintéticos. 'auto' = true em dev, false em prod"
    )
    parser.add_argument(
        '--real-data-days',
        type=int,
        default=90,
        help="Janela de tempo em dias para coletar dados reais do MongoDB"
    )
    parser.add_argument(
        '--min-real-samples',
        type=int,
        default=1000,
        help="Mínimo de amostras reais necessárias para treinamento"
    )
    parser.add_argument(
        '--skip-validation',
        type=str,
        default='false',
        choices=['true', 'false'],
        help="Pular validação de pré-requisitos (USO EMERGENCIAL APENAS)"
    )

    return parser.parse_args()


def load_base_dataset(specialist_type: str, dataset_path_template: str) -> Tuple[pd.DataFrame, str]:
    """
    Carrega dataset base de treinamento.

    Args:
        specialist_type: Tipo do especialista
        dataset_path_template: Template do path (com {specialist_type})

    Returns:
        Tupla (DataFrame com features e labels, data_source)
        - data_source: 'synthetic' se usou dados sintéticos, ou path do arquivo real
    """
    dataset_path = dataset_path_template.format(specialist_type=specialist_type)

    logger.info(
        "Loading base dataset",
        specialist_type=specialist_type,
        path=dataset_path
    )

    # Verificar se arquivo existe
    if not os.path.exists(dataset_path):
        # Verificar se fallback para sintético está habilitado
        allow_synthetic = os.getenv('ALLOW_SYNTHETIC_FALLBACK', 'true').lower() == 'true'
        environment = os.getenv('ENVIRONMENT', 'development')

        if not allow_synthetic and environment == 'production':
            raise FileNotFoundError(
                f"Dataset não encontrado em {dataset_path} e ALLOW_SYNTHETIC_FALLBACK=false em production. "
                f"Configure o dataset real ou defina ALLOW_SYNTHETIC_FALLBACK=true."
            )

        logger.warning(
            "Base dataset not found - using synthetic data",
            path=dataset_path,
            environment=environment,
            allow_synthetic=allow_synthetic
        )
        # Criar dataset sintético para desenvolvimento
        df = create_synthetic_dataset(n_samples=1000)
        return df, 'synthetic'

    # Carregar Parquet
    df = pd.read_parquet(dataset_path)

    # Validar schema de features
    expected_features = get_feature_names()
    actual_features = [col for col in df.columns if col != 'label']

    missing_features = set(expected_features) - set(actual_features)
    extra_features = set(actual_features) - set(expected_features)

    if missing_features:
        logger.warning(
            "dataset_missing_features",
            missing=list(missing_features),
            path=dataset_path
        )
        # Adicionar features faltantes com valor padrão
        for feature in missing_features:
            df[feature] = 0.0

    if extra_features:
        logger.warning(
            "dataset_extra_features",
            extra=list(extra_features),
            path=dataset_path
        )
        # Remover features extras
        df = df.drop(columns=list(extra_features))

    # Reordenar colunas para consistência
    ordered_columns = expected_features + ['label']
    df = df[ordered_columns]

    logger.info(
        "dataset_schema_validated",
        num_features=len(expected_features),
        num_samples=len(df)
    )

    logger.info(
        "Base dataset loaded",
        size=len(df),
        columns=list(df.columns),
        data_source=dataset_path
    )

    return df, dataset_path


def create_synthetic_dataset(n_samples: int = 1000) -> pd.DataFrame:
    """
    Cria dataset sintético COMPATÍVEL com FeatureExtractor para desenvolvimento/teste.
    Usa schema de feature_definitions.py para garantir alinhamento com inferência.

    Args:
        n_samples: Número de amostras

    Returns:
        DataFrame com features sintéticas compatíveis com schema centralizado
    """
    logger.warning(
        "creating_synthetic_dataset",
        n_samples=n_samples,
        reason="Real dataset not found, using synthetic fallback"
    )

    np.random.seed(42)

    # Obter schema de features esperado (mesmo usado em inferência)
    feature_names = get_feature_names()

    # Criar features sintéticas com nomes corretos do schema
    data = {}
    for feature_name in feature_names:
        # Gerar valores sintéticos baseados no tipo de feature
        if 'score' in feature_name or 'weight' in feature_name:
            # Usar distribuição uniforme para melhor balanceamento de labels
            data[feature_name] = np.random.uniform(0, 1, n_samples)
        elif 'num_' in feature_name or 'count' in feature_name:
            data[feature_name] = np.random.randint(0, 20, n_samples).astype(float)
        elif 'duration' in feature_name:
            data[feature_name] = np.random.exponential(5000, n_samples)
        elif 'avg_' in feature_name or 'mean_' in feature_name:
            data[feature_name] = np.random.normal(0.5, 0.2, n_samples)
        elif 'std_' in feature_name:
            data[feature_name] = np.abs(np.random.uniform(0, 0.5, n_samples))
        elif 'density' in feature_name:
            data[feature_name] = np.random.uniform(0, 1, n_samples)
        elif 'max_' in feature_name:
            data[feature_name] = np.random.randint(1, 10, n_samples).astype(float)
        else:
            data[feature_name] = np.abs(np.random.randn(n_samples))

    df = pd.DataFrame(data)

    # Label sintético com proporção balanceada para garantir métricas significativas
    # Usar proporção ~55% approve, ~45% reject para dados balanceados
    # A heurística deve produzir aproximadamente essa distribuição
    has_risk_score = 'risk_score' in df.columns
    has_complexity_score = 'complexity_score' in df.columns

    if has_risk_score and has_complexity_score:
        # Heurística ajustada: approve=1 se risk_score < 0.55 E complexity_score < 0.65
        # Com distribuição uniforme [0,1], isso produz ~55% * 65% = ~36% positivos
        # Para balancear melhor: usar risk_score < 0.6 OU complexity_score < 0.5
        # Isso produz: P(risk<0.6) + P(comp<0.5) - P(ambos) = 0.6 + 0.5 - 0.3 = 0.8
        # Ajustar: approve se (risk < 0.5 AND complexity < 0.7) OR (risk < 0.3)
        condition1 = (df['risk_score'] < 0.5) & (df['complexity_score'] < 0.7)  # ~35%
        condition2 = df['risk_score'] < 0.25  # ~25%
        df['label'] = (condition1 | condition2).astype(int)

        label_dist = df['label'].value_counts().to_dict()
        logger.info(
            "synthetic_label_heuristic",
            method="balanced_risk_complexity_threshold",
            label_distribution=label_dist
        )

        # Se distribuição ainda muito desbalanceada, usar proporção controlada
        positive_ratio = label_dist.get(1, 0) / n_samples
        if positive_ratio < 0.35 or positive_ratio > 0.65:
            logger.warning(
                "rebalancing_synthetic_labels",
                original_positive_ratio=positive_ratio,
                target_positive_ratio=0.5
            )
            # Rebalancear para ~50/50
            df['label'] = np.random.choice([0, 1], size=n_samples, p=[0.5, 0.5])
    else:
        # Fallback: label aleatório com proporção balanceada (50% approve, 50% reject)
        logger.warning(
            "synthetic_label_fallback",
            reason="risk_score and/or complexity_score not in schema",
            has_risk_score=has_risk_score,
            has_complexity_score=has_complexity_score,
            fallback_method="random_balanced_proportion"
        )
        df['label'] = np.random.choice([0, 1], size=n_samples, p=[0.5, 0.5])

    # Adicionar created_at sintético para suportar split temporal
    # Distribuir uniformemente nos últimos 30 dias
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=30)
    random_timestamps = [
        start_date + timedelta(seconds=np.random.randint(0, 30 * 24 * 3600))
        for _ in range(n_samples)
    ]
    df['created_at'] = sorted(random_timestamps)

    logger.info(
        "synthetic_dataset_created",
        n_samples=n_samples,
        num_features=len(feature_names),
        label_distribution=df['label'].value_counts().to_dict(),
        created_at_range=f"{df['created_at'].min()} to {df['created_at'].max()}"
    )

    return df


def temporal_split(
    df: pd.DataFrame,
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    timestamp_col: str = 'created_at'
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    Realiza split temporal do dataset ordenado por created_at.

    Os dados mais antigos vão para treino, intermediários para validação,
    e mais recentes para teste. Isso evita data leakage temporal.

    Args:
        df: DataFrame com coluna timestamp_col
        train_ratio: Proporção para treino (default: 0.7)
        val_ratio: Proporção para validação (default: 0.15)
        test_ratio: Proporção para teste (default: 0.15)
        timestamp_col: Nome da coluna de timestamp

    Returns:
        Tupla (df_train, df_val, df_test, split_metadata)
    """
    assert abs(train_ratio + val_ratio + test_ratio - 1.0) < 0.001, \
        "Ratios devem somar 1.0"

    if timestamp_col not in df.columns:
        raise ValueError(
            f"Coluna '{timestamp_col}' não encontrada no DataFrame. "
            f"Colunas disponíveis: {list(df.columns)}"
        )

    # Ordenar por timestamp
    df_sorted = df.sort_values(by=timestamp_col, ascending=True).reset_index(drop=True)

    n_samples = len(df_sorted)
    train_end = int(n_samples * train_ratio)
    val_end = train_end + int(n_samples * val_ratio)

    # Split temporal
    df_train = df_sorted.iloc[:train_end].copy()
    df_val = df_sorted.iloc[train_end:val_end].copy()
    df_test = df_sorted.iloc[val_end:].copy()

    # Extrair range de datas para cada split
    train_max_date = df_train[timestamp_col].max() if len(df_train) > 0 else None
    val_min_date = df_val[timestamp_col].min() if len(df_val) > 0 else None
    val_max_date = df_val[timestamp_col].max() if len(df_val) > 0 else None
    test_min_date = df_test[timestamp_col].min() if len(df_test) > 0 else None

    # Verificar integridade temporal (sem sobreposição)
    temporal_integrity_valid = True
    if train_max_date and val_min_date:
        if train_max_date >= val_min_date:
            temporal_integrity_valid = False
            logger.warning(
                "temporal_split_overlap_detected",
                train_max=str(train_max_date),
                val_min=str(val_min_date)
            )

    if val_max_date and test_min_date:
        if val_max_date >= test_min_date:
            temporal_integrity_valid = False
            logger.warning(
                "temporal_split_overlap_detected",
                val_max=str(val_max_date),
                test_min=str(test_min_date)
            )

    split_metadata = {
        'train_samples': len(df_train),
        'val_samples': len(df_val),
        'test_samples': len(df_test),
        'train_date_range': {
            'min': df_train[timestamp_col].min().isoformat() if len(df_train) > 0 else None,
            'max': train_max_date.isoformat() if train_max_date else None
        },
        'val_date_range': {
            'min': val_min_date.isoformat() if val_min_date else None,
            'max': val_max_date.isoformat() if val_max_date else None
        },
        'test_date_range': {
            'min': test_min_date.isoformat() if test_min_date else None,
            'max': df_test[timestamp_col].max().isoformat() if len(df_test) > 0 else None
        },
        'temporal_integrity_valid': temporal_integrity_valid
    }

    logger.info(
        "temporal_split_completed",
        train_samples=len(df_train),
        val_samples=len(df_val),
        test_samples=len(df_test),
        train_date_max=str(train_max_date) if train_max_date else None,
        val_date_range=f"{val_min_date} to {val_max_date}" if val_min_date and val_max_date else None,
        test_date_min=str(test_min_date) if test_min_date else None,
        temporal_integrity_valid=temporal_integrity_valid
    )

    return df_train, df_val, df_test, split_metadata


def compare_distributions(
    real_dist: Dict[int, float],
    synthetic_baseline: Dict[int, float]
) -> Dict[str, Any]:
    """
    Compara distribuição de labels reais com baseline sintético.

    Args:
        real_dist: Distribuição real (label -> percentual)
        synthetic_baseline: Baseline sintético (label -> percentual)

    Returns:
        Relatório de comparação com divergências
    """
    divergences = {}
    for label, baseline_pct in synthetic_baseline.items():
        real_pct = real_dist.get(label, 0.0)
        divergences[f"label_{label}_divergence"] = abs(real_pct - baseline_pct)

    max_divergence = max(divergences.values()) if divergences else 0.0

    comparison = {
        'real_distribution': real_dist,
        'synthetic_baseline': synthetic_baseline,
        'divergences': divergences,
        'max_divergence': max_divergence,
        'significant_drift': max_divergence > 30.0
    }

    logger.info(
        "distribution_comparison",
        **comparison
    )

    return comparison


def load_dataset_with_real_data_priority(
    specialist_type: str,
    allow_synthetic_fallback: str,
    real_data_days: int,
    min_real_samples: int,
    min_feedback_rating: float
) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    """
    Carrega dataset priorizando dados reais do MongoDB.

    Fluxo:
    1. Tentar RealDataCollector para buscar dados do ledger cognitivo
    2. Se insuficiente e fallback permitido, usar dados sintéticos
    3. Validar distribuição de labels
    4. Retornar DataFrame, data_source e metadata

    Args:
        specialist_type: Tipo do especialista
        allow_synthetic_fallback: 'true', 'false' ou 'auto'
        real_data_days: Janela de tempo para coleta
        min_real_samples: Mínimo de amostras reais
        min_feedback_rating: Rating mínimo de feedback

    Returns:
        Tupla (DataFrame, data_source, metadata)
        - data_source: 'real', 'synthetic' ou 'hybrid'
        - metadata: Dict com estatísticas e validações
    """
    # Resolver flag allow_synthetic_fallback
    environment = os.getenv('ENVIRONMENT', 'development')

    if allow_synthetic_fallback == 'auto':
        allow_fallback = (environment != 'production')
    else:
        allow_fallback = (allow_synthetic_fallback == 'true')

    logger.info(
        "dataset_loading_config",
        specialist_type=specialist_type,
        environment=environment,
        allow_synthetic_fallback=allow_fallback,
        real_data_days=real_data_days,
        min_real_samples=min_real_samples,
        real_data_collector_available=_REAL_DATA_COLLECTOR_AVAILABLE
    )

    real_data_metadata: Dict[str, Any] = {}

    # Verificar se RealDataCollector está disponível
    if not _REAL_DATA_COLLECTOR_AVAILABLE:
        logger.warning(
            "real_data_collector_not_available",
            reason="RealDataCollector import failed"
        )
        if not allow_fallback:
            raise ImportError(
                "RealDataCollector não está disponível e fallback sintético está desabilitado. "
                "Verifique se real_data_collector.py está no path correto."
            )
    else:
        # Tentar coletar dados reais usando RealDataCollector
        collector = None
        try:
            logger.info("attempting_real_data_collection")

            collector = RealDataCollector(
                mongodb_uri=os.getenv('MONGODB_URI'),
                mongodb_database=os.getenv('MONGODB_DATABASE', 'neural_hive')
            )

            # Executar coleta async
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            df_real = loop.run_until_complete(
                collector.collect_training_data(
                    specialist_type=specialist_type,
                    days=real_data_days,
                    min_samples=min_real_samples,
                    min_feedback_rating=min_feedback_rating
                )
            )

            # Validar distribuição
            distribution_report = collector.validate_label_distribution(
                df=df_real,
                specialist_type=specialist_type
            )

            # Validar qualidade usando DataQualityValidator avançado
            feature_names = get_feature_names()
            if _DATA_QUALITY_VALIDATOR_AVAILABLE:
                validator = DataQualityValidator()
                quality_report = validator.validate(
                    df=df_real,
                    feature_names=feature_names
                )

                # Gerar relatório MLflow e logar se há run ativo
                if mlflow.active_run():
                    mlflow_report = validator.generate_mlflow_report(quality_report)
                    mlflow.log_dict(mlflow_report, "data_quality_report.json")

                    # Log métricas de qualidade individuais
                    mlflow.log_metric("data_quality_score", quality_report['quality_score'])
                    mlflow.log_metric("data_missing_values_max_pct",
                                     quality_report['missing_values']['max_missing_pct'])
                    mlflow.log_metric("data_sparsity_rate",
                                     quality_report['sparsity']['sparsity_rate'])
                    mlflow.log_metric("data_max_outlier_pct",
                                     quality_report['outliers']['max_outlier_pct'])
                    mlflow.log_param("data_quality_passed", str(quality_report['passed']))

                    # Log label balance status
                    mlflow.log_param("data_labels_balanced",
                                    str(quality_report['label_imbalance']['is_balanced']))

                    logger.info(
                        "data_quality_logged_to_mlflow",
                        quality_score=quality_report['quality_score'],
                        passed=quality_report['passed']
                    )
            else:
                # Fallback para método legado se DataQualityValidator não disponível
                logger.warning("DataQualityValidator não disponível, usando validação básica")
                quality_report = {
                    'quality_score': 0.8,  # Valor padrão
                    'passed': True,
                    'warnings': []
                }

            real_data_metadata = {
                'real_samples_count': len(df_real),
                'label_distribution': distribution_report['distribution'],
                'label_percentages': distribution_report['percentages'],
                'is_balanced': distribution_report['is_balanced'],
                'quality_score': quality_report['quality_score'],
                'quality_passed': quality_report['passed'],
                'quality_warnings': quality_report.get('warnings', []),
                'date_range_start': df_real['created_at'].min().isoformat() if 'created_at' in df_real.columns and len(df_real) > 0 else None,
                'date_range_end': df_real['created_at'].max().isoformat() if 'created_at' in df_real.columns and len(df_real) > 0 else None
            }

            # Comparar com baseline sintético
            synthetic_baseline = {
                1: 50.0,  # approve
                0: 25.0,  # reject
                2: 25.0   # review_required
            }

            comparison_report = compare_distributions(
                real_dist=distribution_report['percentages'],
                synthetic_baseline=synthetic_baseline
            )
            real_data_metadata['distribution_comparison'] = comparison_report

            logger.info(
                "real_data_collection_success",
                **{k: v for k, v in real_data_metadata.items() if k not in ['distribution_comparison', 'quality_warnings']}
            )

            # Preparar DataFrame para treinamento (manter created_at para split temporal)
            feature_cols = get_feature_names() + ['label', 'created_at']
            df_training = df_real[[col for col in feature_cols if col in df_real.columns]].copy()

            return df_training, 'real', real_data_metadata

        except (InsufficientDataError, FeatureExtractionError) as e:
            logger.warning(
                "real_data_collection_failed",
                error=str(e),
                error_type=type(e).__name__,
                allow_fallback=allow_fallback
            )

            if not allow_fallback:
                logger.error(
                    "CRITICAL: Real data insufficient and synthetic fallback disabled",
                    environment=environment,
                    specialist_type=specialist_type
                )
                raise

            # Continuar para fallback sintético

        except Exception as e:
            logger.error(
                "unexpected_error_real_data_collection",
                error=str(e),
                error_type=type(e).__name__
            )

            if not allow_fallback:
                raise

        finally:
            # Sempre fechar o collector para evitar vazamento de conexões MongoDB
            if collector is not None:
                try:
                    collector.close()
                    logger.debug("real_data_collector_closed")
                except Exception as close_error:
                    logger.warning(
                        "real_data_collector_close_failed",
                        error=str(close_error)
                    )

    # Fallback para dados sintéticos com warning crítico
    logger.warning(
        "⚠️ USING SYNTHETIC DATA - NOT RECOMMENDED FOR PRODUCTION",
        specialist_type=specialist_type,
        environment=environment,
        reason="Real data collection failed or insufficient"
    )

    df_synthetic = create_synthetic_dataset(n_samples=1000)

    # Calcular distribuição de labels e percentuais
    label_counts = df_synthetic['label'].value_counts().to_dict()
    total_samples = len(df_synthetic)
    label_percentages = {
        label: (count / total_samples) * 100
        for label, count in label_counts.items()
    }

    # Comparar com baseline sintético esperado
    synthetic_baseline = {
        1: 50.0,  # approve
        0: 25.0,  # reject
        2: 25.0   # review_required
    }
    comparison_report = compare_distributions(
        real_dist=label_percentages,
        synthetic_baseline=synthetic_baseline
    )

    synthetic_metadata: Dict[str, Any] = {
        'synthetic_samples_count': len(df_synthetic),
        'label_distribution': label_counts,
        'label_percentages': label_percentages,
        'distribution_comparison': comparison_report,
        'data_source': 'synthetic',
        'warning': 'Model trained on synthetic data - performance may degrade in production'
    }

    return df_synthetic, 'synthetic', synthetic_metadata


def load_feedback_data(
    specialist_type: str,
    window_days: int,
    min_quality: float
) -> pd.DataFrame:
    """
    Carrega feedbacks do MongoDB e converte para features.

    Args:
        specialist_type: Tipo do especialista
        window_days: Janela de tempo
        min_quality: Rating mínimo

    Returns:
        DataFrame com features extraídas de feedback
    """
    try:
        mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
        client = MongoClient(mongodb_uri)
        db = client['neural_hive']

        cutoff_date = datetime.utcnow() - timedelta(days=window_days)

        # Query feedbacks
        feedbacks = list(db.specialist_feedback.find({
            'specialist_type': specialist_type,
            'submitted_at': {'$gte': cutoff_date},
            'human_rating': {'$gte': min_quality}
        }))

        logger.info(
            "Feedbacks loaded from MongoDB",
            specialist_type=specialist_type,
            count=len(feedbacks)
        )

        if not feedbacks:
            return pd.DataFrame()

        # Converter para DataFrame
        feedback_df = pd.DataFrame(feedbacks)

        # Para cada feedback, buscar opinião correspondente e extrair features
        opinions_collection = db.cognitive_ledger

        enriched_rows = []
        for _, feedback in feedback_df.iterrows():
            opinion = opinions_collection.find_one({'opinion_id': feedback['opinion_id']})

            if not opinion:
                continue

            # Extrair features da opinião
            features = extract_features_from_opinion(opinion)

            # Label baseado em concordância humana
            features['label'] = 1 if feedback['human_recommendation'] == opinion.get('recommendation') else 0

            enriched_rows.append(features)

        if not enriched_rows:
            return pd.DataFrame()

        feedback_features_df = pd.DataFrame(enriched_rows)

        logger.info(
            "Feedback features extracted",
            size=len(feedback_features_df)
        )

        return feedback_features_df

    except Exception as e:
        logger.error(
            "Failed to load feedback data",
            error=str(e)
        )
        return pd.DataFrame()


def extract_features_from_opinion(opinion: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extrai features de uma opinião para treinamento usando FeatureExtractor.

    Usa o mesmo pipeline de extração de features que é usado em inferência,
    garantindo alinhamento completo com o schema definido em feature_definitions.py.

    Args:
        opinion: Documento de opinião do MongoDB (deve conter cognitive_plan)

    Returns:
        Dict com features alinhadas ao schema centralizado
    """
    # Obter schema de features esperado
    expected_feature_names = get_feature_names()

    # Inicializar features com valores padrão (0.0)
    features = {name: 0.0 for name in expected_feature_names}

    # Obter cognitive_plan associado à opinião
    cognitive_plan = opinion.get('cognitive_plan', {})

    if not cognitive_plan:
        logger.warning(
            "opinion_missing_cognitive_plan",
            opinion_id=opinion.get('opinion_id'),
            fallback="using_default_features"
        )
        return features

    # Usar FeatureExtractor se disponível
    if _FEATURE_EXTRACTOR_AVAILABLE:
        try:
            extractor = FeatureExtractor()
            features_structured = extractor.extract_features(cognitive_plan)
            extracted_features = features_structured.get('aggregated_features', {})

            # Preencher features extraídas no dict padronizado
            for key, value in extracted_features.items():
                if key in features:
                    features[key] = float(value)
                else:
                    logger.debug(
                        "unexpected_feature_from_extractor",
                        feature_name=key,
                        opinion_id=opinion.get('opinion_id')
                    )

            logger.debug(
                "features_extracted_from_opinion",
                opinion_id=opinion.get('opinion_id'),
                num_features_populated=sum(1 for v in features.values() if v != 0.0)
            )

        except Exception as e:
            logger.warning(
                "feature_extraction_failed_for_opinion",
                opinion_id=opinion.get('opinion_id'),
                error=str(e),
                fallback="using_default_features"
            )
    else:
        logger.warning(
            "feature_extractor_not_available",
            opinion_id=opinion.get('opinion_id'),
            fallback="using_default_features"
        )

    return features


def train_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    model_type: str,
    hyperparameter_tuning: bool
) -> Any:
    """
    Treina modelo baseado no tipo especificado.

    Args:
        X_train: Features de treinamento
        y_train: Labels de treinamento
        model_type: Tipo de modelo
        hyperparameter_tuning: Habilitar tuning

    Returns:
        Modelo treinado
    """
    logger.info(
        "Training model",
        model_type=model_type,
        n_samples=len(X_train),
        hyperparameter_tuning=hyperparameter_tuning
    )

    if model_type == 'random_forest':
        if hyperparameter_tuning:
            from sklearn.model_selection import GridSearchCV
            param_grid = {
                'n_estimators': [50, 100, 200],
                'max_depth': [5, 10, 20],
                'min_samples_split': [2, 5, 10]
            }
            base_model = RandomForestClassifier(random_state=42)
            model = GridSearchCV(base_model, param_grid, cv=3, n_jobs=-1)
        else:
            model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42
            )

    elif model_type == 'gradient_boosting':
        if hyperparameter_tuning:
            from sklearn.model_selection import GridSearchCV
            param_grid = {
                'n_estimators': [50, 100, 200],
                'learning_rate': [0.01, 0.1, 0.2],
                'max_depth': [3, 5, 7]
            }
            base_model = GradientBoostingClassifier(random_state=42)
            model = GridSearchCV(base_model, param_grid, cv=3, n_jobs=-1)
        else:
            model = GradientBoostingClassifier(
                n_estimators=100,
                learning_rate=0.1,
                random_state=42
            )

    elif model_type == 'neural_network':
        model = MLPClassifier(
            hidden_layer_sizes=(100, 50),
            max_iter=500,
            random_state=42
        )

    else:
        raise ValueError(f"Unknown model type: {model_type}")

    # Treinar
    model.fit(X_train, y_train)

    logger.info("Model training completed")

    return model


def validate_predict_proba_support(model: Any) -> bool:
    """
    Valida se o modelo suporta predict_proba() para saída probabilística.

    Args:
        model: Modelo treinado (sklearn ou GridSearchCV)

    Returns:
        True se o modelo suporta predict_proba(), False caso contrário
    """
    # Para GridSearchCV, verificar o best_estimator_
    actual_model = model
    if hasattr(model, 'best_estimator_'):
        actual_model = model.best_estimator_

    supports_proba = hasattr(actual_model, 'predict_proba') and callable(
        getattr(actual_model, 'predict_proba')
    )

    if supports_proba:
        logger.info(
            "model_supports_predict_proba",
            model_type=type(actual_model).__name__,
            supports_proba=True
        )
    else:
        logger.warning(
            "model_does_not_support_predict_proba",
            model_type=type(actual_model).__name__,
            supports_proba=False,
            fallback="using predict() instead"
        )

    return supports_proba


def evaluate_model(
    model: Any,
    X_val: pd.DataFrame,
    y_val: pd.Series
) -> Dict[str, float]:
    """
    Avalia modelo em dataset de validação, incluindo métricas de calibração.

    Args:
        model: Modelo treinado
        X_val: Features de validação
        y_val: Labels de validação

    Returns:
        Dict com métricas (precision, recall, f1, accuracy, brier_score, log_loss,
        supports_predict_proba, calibration_computed)
    """
    y_pred = model.predict(X_val)

    metrics = {
        'precision': precision_score(y_val, y_pred, average='binary', zero_division=0),
        'recall': recall_score(y_val, y_pred, average='binary', zero_division=0),
        'f1': f1_score(y_val, y_pred, average='binary', zero_division=0),
        'accuracy': accuracy_score(y_val, y_pred)
    }

    # Inicializar calibration_computed como False
    metrics['calibration_computed'] = False

    # Calcular métricas de calibração se predict_proba() disponível
    supports_proba = validate_predict_proba_support(model)
    metrics['supports_predict_proba'] = supports_proba

    if supports_proba:
        try:
            y_proba = model.predict_proba(X_val)

            # Brier Score: usa probabilidade da classe positiva (índice 1)
            # Range [0, 1], onde 0 é perfeito
            metrics['brier_score'] = brier_score_loss(y_val, y_proba[:, 1])

            # Log Loss: penaliza predições confiantes incorretas
            # Range [0, ∞), onde 0 é perfeito
            metrics['log_loss'] = log_loss(y_val, y_proba)

            # Classificar qualidade da calibração
            brier = metrics['brier_score']
            if brier <= 0.15:
                calibration_quality = 'excellent'
            elif brier <= 0.25:
                calibration_quality = 'good'
            elif brier <= 0.35:
                calibration_quality = 'fair'
            else:
                calibration_quality = 'poor'

            metrics['calibration_quality'] = calibration_quality
            metrics['calibration_computed'] = True

            logger.info(
                "calibration_metrics_calculated",
                brier_score=metrics['brier_score'],
                log_loss=metrics['log_loss'],
                calibration_quality=calibration_quality
            )

        except Exception as e:
            logger.warning(
                "calibration_metrics_failed",
                error=str(e),
                fallback="metrics without calibration"
            )
            metrics['brier_score'] = None
            metrics['log_loss'] = None
            metrics['calibration_quality'] = 'unknown'
            # calibration_computed permanece False
    else:
        metrics['brier_score'] = None
        metrics['log_loss'] = None
        metrics['calibration_quality'] = 'not_available'
        # calibration_computed permanece False

    logger.info(
        "Model evaluated",
        precision=metrics['precision'],
        recall=metrics['recall'],
        f1=metrics['f1'],
        accuracy=metrics['accuracy'],
        brier_score=metrics.get('brier_score'),
        log_loss=metrics.get('log_loss'),
        calibration_quality=metrics.get('calibration_quality'),
        supports_predict_proba=metrics.get('supports_predict_proba'),
        calibration_computed=metrics.get('calibration_computed')
    )

    return metrics


def get_baseline_model(specialist_type: str, registry_entry: Dict[str, str] = None) -> Tuple[Any, Dict[str, float]]:
    """
    Busca modelo baseline atual em Production.

    Args:
        specialist_type: Tipo do especialista
        registry_entry: Configuração validada para model/experiment/stage

    Returns:
        Tupla (modelo, métricas) ou (None, None)
    """
    try:
        entry = registry_entry or validate_registry_alignment(specialist_type)
        model_name = entry["model_name"]
        model_stage = entry.get("stage") or "Production"

        # Tentar carregar modelo de Production
        model_uri = f"models:/{model_name}/{model_stage}"
        model = mlflow.pyfunc.load_model(model_uri)

        # Buscar métricas do modelo
        client = mlflow.tracking.MlflowClient()
        versions = client.search_model_versions(f"name='{model_name}'")

        baseline_metrics = None
        for version in versions:
            if version.current_stage == model_stage:
                run = client.get_run(version.run_id)
                baseline_metrics = {
                    'precision': run.data.metrics.get('precision', 0.0),
                    'recall': run.data.metrics.get('recall', 0.0),
                    'f1': run.data.metrics.get('f1', 0.0)
                }
                break

        logger.info(
            "Baseline model loaded",
            model_name=model_name,
            metrics=baseline_metrics
        )

        return model, baseline_metrics

    except Exception as e:
        logger.warning(
            "No baseline model found",
            specialist_type=specialist_type,
            error=str(e)
        )
        return None, None


def should_promote_model(
    new_metrics: Dict[str, float],
    baseline_metrics: Dict[str, float] = None,
    precision_threshold: float = 0.75,
    recall_threshold: float = 0.70,
    f1_threshold: float = 0.72,
    improvement_threshold: float = None
) -> bool:
    """
    Determina se modelo deve ser promovido.

    Critérios de promoção:
    1. Métricas absolutas: precision >= 0.75, recall >= 0.70, f1 >= 0.72
    2. Se há baseline: F1 deve ser >= baseline F1 (não regressão)
    3. Se há baseline: ao menos uma métrica deve melhorar >= improvement_threshold

    Args:
        new_metrics: Métricas do novo modelo
        baseline_metrics: Métricas do baseline (None se não há baseline)
        precision_threshold: Precision mínima
        recall_threshold: Recall mínimo
        f1_threshold: F1 score mínimo
        improvement_threshold: Melhoria mínima sobre baseline para F1 (default: env MODEL_IMPROVEMENT_THRESHOLD ou 0.02)

    Returns:
        True se deve promover
    """
    # Carregar improvement_threshold de env var se não fornecido
    if improvement_threshold is None:
        improvement_threshold = float(os.getenv('MODEL_IMPROVEMENT_THRESHOLD', '0.02'))

    logger.info(
        "Checking promotion criteria",
        precision_threshold=precision_threshold,
        recall_threshold=recall_threshold,
        f1_threshold=f1_threshold,
        improvement_threshold=improvement_threshold,
        has_baseline=baseline_metrics is not None
    )

    # Verificar thresholds absolutos
    if new_metrics.get('precision', 0.0) < precision_threshold:
        logger.info(
            "Model not promoted - precision below threshold",
            precision=new_metrics.get('precision', 0.0),
            threshold=precision_threshold
        )
        return False

    if new_metrics.get('recall', 0.0) < recall_threshold:
        logger.info(
            "Model not promoted - recall below threshold",
            recall=new_metrics.get('recall', 0.0),
            threshold=recall_threshold
        )
        return False

    if new_metrics.get('f1', 0.0) < f1_threshold:
        logger.info(
            "Model not promoted - F1 score below threshold",
            f1=new_metrics.get('f1', 0.0),
            threshold=f1_threshold
        )
        return False

    # Se não há baseline (None ou dict vazio), promover se passou thresholds absolutos
    if baseline_metrics is None or len(baseline_metrics) == 0:
        logger.info("No baseline metrics available - promoting new model based on absolute thresholds")
        return True

    # Extrair métricas do baseline com defaults seguros
    baseline_precision = baseline_metrics.get('precision', 0.0)
    baseline_recall = baseline_metrics.get('recall', 0.0)
    baseline_f1 = baseline_metrics.get('f1', 0.0)

    new_precision = new_metrics.get('precision', 0.0)
    new_recall = new_metrics.get('recall', 0.0)
    new_f1 = new_metrics.get('f1', 0.0)

    # Calcular melhorias
    precision_improvement = new_precision - baseline_precision
    recall_improvement = new_recall - baseline_recall
    f1_improvement = new_f1 - baseline_f1

    logger.info(
        "Comparing with baseline",
        baseline_precision=baseline_precision,
        baseline_recall=baseline_recall,
        baseline_f1=baseline_f1,
        new_precision=new_precision,
        new_recall=new_recall,
        new_f1=new_f1,
        precision_improvement=precision_improvement,
        recall_improvement=recall_improvement,
        f1_improvement=f1_improvement
    )

    # Critério 1: F1 não pode regredir (métrica primária)
    if f1_improvement < 0:
        logger.info(
            "Model not promoted - F1 score regressed from baseline",
            new_f1=new_f1,
            baseline_f1=baseline_f1,
            f1_improvement=f1_improvement
        )
        return False

    # Critério 2: Recall não pode regredir significativamente (tolerância de 0.01)
    if recall_improvement < -0.01:
        logger.info(
            "Model not promoted - recall regressed from baseline",
            new_recall=new_recall,
            baseline_recall=baseline_recall,
            recall_improvement=recall_improvement
        )
        return False

    # Critério 3: Precision não pode regredir significativamente (tolerância de 0.01)
    if precision_improvement < -0.01:
        logger.info(
            "Model not promoted - precision regressed from baseline",
            new_precision=new_precision,
            baseline_precision=baseline_precision,
            precision_improvement=precision_improvement
        )
        return False

    # Critério 4: F1 deve melhorar pelo menos improvement_threshold (métrica primária)
    if f1_improvement >= improvement_threshold:
        logger.info(
            "Model promoted - F1 improved over baseline",
            f1_improvement=f1_improvement,
            improvement_threshold=improvement_threshold,
            precision_improvement=precision_improvement,
            recall_improvement=recall_improvement
        )
        return True

    # Critério 5: Se F1 não melhorou o suficiente, verificar se precision E recall melhoraram
    if precision_improvement > 0 and recall_improvement > 0:
        logger.info(
            "Model promoted - both precision and recall improved (F1 improvement below threshold)",
            f1_improvement=f1_improvement,
            precision_improvement=precision_improvement,
            recall_improvement=recall_improvement
        )
        return True

    logger.info(
        "Model not promoted - insufficient improvement over baseline",
        f1_improvement=f1_improvement,
        precision_improvement=precision_improvement,
        recall_improvement=recall_improvement,
        required_f1_improvement=improvement_threshold
    )
    return False


def main():
    """Ponto de entrada principal."""
    args = parse_args()

    print(f"🤖 Neural Hive - Model Retraining Pipeline")
    print(f"   Specialist: {args.specialist_type}")
    print(f"   Model type: {args.model_type}")
    print(f"   Feedback count: {args.feedback_count}")
    print()

    # Configurar MLflow
    registry_entry = validate_registry_alignment(args.specialist_type)
    model_name = registry_entry["model_name"]
    model_stage = registry_entry.get("stage") or "Production"
    experiment_name = registry_entry["experiment_name"]

    mlflow.set_tracking_uri(os.getenv('MLFLOW_TRACKING_URI', 'http://mlflow:5000'))
    mlflow.set_experiment(experiment_name)

    with mlflow.start_run():
        # Log parâmetros
        mlflow.log_param('specialist_type', args.specialist_type)
        mlflow.log_param('model_type', args.model_type)
        mlflow.log_param('feedback_count', args.feedback_count)
        mlflow.log_param('window_days', args.window_days)
        mlflow.log_param('min_feedback_quality', args.min_feedback_quality)
        mlflow.log_param('mlflow_model_name_expected', model_name)
        mlflow.log_param('mlflow_model_stage_expected', model_stage)
        mlflow.log_param('mlflow_experiment_expected', experiment_name)
        mlflow.log_param('allow_synthetic_fallback', args.allow_synthetic_fallback)
        mlflow.log_param('real_data_days', args.real_data_days)
        mlflow.log_param('min_real_samples', args.min_real_samples)

        environment = os.getenv('ENVIRONMENT', 'development')
        mlflow.log_param('environment', environment)

        # Inicializar audit logger para rastreamento do ciclo de vida do modelo
        audit_logger = create_audit_logger()
        training_start_time = datetime.utcnow()
        model_version = f"v{training_start_time.strftime('%Y%m%d%H%M%S')}"

        # Obter ou criar event loop para operações assíncronas
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Registrar início do treinamento no audit log
        if audit_logger and _MODEL_AUDIT_LOGGER_AVAILABLE:
            training_config = {
                'specialist_type': args.specialist_type,
                'model_type': args.model_type,
                'hyperparameter_tuning': args.hyperparameter_tuning,
                'window_days': args.window_days,
                'min_feedback_quality': args.min_feedback_quality,
                'real_data_days': args.real_data_days,
                'min_real_samples': args.min_real_samples,
                'allow_synthetic_fallback': args.allow_synthetic_fallback,
                'mlflow_run_id': mlflow.active_run().info.run_id
            }
            context = AuditEventContext(
                user_id='training_pipeline',
                reason='Retreinamento programado do modelo',
                environment=environment,
                triggered_by='scheduled' if args.feedback_count > 0 else 'manual',
                metadata={'feedback_count': args.feedback_count}
            )
            loop.run_until_complete(log_audit_event(
                audit_logger,
                'log_training_started',
                model_name=model_name,
                model_version=model_version,
                context=context,
                training_config=training_config
            ))
            logger.info('audit_log_training_started', model_name=model_name, model_version=model_version)

        # 0. Validação de pré-requisitos (antes de carregar dados)
        if args.skip_validation == 'false':
            if _PRE_RETRAINING_VALIDATOR_AVAILABLE:
                print(f"🔍 Executando validação de pré-requisitos...")

                validator = PreRetrainingValidator(
                    mongodb_uri=os.getenv('MONGODB_URI'),
                    mongodb_database=os.getenv('MONGODB_DATABASE', 'neural_hive')
                )

                try:
                    validation_report = validator.validate_prerequisites(
                        specialist_type=args.specialist_type,
                        days=args.real_data_days,
                        min_samples=args.min_real_samples,
                        min_feedback_rating=args.min_feedback_quality
                    )

                    # Log relatório de validação no MLflow
                    mlflow.log_dict(validation_report, "pre_retraining_validation.json")
                    mlflow.log_param('pre_validation_passed', validation_report['passed'])
                    mlflow.log_param('pre_validation_recommendation', validation_report['recommendation'])

                    # Verificar se validação passou
                    if not validation_report['passed']:
                        print(f"❌ Validação de pré-requisitos FALHOU")
                        print(f"   Recomendação: {validation_report['recommendation']}")

                        if validation_report['blocking_issues']:
                            print(f"   Problemas bloqueantes:")
                            for issue in validation_report['blocking_issues']:
                                print(f"     - {issue}")

                        if validation_report['recommendation'] == 'wait_for_more_data':
                            raise ValidationFailedError(
                                f"Dados insuficientes para retraining. "
                                f"Atual: {validation_report['checks']['sample_count']['current']} amostras, "
                                f"Necessário: {validation_report['checks']['sample_count']['required']}. "
                                f"Aguarde coleta de mais feedback."
                            )
                        elif validation_report['recommendation'] == 'investigate_distribution':
                            raise ValidationFailedError(
                                f"Problemas de distribuição de dados detectados. "
                                f"Warnings: {validation_report['warnings']}. "
                                f"Investigue a qualidade dos dados antes de retreinar."
                            )

                    print(f"✅ Validação de pré-requisitos PASSOU")
                    print(f"   Amostras disponíveis: {validation_report['checks']['sample_count']['current']}")
                    if validation_report['checks']['label_distribution'].get('percentages'):
                        print(f"   Distribuição de labels: {validation_report['checks']['label_distribution']['percentages']}")
                    print()

                    # Audit log: validation_passed
                    if audit_logger and _MODEL_AUDIT_LOGGER_AVAILABLE:
                        validation_context = AuditEventContext(
                            user_id='training_pipeline',
                            reason='Validação de pré-requisitos passou',
                            environment=environment,
                            triggered_by='automatic',
                            metadata={'validation_report': validation_report}
                        )
                        loop.run_until_complete(log_audit_event(
                            audit_logger,
                            'log_validation_passed',
                            model_name=model_name,
                            model_version=model_version,
                            context=validation_context,
                            validation_results=validation_report
                        ))

                except ValidationFailedError as e:
                    logger.error(
                        "pre_retraining_validation_failed",
                        specialist_type=args.specialist_type,
                        error=str(e)
                    )
                    mlflow.set_tag('validation_failed', 'true')
                    mlflow.log_param('validation_failure_reason', str(e)[:250])

                    # Audit log: validation_failed
                    if audit_logger and _MODEL_AUDIT_LOGGER_AVAILABLE:
                        validation_context = AuditEventContext(
                            user_id='training_pipeline',
                            reason=str(e)[:500],
                            environment=environment,
                            triggered_by='automatic',
                            metadata={'error_type': type(e).__name__}
                        )
                        loop.run_until_complete(log_audit_event(
                            audit_logger,
                            'log_validation_failed',
                            model_name=model_name,
                            model_version=model_version,
                            context=validation_context,
                            validation_results={'passed': False, 'error': str(e)[:500]},
                            failure_reasons=[str(e)]
                        ))

                    raise

                finally:
                    validator.close()

            else:
                logger.warning(
                    "pre_retraining_validator_not_available",
                    specialist_type=args.specialist_type,
                    reason="PreRetrainingValidator import failed"
                )
                print(f"⚠️  Validador de pré-requisitos não disponível, continuando sem validação...")
                mlflow.log_param('pre_validation_passed', 'skipped_unavailable')

        else:
            print(f"⚠️  PULANDO validação de pré-requisitos (--skip-validation=true)")
            logger.warning(
                "pre_retraining_validation_skipped",
                specialist_type=args.specialist_type,
                reason="skip_validation flag set"
            )
            mlflow.set_tag('validation_skipped', 'true')
            mlflow.log_param('pre_validation_passed', 'skipped_manual')

        # 1. Carregar dataset com prioridade para dados reais
        df_base, data_source, data_metadata = load_dataset_with_real_data_priority(
            specialist_type=args.specialist_type,
            allow_synthetic_fallback=args.allow_synthetic_fallback,
            real_data_days=args.real_data_days,
            min_real_samples=args.min_real_samples,
            min_feedback_rating=args.min_feedback_quality
        )

        mlflow.log_metric('base_dataset_size', len(df_base))
        mlflow.log_param('data_source', data_source)
        mlflow.set_tag('data_source_type', data_source)

        # Registrar métricas específicas de dados
        if data_source == 'real':
            mlflow.log_metric('real_samples_count', data_metadata.get('real_samples_count', len(df_base)))
            mlflow.log_metric('quality_score', data_metadata.get('quality_score', 0.0))
            mlflow.log_metric('is_balanced', 1.0 if data_metadata.get('is_balanced', False) else 0.0)

            # Log distribuição de labels
            for label, pct in data_metadata.get('label_percentages', {}).items():
                mlflow.log_metric(f'label_{label}_percentage', pct)

            # Log comparação com sintético
            if 'distribution_comparison' in data_metadata:
                mlflow.log_metric(
                    'max_distribution_divergence',
                    data_metadata['distribution_comparison'].get('max_divergence', 0.0)
                )

            # Log range de datas
            if data_metadata.get('date_range_start'):
                mlflow.log_param('data_date_range_start', data_metadata['date_range_start'])
            if data_metadata.get('date_range_end'):
                mlflow.log_param('data_date_range_end', data_metadata['date_range_end'])

            print(f"📁 Using REAL dataset from MongoDB")
            print(f"   Samples: {data_metadata.get('real_samples_count', len(df_base))}")
            print(f"   Quality score: {data_metadata.get('quality_score', 'N/A')}")
            if data_metadata.get('date_range_start') and data_metadata.get('date_range_end'):
                print(f"   Date range: {data_metadata['date_range_start'][:10]} to {data_metadata['date_range_end'][:10]}")

        elif data_source == 'synthetic':
            mlflow.log_metric('synthetic_samples_count', data_metadata.get('synthetic_samples_count', len(df_base)))
            if data_metadata.get('warning'):
                mlflow.set_tag('data_warning', data_metadata['warning'])

            # Log distribuição de labels para dados sintéticos (similar a dados reais)
            for label, pct in data_metadata.get('label_percentages', {}).items():
                mlflow.log_metric(f'label_{label}_percentage', pct)

            # Log divergência da distribuição (comparação com baseline esperado)
            if 'distribution_comparison' in data_metadata:
                mlflow.log_metric(
                    'max_distribution_divergence',
                    data_metadata['distribution_comparison'].get('max_divergence', 0.0)
                )
                # Log divergência por label
                for label_key, divergence in data_metadata['distribution_comparison'].get('divergences', {}).items():
                    mlflow.log_metric(label_key, divergence)

            print(f"⚠️  Using SYNTHETIC dataset for training")
            print(f"   Samples: {data_metadata.get('synthetic_samples_count', len(df_base))}")
            print(f"   Label distribution: {data_metadata.get('label_distribution', {})}")
            print(f"   Warning: {data_metadata.get('warning', 'Model trained on synthetic data')}")

            # Validação crítica para produção
            if environment == 'production':
                logger.error(
                    "CRITICAL: Cannot train production model with synthetic data",
                    specialist_type=args.specialist_type,
                    environment=environment
                )
                raise RuntimeError(
                    "CRITICAL: Cannot train production model with synthetic data. "
                    f"Specialist: {args.specialist_type}. "
                    "Collect more real feedback data or set ENVIRONMENT=development."
                )

        # 2. Carregar feedbacks adicionais (opcional, para enriquecimento)
        df_feedback = load_feedback_data(
            args.specialist_type,
            args.window_days,
            args.min_feedback_quality
        )
        mlflow.log_metric('feedback_dataset_size', len(df_feedback))

        # 3. Enriquecer dataset (apenas se temos feedback adicional além do real)
        if len(df_feedback) > 0 and data_source != 'real':
            df_enriched = pd.concat([df_base, df_feedback], ignore_index=True)
        else:
            df_enriched = df_base

        mlflow.log_metric('total_dataset_size', len(df_enriched))

        print(f"📊 Dataset sizes:")
        print(f"   Base ({data_source}): {len(df_base)}")
        print(f"   Additional Feedback: {len(df_feedback)}")
        print(f"   Total: {len(df_enriched)}")
        print()

        # Validar schema antes de treinar
        expected_features = get_feature_names()
        actual_features = [col for col in df_enriched.columns if col != 'label']

        if set(expected_features) != set(actual_features):
            missing = list(set(expected_features) - set(actual_features))
            extra = list(set(actual_features) - set(expected_features))
            logger.error(
                "schema_mismatch_before_training",
                expected=expected_features,
                actual=actual_features,
                missing=missing,
                extra=extra
            )
            raise ValueError(
                f"Dataset schema mismatch. Expected {len(expected_features)} features, "
                f"got {len(actual_features)}. Missing: {missing}, Extra: {extra}. "
                f"Run generate_training_datasets.py to regenerate."
            )

        print(f"✅ Schema validation passed: {len(expected_features)} features")

        # 4. Split dataset usando split temporal (evita data leakage)
        # Verificar se temos created_at para split temporal
        if 'created_at' not in df_enriched.columns:
            logger.warning(
                "created_at_not_found_for_temporal_split",
                reason="Usando split aleatório como fallback",
                columns=list(df_enriched.columns)
            )
            # Fallback para split aleatório
            X = df_enriched.drop('label', axis=1)
            y = df_enriched['label']
            X_train, X_temp, y_train, y_temp = train_test_split(
                X, y, test_size=0.3, random_state=42
            )
            X_val, X_test, y_val, y_test = train_test_split(
                X_temp, y_temp, test_size=0.33, random_state=42
            )
            split_metadata = {'split_type': 'random', 'temporal_integrity_valid': False}
        else:
            # Split temporal: treino mais antigo, validação intermediário, teste mais recente
            df_train, df_val, df_test, split_metadata = temporal_split(
                df=df_enriched,
                train_ratio=0.7,
                val_ratio=0.15,
                test_ratio=0.15,
                timestamp_col='created_at'
            )
            split_metadata['split_type'] = 'temporal'

            # Verificar integridade temporal
            if not split_metadata.get('temporal_integrity_valid', True):
                logger.error(
                    "temporal_integrity_violation",
                    split_metadata=split_metadata
                )
                raise ValueError(
                    "Falha na integridade temporal do split: há sobreposição de datas entre splits. "
                    "Verifique os dados de entrada."
                )

            # Validar integridade temporal usando PreRetrainingValidator
            if _PRE_RETRAINING_VALIDATOR_AVAILABLE:
                from pre_retraining_validator import PreRetrainingValidator
                leakage_validation = PreRetrainingValidator.validate_temporal_split_integrity(
                    train_timestamps=df_train['created_at'].tolist(),
                    val_timestamps=df_val['created_at'].tolist(),
                    test_timestamps=df_test['created_at'].tolist()
                )

                if not leakage_validation['passed']:
                    logger.error(
                        "data_leakage_detected",
                        leakage_details=leakage_validation['leakage_details'],
                        train_max=leakage_validation['train_max'],
                        val_min=leakage_validation['val_min'],
                        val_max=leakage_validation['val_max'],
                        test_min=leakage_validation['test_min']
                    )
                    raise ValueError(
                        f"Data leakage detectado no split temporal! "
                        f"Detalhes: {'; '.join(leakage_validation['leakage_details'])}. "
                        f"Verifique a ordenação temporal dos dados."
                    )

                # Logar resultado da validação de leakage
                mlflow.log_dict(leakage_validation, "data_leakage_validation.json")
                mlflow.log_param('data_leakage_validated', True)
                mlflow.log_param('data_leakage_passed', leakage_validation['passed'])

            # Separar features e labels (remover created_at das features)
            feature_cols = [col for col in df_train.columns if col not in ['label', 'created_at']]
            X_train = df_train[feature_cols]
            y_train = df_train['label']
            X_val = df_val[feature_cols]
            y_val = df_val['label']
            X_test = df_test[feature_cols]
            y_test = df_test['label']

            # Log informações temporais
            mlflow.log_dict(split_metadata, "temporal_split_metadata.json")
            mlflow.log_param('split_type', 'temporal')
            mlflow.log_param('temporal_integrity_valid', split_metadata['temporal_integrity_valid'])

        print(f"📈 Splits ({split_metadata.get('split_type', 'unknown')}):")
        print(f"   Train: {len(X_train)}")
        print(f"   Validation: {len(X_val)}")
        print(f"   Test: {len(X_test)}")
        if split_metadata.get('split_type') == 'temporal':
            print(f"   Temporal integrity: {'✓' if split_metadata.get('temporal_integrity_valid') else '✗'}")
            if split_metadata.get('train_date_range', {}).get('max'):
                print(f"   Train date range: até {split_metadata['train_date_range']['max'][:10]}")
            if split_metadata.get('val_date_range', {}).get('min'):
                print(f"   Val date range: {split_metadata['val_date_range']['min'][:10]} a {split_metadata['val_date_range']['max'][:10]}")
            if split_metadata.get('test_date_range', {}).get('min'):
                print(f"   Test date range: a partir de {split_metadata['test_date_range']['min'][:10]}")
        print()

        # 5. Treinar modelo
        print(f"🔧 Training {args.model_type} model...")
        try:
            model = train_model(
                X_train, y_train,
                args.model_type,
                args.hyperparameter_tuning == 'true'
            )
        except Exception as train_error:
            logger.error('model_training_failed', error=str(train_error))

            # Audit log: training_failed
            if audit_logger and _MODEL_AUDIT_LOGGER_AVAILABLE:
                training_end_time = datetime.utcnow()
                training_duration_seconds = (training_end_time - training_start_time).total_seconds()
                failure_context = AuditEventContext(
                    user_id='training_pipeline',
                    reason=f'Falha durante treinamento: {str(train_error)[:500]}',
                    duration_seconds=training_duration_seconds,
                    environment=environment,
                    triggered_by='automatic',
                    metadata={'error_type': type(train_error).__name__}
                )
                loop.run_until_complete(log_audit_event(
                    audit_logger,
                    'log_training_failed',
                    model_name=model_name,
                    model_version=model_version,
                    context=failure_context,
                    error_message=str(train_error)[:500],
                    error_details={'stage': 'training'}
                ))
            raise

        # 6. Avaliar modelo
        print(f"📊 Evaluating model...")
        try:
            metrics = evaluate_model(model, X_val, y_val)
        except Exception as eval_error:
            logger.error('model_evaluation_failed', error=str(eval_error))

            # Audit log: training_failed (avaliação falhou)
            if audit_logger and _MODEL_AUDIT_LOGGER_AVAILABLE:
                training_end_time = datetime.utcnow()
                training_duration_seconds = (training_end_time - training_start_time).total_seconds()
                failure_context = AuditEventContext(
                    user_id='training_pipeline',
                    reason=f'Falha durante avaliação: {str(eval_error)[:500]}',
                    duration_seconds=training_duration_seconds,
                    environment=environment,
                    triggered_by='automatic',
                    metadata={'error_type': type(eval_error).__name__}
                )
                loop.run_until_complete(log_audit_event(
                    audit_logger,
                    'log_training_failed',
                    model_name=model_name,
                    model_version=model_version,
                    context=failure_context,
                    error_message=str(eval_error)[:500],
                    error_details={'stage': 'evaluation'}
                ))
            raise

        # Log métricas (apenas valores numéricos)
        for metric_name, value in metrics.items():
            if isinstance(value, (int, float)) and value is not None:
                mlflow.log_metric(metric_name, value)

        # Log parâmetros de calibração (separando suporte de sucesso)
        mlflow.log_param('supports_predict_proba', metrics.get('supports_predict_proba', False))
        mlflow.log_param('calibration_validated', metrics.get('calibration_computed', False))
        mlflow.log_param('calibration_quality', metrics.get('calibration_quality', 'unknown'))

        print(f"   Precision: {metrics['precision']:.3f}")
        print(f"   Recall: {metrics['recall']:.3f}")
        print(f"   F1: {metrics['f1']:.3f}")

        # Exibir métricas de calibração se disponíveis
        if metrics.get('brier_score') is not None:
            print(f"   Brier Score: {metrics['brier_score']:.4f} ({metrics.get('calibration_quality', 'unknown')})")
            print(f"   Log Loss: {metrics['log_loss']:.4f}")
        print()

        # 7. Registrar modelo
        print(f"💾 Registering model...")

        # Criar signature explícita para enforcement de schema
        # Usar predict_proba() se disponível para saída probabilística
        input_example = X_val.head(1)
        supports_proba = metrics.get('supports_predict_proba', False)

        if supports_proba:
            # Signature com saída probabilística [n_samples, n_classes]
            signature = infer_signature(X_val, model.predict_proba(X_val))
            logger.info(
                "model_signature_created",
                output_type="probabilistic",
                output_shape="[n_samples, n_classes]"
            )
        else:
            # Fallback para predict() se probabilidades não disponíveis
            signature = infer_signature(X_val, model.predict(X_val))
            logger.warning(
                "model_signature_fallback",
                output_type="discrete",
                output_shape="[n_samples]",
                reason="predict_proba not available"
            )

        # Flag para indicar se o modelo foi registrado com sucesso
        model_registered = False
        registered_version = None

        # Logar modelo com signature e schema metadata
        try:
            if supports_proba:
                # Usar wrapper pyfunc para alinhar contrato: predict() retorna probabilidades
                # Salvar modelo sklearn em arquivo temporário para usar como artifact
                with tempfile.TemporaryDirectory() as tmpdir:
                    sklearn_model_path = os.path.join(tmpdir, "sklearn_model.joblib")
                    joblib.dump(model, sklearn_model_path)

                    # Registrar com wrapper pyfunc
                    mlflow.pyfunc.log_model(
                        artifact_path="model",
                        python_model=ProbabilisticModelWrapper(),
                        artifacts={"sklearn_model": sklearn_model_path},
                        registered_model_name=model_name,
                        signature=signature,
                        input_example=input_example,
                        conda_env={
                            "channels": ["defaults", "conda-forge"],
                            "dependencies": [
                                f"python={sys.version_info.major}.{sys.version_info.minor}",
                                "pip",
                                {"pip": ["mlflow", "scikit-learn", "pandas", "numpy", "joblib"]}
                            ],
                            "name": "probabilistic_model_env"
                        }
                    )

                logger.info(
                    "model_registered_with_pyfunc_wrapper",
                    model_name=model_name,
                    wrapper_class="ProbabilisticModelWrapper",
                    predict_returns="probabilities"
                )
            else:
                # Sem suporte a probabilidades, usar sklearn flavor diretamente
                mlflow.sklearn.log_model(
                    sk_model=model,
                    artifact_path="model",
                    registered_model_name=model_name,
                    signature=signature,
                    input_example=input_example
                )

            # Logar feature schema como artifact
            feature_schema = get_feature_schema()
            mlflow.log_dict(feature_schema, "feature_schema.json")

            # Logar feature names como param
            feature_names = get_feature_names()
            mlflow.log_param('feature_names', ','.join(feature_names))
            mlflow.log_param('num_features', len(feature_names))

            # Tag para rastreabilidade de saída probabilística
            mlflow.set_tag('probabilistic_output', str(supports_proba).lower())
            mlflow.set_tag('output_signature_type', 'predict_proba' if supports_proba else 'predict')

            # Criar relatório de calibração como artifact
            calibration_report = {
                'brier_score': metrics.get('brier_score'),
                'log_loss': metrics.get('log_loss'),
                'calibration_quality': metrics.get('calibration_quality', 'unknown'),
                'supports_predict_proba': supports_proba,
                'calibration_computed': metrics.get('calibration_computed', False),
                'interpretation': {
                    'brier_score_range': '[0, 1], 0 = perfeito',
                    'log_loss_range': '[0, ∞), 0 = perfeito',
                    'thresholds': {
                        'excellent': 'brier_score <= 0.15',
                        'good': 'brier_score <= 0.25',
                        'fair': 'brier_score <= 0.35',
                        'poor': 'brier_score > 0.35'
                    }
                }
            }
            mlflow.log_dict(calibration_report, "calibration_report.json")

            # Verificar se a versão foi criada com sucesso
            client = mlflow.tracking.MlflowClient()
            current_run_id = mlflow.active_run().info.run_id
            versions = client.search_model_versions(f"name='{model_name}'")

            # Encontrar versão associada ao run atual
            for v in versions:
                if v.run_id == current_run_id:
                    registered_version = v.version
                    model_registered = True
                    break

            if model_registered:
                print(f"   ✅ Model registered as {model_name} v{registered_version} with explicit signature")
                print(f"   📋 Feature schema: {len(feature_names)} features")
                print(f"   📊 Output type: {'probabilistic (predict_proba)' if supports_proba else 'discrete (predict)'}")
            else:
                logger.warning(
                    "model_version_not_found_for_run",
                    model_name=model_name,
                    run_id=current_run_id,
                    reason="Model logged but version not found in registry"
                )
                print(f"   ⚠️  Model logged but version not found in registry for run {current_run_id}")

        except Exception as e:
            logger.error(
                "model_registration_failed",
                model_name=model_name,
                error=str(e),
                error_type=type(e).__name__
            )
            print(f"   ❌ Model registration failed: {e}")

            # Logar modelo sem registro apenas para debugging (não para promoção)
            try:
                mlflow.sklearn.log_model(
                    sk_model=model,
                    artifact_path="model_unregistered"
                )
                print(f"   ⚠️  Model logged as unregistered artifact for debugging only")
            except Exception as e2:
                logger.error("fallback_model_logging_failed", error=str(e2))

            # Marcar que o modelo não foi registrado
            model_registered = False

        run_id = mlflow.active_run().info.run_id
        model_uri = f"runs:/{run_id}/model"

        # 8. Comparar com baseline e promover
        if args.promote_if_better == 'true':
            print(f"🔍 Checking if model should be promoted...")

            # Verificar se o modelo foi registrado com sucesso antes de tentar promover
            if not model_registered:
                logger.warning(
                    "skipping_promotion_model_not_registered",
                    model_name=model_name,
                    reason="Model was not successfully registered, skipping promotion"
                )
                print(f"   ⚠️  Skipping promotion - model was not successfully registered")
                mlflow.log_param('promoted', 'false')
                mlflow.log_param('promotion_skip_reason', 'model_not_registered')
            else:
                baseline_model, baseline_metrics = get_baseline_model(args.specialist_type, registry_entry)

                # Passar baseline_metrics diretamente (pode ser None se não há baseline)
                if should_promote_model(metrics, baseline_metrics):
                    print(f"✅ Promoting model to {model_stage}...")

                    client = mlflow.tracking.MlflowClient()
                    current_run_id = mlflow.active_run().info.run_id

                    # Buscar versões e verificar que temos uma versão associada ao run atual
                    versions = client.search_model_versions(f"name='{model_name}'")

                    # Encontrar a versão do run atual (não usar max, que poderia pegar versão antiga)
                    version_to_promote = None
                    for v in versions:
                        if v.run_id == current_run_id:
                            version_to_promote = v.version
                            break

                    if version_to_promote is None:
                        logger.error(
                            "no_version_found_for_current_run",
                            model_name=model_name,
                            run_id=current_run_id,
                            available_versions=[v.version for v in versions]
                        )
                        print(f"   ❌ Error: No model version found for current run {current_run_id}")
                        mlflow.log_param('promoted', 'false')
                        mlflow.log_param('promotion_skip_reason', 'version_not_found_for_run')
                    else:
                        # Arquivar versões anteriores no stage alvo
                        archived_versions = []
                        for v in versions:
                            if v.current_stage == model_stage and v.version != version_to_promote:
                                client.transition_model_version_stage(
                                    name=model_name,
                                    version=v.version,
                                    stage='Archived',
                                    archive_existing_versions=False
                                )
                                archived_versions.append(v.version)
                                print(f"   📦 Archived previous version v{v.version}")

                        # Promover para o stage configurado
                        client.transition_model_version_stage(
                            name=model_name,
                            version=version_to_promote,
                            stage=model_stage,
                            archive_existing_versions=False  # Já arquivamos manualmente
                        )

                        mlflow.log_param('promoted', 'true')
                        mlflow.log_param('promoted_version', version_to_promote)
                        mlflow.log_param('archived_versions', str(archived_versions))
                        print(f"   Model version {version_to_promote} promoted to {model_stage}")
                        if archived_versions:
                            print(f"   📋 Archived versions: {archived_versions}")
                else:
                    print(f"ℹ️  Model kept in Staging - performance below threshold or did not improve over baseline")
                    mlflow.log_param('promoted', 'false')
                    mlflow.log_param('promotion_skip_reason', 'metrics_below_threshold')

        # Calcular duração do treinamento
        training_end_time = datetime.utcnow()
        training_duration_seconds = (training_end_time - training_start_time).total_seconds()

        # Audit log: training_completed
        if audit_logger and _MODEL_AUDIT_LOGGER_AVAILABLE:
            completion_context = AuditEventContext(
                user_id='training_pipeline',
                reason='Treinamento concluído com sucesso',
                duration_seconds=training_duration_seconds,
                environment=environment,
                triggered_by='scheduled' if args.feedback_count > 0 else 'manual',
                metadata={
                    'mlflow_run_id': mlflow.active_run().info.run_id,
                    'data_source': data_source,
                    'promoted': 'true' if args.promote_if_better == 'true' and model_registered else 'false'
                }
            )
            loop.run_until_complete(log_audit_event(
                audit_logger,
                'log_training_completed',
                model_name=model_name,
                model_version=model_version,
                context=completion_context,
                metrics={
                    'precision': metrics.get('precision', 0.0),
                    'recall': metrics.get('recall', 0.0),
                    'f1': metrics.get('f1', 0.0),
                    'accuracy': metrics.get('accuracy', 0.0),
                    'brier_score': metrics.get('brier_score'),
                    'log_loss': metrics.get('log_loss'),
                    'calibration_quality': metrics.get('calibration_quality', 'unknown')
                }
            ))
            logger.info(
                'audit_log_training_completed',
                model_name=model_name,
                model_version=model_version,
                duration_seconds=training_duration_seconds
            )

        print()
        print(f"✅ Retraining pipeline completed")
        print(f"   Run ID: {mlflow.active_run().info.run_id}")


if __name__ == '__main__':
    main()
