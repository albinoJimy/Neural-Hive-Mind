"""
Gerador de explicabilidade para pareceres de especialistas.
"""

import uuid
import time
import hashlib
from typing import Dict, Any, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import structlog
from pymongo import MongoClient
from tenacity import retry, stop_after_attempt, wait_exponential
from circuitbreaker import CircuitBreaker, CircuitBreakerError

from .config import SpecialistConfig
from .explainability.shap_explainer import SHAPExplainer
from .explainability.lime_explainer import LIMEExplainer
from .explainability.narrative_generator import NarrativeGenerator
from .explainability.explainability_ledger_v2 import ExplainabilityLedgerV2

logger = structlog.get_logger()


class ExplainabilityGenerator:
    """Gerador de explicabilidade para pareceres."""

    def __init__(self, config: SpecialistConfig, metrics=None, feature_extractor=None):
        self.config = config
        self._mongo_client: Optional[MongoClient] = None
        self._metrics = metrics
        self._circuit_breaker_state = 'closed'
        self._was_open = False
        self._feature_extractor = feature_extractor

        # Initialize circuit breaker state in metrics
        if metrics:
            metrics.set_circuit_breaker_state('explainability', 'closed')

        # Initialize circuit breakers conditionally
        self._persist_breaker = None
        self._retrieve_breaker = None

        if config.enable_circuit_breaker:
            self._persist_breaker = CircuitBreaker(
                failure_threshold=config.circuit_breaker_failure_threshold,
                recovery_timeout=config.circuit_breaker_recovery_timeout,
                expected_exception=Exception,
                name='explainability_persist'
            )
            self._retrieve_breaker = CircuitBreaker(
                failure_threshold=config.circuit_breaker_failure_threshold,
                recovery_timeout=config.circuit_breaker_recovery_timeout,
                expected_exception=Exception,
                name='explainability_retrieve'
            )

        # Inicializar módulos avançados de explicabilidade com configuração formal
        explainability_config = {
            'shap_timeout_seconds': config.shap_timeout_seconds,
            'shap_background_dataset_path': config.shap_background_dataset_path,
            'shap_max_background_samples': config.shap_max_background_samples,
            'lime_timeout_seconds': config.lime_timeout_seconds,
            'lime_num_samples': config.lime_num_samples,
            'narrative_top_features': config.narrative_top_features,
            'narrative_language': config.narrative_language
        }

        self.shap_explainer = SHAPExplainer(explainability_config)
        self.lime_explainer = LIMEExplainer(explainability_config)
        self.narrative_generator = NarrativeGenerator(explainability_config)
        self.ledger_v2 = ExplainabilityLedgerV2(config)

        logger.info(
            "Explainability generator initialized",
            enabled=config.enable_explainability,
            advanced_explainability=True,
            ledger_v2_enabled=config.enable_explainability_ledger_v2
        )

    @property
    def mongo_client(self) -> MongoClient:
        """Lazy initialization do cliente MongoDB para explicações."""
        if self._mongo_client is None:
            self._mongo_client = MongoClient(
                self.config.mongodb_uri,
                serverSelectionTimeoutMS=5000
            )
        return self._mongo_client

    def generate(
        self,
        evaluation_result: Dict[str, Any],
        cognitive_plan: Dict[str, Any],
        model: Any
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Gera token e metadados de explicabilidade.

        Args:
            evaluation_result: Resultado da avaliação do especialista
            cognitive_plan: Plano cognitivo avaliado
            model: Modelo utilizado (ou None para heurísticas)

        Returns:
            Tuple[explainability_token, explainability_metadata]
        """
        if not self.config.enable_explainability:
            return self._generate_minimal_explainability()

        start_time = time.time()

        try:
            # Gerar token único
            explainability_token = str(uuid.uuid4())

            # Determinar método de explicabilidade
            method = self._determine_method(model)
            fallback_reason = None

            # Extrair feature importances
            feature_importances = self._extract_feature_importances(
                evaluation_result,
                model,
                method,
                cognitive_plan
            )

            # Se método SHAP/LIME falhou (sem importâncias), ajustar para heurístico
            if method in ['shap', 'lime'] and not feature_importances:
                fallback_reason = f'{method}_returned_empty'
                method = 'heuristic'
                logger.info(
                    "Fallback to heuristic method",
                    original_method=method,
                    reason=fallback_reason
                )

            # Gerar narrativas estruturadas se tiver importâncias
            if feature_importances and method in ['shap', 'lime']:
                try:
                    # Construir mapeamento entre reasoning_factors e SHAP features
                    reasoning_links = self._build_reasoning_links(
                        evaluation_result.get('reasoning_factors', []),
                        feature_importances
                    )

                    detailed_narrative = self.narrative_generator.generate_narrative(
                        feature_importances,
                        top_n=self.config.narrative_top_features,
                        explanation_type=method,
                        reasoning_links=reasoning_links
                    )
                    summary = self.narrative_generator.generate_summary(
                        feature_importances,
                        explanation_type=method
                    )

                    # Métricas de geração de narrativa
                    if self._metrics:
                        narrative_time = time.time() - start_time
                        self._metrics.observe_narrative_generation_time(
                            self.config.narrative_language,
                            narrative_time
                        )
                except Exception as e:
                    logger.warning("Failed to generate narrative", error=str(e))
                    detailed_narrative = "Narrativa não disponível."
                    summary = "Resumo não disponível."
            else:
                detailed_narrative = "Explicação baseada em heurísticas."
                summary = "Avaliação heurística."

            # Criar metadados enriquecidos
            metadata = {
                'method': method,
                'feature_importances': feature_importances,
                'model_version': self._get_model_version(model),
                'model_type': self._get_model_type(model),
                'human_readable_summary': summary,
                'detailed_narrative': detailed_narrative
            }

            # Adicionar fallback_reason se aplicável
            if fallback_reason:
                metadata['fallback_reason'] = fallback_reason

            # Persistir no ExplainabilityLedgerV2 se habilitado
            if self.config.enable_explainability_ledger_v2:
                try:
                    explainability_data = {
                        'plan_id': cognitive_plan.get('plan_id'),
                        'explanation_method': method,
                        'input_features': self._extract_input_features(cognitive_plan),
                        'feature_names': self._extract_feature_names(cognitive_plan),
                        'model_version': self._get_model_version(model),
                        'model_type': self._get_model_type(model),
                        'feature_importances': feature_importances,
                        'human_readable_summary': summary,
                        'detailed_narrative': detailed_narrative,
                        'prediction': {
                            'confidence_score': evaluation_result.get('confidence_score', 0.0),
                            'risk_score': evaluation_result.get('risk_score', 0.0)
                        },
                        'computation_time_ms': int((time.time() - start_time) * 1000),
                        'background_dataset_hash': self._get_background_dataset_hash() if method == 'shap' else None,
                        'random_seed': None,
                        'num_samples': self.config.lime_num_samples if method == 'lime' else None
                    }

                    ledger_token = self.ledger_v2.persist(
                        explainability_data,
                        specialist_type=self.config.specialist_type,
                        correlation_id=cognitive_plan.get('correlation_id')
                    )

                    # Adicionar token v2 aos metadados
                    metadata['explainability_token_v2'] = ledger_token

                    logger.info("Explainability persisted to ledger v2", token=ledger_token)

                    if self._metrics:
                        self._metrics.increment_ledger_v2_persistence('success')

                except Exception as e:
                    logger.warning("Failed to persist to ledger v2", error=str(e))
                    if self._metrics:
                        self._metrics.increment_ledger_v2_persistence('error')

            # Persistir explicação detalhada (ledger antigo, backward compatibility)
            if self.config.enable_explainability and self.config.enable_legacy_explainability_persistence:
                try:
                    self._persist_detailed_explanation(
                        explainability_token,
                        evaluation_result,
                        cognitive_plan,
                        metadata
                    )
                except CircuitBreakerError:
                    # Update circuit breaker state
                    self._circuit_breaker_state = 'open'
                    if self._metrics:
                        self._metrics.set_circuit_breaker_state('explainability', 'open')
                        self._metrics.increment_circuit_breaker_failure('explainability', 'CircuitBreakerError')
                    self._was_open = True

                    logger.warning(
                        "Circuit breaker open, skipping explainability persistence",
                        token=explainability_token
                    )
                    if self._metrics:
                        self._metrics.increment_fallback_invocation('explainability', 'skip_persistence')

            # Métricas de explicabilidade
            if self._metrics:
                computation_time = time.time() - start_time
                self._metrics.observe_explainability_computation_time(method, computation_time)
                self._metrics.increment_explainability_method_usage(method)
                if len(feature_importances) > 0:
                    self._metrics.observe_explainability_feature_count(method, len(feature_importances))

            logger.debug(
                "Explainability generated",
                token=explainability_token,
                method=method,
                feature_count=len(feature_importances),
                computation_time_ms=int((time.time() - start_time) * 1000)
            )

            return explainability_token, metadata

        except Exception as e:
            logger.warning(
                "Failed to generate full explainability, using minimal",
                error=str(e)
            )
            if self._metrics:
                self._metrics.increment_explainability_errors('unknown', str(type(e).__name__))
            return self._generate_minimal_explainability()

    def _generate_minimal_explainability(self) -> Tuple[str, Dict[str, Any]]:
        """Gera explicabilidade mínima quando completa não disponível."""
        token = str(uuid.uuid4())
        metadata = {
            'method': 'heuristic',
            'feature_importances': [],
            'model_version': 'heuristic',
            'model_type': 'rule_based'
        }
        return token, metadata

    def _determine_method(self, model: Any) -> str:
        """
        Determina método de explicabilidade baseado na preferência configurada ou tipo de modelo.

        Args:
            model: Modelo utilizado

        Returns:
            Método de explicabilidade (shap, lime, rule_based, heuristic)
        """
        # Se preferência não é 'auto', usar preferência configurada
        if self.config.explainability_method_preference != 'auto':
            return self.config.explainability_method_preference

        # Auto-detecção baseada no modelo
        if model is None:
            return 'heuristic'

        # Verificar tipo do modelo
        model_type = type(model).__name__.lower()

        # Modelos sklearn/tree-based: preferir SHAP
        if 'randomforest' in model_type or 'gradientboosting' in model_type:
            return 'shap'

        # Modelos lineares: LIME ou coeficientes
        if 'linear' in model_type or 'logistic' in model_type:
            return 'lime'

        # Modelos baseados em regras
        if 'rule' in model_type or 'decision' in model_type:
            return 'rule_based'

        # Fallback: heurístico
        return 'heuristic'

    def _extract_feature_importances(
        self,
        evaluation_result: Dict[str, Any],
        model: Any,
        method: str,
        cognitive_plan: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extrai importâncias de features.

        Args:
            evaluation_result: Resultado da avaliação
            model: Modelo utilizado
            method: Método de explicabilidade
            cognitive_plan: Plano cognitivo para extração de features estruturadas

        Returns:
            Lista de feature importances
        """
        if method == 'shap':
            return self._extract_shap_importances(model, evaluation_result, cognitive_plan)
        elif method == 'lime':
            return self._extract_lime_importances(model, evaluation_result, cognitive_plan)
        elif method == 'rule_based':
            return self._extract_rule_based_importances(evaluation_result)
        else:
            return self._extract_heuristic_importances(evaluation_result)

    def _on_circuit_breaker_state_change(self, old_state: str, new_state: str):
        """Callback para mudanças de estado do circuit breaker."""
        if self._metrics:
            self._metrics.set_circuit_breaker_state('explainability', new_state)
            self._metrics.increment_circuit_breaker_transition('explainability', old_state, new_state)

        logger.info(
            "Circuit breaker state changed",
            client='explainability',
            old_state=old_state,
            new_state=new_state
        )

    def _extract_shap_importances(
        self,
        model: Any,
        evaluation_result: Dict[str, Any],
        cognitive_plan: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Extrai importâncias usando SHAP com features estruturadas."""
        if self._feature_extractor is None or cognitive_plan is None:
            logger.warning("FeatureExtractor not available or no cognitive plan")
            return []

        try:
            # Extrair features estruturadas
            features_result = self._feature_extractor.extract_features(cognitive_plan)
            aggregated_features = features_result['aggregated_features']
            feature_names = sorted(aggregated_features.keys())

            # Usar SHAPExplainer
            shap_result = self.shap_explainer.explain(
                model,
                aggregated_features,
                feature_names
            )

            if 'error' in shap_result:
                error_type = shap_result.get('error', 'unknown')
                if self._metrics:
                    self._metrics.increment_fallback_invocation('explainability', 'shap_error')
                    self._metrics.increment_explainability_errors('shap', error_type)
                return []

            # Retornar importâncias
            return shap_result.get('feature_importances', [])

        except Exception as e:
            logger.warning("Failed to extract SHAP importances", error=str(e))
            if self._metrics:
                self._metrics.increment_fallback_invocation('explainability', 'shap_exception')
                self._metrics.increment_explainability_errors('shap', type(e).__name__)
            return []

    def _extract_lime_importances(
        self,
        model: Any,
        evaluation_result: Dict[str, Any],
        cognitive_plan: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Extrai importâncias usando LIME com features estruturadas."""
        if self._feature_extractor is None or cognitive_plan is None:
            logger.warning("FeatureExtractor not available or no cognitive plan")
            return []

        try:
            # Extrair features estruturadas
            features_result = self._feature_extractor.extract_features(cognitive_plan)
            aggregated_features = features_result['aggregated_features']
            feature_names = sorted(aggregated_features.keys())

            # Usar LIMEExplainer
            lime_result = self.lime_explainer.explain(
                model,
                aggregated_features,
                feature_names
            )

            if 'error' in lime_result:
                error_type = lime_result.get('error', 'unknown')
                if self._metrics:
                    self._metrics.increment_fallback_invocation('explainability', 'lime_error')
                    self._metrics.increment_explainability_errors('lime', error_type)
                return []

            # Retornar importâncias
            return lime_result.get('feature_importances', [])

        except Exception as e:
            logger.warning("Failed to extract LIME importances", error=str(e))
            if self._metrics:
                self._metrics.increment_fallback_invocation('explainability', 'lime_exception')
                self._metrics.increment_explainability_errors('lime', type(e).__name__)
            return []

    def _extract_rule_based_importances(
        self,
        evaluation_result: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extrai importâncias de reasoning_factors (regras explícitas)."""
        reasoning_factors = evaluation_result.get('reasoning_factors', [])

        importances = []
        for factor in reasoning_factors:
            importances.append({
                'feature_name': factor.get('factor_name', 'unknown'),
                'importance': factor.get('weight', 0.0),
                'contribution': self._determine_contribution(factor.get('score', 0.5))
            })

        return importances

    def _extract_heuristic_importances(
        self,
        evaluation_result: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extrai importâncias usando heurísticas simples."""
        return self._extract_rule_based_importances(evaluation_result)

    def _determine_contribution(self, score: float) -> str:
        """Determina tipo de contribuição baseado no score."""
        if score >= 0.6:
            return 'positive'
        elif score <= 0.4:
            return 'negative'
        else:
            return 'neutral'

    def _get_model_version(self, model: Any) -> str:
        """Obtém versão do modelo."""
        if model is None:
            return 'heuristic'

        # Tentar obter versão de atributos do modelo
        if hasattr(model, 'metadata') and hasattr(model.metadata, 'version'):
            return str(model.metadata.version)

        return 'unknown'

    def _get_model_type(self, model: Any) -> str:
        """Obtém tipo do modelo."""
        if model is None:
            return 'heuristic'

        return type(model).__name__

    def _extract_input_features(self, cognitive_plan: Dict[str, Any]) -> Dict[str, float]:
        """Extrai features estruturadas do plano para persistência."""
        if self._feature_extractor:
            try:
                features_result = self._feature_extractor.extract_features(cognitive_plan)
                return features_result['aggregated_features']
            except Exception as e:
                logger.warning("Failed to extract input features", error=str(e))
                return {}
        return {}

    def _extract_feature_names(self, cognitive_plan: Dict[str, Any]) -> List[str]:
        """Extrai nomes de features do plano."""
        input_features = self._extract_input_features(cognitive_plan)
        return sorted(input_features.keys())

    def _build_reasoning_links(
        self,
        reasoning_factors: List[Dict[str, Any]],
        feature_importances: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Constrói mapeamento entre reasoning_factors e SHAP features.

        Args:
            reasoning_factors: Lista de fatores de raciocínio do evaluation_result
            feature_importances: Lista de importâncias SHAP/LIME

        Returns:
            Dicionário mapeando feature_name para reasoning_factor correspondente
        """
        links = {}

        # Criar índice de features por nome normalizado
        feature_index = {
            self._normalize_name(f['feature_name']): f
            for f in feature_importances
        }

        # Para cada reasoning_factor, tentar encontrar feature correspondente
        for factor in reasoning_factors:
            factor_name = factor.get('factor_name', '')
            normalized_factor = self._normalize_name(factor_name)

            # Busca exata
            if normalized_factor in feature_index:
                feature = feature_index[normalized_factor]
                links[feature['feature_name']] = {
                    'factor_name': factor_name,
                    'factor_score': factor.get('score', 0.0),
                    'factor_weight': factor.get('weight', 0.0),
                    'match_type': 'exact'
                }
            else:
                # Busca fuzzy: verificar se alguma parte do nome coincide
                for norm_feature_name, feature in feature_index.items():
                    # Similaridade parcial: factor_name contém feature_name ou vice-versa
                    if normalized_factor in norm_feature_name or norm_feature_name in normalized_factor:
                        links[feature['feature_name']] = {
                            'factor_name': factor_name,
                            'factor_score': factor.get('score', 0.0),
                            'factor_weight': factor.get('weight', 0.0),
                            'match_type': 'fuzzy'
                        }
                        break

        return links

    def _normalize_name(self, name: str) -> str:
        """
        Normaliza nome de feature/factor para comparação.

        Args:
            name: Nome original

        Returns:
            Nome normalizado (lowercase, sem underscores/hífens)
        """
        return name.lower().replace('_', '').replace('-', '').replace(' ', '')

    def _get_background_dataset_hash(self) -> Optional[str]:
        """
        Retorna hash SHA-256 estável e determinístico do background dataset SHAP.

        Usa estatísticas agregadas por coluna ao invés de to_json() para garantir
        estabilidade e performance.
        """
        if self.shap_explainer.background_data is not None:
            try:
                import pandas as pd
                import json

                df = self.shap_explainer.background_data

                # Computar estatísticas estáveis por coluna
                stats = {}
                sorted_columns = sorted(df.columns.tolist())

                for col in sorted_columns:
                    col_stats = {
                        'count': int(df[col].count()),
                        'mean': float(df[col].mean()) if pd.api.types.is_numeric_dtype(df[col]) else None,
                        'std': float(df[col].std()) if pd.api.types.is_numeric_dtype(df[col]) else None,
                        'min': float(df[col].min()) if pd.api.types.is_numeric_dtype(df[col]) else None,
                        'max': float(df[col].max()) if pd.api.types.is_numeric_dtype(df[col]) else None,
                    }
                    # Remover None values para JSON estável
                    stats[col] = {k: v for k, v in col_stats.items() if v is not None}

                # Adicionar metadados de shape
                stats['_meta'] = {
                    'shape': list(df.shape),
                    'columns': sorted_columns
                }

                # Serializar com chaves ordenadas para garantir determinismo
                stats_json = json.dumps(stats, sort_keys=True)

                return hashlib.sha256(stats_json.encode()).hexdigest()

            except Exception as e:
                logger.warning("Failed to compute background dataset hash", error=str(e))
                return None
        return None

    def _persist_detailed_explanation(
        self,
        token: str,
        evaluation_result: Dict[str, Any],
        cognitive_plan: Dict[str, Any],
        metadata: Dict[str, Any]
    ):
        """
        Persiste explicação detalhada no MongoDB.

        Args:
            token: Token de explicabilidade
            evaluation_result: Resultado da avaliação
            cognitive_plan: Plano cognitivo
            metadata: Metadados de explicabilidade
        """
        if self.config.enable_circuit_breaker and self._persist_breaker:
            return self._persist_breaker.call(
                self._persist_detailed_explanation_impl,
                token, evaluation_result, cognitive_plan, metadata
            )
        else:
            return self._persist_detailed_explanation_impl(
                token, evaluation_result, cognitive_plan, metadata
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def _persist_detailed_explanation_impl(
        self,
        token: str,
        evaluation_result: Dict[str, Any],
        cognitive_plan: Dict[str, Any],
        metadata: Dict[str, Any]
    ):
        """
        Implementação interna de _persist_detailed_explanation.

        Args:
            token: Token de explicabilidade
            evaluation_result: Resultado da avaliação
            cognitive_plan: Plano cognitivo
            metadata: Metadados de explicabilidade
        """
        try:
            db = self.mongo_client[self.config.mongodb_database]
            collection = db['explainability_ledger']

            document = {
                'explainability_token': token,
                'evaluation_result': evaluation_result,
                'cognitive_plan_id': cognitive_plan.get('plan_id'),
                'metadata': metadata,
                'timestamp': evaluation_result.get('timestamp')
            }

            collection.insert_one(document)

            # Check if recovering from open state
            if self._was_open:
                if self._metrics:
                    self._metrics.increment_circuit_breaker_success_after_halfopen('explainability')
                self._circuit_breaker_state = 'closed'
                if self._metrics:
                    self._metrics.set_circuit_breaker_state('explainability', 'closed')
                self._was_open = False
                logger.info("Circuit breaker recovered to closed state", client='explainability')

            logger.debug(
                "Detailed explanation persisted",
                token=token
            )

        except Exception as e:
            if self._metrics:
                self._metrics.increment_circuit_breaker_failure('explainability', type(e).__name__)

            logger.warning(
                "Failed to persist detailed explanation",
                token=token,
                error=str(e)
            )
            raise

    def retrieve_explanation(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Recupera explicação detalhada por token.

        Args:
            token: Token de explicabilidade

        Returns:
            Documento de explicação ou None
        """
        if self.config.enable_circuit_breaker and self._retrieve_breaker:
            return self._retrieve_breaker.call(self.retrieve_explanation_impl, token)
        else:
            return self.retrieve_explanation_impl(token)

    def retrieve_explanation_impl(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Implementação interna de retrieve_explanation.

        Args:
            token: Token de explicabilidade

        Returns:
            Documento de explicação ou None
        """
        try:
            db = self.mongo_client[self.config.mongodb_database]
            collection = db['explainability_ledger']

            document = collection.find_one({'explainability_token': token})

            if document:
                document.pop('_id', None)
                return document

            return None

        except Exception as e:
            logger.error(
                "Failed to retrieve explanation",
                token=token,
                error=str(e)
            )
            return None

    def get_circuit_breaker_state(self) -> str:
        """Retorna o estado atual do circuit breaker."""
        return self._circuit_breaker_state
