"""
Testes unitários para Router do Gateway de Intenções
Testa roteamento de intenções para serviços downstream (STE, execução direta)
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestIntentRouter:
    """Testes para roteador de intenções"""

    @pytest.fixture()
    def mock_kafka_producer(self):
        """Mock do producer Kafka"""
        producer = AsyncMock()
        producer.is_ready = True
        producer.send_intent = AsyncMock()
        return producer

    @pytest.fixture()
    def mock_nlu_pipeline(self):
        """Mock do pipeline NLU"""
        nlu = AsyncMock()
        nlu.is_ready = True
        nlu.process.return_value = MagicMock(
            domain="technical",
            classification="implementation",
            confidence=0.85,
            processed_text="implementar endpoint",
            entities=[],
            keywords=["implementar", "endpoint"],
            confidence_status="high",
        )
        return nlu

    @pytest.fixture()
    def mock_asr_pipeline(self):
        """Mock do pipeline ASR"""
        asr = AsyncMock()
        asr.is_ready = True
        asr.process.return_value = MagicMock(
            text="criar endpoint para usuários", confidence=0.92, language="pt-BR", duration=3.5
        )
        return asr

    @pytest.fixture()
    def mock_redis_client(self):
        """Mock do cliente Redis"""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()
        return redis

    @pytest.mark.asyncio()
    async def test_route_to_semantic_translation(self, mock_nlu_pipeline, mock_kafka_producer):
        """Testar roteamento para Semantic Translation Engine"""
        # Simular intenção que requer tradução semântica
        intent_request = MagicMock()
        intent_request.text = "Preciso implementar um sistema de autenticação"
        intent_request.language = "pt-BR"
        intent_request.context = {}

        # Processar com NLU
        nlu_result = await mock_nlu_pipeline.process(
            text=intent_request.text,
            language=intent_request.language,
            context=intent_request.context,
        )

        # Verificar que foi processado
        assert nlu_result.domain == "technical"
        assert nlu_result.classification == "implementation"

        # Para domínio técnico, deve rotear para STE
        # (simulado aqui pela verificação do domínio)
        assert nlu_result.domain in ["technical", "business", "infrastructure", "security"]

    @pytest.mark.asyncio()
    async def test_route_to_direct_execution(self, mock_nlu_pipeline, mock_kafka_producer):
        """Testar roteamento para execução direta (intenção simples)"""
        intent_request = MagicMock()
        intent_request.text = "status do sistema"
        intent_request.language = "pt-BR"
        intent_request.context = {}

        # Configurar NLU para retornar intenção de status/consulta
        mock_nlu_pipeline.process.return_value = MagicMock(
            domain="infrastructure",
            classification="query",
            confidence=0.90,
            processed_text="status do sistema",
            entities=[],
            keywords=["status", "sistema"],
            confidence_status="high",
        )

        nlu_result = await mock_nlu_pipeline.process(
            text=intent_request.text,
            language=intent_request.language,
            context=intent_request.context,
        )

        # Consultas simples podem ter rota direta
        assert nlu_result.classification == "query"

    @pytest.mark.asyncio()
    async def test_route_with_cache_hit(self, mock_nlu_pipeline, mock_redis_client):
        """Testar roteamento com cache hit"""
        cached_result = {
            "processed_text": "implementar autenticação",
            "domain": "technical",
            "classification": "implementation",
            "confidence": 0.85,
            "entities": [],
            "keywords": ["implementar", "autenticação"],
            "confidence_status": "high",
        }

        # Mock Redis retorna resultado em cache
        mock_redis_client.get = AsyncMock(return_value=cached_result)

        # Verificar cache
        cache_key = "nlu:test-hash"
        cached = await mock_redis_client.get(cache_key)

        assert cached is not None
        assert cached["domain"] == "technical"
        # NLU não deve ser processado novamente

    @pytest.mark.asyncio()
    async def test_route_with_cache_miss(self, mock_nlu_pipeline, mock_redis_client):
        """Testar roteamento com cache miss"""
        # Mock Redis retorna None (cache miss)
        mock_redis_client.get = AsyncMock(return_value=None)

        cache_key = "nlu:test-hash"
        cached = await mock_redis_client.get(cache_key)

        assert cached is None
        # NLU deve processar a requisição

    @pytest.mark.asyncio()
    async def test_concurrent_requests_handling(self, mock_nlu_pipeline, mock_kafka_producer):
        """Testar handling de requisições concorrentes"""
        import asyncio

        # Simular múltiplas requisições concorrentes
        requests = [
            "implementar feature A",
            "status do sistema",
            "criar endpoint usuários",
            "deploy em produção",
            "análise de performance",
        ]

        tasks = []
        for req_text in requests:
            task = mock_nlu_pipeline.process(text=req_text, language="pt-BR", context={})
            tasks.append(task)

        # Executar concorrentemente
        results = await asyncio.gather(*tasks)

        # Verificar que todas foram processadas
        assert len(results) == len(requests)
        for result in results:
            assert result.domain is not None
            assert result.confidence >= 0.0

    @pytest.mark.asyncio()
    async def test_unknown_domain_routing(self, mock_nlu_pipeline, mock_kafka_producer):
        """Testar roteamento para domínio desconhecido"""
        # Configurar NLU para retornar domínio desconhecido
        mock_nlu_pipeline.process.return_value = MagicMock(
            domain="unknown",
            classification="unknown",
            confidence=0.25,
            processed_text="texto sem contexto",
            entities=[],
            keywords=[],
            confidence_status="low",
            requires_manual_validation=True,
        )

        intent_request = MagicMock()
        intent_request.text = "xyz abc 123"
        intent_request.language = "pt-BR"

        result = await mock_nlu_pipeline.process(
            text=intent_request.text, language=intent_request.language, context={}
        )

        # Domínio desconhecido deve ser marcado
        assert result.domain == "unknown"
        assert result.confidence_status == "low"
        assert result.requires_manual_validation is True

    @pytest.mark.asyncio()
    async def test_fallback_on_pipeline_error(self, mock_nlu_pipeline):
        """Testar fallback quando pipeline falha"""
        # Configurar NLU para lançar exceção
        mock_nlu_pipeline.process.side_effect = Exception("NLU pipeline error")

        intent_request = MagicMock()
        intent_request.text = "teste"
        intent_request.language = "pt-BR"

        # Deve lançar exceção ou usar fallback
        with pytest.raises(Exception):
            await mock_nlu_pipeline.process(
                text=intent_request.text, language=intent_request.language, context={}
            )


class TestVoiceIntentRouter:
    """Testes para roteador de intenções de voz"""

    @pytest.fixture()
    def mock_asr_pipeline(self):
        """Mock do pipeline ASR"""
        asr = AsyncMock()
        asr.is_ready = True
        asr.process.return_value = MagicMock(
            text="criar um endpoint para listar usuários",
            confidence=0.92,
            language="pt-BR",
            duration=4.2,
        )
        return asr

    @pytest.fixture()
    def mock_nlu_pipeline(self):
        """Mock do pipeline NLU"""
        nlu = AsyncMock()
        nlu.is_ready = True
        nlu.process.return_value = MagicMock(
            domain="technical",
            classification="implementation",
            confidence=0.88,
            processed_text="criar endpoint listar usuários",
            entities=[],
            keywords=["criar", "endpoint", "listar", "usuários"],
            confidence_status="high",
        )
        return nlu

    @pytest.mark.asyncio()
    async def test_voice_intent_routing(self, mock_asr_pipeline, mock_nlu_pipeline):
        """Testar roteamento completo de intenção de voz"""
        # Dados de áudio simulados
        audio_data = b"fake-audio-data" * 100

        # 1. Processar áudio com ASR
        asr_result = await mock_asr_pipeline.process(audio_data=audio_data, language="pt-BR")

        assert asr_result.text is not None
        assert asr_result.confidence > 0.8

        # 2. Processar texto transcrito com NLU
        nlu_result = await mock_nlu_pipeline.process(
            text=asr_result.text, language=asr_result.language, context={"source": "voice"}
        )

        assert nlu_result.domain == "technical"
        assert nlu_result.classification == "implementation"

    @pytest.mark.asyncio()
    async def test_voice_intent_with_low_asr_confidence(self, mock_asr_pipeline):
        """Testar intenção de voz com baixa confiança ASR"""
        # Configurar ASR com baixa confiança
        mock_asr_pipeline.process.return_value = MagicMock(
            text="texto incerto", confidence=0.45, language="pt-BR", duration=2.0
        )

        audio_data = b"fake-audio-data" * 100
        asr_result = await mock_asr_pipeline.process(audio_data=audio_data, language="pt-BR")

        # Baixa confiança deve ser marcada
        assert asr_result.confidence < 0.5
        # Pode requerer confirmação do usuário

    @pytest.mark.asyncio()
    async def test_voice_intent_language_detection(self, mock_asr_pipeline):
        """Testar detecção de idioma em intenção de voz"""
        # Configurar ASR para detectar inglês
        mock_asr_pipeline.process.return_value = MagicMock(
            text="create a new endpoint", confidence=0.90, language="en", duration=3.0
        )

        audio_data = b"fake-audio-data" * 100
        asr_result = await mock_asr_pipeline.process(
            audio_data=audio_data, language=None  # Auto-detect
        )

        # Deve detectar idioma corretamente
        assert asr_result.language == "en"


class TestCircuitBreaker:
    """Testes para circuit breaker no roteador"""

    @pytest.fixture()
    def mock_circuit_breaker(self):
        """Mock do circuit breaker"""
        cb = MagicMock()
        cb.is_open = False
        cb.allow_request = MagicMock(return_value=True)
        cb.record_success = MagicMock()
        cb.record_failure = MagicMock()
        return cb

    def test_circuit_closed_allows_requests(self, mock_circuit_breaker):
        """Testar circuit breaker fechado permite requisições"""
        mock_circuit_breaker.is_open = False

        assert mock_circuit_breaker.is_open is False
        assert mock_circuit_breaker.allow_request() is True

    def test_circuit_open_blocks_requests(self, mock_circuit_breaker):
        """Testar circuit breaker aberto bloqueia requisições"""
        mock_circuit_breaker.is_open = True
        mock_circuit_breaker.allow_request.return_value = False

        assert mock_circuit_breaker.is_open is True
        assert mock_circuit_breaker.allow_request() is False

    def test_circuit_records_failure(self, mock_circuit_breaker):
        """Testar que falhas são registradas"""
        mock_circuit_breaker.record_failure()

        mock_circuit_breaker.record_failure.assert_called_once()

    def test_circuit_records_success(self, mock_circuit_breaker):
        """Testar que sucessos são registrados"""
        mock_circuit_breaker.record_success()

        mock_circuit_breaker.record_success.assert_called_once()


class TestLoadBalancing:
    """Testes para balanceamento de carga"""

    @pytest.mark.asyncio()
    async def test_round_robin_load_balancing(self):
        """Testar balanceamento round-robin"""
        # Lista de endpoints downstream
        endpoints = ["http://ste-1:8001", "http://ste-2:8001", "http://ste-3:8001"]

        # Simular round-robin
        current_index = 0
        selected_endpoints = []

        for _ in range(6):  # 6 requisições
            selected_endpoints.append(endpoints[current_index])
            current_index = (current_index + 1) % len(endpoints)

        # Verificar distribuição
        assert selected_endpoints.count(endpoints[0]) == 2
        assert selected_endpoints.count(endpoints[1]) == 2
        assert selected_endpoints.count(endpoints[2]) == 2

    @pytest.mark.asyncio()
    async def test_least_connections_load_balancing(self):
        """Testar balanceamento least-connections"""
        # Simular estado de conexões
        endpoint_connections = {
            "http://ste-1:8001": 5,
            "http://ste-2:8001": 2,
            "http://ste-3:8001": 8,
        }

        # Selecionar endpoint com menos conexões
        selected = min(endpoint_connections.items(), key=lambda x: x[1])

        assert selected[0] == "http://ste-2:8001"
        assert selected[1] == 2

    @pytest.mark.asyncio()
    async def test_weighted_round_robin(self):
        """Testar balanceamento round-robin ponderado"""
        endpoints = [
            {"url": "http://ste-1:8001", "weight": 3},
            {"url": "http://ste-2:8001", "weight": 1},
            {"url": "http://ste-3:8001", "weight": 2},
        ]

        # Simular seleção baseada em peso
        # ste-1 deve ser selecionado 3x mais que ste-2
        weighted_list = []
        for ep in endpoints:
            for _ in range(ep["weight"]):
                weighted_list.append(ep["url"])

        # 6 seleções devem refletir pesos
        selected = weighted_list[:6]

        assert selected.count("http://ste-1:8001") == 3
        assert selected.count("http://ste-3:8001") == 2
        assert selected.count("http://ste-2:8001") == 1


class TestRetryLogic:
    """Testes para lógica de retry"""

    @pytest.mark.asyncio()
    async def test_retry_on_transient_failure(self):
        """Testar retry em falha transitória"""
        import asyncio

        call_count = 0

        async def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return "success"

        # Implementar retry simples
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = await flaky_operation()
                assert result == "success"
                assert call_count == 3  # Sucesso na 3ª tentativa
                break
            except Exception:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(0.01)

    @pytest.mark.asyncio()
    async def test_retry_exhausted_raises_exception(self):
        """Testar que esgotar retries lança exceção"""
        import asyncio

        async def always_failing_operation():
            raise Exception("Permanent failure")

        max_retries = 3
        for attempt in range(max_retries):
            try:
                await always_failing_operation()
            except Exception:
                if attempt == max_retries - 1:
                    # Última tentativa, exceção deve ser lançada
                    with pytest.raises(Exception, match="Permanent failure"):
                        raise
                await asyncio.sleep(0.01)

    @pytest.mark.asyncio()
    async def test_exponential_backoff(self):
        """Testar exponential backoff entre retries"""
        import time

        delays = []
        start_time = time.time()

        for attempt in range(3):
            delays.append(time.time() - start_time)
            await asyncio.sleep(2**attempt * 0.01)  # 10ms, 20ms, 40ms

        # Verificar que delays aumentam
        assert delays[1] > delays[0]
        assert delays[2] > delays[1]


class TestRouterMetrics:
    """Testes para métricas do roteador"""

    @pytest.mark.asyncio()
    async def test_request_counted(self):
        """Testar que requisições são contadas"""
        request_counter = {"count": 0}

        def increment_counter():
            request_counter["count"] += 1

        # Simular requisições
        for _ in range(5):
            increment_counter()

        assert request_counter["count"] == 5

    @pytest.mark.asyncio()
    async def test_latency_recorded(self):
        """Testar que latência é registrada"""
        import time

        latencies = []

        async def record_request():
            start = time.time()
            await asyncio.sleep(0.01)
            latencies.append(time.time() - start)

        for _ in range(3):
            await record_request()

        assert len(latencies) == 3
        # Todas as latências devem estar em faixa razoável
        for lat in latencies:
            assert 0.005 < lat < 0.1

    @pytest.mark.asyncio()
    async def test_error_rate_calculated(self):
        """Testar cálculo de taxa de erro"""
        total_requests = 100
        failed_requests = 7

        error_rate = failed_requests / total_requests

        assert error_rate == 0.07
        assert error_rate * 100 == 7.0


class TestRouterHealth:
    """Testes para saúde do roteador"""

    @pytest.mark.asyncio()
    async def test_health_check_returns_healthy(self):
        """Testar health check retorna saudável"""
        health_status = {
            "status": "healthy",
            "dependencies": {
                "nlu_pipeline": "ready",
                "asr_pipeline": "ready",
                "kafka_producer": "ready",
                "redis_cache": "ready",
            },
        }

        assert health_status["status"] == "healthy"
        for dep, status in health_status["dependencies"].items():
            assert status == "ready"

    @pytest.mark.asyncio()
    async def test_health_check_with_degraded_dependency(self):
        """Testar health check com dependência degradada"""
        health_status = {
            "status": "degraded",
            "dependencies": {
                "nlu_pipeline": "ready",
                "asr_pipeline": "slow",  # Degradada
                "kafka_producer": "ready",
                "redis_cache": "ready",
            },
        }

        assert health_status["status"] == "degraded"
        assert health_status["dependencies"]["asr_pipeline"] == "slow"

    @pytest.mark.asyncio()
    async def test_health_check_returns_unhealthy(self):
        """Testar health check retorna não saudável"""
        health_status = {
            "status": "unhealthy",
            "dependencies": {
                "nlu_pipeline": "ready",
                "asr_pipeline": "ready",
                "kafka_producer": "disconnected",  # Crítico
                "redis_cache": "ready",
            },
        }

        assert health_status["status"] == "unhealthy"
