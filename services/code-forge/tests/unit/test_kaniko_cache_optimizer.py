"""
Testes unitários para KanikoCacheOptimizer.
"""

import pytest
from datetime import datetime, timezone

from src.services.kaniko.kaniko_cache_optimizer import (
    CacheConfig,
    CacheLevel,
    CacheMetrics,
    KanikoCacheOptimizer,
    create_optimized_kaniko_pod_spec,
)


class TestCacheMetrics:
    """Testes para CacheMetrics."""

    def test_hit_rate_initial_zero(self):
        """Hit rate inicial deve ser 0."""
        metrics = CacheMetrics()
        assert metrics.hit_rate == 0.0

    def test_hit_rate_with_hits(self):
        """Hit rate com acertos."""
        metrics = CacheMetrics(hits=7, misses=3)
        assert metrics.hit_rate == 0.7

    def test_hit_rate_all_hits(self):
        """Hit rate 100%."""
        metrics = CacheMetrics(hits=10, misses=0)
        assert metrics.hit_rate == 1.0

    def test_hit_rate_all_misses(self):
        """Hit rate 0%."""
        metrics = CacheMetrics(hits=0, misses=10)
        assert metrics.hit_rate == 0.0


class TestKanikoCacheOptimizer:
    """Testes para KanikoCacheOptimizer."""

    def test_init_with_defaults(self):
        """Inicialização com configuração padrão."""
        optimizer = KanikoCacheOptimizer()
        assert optimizer.config.enabled is True
        assert optimizer.config.cache_level == CacheLevel.PVC
        assert optimizer.config.cache_ttl_hours == 24

    def test_init_with_custom_config(self):
        """Inicialização com configuração customizada."""
        config = CacheConfig(
            enabled=True,
            cache_level=CacheLevel.REGISTRY,
            cache_repo="ghcr.io/user/cache",
            cache_ttl_hours=48,
        )
        optimizer = KanikoCacheOptimizer(config)
        assert optimizer.config.cache_level == CacheLevel.REGISTRY
        assert optimizer.config.cache_repo == "ghcr.io/user/cache"

    def test_get_kaniko_cache_args_disabled(self):
        """Cache desabilitado não retorna argumentos."""
        config = CacheConfig(enabled=False)
        optimizer = KanikoCacheOptimizer(config)
        args = optimizer.get_kaniko_cache_args()
        assert args == []

    def test_get_kaniko_cache_args_local(self):
        """Cache local retorna cache-dir."""
        config = CacheConfig(cache_level=CacheLevel.LOCAL)
        optimizer = KanikoCacheOptimizer(config)
        args = optimizer.get_kaniko_cache_args()
        assert "--cache=true" in args
        assert any("--cache-dir=/tmp/kaniko-cache" in arg for arg in args)

    def test_get_kaniko_cache_args_pvc(self):
        """Cache PVC retorna cache-dir."""
        config = CacheConfig(cache_level=CacheLevel.PVC)
        optimizer = KanikoCacheOptimizer(config)
        args = optimizer.get_kaniko_cache_args()
        assert "--cache=true" in args
        assert any("--cache-dir=/cache/kaniko" in arg for arg in args)

    def test_get_kaniko_cache_args_registry(self):
        """Cache Registry retorna cache-repo."""
        config = CacheConfig(
            cache_level=CacheLevel.REGISTRY,
            cache_repo="ghcr.io/user/cache",
        )
        optimizer = KanikoCacheOptimizer(config)
        args = optimizer.get_kaniko_cache_args()
        assert "--cache=true" in args
        assert "--cache-repo=ghcr.io/user/cache" in args

    def test_get_kaniko_cache_args_derive_cache_repo(self):
        """Deriva cache repo da imagem."""
        config = CacheConfig(cache_level=CacheLevel.REGISTRY)
        optimizer = KanikoCacheOptimizer(config)
        args = optimizer.get_kaniko_cache_args("ghcr.io/user/app:latest")
        assert "--cache-repo=ghcr.io/user/app-cache" in args

    def test_derive_cache_repo_with_tag(self):
        """Deriva cache repo removendo tag."""
        optimizer = KanikoCacheOptimizer()
        cache_repo = optimizer._derive_cache_repo("ghcr.io/user/app:v1.0")
        assert cache_repo == "ghcr.io/user/app-cache"

    def test_derive_cache_repo_without_tag(self):
        """Deriva cache repo sem tag."""
        optimizer = KanikoCacheOptimizer()
        cache_repo = optimizer._derive_cache_repo("ghcr.io/user/app")
        assert cache_repo == "ghcr.io/user/app-cache"

    def test_get_cache_volume_mounts_pvc(self):
        """Retorna volume mounts para PVC."""
        config = CacheConfig(cache_level=CacheLevel.PVC)
        optimizer = KanikoCacheOptimizer(config)
        mounts = optimizer.get_cache_volume_mounts()
        assert len(mounts) == 1
        assert mounts[0]["name"] == "kaniko-cache"
        assert "persistentVolumeClaim" in mounts[0]

    def test_get_cache_volume_mounts_local(self):
        """Retorna volume mounts para local."""
        config = CacheConfig(cache_level=CacheLevel.LOCAL)
        optimizer = KanikoCacheOptimizer(config)
        mounts = optimizer.get_cache_volume_mounts()
        assert len(mounts) == 1
        assert mounts[0]["name"] == "kaniko-cache"
        assert "emptyDir" in mounts[0]

    def test_get_cache_volume_mounts_disabled(self):
        """Cache desabilitado não retorna volumes."""
        config = CacheConfig(enabled=False)
        optimizer = KanikoCacheOptimizer(config)
        mounts = optimizer.get_cache_volume_mounts()
        assert mounts == []

    def test_get_cache_volume_mounts_containers_pvc(self):
        """Retorna container mounts para PVC."""
        config = CacheConfig(cache_level=CacheLevel.PVC)
        optimizer = KanikoCacheOptimizer(config)
        mounts = optimizer.get_cache_volume_mounts_containers()
        assert len(mounts) == 1
        assert mounts[0]["name"] == "kaniko-cache"
        assert mounts[0]["mountPath"] == "/cache"

    def test_get_cache_volume_mounts_containers_local(self):
        """Retorna container mounts para local."""
        config = CacheConfig(cache_level=CacheLevel.LOCAL)
        optimizer = KanikoCacheOptimizer(config)
        mounts = optimizer.get_cache_volume_mounts_containers()
        assert len(mounts) == 1
        assert mounts[0]["mountPath"] == "/cache"

    def test_get_pvc_definition(self):
        """Retorna definição de PVC."""
        optimizer = KanikoCacheOptimizer()
        pvc = optimizer.get_pvc_definition(
            namespace="build-ns",
            storage_class="fast-ssd",
            size_gb=20,
        )
        assert pvc["kind"] == "PersistentVolumeClaim"
        assert pvc["metadata"]["name"] == "kaniko-cache-pvc"
        assert pvc["metadata"]["namespace"] == "build-ns"
        assert pvc["spec"]["storageClassName"] == "fast-ssd"
        assert pvc["spec"]["resources"]["requests"]["storage"] == "20Gi"

    def test_record_cache_hit(self):
        """Registra cache hit."""
        optimizer = KanikoCacheOptimizer()
        optimizer.record_cache_hit("sha256:abc123")
        assert optimizer.metrics.hits == 1
        assert optimizer.metrics.misses == 0
        assert optimizer.metrics.last_cache_update is not None

    def test_record_cache_miss(self):
        """Registra cache miss."""
        optimizer = KanikoCacheOptimizer()
        optimizer.record_cache_miss("sha256:def456")
        assert optimizer.metrics.hits == 0
        assert optimizer.metrics.misses == 1

    def test_record_cache_hit_updates_metrics(self):
        """Cache hit atualiza last_cache_update."""
        optimizer = KanikoCacheOptimizer()
        before = datetime.now(timezone.utc)
        optimizer.record_cache_hit()
        after = datetime.now(timezone.utc)
        assert optimizer.metrics.last_cache_update >= before
        assert optimizer.metrics.last_cache_update <= after

    def test_get_metrics(self):
        """Retorna métricas do cache."""
        optimizer = KanikoCacheOptimizer()
        optimizer.record_cache_hit()
        optimizer.record_cache_miss()
        optimizer.record_cache_hit()

        metrics = optimizer.get_metrics()
        assert metrics["hits"] == 2
        assert metrics["misses"] == 1
        assert metrics["hit_rate"] == 2 / 3
        assert metrics["cache_enabled"] is True
        assert "last_cache_update" in metrics

    def test_get_optimization_recommendations_low_hit_rate(self):
        """Recomenda cache warming com baixo hit rate."""
        optimizer = KanikoCacheOptimizer()
        recommendations = optimizer.get_optimization_recommendations(
            build_frequency=5,
            avg_build_time_seconds=300,
            cache_hit_rate=0.2,
        )
        assert len(recommendations) > 0
        warming_rec = next(
            (r for r in recommendations if r["type"] == "enable_cache_warming"),
            None,
        )
        assert warming_rec is not None
        assert warming_rec["priority"] == "medium"

    def test_get_optimization_recommendations_high_frequency(self):
        """Recomenda upgrade de cache para builds frequentes."""
        config = CacheConfig(cache_level=CacheLevel.LOCAL)
        optimizer = KanikoCacheOptimizer(config)
        recommendations = optimizer.get_optimization_recommendations(
            build_frequency=20,
            avg_build_time_seconds=300,
            cache_hit_rate=0.5,
        )
        assert len(recommendations) > 0
        upgrade_rec = next(
            (r for r in recommendations if r["type"] == "upgrade_cache_level"),
            None,
        )
        assert upgrade_rec is not None
        assert upgrade_rec["priority"] == "high"

    def test_get_optimization_recommendations_no_recommendations(self):
        """Sem recomendações para cenário ideal."""
        optimizer = KanikoCacheOptimizer()
        recommendations = optimizer.get_optimization_recommendations(
            build_frequency=5,
            avg_build_time_seconds=120,
            cache_hit_rate=0.8,
        )
        # Hit rate alto, poucos builds - sem recomendações críticas
        critical = [r for r in recommendations if r["priority"] == "high"]
        assert len(critical) == 0


