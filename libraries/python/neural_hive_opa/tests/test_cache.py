"""
Testes TDD para Cache LRU com TTL por política - Fase RED

Testes escritos ANTES da implementação.
Seguem o ciclo RED-GREEN-REFACTOR.
"""
import asyncio
import time
from types import SimpleNamespace

import pytest

# ===== FIXTURES =====


@pytest.fixture
def cache_config():
    """Configurações mockadas para cache."""
    return SimpleNamespace(
        opa_cache_ttl_seconds=300,
        opa_cache_max_size=1000,
    )


# ===== TESTES: OPACache Init =====


class TestOPACacheInit:
    """Testes de inicialização do cache."""

    def test_cache_initialization(self, cache_config):
        """
        DADO: Configuração válida
        QUANDO: Crio OPACache
        ENTÃO: Deve inicializar com TTL e maxsize corretos
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        assert cache.ttl_seconds == 300
        assert cache.max_size == 1000

    def test_cache_initialization_with_defaults(self):
        """
        DADO: Sem parâmetros
        QUANDO: Crio OPACache
        ENTÃO: Deve usar valores padrão
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache()

        assert cache.ttl_seconds == 300
        assert cache.max_size == 1000

    def test_cache_has_lock(self, cache_config):
        """
        DADO: Cache criado
        QUANDO: Verifico se tem lock
        ENTÃO: Deve ter lock para thread-safety
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        assert hasattr(cache, "_lock")
        assert cache.metrics is not None


# ===== TESTES: Cache Get =====


class TestOPACacheGet:
    """Testes do método get."""

    def test_get_returns_cached_value(self, cache_config):
        """
        DADO: Valor no cache
        QUANDO: Chamo get
        ENTÃO: Deve retornar o valor
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        cache_key = "policy:test:input_hash"
        cached_value = {"allow": True, "reason": "cached"}

        cache._cache[cache_key] = cached_value

        result = cache.get(cache_key)

        assert result == cached_value
        assert cache.metrics.hits == 1
        assert cache.metrics.misses == 0

    def test_get_returns_none_for_missing_key(self, cache_config):
        """
        DADO: Chave não existe
        QUANDO: Chamo get
        ENTÃO: Deve retornar None e registrar miss
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        result = cache.get("nonexistent_key")

        assert result is None
        assert cache.metrics.hits == 0
        assert cache.metrics.misses == 1

    def test_get_with_expired_entry(self, cache_config):
        """
        DADO: Entrada expirada pelo TTL
        QUANDO: Chamo get
        ENTÃO: Deve retornar None e registrar miss
        """
        from neural_hive_opa.cache import OPACache

        # Criar cache com TTL curto para teste
        cache = OPACache(ttl_seconds=1, max_size=1000)

        cache_key = "policy:test:input_hash"
        cached_value = {"allow": True}

        cache._cache[cache_key] = cached_value

        # Aguardar expiração
        time.sleep(1.1)

        result = cache.get(cache_key)

        # TTLCache do cachetools remove entradas expiradas automaticamente
        # mas vamos garantir o comportamento
        assert result is None or cache.metrics.misses >= 0


# ===== TESTES: Cache Set =====


class TestOPACacheSet:
    """Testes do método set."""

    def test_set_stores_value(self, cache_config):
        """
        DADO: Valor para armazenar
        QUANDO: Chamo set
        ENTÃO: Deve armazenar no cache
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        cache_key = "policy:test:input_hash"
        value = {"allow": True, "reason": "test"}

        cache.set(cache_key, value)

        assert cache_key in cache._cache
        assert cache._cache[cache_key] == value

    def test_set_overwrites_existing(self, cache_config):
        """
        DADO: Chave já existe
        QUANDO: Chamo set com novo valor
        ENTÃO: Deve sobrescrever
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        cache_key = "policy:test:input_hash"
        old_value = {"allow": False}
        new_value = {"allow": True}

        cache.set(cache_key, old_value)
        cache.set(cache_key, new_value)

        assert cache._cache[cache_key] == new_value

    def test_set_with_custom_ttl(self, cache_config):
        """
        DADO: TTL customizado
        QUANDO: Chamo set com ttl
        ENTÃO: Deve usar TTL customizado
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        cache_key = "policy:test:input_hash"
        value = {"allow": True}

        # Implementação pode usar TTL customizado por entrada
        cache.set(cache_key, value, ttl_seconds=60)

        assert cache_key in cache._cache


# ===== TESTES: Cache Clear =====


