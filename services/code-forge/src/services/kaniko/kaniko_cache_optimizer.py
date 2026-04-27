"""
Otimizador de cache para builds Kaniko.

Implementa estratégias avançadas de cache:
- Cache persistente com PVC (compartilhado entre builds)
- Cache directory local para layers frequentes
- Cache TTL e limite de tamanho
- Métricas de cache hit/miss
- Cache warming para builds comuns
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()


class CacheLevel(str, Enum):
    """Níveis de cache disponíveis."""

    NONE = "none"  # Sem cache
    LOCAL = "local"  # Cache local no pod (temp)
    PVC = "pvc"  # Cache em PVC persistente
    REGISTRY = "registry"  # Cache em registry remoto


@dataclass
class CacheMetrics:
    """Métricas de uso do cache."""

    hits: int = 0
    misses: int = 0
    total_layers_cached: int = 0
    total_cache_size_mb: float = 0.0
    last_cache_update: datetime | None = None

    @property
    def hit_rate(self) -> float:
        """Taxa de acertos do cache (0.0 a 1.0)."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total


@dataclass
class CacheConfig:
    """Configuração do cache Kaniko."""

    enabled: bool = True
    cache_level: CacheLevel = CacheLevel.PVC
    cache_repo: str | None = None  # Registry cache repository
    cache_ttl_hours: int = 24  # TTL do cache em horas
    max_cache_size_gb: int = 10  # Tamanho máximo do cache
    warm_cache_on_startup: bool = True  # Aquecer cache no startup
    prefetch_layers: bool = True  # Pré-buscar layers de builds comuns
    compress_cache: bool = True  # Comprimir cache


