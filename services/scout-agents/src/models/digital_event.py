"""Modelo para eventos de canais digitais."""
from datetime import datetime
from typing import Optional, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class DigitalChannel(str, Enum):
    """Canais digitais de onde os eventos podem se originar."""
    WEB = "web"
    MOBILE_APP = "mobile_app"
    API = "api"
    EMAIL = "email"
    CHAT = "chat"
    SOCIAL = "social"


class DigitalEventType(str, Enum):
    """Tipos de eventos digitais suportados."""
    PAGE_VIEW = "page_view"
    CLICK = "click"
    SUBMIT = "submit"
    SEARCH = "search"
    TRANSACTION = "transaction"
    ERROR = "error"
    CUSTOM = "custom"


class DigitalEvent(BaseModel):
    """
    Modelo representando um evento de canal digital.

    Eventos digitais são gerados por interações em canais como web,
    mobile app, API, email, chat e redes sociais.
    """
    event_id: str = Field(..., description="Unique event ID")
    event_type: DigitalEventType = Field(..., description="Type of digital event")
    channel: DigitalChannel = Field(..., description="Digital channel source")
    user_id: Optional[str] = Field(None, description="User identifier")
    session_id: Optional[str] = Field(None, description="Session identifier")
    timestamp: Union[datetime, str] = Field(default_factory=lambda: datetime.utcnow(), description="Event timestamp")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Event payload data")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Event metadata")

    @field_validator('timestamp', mode='before')
    @classmethod
    def parse_timestamp(cls, v):
        """Parse timestamp from string or datetime."""
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace('Z', '+00:00'))
            except ValueError:
                return datetime.utcnow()
        return v

    @field_validator('event_type', mode='before')
    @classmethod
    def parse_event_type(cls, v):
        """Parse event type from string."""
        if isinstance(v, str):
            try:
                return DigitalEventType(v)
            except ValueError:
                return DigitalEventType.CUSTOM
        return v

    @field_validator('channel', mode='before')
    @classmethod
    def parse_channel(cls, v):
        """Parse channel from string."""
        if isinstance(v, str):
            try:
                return DigitalChannel(v)
            except ValueError:
                return DigitalChannel.API
        return v

    class Config:
        """Configuração do Pydantic."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        use_enum_values = True

    def to_raw_event(self) -> Dict[str, Any]:
        """
        Converte o evento digital para formato RawEvent compatível.

        Returns:
            Dicionário com dados do evento no formato esperado pelo ExplorationEngine
        """
        event_type_str = self.event_type.value if isinstance(self.event_type, DigitalEventType) else str(self.event_type)
        channel_str = self.channel.value if isinstance(self.channel, DigitalChannel) else str(self.channel)

        return {
            "event_id": self.event_id,
            "event_type": f"digital_{event_type_str}",
            "source": f"digital_{channel_str}",
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
            "metadata": {
                **self.metadata,
                "digital_channel": channel_str,
                "digital_event_type": event_type_str,
                "user_id": self.user_id,
                "session_id": self.session_id
            }
        }

    def calculate_priority(self) -> float:
        """
        Calcula prioridade do evento baseado em suas características.

        Returns:
            Score de prioridade entre 0.0 e 1.0
        """
        priority = 0.5

        # Get string value for comparison
        event_type_str = self.event_type.value if isinstance(self.event_type, DigitalEventType) else str(self.event_type)

        # Eventos de erro têm prioridade mais alta
        if event_type_str == "error":
            priority += 0.3

        # Transações têm prioridade alta
        if event_type_str == "transaction":
            priority += 0.2

        # Eventos com user_id têm maior relevância
        if self.user_id:
            priority += 0.1

        # Eventos com session_id têm maior relevância
        if self.session_id:
            priority += 0.05

        return min(1.0, priority)

    def is_valid(self) -> bool:
        """
        Valida se o evento tem todos os campos obrigatórios.

        Returns:
            True se válido, False caso contrário
        """
        if not self.event_id:
            return False

        # Check if event_type is valid enum value (string or enum)
        try:
            valid_type = DigitalEventType(self.event_type)
        except ValueError:
            return False

        # Check if channel is valid enum value (string or enum)
        try:
            valid_channel = DigitalChannel(self.channel)
        except ValueError:
            return False

        if not self.timestamp:
            return False

        return True
