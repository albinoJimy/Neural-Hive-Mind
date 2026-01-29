"""
ABTestingSpecialist: Especialista que executa A/B testing de modelos ML.

Este módulo implementa um especialista que compara dois modelos em produção
usando distribuição determinística baseada em hash para seleção de variante.
"""

import hashlib
from typing import Any, Dict, Optional, Tuple

import structlog
from opentelemetry import trace

from .base_specialist import BaseSpecialist
from .config import SpecialistConfig

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class ABTestingSpecialist(BaseSpecialist):
    """
    Especialista que executa A/B testing de modelos ML.

    Carrega dois modelos (A e B) e distribui tráfego deterministicamente
    baseado em hash do request. Coleta métricas por variante para comparação.

    Atributos:
        model_a (Any): Modelo A (baseline)
        model_b (Any): Modelo B (challenger)
        model_a_metadata (Dict): Metadados do modelo A
        model_b_metadata (Dict): Metadados do modelo B
    """

    def __init__(self, config: SpecialistConfig):
        """
        Inicializa ABTestingSpecialist.

        Args:
            config: Configuração do especialista com parâmetros de A/B testing
        """
        super().__init__(config)
        self.model_a: Optional[Any] = None
        self.model_b: Optional[Any] = None
        self.model_a_metadata: Dict = {}
        self.model_b_metadata: Dict = {}

    def _load_model(self) -> Optional[Any]:
        """
        Carrega ambos os modelos (A e B) para A/B testing.

        Returns:
            Modelo A como padrão (para compatibilidade com BaseSpecialist)

        Raises:
            Exception: Se modelo A não puder ser carregado
        """
        if not self.config.enable_ab_testing:
            logger.warning("A/B testing não habilitado, usando modelo único")
            return super()._load_model()

        # Determinar nomes dos modelos
        model_a_name = self.config.ab_test_model_a_name or self.config.mlflow_model_name
        model_b_name = self.config.ab_test_model_b_name

        if not model_b_name:
            logger.error(
                "ab_test_model_b_name não configurado, A/B testing desabilitado"
            )
            return super()._load_model()

        logger.info(
            "Carregando modelos para A/B testing",
            model_a=model_a_name,
            model_a_stage=self.config.ab_test_model_a_stage,
            model_b=model_b_name,
            model_b_stage=self.config.ab_test_model_b_stage,
        )

        # Carregar modelo A
        try:
            with tracer.start_as_current_span("ab_test.load_model_a") as span:
                span.set_attribute("model_name", model_a_name)
                span.set_attribute("stage", self.config.ab_test_model_a_stage)

                self.model_a = self.mlflow_client.load_model(
                    model_a_name, self.config.ab_test_model_a_stage
                )

                if self.model_a:
                    # Obter metadados completos do modelo, incluindo version e run_id
                    metadata = self.mlflow_client.get_model_metadata(
                        model_a_name, self.config.ab_test_model_a_stage
                    )
                    self.model_a_metadata = {
                        "name": model_a_name,
                        "stage": self.config.ab_test_model_a_stage,
                        "version": metadata.get("version"),
                        "run_id": metadata.get("run_id"),
                    }
                    logger.info(
                        "Modelo A carregado com sucesso",
                        model=model_a_name,
                        version=self.model_a_metadata.get("version"),
                    )
                else:
                    logger.error("Falha ao carregar modelo A", model=model_a_name)
                    return None

        except Exception as e:
            logger.error("Erro ao carregar modelo A", model=model_a_name, error=str(e))
            return None

        # Carregar modelo B
        try:
            with tracer.start_as_current_span("ab_test.load_model_b") as span:
                span.set_attribute("model_name", model_b_name)
                span.set_attribute("stage", self.config.ab_test_model_b_stage)

                self.model_b = self.mlflow_client.load_model(
                    model_b_name, self.config.ab_test_model_b_stage
                )

                if self.model_b:
                    # Obter metadados completos do modelo, incluindo version e run_id
                    metadata = self.mlflow_client.get_model_metadata(
                        model_b_name, self.config.ab_test_model_b_stage
                    )
                    self.model_b_metadata = {
                        "name": model_b_name,
                        "stage": self.config.ab_test_model_b_stage,
                        "version": metadata.get("version"),
                        "run_id": metadata.get("run_id"),
                    }
                    logger.info(
                        "Modelo B carregado com sucesso",
                        model=model_b_name,
                        version=self.model_b_metadata.get("version"),
                    )
                else:
                    logger.warning(
                        "Falha ao carregar modelo B, A/B testing desabilitado",
                        model=model_b_name,
                    )
                    # Continuar com apenas modelo A

        except Exception as e:
            logger.error(
                "Erro ao carregar modelo B, A/B testing desabilitado",
                model=model_b_name,
                error=str(e),
            )
            # Continuar com apenas modelo A

        # Registrar traffic split
        self.metrics.set_ab_test_traffic_split(self.config.ab_test_traffic_split)

        logger.info(
            "A/B testing configurado",
            has_model_a=self.model_a is not None,
            has_model_b=self.model_b is not None,
            traffic_split=self.config.ab_test_traffic_split,
        )

        # Retornar modelo A como padrão
        return self.model_a

    def _select_model_for_request(
        self, plan_id: str, intent_id: str
    ) -> Tuple[str, Optional[Any]]:
        """
        Seleciona modelo (A ou B) para request usando hash determinístico.

        Garante que o mesmo plano sempre vai para a mesma variante.

        Args:
            plan_id: ID do plano cognitivo
            intent_id: ID da intenção

        Returns:
            Tupla (variant_name, model) onde variant_name é 'model_a' ou 'model_b'
        """
        # Se modelo B não disponível, usar sempre modelo A
        if not self.model_b:
            return ("model_a", self.model_a)

        with tracer.start_as_current_span("ab_test.select_model") as span:
            # Calcular hash determinístico
            hash_value = self._calculate_hash_value(plan_id, intent_id)

            span.set_attribute("ab_test.hash_value", hash_value)
            span.set_attribute(
                "ab_test.traffic_split", self.config.ab_test_traffic_split
            )

            # Selecionar variante baseado em hash
            if hash_value < self.config.ab_test_traffic_split:
                variant = "model_a"
                model = self.model_a
            else:
                variant = "model_b"
                model = self.model_b

            span.set_attribute("ab_test.variant", variant)

            logger.debug(
                "Variante selecionada",
                plan_id=plan_id[:8],
                intent_id=intent_id[:8] if intent_id else None,
                hash_value=hash_value,
                variant=variant,
            )

            return (variant, model)

    def _calculate_hash_value(self, plan_id: str, intent_id: str = "") -> float:
        """
        Calcula hash determinístico e normaliza para 0.0-1.0.

        Args:
            plan_id: ID do plano cognitivo
            intent_id: ID da intenção (opcional)

        Returns:
            Valor normalizado entre 0.0 e 1.0
        """
        # Concatenar IDs e seed
        hash_input = f"{plan_id}{intent_id}{self.config.ab_test_hash_seed}"

        # Calcular SHA-256
        hash_bytes = hashlib.sha256(hash_input.encode("utf-8")).digest()

        # Usar primeiros 8 bytes e normalizar para 0.0-1.0
        hash_int = int.from_bytes(hash_bytes[:8], byteorder="big")
        hash_value = hash_int / (2**64 - 1)  # Normalizar para [0, 1]

        return hash_value

    def _predict_with_model(self, cognitive_plan: dict) -> Optional[dict]:
        """
        Executa predição com modelo selecionado via A/B test.

        Args:
            cognitive_plan: Plano cognitivo para avaliar

        Returns:
            Resultado da predição com metadados de A/B test
        """
        if not self.model_a:
            logger.warning("Modelo A não carregado")
            return None

        # Extrair IDs para seleção de variante
        plan_id = cognitive_plan.get("plan_id", "")
        intent_id = cognitive_plan.get("intent_id", "")

        if not plan_id:
            # Gerar ID temporário se não fornecido
            import uuid

            plan_id = str(uuid.uuid4())
            logger.warning(
                "plan_id não fornecido, usando ID temporário", plan_id=plan_id
            )

        # Selecionar modelo
        variant, model = self._select_model_for_request(plan_id, intent_id)

        if not model:
            logger.error("Modelo selecionado não disponível", variant=variant)
            return None

        with tracer.start_as_current_span("ab_test.predict") as span:
            span.set_attribute("ab_test.variant", variant)

            # Executar predição
            import time

            start_time = time.time()

            try:
                # Reusar o pipeline de inferência do BaseSpecialist temporariamente alterando self.model
                original_model = self.model
                try:
                    self.model = model
                    result = super()._predict_with_model(cognitive_plan)
                finally:
                    self.model = original_model

                if not result:
                    # Tentar fallback para outro modelo
                    if variant == "model_b" and self.model_a:
                        logger.warning("Fazendo fallback para modelo A")
                        return self._predict_with_fallback_model(
                            cognitive_plan, "model_a", self.model_a
                        )
                    elif variant == "model_a" and self.model_b:
                        logger.warning("Fazendo fallback para modelo B")
                        return self._predict_with_fallback_model(
                            cognitive_plan, "model_b", self.model_b
                        )
                    return None

                # Registrar métricas específicas de A/B testing
                duration = time.time() - start_time
                self.metrics.observe_ab_test_variant_processing_time(variant, duration)
                self.metrics.increment_ab_test_variant_usage(variant)

                # Observar confidence e risk por variante
                self.metrics.observe_ab_test_variant_confidence(
                    variant, result.get("confidence_score", 0.5)
                )
                self.metrics.observe_ab_test_variant_risk(
                    variant, result.get("risk_score", 0.5)
                )

                # Incrementar contador de recomendação
                recommendation = result.get("recommendation", "review_required")
                self.metrics.increment_ab_test_recommendation(variant, recommendation)

                # Adicionar metadados de A/B test
                model_metadata = (
                    self.model_a_metadata
                    if variant == "model_a"
                    else self.model_b_metadata
                )
                result["metadata"] = result.get("metadata", {})
                result["metadata"].update(
                    {
                        "ab_test_variant": variant,
                        "ab_test_model_name": model_metadata["name"],
                        "ab_test_model_stage": model_metadata["stage"],
                        "ab_test_model_version": model_metadata.get("version"),
                        "ab_test_model_run_id": model_metadata.get("run_id"),
                        "ab_test_traffic_split": self.config.ab_test_traffic_split,
                        "ab_test_hash_value": self._calculate_hash_value(
                            plan_id, intent_id
                        ),
                    }
                )

                logger.info(
                    "Predição A/B test concluída",
                    variant=variant,
                    confidence=result.get("confidence_score"),
                    duration_seconds=duration,
                )

                return result

            except Exception as e:
                logger.error(
                    "Erro na predição com modelo selecionado",
                    variant=variant,
                    error=str(e),
                )

                # Tentar fallback para outro modelo
                if variant == "model_b" and self.model_a:
                    logger.warning("Fazendo fallback para modelo A")
                    return self._predict_with_fallback_model(
                        cognitive_plan, "model_a", self.model_a
                    )
                elif variant == "model_a" and self.model_b:
                    logger.warning("Fazendo fallback para modelo B")
                    return self._predict_with_fallback_model(
                        cognitive_plan, "model_b", self.model_b
                    )

                return None

    def _predict_with_fallback_model(
        self, cognitive_plan: dict, variant: str, model: Any
    ) -> Optional[dict]:
        """
        Executa predição com modelo de fallback.

        Args:
            cognitive_plan: Plano cognitivo
            variant: Nome da variante
            model: Modelo a usar

        Returns:
            Resultado da predição
        """
        try:
            # Reusar o pipeline de inferência do BaseSpecialist
            original_model = self.model
            try:
                self.model = model
                result = super()._predict_with_model(cognitive_plan)
            finally:
                self.model = original_model

            if result:
                result["metadata"] = result.get("metadata", {})
                result["metadata"].update(
                    {"ab_test_variant": f"{variant}_fallback", "ab_test_fallback": True}
                )

            return result

        except Exception as e:
            logger.error("Erro no modelo de fallback", variant=variant, error=str(e))
            return None

    def get_ab_test_statistics(self) -> Dict[str, Any]:
        """
        Retorna estatísticas do A/B test.

        Returns:
            Dict com estatísticas de ambas as variantes:
            - Total de avaliações por variante
            - Concordância com consenso (se disponível)
            - Confidence score médio
            - Latência média
            - Distribuição de recomendações
            - Análise estatística (se amostras suficientes)
        """
        try:
            # Coletar métricas do Prometheus registry local via self.metrics
            stats = {
                "model_a": self._collect_variant_stats("model_a"),
                "model_b": self._collect_variant_stats("model_b"),
                "statistical_significance": {
                    "p_value": None,
                    "is_significant": False,
                    "winner": None,
                },
                "recommendation": "insufficient_data",
            }

            # Calcular significância estatística se ambas variantes têm amostras suficientes
            min_samples = (
                self.config.ab_test_minimum_sample_size
                if hasattr(self.config, "ab_test_minimum_sample_size")
                else 30
            )

            sample_a = stats["model_a"]["sample_size"]
            sample_b = stats["model_b"]["sample_size"]

            if sample_a >= min_samples and sample_b >= min_samples:
                try:
                    from scipy.stats import chi2_contingency

                    # Simular tabela de contingência usando recommendation distribution
                    # Como proxy: usar approve vs não-approve
                    approve_a = stats["model_a"]["recommendation_distribution"].get(
                        "approve", 0
                    )
                    total_a = stats["model_a"]["sample_size"]
                    reject_a = total_a - approve_a

                    approve_b = stats["model_b"]["recommendation_distribution"].get(
                        "approve", 0
                    )
                    total_b = stats["model_b"]["sample_size"]
                    reject_b = total_b - approve_b

                    contingency_table = [[approve_a, reject_a], [approve_b, reject_b]]

                    chi2, p_value, dof, expected = chi2_contingency(contingency_table)

                    is_significant = p_value < 0.05

                    # Determinar vencedor baseado em confidence médio
                    if is_significant:
                        winner = (
                            "model_b"
                            if stats["model_b"]["avg_confidence"]
                            > stats["model_a"]["avg_confidence"]
                            else "model_a"
                        )
                        stats["recommendation"] = f"deploy_{winner}"
                    else:
                        winner = None
                        stats["recommendation"] = "continue_testing"

                    stats["statistical_significance"] = {
                        "p_value": float(p_value),
                        "chi2": float(chi2),
                        "is_significant": is_significant,
                        "winner": winner,
                    }

                except ImportError:
                    logger.warning(
                        "scipy não disponível, não é possível calcular significância estatística"
                    )
                    stats["recommendation"] = "scipy_not_available"
                except Exception as e:
                    logger.error(
                        "Erro ao calcular significância estatística", error=str(e)
                    )
            else:
                stats[
                    "recommendation"
                ] = f"insufficient_data (need {min_samples} per variant, have {sample_a}/{sample_b})"

            logger.info(
                "Estatísticas de A/B test calculadas",
                sample_a=sample_a,
                sample_b=sample_b,
                recommendation=stats["recommendation"],
            )

            return stats

        except Exception as e:
            logger.error(
                "Erro ao coletar estatísticas de A/B test", error=str(e), exc_info=True
            )
            return {
                "error": str(e),
                "model_a": {"sample_size": 0},
                "model_b": {"sample_size": 0},
                "statistical_significance": {
                    "p_value": None,
                    "is_significant": False,
                    "winner": None,
                },
                "recommendation": "error",
            }

    def _collect_variant_stats(self, variant: str) -> Dict[str, Any]:
        """
        Coleta estatísticas de uma variante do Prometheus registry.

        Args:
            variant: Nome da variante ('model_a' ou 'model_b')

        Returns:
            Dict com estatísticas da variante
        """
        try:
            # Coletar sample size
            sample_size = 0
            try:
                sample_size = int(
                    self.metrics.ab_test_variant_usage_total.labels(
                        self.specialist_type, variant
                    )._value.get()
                )
            except Exception:
                logger.debug(f"Não foi possível obter sample_size para {variant}")

            # Coletar agreement rate
            agreement_rate = 0.0
            try:
                agreement_rate = (
                    self.metrics.ab_test_variant_consensus_agreement.labels(
                        self.specialist_type, variant
                    )._value.get()
                )
            except Exception:
                logger.debug(f"Não foi possível obter agreement_rate para {variant}")

            # Coletar média de confidence (via histogram)
            avg_confidence = 0.0
            try:
                histogram = self.metrics.ab_test_variant_confidence_score.labels(
                    self.specialist_type, variant
                )
                # Calcular média a partir do histogram
                if hasattr(histogram, "_sum") and hasattr(histogram, "_count"):
                    count = histogram._count.get()
                    if count > 0:
                        avg_confidence = histogram._sum.get() / count
            except Exception:
                logger.debug(f"Não foi possível obter avg_confidence para {variant}")

            # Coletar média de latência (via histogram)
            avg_latency = 0.0
            try:
                histogram = self.metrics.ab_test_variant_processing_time_seconds.labels(
                    self.specialist_type, variant
                )
                if hasattr(histogram, "_sum") and hasattr(histogram, "_count"):
                    count = histogram._count.get()
                    if count > 0:
                        avg_latency = histogram._sum.get() / count
            except Exception:
                logger.debug(f"Não foi possível obter avg_latency para {variant}")

            # Coletar distribuição de recomendações
            recommendation_distribution = {}
            for recommendation in [
                "approve",
                "reject",
                "review_required",
                "conditional",
            ]:
                try:
                    count = int(
                        self.metrics.ab_test_variant_recommendation_distribution.labels(
                            self.specialist_type, variant, recommendation
                        )._value.get()
                    )
                    if count > 0:
                        recommendation_distribution[recommendation] = count
                except Exception:
                    pass

            return {
                "sample_size": sample_size,
                "agreement_rate": float(agreement_rate),
                "avg_confidence": float(avg_confidence),
                "avg_latency": float(avg_latency),
                "recommendation_distribution": recommendation_distribution,
            }

        except Exception as e:
            logger.error(
                "Erro ao coletar estatísticas da variante",
                variant=variant,
                error=str(e),
            )
            return {
                "sample_size": 0,
                "agreement_rate": 0.0,
                "avg_confidence": 0.0,
                "avg_latency": 0.0,
                "recommendation_distribution": {},
                "error": str(e),
            }
