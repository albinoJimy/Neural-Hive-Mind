#!/usr/bin/env python3
"""
RealDataCollector: Coleta e prepara dados reais do ledger cognitivo para treinamento ML.

Este módulo busca opiniões do specialist_opinions, enriquece com feedback humano
do specialist_feedback, extrai features usando FeatureExtractor e prepara datasets
validados para treinamento de modelos de especialistas.

Diferencia-se de dados sintéticos por:
- Usar opiniões reais do sistema em produção
- Incorporar feedback humano para labels
- Aplicar splits temporais (não aleatórios) para evitar data leakage
- Validar distribuição e qualidade dos dados
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
import structlog
import pandas as pd
import numpy as np
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection

# Adicionar paths para imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'libraries' / 'python'))

# Importar schema de features centralizado
from feature_store.feature_definitions import get_feature_names

# Importar FeatureExtractor
try:
    from neural_hive_specialists.feature_extraction.feature_extractor import FeatureExtractor
    _FEATURE_EXTRACTOR_AVAILABLE = True
except ImportError:
    _FEATURE_EXTRACTOR_AVAILABLE = False

# Circuit breaker para resiliência
try:
    import pybreaker
    _PYBREAKER_AVAILABLE = True
except ImportError:
    _PYBREAKER_AVAILABLE = False

logger = structlog.get_logger(__name__)


class InsufficientDataError(Exception):
    """Dados reais insuficientes para treinamento."""
    pass


class DataQualityError(Exception):
    """Qualidade dos dados abaixo do threshold aceitável."""
    pass


class FeatureExtractionError(Exception):
    """Erro na extração de features."""
    pass


class RealDataCollector:
    """
    Coleta dados reais do ledger cognitivo para treinamento de modelos ML.

    Integra com:
    - specialist_opinions: Opiniões geradas pelos especialistas
    - specialist_feedback: Feedback humano sobre as opiniões
    - FeatureExtractor: Extração de features padronizadas
    """

    # Baseline de distribuição de labels
    # Nota: Alinhado com FeedbackDocument schema que aceita apenas:
    # approve, reject, review_required
    BASELINE_DISTRIBUTION = {
        1: 50.0,  # approve
        0: 25.0,  # reject
        2: 25.0   # review_required
    }

    # Mapeamento de recomendações para labels
    # Nota: Valores válidos definidos em FeedbackDocument.validate_recommendation()
    RECOMMENDATION_TO_LABEL = {
        "approve": 1,
        "reject": 0,
        "review_required": 2
    }

    def __init__(
        self,
        mongodb_uri: str = None,
        mongodb_database: str = "neural_hive",
        opinions_collection_name: str = None,
        feedback_collection_name: str = None
    ):
        """
        Inicializa o coletor de dados reais.

        Args:
            mongodb_uri: URI de conexão MongoDB. Default: env MONGODB_URI
            mongodb_database: Nome do database. Default: neural_hive
            opinions_collection_name: Nome da collection de opiniões.
                Default: env OPINIONS_COLLECTION ou 'specialist_opinions'
            feedback_collection_name: Nome da collection de feedback.
                Default: env FEEDBACK_COLLECTION ou 'feedback'
        """
        self.mongodb_uri = mongodb_uri or os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
        self.mongodb_database = mongodb_database
        self.opinions_collection_name = opinions_collection_name or os.getenv(
            'OPINIONS_COLLECTION', 'specialist_opinions'
        )
        self.feedback_collection_name = feedback_collection_name or os.getenv(
            'FEEDBACK_COLLECTION', 'feedback'
        )

        # Conexão MongoDB
        self.mongodb_client: Optional[MongoClient] = None
        self.db: Optional[Database] = None
        self.opinions_collection: Optional[Collection] = None
        self.feedback_collection: Optional[Collection] = None

        # FeatureExtractor
        self.feature_extractor: Optional[FeatureExtractor] = None
        self.expected_feature_names: List[str] = get_feature_names()

        # Circuit breaker para MongoDB
        self._setup_circuit_breaker()

        # Inicializar conexões
        self._connect()

        logger.info(
            "RealDataCollector inicializado",
            mongodb_uri=self._mask_uri(self.mongodb_uri),
            database=self.mongodb_database,
            opinions_collection=self.opinions_collection_name,
            feedback_collection=self.feedback_collection_name,
            feature_extractor_available=_FEATURE_EXTRACTOR_AVAILABLE,
            num_expected_features=len(self.expected_feature_names)
        )

    def _mask_uri(self, uri: str) -> str:
        """Mascara credenciais na URI para logging seguro."""
        if '@' in uri:
            parts = uri.split('@')
            return f"mongodb://***@{parts[-1]}"
        return uri

    def _setup_circuit_breaker(self):
        """Configura circuit breaker para operações MongoDB."""
        if _PYBREAKER_AVAILABLE:
            self.circuit_breaker = pybreaker.CircuitBreaker(
                fail_max=5,
                reset_timeout=60,
                name="mongodb_real_data"
            )
        else:
            self.circuit_breaker = None
            logger.warning(
                "pybreaker não disponível, circuit breaker desabilitado"
            )

    def _connect(self):
        """Estabelece conexão com MongoDB e inicializa FeatureExtractor."""
        try:
            self.mongodb_client = MongoClient(
                self.mongodb_uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000
            )
            # Testar conexão
            self.mongodb_client.admin.command('ping')

            self.db = self.mongodb_client[self.mongodb_database]
            self.opinions_collection = self.db[self.opinions_collection_name]
            self.feedback_collection = self.db[self.feedback_collection_name]

            logger.info("Conexão MongoDB estabelecida")

        except Exception as e:
            logger.error(
                "Falha na conexão MongoDB",
                error=str(e)
            )
            raise

        # Inicializar FeatureExtractor
        if _FEATURE_EXTRACTOR_AVAILABLE:
            try:
                self.feature_extractor = FeatureExtractor()
                logger.info("FeatureExtractor inicializado")
            except Exception as e:
                logger.warning(
                    "Falha ao inicializar FeatureExtractor",
                    error=str(e)
                )
                self.feature_extractor = None
        else:
            logger.warning(
                "FeatureExtractor não disponível para import"
            )

    def _execute_with_breaker(self, func, *args, **kwargs):
        """Executa função com circuit breaker se disponível."""
        if self.circuit_breaker:
            return self.circuit_breaker.call(func, *args, **kwargs)
        return func(*args, **kwargs)

    async def collect_training_data(
        self,
        specialist_type: str,
        days: int = 90,
        min_samples: int = 1000,
        min_feedback_rating: float = 0.0,
        max_extraction_failure_rate: float = 0.05
    ) -> pd.DataFrame:
        """
        Coleta dados de treinamento do ledger cognitivo.

        Args:
            specialist_type: Tipo do especialista (technical, business, etc)
            days: Janela de tempo em dias para buscar opiniões
            min_samples: Mínimo de amostras necessárias
            min_feedback_rating: Rating mínimo de feedback para incluir
            max_extraction_failure_rate: Taxa máxima aceitável de falhas de
                extração de features (0.0-1.0). Default: 0.05 (5%)

        Returns:
            DataFrame com features extraídas e labels

        Raises:
            InsufficientDataError: Se dados insuficientes
            FeatureExtractionError: Se FeatureExtractor não estiver disponível
                ou taxa de falhas exceder o limite
        """
        # Validar que FeatureExtractor está disponível
        if self.feature_extractor is None:
            raise FeatureExtractionError(
                "FeatureExtractor não está disponível. "
                "A extração de features consistente é obrigatória para dados de treinamento. "
                "Verifique se neural_hive_specialists está instalado corretamente."
            )

        logger.info(
            "Iniciando coleta de dados reais",
            specialist_type=specialist_type,
            days=days,
            min_samples=min_samples,
            min_feedback_rating=min_feedback_rating,
            max_extraction_failure_rate=max_extraction_failure_rate
        )

        # 1. Buscar opiniões do ledger cognitivo
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        query = {
            'specialist_type': specialist_type,
            'created_at': {'$gte': cutoff_date}
        }

        projection = {
            'opinion_id': 1,
            'plan_id': 1,
            'specialist_type': 1,
            'recommendation': 1,
            'confidence_score': 1,
            'risk_score': 1,
            'cognitive_plan': 1,
            'created_at': 1
        }

        def fetch_opinions():
            return list(
                self.opinions_collection.find(query, projection)
                .sort('created_at', 1)
            )

        opinions = self._execute_with_breaker(fetch_opinions)

        logger.info(
            "Opiniões encontradas",
            specialist_type=specialist_type,
            count=len(opinions)
        )

        if not opinions:
            raise InsufficientDataError(
                f"Nenhuma opinião encontrada para {specialist_type} nos últimos {days} dias"
            )

        # 2. Enriquecer com feedback humano
        enriched_samples = []
        opinions_with_feedback = 0
        extraction_failures = 0

        for opinion in opinions:
            opinion_id = opinion.get('opinion_id')
            if not opinion_id:
                continue

            # Buscar feedback correspondente (mais recente primeiro)
            def fetch_feedback():
                return self.feedback_collection.find_one(
                    {
                        'opinion_id': opinion_id,
                        'human_rating': {'$gte': min_feedback_rating}
                    },
                    sort=[('submitted_at', -1)]  # Mais recente primeiro
                )

            feedback = self._execute_with_breaker(fetch_feedback)

            if not feedback:
                continue

            opinions_with_feedback += 1

            # 3. Extrair features usando FeatureExtractor
            cognitive_plan = opinion.get('cognitive_plan', {})

            # Extrair features (obrigatório - não usar valores zerados)
            try:
                features_structured = self.feature_extractor.extract_features(cognitive_plan)
                extracted_features = features_structured.get('aggregated_features', {})

                # Inicializar features com valores extraídos
                features = {name: 0.0 for name in self.expected_feature_names}
                for key, value in extracted_features.items():
                    if key in features:
                        features[key] = float(value)

            except Exception as e:
                extraction_failures += 1
                logger.warning(
                    "Falha na extração de features - amostra descartada",
                    opinion_id=opinion_id,
                    error=str(e)
                )
                continue  # Descartar amostra com falha de extração

            # 4. Criar label baseado em feedback humano
            human_recommendation = feedback.get('human_recommendation', '')
            label = self.RECOMMENDATION_TO_LABEL.get(human_recommendation.lower(), -1)

            if label == -1:
                logger.warning(
                    "Recomendação humana desconhecida",
                    opinion_id=opinion_id,
                    human_recommendation=human_recommendation
                )
                continue

            features['label'] = label

            # Metadados para rastreabilidade
            features['opinion_id'] = opinion_id
            features['plan_id'] = opinion.get('plan_id', '')
            features['specialist_type'] = specialist_type
            features['created_at'] = opinion.get('created_at')
            features['human_rating'] = feedback.get('human_rating', 0.0)

            enriched_samples.append(features)

        # Calcular taxas
        coverage_rate = (opinions_with_feedback / len(opinions) * 100) if opinions else 0
        extraction_failure_rate = (
            extraction_failures / opinions_with_feedback
            if opinions_with_feedback > 0 else 0.0
        )

        logger.info(
            "Opiniões enriquecidas com feedback",
            total_opinions=len(opinions),
            with_feedback=opinions_with_feedback,
            extraction_failures=extraction_failures,
            extraction_failure_rate=f"{extraction_failure_rate:.1%}",
            valid_samples=len(enriched_samples),
            coverage_rate=f"{coverage_rate:.1f}%"
        )

        # Verificar taxa de falhas de extração
        if extraction_failure_rate > max_extraction_failure_rate:
            raise FeatureExtractionError(
                f"Taxa de falhas de extração ({extraction_failure_rate:.1%}) excede o limite "
                f"({max_extraction_failure_rate:.1%}). "
                f"{extraction_failures} de {opinions_with_feedback} opiniões falharam na extração. "
                "Verifique a integridade dos cognitive_plan nas opiniões."
            )

        # 5. Validar quantidade mínima
        if len(enriched_samples) < min_samples:
            raise InsufficientDataError(
                f"Dados reais insuficientes para {specialist_type}: "
                f"{len(enriched_samples)} amostras < {min_samples} mínimo. "
                f"Necessário coletar mais feedback humano. "
                f"Taxa de cobertura atual: {coverage_rate:.1f}%"
            )

        # 6. Criar DataFrame
        df = pd.DataFrame(enriched_samples)

        # Validar schema
        missing_features = set(self.expected_feature_names) - set(df.columns)
        if missing_features:
            logger.warning(
                "Features ausentes no DataFrame",
                missing=list(missing_features)
            )

        # Estatísticas
        non_zero_features = sum(
            1 for col in self.expected_feature_names
            if col in df.columns and (df[col] != 0.0).any()
        )

        logger.info(
            "DataFrame de treinamento criado",
            total_samples=len(df),
            total_features=len(self.expected_feature_names),
            non_zero_features=non_zero_features,
            date_range_start=df['created_at'].min() if 'created_at' in df.columns else None,
            date_range_end=df['created_at'].max() if 'created_at' in df.columns else None,
            label_distribution=df['label'].value_counts().to_dict()
        )

        return df

    def validate_label_distribution(
        self,
        df: pd.DataFrame,
        specialist_type: str
    ) -> Dict[str, Any]:
        """
        Valida distribuição de labels comparando com baseline sintético.

        Args:
            df: DataFrame com coluna 'label'
            specialist_type: Tipo do especialista (para logging)

        Returns:
            Relatório de distribuição com warnings se desbalanceado
        """
        if 'label' not in df.columns:
            raise ValueError("DataFrame deve conter coluna 'label'")

        # Calcular distribuição atual
        distribution = df['label'].value_counts().to_dict()
        total = len(df)
        percentages = {
            label: (count / total * 100)
            for label, count in distribution.items()
        }

        # Comparar com baseline
        divergences = {}
        for label, baseline_pct in self.BASELINE_DISTRIBUTION.items():
            real_pct = percentages.get(label, 0.0)
            divergences[label] = abs(real_pct - baseline_pct)

        max_divergence = max(divergences.values()) if divergences else 0.0

        # Detectar desbalanceamento crítico
        warnings = []

        for label, pct in percentages.items():
            if pct < 5.0:
                warnings.append(
                    f"Label {label} representa apenas {pct:.1f}% das amostras (< 5%)"
                )
            if pct > 80.0:
                warnings.append(
                    f"Label {label} domina com {pct:.1f}% das amostras (> 80%)"
                )

        # Labels ausentes
        for label in self.BASELINE_DISTRIBUTION.keys():
            if label not in distribution:
                warnings.append(f"Label {label} ausente nos dados")

        is_balanced = max_divergence < 30.0 and len(warnings) == 0

        if warnings:
            logger.warning(
                "Desbalanceamento detectado na distribuição de labels",
                specialist_type=specialist_type,
                warnings=warnings,
                max_divergence=f"{max_divergence:.1f}%"
            )
        else:
            logger.info(
                "Distribuição de labels validada",
                specialist_type=specialist_type,
                is_balanced=is_balanced
            )

        return {
            'distribution': distribution,
            'percentages': percentages,
            'divergence_from_baseline': divergences,
            'is_balanced': is_balanced,
            'max_divergence': max_divergence,
            'warnings': warnings
        }

    def create_temporal_splits(
        self,
        df: pd.DataFrame,
        train_ratio: float = 0.6,
        val_ratio: float = 0.2,
        test_ratio: float = 0.2
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Cria splits temporais para evitar data leakage.

        Diferente de splits aleatórios, splits temporais garantem que
        dados de treinamento sejam sempre anteriores aos de validação/teste.

        Args:
            df: DataFrame com coluna 'created_at'
            train_ratio: Proporção para treinamento
            val_ratio: Proporção para validação
            test_ratio: Proporção para teste

        Returns:
            Tupla (train_df, val_df, test_df)
        """
        # Validar ratios
        total_ratio = train_ratio + val_ratio + test_ratio
        if abs(total_ratio - 1.0) > 0.001:
            raise ValueError(
                f"Ratios devem somar 1.0, recebido: {total_ratio}"
            )

        # Garantir que created_at existe
        if 'created_at' not in df.columns:
            raise ValueError("DataFrame deve conter coluna 'created_at'")

        # Remover linhas com created_at nulo
        df_clean = df.dropna(subset=['created_at']).copy()

        if len(df_clean) < len(df):
            logger.warning(
                "Linhas removidas por created_at nulo",
                removed=len(df) - len(df_clean)
            )

        # Ordenar por timestamp (mais antigos primeiro)
        df_sorted = df_clean.sort_values('created_at').reset_index(drop=True)

        # Calcular índices de split
        n_samples = len(df_sorted)
        train_end = int(n_samples * train_ratio)
        val_end = train_end + int(n_samples * val_ratio)

        train_df = df_sorted.iloc[:train_end].copy()
        val_df = df_sorted.iloc[train_end:val_end].copy()
        test_df = df_sorted.iloc[val_end:].copy()

        # Validar tamanhos mínimos
        min_samples_per_split = 10
        for name, split_df in [('train', train_df), ('val', val_df), ('test', test_df)]:
            if len(split_df) < min_samples_per_split:
                logger.warning(
                    f"Split {name} tem poucas amostras",
                    count=len(split_df),
                    minimum=min_samples_per_split
                )

        # Verificar que não há overlap temporal
        if len(train_df) > 0 and len(val_df) > 0:
            train_max = train_df['created_at'].max()
            val_min = val_df['created_at'].min()
            if train_max >= val_min:
                logger.warning(
                    "Overlap temporal detectado entre train e val",
                    train_max=train_max,
                    val_min=val_min
                )

        if len(val_df) > 0 and len(test_df) > 0:
            val_max = val_df['created_at'].max()
            test_min = test_df['created_at'].min()
            if val_max >= test_min:
                logger.warning(
                    "Overlap temporal detectado entre val e test",
                    val_max=val_max,
                    test_min=test_min
                )

        # Log estatísticas
        logger.info(
            "Splits temporais criados",
            train_size=len(train_df),
            train_date_range=(
                str(train_df['created_at'].min()) if len(train_df) > 0 else None,
                str(train_df['created_at'].max()) if len(train_df) > 0 else None
            ),
            val_size=len(val_df),
            val_date_range=(
                str(val_df['created_at'].min()) if len(val_df) > 0 else None,
                str(val_df['created_at'].max()) if len(val_df) > 0 else None
            ),
            test_size=len(test_df),
            test_date_range=(
                str(test_df['created_at'].min()) if len(test_df) > 0 else None,
                str(test_df['created_at'].max()) if len(test_df) > 0 else None
            )
        )

        return train_df, val_df, test_df

    async def get_collection_statistics(
        self,
        specialist_type: str,
        days: int = 90
    ) -> Dict[str, Any]:
        """
        Obtém estatísticas das collections sem carregar todos os dados.

        Útil para verificação rápida de disponibilidade de dados.

        Args:
            specialist_type: Tipo do especialista
            days: Janela de tempo

        Returns:
            Estatísticas de opiniões e feedback
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Contar opiniões
        def count_opinions():
            return self.opinions_collection.count_documents({
                'specialist_type': specialist_type,
                'created_at': {'$gte': cutoff_date}
            })

        total_opinions = self._execute_with_breaker(count_opinions)

        # Contar opiniões com feedback usando aggregation
        def count_with_feedback():
            pipeline = [
                {
                    '$match': {
                        'specialist_type': specialist_type,
                        'created_at': {'$gte': cutoff_date}
                    }
                },
                {
                    '$lookup': {
                        'from': 'specialist_feedback',
                        'localField': 'opinion_id',
                        'foreignField': 'opinion_id',
                        'as': 'feedback'
                    }
                },
                {
                    '$match': {
                        'feedback': {'$ne': []}
                    }
                },
                {
                    '$count': 'total'
                }
            ]
            result = list(self.opinions_collection.aggregate(pipeline))
            return result[0]['total'] if result else 0

        opinions_with_feedback = self._execute_with_breaker(count_with_feedback)

        # Calcular taxa de cobertura
        coverage_rate = (
            opinions_with_feedback / total_opinions * 100
            if total_opinions > 0 else 0.0
        )

        # Distribuição de feedback ratings
        def get_rating_distribution():
            pipeline = [
                {
                    '$match': {
                        'specialist_type': specialist_type,
                        'submitted_at': {'$gte': cutoff_date}
                    }
                },
                {
                    '$group': {
                        '_id': '$human_rating',
                        'count': {'$sum': 1}
                    }
                }
            ]
            return list(self.feedback_collection.aggregate(pipeline))

        rating_dist = self._execute_with_breaker(get_rating_distribution)
        rating_distribution = {
            item['_id']: item['count']
            for item in rating_dist
        }

        stats = {
            'specialist_type': specialist_type,
            'days': days,
            'cutoff_date': cutoff_date.isoformat(),
            'total_opinions': total_opinions,
            'opinions_with_feedback': opinions_with_feedback,
            'coverage_rate': round(coverage_rate, 2),
            'rating_distribution': rating_distribution,
            'sufficient_for_training': opinions_with_feedback >= 1000
        }

        logger.info(
            "Estatísticas de collection obtidas",
            **stats
        )

        return stats

    def validate_data_quality(
        self,
        df: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Valida qualidade dos dados coletados.

        Verifica:
        - Missing values
        - Sparsity de features
        - Outliers
        - Consistência de labels

        Args:
            df: DataFrame a validar

        Returns:
            Relatório de qualidade com score e warnings
        """
        warnings = []
        quality_issues = {}

        # Colunas de features (excluir metadados)
        metadata_cols = ['opinion_id', 'plan_id', 'specialist_type', 'created_at', 'human_rating', 'label']
        feature_cols = [col for col in df.columns if col in self.expected_feature_names]

        # 1. Missing values
        missing_pcts = {}
        for col in feature_cols:
            missing_pct = df[col].isna().mean() * 100
            if missing_pct > 0:
                missing_pcts[col] = round(missing_pct, 2)

        high_missing = {k: v for k, v in missing_pcts.items() if v > 5}
        if high_missing:
            warnings.append(f"{len(high_missing)} features com > 5% missing values")
            quality_issues['high_missing_values'] = high_missing

        # 2. Feature sparsity (features sempre zero)
        sparse_features = []
        for col in feature_cols:
            if (df[col] == 0.0).all():
                sparse_features.append(col)

        sparsity_rate = len(sparse_features) / len(feature_cols) * 100 if feature_cols else 0
        if sparsity_rate > 50:
            warnings.append(f"{len(sparse_features)} features ({sparsity_rate:.1f}%) são sempre zero")
        quality_issues['sparse_features'] = sparse_features

        # 3. Outliers (usando IQR)
        outliers = {}
        for col in feature_cols:
            if df[col].dtype in ['float64', 'int64', 'float32', 'int32']:
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1

                if IQR > 0:
                    lower_bound = Q1 - 1.5 * IQR
                    upper_bound = Q3 + 1.5 * IQR

                    outlier_mask = (df[col] < lower_bound) | (df[col] > upper_bound)
                    outlier_pct = outlier_mask.mean() * 100

                    if outlier_pct > 10:
                        outliers[col] = round(outlier_pct, 2)

        if outliers:
            warnings.append(f"{len(outliers)} features com > 10% outliers")
            quality_issues['high_outliers'] = outliers

        # 4. Label consistency
        if 'label' in df.columns:
            valid_labels = set(self.RECOMMENDATION_TO_LABEL.values())
            invalid_labels = df[~df['label'].isin(valid_labels)]['label'].unique()

            if len(invalid_labels) > 0:
                warnings.append(f"Labels inválidos encontrados: {list(invalid_labels)}")
                quality_issues['invalid_labels'] = list(invalid_labels)

            if df['label'].isna().any():
                warnings.append("Labels nulos encontrados")
                quality_issues['null_labels'] = int(df['label'].isna().sum())

        # Calcular quality score (0.0 - 1.0)
        # Penalizar por cada tipo de problema
        quality_score = 1.0

        # Penalidade por missing values
        if missing_pcts:
            avg_missing = sum(missing_pcts.values()) / len(missing_pcts)
            quality_score -= min(0.2, avg_missing / 100)

        # Penalidade por sparsity
        quality_score -= min(0.3, sparsity_rate / 200)

        # Penalidade por outliers
        if outliers:
            avg_outliers = sum(outliers.values()) / len(outliers)
            quality_score -= min(0.2, avg_outliers / 100)

        # Penalidade por problemas de label
        if 'invalid_labels' in quality_issues or 'null_labels' in quality_issues:
            quality_score -= 0.3

        quality_score = max(0.0, quality_score)

        passed = quality_score >= 0.6 and 'invalid_labels' not in quality_issues

        report = {
            'missing_values': missing_pcts,
            'sparse_features': sparse_features,
            'sparse_features_count': len(sparse_features),
            'sparsity_rate': round(sparsity_rate, 2),
            'outliers': outliers,
            'quality_score': round(quality_score, 3),
            'passed': passed,
            'warnings': warnings
        }

        log_level = 'info' if passed else 'warning'
        getattr(logger, log_level)(
            "Validação de qualidade concluída",
            quality_score=report['quality_score'],
            passed=passed,
            num_warnings=len(warnings)
        )

        return report

    def close(self):
        """Fecha conexão MongoDB."""
        if self.mongodb_client:
            self.mongodb_client.close()
            logger.info("Conexão MongoDB fechada")


