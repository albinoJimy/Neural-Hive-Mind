"""
Application Fault Injector para Chaos Engineering.

Implementa injeção de falhas em nível de aplicação como erros HTTP,
respostas lentas e trigger de circuit breakers.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
import structlog
from kubernetes import client

from .base_injector import BaseFaultInjector, InjectionResult
from ..chaos_models import FaultInjection, FaultType, TargetSelector
from ..chaos_config import CHAOS_LABELS, CHAOS_ANNOTATIONS

logger = structlog.get_logger(__name__)


class ApplicationFaultInjector(BaseFaultInjector):
    """
    Injetor de falhas em nível de aplicação.

    Suporta:
    - Injeção de erros HTTP via Istio VirtualService
    - Injeção de delays HTTP via Istio VirtualService
    - Trigger de circuit breakers via carga artificial
    """

    def __init__(self, *args, k8s_custom_objects=None, **kwargs):
        """
        Inicializa o injetor de aplicação.

        Args:
            k8s_custom_objects: Cliente Kubernetes CustomObjectsApi para Istio
        """
        super().__init__(*args, **kwargs)
        self.k8s_custom_objects = k8s_custom_objects

    @property
    def supported_fault_types(self) -> List[FaultType]:
        return [
            FaultType.HTTP_ERROR,
            FaultType.HTTP_DELAY,
            FaultType.CIRCUIT_BREAKER_TRIGGER,
        ]

    async def inject(self, injection: FaultInjection) -> InjectionResult:
        """Injeta falha em nível de aplicação."""
        start_time = datetime.utcnow()

        if injection.fault_type not in self.supported_fault_types:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message=f"Tipo de falha não suportado: {injection.fault_type}",
                start_time=start_time
            )

        try:
            if injection.fault_type == FaultType.HTTP_ERROR:
                result = await self._inject_http_error(injection)
            elif injection.fault_type == FaultType.HTTP_DELAY:
                result = await self._inject_http_delay(injection)
            elif injection.fault_type == FaultType.CIRCUIT_BREAKER_TRIGGER:
                result = await self._trigger_circuit_breaker(injection)
            else:
                result = InjectionResult(
                    success=False,
                    injection_id=injection.id,
                    fault_type=injection.fault_type,
                    error_message="Tipo de falha não implementado"
                )

            if result.success:
                injection.start_time = start_time
                injection.status = "active"
                injection.rollback_data = result.rollback_data
                self._track_active_injection(injection)

            self._record_injection_metrics(
                injection.fault_type.value,
                "success" if result.success else "failed",
                injection.target.namespace
            )

            return result

        except Exception as e:
            logger.error(
                "application_injector.inject_failed",
                injection_id=injection.id,
                fault_type=injection.fault_type.value,
                error=str(e)
            )
            self._record_injection_metrics(
                injection.fault_type.value,
                "error",
                injection.target.namespace
            )
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message=str(e),
                start_time=start_time
            )

    async def _inject_http_error(self, injection: FaultInjection) -> InjectionResult:
        """
        Injeta erros HTTP via Istio VirtualService fault injection.

        Cria uma VirtualService que retorna o código de erro especificado
        para uma porcentagem das requisições.
        """
        if not self.k8s_custom_objects:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Cliente CustomObjectsApi não disponível para Istio"
            )

        params = injection.parameters
        status_code = params.http_status_code or 500
        path_pattern = params.http_path_pattern or "/*"
        percentage = injection.target.percentage or 100

        service_name = injection.target.service_name
        if not service_name:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="service_name é obrigatório para HTTP fault injection"
            )

        try:
            vs_name = f"chaos-http-error-{injection.id[:8]}"

            virtual_service = {
                "apiVersion": "networking.istio.io/v1beta1",
                "kind": "VirtualService",
                "metadata": {
                    "name": vs_name,
                    "namespace": injection.target.namespace,
                    "labels": {
                        **CHAOS_LABELS,
                        "chaos.neuralhive.io/injection-id": injection.id,
                    },
                    "annotations": {
                        "chaos.neuralhive.io/experiment-id": injection.id,
                        "chaos.neuralhive.io/created-at": datetime.utcnow().isoformat(),
                    }
                },
                "spec": {
                    "hosts": [service_name],
                    "http": [
                        {
                            "match": [
                                {"uri": {"prefix": path_pattern.replace("*", "")}}
                            ] if path_pattern != "/*" else [],
                            "fault": {
                                "abort": {
                                    "percentage": {"value": percentage},
                                    "httpStatus": status_code
                                }
                            },
                            "route": [
                                {
                                    "destination": {
                                        "host": service_name
                                    }
                                }
                            ]
                        }
                    ]
                }
            }

            self.k8s_custom_objects.create_namespaced_custom_object(
                group="networking.istio.io",
                version="v1beta1",
                namespace=injection.target.namespace,
                plural="virtualservices",
                body=virtual_service
            )

            logger.info(
                "application_injector.http_error_injected",
                vs_name=vs_name,
                service=service_name,
                status_code=status_code,
                percentage=percentage
            )

            return InjectionResult(
                success=True,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                affected_resources=[service_name],
                blast_radius=1,
                start_time=datetime.utcnow(),
                rollback_data={
                    "type": "istio_virtual_service",
                    "vs_name": vs_name,
                    "namespace": injection.target.namespace,
                }
            )

        except Exception as e:
            logger.error(
                "application_injector.http_error_failed",
                error=str(e)
            )
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message=str(e)
            )

    async def _inject_http_delay(self, injection: FaultInjection) -> InjectionResult:
        """
        Injeta delays HTTP via Istio VirtualService fault injection.

        Adiciona latência artificial às requisições.
        """
        if not self.k8s_custom_objects:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Cliente CustomObjectsApi não disponível para Istio"
            )

        params = injection.parameters
        delay_ms = params.http_delay_ms or 1000
        path_pattern = params.http_path_pattern or "/*"
        percentage = injection.target.percentage or 100

        service_name = injection.target.service_name
        if not service_name:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="service_name é obrigatório para HTTP fault injection"
            )

        try:
            vs_name = f"chaos-http-delay-{injection.id[:8]}"

            virtual_service = {
                "apiVersion": "networking.istio.io/v1beta1",
                "kind": "VirtualService",
                "metadata": {
                    "name": vs_name,
                    "namespace": injection.target.namespace,
                    "labels": {
                        **CHAOS_LABELS,
                        "chaos.neuralhive.io/injection-id": injection.id,
                    },
                    "annotations": {
                        "chaos.neuralhive.io/experiment-id": injection.id,
                        "chaos.neuralhive.io/created-at": datetime.utcnow().isoformat(),
                    }
                },
                "spec": {
                    "hosts": [service_name],
                    "http": [
                        {
                            "match": [
                                {"uri": {"prefix": path_pattern.replace("*", "")}}
                            ] if path_pattern != "/*" else [],
                            "fault": {
                                "delay": {
                                    "percentage": {"value": percentage},
                                    "fixedDelay": f"{delay_ms}ms"
                                }
                            },
                            "route": [
                                {
                                    "destination": {
                                        "host": service_name
                                    }
                                }
                            ]
                        }
                    ]
                }
            }

            self.k8s_custom_objects.create_namespaced_custom_object(
                group="networking.istio.io",
                version="v1beta1",
                namespace=injection.target.namespace,
                plural="virtualservices",
                body=virtual_service
            )

            logger.info(
                "application_injector.http_delay_injected",
                vs_name=vs_name,
                service=service_name,
                delay_ms=delay_ms,
                percentage=percentage
            )

            return InjectionResult(
                success=True,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                affected_resources=[service_name],
                blast_radius=1,
                start_time=datetime.utcnow(),
                rollback_data={
                    "type": "istio_virtual_service",
                    "vs_name": vs_name,
                    "namespace": injection.target.namespace,
                }
            )

        except Exception as e:
            logger.error(
                "application_injector.http_delay_failed",
                error=str(e)
            )
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message=str(e)
            )

    async def _trigger_circuit_breaker(
        self,
        injection: FaultInjection
    ) -> InjectionResult:
        """
        Força abertura de circuit breakers via carga artificial.

        Gera erros ou latência suficiente para abrir circuit breakers.
        """
        service_name = injection.target.service_name
        if not service_name:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="service_name é obrigatório para circuit breaker trigger"
            )

        # Usar combinação de HTTP errors e delays para forçar abertura
        # Criar VirtualService com alto percentual de erros
        params = injection.parameters
        error_percentage = 80  # 80% de erros para forçar abertura rápida

        try:
            vs_name = f"chaos-cb-trigger-{injection.id[:8]}"

            virtual_service = {
                "apiVersion": "networking.istio.io/v1beta1",
                "kind": "VirtualService",
                "metadata": {
                    "name": vs_name,
                    "namespace": injection.target.namespace,
                    "labels": {
                        **CHAOS_LABELS,
                        "chaos.neuralhive.io/injection-id": injection.id,
                    },
                },
                "spec": {
                    "hosts": [service_name],
                    "http": [
                        {
                            "fault": {
                                "abort": {
                                    "percentage": {"value": error_percentage},
                                    "httpStatus": 503
                                }
                            },
                            "route": [
                                {
                                    "destination": {
                                        "host": service_name
                                    }
                                }
                            ]
                        }
                    ]
                }
            }

            if self.k8s_custom_objects:
                self.k8s_custom_objects.create_namespaced_custom_object(
                    group="networking.istio.io",
                    version="v1beta1",
                    namespace=injection.target.namespace,
                    plural="virtualservices",
                    body=virtual_service
                )

                logger.info(
                    "application_injector.circuit_breaker_trigger_started",
                    vs_name=vs_name,
                    service=service_name,
                    error_percentage=error_percentage
                )

                return InjectionResult(
                    success=True,
                    injection_id=injection.id,
                    fault_type=injection.fault_type,
                    affected_resources=[service_name],
                    blast_radius=1,
                    start_time=datetime.utcnow(),
                    rollback_data={
                        "type": "istio_virtual_service",
                        "vs_name": vs_name,
                        "namespace": injection.target.namespace,
                    }
                )
            else:
                # Fallback: apenas registrar que CB deveria ser trigado
                logger.warning(
                    "application_injector.circuit_breaker_trigger_no_istio",
                    service=service_name,
                    note="Istio não disponível, trigger manual necessário"
                )
                return InjectionResult(
                    success=True,
                    injection_id=injection.id,
                    fault_type=injection.fault_type,
                    affected_resources=[service_name],
                    blast_radius=1,
                    start_time=datetime.utcnow(),
                    rollback_data={
                        "type": "manual",
                        "service": service_name,
                        "namespace": injection.target.namespace,
                    },
                    metadata={"note": "Circuit breaker trigger sem Istio"}
                )

        except Exception as e:
            logger.error(
                "application_injector.circuit_breaker_trigger_failed",
                error=str(e)
            )
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message=str(e)
            )

    async def validate(self, injection_id: str) -> bool:
        """Valida se a injeção de aplicação está ativa."""
        if injection_id not in self._active_injections:
            return False

        injection = self._active_injections[injection_id]
        rollback_data = injection.rollback_data

        if rollback_data.get("type") == "istio_virtual_service":
            vs_name = rollback_data.get("vs_name")
            namespace = rollback_data.get("namespace")

            if not self.k8s_custom_objects:
                return False

            try:
                self.k8s_custom_objects.get_namespaced_custom_object(
                    group="networking.istio.io",
                    version="v1beta1",
                    namespace=namespace,
                    plural="virtualservices",
                    name=vs_name
                )
                return True
            except Exception:
                return False

        elif rollback_data.get("type") == "manual":
            # Para trigger manual, assumir ativo
            return True

        return False

    async def rollback(self, injection_id: str) -> InjectionResult:
        """Remove a injeção de aplicação."""
        if injection_id not in self._active_injections:
            return InjectionResult(
                success=False,
                injection_id=injection_id,
                fault_type=FaultType.HTTP_ERROR,
                error_message="Injeção não encontrada"
            )

        injection = self._active_injections[injection_id]
        rollback_data = injection.rollback_data
        rollback_type = rollback_data.get("type")

        try:
            if rollback_type == "istio_virtual_service":
                result = await self._delete_virtual_service(injection_id, rollback_data)
            elif rollback_type == "manual":
                result = InjectionResult(
                    success=True,
                    injection_id=injection_id,
                    fault_type=injection.fault_type,
                    end_time=datetime.utcnow(),
                    metadata={"note": "Rollback manual - nenhuma ação automática"}
                )
            else:
                result = InjectionResult(
                    success=False,
                    injection_id=injection_id,
                    fault_type=injection.fault_type,
                    error_message=f"Tipo de rollback desconhecido: {rollback_type}"
                )

            if result.success:
                self._untrack_active_injection(injection_id)
                self._record_rollback_metrics(injection.fault_type.value, "success")
            else:
                self._record_rollback_metrics(injection.fault_type.value, "failed")

            return result

        except Exception as e:
            logger.error(
                "application_injector.rollback_failed",
                injection_id=injection_id,
                error=str(e)
            )
            self._record_rollback_metrics(injection.fault_type.value, "error")
            return InjectionResult(
                success=False,
                injection_id=injection_id,
                fault_type=injection.fault_type,
                error_message=str(e)
            )

    async def _delete_virtual_service(
        self,
        injection_id: str,
        rollback_data: Dict[str, Any]
    ) -> InjectionResult:
        """Remove VirtualService do Istio."""
        vs_name = rollback_data.get("vs_name")
        namespace = rollback_data.get("namespace")

        if not self.k8s_custom_objects:
            return InjectionResult(
                success=False,
                injection_id=injection_id,
                fault_type=FaultType.HTTP_ERROR,
                error_message="Cliente CustomObjectsApi não disponível"
            )

        try:
            self.k8s_custom_objects.delete_namespaced_custom_object(
                group="networking.istio.io",
                version="v1beta1",
                namespace=namespace,
                plural="virtualservices",
                name=vs_name
            )

            logger.info(
                "application_injector.virtual_service_deleted",
                vs_name=vs_name,
                namespace=namespace
            )

            return InjectionResult(
                success=True,
                injection_id=injection_id,
                fault_type=FaultType.HTTP_ERROR,
                end_time=datetime.utcnow()
            )

        except Exception as e:
            return InjectionResult(
                success=False,
                injection_id=injection_id,
                fault_type=FaultType.HTTP_ERROR,
                error_message=str(e)
            )

    async def get_blast_radius(self, target: TargetSelector) -> int:
        """
        Calcula o blast radius para injeção de aplicação.

        Para HTTP faults, o blast radius é geralmente 1 (o serviço alvo).
        """
        if target.service_name:
            return 1
        return 0