class TestCreateOptimizedKanikoPodSpec:
    """Testes para create_optimized_kaniko_pod_spec."""

    def test_creates_pod_spec_with_cache(self):
        """Cria spec de pod com cache."""
        config = CacheConfig(cache_level=CacheLevel.PVC)
        pod_spec = create_optimized_kaniko_pod_spec(
            image_tag="ghcr.io/user/app:latest",
            dockerfile_path="Dockerfile",
            build_context=".",
            cache_config=config,
        )
        assert pod_spec["kind"] == "Pod"
        assert "kaniko" in str(pod_spec)
        # Verificar que volumes de cache estão presentes
        volumes = pod_spec["spec"]["volumes"]
        assert any(v.get("name") == "kaniko-cache" for v in volumes)

    def test_creates_pod_spec_without_cache(self):
        """Cria spec de pod sem cache."""
        config = CacheConfig(enabled=False)
        pod_spec = create_optimized_kaniko_pod_spec(
            image_tag="ghcr.io/user/app:latest",
            dockerfile_path="Dockerfile",
            build_context=".",
            cache_config=config,
        )
        assert pod_spec["kind"] == "Pod"
        # Não deve ter volume de cache
        volumes = pod_spec["spec"]["volumes"]
        assert not any(v.get("name") == "kaniko-cache" for v in volumes)

    def test_pod_spec_contains_kaniko_args(self):
        """Spec contém argumentos do Kaniko."""
        config = CacheConfig(cache_level=CacheLevel.PVC)
        pod_spec = create_optimized_kaniko_pod_spec(
            image_tag="ghcr.io/user/app:v1.0",
            dockerfile_path="Dockerfile",
            build_context=".",
            cache_config=config,
        )
        container = pod_spec["spec"]["containers"][0]
        args = container["args"]
        assert "--dockerfile=Dockerfile" in args
        assert "--context=dir:///workspace" in args
        assert "--destination=ghcr.io/user/app:v1.0" in args


class TestCacheWarming:
    """Testes para warm_cache."""

    @pytest.mark.asyncio
    async def test_warm_cache_disabled(self):
        """Não aquece cache se desabilitado."""
        config = CacheConfig(warm_cache_on_startup=False)
        optimizer = KanikoCacheOptimizer(config)
        result = await optimizer.warm_cache()
        assert result["warmed"] is False

    @pytest.mark.asyncio
    async def test_warm_cache_with_images(self):
        """Aquece cache com lista de imagens."""
        optimizer = KanikoCacheOptimizer()
        result = await optimizer.warm_cache(
            common_images=["gcr.io/distroless/base:latest"],
            max_concurrent=1,
        )
        assert result["warmed"] is True
        assert "images_warmed" in result
        assert "total_count" in result

    @pytest.mark.asyncio
    async def test_warm_cache_records_metrics(self):
        """Aquece cache e registra métricas."""
        optimizer = KanikoCacheOptimizer()
        await optimizer.warm_cache(
            common_images=["gcr.io/distroless/base:latest"],
        )
        # Verificar que não houve exceções
        assert optimizer.metrics is not None
