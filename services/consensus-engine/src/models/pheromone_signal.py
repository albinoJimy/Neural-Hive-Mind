import uuid
from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class PheromoneType(str, Enum):
    '''Tipo de feromônio digital'''
    SUCCESS = 'success'
    FAILURE = 'failure'
    WARNING = 'warning'


class PheromoneSignal(BaseModel):
    '''Sinalização de feromônio digital para coordenação de enxame'''
    signal_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description='ID do sinal')
    specialist_type: str = Field(..., description='Tipo do especialista')
    domain: str = Field(..., description='Domínio da avaliação')
    pheromone_type: PheromoneType = Field(..., description='Tipo de feromônio')

    # Força do feromônio
    strength: float = Field(..., ge=0.0, le=1.0, description='Força do feromônio')

    # Contexto
    plan_id: str = Field(..., description='ID do plano')
    intent_id: str = Field(..., description='ID da intenção')
    decision_id: Optional[str] = Field(default=None, description='ID da decisão')

    # Metadados
    created_at: datetime = Field(default_factory=datetime.utcnow, description='Data de criação')
    expires_at: datetime = Field(..., description='Expiração do feromônio')
    decay_rate: float = Field(default=0.1, description='Taxa de decay por hora', ge=0.0, le=1.0)

    metadata: Dict[str, Any] = Field(default_factory=dict, description='Metadados adicionais')

    def get_redis_key(self) -> str:
        '''Gera chave Redis para o feromônio'''
        return f'pheromone:{self.specialist_type}:{self.domain}:{self.pheromone_type.value}'

    def calculate_current_strength(self) -> float:
        '''Calcula força atual considerando decay temporal'''
        elapsed_hours = (datetime.utcnow() - self.created_at).total_seconds() / 3600
        decayed_strength = self.strength * ((1 - self.decay_rate) ** elapsed_hours)
        return max(0.0, decayed_strength)

    class Config:
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
