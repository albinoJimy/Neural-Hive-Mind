"""
Testes de performance para NLP Processor

Verifica latência e throughput das operações de extração NLP.
"""

import pytest
import time
import statistics
from unittest.mock import AsyncMock


class TestNLPExtractionLatency:
    """Testes de latência de extração NLP"""

    @pytest.fixture
    async def nlp_processor(self):
        """Fixture que cria e inicializa NLPProcessor"""
        from src.services.nlp_processor import NLPProcessor
        processor = NLPProcessor(redis_client=None)
        await processor.initialize()
        return processor

    @pytest.fixture
    def sample_texts(self):
        """Textos de exemplo para benchmark"""
        return [
            "Criar API REST para gerenciamento de produtos com autenticação JWT",
            "Atualizar sistema de cache Redis para melhorar performance",
            "Buscar todos os pedidos realizados nos últimos 30 dias",
            "Deletar registros antigos da base de dados MongoDB",
            "Transformar dados de CSV para formato JSON normalizado",
            "Build a new GraphQL API for user management with authentication",
            "Update the database schema to support new features",
            "Search for all active users in the system",
            "Migrate legacy data to the new microservices architecture",
            "Create an event-driven system using Kafka and Redis Streams"
        ]

    @pytest.mark.asyncio
    async def test_extract_keywords_latency_p95(self, nlp_processor, sample_texts):
        """Testa que extração de keywords tem latência P95 < 50ms"""
        latencies = []

        # Warm-up
        for text in sample_texts[:3]:
            nlp_processor.extract_keywords(text)

        # Benchmark
        iterations = 100
        for i in range(iterations):
            text = sample_texts[i % len(sample_texts)]

            start = time.perf_counter()
            nlp_processor.extract_keywords(text, max_keywords=10)
            end = time.perf_counter()

            latencies.append((end - start) * 1000)  # ms

        p95 = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
        p50 = statistics.median(latencies)
        avg = statistics.mean(latencies)

        print(f"\nKeywords Extraction - P50: {p50:.2f}ms, P95: {p95:.2f}ms, Avg: {avg:.2f}ms")

        # SLO: P95 < 50ms
        assert p95 < 50, f"Keywords extraction P95 latency {p95:.2f}ms exceeds 50ms SLO"

    @pytest.mark.asyncio
    async def test_extract_objectives_latency_p95(self, nlp_processor, sample_texts):
        """Testa que extração de objectives tem latência P95 < 50ms"""
        latencies = []

        # Warm-up
        for text in sample_texts[:3]:
            nlp_processor.extract_objectives(text)

        # Benchmark
        iterations = 100
        for i in range(iterations):
            text = sample_texts[i % len(sample_texts)]

            start = time.perf_counter()
            nlp_processor.extract_objectives(text)
            end = time.perf_counter()

            latencies.append((end - start) * 1000)  # ms

        p95 = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
        p50 = statistics.median(latencies)
        avg = statistics.mean(latencies)

        print(f"\nObjectives Extraction - P50: {p50:.2f}ms, P95: {p95:.2f}ms, Avg: {avg:.2f}ms")

        # SLO: P95 < 50ms
        assert p95 < 50, f"Objectives extraction P95 latency {p95:.2f}ms exceeds 50ms SLO"

    @pytest.mark.asyncio
    async def test_extract_entities_latency_p95(self, nlp_processor, sample_texts):
        """Testa que extração de entidades tem latência P95 < 100ms"""
        latencies = []

        # Warm-up
        for text in sample_texts[:3]:
            nlp_processor.extract_entities_advanced(text)

        # Benchmark
        iterations = 100
        for i in range(iterations):
            text = sample_texts[i % len(sample_texts)]

            start = time.perf_counter()
            nlp_processor.extract_entities_advanced(text)
            end = time.perf_counter()

            latencies.append((end - start) * 1000)  # ms

        p95 = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
        p50 = statistics.median(latencies)
        avg = statistics.mean(latencies)

        print(f"\nEntities Extraction - P50: {p50:.2f}ms, P95: {p95:.2f}ms, Avg: {avg:.2f}ms")

        # SLO: P95 < 100ms (entidades são mais custosas)
        assert p95 < 100, f"Entities extraction P95 latency {p95:.2f}ms exceeds 100ms SLO"

    @pytest.mark.asyncio
    async def test_full_extraction_latency_p95(self, nlp_processor, sample_texts):
        """Testa latência total de todas as extrações combinadas"""
        latencies = []

        # Warm-up
        for text in sample_texts[:3]:
            nlp_processor.extract_keywords(text)
            nlp_processor.extract_objectives(text)
            nlp_processor.extract_entities_advanced(text)

        # Benchmark
        iterations = 50
        for i in range(iterations):
            text = sample_texts[i % len(sample_texts)]

            start = time.perf_counter()
            nlp_processor.extract_keywords(text, max_keywords=10)
            nlp_processor.extract_objectives(text)
            nlp_processor.extract_entities_advanced(text)
            end = time.perf_counter()

            latencies.append((end - start) * 1000)  # ms

        p95 = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
        p50 = statistics.median(latencies)
        avg = statistics.mean(latencies)

        print(f"\nFull Extraction - P50: {p50:.2f}ms, P95: {p95:.2f}ms, Avg: {avg:.2f}ms")

        # SLO: P95 < 150ms (para manter Semantic Translation Engine < 200ms total)
        assert p95 < 150, f"Full extraction P95 latency {p95:.2f}ms exceeds 150ms SLO"


