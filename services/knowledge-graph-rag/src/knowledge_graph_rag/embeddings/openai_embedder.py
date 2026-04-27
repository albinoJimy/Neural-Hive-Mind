"""Serviço de embeddings OpenAI com cache usando neural_hive_llm."""

from typing import List, Optional

import structlog
from neural_hive_llm import LLMClient, LLMProvider

from knowledge_graph_rag.config.settings import get_settings
from knowledge_graph_rag.embeddings.cache import EmbeddingCache
from knowledge_graph_rag.embeddings.models import (
    EmbeddingBatchResponse,
    EmbeddingResponse,
)

logger = structlog.get_logger()
settings = get_settings()


class OpenAIEmbedder:
    """Gerador de embeddings usando neural_hive_llm."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        dimensions: Optional[int] = None,
        cache: Optional[EmbeddingCache] = None,
        batch_size: int = 100,
    ):
        """Inicializa o gerador de embeddings.

        Args:
            api_key: Chave da API OpenAI
            model: Modelo de embedding
            dimensions: Dimensões do vetor
            cache: Cache de embeddings
            batch_size: Tamanho do lote para processamento
        """
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.embedding_model
        self.dimensions = dimensions or settings.embedding_dimensions
        self.batch_size = batch_size
        self.cache = cache
        self._client: Optional[LLMClient] = None

    async def connect(self):
        """Inicializa cliente neural_hive_llm e cache."""
        if not self.api_key:
            logger.warning("openai_no_api_key")
            return

        self._client = LLMClient(
            provider=LLMProvider.OPENAI,
            api_key=self.api_key,
            model=self.model,
        )
        await self._client.start()

        if self.cache:
            await self.cache.connect()

        logger.info(
            "openai_embedder_initialized",
            model=self.model,
            dimensions=self.dimensions,
            cache_enabled=self.cache is not None,
        )

    async def close(self):
        """Fecha conexões."""
        if self.cache:
            await self.cache.close()

        if self._client:
            await self._client.stop()

    async def embed(self, text: str, use_cache: bool = True) -> List[float]:
        """Gera embedding para um texto.

        Args:
            text: Texto para gerar embedding
            use_cache: Usar cache se disponível

        Returns:
            Vetor de embedding

        Raises:
            ValueError: se texto vazio
            RuntimeError: se API indisponível
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        # Verificar cache
        if use_cache and self.cache and await self.cache.exists(text, self.model):
            cached = await self.cache.get(text, self.model)
            if cached:
                logger.debug("embedding_cache_hit", text_length=len(text))
                return cached

        # Gerar embedding via neural_hive_llm
        if not self._client:
            await self.connect()

        try:
            response = await self._client.generate_embeddings(
                input=text,
                model=self.model,
                dimensions=self.dimensions,
            )

            embedding = response.data[0].embedding

            # Armazenar no cache
            if use_cache and self.cache:
                await self.cache.set(text, embedding, self.model)

            logger.debug(
                "embedding_generated",
                text_length=len(text),
                dimensions=len(embedding),
            )

            return embedding

        except Exception as e:
            logger.error("embedding_generation_error", error=str(e))
            raise RuntimeError(f"Failed to generate embedding: {e}") from e

    async def embed_batch(
        self,
        texts: List[str],
        use_cache: bool = True,
    ) -> List[List[float]]:
        """Gera embeddings para múltiplos textos.

        Args:
            texts: Lista de textos
            use_cache: Usar cache se disponível

        Returns:
            Lista de vetores de embedding

        Raises:
            ValueError: se lista vazia
            RuntimeError: se API indisponível
        """
        if not texts:
            raise ValueError("Texts list cannot be empty")

        all_embeddings: List[List[float]] = []
        texts_to_fetch: List[tuple[int, str]] = []  # (index, text)

        # Verificar cache primeiro
        if use_cache and self.cache:
            for idx, text in enumerate(texts):
                if not text or not text.strip():
                    all_embeddings.append([])  # Placeholder para texto vazio
                    continue

                cached = await self.cache.get(text, self.model)
                if cached:
                    all_embeddings.append(cached)
                    logger.debug("embedding_batch_cache_hit", index=idx)
                else:
                    texts_to_fetch.append((idx, text))
        else:
            texts_to_fetch = [
                (idx, text) for idx, text in enumerate(texts) if text and text.strip()
            ]

        # Buscar embeddings não cacheados
        if texts_to_fetch:
            # Processar em lotes
            for i in range(0, len(texts_to_fetch), self.batch_size):
                batch = texts_to_fetch[i : i + self.batch_size]
                batch_texts = [text for _, text in batch]

                batch_embeddings = await self._fetch_batch(batch_texts)

                # Armazenar no cache e adicionar aos resultados
                for (idx, text), embedding in zip(batch, batch_embeddings):
                    if use_cache and self.cache:
                        await self.cache.set(text, embedding, self.model)

                    # Inserir na posição correta
                    while len(all_embeddings) <= idx:
                        all_embeddings.append([])
                    all_embeddings[idx] = embedding

        logger.info(
            "embedding_batch_completed",
            total=len(texts),
            cached=sum(1 for e in all_embeddings if e != []),
            fetched=len(texts_to_fetch),
        )

        return all_embeddings

    async def _fetch_batch(self, texts: List[str]) -> List[List[float]]:
        """Busca embeddings da API em lote usando neural_hive_llm.

        Args:
            texts: Textos para processar

        Returns:
            Lista de embeddings
        """
        if not self._client:
            await self.connect()

        try:
            response = await self._client.generate_embeddings(
                input=texts,
                model=self.model,
                dimensions=self.dimensions,
            )

            # neural_hive_llm retorna data ordenado por index
            embeddings = [item.embedding for item in response.data]

            logger.debug(
                "embedding_batch_fetched",
                count=len(embeddings),
                dimensions=len(embeddings[0]) if embeddings else 0,
            )

            return embeddings

        except Exception as e:
            logger.error("embedding_batch_fetch_error", error=str(e))
            raise RuntimeError(f"Failed to fetch batch embeddings: {e}") from e

    @staticmethod
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        """Calcula similaridade de cosseno entre dois vetores.

        Args:
            a: Primeiro vetor
            b: Segundo vetor

        Returns:
            Similaridade de cosseno (-1 a 1)

        Raises:
            ValueError: se vetores de tamanhos diferentes
        """
        if len(a) != len(b):
            raise ValueError(f"Vectors must have same length: {len(a)} != {len(b)}")

        try:
            dot_product = sum(x * y for x, y in zip(a, b))
            norm_a = sum(x * x for x in a) ** 0.5
            norm_b = sum(y * y for y in b) ** 0.5

            if norm_a == 0 or norm_b == 0:
                return 0.0

            return dot_product / (norm_a * norm_b)

        except Exception as e:
            logger.error("cosine_similarity_error", error=str(e))
            raise RuntimeError(f"Failed to calculate cosine similarity: {e}") from e

    async def to_response(self, text: str, use_cache: bool = True) -> EmbeddingResponse:
        """Gera embedding e retorna como response model.

        Args:
            text: Texto para gerar embedding
            use_cache: Usar cache se disponível

        Returns:
            EmbeddingResponse
        """
        embedding = await self.embed(text, use_cache=use_cache)

        return EmbeddingResponse(
            embedding=embedding,
            model=self.model,
            dimensions=len(embedding),
        )

    async def to_batch_response(
        self,
        texts: List[str],
        use_cache: bool = True,
    ) -> EmbeddingBatchResponse:
        """Gera embeddings e retorna como response model.

        Args:
            texts: Lista de textos
            use_cache: Usar cache se disponível

        Returns:
            EmbeddingBatchResponse
        """
        embeddings = await self.embed_batch(texts, use_cache=use_cache)

        dimensions = len(embeddings[0]) if embeddings and embeddings[0] else 0

        return EmbeddingBatchResponse(
            embeddings=embeddings,
            model=self.model,
            dimensions=dimensions,
        )

    @property
    def is_connected(self) -> bool:
        """Verifica se está conectado à API.

        Returns:
            True se conectado
        """
        return self._client is not None
