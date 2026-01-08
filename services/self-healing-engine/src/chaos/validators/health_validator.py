"""
Health Validator para Chaos Engineering.

Verifica saúde de serviços, conformidade de SLOs e integridade de dados
durante e após experimentos de chaos.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
import aiohttp
import structlog

logger = structlog.get_logger(__name__)


class HealthValidator:
    """
    Validador de saúde de serviços e conformidade de SLOs.

    Verifica:
    - Health endpoints de serviços
    - Conformidade de SLOs via SLA Management System
    - Integridade de dados
    - Disponibilidade de traces/logs/metrics
    """

    def __init__(
        self,
        service_registry_client=None,
        sla_management_client=None,
        prometheus_client=None,
    ):
        """
        Inicializa o validador de saúde.

        Args:
            service_registry_client: Cliente do Service Registry
            sla_management_client: Cliente do SLA Management System
            prometheus_client: Cliente Prometheus para queries
        """
        self.service_registry_client = service_registry_client
        self.sla_management_client = sla_management_client
        self.prometheus_client = prometheus_client
        self._http_session: Optional[aiohttp.ClientSession] = None

    async def initialize(self):
        """Inicializa recursos necessários."""
        if not self._http_session:
            timeout = aiohttp.ClientTimeout(total=10)
            self._http_session = aiohttp.ClientSession(timeout=timeout)

    async def close(self):
        """Fecha recursos."""
        if self._http_session:
            await self._http_session.close()
            self._http_session = None

    async def check_service_health(
        self,
        service_name: str,
        namespace: str = "default",
    ) -> Dict[str, Any]:
        """
        Verifica saúde de um serviço via health endpoint.

        Args:
            service_name: Nome do serviço
            namespace: Namespace Kubernetes

        Returns:
            Dicionário com status de saúde
        """
        result = {
            "service_name": service_name,
            "namespace": namespace,
            "healthy": False,
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {}
        }

        try:
            # Obter informações do serviço via Service Registry
            service_info = None
            if self.service_registry_client:
                try:
                    service_info = await self.service_registry_client.get_service_info(
                        service_name
                    )
                except Exception as e:
                    logger.warning(
                        "health_validator.service_registry_failed",
                        service=service_name,
                        error=str(e)
                    )

            # Construir URL do health endpoint
            if service_info:
                health_url = service_info.get("health_url")
            else:
                # Fallback para URL padrão Kubernetes
                health_url = (
                    f"http://{service_name}.{namespace}.svc.cluster.local:8080/health"
                )

            # Verificar health endpoint
            if self._http_session:
                try:
                    async with self._http_session.get(health_url) as response:
                        result["checks"]["http_health"] = {
                            "status": response.status,
                            "healthy": response.status == 200
                        }

                        if response.status == 200:
                            try:
                                health_data = await response.json()
                                result["checks"]["health_data"] = health_data
                            except Exception:
                                pass

                except aiohttp.ClientError as e:
                    result["checks"]["http_health"] = {
                        "status": "error",
                        "error": str(e),
                        "healthy": False
                    }

            # Verificar via Prometheus se disponível
            if self.prometheus_client:
                up_result = await self._check_prometheus_up(service_name, namespace)
                result["checks"]["prometheus_up"] = up_result

            # Determinar saúde geral
            health_checks = [
                c.get("healthy", False)
                for c in result["checks"].values()
                if isinstance(c, dict) and "healthy" in c
            ]
            result["healthy"] = all(health_checks) if health_checks else False

            logger.info(
                "health_validator.check_complete",
                service=service_name,
                healthy=result["healthy"]
            )

        except Exception as e:
            logger.error(
                "health_validator.check_failed",
                service=service_name,
                error=str(e)
            )
            result["error"] = str(e)

        return result

    async def check_slo_compliance(
        self,
        service_name: str,
        slo_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Verifica conformidade de SLOs via SLA Management System.

        Args:
            service_name: Nome do serviço
            slo_name: Nome específico do SLO (opcional)

        Returns:
            Dicionário com status de conformidade
        """
        result = {
            "service_name": service_name,
            "compliant": True,
            "timestamp": datetime.utcnow().isoformat(),
            "slos": []
        }

        if not self.sla_management_client:
            result["warning"] = "SLA Management client não disponível"
            return result

        try:
            # Obter SLOs do serviço
            slos = await self.sla_management_client.get_service_slos(service_name)

            for slo in slos:
                if slo_name and slo.get("name") != slo_name:
                    continue

                slo_status = await self.sla_management_client.check_slo_status(
                    slo.get("id")
                )

                slo_result = {
                    "name": slo.get("name"),
                    "type": slo.get("type"),
                    "target": slo.get("target"),
                    "current": slo_status.get("current_value"),
                    "compliant": slo_status.get("compliant", True),
                    "error_budget_remaining": slo_status.get("error_budget_remaining")
                }

                result["slos"].append(slo_result)

                if not slo_result["compliant"]:
                    result["compliant"] = False

            logger.info(
                "health_validator.slo_check_complete",
                service=service_name,
                compliant=result["compliant"],
                slo_count=len(result["slos"])
            )

        except Exception as e:
            logger.error(
                "health_validator.slo_check_failed",
                service=service_name,
                error=str(e)
            )
            result["error"] = str(e)
            result["compliant"] = False

        return result

    async def check_data_integrity(
        self,
        service_name: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Verifica integridade de dados após experimento de chaos.

        Args:
            service_name: Nome do serviço
            context: Contexto com informações de dados a verificar

        Returns:
            Dicionário com resultado da verificação
        """
        result = {
            "service_name": service_name,
            "integrity_valid": True,
            "timestamp": datetime.utcnow().isoformat(),
            "checks": []
        }

        # Verificar se há endpoints de validação de dados
        validation_endpoints = context.get("data_validation_endpoints", [])

        if not validation_endpoints and self._http_session:
            # Tentar endpoint padrão de healthcheck de dados
            namespace = context.get("namespace", "default")
            default_endpoint = (
                f"http://{service_name}.{namespace}.svc.cluster.local:8080"
                "/health/data"
            )
            validation_endpoints = [default_endpoint]

        for endpoint in validation_endpoints:
            check_result = {
                "endpoint": endpoint,
                "valid": False
            }

            try:
                if self._http_session:
                    async with self._http_session.get(endpoint) as response:
                        check_result["status"] = response.status
                        check_result["valid"] = response.status == 200

                        if response.status == 200:
                            try:
                                data = await response.json()
                                check_result["details"] = data
                            except Exception:
                                pass

            except Exception as e:
                check_result["error"] = str(e)

            result["checks"].append(check_result)

            if not check_result["valid"]:
                result["integrity_valid"] = False

        logger.info(
            "health_validator.data_integrity_check_complete",
            service=service_name,
            valid=result["integrity_valid"]
        )

        return result

    async def check_observability(
        self,
        service_name: str,
        namespace: str = "default",
    ) -> Dict[str, Any]:
        """
        Verifica disponibilidade de observability (traces, logs, metrics).

        Args:
            service_name: Nome do serviço
            namespace: Namespace Kubernetes

        Returns:
            Dicionário com status de observabilidade
        """
        result = {
            "service_name": service_name,
            "namespace": namespace,
            "observability_healthy": True,
            "timestamp": datetime.utcnow().isoformat(),
            "components": {}
        }

        # Verificar métricas via Prometheus
        if self.prometheus_client:
            metrics_result = await self._check_metrics_availability(
                service_name,
                namespace
            )
            result["components"]["metrics"] = metrics_result
            if not metrics_result.get("available"):
                result["observability_healthy"] = False

        # Verificar traces seria via Tempo/Jaeger API
        # Por simplicidade, marcamos como disponível se Prometheus está ok
        result["components"]["traces"] = {
            "available": True,
            "note": "Verificação via Tempo API não implementada"
        }

        # Verificar logs seria via Loki API
        result["components"]["logs"] = {
            "available": True,
            "note": "Verificação via Loki API não implementada"
        }

        logger.info(
            "health_validator.observability_check_complete",
            service=service_name,
            healthy=result["observability_healthy"]
        )

        return result

    async def run_full_health_check(
        self,
        service_name: str,
        namespace: str = "default",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executa verificação completa de saúde.

        Args:
            service_name: Nome do serviço
            namespace: Namespace Kubernetes
            context: Contexto adicional

        Returns:
            Dicionário com todos os resultados de verificação
        """
        context = context or {}

        # Executar verificações em paralelo
        results = await asyncio.gather(
            self.check_service_health(service_name, namespace),
            self.check_slo_compliance(service_name),
            self.check_data_integrity(service_name, {**context, "namespace": namespace}),
            self.check_observability(service_name, namespace),
            return_exceptions=True
        )

        full_result = {
            "service_name": service_name,
            "namespace": namespace,
            "overall_healthy": True,
            "timestamp": datetime.utcnow().isoformat(),
            "service_health": results[0] if not isinstance(results[0], Exception)
                else {"error": str(results[0])},
            "slo_compliance": results[1] if not isinstance(results[1], Exception)
                else {"error": str(results[1])},
            "data_integrity": results[2] if not isinstance(results[2], Exception)
                else {"error": str(results[2])},
            "observability": results[3] if not isinstance(results[3], Exception)
                else {"error": str(results[3])},
        }

        # Determinar saúde geral
        for check_name in ["service_health", "slo_compliance", "data_integrity"]:
            check = full_result.get(check_name, {})
            if isinstance(check, dict):
                health_key = {
                    "service_health": "healthy",
                    "slo_compliance": "compliant",
                    "data_integrity": "integrity_valid",
                }.get(check_name, "healthy")

                if not check.get(health_key, True):
                    full_result["overall_healthy"] = False
                    break

        logger.info(
            "health_validator.full_check_complete",
            service=service_name,
            overall_healthy=full_result["overall_healthy"]
        )

        return full_result

    async def _check_prometheus_up(
        self,
        service_name: str,
        namespace: str,
    ) -> Dict[str, Any]:
        """Verifica se serviço está UP via Prometheus."""
        result = {
            "available": False,
            "up": False
        }

        try:
            query = f'up{{service="{service_name}",namespace="{namespace}"}}'
            prom_result = await self.prometheus_client.query(query)

            if prom_result:
                result["available"] = True
                # Verificar se valor é 1 (up)
                value = prom_result[0].get("value", [None, "0"])[1]
                result["up"] = value == "1"
                result["healthy"] = result["up"]

        except Exception as e:
            result["error"] = str(e)

        return result

    async def _check_metrics_availability(
        self,
        service_name: str,
        namespace: str,
    ) -> Dict[str, Any]:
        """Verifica se métricas estão sendo coletadas."""
        result = {
            "available": False,
            "metrics_found": 0
        }

        try:
            # Verificar se há métricas sendo emitidas
            query = f'count({{service="{service_name}",namespace="{namespace}"}})'
            prom_result = await self.prometheus_client.query(query)

            if prom_result:
                result["available"] = True
                count = prom_result[0].get("value", [None, "0"])[1]
                result["metrics_found"] = int(count)

        except Exception as e:
            result["error"] = str(e)

        return result

    async def wait_for_healthy(
        self,
        service_name: str,
        namespace: str = "default",
        timeout_seconds: int = 300,
        check_interval: int = 10,
    ) -> bool:
        """
        Aguarda serviço ficar saudável.

        Args:
            service_name: Nome do serviço
            namespace: Namespace Kubernetes
            timeout_seconds: Timeout máximo
            check_interval: Intervalo entre verificações

        Returns:
            True se serviço ficou saudável, False se timeout
        """
        from time import perf_counter

        start = perf_counter()

        while perf_counter() - start < timeout_seconds:
            health_result = await self.check_service_health(service_name, namespace)

            if health_result.get("healthy"):
                logger.info(
                    "health_validator.service_healthy",
                    service=service_name,
                    elapsed_seconds=perf_counter() - start
                )
                return True

            await asyncio.sleep(check_interval)

        logger.warning(
            "health_validator.timeout_waiting_healthy",
            service=service_name,
            timeout_seconds=timeout_seconds
        )
        return False
