"""
Modelos Pydantic para Intent Envelope baseados no schema JSON-LD
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from neural_hive_domain import UnifiedDomain


# Python 3.10 compatibility: StrEnum was added in 3.11
class StrEnum(str, Enum):
    """Compatibility shim for StrEnum (Python 3.11+)."""

    def __str__(self) -> str:
        return str(self.value)


class ActorType(StrEnum):
    """Tipos de ator que podem originar intenções"""

    HUMAN = "human"
    SYSTEM = "system"
    SERVICE = "service"
    BOT = "bot"


class Channel(StrEnum):
    """Canais de origem da intenção"""

    WEB = "web"
    MOBILE = "mobile"
    API = "api"
    VOICE = "voice"
    CHAT = "chat"


class Priority(StrEnum):
    """Níveis de prioridade"""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityLevel(StrEnum):
    """Níveis de segurança"""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class DeliveryMode(StrEnum):
    """Modos de entrega"""

    AT_MOST_ONCE = "at-most-once"
    AT_LEAST_ONCE = "at-least-once"
    EXACTLY_ONCE = "exactly-once"


class Durability(StrEnum):
    """Durabilidade da mensagem"""

    TRANSIENT = "transient"
    PERSISTENT = "persistent"


class Consistency(StrEnum):
    """Níveis de consistência"""

    EVENTUAL = "eventual"
    STRONG = "strong"


class Entity(BaseModel):
    """Entidade extraída do texto"""

    type: str = Field(..., description="Tipo da entidade")
    value: str = Field(..., description="Valor da entidade")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confiança da extração")
    start: int | None = Field(None, description="Posição inicial no texto")
    end: int | None = Field(None, description="Posição final no texto")


class Geolocation(BaseModel):
    """Localização geográfica"""

    country: str | None = Field(None, description="Código do país")
    region: str | None = Field(None, description="Estado/região")
    city: str | None = Field(None, description="Cidade")
    timezone: str | None = Field(None, description="Fuso horário")


class Actor(BaseModel):
    """Ator que originou a intenção"""

    id: str = Field(..., description="Identificador único do ator")
    actor_type: ActorType = Field(..., description="Tipo do ator")
    name: str | None = Field(None, description="Nome do ator")


class Intent(BaseModel):
    """Detalhes da intenção"""

    text: str = Field(..., min_length=1, max_length=10000, description="Texto da intenção")
    domain: UnifiedDomain = Field(..., description="Domínio da intenção")
    classification: str | None = Field(None, description="Classificação específica")
    original_language: str | None = Field(None, description="Idioma original (ISO 639-1)")
    processed_text: str | None = Field(None, description="Texto processado")
    entities: list[Entity] = Field(default_factory=list, description="Entidades extraídas")
    keywords: list[str] = Field(default_factory=list, description="Palavras-chave")

    @field_validator("domain", mode="before")
    @classmethod
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

    session_id: str | None = Field(None, description="ID da sessão")
    user_id: str | None = Field(None, description="ID do usuário")
    tenant_id: str | None = Field(None, description="ID do tenant")
    channel: Channel | None = Field(None, description="Canal de origem")
    user_agent: str | None = Field(None, description="User-Agent")
    client_ip: str | None = Field(None, description="IP do cliente (anonimizado)")
    geolocation: Geolocation | None = Field(None, description="Localização")


class Constraint(BaseModel):
    """Restrições e requisitos"""

    priority: Priority = Field(default=Priority.NORMAL, description="Prioridade")
    deadline: datetime | None = Field(None, description="Prazo limite")
    max_retries: int = Field(default=3, ge=0, le=10, description="Máximo de tentativas")
    timeout_ms: int | None = Field(None, gt=0, description="Timeout em millisegundos")
    required_capabilities: list[str] = Field(
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
    durability: Durability = Field(default=Durability.PERSISTENT, description="Durabilidade")
    consistency: Consistency = Field(default=Consistency.STRONG, description="Consistência")


class IntentEnvelope(BaseModel):
    """Envelope principal para intenções"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="ID único da intenção")
    version: str = Field(default="1.0.0", description="Versão do schema")
    correlation_id: str | None = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="ID de correlação - gerado automaticamente se não fornecido",
    )
    trace_id: str | None = Field(None, description="ID de trace OpenTelemetry")
    span_id: str | None = Field(None, description="ID de span OpenTelemetry")

    actor: Actor = Field(..., description="Ator que originou a intenção")
    intent: Intent = Field(..., description="Detalhes da intenção")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Score de confiança")
    confidence_status: str | None = Field(
        None, description="Status de confiança: high, medium, ou low"
    )

    context: Context | None = Field(None, description="Contexto da intenção")
    constraints: Constraint | None = Field(None, description="Restrições")
    qos: QualityOfService | None = Field(None, description="QoS")

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Timestamp de criação"
    )

    @field_validator("id")
    @classmethod
    def validate_uuid(cls, v):
        """Validar formato UUID"""
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError("ID deve ser um UUID válido")
        return v

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v):
        """Validar score de confiança"""
        if not 0.0 <= v <= 1.0:
            raise ValueError("Confidence deve estar entre 0.0 e 1.0")
        return v

    @model_validator(mode="after")
    def validate_constraints_consistency(self) -> "IntentEnvelope":
        """Validar consistência entre constraints e QoS"""
        constraints = self.constraints
        qos = self.qos

        if constraints and constraints.security_level == SecurityLevel.RESTRICTED:
            if not qos or qos.consistency != Consistency.STRONG:
                raise ValueError("Nível de segurança RESTRICTED requer consistência STRONG")

        return self

    def to_avro_dict(self) -> dict[str, Any]:
        """Converter para formato compatível com Avro"""

        def convert_enum(value):
            return value.value.upper() if isinstance(value, Enum) else value

        return {
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
            "context": (
                {
                    "sessionId": self.context.session_id if self.context else None,
                    "userId": self.context.user_id if self.context else None,
                    "tenantId": self.context.tenant_id if self.context else None,
                    "channel": (
                        convert_enum(self.context.channel)
                        if self.context and self.context.channel
                        else None
                    ),
                    "userAgent": self.context.user_agent if self.context else None,
                    "clientIp": self.context.client_ip if self.context else None,
                    "geolocation": (
                        {
                            "country": self.context.geolocation.country,
                            "region": self.context.geolocation.region,
                            "city": self.context.geolocation.city,
                            "timezone": self.context.geolocation.timezone,
                        }
                        if self.context and self.context.geolocation
                        else None
                    ),
                }
                if self.context
                else None
            ),
            "constraints": (
                {
                    "priority": convert_enum(self.constraints.priority),
                    "deadline": (
                        int(self.constraints.deadline.timestamp() * 1000)
                        if self.constraints.deadline
                        else None
                    ),
                    "maxRetries": self.constraints.max_retries,
                    "timeoutMs": self.constraints.timeout_ms,
                    "requiredCapabilities": self.constraints.required_capabilities,
                    "securityLevel": convert_enum(self.constraints.security_level),
                }
                if self.constraints
                else None
            ),
            "qos": (
                {
                    "deliveryMode": convert_enum(self.qos.delivery_mode),
                    "durability": convert_enum(self.qos.durability),
                    "consistency": convert_enum(self.qos.consistency),
                }
                if self.qos
                else None
            ),
            "timestamp": int(self.timestamp.timestamp() * 1000),
            "schemaVersion": 1,
            "metadata": {},
        }

    def get_partition_key(self) -> str:
        """Gerar chave de partição baseada no domínio"""
        return self.intent.domain.value

    def get_idempotency_key(self) -> str:
        """Gerar chave de idempotência para exactly-once"""
        return f"{self.actor.id}:{self.correlation_id or self.id}:{int(self.timestamp.timestamp())}"

    def to_cache_dict(self) -> dict[str, Any]:
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
                "text": (
                    self.intent.text[:500] if len(self.intent.text) > 500 else self.intent.text
                ),  # Truncar texto longo
                "domain": self.intent.domain.value,
                "classification": self.intent.classification,
                "original_language": self.intent.original_language,
            },
            "confidence": self.confidence,
            "confidence_status": self.confidence_status,
            "timestamp": self.timestamp.isoformat(),
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }

    model_config = ConfigDict(use_enum_values=True, validate_assignment=True)