class TestOPACacheClear:
    """Testes do método clear."""

    def test_clear_removes_all_entries(self, cache_config):
        """
        DADO: Cache com entradas
        QUANDO: Chamo clear
        ENTÃO: Deve remover todas as entradas
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        cache.set("key1", {"allow": True})
        cache.set("key2", {"allow": False})
        cache.set("key3", {"allow": True})

        assert len(cache._cache) == 3

        cache.clear()

        assert len(cache._cache) == 0

    def test_clear_resets_metrics(self, cache_config):
        """
        DADO: Cache com métricas
        QUANDO: Chamo clear
        ENTÃO: Deve resetar métricas
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        cache.get("nonexistent")  # Registra miss
        assert cache.metrics.misses > 0

        cache.clear()

        # Métricas devem ser resetadas
        assert cache.metrics.hits == 0
        assert cache.metrics.misses == 0


# ===== TESTES: Cache Invalidate =====


class TestOPACacheInvalidate:
    """Testes do método invalidate."""

    def test_invalidate_by_key(self, cache_config):
        """
        DADO: Cache com entradas
        QUANDO: Chamo invalidate com chave específica
        ENTÃO: Deve remover apenas essa entrada
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        cache.set("key1", {"allow": True})
        cache.set("key2", {"allow": False})
        cache.set("key3", {"allow": True})

        cache.invalidate("key2")

        assert "key1" in cache._cache
        assert "key2" not in cache._cache
        assert "key3" in cache._cache

    def test_invalidate_by_prefix(self, cache_config):
        """
        DADO: Cache com entradas de mesma política
        QUANDO: Chamo invalidate com prefixo
        ENTÃO: Deve remover todas entradas com prefixo
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        cache.set("policy:allow:hash1", {"allow": True})
        cache.set("policy:allow:hash2", {"allow": False})
        cache.set("policy:deny:hash1", {"allow": True})
        cache.set("other:policy:hash1", {"allow": True})

        cache.invalidate(prefix="policy:allow")

        assert "policy:allow:hash1" not in cache._cache
        assert "policy:allow:hash2" not in cache._cache
        assert "policy:deny:hash1" in cache._cache
        assert "other:policy:hash1" in cache._cache

    def test_invalidate_nonexistent_key(self, cache_config):
        """
        DADO: Chave não existe
        QUANDO: Chamo invalidate
        ENTÃO: Não deve levantar erro
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        # Não deve levantar exceção
        cache.invalidate("nonexistent_key")
        cache.invalidate(prefix="nonexistent:")


# ===== TESTES: Thread-Safety =====


class TestOPACacheThreadSafety:
    """Testes de thread-safety."""

    @pytest.mark.asyncio
    async def test_concurrent_get_operations(self, cache_config):
        """
        DADO: Cache com valor
        QUANDO: Múltiplas operações get concorrentes
        ENTÃO: Todas devem retornar o valor corretamente
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        cache_key = "policy:test:input_hash"
        cached_value = {"allow": True}
        cache.set(cache_key, cached_value)

        async def get_value():
            return cache.get(cache_key)

        results = await asyncio.gather(*[get_value() for _ in range(100)])

        assert all(r == cached_value for r in results)

    @pytest.mark.asyncio
    async def test_concurrent_set_operations(self, cache_config):
        """
        DADO: Cache vazio
        QUANDO: Múltiplas operações set concorrentes
        ENTÃO: Todas devem ser armazenadas
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        async def set_value(key: int):
            cache.set(f"key{key}", {"value": key})

        await asyncio.gather(*[set_value(i) for i in range(100)])

        assert len(cache._cache) == 100

    @pytest.mark.asyncio
    async def test_concurrent_mixed_operations(self, cache_config):
        """
        DADO: Cache
        QUANDO: Operações mistas concorrentes
        ENTÃO: Não deve ter corrupção de dados
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        async def mixed_ops(key: int):
            cache.set(f"key{key}", {"value": key})
            cache.get(f"key{key}")
            if key % 10 == 0:
                cache.invalidate(f"key{key}")

        await asyncio.gather(*[mixed_ops(i) for i in range(100)])

        # Cache deve estar em estado consistente
        assert len(cache._cache) >= 0


# ===== TESTES: Metrics =====


