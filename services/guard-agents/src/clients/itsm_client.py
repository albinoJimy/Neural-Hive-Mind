"""ITSM client for ticketing system integration"""
from typing import Dict, Any, Optional, List
import httpx
import structlog
from datetime import datetime, timezone
from enum import Enum
from prometheus_client import Counter, Histogram

logger = structlog.get_logger()

# Prometheus metrics
itsm_operations_total = Counter(
    'guard_agents_itsm_operations_total',
    'Total de operacoes ITSM',
    ['operation', 'itsm_type', 'status']
)

itsm_operation_duration = Histogram(
    'guard_agents_itsm_operation_duration_seconds',
    'Duracao das operacoes ITSM',
    ['operation'],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
)


class ITSMType(str, Enum):
    """Tipos de sistemas ITSM suportados"""
    SERVICENOW = "servicenow"
    JIRA = "jira"
    PAGERDUTY = "pagerduty"
    OPSGENIE = "opsgenie"
    WEBHOOK = "webhook"  # Generic webhook


class IncidentPriority(str, Enum):
    """Prioridades de incidentes"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ITSMClient:
    """
    Cliente para integração com sistemas ITSM (IT Service Management).

    Suporta criação de incidentes em:
    - ServiceNow
    - Jira Service Management
    - PagerDuty
    - OpsGenie
    - Generic webhook

    Requer configuração de URL e credenciais do sistema ITSM.
    """

    def __init__(
        self,
        itsm_type: str = "webhook",
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        enabled: bool = True,
        timeout_seconds: int = 30
    ):
        self.itsm_type = ITSMType(itsm_type.lower()) if itsm_type else ITSMType.WEBHOOK
        self.base_url = base_url
        self.api_key = api_key
        self.username = username
        self.password = password
        self.enabled = enabled
        self.timeout = timeout_seconds
        self._client: Optional[httpx.AsyncClient] = None

    async def connect(self):
        """Inicializa cliente HTTP"""
        if not self.enabled:
            logger.info("itsm_client.disabled")
            return

        if not self.base_url:
            logger.warning("itsm_client.no_base_url")
            return

        try:
            headers = self._build_headers()
            auth = None

            if self.username and self.password:
                auth = httpx.BasicAuth(self.username, self.password)

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                auth=auth,
                timeout=self.timeout
            )

            logger.info(
                "itsm_client.connected",
                itsm_type=self.itsm_type.value,
                base_url=self.base_url
            )

        except Exception as e:
            logger.error(
                "itsm_client.connection_failed",
                error=str(e)
            )

    async def close(self):
        """Fecha cliente HTTP"""
        if self._client:
            await self._client.aclose()
            logger.info("itsm_client.closed")

    def is_healthy(self) -> bool:
        """Verifica se cliente está saudável"""
        return self.enabled and self._client is not None and self.base_url is not None

    def _build_headers(self) -> Dict[str, str]:
        """Constrói headers baseado no tipo de ITSM"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        if self.api_key:
            if self.itsm_type == ITSMType.SERVICENOW:
                headers["Authorization"] = f"Bearer {self.api_key}"
            elif self.itsm_type == ITSMType.JIRA:
                headers["Authorization"] = f"Basic {self.api_key}"
            elif self.itsm_type == ITSMType.PAGERDUTY:
                headers["Authorization"] = f"Token token={self.api_key}"
            elif self.itsm_type == ITSMType.OPSGENIE:
                headers["Authorization"] = f"GenieKey {self.api_key}"
            else:
                headers["Authorization"] = f"Bearer {self.api_key}"

        return headers

    async def create_incident(
        self,
        title: str,
        description: str,
        priority: str = "high",
        category: str = "sla_breach",
        original_incident_id: Optional[str] = None,
        issues: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Cria incidente no sistema ITSM.

        Args:
            title: Título do incidente
            description: Descrição detalhada
            priority: Prioridade (critical, high, medium, low)
            category: Categoria do incidente
            original_incident_id: ID do incidente original no Guard Agents
            issues: Lista de problemas detectados
            metadata: Metadados adicionais

        Returns:
            Dict com resultado da criação incluindo ticket_id
        """
        if not self.is_healthy():
            logger.warning(
                "itsm_client.not_available",
                action="create_incident"
            )
            return {
                "success": False,
                "error": "ITSM client not available",
                "simulated": True
            }

        with itsm_operation_duration.labels(operation="create_incident").time():
            try:
                # Construir payload baseado no tipo de ITSM
                payload = self._build_incident_payload(
                    title=title,
                    description=description,
                    priority=priority,
                    category=category,
                    original_incident_id=original_incident_id,
                    issues=issues,
                    metadata=metadata
                )

                # Determinar endpoint
                endpoint = self._get_incident_endpoint()

                # Enviar requisição
                response = await self._client.post(endpoint, json=payload)

                if response.status_code in (200, 201, 202):
                    result = response.json()
                    ticket_id = self._extract_ticket_id(result)

                    itsm_operations_total.labels(
                        operation="create_incident",
                        itsm_type=self.itsm_type.value,
                        status="success"
                    ).inc()

                    logger.info(
                        "itsm_client.incident_created",
                        ticket_id=ticket_id,
                        itsm_type=self.itsm_type.value,
                        priority=priority
                    )

                    return {
                        "success": True,
                        "ticket_id": ticket_id,
                        "itsm_type": self.itsm_type.value,
                        "priority": priority,
                        "response": result
                    }
                else:
                    itsm_operations_total.labels(
                        operation="create_incident",
                        itsm_type=self.itsm_type.value,
                        status="error"
                    ).inc()

                    logger.error(
                        "itsm_client.create_failed",
                        status_code=response.status_code,
                        response=response.text
                    )

                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}: {response.text}"
                    }

            except httpx.TimeoutException:
                itsm_operations_total.labels(
                    operation="create_incident",
                    itsm_type=self.itsm_type.value,
                    status="timeout"
                ).inc()

                logger.error("itsm_client.timeout")
                return {
                    "success": False,
                    "error": "Request timeout"
                }

            except Exception as e:
                itsm_operations_total.labels(
                    operation="create_incident",
                    itsm_type=self.itsm_type.value,
                    status="error"
                ).inc()

                logger.error(
                    "itsm_client.create_error",
                    error=str(e)
                )
                return {
                    "success": False,
                    "error": str(e)
                }

    def _build_incident_payload(
        self,
        title: str,
        description: str,
        priority: str,
        category: str,
        original_incident_id: Optional[str],
        issues: Optional[List[str]],
        metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Constrói payload baseado no tipo de ITSM"""

        # Descrição completa
        full_description = description
        if issues:
            full_description += "\n\nIssues detected:\n" + "\n".join(f"- {issue}" for issue in issues)
        if original_incident_id:
            full_description += f"\n\nOriginal Incident ID: {original_incident_id}"

        timestamp = datetime.now(timezone.utc).isoformat()

        if self.itsm_type == ITSMType.SERVICENOW:
            return {
                "short_description": title,
                "description": full_description,
                "urgency": self._map_priority_servicenow(priority),
                "impact": self._map_priority_servicenow(priority),
                "category": category,
                "u_source": "guard-agents",
                "u_correlation_id": original_incident_id
            }

        elif self.itsm_type == ITSMType.JIRA:
            return {
                "fields": {
                    "project": {"key": metadata.get("project_key", "OPS") if metadata else "OPS"},
                    "summary": title,
                    "description": full_description,
                    "issuetype": {"name": "Incident"},
                    "priority": {"name": self._map_priority_jira(priority)},
                    "labels": ["guard-agents", "sla-breach", category]
                }
            }

        elif self.itsm_type == ITSMType.PAGERDUTY:
            return {
                "routing_key": self.api_key,
                "event_action": "trigger",
                "dedup_key": original_incident_id,
                "payload": {
                    "summary": title,
                    "severity": self._map_priority_pagerduty(priority),
                    "source": "guard-agents",
                    "custom_details": {
                        "description": full_description,
                        "category": category,
                        "issues": issues or [],
                        "original_incident_id": original_incident_id
                    }
                }
            }

        elif self.itsm_type == ITSMType.OPSGENIE:
            return {
                "message": title,
                "description": full_description,
                "priority": self._map_priority_opsgenie(priority),
                "source": "guard-agents",
                "alias": original_incident_id,
                "tags": ["guard-agents", "sla-breach", category],
                "details": {
                    "original_incident_id": original_incident_id,
                    "category": category,
                    "issues": ", ".join(issues) if issues else ""
                }
            }

        else:
            # Generic webhook format
            return {
                "title": title,
                "description": full_description,
                "priority": priority,
                "category": category,
                "source": "guard-agents",
                "original_incident_id": original_incident_id,
                "issues": issues or [],
                "metadata": metadata or {},
                "timestamp": timestamp
            }

    def _get_incident_endpoint(self) -> str:
        """Retorna endpoint para criação de incidentes"""
        endpoints = {
            ITSMType.SERVICENOW: "/api/now/table/incident",
            ITSMType.JIRA: "/rest/api/3/issue",
            ITSMType.PAGERDUTY: "/v2/enqueue",
            ITSMType.OPSGENIE: "/v2/alerts",
            ITSMType.WEBHOOK: "/incidents"
        }
        return endpoints.get(self.itsm_type, "/incidents")

    def _extract_ticket_id(self, response: Dict[str, Any]) -> Optional[str]:
        """Extrai ID do ticket da resposta"""
        if self.itsm_type == ITSMType.SERVICENOW:
            return response.get("result", {}).get("sys_id")
        elif self.itsm_type == ITSMType.JIRA:
            return response.get("key")
        elif self.itsm_type == ITSMType.PAGERDUTY:
            return response.get("dedup_key")
        elif self.itsm_type == ITSMType.OPSGENIE:
            return response.get("requestId")
        else:
            return response.get("id") or response.get("ticket_id")

    def _map_priority_servicenow(self, priority: str) -> str:
        """Mapeia prioridade para ServiceNow (1-5)"""
        mapping = {
            "critical": "1",
            "high": "2",
            "medium": "3",
            "low": "4"
        }
        return mapping.get(priority.lower(), "2")

    def _map_priority_jira(self, priority: str) -> str:
        """Mapeia prioridade para Jira"""
        mapping = {
            "critical": "Highest",
            "high": "High",
            "medium": "Medium",
            "low": "Low"
        }
        return mapping.get(priority.lower(), "High")

    def _map_priority_pagerduty(self, priority: str) -> str:
        """Mapeia prioridade para PagerDuty"""
        mapping = {
            "critical": "critical",
            "high": "error",
            "medium": "warning",
            "low": "info"
        }
        return mapping.get(priority.lower(), "error")

    def _map_priority_opsgenie(self, priority: str) -> str:
        """Mapeia prioridade para OpsGenie"""
        mapping = {
            "critical": "P1",
            "high": "P2",
            "medium": "P3",
            "low": "P4"
        }
        return mapping.get(priority.lower(), "P2")

    async def update_incident(
        self,
        ticket_id: str,
        status: Optional[str] = None,
        notes: Optional[str] = None,
        resolution: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Atualiza status de um incidente.

        Args:
            ticket_id: ID do ticket ITSM
            status: Novo status
            notes: Notas adicionais
            resolution: Texto de resolução

        Returns:
            Dict com resultado da atualização
        """
        if not self.is_healthy():
            return {
                "success": False,
                "error": "ITSM client not available"
            }

        with itsm_operation_duration.labels(operation="update_incident").time():
            try:
                payload = {}

                if self.itsm_type == ITSMType.SERVICENOW:
                    if status:
                        payload["state"] = status
                    if notes:
                        payload["work_notes"] = notes
                    if resolution:
                        payload["close_notes"] = resolution

                    endpoint = f"/api/now/table/incident/{ticket_id}"
                    response = await self._client.patch(endpoint, json=payload)

                elif self.itsm_type == ITSMType.JIRA:
                    if status:
                        # Jira transition
                        payload = {"transition": {"id": status}}
                        endpoint = f"/rest/api/3/issue/{ticket_id}/transitions"
                        response = await self._client.post(endpoint, json=payload)
                    else:
                        response = httpx.Response(200)

                else:
                    # Generic update
                    payload = {
                        "status": status,
                        "notes": notes,
                        "resolution": resolution
                    }
                    endpoint = f"/incidents/{ticket_id}"
                    response = await self._client.patch(endpoint, json=payload)

                if response.status_code in (200, 201, 204):
                    itsm_operations_total.labels(
                        operation="update_incident",
                        itsm_type=self.itsm_type.value,
                        status="success"
                    ).inc()

                    return {
                        "success": True,
                        "ticket_id": ticket_id
                    }
                else:
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}"
                    }

            except Exception as e:
                itsm_operations_total.labels(
                    operation="update_incident",
                    itsm_type=self.itsm_type.value,
                    status="error"
                ).inc()

                return {
                    "success": False,
                    "error": str(e)
                }

    async def get_incident_status(
        self,
        ticket_id: str
    ) -> Dict[str, Any]:
        """
        Obtém status de um incidente.

        Args:
            ticket_id: ID do ticket ITSM

        Returns:
            Dict com status do incidente
        """
        if not self.is_healthy():
            return {
                "success": False,
                "error": "ITSM client not available"
            }

        try:
            if self.itsm_type == ITSMType.SERVICENOW:
                endpoint = f"/api/now/table/incident/{ticket_id}"
            elif self.itsm_type == ITSMType.JIRA:
                endpoint = f"/rest/api/3/issue/{ticket_id}"
            else:
                endpoint = f"/incidents/{ticket_id}"

            response = await self._client.get(endpoint)

            if response.status_code == 200:
                return {
                    "success": True,
                    "ticket_id": ticket_id,
                    "data": response.json()
                }
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}"
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