# Modelos para requests da API


class IntentRequest(BaseModel):
    """Request para processar intenção de texto.

    Attributes:
        text: Texto da intenção (1-10000 caracteres, sanitizado contra injeção)
        language: Idioma do texto (ISO 639-1, ex: pt-BR, en-US)
        correlation_id: ID de correlação opcional para rastreamento distribuído
        constraints: Restrições de processamento (prioridade, timeout, etc)
        qos: Requisitos de Quality of Service

    Raises:
        ValueError: Se text estiver vazio, contiver padrões de injeção,
                    language for inválido, ou correlation_id não for UUID válido
    """

    text: str = Field(..., min_length=1, max_length=10000, description="Texto da intenção")
    language: str = Field(default="pt-BR", description="Idioma do texto (ISO 639-1)")
    correlation_id: str | None = Field(None, description="ID de correlação (UUID válido)")
    constraints: Constraint | None = Field(None, description="Restrições de processamento")
    qos: QualityOfService | None = Field(None, description="Requisitos de QoS")

    @field_validator("text")
    @classmethod
    def sanitize_text_input(cls, v: str) -> str:
        """Sanitiza input de texto contra injeção maliciosa."""
        if not v or not v.strip():
            raise ValueError("Texto da intenção não pode ser vazio ou apenas whitespace")

        # Remover null bytes e caracteres de controle perigosos
        dangerous_chars = ["\x00", "\r", "\x1b"]
        for char in dangerous_chars:
            if char in v:
                v = v.replace(char, "")

        # Verificar por padrões de injeção comuns
        v_lower = v.lower()
        injection_patterns = [
            "<script",
            "javascript:",
            "onerror=",
            "onload=",
            "eval(",
            "exec(",
            "system(",
            "__import__",
            "${",
            "#{",
            "@{",  # Template injection patterns
        ]
        for pattern in injection_patterns:
            if pattern in v_lower:
                raise ValueError(f"Texto contém padrão potencialmente perigoso: {pattern}")

        return v.strip()

    @field_validator("language")
    @classmethod
    def validate_language_code(cls, v: str) -> str:
        """Valida código de idioma no formato ISO 639-1."""
        valid_languages = {
            "pt-BR",
            "pt-PT",
            "pt",
            "en-US",
            "en-GB",
            "en",
            "es-ES",
            "es",
            "fr-FR",
            "fr",
            "de-DE",
            "de",
            "it-IT",
            "it",
            "nl-NL",
            "nl",
            "pl-PL",
            "pl",
        }
        if v not in valid_languages:
            raise ValueError(
                f"Idioma '{v}' não é suportado. Use formato ISO 639-1 (ex: pt-BR, en-US)"
            )
        return v

    @field_validator("correlation_id")
    @classmethod
    def validate_correlation_id(cls, v: str | None) -> str | None:
        """Valida que correlation_id é um UUID válido quando fornecido."""
        if v is None:
            return None
        try:
            uuid.UUID(v)
            return v
        except ValueError:
            raise ValueError(f"correlation_id deve ser um UUID válido, recebido: {v[:20]}...")