class TestNLPCachePerformance:
    """Testes de performance do cache NLP"""

    @pytest.fixture
    def mock_redis_client(self):
        """Mock do RedisClient com cache simulado"""
        cache = {}

        async def get_cached(key):
            return cache.get(key)

        async def set_cached(key, value, ttl=600):
            cache[key] = value

        mock = AsyncMock()
        mock.get_cached_query = AsyncMock(side_effect=get_cached)
        mock.cache_query_result = AsyncMock(side_effect=set_cached)
        return mock

    @pytest.fixture
    async def nlp_processor_with_cache(self, mock_redis_client):
        """NLPProcessor com cache simulado"""
        from src.services.nlp_processor import NLPProcessor
        processor = NLPProcessor(redis_client=mock_redis_client)
        processor._cache_ttl = 600
        await processor.initialize()
        return processor

    @pytest.mark.asyncio
    async def test_cache_hit_latency(self, nlp_processor_with_cache):
        """Testa que cache hit tem latência < 5ms"""
        text = "Criar API REST para produtos"

        # Primeira chamada (cache miss)
        await nlp_processor_with_cache._cache_extraction(
            nlp_processor_with_cache._generate_cache_key('keywords', text),
            {'keywords': ['api', 'rest', 'produto']}
        )

        # Medir latência do cache hit
        latencies = []
        for _ in range(50):
            start = time.perf_counter()
            result = await nlp_processor_with_cache._get_cached_extraction(
                nlp_processor_with_cache._generate_cache_key('keywords', text)
            )
            end = time.perf_counter()

            if result:  # Cache hit
                latencies.append((end - start) * 1000)

        if latencies:
            avg_latency = statistics.mean(latencies)
            print(f"\nCache Hit Avg Latency: {avg_latency:.2f}ms")

            # SLO: Cache hit < 5ms
            assert avg_latency < 5, f"Cache hit latency {avg_latency:.2f}ms exceeds 5ms SLO"


class TestNLPThroughput:
    """Testes de throughput do NLP"""

    @pytest.fixture
    async def nlp_processor(self):
        """Fixture que cria e inicializa NLPProcessor"""
        from src.services.nlp_processor import NLPProcessor
        processor = NLPProcessor(redis_client=None)
        await processor.initialize()
        return processor

    @pytest.mark.asyncio
    async def test_keywords_throughput(self, nlp_processor):
        """Testa throughput de extração de keywords"""
        text = "Criar API REST para gerenciamento de produtos"

        # Warm-up
        for _ in range(10):
            nlp_processor.extract_keywords(text)

        # Benchmark
        iterations = 500
        start = time.perf_counter()

        for _ in range(iterations):
            nlp_processor.extract_keywords(text, max_keywords=5)

        end = time.perf_counter()
        duration = end - start

        throughput = iterations / duration
        print(f"\nKeywords Throughput: {throughput:.0f} req/s")

        # Mínimo: 100 req/s
        assert throughput >= 100, f"Keywords throughput {throughput:.0f} req/s below 100 req/s minimum"

    @pytest.mark.asyncio
    async def test_objectives_throughput(self, nlp_processor):
        """Testa throughput de extração de objectives"""
        text = "Criar API REST para gerenciamento de produtos"

        # Warm-up
        for _ in range(10):
            nlp_processor.extract_objectives(text)

        # Benchmark
        iterations = 500
        start = time.perf_counter()

        for _ in range(iterations):
            nlp_processor.extract_objectives(text)

        end = time.perf_counter()
        duration = end - start

        throughput = iterations / duration
        print(f"\nObjectives Throughput: {throughput:.0f} req/s")

        # Mínimo: 100 req/s
        assert throughput >= 100, f"Objectives throughput {throughput:.0f} req/s below 100 req/s minimum"
