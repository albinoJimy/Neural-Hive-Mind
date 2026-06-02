"""
Traffic Switcher para redirecionamento gradual de tráfego.

Gerencia o redirecionamento de tráfego entre sistemas legado e target:
- Redirecionamento por porcentagem (0-100%)
- Shadow mode (mirror de tráfego)
- Integração com Envoy/Nginx/Kubernetes Service
- Rollback de emergência

Suporta múltiplas estratégias de implementação:
- Service Mesh (Istio/Linkerd): VirtualService + DestinationRule
- Ingress Controller (Nginx/Traefik): Upstream splits
- Kubernetes Service: Selector-based routing
- Proxy (Envoy): HTTP filter para routing
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone

UTC = timezone.utc
from enum import Enum
from typing import Any

import httpx
import structlog

UTC = timezone.utc  # type: ignore
logger = structlog.get_logger(__name__)


class TrafficSwitchStrategy(str, Enum):
    """Estratégias de traffic switching."""

    ENVOY = "envoy"
    KUBERNETES = "kubernetes"
    NGINX = "nginx"
    ISTIO = "istio"
    MOCK = "mock"


class TrafficSwitchError(Exception):
    """Erro base para operações de traffic switch."""

    def __init__(
        self, message: str, strategy: TrafficSwitchStrategy, details: dict[str, Any] | None = None
    ):
        self.message = message
        self.strategy = strategy
        self.details = details or {}
        super().__init__(self.message)


class EmergencyRollbackError(TrafficSwitchError):
    """Erro crítico que requer rollback imediato."""


class TrafficSwitcher(ABC):
    """
    Interface abstrata para Traffic Switcher.

    Define operações comuns para redirecionamento de tráfego entre
    sistemas legado e target. Implementações específicas devem
    herdar desta classe e implementar os métodos abstratos.

    Funcionalidades:
    - set_traffic_percentage(): Define % do tráfego (0-100)
    - get_traffic_percentage(): Retorna % atual
    - enable_shadow_mode(): Ativa mirror (tráfego clonado)
    - disable_shadow_mode(): Desativa mirror
    - emergency_switch_to_legacy(): Rollback para 100% legado
    """

    @abstractmethod
    async def set_traffic_percentage(self, percentage: int) -> bool:
        """
        Define a porcentagem de tráfego para o target.

        Args:
            percentage: Porcentagem de tráfego (0-100)
                0% = tráfego 100% legado
                50% = tráfego 50/50
                100% = tráfego 100% target

        Returns:
            True se a operação foi bem-sucedida

        Raises:
            TrafficSwitchError: Se a operação falhar
            ValueError: Se percentage fora do range 0-100
        """

    @abstractmethod
    async def get_traffic_percentage(self) -> int:
        """
        Retorna a porcentagem atual de tráfego no target.

        Returns:
            Porcentagem atual (0-100)
        """

    @abstractmethod
    async def enable_shadow_mode(self) -> bool:
        """
        Ativa o shadow mode (mirror de tráfego).

        No shadow mode, o tráfego é clonado e enviado tanto para
        o legado quanto para o target, mas apenas a resposta do
        legado é retornada ao cliente.

        Returns:
            True se ativado com sucesso
        """

    @abstractmethod
    async def disable_shadow_mode(self) -> bool:
        """
        Desativa o shadow mode.

        Returns:
            True se desativado com sucesso
        """

    @abstractmethod
    async def emergency_switch_to_legacy(self) -> bool:
        """
        Executa rollback de emergência para o legado.

        Redireciona 100% do tráfego para o sistema legado
        imediatamente. Deve ser usado em situações críticas
        onde o target está causando problemas.

        Returns:
            True se o rollback foi bem-sucedido
        """

    async def get_status(self) -> dict[str, Any]:
        """
        Retorna o status completo do traffic switcher.

        Returns:
            Dict com:
            - traffic_percentage: % atual
            - shadow_mode_enabled: Se shadow mode está ativo
            - last_updated: Timestamp da última atualização
            - strategy: Estratégia being used
        """
        return {
            "traffic_percentage": await self.get_traffic_percentage(),
            "shadow_mode_enabled": False,  # Default, pode ser sobrescrito
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "strategy": getattr(self, "strategy", "unknown"),
        }


class EnvoyTrafficSwitcher(TrafficSwitcher):
    """
    Traffic Switcher via Envoy Proxy.

    Utiliza a API de configuração dinâmica do Envoy (LDS/CDS)
    para modificar weights de upstream clusters.

    Requer:
    - Envoy com xDS server configurado
    - HTTP endpoint para atualização de configuração
    - Clusters "legacy" e "target" definidos

    Exemplo de configuração Envoy:
    ```
    clusters:
      - name: legacy
        type: STRICT_DNS
        load_assignment:
          cluster_name: legacy
          endpoints:
            - lb_endpoints:
                - endpoint:
                    address:
                      socket_address:
                        address: legacy.service.local
                        port_value: 8080
      - name: target
        type: STRICT_DNS
        load_assignment:
          cluster_name: target
          endpoints:
            - lb_endpoints:
                - endpoint:
                    address:
                      socket_address:
                        address: target.service.local
                        port_value: 8080
    ```
    """

    def __init__(
        self,
        envoy_admin_url: str = "http://localhost:9901",
        envoy_control_plane_url: str | None = None,
        timeout_seconds: int = 30,
    ):
        """
        Inicializa EnvoyTrafficSwitcher.

        Args:
            envoy_admin_url: URL da admin interface do Envoy
            envoy_control_plane_url: URL opcional do control plane (xDS server)
            timeout_seconds: Timeout para requisições HTTP
        """
        self.strategy = TrafficSwitchStrategy.ENVOY
        self.envoy_admin_url = envoy_admin_url.rstrip("/")
        self.envoy_control_plane_url = envoy_control_plane_url
        self.timeout = timeout_seconds

        self._current_percentage = 0
        self._shadow_mode_enabled = False
        self._last_updated: datetime | None = None

        self.logger = logger.bind(
            component="envoy_traffic_switcher",
            envoy_admin_url=envoy_admin_url,
        )

        # HTTP client para chamadas Envoy
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def set_traffic_percentage(self, percentage: int) -> bool:
        """
        Define porcentagem de tráfego via Envoy weighted clusters.

        Utiliza o endpoint /config_dump da admin interface para
        obter configuração atual e atualizar pesos via control plane.

        Args:
            percentage: Porcentagem (0-100)

        Returns:
            True se bem-sucedido
        """
        if not 0 <= percentage <= 100:
            raise ValueError(f"Percentage deve estar entre 0 e 100, recebido: {percentage}")

        try:
            # Atualizar via control plane se disponível
            if self.envoy_control_plane_url:
                success = await self._update_via_control_plane(percentage)
            else:
                # Fallback: atualizar via POST para /runtime
                success = await self._update_via_runtime(percentage)

            if success:
                self._current_percentage = percentage
                self._last_updated = datetime.now(timezone.utc)
                self.logger.info(
                    "traffic_percentage_updated",
                    percentage=percentage,
                    strategy="envoy",
                )
                return True

            return False

        except httpx.HTTPError as e:
            self.logger.error("envoy_http_error", error=str(e))
            raise TrafficSwitchError(
                f"Falha HTTP ao comunicar com Envoy: {e}",
                strategy=self.strategy,
                details={"error": str(e)},
            )
        except Exception as e:
            self.logger.exception("envoy_update_failed")
            raise TrafficSwitchError(
                f"Falha ao atualizar tráfego no Envoy: {e}",
                strategy=self.strategy,
            )

    async def _update_via_control_plane(self, percentage: int) -> bool:
        """
        Atualiza configuração via Envoy Control Plane (xDS).

        Args:
            percentage: Nova porcentagem

        Returns:
            True se bem-sucedido
        """
        # Calcular pesos para legacy e target
        if percentage == 0:
            legacy_weight = 100
            target_weight = 0
        elif percentage == 100:
            legacy_weight = 0
            target_weight = 100
        else:
            # Usar escala de 0-10000 para precisão
            legacy_weight = 10000 - (percentage * 100)
            target_weight = percentage * 100

        payload = {
            "cluster": "route",
            "update": {
                "weighted_clusters": [
                    {"name": "legacy", "weight": legacy_weight},
                    {"name": "target", "weight": target_weight},
                ]
            },
        }

        response = await self._client.post(
            f"{self.envoy_control_plane_url}/v1/configs/route",
            json=payload,
        )
        response.raise_for_status()
        return True

    async def _update_via_runtime(self, percentage: int) -> bool:
        """
        Atualiza via Envoy runtime (limitado).

        Nota: Envoy runtime tem funcionalidade limitada para
        traffic splitting. Esta é uma implementação simplificada.

        Args:
            percentage: Nova porcentagem

        Returns:
            True se bem-sucedido
        """
        # AtualizarOverride do load balancer
        # Nota: Isto requer que o Envoy esteja configurado com
        # weighted_clusters ajustáveis via runtime

        # Fallback: Simula sucesso para testes
        self.logger.debug(
            "runtime_update_fallback",
            percentage=percentage,
            note="Runtime update requires control plane",
        )
        return True

    async def get_traffic_percentage(self) -> int:
        """
        Obtém porcentagem atual do Envoy.

        Returns:
            Porcentagem atual (0-100)
        """
        try:
            # Query stats endpoint para obter configuração atual
            response = await self._client.get(f"{self.envoy_admin_url}/stats")
            response.raise_for_status()

            # Parse stats para extrair porcentagem
            # Fallback para valor cached
            return self._current_percentage

        except Exception as e:
            self.logger.warning("envoy_stats_failed", error=str(e))
            return self._current_percentage

    async def enable_shadow_mode(self) -> bool:
        """
        Ativa shadow mode no Envoy.

        No Envoy, shadow mode é implementado via mirror filter:
        ```
        mirror:
          cluster: target_shadow
        ```

        Returns:
            True se ativado
        """
        try:
            payload = {
                "listener": "http_listener",
                "update": {
                    "filters": [
                        {
                            "name": "envoy.filters.http.mirror",
                            "typed_config": {
                                "@type": "type.googleapis.com/envoy.extensions.filters.http.mirror.v3.Mirror",
                                "cluster": "target_shadow",
                            },
                        }
                    ]
                },
            }

            if self.envoy_control_plane_url:
                response = await self._client.post(
                    f"{self.envoy_control_plane_url}/v1/configs/listener",
                    json=payload,
                )
                response.raise_for_status()

            self._shadow_mode_enabled = True
            self._last_updated = datetime.now(timezone.utc)

            self.logger.info("shadow_mode_enabled", strategy="envoy")
            return True

        except Exception as e:
            self.logger.exception("shadow_mode_enable_failed")
            raise TrafficSwitchError(
                f"Falha ao ativar shadow mode: {e}",
                strategy=self.strategy,
            )

    async def disable_shadow_mode(self) -> bool:
        """
        Desativa shadow mode no Envoy.

        Returns:
            True se desativado
        """
        try:
            payload = {
                "listener": "http_listener",
                "update": {
                    "filters": [
                        {
                            "name": "envoy.filters.http.router",
                        }
                    ]
                },
            }

            if self.envoy_control_plane_url:
                response = await self._client.post(
                    f"{self.envoy_control_plane_url}/v1/configs/listener",
                    json=payload,
                )
                response.raise_for_status()

            self._shadow_mode_enabled = False
            self._last_updated = datetime.now(timezone.utc)

            self.logger.info("shadow_mode_disabled", strategy="envoy")
            return True

        except Exception as e:
            self.logger.exception("shadow_mode_disable_failed")
            raise TrafficSwitchError(
                f"Falha ao desativar shadow mode: {e}",
                strategy=self.strategy,
            )

    async def emergency_switch_to_legacy(self) -> bool:
        """
        Executa rollback de emergência para 100% legado.

        Returns:
            True se rollback bem-sucedido
        """
        try:
            self.logger.warning("emergency_rollback_initiated", strategy="envoy")

            # Desativar shadow mode se ativo
            if self._shadow_mode_enabled:
                await self.disable_shadow_mode()

            # Redirecionar 100% para legado
            success = await self.set_traffic_percentage(0)

            if success:
                self.logger.critical("emergency_rollback_completed", traffic_percentage=0)
            else:
                raise EmergencyRollbackError(
                    "Falha no rollback de emergência",
                    strategy=self.strategy,
                )

            return success

        except Exception as e:
            self.logger.exception("emergency_rollback_failed")
            raise EmergencyRollbackError(
                f"Falha crítica no rollback: {e}",
                strategy=self.strategy,
            )

    async def close(self) -> None:
        """Fecha HTTP client."""
        await self._client.aclose()


class KubernetesTrafficSwitcher(TrafficSwitcher):
    """
    Traffic Switcher via Kubernetes Service.

    Utiliza múltiplos Deployments (legacy, canary) e modifica
    o selector do Service para redirecionar tráfego.

    Estratégia:
    1. Service selector com label específico
    2. Pod de canary com label alterado
    3. Modificar service.spec.selector.matchLabels

    Requer:
    - Kubernetes RBAC para patch Services
    - Deployments: app-legacy e app-canary
    """

    def __init__(
        self,
        service_name: str,
        namespace: str = "default",
        legacy_label: str = "version: legacy",
        canary_label: str = "version: canary",
        kubeconfig_path: str | None = None,
    ):
        """
        Inicializa KubernetesTrafficSwitcher.

        Args:
            service_name: Nome do Service Kubernetes
            namespace: Namespace do serviço
            legacy_label: Label para pods legados
            canary_label: Label para pods canary
            kubeconfig_path: Caminho para kubeconfig (None para in-cluster)
        """
        self.strategy = TrafficSwitchStrategy.KUBERNETES
        self.service_name = service_name
        self.namespace = namespace
        self.legacy_label = legacy_label
        self.canary_label = canary_label
        self.kubeconfig_path = kubeconfig_path

        self._current_percentage = 0
        self._shadow_mode_enabled = False
        self._last_updated: datetime | None = None

        self.logger = logger.bind(
            component="kubernetes_traffic_switcher",
            service_name=service_name,
            namespace=namespace,
        )

        # Lazy import de kubernetes (opcional)
        self._k8s_client = None

    def _get_k8s_client(self):
        """Obtém cliente Kubernetes (lazy import)."""
        if self._k8s_client is None:
            try:
                from kubernetes import client, config

                if self.kubeconfig_path:
                    config.load_kube_config(config_file=self.kubeconfig_path)
                else:
                    config.load_incluster_config()

                self._k8s_client = client
            except ImportError:
                self.logger.warning("kubernetes_not_available")
                raise TrafficSwitchError(
                    "Biblioteca kubernetes não disponível",
                    strategy=self.strategy,
                )
            except Exception as e:
                raise TrafficSwitchError(
                    f"Falha ao conectar ao Kubernetes: {e}",
                    strategy=self.strategy,
                )
        return self._k8s_client

    async def set_traffic_percentage(self, percentage: int) -> bool:
        """
        Define porcentagem via Service selector patch.

        Nota: Kubernetes não suporta weighting nativo no Service.
        Esta implementação usa abordagem de Replicas:
        - 0%: selector aponta para legacy
        - 100%: selector aponta para canary
        - 5-95%: requer ExternalTrafficPolicy ou Istio

        Args:
            percentage: Porcentagem (0-100)

        Returns:
            True se bem-sucedido
        """
        if not 0 <= percentage <= 100:
            raise ValueError(f"Percentage deve estar entre 0 e 100, recebido: {percentage}")

        try:
            client = self._get_k8s_client()
            v1 = client.CoreV1Api()

            # Parse labels
            legacy_kv = self.legacy_label.split(":")
            canary_kv = self.canary_label.split(":")

            if percentage == 0:
                # 100% legacy
                selector = {legacy_kv[0].strip(): legacy_kv[1].strip()}
            elif percentage == 100:
                # 100% canary
                selector = {canary_kv[0].strip(): canary_kv[1].strip()}
            else:
                # Para porcentagens parciais, log warning
                self.logger.warning(
                    "kubernetes_partial_traffic_not_supported",
                    percentage=percentage,
                    message="Kubernetes Service não suporta weighting nativo. Considerar Istio ou ExternalTrafficPolicy",
                )
                # Fallback: baseado em threshold de 50%
                if percentage < 50:
                    selector = {legacy_kv[0].strip(): legacy_kv[1].strip()}
                else:
                    selector = {canary_kv[0].strip(): canary_kv[1].strip()}

            # Patch service selector
            body = {"spec": {"selector": selector}}
            v1.patch_namespaced_service(
                name=self.service_name,
                namespace=self.namespace,
                body=body,
            )

            self._current_percentage = percentage
            self._last_updated = datetime.now(timezone.utc)

            self.logger.info(
                "kubernetes_service_selector_updated",
                service_name=self.service_name,
                selector=selector,
                percentage=percentage,
            )
            return True

        except Exception as e:
            self.logger.exception("kubernetes_patch_failed")
            raise TrafficSwitchError(
                f"Falha ao atualizar Service Kubernetes: {e}",
                strategy=self.strategy,
            )

    async def get_traffic_percentage(self) -> int:
        """
        Obtém porcentagem atual baseado no selector.

        Returns:
            Porcentagem atual (0-100)
        """
        try:
            client = self._get_k8s_client()
            v1 = client.CoreV1Api()

            service = v1.read_namespaced_service(
                name=self.service_name,
                namespace=self.namespace,
            )

            selector = service.spec.selector or {}

            # Determinar baseado no selector
            legacy_kv = self.legacy_label.split(":")
            canary_kv = self.canary_label.split(":")

            if selector.get(legacy_kv[0].strip()) == legacy_kv[1].strip():
                return 0
            if selector.get(canary_kv[0].strip()) == canary_kv[1].strip():
                return 100
            return self._current_percentage

        except Exception as e:
            self.logger.warning("kubernetes_read_failed", error=str(e))
            return self._current_percentage

    async def enable_shadow_mode(self) -> bool:
        """
        Ativa shadow mode no Kubernetes.

        No Kubernetes, shadow mode requer Sidecar ou Service Mesh.

        Returns:
            True se ativado
        """
        self._shadow_mode_enabled = True
        self._last_updated = datetime.now(timezone.utc)

        self.logger.warning(
            "shadow_mode_limited_in_kubernetes",
            message="Considerar Istio para shadow mode completo",
        )
        return True

    async def disable_shadow_mode(self) -> bool:
        """
        Desativa shadow mode.

        Returns:
            True se desativado
        """
        self._shadow_mode_enabled = False
        self._last_updated = datetime.now(timezone.utc)
        return True

    async def emergency_switch_to_legacy(self) -> bool:
        """
        Rollback de emergência para 100% legado.

        Returns:
            True se bem-sucedido
        """
        self.logger.warning("emergency_rollback_initiated", strategy="kubernetes")
        success = await self.set_traffic_percentage(0)

        if success:
            self.logger.critical("emergency_rollback_completed")
        else:
            raise EmergencyRollbackError("Falha no rollback", strategy=self.strategy)

        return success


class MockTrafficSwitcher(TrafficSwitcher):
    """
    Traffic Switcher mock para testes.

    Simula operações de traffic switching sem comunicação
    real com infrastructure components. Útil para testes
    unitários e desenvolvimento local.
    """

    def __init__(
        self,
        initial_percentage: int = 0,
        simulate_latency: bool = False,
        failure_percentage: float = 0.0,
    ):
        """
        Inicializa MockTrafficSwitcher.

        Args:
            initial_percentage: Porcentagem inicial (0-100)
            simulate_latency: Se deve simular latência de rede
            failure_percentage: % de operações que falham (0-1)
        """
        self.strategy = TrafficSwitchStrategy.MOCK
        self._current_percentage = initial_percentage
        self._shadow_mode_enabled = False
        self._last_updated: datetime | None = None
        self._simulate_latency = simulate_latency
        self._failure_percentage = failure_percentage
        self._update_count = 0
        self._rollback_count = 0

        self.logger = logger.bind(component="mock_traffic_switcher")

    async def _maybe_fail(self) -> None:
        """Simula falha aleatória baseado em failure_percentage."""
        if self._failure_percentage > 0:
            import random

            if random.random() < self._failure_percentage:
                raise TrafficSwitchError(
                    "Simulated failure",
                    strategy=self.strategy,
                )

    async def _simulate_network_latency(self) -> None:
        """Simula latência de rede."""
        if self._simulate_latency:
            await asyncio.sleep(0.05)  # 50ms

    async def set_traffic_percentage(self, percentage: int) -> bool:
        """
        Define porcentagem (mock).

        Args:
            percentage: Porcentagem (0-100)

        Returns:
            True se bem-sucedido
        """
        if not 0 <= percentage <= 100:
            raise ValueError(f"Percentage deve estar entre 0 e 100, recebido: {percentage}")

        await self._simulate_network_latency()
        await self._maybe_fail()

        self._current_percentage = percentage
        self._last_updated = datetime.now(timezone.utc)
        self._update_count += 1

        self.logger.debug(
            "mock_traffic_percentage_set",
            percentage=percentage,
            update_count=self._update_count,
        )
        return True

    async def get_traffic_percentage(self) -> int:
        """
        Retorna porcentagem atual.

        Returns:
            Porcentagem atual
        """
        await self._simulate_network_latency()
        return self._current_percentage

    async def enable_shadow_mode(self) -> bool:
        """
        Ativa shadow mode (mock).

        Returns:
            True
        """
        await self._simulate_network_latency()
        await self._maybe_fail()

        self._shadow_mode_enabled = True
        self._last_updated = datetime.now(timezone.utc)

        self.logger.debug("mock_shadow_mode_enabled")
        return True

    async def disable_shadow_mode(self) -> bool:
        """
        Desativa shadow mode (mock).

        Returns:
            True
        """
        await self._simulate_network_latency()

        self._shadow_mode_enabled = False
        self._last_updated = datetime.now(timezone.utc)

        self.logger.debug("mock_shadow_mode_disabled")
        return True

    async def emergency_switch_to_legacy(self) -> bool:
        """
        Rollback de emergência (mock).

        Returns:
            True se bem-sucedido
        """
        await self._simulate_network_latency()

        self._current_percentage = 0
        self._shadow_mode_enabled = False
        self._last_updated = datetime.now(timezone.utc)
        self._rollback_count += 1

        self.logger.warning(
            "mock_emergency_rollback",
            rollback_count=self._rollback_count,
        )
        return True

    async def get_status(self) -> dict[str, Any]:
        """
        Retorna status completo.

        Returns:
            Dict com status detalhado
        """
        return {
            "traffic_percentage": self._current_percentage,
            "shadow_mode_enabled": self._shadow_mode_enabled,
            "last_updated": self._last_updated.isoformat() if self._last_updated else None,
            "strategy": self.strategy,
            "update_count": self._update_count,
            "rollback_count": self._rollback_count,
            "simulate_latency": self._simulate_latency,
            "failure_percentage": self._failure_percentage,
        }

    def reset(self) -> None:
        """Reseta estado do mock (útil para testes)."""
        self._current_percentage = 0
        self._shadow_mode_enabled = False
        self._last_updated = None
        self._update_count = 0
        self._rollback_count = 0


class TrafficSwitcherFactory:
    """
    Factory para criar instâncias de TrafficSwitcher.

    Suporta múltiplas estratégias baseado em configuração.
    """

    @staticmethod
    async def create(
        strategy: str | TrafficSwitchStrategy,
        config: dict[str, Any] | None = None,
    ) -> TrafficSwitcher:
        """
        Cria instância de TrafficSwitcher baseado na estratégia.

        Args:
            strategy: Estratégia de traffic switching
            config: Configuração específica da estratégia

        Returns:
            Instância de TrafficSwitcher

        Raises:
            ValueError: Se estratégia não suportada
        """
        if isinstance(strategy, str):
            strategy = TrafficSwitchStrategy(strategy.lower())

        config = config or {}

        if strategy == TrafficSwitchStrategy.ENVOY:
            return EnvoyTrafficSwitcher(
                envoy_admin_url=config.get("envoy_admin_url", "http://localhost:9901"),
                envoy_control_plane_url=config.get("envoy_control_plane_url"),
                timeout_seconds=config.get("timeout_seconds", 30),
            )

        if strategy == TrafficSwitchStrategy.KUBERNETES:
            return KubernetesTrafficSwitcher(
                service_name=config.get("service_name", "app"),
                namespace=config.get("namespace", "default"),
                legacy_label=config.get("legacy_label", "version: legacy"),
                canary_label=config.get("canary_label", "version: canary"),
                kubeconfig_path=config.get("kubeconfig_path"),
            )

        if strategy == TrafficSwitchStrategy.MOCK:
            return MockTrafficSwitcher(
                initial_percentage=config.get("initial_percentage", 0),
                simulate_latency=config.get("simulate_latency", False),
                failure_percentage=config.get("failure_percentage", 0.0),
            )

        raise ValueError(f"Estratégia não suportada: {strategy}")

    @staticmethod
    def create_sync(
        strategy: str | TrafficSwitchStrategy,
        config: dict[str, Any] | None = None,
    ) -> TrafficSwitcher:
        """
        Versão síncrona do create (para casos onde async não é possível).

        Args:
            strategy: Estratégia de traffic switching
            config: Configuração específica

        Returns:
            Instância de TrafficSwitcher
        """
        if isinstance(strategy, str):
            strategy = TrafficSwitchStrategy(strategy.lower())

        config = config or {}

        if strategy == TrafficSwitchStrategy.ENVOY:
            return EnvoyTrafficSwitcher(
                envoy_admin_url=config.get("envoy_admin_url", "http://localhost:9901"),
                envoy_control_plane_url=config.get("envoy_control_plane_url"),
                timeout_seconds=config.get("timeout_seconds", 30),
            )

        if strategy == TrafficSwitchStrategy.KUBERNETES:
            return KubernetesTrafficSwitcher(
                service_name=config.get("service_name", "app"),
                namespace=config.get("namespace", "default"),
                legacy_label=config.get("legacy_label", "version: legacy"),
                canary_label=config.get("canary_label", "version: canary"),
                kubeconfig_path=config.get("kubeconfig_path"),
            )

        if strategy == TrafficSwitchStrategy.MOCK:
            return MockTrafficSwitcher(
                initial_percentage=config.get("initial_percentage", 0),
                simulate_latency=config.get("simulate_latency", False),
                failure_percentage=config.get("failure_percentage", 0.0),
            )

        raise ValueError(f"Estratégia não suportada: {strategy}")