class VoiceIntentRequest(BaseModel):
    """Request para processar intenção de voz.

    Attributes:
        language: Idioma esperado no áudio (ISO 639-1, ex: pt-BR, en-US)
        correlation_id: ID de correlação opcional para rastreamento distribuído
        constraints: Restrições de processamento (prioridade, timeout, etc)
        qos: Requisitos de Quality of Service

    Raises:
        ValueError: Se language for inválido ou correlation_id não for UUID válido
    """

    language: str = Field(default="pt-BR", description="Idioma esperado no áudio (ISO 639-1)")
    correlation_id: str | None = Field(None, description="ID de correlação (UUID válido)")
    constraints: Constraint | None = Field(None, description="Restrições de processamento")
    qos: QualityOfService | None = Field(None, description="Requisitos de QoS")

    @field_validator("language")
    @classmethod
    def validate_language_code(cls, v: str) -> str:
        """Valida código de idioma no formato ISO 639-1."""
        valid_languages = {
            "pt-BR",
            "pt-PT",
            "pt",
            "en-US",
            "en-GB",
            "en",
            "es-ES",
            "es",
            "fr-FR",
            "fr",
            "de-DE",
            "de",
            "it-IT",
            "it",
            "nl-NL",
            "nl",
            "pl-PL",
            "pl",
        }
        if v not in valid_languages:
            raise ValueError(
                f"Idioma '{v}' não é suportado. Use formato ISO 639-1 (ex: pt-BR, en-US)"
            )
        return v

    @field_validator("correlation_id")
    @classmethod
    def validate_correlation_id(cls, v: str | None) -> str | None:
        """Valida que correlation_id é um UUID válido quando fornecido."""
        if v is None:
            return None
        try:
            uuid.UUID(v)
            return v
        except ValueError:
            raise ValueError(f"correlation_id deve ser um UUID válido, recebido: {v[:20]}...")


# Modelos para resultados de pipeline


class ASRResult(BaseModel):
    """Resultado do pipeline ASR (Automatic Speech Recognition).

    Attributes:
        text: Texto transcrito do áudio
        confidence: Confiança da transcrição (0.0 a 1.0)
        language: Idioma detectado no áudio
        duration: Duração do áudio em segundos
    """

    text: str = Field(..., description="Texto transcrito")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confiança da transcrição")
    language: str = Field(..., description="Idioma detectado")
    duration: float = Field(..., description="Duração do áudio em segundos")


class NLUResult(BaseModel):
    """Resultado do pipeline NLU (Natural Language Understanding).

    Attributes:
        processed_text: Texto processado e normalizado
        domain: Domínio classificado da intenção
        classification: Classificação específica dentro do domínio
        confidence: Confiança da classificação (0.0 a 1.0)
        entities: Lista de entidades extraídas do texto
        keywords: Lista de palavras-chave extraídas
        requires_manual_validation: Indica se requer validação humana
        confidence_status: Status de confiança (high, medium, low)
        adaptive_threshold: Threshold adaptativo calculado pelo NLU
    """

    processed_text: str = Field(..., description="Texto processado")
    domain: UnifiedDomain = Field(..., description="Domínio classificado")
    classification: str = Field(..., description="Classificação específica")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confiança da classificação")
    entities: list[Entity] = Field(default_factory=list, description="Entidades extraídas")
    keywords: list[str] = Field(default_factory=list, description="Palavras-chave")
    requires_manual_validation: bool = Field(default=False, description="Requer validação manual")
    confidence_status: str = Field(
        default="medium", description="Status de confiança: high, medium, ou low"
    )
    adaptive_threshold: float | None = Field(
        None, description="Threshold adaptativo calculado pelo NLU"
    )

    @field_validator("domain", mode="before")
    @classmethod
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
