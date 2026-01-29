"""
BatchEvaluator: Processa múltiplos planos em batch para otimizar throughput.

Amortiza overhead de GPU/CPU ao processar múltiplos planos simultaneamente,
com feature extraction paralela e inferência em batch.
"""

import asyncio
import time
import numpy as np
import pandas as pd
import structlog
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from concurrent.futures import ThreadPoolExecutor

if TYPE_CHECKING:
    from .base_specialist import BaseSpecialist

logger = structlog.get_logger(__name__)


class BatchEvaluator:
    """Avalia múltiplos planos em batch."""

    def __init__(
        self, specialist: "BaseSpecialist", batch_size: int = 32, max_workers: int = 8
    ):
        """
        Inicializa batch evaluator.

        Args:
            specialist: Instância do BaseSpecialist
            batch_size: Tamanho máximo do batch
            max_workers: Número de workers para feature extraction paralela
        """
        self.specialist = specialist
        self.batch_size = batch_size
        self.max_workers = max_workers

        logger.info(
            "BatchEvaluator initialized",
            specialist_type=specialist.specialist_type,
            batch_size=batch_size,
            max_workers=max_workers,
        )

    async def evaluate_batch(
        self,
        cognitive_plans: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Avalia batch de planos cognitivos.

        Args:
            cognitive_plans: Lista de planos cognitivos
            context: Contexto compartilhado (opcional)

        Returns:
            Lista de resultados de avaliação
        """
        start_time = time.time()
        num_plans = len(cognitive_plans)

        if num_plans == 0:
            return []

        logger.info(
            "batch_evaluation_started",
            num_plans=num_plans,
            batch_size=self.batch_size,
            specialist_type=self.specialist.specialist_type,
        )

        try:
            # 1. Extrair features em paralelo
            feature_extraction_start = time.time()
            features_batch = await self._extract_features_batch(cognitive_plans)
            feature_extraction_time = time.time() - feature_extraction_start

            # 2. Inferência em batch
            inference_start = time.time()
            predictions_batch = await self._predict_batch(features_batch)
            inference_time = time.time() - inference_start

            # 3. Pós-processamento individual
            results = []
            for i, (plan, features, prediction) in enumerate(
                zip(cognitive_plans, features_batch, predictions_batch)
            ):
                result = self._post_process_prediction(
                    plan, features, prediction, context or {}
                )
                results.append(result)

            duration = time.time() - start_time

            logger.info(
                "batch_evaluation_completed",
                num_plans=num_plans,
                duration_seconds=round(duration, 3),
                avg_latency_ms=round((duration / num_plans) * 1000, 2),
                feature_extraction_ms=round(feature_extraction_time * 1000, 2),
                inference_ms=round(inference_time * 1000, 2),
                specialist_type=self.specialist.specialist_type,
            )

            # Registrar métrica
            if self.specialist.metrics:
                try:
                    self.specialist.metrics.evaluation_duration_seconds.labels(
                        specialist_type=self.specialist.specialist_type
                    ).observe(
                        duration / num_plans
                    )  # Média por plano
                except Exception as e:
                    logger.warning("Failed to record batch metrics", error=str(e))

            return results

        except Exception as e:
            logger.error(
                "batch_evaluation_failed",
                num_plans=num_plans,
                error=str(e),
                exc_info=True,
            )
            raise

    async def _extract_features_batch(
        self, cognitive_plans: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Extrai features de múltiplos planos em paralelo.

        Args:
            cognitive_plans: Lista de planos cognitivos

        Returns:
            Lista de dicionários de features
        """
        loop = asyncio.get_event_loop()

        def _extract_single(plan: Dict[str, Any]) -> Dict[str, Any]:
            """Extrai features de um único plano."""
            try:
                # Verificar cache primeiro
                if self.specialist.feature_cache:
                    plan_hash = self.specialist._hash_plan(plan)
                    cached = self.specialist.feature_cache.get(plan_hash)
                    if cached:
                        # Ainda precisa gerar embeddings se necessário
                        if self.specialist.model and "embedding_features" not in cached:
                            embedding_features = self.specialist.feature_extractor._extract_embedding_features(
                                plan.get("tasks", [])
                            )
                            cached["embedding_features"] = embedding_features
                        return cached

                # Extrair features
                features = self.specialist.feature_extractor.extract_features(
                    plan, include_embeddings=self.specialist.model is not None
                )

                # Cachear features
                if self.specialist.feature_cache:
                    plan_hash = self.specialist._hash_plan(plan)
                    self.specialist.feature_cache.set(plan_hash, features)

                return features
            except Exception as e:
                logger.warning(
                    "feature_extraction_failed_in_batch",
                    plan_id=plan.get("plan_id"),
                    error=str(e),
                )
                # Retornar features mínimas em caso de erro
                return {
                    "aggregated_features": {},
                    "metadata_features": {},
                    "ontology_features": {},
                    "graph_features": {},
                    "error": str(e),
                }

        # Extrair features em paralelo usando ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                loop.run_in_executor(executor, _extract_single, plan)
                for plan in cognitive_plans
            ]
            features_batch = await asyncio.gather(*futures)

        return features_batch

    async def _predict_batch(
        self, features_batch: List[Dict[str, Any]]
    ) -> List[Optional[np.ndarray]]:
        """
        Executa inferência em batch.

        Args:
            features_batch: Lista de dicionários de features

        Returns:
            Lista de arrays de predições (None para features com erro)
        """
        if not self.specialist.model:
            return [None] * len(features_batch)

        # Filtrar features válidas
        valid_indices = []
        valid_features = []
        for i, features in enumerate(features_batch):
            if "error" not in features and features.get("aggregated_features"):
                valid_indices.append(i)
                valid_features.append(features["aggregated_features"])

        if not valid_features:
            return [None] * len(features_batch)

        # Importar definições de features
        try:
            import sys

            sys.path.insert(0, "/app/ml_pipelines")
            from feature_store.feature_definitions import get_feature_names

            feature_names = get_feature_names()
        except Exception:
            feature_names = None

        # Construir DataFrame batch com schema consistente
        if feature_names:
            batch_df = pd.DataFrame(
                [
                    {name: fd.get(name, 0.0) for name in feature_names}
                    for fd in valid_features
                ]
            )
        else:
            batch_df = pd.DataFrame(valid_features)

        # Inferência batch
        loop = asyncio.get_event_loop()

        def _run_batch_inference():
            try:
                if hasattr(self.specialist.model, "predict_proba"):
                    return self.specialist.model.predict_proba(batch_df)
                else:
                    return self.specialist.model.predict(batch_df)
            except Exception as e:
                logger.error(
                    "batch_inference_failed", error=str(e), batch_size=len(batch_df)
                )
                return None

        with ThreadPoolExecutor(max_workers=1) as executor:
            predictions = await loop.run_in_executor(executor, _run_batch_inference)

        if predictions is None:
            return [None] * len(features_batch)

        # Mapear predições de volta para índices originais
        results = [None] * len(features_batch)
        for i, valid_idx in enumerate(valid_indices):
            if i < len(predictions):
                results[valid_idx] = predictions[
                    i : i + 1
                ]  # Manter shape [1, n_classes]

        return results

    def _post_process_prediction(
        self,
        plan: Dict[str, Any],
        features: Dict[str, Any],
        prediction: Optional[np.ndarray],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Pós-processa predição individual.

        Args:
            plan: Plano cognitivo original
            features: Features extraídas
            prediction: Predição do modelo (ou None)
            context: Contexto compartilhado

        Returns:
            Resultado de avaliação formatado
        """
        plan_id = plan.get("plan_id")

        if prediction is None or "error" in features:
            # Fallback para avaliação heurística
            logger.debug(
                "batch_using_fallback",
                plan_id=plan_id,
                reason="prediction_unavailable"
                if prediction is None
                else "feature_error",
            )
            try:
                result = self.specialist._evaluate_plan_internal(plan, context)
                # Garantir que metadata existe e adicionar campos de batch
                if "metadata" not in result:
                    result["metadata"] = {}
                result["metadata"]["batch_processed"] = True
                result["metadata"]["plan_id"] = plan_id
                result["metadata"]["fallback_used"] = True
                return result
            except Exception as e:
                logger.error("batch_fallback_failed", plan_id=plan_id, error=str(e))
                return {
                    "confidence_score": 0.5,
                    "risk_score": 0.5,
                    "recommendation": "review_required",
                    "reasoning_summary": f"Avaliação falhou: {str(e)}",
                    "reasoning_factors": [],
                    "metadata": {
                        "batch_processed": True,
                        "plan_id": plan_id,
                        "error": str(e),
                    },
                }

        # Usar método existente do specialist para parsing
        features["prediction_method"] = "batch_predict_proba"
        result = self.specialist._parse_model_prediction(prediction, features)

        # Adicionar metadata de batch
        result["metadata"]["batch_processed"] = True
        result["metadata"]["plan_id"] = plan_id

        return result

    def evaluate_batch_sync(
        self,
        cognitive_plans: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Versão síncrona de evaluate_batch.

        Útil para contextos onde async não está disponível.

        Args:
            cognitive_plans: Lista de planos cognitivos
            context: Contexto compartilhado

        Returns:
            Lista de resultados de avaliação
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.evaluate_batch(cognitive_plans, context))