# Função auxiliar para uso síncrono
def collect_training_data_sync(
    specialist_type: str,
    days: int = 90,
    min_samples: int = 1000,
    min_feedback_rating: float = 0.0,
    mongodb_uri: str = None,
    mongodb_database: str = "neural_hive",
    opinions_collection_name: str = None,
    feedback_collection_name: str = None
) -> pd.DataFrame:
    """
    Versão síncrona para coleta de dados de treinamento.

    Wrapper conveniente para uso em scripts e notebooks.

    Args:
        specialist_type: Tipo do especialista
        days: Janela de tempo
        min_samples: Mínimo de amostras
        min_feedback_rating: Rating mínimo
        mongodb_uri: URI MongoDB
        mongodb_database: Nome do database
        opinions_collection_name: Nome da collection de opiniões
        feedback_collection_name: Nome da collection de feedback

    Returns:
        DataFrame com dados de treinamento
    """
    import asyncio

    collector = RealDataCollector(
        mongodb_uri=mongodb_uri,
        mongodb_database=mongodb_database,
        opinions_collection_name=opinions_collection_name,
        feedback_collection_name=feedback_collection_name
    )

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        return loop.run_until_complete(
            collector.collect_training_data(
                specialist_type=specialist_type,
                days=days,
                min_samples=min_samples,
                min_feedback_rating=min_feedback_rating
            )
        )
    finally:
        collector.close()
