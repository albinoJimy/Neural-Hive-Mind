"""
Temporal Split Validator - Neural Hive-Mind ML Pipelines

Valida splits temporais para prevenir data leakage em pipelines de ML.
Garante que dados de treino, validação e teste estejam em ordem cronológica correta.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any, Union
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TemporalSplitValidation:
    """Resultado da validação temporal de splits."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    train_time_range: Optional[tuple] = None
    val_time_range: Optional[tuple] = None
    test_time_range: Optional[tuple] = None
    gaps_detected: List[Dict[str, Any]] = None
    overlaps_detected: List[Dict[str, Any]] = None


class TemporalSplitValidator:
    """
    Validador de splits temporais para prevenir data leakage.
    
    Garante:
    1. Ordem cronológica: train < val < test
    2. Sem overlap entre splits
    3. Gaps mínimos entre splits
    4. Cobertura temporal adequada
    
    Example:
        validator = TemporalSplitValidator(min_gap_hours=1)
        
        # Validar DataFrames
        result = validator.validate_splits(
            train_df=train_data,
            val_df=val_data,
            test_df=test_data,
            timestamp_column="timestamp"
        )
        
        if not result.is_valid:
            raise ValueError(f"Invalid temporal splits: {result.errors}")
    """
    
    def __init__(
        self,
        min_gap_hours: float = 1.0,
        min_train_days: float = 30.0,
        max_future_data_hours: float = 0.0,
        strict_mode: bool = True
    ):
        """
        Inicializa o validador.
        
        Args:
            min_gap_hours: Gap mínimo em horas entre splits
            min_train_days: Dias mínimos de dados de treino
            max_future_data_hours: Horas máximas no futuro permitidas
            strict_mode: Se True, falha em warnings também
        """
        self.min_gap_hours = min_gap_hours
        self.min_train_days = min_train_days
        self.max_future_data_hours = max_future_data_hours
        self.strict_mode = strict_mode
    
    def validate_splits(
        self,
        train_data: Union[pd.DataFrame, List[datetime]],
        val_data: Union[pd.DataFrame, List[datetime]],
        test_data: Union[pd.DataFrame, List[datetime]],
        timestamp_column: str = "timestamp"
    ) -> TemporalSplitValidation:
        """
        Valida splits temporais.
        
        Args:
            train_data: Dados de treino (DataFrame ou lista de timestamps)
            val_data: Dados de validação
            test_data: Dados de teste
            timestamp_column: Nome da coluna de timestamp
            
        Returns:
            TemporalSplitValidation com resultado da validação
        """
        errors = []
        warnings = []
        gaps_detected = []
        overlaps_detected = []
        
        # Extrair timestamps
        train_timestamps = self._extract_timestamps(train_data, timestamp_column)
        val_timestamps = self._extract_timestamps(val_data, timestamp_column)
        test_timestamps = self._extract_timestamps(test_data, timestamp_column)
        
        # Verificar se há dados
        if not train_timestamps:
            errors.append("Train split está vazio")
        if not val_timestamps:
            errors.append("Validation split está vazio")
        if not test_timestamps:
            errors.append("Test split está vazio")
        
        if errors:
            return TemporalSplitValidation(
                is_valid=False,
                errors=errors,
                warnings=warnings,
                gaps_detected=gaps_detected,
                overlaps_detected=overlaps_detected
            )
        
        # Calcular ranges
        train_min, train_max = min(train_timestamps), max(train_timestamps)
        val_min, val_max = min(val_timestamps), max(val_timestamps)
        test_min, test_max = min(test_timestamps), max(test_timestamps)
        
        train_time_range = (train_min, train_max)
        val_time_range = (val_min, val_max)
        test_time_range = (test_min, test_max)
        
        # Validação 1: Ordem cronológica correta
        if train_max >= val_min:
            error_msg = (
                f"Data leakage detectado: train_max ({train_max}) >= val_min ({val_min}). "
                f"Dados de treino não podem ser posteriores ou iguais à validação."
            )
            errors.append(error_msg)
            overlaps_detected.append({
                "type": "train_val_overlap",
                "train_end": train_max,
                "val_start": val_min,
                "overlap_hours": (train_max - val_min).total_seconds() / 3600
            })
        
        if val_max >= test_min:
            error_msg = (
                f"Data leakage detectado: val_max ({val_max}) >= test_min ({test_min}). "
                f"Dados de validação não podem ser posteriores ou iguais ao teste."
            )
            errors.append(error_msg)
            overlaps_detected.append({
                "type": "val_test_overlap",
                "val_end": val_max,
                "test_start": test_min,
                "overlap_hours": (val_max - test_min).total_seconds() / 3600
            })
        
        # Validação 2: Gap mínimo entre splits
        gap_train_val = (val_min - train_max).total_seconds() / 3600
        if gap_train_val < self.min_gap_hours:
            warning_msg = (
                f"Gap muito pequeno entre train e val: {gap_train_val:.2f}h "
                f"(mínimo recomendado: {self.min_gap_hours}h)"
            )
            if self.strict_mode:
                errors.append(warning_msg)
            else:
                warnings.append(warning_msg)
            gaps_detected.append({
                "type": "small_gap_train_val",
                "gap_hours": gap_train_val,
                "recommended_hours": self.min_gap_hours
            })
        
        gap_val_test = (test_min - val_max).total_seconds() / 3600
        if gap_val_test < self.min_gap_hours:
            warning_msg = (
                f"Gap muito pequeno entre val e test: {gap_val_test:.2f}h "
                f"(mínimo recomendado: {self.min_gap_hours}h)"
            )
            if self.strict_mode:
                errors.append(warning_msg)
            else:
                warnings.append(warning_msg)
            gaps_detected.append({
                "type": "small_gap_val_test",
                "gap_hours": gap_val_test,
                "recommended_hours": self.min_gap_hours
            })
        
        # Validação 3: Tamanho mínimo do treino
        train_duration_days = (train_max - train_min).total_seconds() / (24 * 3600)
        if train_duration_days < self.min_train_days:
            warning_msg = (
                f"Dados de treino muito curtos: {train_duration_days:.1f} dias "
                f"(mínimo recomendado: {self.min_train_days} dias)"
            )
            if self.strict_mode:
                errors.append(warning_msg)
            else:
                warnings.append(warning_msg)
        
        # Validação 4: Dados no futuro
        now = datetime.utcnow()
        if train_max > now:
            hours_in_future = (train_max - now).total_seconds() / 3600
            if hours_in_future > self.max_future_data_hours:
                errors.append(
                    f"Train contém dados {hours_in_future:.1f}h no futuro"
                )
        
        if val_max > now:
            hours_in_future = (val_max - now).total_seconds() / 3600
            if hours_in_future > self.max_future_data_hours:
                errors.append(
                    f"Validation contém dados {hours_in_future:.1f}h no futuro"
                )
        
        if test_max > now:
            hours_in_future = (test_max - now).total_seconds() / 3600
            if hours_in_future > self.max_future_data_hours:
                errors.append(
                    f"Test contém dados {hours_in_future:.1f}h no futuro"
                )
        
        # Validação 5: Ordenação interna
        if not all(train_timestamps[i] <= train_timestamps[i+1] 
                   for i in range(len(train_timestamps)-1)):
            warnings.append("Train data não está ordenado cronologicamente")
        
        is_valid = len(errors) == 0
        
        if is_valid:
            logger.info(
                "temporal_validation_passed",
                train_days=train_duration_days,
                train_val_gap_hours=gap_train_val,
                val_test_gap_hours=gap_val_test
            )
        else:
            logger.error(
                "temporal_validation_failed",
                errors=errors,
                overlaps=overlaps_detected,
                gaps=gaps_detected
            )
        
        return TemporalSplitValidation(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            train_time_range=train_time_range,
            val_time_range=val_time_range,
            test_time_range=test_time_range,
            gaps_detected=gaps_detected or [],
            overlaps_detected=overlaps_detected or []
        )
    
    def _extract_timestamps(
        self,
        data: Union[pd.DataFrame, List[datetime]],
        timestamp_column: str
    ) -> List[datetime]:
        """Extrai lista de timestamps dos dados."""
        if isinstance(data, pd.DataFrame):
            if timestamp_column not in data.columns:
                raise ValueError(f"Coluna '{timestamp_column}' não encontrada no DataFrame")
            return data[timestamp_column].tolist()
        elif isinstance(data, list):
            return data
        else:
            raise ValueError(f"Tipo de dados não suportado: {type(data)}")
    
    def validate_no_data_leakage(
        self,
        train_features: pd.DataFrame,
        train_labels: pd.Series,
        val_features: pd.DataFrame,
        val_labels: pd.Series,
        test_features: pd.DataFrame,
        test_labels: pd.Series,
        timestamp_column: str = "timestamp",
        entity_id_column: Optional[str] = None
    ) -> TemporalSplitValidation:
        """
        Valida que não há data leakage entre features e labels.
        
        Args:
            train_features: Features de treino
            train_labels: Labels de treino
            val_features: Features de validação
            val_labels: Labels de validação
            test_features: Features de teste
            test_labels: Labels de teste
            timestamp_column: Coluna de timestamp
            entity_id_column: Coluna de ID de entidade (opcional)
            
        Returns:
            TemporalSplitValidation com resultado
        """
        # Combinar features e labels para validação temporal
        train_data = train_features.copy()
        train_data['__label__'] = train_labels
        
        val_data = val_features.copy()
        val_data['__label__'] = val_labels
        
        test_data = test_features.copy()
        test_data['__label__'] = test_labels
        
        # Validar splits temporais
        result = self.validate_splits(
            train_data=train_data,
            val_data=val_data,
            test_data=test_data,
            timestamp_column=timestamp_column
        )
        
        # Validação adicional: verificar se entidades não se misturam
        if entity_id_column and entity_id_column in train_features.columns:
            train_entities = set(train_features[entity_id_column].unique())
            val_entities = set(val_features[entity_id_column].unique())
            test_entities = set(test_features[entity_id_column].unique())
            
            # Entidades podem aparecer em múltiplos splits, mas não deve haver
            # overlap temporal das mesmas entidades
            train_val_entities = train_entities.intersection(val_entities)
            train_test_entities = train_entities.intersection(test_entities)
            val_test_entities = val_entities.intersection(test_entities)
            
            if train_val_entities:
                result.warnings.append(
                    f"{len(train_val_entities)} entidades aparecem em train e val. "
                    "Verificar que não há overlap temporal."
                )
            
            if train_test_entities:
                result.warnings.append(
                    f"{len(train_test_entities)} entidades aparecem em train e test. "
                    "Verificar que não há overlap temporal."
                )
            
            if val_test_entities:
                result.warnings.append(
                    f"{len(val_test_entities)} entidades aparecem em val e test. "
                    "Verificar que não há overlap temporal."
                )
        
        return result


