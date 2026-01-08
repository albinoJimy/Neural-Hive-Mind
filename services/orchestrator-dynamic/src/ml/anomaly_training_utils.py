"""
Utilitários para preparação de dados de treinamento do AnomalyDetector.

Funções para preparação de dados, geração de anomalias sintéticas,
e validação de dados para treinamento de modelos de detecção de anomalias.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from sklearn.model_selection import train_test_split

import structlog

logger = structlog.get_logger(__name__)


def prepare_anomaly_training_data(
    df: pd.DataFrame,
    label_column: str = 'is_anomaly',
    features_to_use: Optional[List[str]] = None,
    synthetic_ratio: float = 0.1
) -> Tuple[pd.DataFrame, pd.DataFrame, np.ndarray, np.ndarray]:
    """
    Prepara dados para treinamento do AnomalyDetector.

    Extrai features relevantes, aplica labeling heurístico se necessário,
    e gera anomalias sintéticas para balanceamento.

    Args:
        df: DataFrame com tickets históricos
        label_column: Nome da coluna de label (ou criada se não existir)
        features_to_use: Lista de features a usar (None = auto-select)
        synthetic_ratio: Ratio de anomalias sintéticas a adicionar

    Returns:
        Tuple (X_train, X_test, y_train, y_test)
    """
    if df.empty:
        logger.warning("empty_dataframe_for_anomaly_training")
        return pd.DataFrame(), pd.DataFrame(), np.array([]), np.array([])

    df_work = df.copy()

    # Auto-selecionar features se não especificadas
    if features_to_use is None:
        features_to_use = _get_default_anomaly_features()

    # Filtrar features disponíveis
    available_features = [f for f in features_to_use if f in df_work.columns]

    if len(available_features) < 3:
        logger.warning(
            "insufficient_features_for_anomaly_training",
            available=available_features,
            required=features_to_use
        )
        # Tentar criar features derivadas
        df_work = _create_derived_features(df_work)
        available_features = [f for f in features_to_use if f in df_work.columns]

    # Aplicar labeling heurístico se label não existir
    if label_column not in df_work.columns:
        df_work[label_column] = _apply_heuristic_labels(df_work)

    # Gerar anomalias sintéticas para balanceamento
    if synthetic_ratio > 0:
        df_work = _add_synthetic_anomalies(df_work, available_features, synthetic_ratio)

    # Remover linhas com NaN nas features
    df_clean = df_work.dropna(subset=available_features)

    if len(df_clean) < 100:
        logger.warning(
            "insufficient_samples_after_cleaning",
            original=len(df),
            cleaned=len(df_clean)
        )

    # Separar features e labels
    X = df_clean[available_features]
    y = df_clean[label_column].astype(int)

    # Split train/test com estratificação
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y,
            test_size=0.2,
            random_state=42,
            stratify=y
        )
    except ValueError:
        # Se estratificação falhar (poucas amostras de uma classe)
        X_train, X_test, y_train, y_test = train_test_split(
            X, y,
            test_size=0.2,
            random_state=42
        )

    logger.info(
        "anomaly_training_data_prepared",
        total_samples=len(df_clean),
        train_samples=len(X_train),
        test_samples=len(X_test),
        features_used=len(available_features),
        anomaly_ratio=y.mean()
    )

    return X_train, X_test, y_train.values, y_test.values


def _get_default_anomaly_features() -> List[str]:
    """Retorna lista de features padrão para detecção de anomalias."""
    return [
        # Timing features
        'actual_duration_ms',
        'estimated_duration_ms',
        'queue_wait_ms',
        'duration_deviation',  # derivada

        # Resource features
        'resource_cpu',
        'resource_memory',
        'capabilities_count',
        'parameters_size',

        # Contextual features
        'retry_count',
        'sla_timeout_ms',
        'hour_of_day',
        'day_of_week',

        # Derived features
        'duration_ratio',  # actual/estimated
        'sla_utilization',  # duration/sla_timeout
    ]


def _create_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """Cria features derivadas úteis para detecção de anomalias."""
    df = df.copy()

    # Duration ratio (actual/estimated)
    if 'actual_duration_ms' in df.columns and 'estimated_duration_ms' in df.columns:
        estimated = df['estimated_duration_ms'].replace(0, 60000)  # default 60s
        df['duration_ratio'] = df['actual_duration_ms'] / estimated

    # Duration deviation (z-score simplificado por task_type)
    if 'actual_duration_ms' in df.columns and 'task_type' in df.columns:
        df['duration_deviation'] = df.groupby('task_type')['actual_duration_ms'].transform(
            lambda x: (x - x.mean()) / (x.std() + 1e-6)
        )
    elif 'actual_duration_ms' in df.columns:
        mean_dur = df['actual_duration_ms'].mean()
        std_dur = df['actual_duration_ms'].std() + 1e-6
        df['duration_deviation'] = (df['actual_duration_ms'] - mean_dur) / std_dur

    # SLA utilization
    if 'actual_duration_ms' in df.columns and 'sla_timeout_ms' in df.columns:
        sla = df['sla_timeout_ms'].replace(0, 300000)  # default 5min
        df['sla_utilization'] = df['actual_duration_ms'] / sla

    # Temporal features
    if 'created_at' in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df['created_at']):
            df['hour_of_day'] = df['created_at'].dt.hour
            df['day_of_week'] = df['created_at'].dt.dayofweek
        elif df['created_at'].dtype == object:
            try:
                dt_col = pd.to_datetime(df['created_at'])
                df['hour_of_day'] = dt_col.dt.hour
                df['day_of_week'] = dt_col.dt.dayofweek
            except Exception:
                df['hour_of_day'] = 12
                df['day_of_week'] = 0

    # Default values para features faltantes
    if 'queue_wait_ms' not in df.columns:
        df['queue_wait_ms'] = 0.0

    if 'retry_count' not in df.columns:
        df['retry_count'] = 0

    if 'capabilities_count' not in df.columns:
        if 'required_capabilities' in df.columns:
            df['capabilities_count'] = df['required_capabilities'].apply(
                lambda x: len(x) if isinstance(x, list) else 1
            )
        else:
            df['capabilities_count'] = 1

    if 'parameters_size' not in df.columns:
        if 'parameters' in df.columns:
            df['parameters_size'] = df['parameters'].apply(
                lambda x: len(str(x)) if x else 0
            )
        else:
            df['parameters_size'] = 0

    return df


def _apply_heuristic_labels(df: pd.DataFrame) -> np.ndarray:
    """
    Aplica labeling heurístico para identificar anomalias.

    Heurísticas:
    - Duration > 3x média do task_type
    - Retry count >= 3
    - SLA utilization > 0.95
    - Status FAILED
    - Duration deviation > 3 (z-score)
    """
    n = len(df)
    labels = np.zeros(n, dtype=int)

    # Heurística 1: Duration muito alta (>3x média por task_type)
    if 'actual_duration_ms' in df.columns and 'task_type' in df.columns:
        task_means = df.groupby('task_type')['actual_duration_ms'].transform('mean')
        labels = np.where(df['actual_duration_ms'] > 3 * task_means, 1, labels)
    elif 'actual_duration_ms' in df.columns:
        mean_dur = df['actual_duration_ms'].mean()
        labels = np.where(df['actual_duration_ms'] > 3 * mean_dur, 1, labels)

    # Heurística 2: Muitos retries
    if 'retry_count' in df.columns:
        labels = np.where(df['retry_count'] >= 3, 1, labels)

    # Heurística 3: SLA quase estourado
    if 'sla_utilization' in df.columns:
        labels = np.where(df['sla_utilization'] > 0.95, 1, labels)
    elif 'actual_duration_ms' in df.columns and 'sla_timeout_ms' in df.columns:
        sla = df['sla_timeout_ms'].replace(0, 300000)
        util = df['actual_duration_ms'] / sla
        labels = np.where(util > 0.95, 1, labels)

    # Heurística 4: Falha
    if 'status' in df.columns:
        labels = np.where(df['status'] == 'FAILED', 1, labels)

    # Heurística 5: Duration deviation alta
    if 'duration_deviation' in df.columns:
        labels = np.where(abs(df['duration_deviation']) > 3, 1, labels)

    anomaly_count = labels.sum()
    anomaly_ratio = anomaly_count / n if n > 0 else 0

    logger.info(
        "heuristic_labels_applied",
        total=n,
        anomalies=anomaly_count,
        anomaly_ratio=round(anomaly_ratio, 4)
    )

    return labels


def _add_synthetic_anomalies(
    df: pd.DataFrame,
    features: List[str],
    ratio: float
) -> pd.DataFrame:
    """
    Gera anomalias sintéticas para balanceamento do dataset.

    Estratégias:
    - Perturbação de valores normais (3-5x desvio padrão)
    - Combinações de features extremas
    - Outliers baseados em IQR
    """
    if ratio <= 0:
        return df

    n_synthetic = int(len(df) * ratio)
    if n_synthetic == 0:
        return df

    df_work = df.copy()

    # Garantir que features existem
    available_features = [f for f in features if f in df_work.columns]
    if not available_features:
        return df

    # Estatísticas das features
    means = {}
    stds = {}
    for f in available_features:
        col = pd.to_numeric(df_work[f], errors='coerce')
        means[f] = col.mean()
        stds[f] = col.std()

    # Gerar amostras sintéticas
    synthetic_rows = []
    np.random.seed(42)

    for _ in range(n_synthetic):
        # Selecionar linha base aleatória
        base_idx = np.random.randint(0, len(df_work))
        row = df_work.iloc[base_idx].to_dict()

        # Perturbar 2-4 features
        n_perturb = np.random.randint(2, min(5, len(available_features) + 1))
        features_to_perturb = np.random.choice(available_features, n_perturb, replace=False)

        for f in features_to_perturb:
            if f not in means or pd.isna(means[f]) or stds[f] == 0:
                continue

            # Perturbar com 3-5 desvios padrão
            direction = np.random.choice([-1, 1])
            magnitude = np.random.uniform(3, 5)
            row[f] = means[f] + direction * magnitude * stds[f]

            # Garantir valores não negativos para features apropriadas
            if f.endswith('_ms') or f.endswith('_count') or f == 'retry_count':
                row[f] = max(0, row[f])

        # Marcar como anomalia
        row['is_anomaly'] = 1
        synthetic_rows.append(row)

    # Adicionar ao DataFrame
    df_synthetic = pd.DataFrame(synthetic_rows)
    df_augmented = pd.concat([df_work, df_synthetic], ignore_index=True)

    logger.info(
        "synthetic_anomalies_added",
        original_samples=len(df),
        synthetic_samples=n_synthetic,
        total_samples=len(df_augmented)
    )

    return df_augmented


def compute_anomaly_features_from_ticket(ticket: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """
    Extrai features de anomalia de um único ticket.

    Args:
        ticket: Dict com dados do ticket

    Returns:
        Dict com features ou None se impossível extrair
    """
    try:
        features = {}

        # Timing
        features['actual_duration_ms'] = float(ticket.get('actual_duration_ms', 60000))
        features['estimated_duration_ms'] = float(ticket.get('estimated_duration_ms', 60000))

        # Duration ratio
        est = features['estimated_duration_ms'] if features['estimated_duration_ms'] > 0 else 60000
        features['duration_ratio'] = features['actual_duration_ms'] / est

        # Queue wait
        features['queue_wait_ms'] = float(ticket.get('queue_wait_ms', 0))

        # Resources
        features['resource_cpu'] = float(ticket.get('resource_cpu', 0.5))
        features['resource_memory'] = float(ticket.get('resource_memory', 512))

        # Counts
        caps = ticket.get('required_capabilities', [])
        features['capabilities_count'] = len(caps) if isinstance(caps, list) else 1

        params = ticket.get('parameters', {})
        features['parameters_size'] = len(str(params)) if params else 0

        features['retry_count'] = int(ticket.get('retry_count', 0))

        # SLA
        sla = float(ticket.get('sla_timeout_ms', 300000))
        features['sla_timeout_ms'] = sla
        features['sla_utilization'] = features['actual_duration_ms'] / sla if sla > 0 else 1.0

        # Temporal
        created_at = ticket.get('created_at')
        if created_at:
            if isinstance(created_at, datetime):
                features['hour_of_day'] = created_at.hour
                features['day_of_week'] = created_at.weekday()
            else:
                try:
                    dt = pd.to_datetime(created_at)
                    features['hour_of_day'] = dt.hour
                    features['day_of_week'] = dt.weekday()
                except Exception:
                    features['hour_of_day'] = 12
                    features['day_of_week'] = 0
        else:
            features['hour_of_day'] = 12
            features['day_of_week'] = 0

        return features

    except Exception as e:
        logger.warning("anomaly_feature_extraction_failed", error=str(e))
        return None


def validate_anomaly_training_data(
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    min_samples: int = 100,
    min_anomaly_ratio: float = 0.01,
    max_anomaly_ratio: float = 0.5
) -> Tuple[bool, List[str]]:
    """
    Valida dados de treinamento para AnomalyDetector.

    Args:
        X_train: Features de treino
        y_train: Labels de treino
        min_samples: Mínimo de amostras
        min_anomaly_ratio: Ratio mínimo de anomalias
        max_anomaly_ratio: Ratio máximo de anomalias

    Returns:
        Tuple (is_valid, list of issues)
    """
    issues = []

    # Check tamanho
    if len(X_train) < min_samples:
        issues.append(f"Insufficient samples: {len(X_train)} < {min_samples}")

    # Check anomaly ratio
    if len(y_train) > 0:
        anomaly_ratio = y_train.mean()
        if anomaly_ratio < min_anomaly_ratio:
            issues.append(f"Low anomaly ratio: {anomaly_ratio:.4f} < {min_anomaly_ratio}")
        if anomaly_ratio > max_anomaly_ratio:
            issues.append(f"High anomaly ratio: {anomaly_ratio:.4f} > {max_anomaly_ratio}")

    # Check NaN
    nan_cols = X_train.columns[X_train.isna().any()].tolist()
    if nan_cols:
        issues.append(f"Columns with NaN: {nan_cols}")

    # Check variance
    low_var_cols = []
    for col in X_train.columns:
        if X_train[col].std() < 1e-10:
            low_var_cols.append(col)
    if low_var_cols:
        issues.append(f"Low variance columns: {low_var_cols}")

    is_valid = len(issues) == 0

    if not is_valid:
        logger.warning(
            "anomaly_training_data_validation_failed",
            issues=issues
        )
    else:
        logger.info("anomaly_training_data_validation_passed")

    return is_valid, issues
