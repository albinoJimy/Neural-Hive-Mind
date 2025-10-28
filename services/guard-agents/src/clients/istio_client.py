"""Cliente para integração com Istio via Kubernetes API"""
from typing import Dict, Any, Optional, List
import structlog
from kubernetes import client
from kubernetes.client.rest import ApiException

logger = structlog.get_logger()


class IstioClient:
    """
    Cliente para criação e gerenciamento de recursos Istio.
    Manipula AuthorizationPolicy, EnvoyFilter e outros CRDs Istio.
    """

    def __init__(self, k8s_client, namespace: str = "neural-hive-resilience"):
        self.k8s_client = k8s_client
        self.namespace = namespace
        self.custom_api: Optional[client.CustomObjectsApi] = None

    async def connect(self):
        """Inicializa cliente Kubernetes Custom Objects API"""
        if not self.k8s_client or not self.k8s_client.api_client:
            raise RuntimeError("Kubernetes client not initialized")

        self.custom_api = client.CustomObjectsApi(self.k8s_client.api_client)
        logger.info("istio_client.connected", namespace=self.namespace)

    async def apply_authorization_policy(
        self,
        name: str,
        action: str,  # ALLOW, DENY, CUSTOM
        selector: Dict[str, str],
        rules: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Aplica AuthorizationPolicy Istio.

        Args:
            name: Nome da política
            action: ALLOW, DENY ou CUSTOM
            selector: Label selector para workloads
            rules: Regras de autorização

        Returns:
            Dict com resultado da criação
        """
        if not self.custom_api:
            raise RuntimeError("Client not connected")

        policy = {
            "apiVersion": "security.istio.io/v1beta1",
            "kind": "AuthorizationPolicy",
            "metadata": {
                "name": name,
                "namespace": self.namespace
            },
            "spec": {
                "action": action,
                "selector": {
                    "matchLabels": selector
                },
                "rules": rules
            }
        }

        try:
            logger.info(
                "istio_client.applying_authorization_policy",
                name=name,
                action=action,
                namespace=self.namespace
            )

            result = self.custom_api.create_namespaced_custom_object(
                group="security.istio.io",
                version="v1beta1",
                namespace=self.namespace,
                plural="authorizationpolicies",
                body=policy
            )

            logger.info(
                "istio_client.authorization_policy_applied",
                name=name
            )

            return {
                "success": True,
                "name": name,
                "kind": "AuthorizationPolicy",
                "action": action
            }

        except ApiException as e:
            if e.status == 409:  # Already exists
                logger.info(
                    "istio_client.authorization_policy_exists",
                    name=name
                )
                # Atualizar existente
                try:
                    result = self.custom_api.patch_namespaced_custom_object(
                        group="security.istio.io",
                        version="v1beta1",
                        namespace=self.namespace,
                        plural="authorizationpolicies",
                        name=name,
                        body=policy
                    )
                    return {
                        "success": True,
                        "name": name,
                        "kind": "AuthorizationPolicy",
                        "action": "updated"
                    }
                except Exception as update_error:
                    logger.error(
                        "istio_client.update_failed",
                        name=name,
                        error=str(update_error)
                    )
                    raise
            else:
                logger.error(
                    "istio_client.apply_failed",
                    name=name,
                    status=e.status,
                    error=str(e)
                )
                raise

    async def block_ip(
        self,
        source_ip: str,
        workload_selector: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Bloqueia IP específico usando AuthorizationPolicy.

        Args:
            source_ip: IP a ser bloqueado
            workload_selector: Selector de workloads (opcional)

        Returns:
            Dict com resultado
        """
        name = f"block-ip-{source_ip.replace('.', '-')}"
        selector = workload_selector or {"app": "neural-hive"}

        rules = [
            {
                "from": [
                    {
                        "source": {
                            "ipBlocks": [source_ip]
                        }
                    }
                ]
            }
        ]

        return await self.apply_authorization_policy(
            name=name,
            action="DENY",
            selector=selector,
            rules=rules
        )

    async def apply_rate_limit(
        self,
        name: str,
        workload_selector: Dict[str, str],
        requests_per_unit: int = 100,
        unit: str = "MINUTE"
    ) -> Dict[str, Any]:
        """
        Aplica rate limiting via EnvoyFilter.

        Args:
            name: Nome do filtro
            workload_selector: Selector de workloads
            requests_per_unit: Número de requisições permitidas
            unit: Unidade de tempo (SECOND, MINUTE, HOUR)

        Returns:
            Dict com resultado
        """
        if not self.custom_api:
            raise RuntimeError("Client not connected")

        envoy_filter = {
            "apiVersion": "networking.istio.io/v1alpha3",
            "kind": "EnvoyFilter",
            "metadata": {
                "name": name,
                "namespace": self.namespace
            },
            "spec": {
                "workloadSelector": {
                    "labels": workload_selector
                },
                "configPatches": [
                    {
                        "applyTo": "HTTP_FILTER",
                        "match": {
                            "context": "SIDECAR_INBOUND",
                            "listener": {
                                "filterChain": {
                                    "filter": {
                                        "name": "envoy.filters.network.http_connection_manager"
                                    }
                                }
                            }
                        },
                        "patch": {
                            "operation": "INSERT_BEFORE",
                            "value": {
                                "name": "envoy.filters.http.local_ratelimit",
                                "typed_config": {
                                    "@type": "type.googleapis.com/envoy.extensions.filters.http.local_ratelimit.v3.LocalRateLimit",
                                    "stat_prefix": "http_local_rate_limiter",
                                    "token_bucket": {
                                        "max_tokens": requests_per_unit,
                                        "tokens_per_fill": requests_per_unit,
                                        "fill_interval": f"1{unit[0].lower()}"  # 1s, 1m, 1h
                                    },
                                    "filter_enabled": {
                                        "runtime_key": "local_rate_limit_enabled",
                                        "default_value": {
                                            "numerator": 100,
                                            "denominator": "HUNDRED"
                                        }
                                    },
                                    "filter_enforced": {
                                        "runtime_key": "local_rate_limit_enforced",
                                        "default_value": {
                                            "numerator": 100,
                                            "denominator": "HUNDRED"
                                        }
                                    }
                                }
                            }
                        }
                    }
                ]
            }
        }

        try:
            logger.info(
                "istio_client.applying_rate_limit",
                name=name,
                requests_per_unit=requests_per_unit,
                unit=unit
            )

            result = self.custom_api.create_namespaced_custom_object(
                group="networking.istio.io",
                version="v1alpha3",
                namespace=self.namespace,
                plural="envoyfilters",
                body=envoy_filter
            )

            logger.info("istio_client.rate_limit_applied", name=name)

            return {
                "success": True,
                "name": name,
                "kind": "EnvoyFilter",
                "rate_limit": f"{requests_per_unit}/{unit}"
            }

        except ApiException as e:
            if e.status == 409:
                logger.info("istio_client.envoy_filter_exists", name=name)
                return {
                    "success": True,
                    "name": name,
                    "kind": "EnvoyFilter",
                    "action": "already_exists"
                }
            else:
                logger.error(
                    "istio_client.rate_limit_failed",
                    name=name,
                    error=str(e)
                )
                raise

    def is_connected(self) -> bool:
        """Verifica se cliente está conectado"""
        return self.custom_api is not None
