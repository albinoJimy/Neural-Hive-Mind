from typing import Any

from pydantic import BaseModel

from .execution_ticket import TicketStatus


class ExecutionResult(BaseModel):
    """Modelo Pydantic para ExecutionResult (publicado no Kafka execution.results)"""

    ticket_id: str
    status: TicketStatus
    result: dict[str, Any]
    error_message: str | None = None
    actual_duration_ms: int | None = None
    agent_id: str
    timestamp: int  # Unix millis
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Serializar para Kafka"""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionResult":
        """Deserializar de dict"""
        return cls(**data)