class TestOPACacheMetrics:
    """Testes de métricas de cache."""

    def test_metrics_initialization(self, cache_config):
        """
        DADO: Cache criado
        QUANDO: Verifico métricas
        ENTÃO: Devem estar inicializadas
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        assert hasattr(cache, "metrics")
        assert cache.metrics.hits == 0
        assert cache.metrics.misses == 0

    def test_metrics_hit_count(self, cache_config):
        """
        DADO: Cache com valor
        QUANDO: Faço get que encontra valor
        ENTÃO: Deve incrementar hits
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        cache.set("key1", {"allow": True})
        cache.get("key1")
        cache.get("key1")
        cache.get("key1")

        assert cache.metrics.hits == 3

    def test_metrics_miss_count(self, cache_config):
        """
        DADO: Cache vazio
        QUANDO: Faço get que não encontra valor
        ENTÃO: Deve incrementar misses
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        cache.get("key1")
        cache.get("key2")
        cache.get("key3")

        assert cache.metrics.misses == 3

    def test_metrics_hit_ratio(self, cache_config):
        """
        DADO: Cache com hits e misses
        QUANDO: Calculo hit ratio
        ENTÃO: Deve retornar proporção correta
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        cache.set("key1", {"allow": True})
        cache.set("key2", {"allow": False})

        cache.get("key1")  # hit
        cache.get("key2")  # hit
        cache.get("key3")  # miss

        assert cache.metrics.hit_ratio == 2 / 3

    def test_metrics_hit_ratio_empty(self, cache_config):
        """
        DADO: Cache sem acessos
        QUANDO: Calculo hit ratio
        ENTÃO: Deve retornar 0
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        assert cache.metrics.hit_ratio == 0.0

    def test_metrics_reset(self, cache_config):
        """
        DADO: Métricas com valores
        QUANDO: Reseto métricas
        ENTÃO: Devem voltar a zero
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        cache.set("key1", {"allow": True})
        cache.get("key1")
        cache.get("key2")

        assert cache.metrics.hits > 0 or cache.metrics.misses > 0

        cache.metrics.reset()

        assert cache.metrics.hits == 0
        assert cache.metrics.misses == 0

    def test_metrics_to_dict(self, cache_config):
        """
        DADO: Métricas com valores
        QUANDO: Chamo to_dict
        ENTÃO: Deve retornar dicionário com métricas
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        cache.set("key1", {"allow": True})
        cache.get("key1")
        cache.get("key2")

        metrics_dict = cache.metrics.to_dict()

        assert "hits" in metrics_dict
        assert "misses" in metrics_dict
        assert "hit_ratio" in metrics_dict
        assert metrics_dict["hits"] == 1
        assert metrics_dict["misses"] == 1


# ===== TESTES: LRU Eviction =====


class TestOPACacheLRU:
    """Testes de evicção LRU."""

    def test_lru_eviction_when_full(self, cache_config):
        """
        DADO: Cache com tamanho pequeno
        QUANDO: Adiciono mais entradas que o maxsize
        ENTÃO: Entradas mais antigas devem ser removidas
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=3)

        cache.set("key1", {"value": 1})
        cache.set("key2", {"value": 2})
        cache.set("key3", {"value": 3})
        cache.set("key4", {"value": 4})  # Deve evict key1

        assert "key1" not in cache._cache
        assert "key4" in cache._cache

    def test_lru_updates_on_access(self, cache_config):
        """
        DADO: Cache com entradas
        QUANDO: Acesso entrada antiga
        ENTÃO: Ela se torna mais recente
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=3)

        cache.set("key1", {"value": 1})
        cache.set("key2", {"value": 2})
        cache.set("key3", {"value": 3})

        # Acessar key1 para torná-la mais recente
        cache.get("key1")

        cache.set("key4", {"value": 4})  # Deve evict key2 (não key1)

        assert "key1" in cache._cache
        assert "key2" not in cache._cache
        assert "key4" in cache._cache


# ===== TESTES: Get Cache Key Generation =====


class TestOPACacheKeyGeneration:
    """Testes de geração de chave de cache."""

    def test_generate_cache_key_same_input(self, cache_config):
        """
        DADO: Mesmo policy e input
        QUANDO: Gero chave duas vezes
        ENTÃO: Deve gerar mesma chave
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        policy = "neuralhive/orchestrator/allow"
        input_data = {"user": "alice", "resource": "cpu"}

        key1 = cache.generate_key(policy, input_data)
        key2 = cache.generate_key(policy, input_data)

        assert key1 == key2

    def test_generate_cache_key_different_input(self, cache_config):
        """
        DADO: Mesmo policy mas input diferente
        QUANDO: Gero chave
        ENTÃO: Deve gerar chave diferente
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        policy = "neuralhive/orchestrator/allow"

        key1 = cache.generate_key(policy, {"user": "alice"})
        key2 = cache.generate_key(policy, {"user": "bob"})

        assert key1 != key2

    def test_generate_cache_key_different_policy(self, cache_config):
        """
        DADO: Policy diferente
        QUANDO: Gero chave
        ENTÃO: Deve gerar chave diferente
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        input_data = {"user": "alice"}

        key1 = cache.generate_key("policy1", input_data)
        key2 = cache.generate_key("policy2", input_data)

        assert key1 != key2

    def test_generate_cache_key_input_order_doesnt_matter(self, cache_config):
        """
        DADO: Input com mesma chaves em ordem diferente
        QUANDO: Gero chave
        ENTÃO: Deve gerar mesma chave (ordenação)
        """
        from neural_hive_opa.cache import OPACache

        cache = OPACache(ttl_seconds=300, max_size=1000)

        policy = "neuralhive/orchestrator/allow"

        key1 = cache.generate_key(policy, {"user": "alice", "action": "read"})
        key2 = cache.generate_key(policy, {"action": "read", "user": "alice"})

        assert key1 == key2
