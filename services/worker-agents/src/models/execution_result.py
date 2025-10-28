from typing import Dict, Optional, Any
from pydantic import BaseModel
from .execution_ticket import TicketStatus
from datetime import datetime


class ExecutionResult(BaseModel):
    '''Modelo Pydantic para ExecutionResult (publicado no Kafka execution.results)'''

    ticket_id: str
    status: TicketStatus
    result: Dict[str, Any]
    error_message: Optional[str] = None
    actual_duration_ms: Optional[int] = None
    agent_id: str
    timestamp: int  # Unix millis
    schema_version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        '''Serializar para Kafka'''
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExecutionResult':
        '''Deserializar de dict'''
        return cls(**data)
