"""
Modelo Pydantic para eventos de webhook.
"""
import time
from typing import Optional, Literal
from pydantic import BaseModel, Field, HttpUrl

from . import ExecutionTicket


class WebhookEvent(BaseModel):
    """Evento de webhook para notificar Worker Agents."""

    event_id: str = Field(..., description='UUID do evento')
    event_type: Literal['ticket.created', 'ticket.updated', 'ticket.completed', 'ticket.failed'] = Field(
        ...,
        description='Tipo de evento'
    )
    ticket_id: str = Field(..., description='ID do ticket')
    ticket: ExecutionTicket = Field(..., description='Payload completo do ticket')
    timestamp: int = Field(..., description='Timestamp Unix (millis)')
    webhook_url: HttpUrl = Field(..., description='URL do Worker Agent')
    retry_count: int = Field(default=0, description='Contador de tentativas')
    max_retries: int = Field(default=3, description='Máximo de retries')
    next_retry_at: Optional[int] = Field(default=None, description='Timestamp do próximo retry')
    status: Literal['pending', 'sent', 'failed', 'expired'] = Field(
        default='pending',
        description='Status do webhook'
    )
    response_status_code: Optional[int] = Field(default=None, description='HTTP status code da resposta')
    response_body: Optional[str] = Field(default=None, description='Corpo da resposta')
    error_message: Optional[str] = Field(default=None, description='Mensagem de erro')

    def should_retry(self) -> bool:
        """
        Verifica se deve fazer retry do webhook.

        Returns:
            True se deve retry, False caso contrário
        """
        return self.retry_count < self.max_retries and self.status in ['pending', 'failed']

    def calculate_next_retry(self) -> int:
        """
        Calcula timestamp do próximo retry com backoff exponencial.

        Returns:
            Timestamp Unix (millis) do próximo retry
        """
        # Backoff exponencial: 2^retry_count * 2 segundos
        backoff_seconds = (2 ** self.retry_count) * 2
        current_time_ms = int(time.time() * 1000)
        return current_time_ms + (backoff_seconds * 1000)

    def to_http_payload(self) -> dict:
        """
        Converte para payload HTTP POST.

        Returns:
            Dicionário com dados para envio HTTP
        """
        return {
            'event_id': self.event_id,
            'event_type': self.event_type,
            'ticket_id': self.ticket_id,
            'ticket': self.ticket.model_dump(),
            'timestamp': self.timestamp
        }

    class Config:
        use_enum_values = True
        json_encoders = {
            HttpUrl: lambda v: str(v)
        }