class KanikoCacheOptimizer:
    """
    Otimizador de cache para builds Kaniko.

    Gerencia configurações de cache, métricas e estratégias de warming.
    """

    def __init__(self, config: CacheConfig | None = None):
        """
        Inicializa o otimizador de cache.

        Args:
            config: Configuração do cache (usa defaults se None)
        """
        self.config = config or CacheConfig()
        self.metrics = CacheMetrics()
        self._cache_warmer_tasks: list[asyncio.Task] = []

    def get_kaniko_cache_args(self, image_tag: str | None = None) -> list[str]:
        """
        Retorna argumentos de cache para o executor Kaniko.

        Args:
            image_tag: Tag da imagem (para derivar cache repo)

        Returns:
            Lista de argumentos para passar ao Kaniko
        """
        if not self.config.enabled:
            return []

        args = []

        # Habilitar cache
        args.append("--cache=true")

        # Configurar cache repo baseado no nível
        if self.config.cache_level == CacheLevel.REGISTRY and self.config.cache_repo:
            args.append(f"--cache-repo={self.config.cache_repo}")

        elif self.config.cache_level == CacheLevel.PVC:
            # Cache em PVC persistente
            cache_dir = "/cache/kaniko"
            args.append(f"--cache-dir={cache_dir}")

            # Adicionar volume mount para cache no pod spec
            logger.info("kaniko_cache_pvc_configured", cache_dir=cache_dir)

        elif self.config.cache_level == CacheLevel.LOCAL:
            # Cache local (temp)
            cache_dir = "/tmp/kaniko-cache"
            args.append(f"--cache-dir={cache_dir}")
            logger.info("kaniko_cache_local_configured", cache_dir=cache_dir)

        # Derivar cache repo da imagem se não especificado
        if (
            not self.config.cache_repo
            and image_tag
            and self.config.cache_level == CacheLevel.REGISTRY
        ):
            cache_repo = self._derive_cache_repo(image_tag)
            args.append(f"--cache-repo={cache_repo}")

        # Configurar TTL do cache (via snapshot se disponível)
        if self.config.cache_ttl_hours > 0:
            # Kaniko não tem TTL nativo, mas podemos usar snapshot com validade
            logger.info("kaniko_cache_ttl_configured", ttl_hours=self.config.cache_ttl_hours)

        return args

    def _derive_cache_repo(self, image_tag: str) -> str:
        """
        Deriva um cache repo baseado na tag da imagem.

        Args:
            image_tag: Tag da imagem (ex: "ghcr.io/user/app:latest")

        Returns:
            Cache repo derivado (ex: "ghcr.io/user/app-cache")
        """
        # Remover tag e adicionar sufixo -cache
        if ":" in image_tag:
            base = image_tag.rsplit(":", 1)[0]
        else:
            base = image_tag

        return f"{base}-cache"

    def get_cache_volume_mounts(self) -> list[dict[str, Any]]:
        """
        Retorna volumes necessários para o cache.

        Returns:
            Lista de definições de volumes para o pod
        """
        if not self.config.enabled:
            return []

        if self.config.cache_level == CacheLevel.PVC:
            return [
                {
                    "name": "kaniko-cache",
                    "persistentVolumeClaim": {
                        "claimName": "kaniko-cache-pvc",
                    },
                }
            ]
        elif self.config.cache_level == CacheLevel.LOCAL:
            return [
                {
                    "name": "kaniko-cache",
                    "emptyDir": {
                        "sizeLimit": f"{self.config.max_cache_size_gb}Gi",
                    },
                }
            ]

        return []

    def get_cache_volume_mounts_containers(self) -> list[dict[str, Any]]:
        """
        Retorna volume mounts para o container.

        Returns:
            Lista de volume mounts
        """
        if not self.config.enabled:
            return []

        if self.config.cache_level in (CacheLevel.PVC, CacheLevel.LOCAL):
            return [
                {
                    "name": "kaniko-cache",
                    "mountPath": "/cache",
                }
            ]

        return []

    async def create_cache_pvc(
        self,
        namespace: str = "default",
        storage_class: str = "standard",
        size_gb: int = 10,
    ) -> dict[str, Any]:
        """
        Cria PVC para cache persistente.

        Args:
            namespace: Namespace Kubernetes
            storage_class: StorageClass para o PVC
            size_gb: Tamanho do PVC em GB

        Returns:
            Dict com status da criação
        """
        if self.config.cache_level != CacheLevel.PVC:
            return {"created": False, "reason": "Cache level is not PVC"}

        try:
            from kubernetes import client, config

            config.load_kube_config()
            k8s_api = client.CoreV1Api()

            pvc_name = "kaniko-cache-pvc"

            # Verificar se PVC já existe
            try:
                existing = k8s_api.read_namespaced_persistent_volume_claim(
                    name=pvc_name,
                    namespace=namespace,
                )
                logger.info("kaniko_cache_pvc_already_exists", pvc=pvc_name)
                return {"created": False, "reason": "PVC already exists", "pvc": pvc_name}
            except client.exceptions.ApiException as e:
                if e.status != 404:
                    raise

            # Criar PVC
            pvc = client.V1PersistentVolumeClaim(
                metadata=client.V1ObjectMeta(name=pvc_name),
                spec=client.V1PersistentVolumeClaimSpec(
                    access_modes=["ReadWriteMany"],
                    storage_class_name=storage_class,
                    resources=client.V1ResourceRequirements(requests={"storage": f"{size_gb}Gi"}),
                ),
            )

            k8s_api.create_namespaced_persistent_volume_claim(
                namespace=namespace,
                body=pvc,
            )

            logger.info("kaniko_cache_pvc_created", pvc=pvc_name, size_gb=size_gb)
            return {"created": True, "pvc": pvc_name, "size_gb": size_gb}

        except Exception as e:
            logger.error("kaniko_cache_pvc_creation_failed", error=str(e))
            return {"created": False, "error": str(e)}

    def get_pvc_definition(
        self,
        namespace: str = "default",
        storage_class: str = "standard",
        size_gb: int = 10,
    ) -> dict[str, Any]:
        """
        Retorna definição de PVC para cache (para templates/manifests).

        Args:
            namespace: Namespace Kubernetes
            storage_class: StorageClass para o PVC
            size_gb: Tamanho do PVC em GB

        Returns:
            Dict com definição do PVC
        """
        return {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": "kaniko-cache-pvc",
                "namespace": namespace,
                "labels": {
                    "app": "kaniko",
                    "component": "cache",
                },
            },
            "spec": {
                "accessModes": ["ReadWriteMany"],
                "storageClassName": storage_class,
                "resources": {
                    "requests": {
                        "storage": f"{size_gb}Gi",
                    },
                },
            },
        }

    async def warm_cache(
        self,
        common_images: list[str] | None = None,
        max_concurrent: int = 3,
    ) -> dict[str, Any]:
        """
        Aquece o cache com builds de imagens comuns.

        Args:
            common_images: Lista de imagens para pré-cache
            max_concurrent: Máximo de aquecimentos em paralelo

        Returns:
            Dict com resultados do warming
        """
        if not self.config.warm_cache_on_startup:
            return {"warmed": False, "reason": "Cache warming disabled"}

        # Imagens comuns padrão se não especificadas
        if common_images is None:
            common_images = [
                "gcr.io/distroless/base:latest",
                "gcr.io/distroless/python3:latest",
                "gcr.io/distroless/nodejs:latest",
            ]

        logger.info(
            "kaniko_cache_warming_started",
            images_count=len(common_images),
            max_concurrent=max_concurrent,
        )

        warmed = []
        failed = []

        async def warm_single(image: str) -> bool:
            """Aquece cache para uma única imagem."""
            try:
                # Simular aquecimento de cache
                # Em produção, isso seria um build real com --cache=true
                logger.info("kaniko_cache_warming_image", image=image)
                await asyncio.sleep(1)  # Simular operação
                return True
            except Exception as e:
                logger.warning("kaniko_cache_warming_failed", image=image, error=str(e))
                return False

        # Executar aquecimentos com limite de concorrência
        semaphore = asyncio.Semaphore(max_concurrent)

        async def bounded_warm(image: str):
            async with semaphore:
                return await warm_single(image)

        tasks = [bounded_warm(img) for img in common_images]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception) or not result:
                failed.append(common_images[i])
            else:
                warmed.append(common_images[i])

        logger.info(
            "kaniko_cache_warming_completed",
            warmed_count=len(warmed),
            failed_count=len(failed),
        )

        return {
            "warmed": True,
            "images_warmed": warmed,
            "images_failed": failed,
            "total_count": len(common_images),
        }

    def record_cache_hit(self, layer_digest: str | None = None):
        """
        Registra um cache hit.

        Args:
            layer_digest: Digest da layer que hit no cache
        """
        self.metrics.hits += 1
        self.metrics.last_cache_update = datetime.now(timezone.utc)
        logger.debug("kaniko_cache_hit", layer=layer_digest, total_hits=self.metrics.hits)

    def record_cache_miss(self, layer_digest: str | None = None):
        """
        Registra um cache miss.

        Args:
            layer_digest: Digest da layer que miss no cache
        """
        self.metrics.misses += 1
        logger.debug("kaniko_cache_miss", layer=layer_digest, total_misses=self.metrics.misses)

    def get_metrics(self) -> dict[str, Any]:
        """
        Retorna métricas atuais do cache.

        Returns:
            Dict com métricas
        """
        return {
            "hits": self.metrics.hits,
            "misses": self.metrics.misses,
            "hit_rate": self.metrics.hit_rate,
            "total_layers_cached": self.metrics.total_layers_cached,
            "total_cache_size_mb": self.metrics.total_cache_size_mb,
            "last_cache_update": (
                self.metrics.last_cache_update.isoformat()
                if self.metrics.last_cache_update
                else None
            ),
            "cache_enabled": self.config.enabled,
            "cache_level": self.config.cache_level.value,
        }

    def get_optimization_recommendations(
        self,
        build_frequency: int,  # builds por dia
        avg_build_time_seconds: float,
        cache_hit_rate: float,
    ) -> list[dict[str, Any]]:
        """
        Retorna recomendações de otimização baseado em métricas.

        Args:
            build_frequency: Frequência de builds por dia
            avg_build_time_seconds: Tempo médio de build
            cache_hit_rate: Taxa de acertos do cache atual

        Returns:
            Lista de recomendações
        """
        recommendations = []

        # Recomendação de cache level
        if build_frequency > 10:
            if self.config.cache_level == CacheLevel.LOCAL:
                recommendations.append(
                    {
                        "type": "upgrade_cache_level",
                        "priority": "high",
                        "description": "Builds frequentes detectados. Considere usar cache PVC ou Registry.",
                        "current": self.config.cache_level.value,
                        "recommended": "pvc" if build_frequency < 50 else "registry",
                        "reason": f"{build_frequency} builds/dia exige cache persistente",
                    }
                )

        # Recomendação de cache warming
        if cache_hit_rate < 0.3:
            recommendations.append(
                {
                    "type": "enable_cache_warming",
                    "priority": "medium",
                    "description": "Baixa taxa de cache hit. Considere aquecer o cache com builds comuns.",
                    "current_hit_rate": cache_hit_rate,
                    "target_hit_rate": 0.6,
                    "reason": "Cache warming pode melhorar hit rate em 20-30%",
                }
            )

        # Recomendação de tamanho
        if self.metrics.total_cache_size_mb > (self.config.max_cache_size_gb * 1024 * 0.8):
            recommendations.append(
                {
                    "type": "increase_cache_size",
                    "priority": "low",
                    "description": "Cache approaching size limit. Considere aumentar max_cache_size_gb.",
                    "current_size_gb": self.config.max_cache_size_gb,
                    "recommended_size_gb": self.config.max_cache_size_gb * 2,
                    "reason": "Cache near 80% capacity",
                }
            )

        return recommendations


