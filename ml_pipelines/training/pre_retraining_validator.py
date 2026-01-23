#!/usr/bin/env python3
"""
PreRetrainingValidator: Validador de pré-requisitos antes de iniciar retraining.

Este módulo atua como gatekeeper antes do pipeline de treinamento,
verificando se as condições mínimas são atendidas:
- Disponibilidade de dados (contagem mínima)
- Qualidade de dados (distribuição de labels, completude de features)
- Integridade temporal (sem vazamento de dados)
- Comparação com baseline (divergência de distribuição)

Executa validações leves via aggregation pipelines do MongoDB,
evitando carregar o dataset completo antes de garantir que o
treinamento deve prosseguir.
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import structlog
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection

# Adicionar path para importar FeatureExtractor
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..', '..', 'libraries', 'python')))

# Importar FeatureExtractor para extração de features
try:
    from neural_hive_specialists.feature_extraction.feature_extractor import FeatureExtractor
    _FEATURE_EXTRACTOR_AVAILABLE = True
except ImportError:
    _FEATURE_EXTRACTOR_AVAILABLE = False

# Importar schema de features centralizado
try:
    sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..')))
    from feature_store.feature_definitions import get_feature_names
    _FEATURE_DEFINITIONS_AVAILABLE = True
except ImportError:
    _FEATURE_DEFINITIONS_AVAILABLE = False

logger = structlog.get_logger(__name__)


class ValidationFailedError(Exception):
    """Lançado quando a validação de pré-requisitos falha."""
    pass


class PreRetrainingValidator:
    """
    Valida pré-requisitos antes de iniciar o pipeline de retraining.

    Verificações:
    - Contagem mínima de amostras (default: 1000 por especialista)
    - Balanceamento de distribuição de labels (nenhuma classe < 5%)
    - Qualidade de features (< 5% valores ausentes via sampling)
    - Integridade temporal dos splits
    - Comparação de baseline com treinamento anterior
    """

    # Mapeamento de recomendações para labels (alinhado com RealDataCollector)
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
        Inicializa o validador de pré-requisitos.

        Args:
            mongodb_uri: URI de conexão MongoDB. Default: env MONGODB_URI
            mongodb_database: Nome do database. Default: neural_hive
            opinions_collection_name: Nome da collection de opiniões
            feedback_collection_name: Nome da collection de feedback
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

        # Inicializar conexões
        self._connect()

        logger.info(
            "PreRetrainingValidator inicializado",
            mongodb_uri=self._mask_uri(self.mongodb_uri),
            database=self.mongodb_database,
            opinions_collection=self.opinions_collection_name,
            feedback_collection=self.feedback_collection_name
        )

    def _mask_uri(self, uri: str) -> str:
        """Mascara credenciais na URI para logging seguro."""
        if '@' in uri:
            parts = uri.split('@')
            return f"mongodb://***@{parts[-1]}"
        return uri

    def _connect(self):
        """Estabelece conexão com MongoDB."""
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

            logger.info("Conexão MongoDB estabelecida para validação")

        except Exception as e:
            logger.error(
                "Falha na conexão MongoDB para validação",
                error=str(e)
            )
            raise

    def validate_prerequisites(
        self,
        specialist_type: str,
        days: int = 90,
        min_samples: int = 1000,
        min_feedback_rating: float = 0.0
    ) -> Dict[str, Any]:
        """
        Executa todas as validações de pré-requisitos.

        Args:
            specialist_type: Tipo do especialista (technical, evolution, etc)
            days: Janela de tempo em dias para considerar dados
            min_samples: Mínimo de amostras necessárias
            min_feedback_rating: Rating mínimo de feedback para incluir

        Returns:
            Relatório estruturado com:
            - passed: bool indicando se todas as verificações passaram
            - recommendation: 'proceed' | 'wait_for_more_data' | 'investigate_distribution'
            - checks: resultados detalhados de cada verificação
            - warnings: lista de avisos não-bloqueantes
            - blocking_issues: lista de problemas críticos
        """
        validation_timestamp = datetime.utcnow().isoformat() + 'Z'

        logger.info(
            "pre_retraining_validation_started",
            specialist_type=specialist_type,
            days=days,
            min_samples=min_samples,
            min_feedback_rating=min_feedback_rating
        )

        blocking_issues: List[str] = []
        warnings: List[str] = []

        # 1. Verificar contagem de amostras
        sample_count_result = self._check_sample_count(
            specialist_type=specialist_type,
            days=days,
            min_samples=min_samples,
            min_feedback_rating=min_feedback_rating
        )

        if not sample_count_result['passed']:
            blocking_issues.append(
                f"Amostras insuficientes: {sample_count_result['current']} de {sample_count_result['required']} necessárias"
            )

        # 2. Verificar distribuição de labels
        label_distribution_result = self._check_label_distribution(
            specialist_type=specialist_type,
            days=days,
            min_feedback_rating=min_feedback_rating
        )

        if label_distribution_result.get('underrepresented_classes'):
            blocking_issues.append(
                f"Classes subrepresentadas (< 5%): {label_distribution_result['underrepresented_classes']}"
            )

        if label_distribution_result.get('dominant_classes'):
            warnings.append(
                f"Classes dominantes (> 80%): {label_distribution_result['dominant_classes']}"
            )

        # 3. Verificar qualidade de features (amostragem)
        feature_quality_result = self._check_feature_quality(
            specialist_type=specialist_type,
            days=days,
            min_feedback_rating=min_feedback_rating,
            sample_size=100
        )

        if not feature_quality_result['passed']:
            # Threshold de 5% (>= 0.05) é bloqueante, não 10%
            if feature_quality_result['missing_value_rate'] >= 0.05:
                blocking_issues.append(
                    f"Taxa de valores ausentes >= 5%: {feature_quality_result['missing_value_rate']:.1%}. "
                    f"Features com alta taxa de ausência: {feature_quality_result.get('high_missing_features', {})}"
                )
            else:
                warnings.append(
                    f"Taxa de valores ausentes: {feature_quality_result['missing_value_rate']:.1%}"
                )

        # 4. Verificar integridade temporal
        temporal_integrity_result = self._validate_temporal_integrity(
            specialist_type=specialist_type,
            days=days
        )

        if not temporal_integrity_result['passed']:
            if temporal_integrity_result.get('has_future_timestamps'):
                blocking_issues.append("Timestamps no futuro detectados")
            if temporal_integrity_result.get('span_days', 0) < 7:
                warnings.append(
                    f"Range de dados muito curto: {temporal_integrity_result.get('span_days', 0)} dias"
                )

        # 5. Comparar com baseline (MLflow)
        baseline_comparison_result = self._compare_with_baseline(
            specialist_type=specialist_type,
            current_distribution=label_distribution_result.get('percentages', {})
        )

        if baseline_comparison_result.get('significant_shift'):
            warnings.append(
                f"Shift significativo de distribuição detectado: {baseline_comparison_result.get('max_divergence', 0):.1f}%"
            )

        # Determinar resultado e recomendação
        passed = len(blocking_issues) == 0

        if not passed:
            if not sample_count_result['passed']:
                recommendation = 'wait_for_more_data'
            else:
                recommendation = 'investigate_distribution'
        else:
            recommendation = 'proceed'

        result = {
            'validation_timestamp': validation_timestamp,
            'specialist_type': specialist_type,
            'passed': passed,
            'recommendation': recommendation,
            'checks': {
                'sample_count': sample_count_result,
                'label_distribution': label_distribution_result,
                'feature_quality': feature_quality_result,
                'temporal_integrity': temporal_integrity_result,
                'baseline_comparison': baseline_comparison_result
            },
            'warnings': warnings,
            'blocking_issues': blocking_issues,
            'recommendations': self._generate_recommendations(
                passed=passed,
                recommendation=recommendation,
                sample_count_result=sample_count_result,
                label_distribution_result=label_distribution_result,
                feature_quality_result=feature_quality_result,
                baseline_comparison_result=baseline_comparison_result
            )
        }

        logger.info(
            "pre_retraining_validation_completed",
            specialist_type=specialist_type,
            passed=passed,
            recommendation=recommendation,
            num_warnings=len(warnings),
            num_blocking_issues=len(blocking_issues)
        )

        return result

    def _check_sample_count(
        self,
        specialist_type: str,
        days: int,
        min_samples: int,
        min_feedback_rating: float
    ) -> Dict[str, Any]:
        """
        Verifica contagem de amostras usando aggregation pipeline.

        Conta opiniões com feedback associado sem carregar dados completos.
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        try:
            # Pipeline para contar opiniões com feedback
            pipeline = [
                {
                    '$match': {
                        'specialist_type': specialist_type,
                        'created_at': {'$gte': cutoff_date}
                    }
                },
                {
                    '$lookup': {
                        'from': self.feedback_collection_name,
                        'localField': 'opinion_id',
                        'foreignField': 'opinion_id',
                        'as': 'feedback_docs'
                    }
                },
                {
                    '$match': {
                        'feedback_docs': {'$ne': []},
                        'feedback_docs.human_rating': {'$gte': min_feedback_rating}
                    }
                },
                {
                    '$count': 'total'
                }
            ]

            result = list(self.opinions_collection.aggregate(pipeline))
            current_count = result[0]['total'] if result else 0

            # Calcular taxa de cobertura (opiniões com feedback / total de opiniões)
            total_opinions = self.opinions_collection.count_documents({
                'specialist_type': specialist_type,
                'created_at': {'$gte': cutoff_date}
            })

            coverage_rate = (current_count / total_opinions * 100) if total_opinions > 0 else 0.0

            passed = current_count >= min_samples

            logger.info(
                "sample_count_check",
                specialist_type=specialist_type,
                current_count=current_count,
                required_count=min_samples,
                coverage_rate=f"{coverage_rate:.1f}%",
                passed=passed
            )

            return {
                'passed': passed,
                'current': current_count,
                'required': min_samples,
                'total_opinions': total_opinions,
                'coverage_rate': round(coverage_rate, 2)
            }

        except Exception as e:
            logger.error(
                "sample_count_check_failed",
                specialist_type=specialist_type,
                error=str(e)
            )
            return {
                'passed': False,
                'current': 0,
                'required': min_samples,
                'error': str(e)
            }

    def _check_label_distribution(
        self,
        specialist_type: str,
        days: int,
        min_feedback_rating: float
    ) -> Dict[str, Any]:
        """
        Verifica distribuição de labels usando aggregation pipeline.

        Agrupa por human_recommendation e calcula percentuais.
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        try:
            # Pipeline para obter distribuição de labels
            pipeline = [
                {
                    '$match': {
                        'specialist_type': specialist_type,
                        'created_at': {'$gte': cutoff_date}
                    }
                },
                {
                    '$lookup': {
                        'from': self.feedback_collection_name,
                        'localField': 'opinion_id',
                        'foreignField': 'opinion_id',
                        'as': 'feedback_docs'
                    }
                },
                {
                    '$unwind': '$feedback_docs'
                },
                {
                    '$match': {
                        'feedback_docs.human_rating': {'$gte': min_feedback_rating}
                    }
                },
                {
                    '$group': {
                        '_id': '$feedback_docs.human_recommendation',
                        'count': {'$sum': 1}
                    }
                }
            ]

            results = list(self.opinions_collection.aggregate(pipeline))

            # Calcular distribuição
            distribution = {}
            total = 0
            for item in results:
                label = item['_id']
                count = item['count']
                if label:
                    distribution[label] = count
                    total += count

            # Calcular percentuais
            percentages = {}
            for label, count in distribution.items():
                pct = (count / total * 100) if total > 0 else 0.0
                percentages[label] = round(pct, 2)

            # Detectar classes problemáticas
            underrepresented = [
                label for label, pct in percentages.items()
                if pct < 5.0
            ]
            dominant = [
                label for label, pct in percentages.items()
                if pct > 80.0
            ]

            is_balanced = len(underrepresented) == 0 and len(dominant) == 0

            logger.info(
                "label_distribution_check",
                specialist_type=specialist_type,
                distribution=distribution,
                percentages=percentages,
                is_balanced=is_balanced
            )

            return {
                'passed': is_balanced,
                'distribution': distribution,
                'percentages': percentages,
                'total_samples': total,
                'is_balanced': is_balanced,
                'underrepresented_classes': underrepresented,
                'dominant_classes': dominant
            }

        except Exception as e:
            logger.error(
                "label_distribution_check_failed",
                specialist_type=specialist_type,
                error=str(e)
            )
            return {
                'passed': False,
                'error': str(e),
                'distribution': {},
                'percentages': {}
            }

    def _check_feature_quality(
        self,
        specialist_type: str,
        days: int,
        min_feedback_rating: float,
        sample_size: int = 100
    ) -> Dict[str, Any]:
        """
        Verifica qualidade de features usando FeatureExtractor e amostragem.

        Amostra N opiniões, extrai features usando FeatureExtractor e calcula
        a taxa de valores ausentes por feature. Falha se missing_value_rate >= 5%.
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        try:
            # Pipeline para amostrar opiniões com feedback
            pipeline = [
                {
                    '$match': {
                        'specialist_type': specialist_type,
                        'created_at': {'$gte': cutoff_date}
                    }
                },
                {
                    '$lookup': {
                        'from': self.feedback_collection_name,
                        'localField': 'opinion_id',
                        'foreignField': 'opinion_id',
                        'as': 'feedback_docs'
                    }
                },
                {
                    '$match': {
                        'feedback_docs': {'$ne': []},
                        'feedback_docs.human_rating': {'$gte': min_feedback_rating}
                    }
                },
                {
                    '$sample': {'size': sample_size}
                },
                {
                    '$project': {
                        'opinion_id': 1,
                        'cognitive_plan': 1
                    }
                }
            ]

            samples = list(self.opinions_collection.aggregate(pipeline))

            if not samples:
                return {
                    'passed': False,
                    'sample_size': 0,
                    'missing_value_rate': 1.0,
                    'extraction_failure_rate': 1.0,
                    'feature_missing_rates': {},
                    'error': 'Nenhuma amostra disponível'
                }

            actual_sample_size = len(samples)

            # Verificar se FeatureExtractor está disponível
            if not _FEATURE_EXTRACTOR_AVAILABLE:
                logger.warning(
                    "feature_extractor_not_available_for_quality_check",
                    fallback="checking cognitive_plan completeness only"
                )
                # Fallback: verificar apenas completude de cognitive_plan
                missing_count = sum(
                    1 for s in samples
                    if not s.get('cognitive_plan') or not isinstance(s.get('cognitive_plan'), dict)
                )
                missing_value_rate = missing_count / actual_sample_size
                passed = missing_value_rate < 0.05

                return {
                    'passed': passed,
                    'sample_size': actual_sample_size,
                    'missing_value_rate': round(missing_value_rate, 4),
                    'extraction_failure_rate': 0.0,
                    'feature_missing_rates': {},
                    'validation_method': 'cognitive_plan_completeness_only'
                }

            # Usar FeatureExtractor para extrair features
            extractor = FeatureExtractor()
            expected_features = get_feature_names() if _FEATURE_DEFINITIONS_AVAILABLE else []

            extraction_failures = 0
            extracted_features_list = []

            for sample in samples:
                cognitive_plan = sample.get('cognitive_plan')

                if not cognitive_plan or not isinstance(cognitive_plan, dict):
                    extraction_failures += 1
                    extracted_features_list.append({})
                    continue

                try:
                    features_result = extractor.extract_features(cognitive_plan)
                    features = features_result.get('aggregated_features', {})
                    extracted_features_list.append(features)
                except Exception as e:
                    logger.debug(
                        "feature_extraction_failed_for_sample",
                        opinion_id=sample.get('opinion_id'),
                        error=str(e)
                    )
                    extraction_failures += 1
                    extracted_features_list.append({})

            extraction_failure_rate = extraction_failures / actual_sample_size

            # Calcular taxa de valores ausentes POR FEATURE
            feature_missing_rates = {}
            total_missing_count = 0
            total_feature_checks = 0

            if expected_features:
                for feature_name in expected_features:
                    missing_for_feature = 0
                    for features in extracted_features_list:
                        value = features.get(feature_name)
                        # Considerar ausente se: None, não existe, ou NaN
                        if value is None or feature_name not in features:
                            missing_for_feature += 1
                        elif isinstance(value, float) and (value != value):  # NaN check
                            missing_for_feature += 1

                    feature_missing_rate = missing_for_feature / actual_sample_size
                    feature_missing_rates[feature_name] = round(feature_missing_rate, 4)
                    total_missing_count += missing_for_feature
                    total_feature_checks += actual_sample_size

                # Taxa global de valores ausentes
                overall_missing_rate = total_missing_count / total_feature_checks if total_feature_checks > 0 else 1.0
            else:
                # Sem schema de features, calcular baseado nas features extraídas
                all_feature_names = set()
                for features in extracted_features_list:
                    all_feature_names.update(features.keys())

                for feature_name in all_feature_names:
                    missing_for_feature = sum(
                        1 for features in extracted_features_list
                        if feature_name not in features or features.get(feature_name) is None
                    )
                    feature_missing_rates[feature_name] = round(missing_for_feature / actual_sample_size, 4)

                # Taxa global baseada nas features encontradas
                if all_feature_names and extracted_features_list:
                    total_checks = len(all_feature_names) * actual_sample_size
                    total_missing = sum(
                        1 for features in extracted_features_list
                        for fname in all_feature_names
                        if fname not in features or features.get(fname) is None
                    )
                    overall_missing_rate = total_missing / total_checks
                else:
                    overall_missing_rate = 1.0

            # Encontrar features com maior taxa de valores ausentes
            high_missing_features = {
                k: v for k, v in feature_missing_rates.items()
                if v >= 0.05
            }

            # IMPORTANTE: Threshold de 5% (0.05), não 10%
            # Falha se missing_value_rate >= 0.05
            passed = overall_missing_rate < 0.05

            logger.info(
                "feature_quality_check",
                specialist_type=specialist_type,
                sample_size=actual_sample_size,
                extraction_failure_rate=f"{extraction_failure_rate:.1%}",
                overall_missing_rate=f"{overall_missing_rate:.1%}",
                num_features_checked=len(feature_missing_rates),
                num_high_missing_features=len(high_missing_features),
                passed=passed
            )

            if high_missing_features:
                logger.warning(
                    "features_with_high_missing_rate",
                    high_missing_features=high_missing_features,
                    threshold="5%"
                )

            return {
                'passed': passed,
                'sample_size': actual_sample_size,
                'missing_value_rate': round(overall_missing_rate, 4),
                'extraction_failure_rate': round(extraction_failure_rate, 4),
                'feature_missing_rates': feature_missing_rates,
                'high_missing_features': high_missing_features,
                'num_features_checked': len(feature_missing_rates),
                'validation_method': 'feature_extractor'
            }

        except Exception as e:
            logger.error(
                "feature_quality_check_failed",
                specialist_type=specialist_type,
                error=str(e)
            )
            return {
                'passed': False,
                'sample_size': 0,
                'missing_value_rate': 1.0,
                'extraction_failure_rate': 1.0,
                'feature_missing_rates': {},
                'error': str(e)
            }

    def _validate_temporal_integrity(
        self,
        specialist_type: str,
        days: int
    ) -> Dict[str, Any]:
        """
        Valida integridade temporal dos dados.

        Verifica:
        - Sem timestamps no futuro
        - Range de datas razoável
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        now = datetime.utcnow()

        try:
            # Buscar min/max created_at
            pipeline = [
                {
                    '$match': {
                        'specialist_type': specialist_type,
                        'created_at': {'$gte': cutoff_date}
                    }
                },
                {
                    '$group': {
                        '_id': None,
                        'min_date': {'$min': '$created_at'},
                        'max_date': {'$max': '$created_at'}
                    }
                }
            ]

            result = list(self.opinions_collection.aggregate(pipeline))

            if not result:
                return {
                    'passed': False,
                    'error': 'Nenhum dado encontrado para validação temporal'
                }

            min_date = result[0]['min_date']
            max_date = result[0]['max_date']

            # Verificar timestamps no futuro
            has_future_timestamps = max_date > now

            # Calcular span em dias
            if min_date and max_date:
                span_days = (max_date - min_date).days
            else:
                span_days = 0

            # Passa se:
            # - Sem timestamps no futuro
            # - Range de pelo menos 7 dias (para evitar dados de um único dia)
            passed = not has_future_timestamps and span_days >= 7

            logger.info(
                "temporal_integrity_check",
                specialist_type=specialist_type,
                min_date=min_date.isoformat() if min_date else None,
                max_date=max_date.isoformat() if max_date else None,
                span_days=span_days,
                has_future_timestamps=has_future_timestamps,
                passed=passed
            )

            return {
                'passed': passed,
                'date_range_start': min_date.isoformat() + 'Z' if min_date else None,
                'date_range_end': max_date.isoformat() + 'Z' if max_date else None,
                'span_days': span_days,
                'has_future_timestamps': has_future_timestamps
            }

        except Exception as e:
            logger.error(
                "temporal_integrity_check_failed",
                specialist_type=specialist_type,
                error=str(e)
            )
            return {
                'passed': False,
                'error': str(e)
            }

    @staticmethod
    def validate_temporal_split_integrity(
        train_timestamps: List[datetime],
        val_timestamps: List[datetime],
        test_timestamps: List[datetime]
    ) -> Dict[str, Any]:
        """
        Valida integridade temporal dos splits para evitar data leakage.

        Verifica que:
        - max(created_at) do treino < min(created_at) da validação
        - max(created_at) da validação < min(created_at) do teste

        Args:
            train_timestamps: Lista de timestamps do conjunto de treino
            val_timestamps: Lista de timestamps do conjunto de validação
            test_timestamps: Lista de timestamps do conjunto de teste

        Returns:
            Dict com resultado da validação:
            - passed: bool indicando se não há data leakage
            - leakage_details: descrição dos problemas encontrados
            - train_max, val_min, val_max, test_min: datas dos limites
        """
        result = {
            'passed': True,
            'leakage_details': [],
            'train_max': None,
            'val_min': None,
            'val_max': None,
            'test_min': None
        }

        if not train_timestamps or not val_timestamps or not test_timestamps:
            result['passed'] = False
            result['leakage_details'].append(
                "Um ou mais splits estão vazios - impossível validar integridade temporal"
            )
            logger.warning(
                "temporal_split_validation_empty_splits",
                train_count=len(train_timestamps) if train_timestamps else 0,
                val_count=len(val_timestamps) if val_timestamps else 0,
                test_count=len(test_timestamps) if test_timestamps else 0
            )
            return result

        train_max = max(train_timestamps)
        val_min = min(val_timestamps)
        val_max = max(val_timestamps)
        test_min = min(test_timestamps)

        result['train_max'] = train_max.isoformat() if train_max else None
        result['val_min'] = val_min.isoformat() if val_min else None
        result['val_max'] = val_max.isoformat() if val_max else None
        result['test_min'] = test_min.isoformat() if test_min else None

        # Verificar leakage entre treino e validação
        if train_max >= val_min:
            result['passed'] = False
            result['leakage_details'].append(
                f"DATA LEAKAGE: max(treino)={train_max.isoformat()} >= min(validação)={val_min.isoformat()}. "
                f"Dados de treino contêm informações do futuro relativo à validação."
            )
            logger.error(
                "temporal_split_leakage_train_val",
                train_max=train_max.isoformat(),
                val_min=val_min.isoformat(),
                overlap_seconds=(train_max - val_min).total_seconds()
            )

        # Verificar leakage entre validação e teste
        if val_max >= test_min:
            result['passed'] = False
            result['leakage_details'].append(
                f"DATA LEAKAGE: max(validação)={val_max.isoformat()} >= min(teste)={test_min.isoformat()}. "
                f"Dados de validação contêm informações do futuro relativo ao teste."
            )
            logger.error(
                "temporal_split_leakage_val_test",
                val_max=val_max.isoformat(),
                test_min=test_min.isoformat(),
                overlap_seconds=(val_max - test_min).total_seconds()
            )

        # Verificar leakage entre treino e teste (caso mais grave)
        if train_max >= test_min:
            result['passed'] = False
            result['leakage_details'].append(
                f"DATA LEAKAGE CRÍTICO: max(treino)={train_max.isoformat()} >= min(teste)={test_min.isoformat()}. "
                f"Dados de treino contêm informações do período de teste."
            )
            logger.error(
                "temporal_split_leakage_train_test",
                train_max=train_max.isoformat(),
                test_min=test_min.isoformat(),
                overlap_seconds=(train_max - test_min).total_seconds()
            )

        if result['passed']:
            logger.info(
                "temporal_split_validation_passed",
                train_max=train_max.isoformat(),
                val_min=val_min.isoformat(),
                val_max=val_max.isoformat(),
                test_min=test_min.isoformat()
            )

        return result

    def _compare_with_baseline(
        self,
        specialist_type: str,
        current_distribution: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Compara distribuição atual com baseline do último modelo Production.

        Usa MLflow para recuperar metadados do treinamento anterior.
        """
        try:
            import mlflow
            from mlflow.tracking import MlflowClient

            # Mapear specialist_type para model_name
            model_name_map = {
                'technical': 'technical-evaluator',
                'evolution': 'evolution-evaluator'
            }

            model_name = model_name_map.get(specialist_type)
            if not model_name:
                return {
                    'comparison_available': False,
                    'reason': f'Specialist {specialist_type} não mapeado para model_name'
                }

            client = MlflowClient()

            # Buscar versão Production
            try:
                versions = client.search_model_versions(f"name='{model_name}'")
            except Exception:
                return {
                    'comparison_available': False,
                    'reason': f'Modelo {model_name} não encontrado no registry'
                }

            baseline_run_id = None
            for version in versions:
                if version.current_stage == 'Production':
                    baseline_run_id = version.run_id
                    break

            if not baseline_run_id:
                return {
                    'comparison_available': False,
                    'reason': 'Nenhum modelo Production encontrado para baseline'
                }

            # Obter metadados do run baseline
            baseline_run = client.get_run(baseline_run_id)

            # Extrair distribuição de labels do baseline
            baseline_distribution = {}
            for key, value in baseline_run.data.metrics.items():
                if key.startswith('label_') and key.endswith('_percentage'):
                    # Extrair nome do label (ex: label_approve_percentage -> approve)
                    label = key.replace('label_', '').replace('_percentage', '')
                    baseline_distribution[label] = value

            if not baseline_distribution:
                return {
                    'comparison_available': False,
                    'reason': 'Distribuição de labels não encontrada nas métricas do baseline',
                    'baseline_run_id': baseline_run_id
                }

            # Calcular divergência
            total_divergence = 0.0
            max_divergence = 0.0

            all_labels = set(current_distribution.keys()) | set(baseline_distribution.keys())

            for label in all_labels:
                current_pct = current_distribution.get(label, 0.0)
                baseline_pct = baseline_distribution.get(label, 0.0)
                divergence = abs(current_pct - baseline_pct)

                total_divergence += divergence
                max_divergence = max(max_divergence, divergence)

            # Shift significativo se max_divergence > 30%
            significant_shift = max_divergence > 30.0

            logger.info(
                "baseline_comparison",
                specialist_type=specialist_type,
                baseline_run_id=baseline_run_id,
                total_divergence=f"{total_divergence:.1f}%",
                max_divergence=f"{max_divergence:.1f}%",
                significant_shift=significant_shift
            )

            return {
                'comparison_available': True,
                'baseline_run_id': baseline_run_id,
                'baseline_distribution': baseline_distribution,
                'current_distribution': current_distribution,
                'total_divergence': round(total_divergence, 2),
                'max_divergence': round(max_divergence, 2),
                'significant_shift': significant_shift,
                'baseline_data_source': baseline_run.data.params.get('data_source', 'unknown'),
                'baseline_samples': baseline_run.data.metrics.get('real_samples_count', 0)
            }

        except ImportError:
            logger.warning("MLflow não disponível para comparação de baseline")
            return {
                'comparison_available': False,
                'reason': 'MLflow não disponível'
            }

        except Exception as e:
            logger.warning(
                "baseline_comparison_failed",
                specialist_type=specialist_type,
                error=str(e)
            )
            return {
                'comparison_available': False,
                'error': str(e)
            }

    def _generate_recommendations(
        self,
        passed: bool,
        recommendation: str,
        sample_count_result: Dict[str, Any],
        label_distribution_result: Dict[str, Any],
        feature_quality_result: Dict[str, Any],
        baseline_comparison_result: Dict[str, Any]
    ) -> List[str]:
        """Gera recomendações acionáveis baseadas nos resultados."""
        recommendations = []

        if passed:
            recommendations.append("Prosseguir com retraining - todas as verificações passaram")
            return recommendations

        if recommendation == 'wait_for_more_data':
            current = sample_count_result.get('current', 0)
            required = sample_count_result.get('required', 1000)
            deficit = required - current

            recommendations.append(
                f"Aguardar coleta de mais {deficit} amostras de feedback"
            )
            recommendations.append(
                "Verificar taxa de coleta de feedback no dashboard do Grafana"
            )
            recommendations.append(
                "Confirmar que approval-service está submetendo feedback corretamente"
            )

        if recommendation == 'investigate_distribution':
            if label_distribution_result.get('underrepresented_classes'):
                recommendations.append(
                    f"Investigar baixa representação de classes: {label_distribution_result['underrepresented_classes']}"
                )
                recommendations.append(
                    "Verificar se coleta de feedback está enviesada"
                )

            if not feature_quality_result.get('passed'):
                recommendations.append(
                    "Revisar qualidade de cognitive_plan nas opiniões"
                )
                recommendations.append(
                    "Verificar pipeline de extração de features"
                )

        if baseline_comparison_result.get('significant_shift'):
            recommendations.append(
                "Shift de distribuição detectado - investigar mudanças no comportamento de usuários"
            )

        return recommendations

    def close(self):
        """Fecha conexão MongoDB."""
        if self.mongodb_client:
            self.mongodb_client.close()
            logger.info("Conexão MongoDB fechada (PreRetrainingValidator)")
