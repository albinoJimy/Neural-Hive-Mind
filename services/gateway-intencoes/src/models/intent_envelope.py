"""
Modelos Pydantic para Intent Envelope baseados no schema JSON-LD
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from enum import Enum
import uuid

from pydantic import BaseModel, Field, validator, root_validator
from pydantic.types import UUID4
from neural_hive_domain import UnifiedDomain


class ActorType(str, Enum):
    """Tipos de ator que podem originar intenções"""

    HUMAN = "human"
    SYSTEM = "system"
    SERVICE = "service"
    BOT = "bot"


class Channel(str, Enum):
    """Canais de origem da intenção"""

    WEB = "web"
    MOBILE = "mobile"
    API = "api"
    VOICE = "voice"
    CHAT = "chat"


class Priority(str, Enum):
    """Níveis de prioridade"""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityLevel(str, Enum):
    """Níveis de segurança"""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class DeliveryMode(str, Enum):
    """Modos de entrega"""

    AT_MOST_ONCE = "at-most-once"
    AT_LEAST_ONCE = "at-least-once"
    EXACTLY_ONCE = "exactly-once"


class Durability(str, Enum):
    """Durabilidade da mensagem"""

    TRANSIENT = "transient"
    PERSISTENT = "persistent"


class Consistency(str, Enum):
    """Níveis de consistência"""

    EVENTUAL = "eventual"
    STRONG = "strong"


class Entity(BaseModel):
    """Entidade extraída do texto"""

    type: str = Field(..., description="Tipo da entidade")
    value: str = Field(..., description="Valor da entidade")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confiança da extração")
    start: Optional[int] = Field(None, description="Posição inicial no texto")
    end: Optional[int] = Field(None, description="Posição final no texto")


class Geolocation(BaseModel):
    """Localização geográfica"""

    country: Optional[str] = Field(None, description="Código do país")
    region: Optional[str] = Field(None, description="Estado/região")
    city: Optional[str] = Field(None, description="Cidade")
    timezone: Optional[str] = Field(None, description="Fuso horário")


class Actor(BaseModel):
    """Ator que originou a intenção"""

    id: str = Field(..., description="Identificador único do ator")
    actor_type: ActorType = Field(..., description="Tipo do ator")
    name: Optional[str] = Field(None, description="Nome do ator")


class Intent(BaseModel):
    """Detalhes da intenção"""

    text: str = Field(
        ..., min_length=1, max_length=10000, description="Texto da intenção"
    )
    domain: UnifiedDomain = Field(..., description="Domínio da intenção")
    classification: Optional[str] = Field(None, description="Classificação específica")
    original_language: Optional[str] = Field(
        None, description="Idioma original (ISO 639-1)"
    )
    processed_text: Optional[str] = Field(None, description="Texto processado")
    entities: List[Entity] = Field(
        default_factory=list, description="Entidades extraídas"
    )
    keywords: List[str] = Field(default_factory=list, description="Palavras-chave")

    @validator("domain", pre=True)
    def coerce_domain_to_unified(cls, v):
        """Coerce incoming strings to UnifiedDomain"""
        if isinstance(v, UnifiedDomain):
            return v
        if isinstance(v, str):
            try:
                return UnifiedDomain[v.upper()]
            except KeyError:
                raise ValueError(
                    f"Invalid domain '{v}'. Valid domains: {[d.name for d in UnifiedDomain]}"
                )
        return v


class Context(BaseModel):
    """Contexto da intenção"""

    session_id: Optional[str] = Field(None, description="ID da sessão")
    user_id: Optional[str] = Field(None, description="ID do usuário")
    tenant_id: Optional[str] = Field(None, description="ID do tenant")
    channel: Optional[Channel] = Field(None, description="Canal de origem")
    user_agent: Optional[str] = Field(None, description="User-Agent")
    client_ip: Optional[str] = Field(None, description="IP do cliente (anonimizado)")
    geolocation: Optional[Geolocation] = Field(None, description="Localização")


class Constraint(BaseModel):
    """Restrições e requisitos"""

    priority: Priority = Field(default=Priority.NORMAL, description="Prioridade")
    deadline: Optional[datetime] = Field(None, description="Prazo limite")
    max_retries: int = Field(default=3, ge=0, le=10, description="Máximo de tentativas")
    timeout_ms: Optional[int] = Field(
        None, gt=0, description="Timeout em millisegundos"
    )
    required_capabilities: List[str] = Field(
        default_factory=list, description="Capacidades necessárias"
    )
    security_level: SecurityLevel = Field(
        default=SecurityLevel.INTERNAL, description="Nível de segurança"
    )


class QualityOfService(BaseModel):
    """Garantias de QoS"""

    delivery_mode: DeliveryMode = Field(
        default=DeliveryMode.EXACTLY_ONCE, description="Modo de entrega"
    )
    durability: Durability = Field(
        default=Durability.PERSISTENT, description="Durabilidade"
    )
    consistency: Consistency = Field(
        default=Consistency.STRONG, description="Consistência"
    )


class IntentEnvelope(BaseModel):
    """Envelope principal para intenções"""

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="ID único da intenção"
    )
    version: str = Field(default="1.0.0", description="Versão do schema")
    correlation_id: Optional[str] = Field(None, description="ID de correlação")
    trace_id: Optional[str] = Field(None, description="ID de trace OpenTelemetry")
    span_id: Optional[str] = Field(None, description="ID de span OpenTelemetry")

    actor: Actor = Field(..., description="Ator que originou a intenção")
    intent: Intent = Field(..., description="Detalhes da intenção")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Score de confiança")
    confidence_status: Optional[str] = Field(
        None, description="Status de confiança: high, medium, ou low"
    )

    context: Optional[Context] = Field(None, description="Contexto da intenção")
    constraints: Optional[Constraint] = Field(None, description="Restrições")
    qos: Optional[QualityOfService] = Field(None, description="QoS")

    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp de criação"
    )

    @validator("id")
    def validate_uuid(cls, v):
        """Validar formato UUID"""
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError("ID deve ser um UUID válido")
        return v

    @validator("confidence")
    def validate_confidence(cls, v):
        """Validar score de confiança"""
        if not 0.0 <= v <= 1.0:
            raise ValueError("Confidence deve estar entre 0.0 e 1.0")
        return v

    @root_validator(skip_on_failure=True)
    def validate_constraints_consistency(cls, values):
        """Validar consistência entre constraints e QoS"""
        constraints = values.get("constraints")
        qos = values.get("qos")

        if constraints and constraints.security_level == SecurityLevel.RESTRICTED:
            if not qos or qos.consistency != Consistency.STRONG:
                raise ValueError(
                    "Nível de segurança RESTRICTED requer consistência STRONG"
                )

        return values

    def to_avro_dict(self) -> Dict[str, Any]:
        """Converter para formato compatível com Avro"""

        def convert_enum(value):
            return value.value.upper() if isinstance(value, Enum) else value

        avro_data = {
            "id": self.id,
            "version": self.version,
            "correlationId": self.correlation_id,
            "traceId": self.trace_id,
            "spanId": self.span_id,
            "actor": {
                "id": self.actor.id,
                "actorType": convert_enum(self.actor.actor_type),
                "name": self.actor.name,
            },
            "intent": {
                "text": self.intent.text,
                "domain": convert_enum(self.intent.domain),
                "classification": self.intent.classification,
                "originalLanguage": self.intent.original_language,
                "processedText": self.intent.processed_text,
                "entities": [
                    {
                        "entityType": entity.type,
                        "value": entity.value,
                        "confidence": entity.confidence,
                        "start": entity.start,
                        "end": entity.end,
                    }
                    for entity in self.intent.entities
                ],
                "keywords": self.intent.keywords,
            },
            "confidence": self.confidence,
            "context": {
                "sessionId": self.context.session_id if self.context else None,
                "userId": self.context.user_id if self.context else None,
                "tenantId": self.context.tenant_id if self.context else None,
                "channel": convert_enum(self.context.channel)
                if self.context and self.context.channel
                else None,
                "userAgent": self.context.user_agent if self.context else None,
                "clientIp": self.context.client_ip if self.context else None,
                "geolocation": {
                    "country": self.context.geolocation.country,
                    "region": self.context.geolocation.region,
                    "city": self.context.geolocation.city,
                    "timezone": self.context.geolocation.timezone,
                }
                if self.context and self.context.geolocation
                else None,
            }
            if self.context
            else None,
            "constraints": {
                "priority": convert_enum(self.constraints.priority),
                "deadline": int(self.constraints.deadline.timestamp() * 1000)
                if self.constraints.deadline
                else None,
                "maxRetries": self.constraints.max_retries,
                "timeoutMs": self.constraints.timeout_ms,
                "requiredCapabilities": self.constraints.required_capabilities,
                "securityLevel": convert_enum(self.constraints.security_level),
            }
            if self.constraints
            else None,
            "qos": {
                "deliveryMode": convert_enum(self.qos.delivery_mode),
                "durability": convert_enum(self.qos.durability),
                "consistency": convert_enum(self.qos.consistency),
            }
            if self.qos
            else None,
            "timestamp": int(self.timestamp.timestamp() * 1000),
            "schemaVersion": 1,
            "metadata": {},
        }

        return avro_data

    def get_partition_key(self) -> str:
        """Gerar chave de partição baseada no domínio"""
        return self.intent.domain.value

    def get_idempotency_key(self) -> str:
        """Gerar chave de idempotência para exactly-once"""
        return f"{self.actor.id}:{self.correlation_id or self.id}:{int(self.timestamp.timestamp())}"

    def to_cache_dict(self) -> Dict[str, Any]:
        """Converter para formato de cache Redis (versão compacta)"""
        return {
            "id": self.id,
            "correlation_id": self.correlation_id,
            "actor": {
                "id": self.actor.id,
                "actor_type": self.actor.actor_type.value,
                "name": self.actor.name,
            },
            "intent": {
                "text": self.intent.text[:500]
                if len(self.intent.text) > 500
                else self.intent.text,  # Truncar texto longo
                "domain": self.intent.domain.value,
                "classification": self.intent.classification,
                "original_language": self.intent.original_language,
            },
            "confidence": self.confidence,
            "confidence_status": self.confidence_status,
            "timestamp": self.timestamp.isoformat(),
            "cached_at": datetime.utcnow().isoformat(),
        }

    class Config:
        use_enum_values = True
        validate_assignment = True


# Modelos para requests da API


class IntentRequest(BaseModel):
    """Request para processar intenção de texto"""

    text: str = Field(
        ..., min_length=1, max_length=10000, description="Texto da intenção"
    )
    language: str = Field(default="pt-BR", description="Idioma do texto")
    correlation_id: Optional[str] = Field(None, description="ID de correlação")
    constraints: Optional[Constraint] = Field(
        None, description="Restrições de processamento"
    )
    qos: Optional[QualityOfService] = Field(None, description="Requisitos de QoS")


class VoiceIntentRequest(BaseModel):
    """Request para processar intenção de voz"""

    language: str = Field(default="pt-BR", description="Idioma esperado no áudio")
    correlation_id: Optional[str] = Field(None, description="ID de correlação")
    constraints: Optional[Constraint] = Field(
        None, description="Restrições de processamento"
    )
    qos: Optional[QualityOfService] = Field(None, description="Requisitos de QoS")


# Modelos para resultados de pipeline


class ASRResult(BaseModel):
    """Resultado do pipeline ASR"""

    text: str = Field(..., description="Texto transcrito")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confiança da transcrição"
    )
    language: str = Field(..., description="Idioma detectado")
    duration: float = Field(..., description="Duração do áudio em segundos")


class NLUResult(BaseModel):
    """Resultado do pipeline NLU"""

    processed_text: str = Field(..., description="Texto processado")
    domain: UnifiedDomain = Field(..., description="Domínio classificado")
    classification: str = Field(..., description="Classificação específica")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confiança da classificação"
    )
    entities: List[Entity] = Field(
        default_factory=list, description="Entidades extraídas"
    )
    keywords: List[str] = Field(default_factory=list, description="Palavras-chave")
    requires_manual_validation: bool = Field(
        default=False, description="Requer validação manual"
    )
    confidence_status: str = Field(
        default="medium", description="Status de confiança: high, medium, ou low"
    )
    adaptive_threshold: Optional[float] = Field(
        None, description="Threshold adaptativo calculado pelo NLU"
    )

    @validator("domain", pre=True)
    def coerce_domain_to_unified(cls, v):
        """Coerce incoming strings to UnifiedDomain"""
        if isinstance(v, UnifiedDomain):
            return v
        if isinstance(v, str):
            try:
                return UnifiedDomain[v.upper()]
            except KeyError:
                raise ValueError(
                    f"Invalid domain '{v}'. Valid domains: {[d.name for d in UnifiedDomain]}"
                )
        return v
