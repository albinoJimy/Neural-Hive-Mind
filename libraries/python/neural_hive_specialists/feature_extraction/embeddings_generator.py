"""
EmbeddingsGenerator: Gera embeddings semânticos de descrições de tarefas.

Usa modelos de linguagem pré-treinados (sentence-transformers) para gerar
representações vetoriais densas, substituindo análise de keywords.
"""

import hashlib
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

import numpy as np
import structlog

if TYPE_CHECKING:
    from ..metrics import SpecialistMetrics

logger = structlog.get_logger(__name__)


class EmbeddingsGenerator:
    """Gera embeddings semânticos de texto com cache em memória e métricas opcionais."""

    def __init__(
        self,
        model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
        cache_size: int = 1000,
        batch_size: int = 32,
        metrics: Optional["SpecialistMetrics"] = None,
        cache_ttl_seconds: Optional[int] = None,
        cache_enabled: bool = True,
    ):
        """
        Inicializa gerador de embeddings.

        Args:
            model_name: Nome do modelo sentence-transformers
            cache_size: Tamanho máximo do cache LRU em memória
            batch_size: Tamanho do batch para geração de embeddings
            metrics: Exportador opcional de métricas Prometheus
            cache_ttl_seconds: TTL opcional para entradas do cache (None desabilita TTL)
            cache_enabled: Permite desabilitar cache em memória
        """
        self.model_name = model_name
        self.model = None
        self.embedding_dim = None  # Dimensão será determinada dinamicamente
        self.cache_size = cache_size
        self.batch_size = batch_size
        self.metrics = metrics
        self.cache_ttl_seconds = cache_ttl_seconds
        self.cache_enabled = cache_enabled
        self._embedding_cache: "OrderedDict[str, Tuple[np.ndarray, float]]" = (
            OrderedDict()
        )
        self._cache_stats: Dict[str, int] = {"hits": 0, "misses": 0}
        self._load_model()
        logger.info(
            "Embeddings cache initialized",
            cache_enabled=self.cache_enabled,
            cache_size=self.cache_size,
            cache_ttl_seconds=self.cache_ttl_seconds,
            batch_size=self.batch_size,
        )

    def _load_model(self):
        """Carrega modelo de embeddings e determina dimensão dinamicamente."""
        try:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embeddings model", model_name=self.model_name)
            self.model = SentenceTransformer(self.model_name)

            # Determinar dimensão dinamicamente do modelo
            self.embedding_dim = self.model.get_sentence_embedding_dimension()

            logger.info(
                "Embeddings model loaded successfully",
                model_name=self.model_name,
                embedding_dim=self.embedding_dim,
            )
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
            self.model = None
            self.embedding_dim = 384  # Dimensão padrão como fallback
        except Exception as e:
            logger.error(
                "Failed to load embeddings model",
                error=str(e),
                model_name=self.model_name,
            )
            self.model = None
            self.embedding_dim = 384  # Dimensão padrão como fallback

    def _hash_description(self, description: str) -> str:
        """Normaliza e calcula hash da descrição para uso como chave de cache."""
        normalized = description.strip().lower()
        description_hash = hashlib.md5(normalized.encode("utf-8")).hexdigest()
        logger.debug("Description hashed", hash_prefix=description_hash[:8])
        return description_hash

    def _is_cache_entry_valid(self, desc_hash: str) -> bool:
        """Verifica se entrada do cache é válida considerando TTL opcional."""
        if desc_hash not in self._embedding_cache:
            return False

        if self.cache_ttl_seconds is None:
            return True

        _, timestamp = self._embedding_cache[desc_hash]
        if (time.time() - timestamp) <= self.cache_ttl_seconds:
            return True

        # Expirado - remover
        self._embedding_cache.pop(desc_hash, None)
        return False

    def _enforce_cache_limit(self):
        """Evita crescimento ilimitado do cache."""
        while len(self._embedding_cache) > self.cache_size:
            evicted_hash, _ = self._embedding_cache.popitem(last=False)
            logger.warning(
                "Embedding cache evicted entry due to size limit",
                evicted_hash_prefix=evicted_hash[:8],
                cache_size=self.cache_size,
            )

    def _record_cache_hit(self, duration: float):
        """Atualiza contadores e métricas para cache hit."""
        self._cache_stats["hits"] += 1
        if self.metrics:
            self.metrics.increment_embedding_cache_hit()
            self.metrics.observe_embedding_generation_duration(duration, "hit")

    def _record_cache_miss(self, duration: Optional[float] = None):
        """Atualiza contadores e métricas para cache miss."""
        self._cache_stats["misses"] += 1
        if self.metrics:
            self.metrics.increment_embedding_cache_miss()
            if duration is not None:
                self.metrics.observe_embedding_generation_duration(duration, "miss")

    def _log_cache_stats_if_needed(self):
        """Loga estatísticas de cache periodicamente para observabilidade."""
        operations = self._cache_stats["hits"] + self._cache_stats["misses"]
        if operations and operations % 100 == 0:
            hit_ratio = self._cache_stats["hits"] / operations
            logger.info(
                "Embedding cache stats",
                operations=operations,
                hits=self._cache_stats["hits"],
                misses=self._cache_stats["misses"],
                hit_ratio=hit_ratio,
            )

    def _get_embeddings_for_descriptions(
        self, descriptions: List[str]
    ) -> List[np.ndarray]:
        """
        Retorna embeddings preservando ordem, utilizando cache e batch único para misses.
        """
        if self.model is None:
            logger.warning(
                "Model not available, returning zero embeddings",
                embedding_dim=self.embedding_dim,
            )
            return [np.zeros(self.embedding_dim) for _ in descriptions]

        embeddings_result: List[Optional[np.ndarray]] = [None] * len(descriptions)
        descriptions_to_encode: List[str] = []
        hashes_to_encode: List[str] = []
        indices_to_encode: List[int] = []

        for idx, desc in enumerate(descriptions):
            desc_hash = self._hash_description(desc)
            if self.cache_enabled and self._is_cache_entry_valid(desc_hash):
                start_time = time.time()
                embedding, _ = self._embedding_cache[desc_hash]
                self._embedding_cache.move_to_end(desc_hash)
                embeddings_result[idx] = embedding
                self._record_cache_hit(time.time() - start_time)
                logger.debug("Embedding cache hit", hash_prefix=desc_hash[:8])
                continue

            descriptions_to_encode.append(desc)
            hashes_to_encode.append(desc_hash)
            indices_to_encode.append(idx)
            if self.cache_enabled:
                self._record_cache_miss()
            else:
                self._record_cache_miss()
                logger.debug("Embedding cache disabled; treating as miss")

        if descriptions_to_encode:
            encode_start = time.time()
            try:
                encoded = self.model.encode(
                    descriptions_to_encode,
                    convert_to_numpy=True,
                    batch_size=self.batch_size,
                )
            except Exception as e:
                logger.error("Failed to generate embeddings", error=str(e))
                encoded = np.zeros((len(descriptions_to_encode), self.embedding_dim))
            duration = time.time() - encode_start
            if self.metrics:
                self.metrics.observe_embedding_generation_duration(duration, "miss")

            for i, embedding in enumerate(encoded):
                original_idx = indices_to_encode[i]
                embeddings_result[original_idx] = embedding

                if self.cache_enabled:
                    desc_hash = hashes_to_encode[i]
                    self._embedding_cache[desc_hash] = (embedding, time.time())
                    self._embedding_cache.move_to_end(desc_hash)
                    self._enforce_cache_limit()

            if self.metrics:
                self.metrics.set_embedding_cache_size(len(self._embedding_cache))
            logger.info(
                "Embeddings generated for uncached descriptions",
                generated=len(descriptions_to_encode),
                duration_ms=int(duration * 1000),
                batch_size=self.batch_size,
            )

        # Preencher faltantes com zeros (casos de erro)
        for idx, emb in enumerate(embeddings_result):
            if emb is None:
                embeddings_result[idx] = np.zeros(self.embedding_dim)

        self._log_cache_stats_if_needed()
        return embeddings_result

    def get_embeddings(self, descriptions: List[str]) -> List[np.ndarray]:
        """
        Interface pública para obtenção de embeddings em batch preservando ordem.

        Apenas encaminha para o helper interno mantendo semântica existente.
        """
        return self._get_embeddings_for_descriptions(descriptions)

    def generate_task_embeddings(self, tasks: List[Dict[str, Any]]) -> np.ndarray:
        """
        Gera embeddings para descrições de tarefas.

        Args:
            tasks: Lista de tarefas do plano cognitivo

        Returns:
            Array numpy (num_tasks, embedding_dim)
        """
        if not tasks:
            dim = self.embedding_dim or 0
            return np.zeros((0, dim))

        descriptions = [task.get("description", "") for task in tasks]
        embeddings = self._get_embeddings_for_descriptions(descriptions)
        stacked = np.array(embeddings)
        logger.debug("Task embeddings generated", shape=stacked.shape)
        return stacked

    def generate_plan_embedding(self, tasks: List[Dict[str, Any]]) -> np.ndarray:
        """
        Gera embedding agregado do plano inteiro.

        Args:
            tasks: Lista de tarefas do plano cognitivo

        Returns:
            Array numpy (embedding_dim,) - média dos embeddings de tarefas
        """
        if not tasks:
            return np.zeros(self.embedding_dim or 0)

        task_embeddings = self.generate_task_embeddings(tasks)

        # Agregar por média
        plan_embedding = np.mean(task_embeddings, axis=0)

        logger.debug("Plan embedding generated", shape=plan_embedding.shape)
        return plan_embedding

    def calculate_semantic_similarity(self, text1: str, text2: str) -> float:
        """
        Calcula similaridade semântica entre dois textos.

        Args:
            text1: Primeiro texto
            text2: Segundo texto

        Returns:
            Score de similaridade (0.0-1.0)
        """
        if self.model is None:
            return 0.0

        try:
            embeddings = self._get_embeddings_for_descriptions([text1, text2])
            similarity = float(
                np.dot(embeddings[0], embeddings[1])
                / (np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1]))
            )
            return similarity
        except Exception as e:
            logger.error("Failed to calculate similarity", error=str(e))
            return 0.0

    def generate_embeddings_batch(
        self, plans: List[Dict[str, Any]]
    ) -> List[np.ndarray]:
        """
        Gera embeddings em lote para múltiplos planos em uma única chamada ao modelo.
        """
        flattened_descriptions: List[str] = []
        plan_task_counts: List[int] = []

        for plan in plans:
            tasks = plan.get("tasks", [])
            plan_task_counts.append(len(tasks))
            flattened_descriptions.extend(
                [task.get("description", "") for task in tasks]
            )

        embeddings = self._get_embeddings_for_descriptions(flattened_descriptions)

        results: List[np.ndarray] = []
        cursor = 0
        for task_count in plan_task_counts:
            slice_embeddings = embeddings[cursor : cursor + task_count]
            results.append(np.array(slice_embeddings))
            cursor += task_count

        logger.debug(
            "Batch embeddings generated",
            num_plans=len(plans),
            total_tasks=len(flattened_descriptions),
        )
        return results

    def extract_statistical_features(self, embeddings: np.ndarray) -> Dict[str, float]:
        """
        Extrai features estatísticas de embeddings.

        Args:
            embeddings: Array de embeddings (num_samples, embedding_dim)

        Returns:
            Dicionário com features estatísticas
        """
        if embeddings is None or len(embeddings) == 0:
            return {
                "mean_norm": 0.0,
                "std_norm": 0.0,
                "max_norm": 0.0,
                "min_norm": 0.0,
                "avg_diversity": 0.0,
            }

        features = {
            "mean_norm": float(np.mean(np.linalg.norm(embeddings, axis=1))),
            "std_norm": float(np.std(np.linalg.norm(embeddings, axis=1))),
            "max_norm": float(np.max(np.linalg.norm(embeddings, axis=1))),
            "min_norm": float(np.min(np.linalg.norm(embeddings, axis=1))),
        }

        # Diversidade (distância média entre embeddings)
        if len(embeddings) > 1:
            pairwise_distances = []
            for i in range(len(embeddings)):
                for j in range(i + 1, len(embeddings)):
                    dist = np.linalg.norm(embeddings[i] - embeddings[j])
                    pairwise_distances.append(dist)
            features["avg_diversity"] = float(np.mean(pairwise_distances))
        else:
            features["avg_diversity"] = 0.0

        return features

    def get_cache_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas de cache."""
        hits = self._cache_stats["hits"]
        misses = self._cache_stats["misses"]
        total = hits + misses
        hit_ratio = hits / total if total > 0 else 0.0
        return {
            "cache_size": len(self._embedding_cache),
            "cache_max_size": self.cache_size,
            "total_hits": hits,
            "total_misses": misses,
            "hit_ratio": hit_ratio,
        }

    def clear_cache(self):
        """Limpa cache de embeddings e estatísticas."""
        self._embedding_cache.clear()
        self._cache_stats = {"hits": 0, "misses": 0}
        if self.metrics:
            self.metrics.set_embedding_cache_size(0)
