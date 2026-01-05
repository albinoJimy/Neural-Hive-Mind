from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AgentType(str, Enum):
    """Tipos de agentes no Neural Hive-Mind"""
    WORKER = "WORKER"
    SCOUT = "SCOUT"
    GUARD = "GUARD"
    ANALYST = "ANALYST"

    @classmethod
    def from_proto_value(cls, value) -> "AgentType":
        """
        Converte valor protobuf (int ou string) para AgentType enum.

        Protobuf enums são transmitidos como inteiros:
        - 0: AGENT_TYPE_UNSPECIFIED (inválido)
        - 1: WORKER
        - 2: SCOUT
        - 3: GUARD
        - 4: ANALYST

        Args:
            value: Pode ser int (1, 2, 3, 4), string ("WORKER", "SCOUT", "GUARD", "ANALYST"),
                   ou já um AgentType enum

        Returns:
            AgentType enum correspondente

        Raises:
            ValueError: Se o valor não puder ser mapeado para um AgentType válido
        """
        # Se já é AgentType, retorna diretamente
        if isinstance(value, cls):
            return value

        # Mapeamento de int protobuf para enum
        proto_int_map = {
            1: cls.WORKER,
            2: cls.SCOUT,
            3: cls.GUARD,
            4: cls.ANALYST,
        }

        # Se é inteiro, usar mapeamento direto
        if isinstance(value, int):
            if value in proto_int_map:
                return proto_int_map[value]
            raise ValueError(
                f"Invalid AgentType int value: {value}. "
                f"Expected 1 (WORKER), 2 (SCOUT), 3 (GUARD), or 4 (ANALYST)"
            )

        # Se é string, tentar converter para enum
        if isinstance(value, str):
            value_upper = value.upper()
            try:
                return cls(value_upper)
            except ValueError:
                raise ValueError(
                    f"Invalid AgentType string value: '{value}'. "
                    f"Expected 'WORKER', 'SCOUT', 'GUARD', or 'ANALYST'"
                )

        raise ValueError(
            f"Cannot convert {type(value).__name__} to AgentType. "
            f"Expected int, str, or AgentType"
        )


class AgentStatus(str, Enum):
    """Status de saúde do agente"""
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    DEGRADED = "DEGRADED"


class AgentTelemetry(BaseModel):
    """Telemetria do agente"""
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_duration_ms: int = Field(default=0, ge=0)
    total_executions: int = Field(default=0, ge=0)
    failed_executions: int = Field(default=0, ge=0)
    last_execution_at: Optional[int] = Field(default=None)

    def calculate_score(self) -> float:
        """Calcula score de telemetria normalizado [0.0-1.0]"""
        if self.total_executions == 0:
            return 0.5  # Score neutro para agentes novos
        return self.success_rate


class AgentInfo(BaseModel):
    """Informações completas do agente"""
    agent_id: UUID = Field(default_factory=uuid4)
    agent_type: AgentType
    capabilities: List[str] = Field(default_factory=list)
    metadata: Dict[str, str] = Field(default_factory=dict)
    telemetry: AgentTelemetry = Field(default_factory=AgentTelemetry)
    status: AgentStatus = Field(default=AgentStatus.HEALTHY)
    namespace: str = Field(default="default")
    cluster: str = Field(default="local")
    version: str = Field(default="1.0.0")
    registered_at: int = Field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp()))
    last_seen: int = Field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp()))
    schema_version: int = Field(default=1)

    def to_proto_dict(self) -> Dict:
        """Converte para dicionário compatível com protobuf"""
        return {
            "agent_id": str(self.agent_id),
            "agent_type": self.agent_type.value,
            "capabilities": self.capabilities,
            "metadata": self.metadata,
            "telemetry": {
                "success_rate": self.telemetry.success_rate,
                "avg_duration_ms": self.telemetry.avg_duration_ms,
                "total_executions": self.telemetry.total_executions,
                "failed_executions": self.telemetry.failed_executions,
                "last_execution_at": self.telemetry.last_execution_at or 0,
            },
            "status": self.status.value,
            "registered_at": self.registered_at,
            "last_seen": self.last_seen,
            "namespace": self.namespace,
            "cluster": self.cluster,
            "version": self.version,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_proto_dict(cls, data: Dict) -> "AgentInfo":
        """Cria instância a partir de dicionário protobuf"""
        telemetry_data = data.get("telemetry", {})
        return cls(
            agent_id=UUID(data["agent_id"]),
            agent_type=AgentType.from_proto_value(data["agent_type"]),
            capabilities=data.get("capabilities", []),
            metadata=data.get("metadata", {}),
            telemetry=AgentTelemetry(
                success_rate=telemetry_data.get("success_rate", 0.0),
                avg_duration_ms=telemetry_data.get("avg_duration_ms", 0),
                total_executions=telemetry_data.get("total_executions", 0),
                failed_executions=telemetry_data.get("failed_executions", 0),
                last_execution_at=telemetry_data.get("last_execution_at"),
            ),
            status=AgentStatus(data.get("status", "HEALTHY")),
            namespace=data.get("namespace", "default"),
            cluster=data.get("cluster", "local"),
            version=data.get("version", "1.0.0"),
            registered_at=data.get("registered_at", int(datetime.now(timezone.utc).timestamp())),
            last_seen=data.get("last_seen", int(datetime.now(timezone.utc).timestamp())),
            schema_version=data.get("schema_version", 1),
        )

    def calculate_health_score(self) -> float:
        """Calcula score de saúde [0.0-1.0]"""
        if self.status == AgentStatus.HEALTHY:
            return 1.0
        elif self.status == AgentStatus.DEGRADED:
            return 0.5
        else:  # UNHEALTHY
            return 0.0

    def is_expired(self, timeout_seconds: int) -> bool:
        """Verifica se o agente está expirado"""
        current_time = int(datetime.now(timezone.utc).timestamp())
        return (current_time - self.last_seen) > timeout_seconds

    def get_etcd_key(self, prefix: str = "/neural-hive/agents") -> str:
        """Retorna a chave etcd para este agente"""
        return f"{prefix}/{self.agent_type.value.lower()}/{str(self.agent_id)}"