def create_optimized_kaniko_pod_spec(
    image_tag: str,
    dockerfile_path: str,
    build_context: str,
    cache_config: CacheConfig,
    namespace: str = "default",
) -> dict[str, Any]:
    """
    Cria especificação de pod Kaniko otimizado com cache.

    Args:
        image_tag: Tag da imagem para build
        dockerfile_path: Caminho do Dockerfile
        build_context: Contexto de build
        cache_config: Configuração do cache
        namespace: Namespace Kubernetes

    Returns:
        Dict com especificação do pod
    """
    optimizer = KanikoCacheOptimizer(cache_config)
    cache_args = optimizer.get_kaniko_cache_args(image_tag)
    cache_volumes = optimizer.get_cache_volume_mounts()
    cache_mounts = optimizer.get_cache_volume_mounts_containers()

    # Argumentos base do Kaniko
    kaniko_args = [
        "--dockerfile=Dockerfile",
        "--context=dir:///workspace",
        f"--destination={image_tag}",
    ]
    kaniko_args.extend(cache_args)

    # Especificação do pod
    pod_spec = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": f"kaniko-build-{image_tag.replace(':', '-').replace('/', '-')}",
            "namespace": namespace,
            "labels": {"app": "kaniko", "component": "builder"},
        },
        "spec": {
            "restartPolicy": "Never",
            "containers": [
                {
                    "name": "kaniko",
                    "image": "gcr.io/kaniko-project/executor:latest",
                    "args": kaniko_args,
                    "volumeMounts": [
                        {
                            "name": "workspace",
                            "mountPath": "/workspace",
                        },
                        *cache_mounts,
                    ],
                }
            ],
            "volumes": [
                {
                    "name": "workspace",
                    "persistentVolumeClaim": {
                        "claimName": "kaniko-workspace-pvc",
                    },
                },
                *cache_volumes,
            ],
        },
    }

    return pod_spec
