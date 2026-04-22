"""Serviço de inferência ML."""

import asyncio
import time
from typing import Any, Optional

import structlog

from src.cache.redis_cache import InferenceCache, RedisCache, hash_features
from src.models.inference import (
    InferenceRequest,
    InferenceResponse,
    InferenceStatus,
    ModelMetadata,
    ModelType,
)

logger = structlog.get_logger(__name__)


class MLModelRegistry:
    """Registro de modelos ML carregados na memória."""

    def __init__(self) -> None:
        """Inicializa registro de modelos."""
        self._models: dict[str, Any] = {}
        self._metadata: dict[str, ModelMetadata] = {}
        self._logger = logger

    async def load_model(self, name: str, version: str = "latest") -> ModelMetadata:
        """Carrega um modelo ML na memória.

        Args:
            name: Nome do modelo
            version: Versão do modelo

        Returns:
            Metadados do modelo carregado
        """
        key = f"{name}:{version}"

        if key in self._models:
            self._logger.info("model_already_loaded", model=key)
            return self._metadata[key]

        self._logger.info("loading_model", model=name, version=version)

        # Simulação de carregamento de modelo
        # Em produção, carregaria modelo pickle/onnx/torchserve/etc
        await asyncio.sleep(0.1)  # Simular I/O

        # Criar modelo mock baseado no tipo
        model_type = self._infer_model_type(name)
        self._models[key] = {
            "type": model_type,
            "name": name,
            "version": version,
        }

        metadata = ModelMetadata(
            name=name,
            version=version,
            model_type=model_type,
            feature_names=self._get_feature_names(model_type),
        )
        self._metadata[key] = metadata

        self._logger.info("model_loaded", model=key, model_type=model_type)
        return metadata

    def get_model(self, name: str, version: str = "latest") -> Optional[Any]:
        """Retorna modelo carregado.

        Args:
            name: Nome do modelo
            version: Versão do modelo

        Returns:
            Modelo ou None se não carregado
        """
        key = f"{name}:{version}"
        return self._models.get(key)

    def _infer_model_type(self, name: str) -> ModelType:
        """Infere tipo do modelo pelo nome.

        Args:
            name: Nome do modelo

        Returns:
            Tipo inferido do modelo
        """
        name_lower = name.lower()
        if "classify" in name_lower or "class" in name_lower:
            return ModelType.CLASSIFICATION
        elif "regress" in name_lower:
            return ModelType.REGRESSION
        elif "cluster" in name_lower:
            return ModelType.CLUSTERING
        elif "anomaly" in name_lower or "detect" in name_lower:
            return ModelType.ANOMALY_DETECTION
        elif "recommend" in name_lower:
            return ModelType.RECOMMENDATION
        return ModelType.CLASSIFICATION

    def _get_feature_names(self, model_type: ModelType) -> list[str]:
        """Retorna nomes de features esperados por tipo.

        Args:
            model_type: Tipo do modelo

        Returns:
            Lista de nomes de features
        """
        # Features genéricas - em produção viria do schema do modelo
        return [
            "feature_1",
            "feature_2",
            "feature_3",
            "text_input",
            "categorical_feature",
        ]


