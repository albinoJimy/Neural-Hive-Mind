"""Scout Signal data model based on Avro schema"""
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, field_validator
from neural_hive_domain import UnifiedDomain


class SignalType(str, Enum):
    """Type of signal detected"""
    ANOMALY_POSITIVE = "ANOMALY_POSITIVE"
    ANOMALY_NEGATIVE = "ANOMALY_NEGATIVE"
    PATTERN_EMERGING = "PATTERN_EMERGING"
    OPPORTUNITY = "OPPORTUNITY"
    THREAT = "THREAT"
    TREND = "TREND"


class ChannelType(str, Enum):
    """Channel type where signal was detected"""
    CORE = "CORE"
    EDGE = "EDGE"
    WEB = "WEB"
    MOBILE = "MOBILE"
    IOT = "IOT"
    API = "API"


class Geolocation(BaseModel):
    """Geographic location"""
    latitude: float
    longitude: float

    @field_validator('latitude')
    @classmethod
    def validate_latitude(cls, v):
        if not -90 <= v <= 90:
            raise ValueError('Latitude must be between -90 and 90')
        return v

    @field_validator('longitude')
    @classmethod
    def validate_longitude(cls, v):
        if not -180 <= v <= 180:
            raise ValueError('Longitude must be between -180 and 180')
        return v


class SignalSource(BaseModel):
    """Source information for the signal"""
    channel: ChannelType
    device_id: Optional[str] = None
    geolocation: Optional[Geolocation] = None


class ScoutSignal(BaseModel):
    """Scout Signal model matching Avro schema"""
    signal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version: str = Field(default="1.0.0")
    correlation_id: str
    trace_id: str
    span_id: str
    scout_agent_id: str
    signal_type: SignalType
    exploration_domain: UnifiedDomain
    source: SignalSource
    curiosity_score: float
    confidence: float
    relevance_score: float
    risk_score: float
    description: str
    raw_data: Dict[str, str]
    features: List[float]
    metadata: Dict[str, str] = Field(default_factory=dict)
    timestamp: int = Field(default_factory=lambda: int(datetime.utcnow().timestamp() * 1000))
    expires_at: int = Field(default_factory=lambda: int((datetime.utcnow() + timedelta(hours=24)).timestamp() * 1000))
    requires_validation: bool = False

    @field_validator('curiosity_score', 'confidence', 'relevance_score', 'risk_score')
    @classmethod
    def validate_score(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError('Scores must be between 0.0 and 1.0')
        return v

    @field_validator('timestamp', 'expires_at')
    @classmethod
    def validate_timestamp(cls, v):
        if v <= 0:
            raise ValueError('Timestamp must be positive')
        return v

    def to_avro_dict(self) -> Dict[str, Any]:
        """Convert to Avro-compatible dictionary"""
        data = self.model_dump()

        # Convert enums to strings
        data['signal_type'] = self.signal_type.value
        data['exploration_domain'] = self.exploration_domain.value
        data['source']['channel'] = self.source.channel.value

        # Handle optional geolocation
        if self.source.geolocation:
            data['source']['geolocation'] = {
                'latitude': self.source.geolocation.latitude,
                'longitude': self.source.geolocation.longitude
            }

        return data

    @classmethod
    def from_avro_dict(cls, data: Dict[str, Any]) -> 'ScoutSignal':
        """Create instance from Avro dictionary"""
        # Convert string enums back
        data['signal_type'] = SignalType(data['signal_type'])
        data['exploration_domain'] = UnifiedDomain(data['exploration_domain'])
        data['source']['channel'] = ChannelType(data['source']['channel'])

        # Handle optional geolocation
        if data['source'].get('geolocation'):
            data['source']['geolocation'] = Geolocation(**data['source']['geolocation'])

        data['source'] = SignalSource(**data['source'])

        return cls(**data)

    def calculate_priority(self) -> float:
        """Calculate signal priority based on scores"""
        weights = {
            'curiosity': 0.3,
            'confidence': 0.25,
            'relevance': 0.25,
            'risk': 0.2
        }

        priority = (
            self.curiosity_score * weights['curiosity'] +
            self.confidence * weights['confidence'] +
            self.relevance_score * weights['relevance'] +
            (1 - self.risk_score) * weights['risk']  # Lower risk = higher priority
        )

        return priority

    def should_publish(
        self,
        curiosity_threshold: float = 0.6,
        confidence_threshold: float = 0.7,
        relevance_threshold: float = 0.5,
        risk_threshold: float = 0.8
    ) -> bool:
        """Determine if signal should be published based on thresholds"""
        return (
            self.curiosity_score >= curiosity_threshold and
            self.confidence >= confidence_threshold and
            self.relevance_score >= relevance_threshold and
            self.risk_score <= risk_threshold
        )