def create_time_based_splits(
    df: pd.DataFrame,
    timestamp_column: str = "timestamp",
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    gap_hours: float = 1.0
) -> Dict[str, pd.DataFrame]:
    """
    Cria splits temporais ordenados com gaps.
    
    Args:
        df: DataFrame com dados
        timestamp_column: Nome da coluna de timestamp
        train_ratio: Proporção de dados para treino
        val_ratio: Proporção de dados para validação
        test_ratio: Proporção de dados para teste
        gap_hours: Gap em horas entre splits
        
    Returns:
        Dicionário com train, val, test DataFrames
        
    Example:
        splits = create_time_based_splits(
            df=data,
            timestamp_column="created_at",
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
            gap_hours=1.0
        )
        train_df = splits["train"]
        val_df = splits["val"]
        test_df = splits["test"]
    """
    if abs(train_ratio + val_ratio + test_ratio - 1.0) > 0.01:
        raise ValueError("Ratios devem somar 1.0")
    
    # Ordenar por timestamp
    df_sorted = df.sort_values(by=timestamp_column).reset_index(drop=True)
    
    n_samples = len(df_sorted)
    n_train = int(n_samples * train_ratio)
    n_val = int(n_samples * val_ratio)
    
    # Calcular timestamps de corte
    train_end_idx = n_train
    val_start_time = df_sorted.iloc[train_end_idx][timestamp_column]
    
    # Aplicar gap
    gap_timedelta = pd.Timedelta(hours=gap_hours)
    val_start_time_with_gap = val_start_time + gap_timedelta
    
    # Encontrar índice onde validação começa (após gap)
    val_start_idx = df_sorted[df_sorted[timestamp_column] >= val_start_time_with_gap].index.min()
    if pd.isna(val_start_idx):
        val_start_idx = train_end_idx
    
    val_end_idx = min(val_start_idx + n_val, n_samples - 1)
    test_start_time = df_sorted.iloc[val_end_idx][timestamp_column]
    test_start_time_with_gap = test_start_time + gap_timedelta
    
    test_start_idx = df_sorted[df_sorted[timestamp_column] >= test_start_time_with_gap].index.min()
    if pd.isna(test_start_idx):
        test_start_idx = val_end_idx
    
    # Criar splits
    train_df = df_sorted.iloc[:train_end_idx].copy()
    val_df = df_sorted.iloc[val_start_idx:val_end_idx].copy()
    test_df = df_sorted.iloc[test_start_idx:].copy()
    
    logger.info(
        "splits_created",
        train_samples=len(train_df),
        val_samples=len(val_df),
        test_samples=len(test_df),
        train_start=train_df[timestamp_column].min(),
        train_end=train_df[timestamp_column].max(),
        val_start=val_df[timestamp_column].min(),
        val_end=val_df[timestamp_column].max(),
        test_start=test_df[timestamp_column].min(),
        test_end=test_df[timestamp_column].max()
    )
    
    return {
        "train": train_df,
        "val": val_df,
        "test": test_df
    }


# Instância padrão para uso conveniente
default_validator = TemporalSplitValidator()


def validate_temporal_splits(*args, **kwargs) -> TemporalSplitValidation:
    """Função helper usando validador padrão."""
    return default_validator.validate_splits(*args, **kwargs)