class InferenceService:
    """Serviço de execução de inferências ML."""

    def __init__(
        self,
        model_registry: Optional[MLModelRegistry] = None,
        redis_cache: Optional[RedisCache] = None,
        cache_ttl_seconds: int = 3600,
    ) -> None:
        """Inicializa serviço de inferência.

        Args:
            model_registry: Registro de modelos (opcional)
            redis_cache: Cache Redis distribuído (opcional)
            cache_ttl_seconds: TTL do cache em segundos
        """
        self._model_registry = model_registry or MLModelRegistry()
        self._redis_cache = redis_cache
        self._inference_cache: Optional[InferenceCache] = (
            InferenceCache(redis_cache) if redis_cache else None
        )
        self._cache_ttl = cache_ttl_seconds
        # Fallback para cache em memória se Redis não disponível
        self._memory_cache: dict[str, InferenceResponse] = {}
        self._memory_cache_timestamps: dict[str, float] = {}
        self._logger = logger

    async def predict(
        self,
        request: InferenceRequest,
        use_cache: bool = True,
    ) -> InferenceResponse:
        """Executa predição ML.

        Args:
            request: Requisição de inferência
            use_cache: Se deve usar cache

        Returns:
            Resposta da inferência
        """
        start_time = time.time()

        # Verificar cache Redis primeiro
        if use_cache and self._inference_cache:
            features_hash = hash_features(request.features)
            cached = await self._inference_cache.get_inference_result(
                request.model_name,
                request.model_version,
                features_hash,
            )
            if cached:
                self._logger.info("redis_cache_hit", request_id=request.request_id)
                return InferenceResponse(**cached, cached=True)

        # Fallback para cache em memória
        if use_cache:
            cached = self._get_from_memory_cache(request.request_id)
            if cached:
                self._logger.info("memory_cache_hit", request_id=request.request_id)
                cached.cached = True
                return cached

        # Carregar modelo se necessário
        model_key = f"{request.model_name}:{request.model_version}"
        model = self._model_registry.get_model(request.model_name, request.model_version)
        if not model:
            await self._model_registry.load_model(request.model_name, request.model_version)
            model = self._model_registry.get_model(request.model_name, request.model_version)

        # Executar predição
        try:
            prediction, confidence = await self._execute_prediction(model, request)
            latency_ms = int((time.time() - start_time) * 1000)

            response = InferenceResponse(
                request_id=request.request_id,
                model_name=request.model_name,
                model_version=request.model_version,
                status=InferenceStatus.COMPLETED,
                prediction=prediction,
                confidence=confidence,
                latency_ms=latency_ms,
                cached=False,
            )

            # Salvar no cache Redis
            if use_cache and self._inference_cache:
                features_hash = hash_features(request.features)
                await self._inference_cache.set_inference_result(
                    request.model_name,
                    request.model_version,
                    features_hash,
                    response.model_dump(),
                    self._cache_ttl,
                )

            # Salvar no cache em memória (fallback)
            if use_cache:
                self._save_to_memory_cache(request.request_id, response)

            self._logger.info(
                "inference_completed",
                request_id=request.request_id,
                model=request.model_name,
                latency_ms=latency_ms,
            )
            return response

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            self._logger.error(
                "inference_failed",
                request_id=request.request_id,
                error=str(e),
            )
            return InferenceResponse(
                request_id=request.request_id,
                model_name=request.model_name,
                model_version=request.model_version,
                status=InferenceStatus.FAILED,
                error=str(e),
                latency_ms=latency_ms,
            )

    async def _execute_prediction(
        self, model: dict[str, Any], request: InferenceRequest
    ) -> tuple[dict[str, Any], Optional[float]]:
        """Executa predição do modelo.

        Args:
            model: Modelo ML
            request: Requisição de inferência

        Returns:
            Tupla de (predição, confiança)
        """
        model_type = model.get("type", ModelType.CLASSIFICATION)

        # Simulação de predição
        # Em produção, chamaria model.predict() ou equivalente
        await asyncio.sleep(0.01)  # Simular compute

        if model_type == ModelType.CLASSIFICATION:
            # Predição de classificação
            prediction = {
                "class": "positive" if request.features.get("feature_1", 0) > 0.5 else "negative",
                "probabilities": {
                    "positive": 0.75,
                    "negative": 0.25,
                },
            }
            confidence = 0.75

        elif model_type == ModelType.REGRESSION:
            # Predição de regressão
            value = request.features.get("feature_1", 0) * 2.5 + 1.0
            prediction = {"value": value, "units": "score"}
            confidence = 0.85

        elif model_type == ModelType.ANOMALY_DETECTION:
            # Detecção de anomalia
            anomaly_score = abs(request.features.get("feature_1", 0) - 0.5)
            is_anomaly = anomaly_score > 0.3
            prediction = {
                "is_anomaly": is_anomaly,
                "anomaly_score": float(anomaly_score),
            }
            confidence = 0.9

        else:
            # Default genérico
            prediction = {
                "result": "processed",
                "feature_count": len(request.features),
            }
            confidence = 0.7

        return prediction, confidence

    def _get_from_memory_cache(self, request_id: str) -> Optional[InferenceResponse]:
        """Busca resposta do cache em memória.

        Args:
            request_id: ID da requisição

        Returns:
            Resposta cacheada ou None
        """
        if request_id not in self._memory_cache:
            return None

        # Verificar TTL
        timestamp = self._memory_cache_timestamps.get(request_id, 0)
        if time.time() - timestamp > self._cache_ttl:
            del self._memory_cache[request_id]
            del self._memory_cache_timestamps[request_id]
            return None

        return self._memory_cache[request_id]

    def _save_to_memory_cache(self, request_id: str, response: InferenceResponse) -> None:
        """Salva resposta no cache em memória.

        Args:
            request_id: ID da requisição
            response: Resposta a cachear
        """
        self._memory_cache[request_id] = response
        self._memory_cache_timestamps[request_id] = time.time()

        # Limpar cache antigo se necessário
        if len(self._memory_cache) > 1000:
            oldest_key = min(self._memory_cache_timestamps, key=self._memory_cache_timestamps.get)
            del self._memory_cache[oldest_key]
            del self._memory_cache_timestamps[oldest_key]

    async def clear_cache(self) -> None:
        """Limpa todo o cache (Redis e memória)."""
        # Limpar cache Redis
        if self._redis_cache:
            try:
                await self._redis_cache._redis.flushdb()
                self._logger.info("redis_cache_cleared")
            except Exception as e:
                self._logger.warning("redis_cache_clear_failed", error=str(e))

        # Limpar cache em memória
        self._memory_cache.clear()
        self._memory_cache_timestamps.clear()
        self._logger.info("memory_cache_cleared")

    async def get_cache_stats(self) -> dict[str, Any]:
        """Retorna estatísticas do cache.

        Returns:
            Estatísticas do cache
        """
        stats = {
            "memory_cache_size": len(self._memory_cache),
            "cache_ttl_seconds": self._cache_ttl,
        }

        # Adicionar estatísticas Redis se disponível
        if self._redis_cache:
            redis_stats = await self._redis_cache.get_stats()
            stats["redis"] = redis_stats

        return stats

    async def connect_redis(self, redis_url: str) -> None:
        """Conecta ao Redis.

        Args:
            redis_url: URL de conexão Redis
        """
        self._redis_cache = RedisCache(redis_url=redis_url)
        await self._redis_cache.connect()
        self._inference_cache = InferenceCache(self._redis_cache)
        self._logger.info("redis_cache_enabled")

    async def disconnect_redis(self) -> None:
        """Desconecta do Redis."""
        if self._redis_cache:
            await self._redis_cache.disconnect()
            self._inference_cache = None
            self._logger.info("redis_cache_disabled")
