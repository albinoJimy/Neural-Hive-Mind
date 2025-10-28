"""Raw Event data model for incoming events"""
from datetime import datetime
from typing import Dict, Any, List
from pydantic import BaseModel, Field
import numpy as np


class RawEvent(BaseModel):
    """Raw event from external sources (Kafka, MQTT, etc.)"""
    event_id: str
    event_type: str = Field(description="Type: log, metric, trace, user_action, system_event")
    source: str = Field(description="Event source identifier")
    timestamp: datetime
    payload: Dict[str, Any] = Field(description="Raw event data")
    metadata: Dict[str, str] = Field(default_factory=dict)

    def extract_features(self) -> List[float]:
        """Extract numerical features from payload for analysis"""
        features = []

        def extract_numeric(obj: Any, depth: int = 0, max_depth: int = 3):
            """Recursively extract numeric values"""
            if depth > max_depth:
                return

            if isinstance(obj, (int, float)):
                features.append(float(obj))
            elif isinstance(obj, dict):
                for value in obj.values():
                    extract_numeric(value, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    extract_numeric(item, depth + 1)

        extract_numeric(self.payload)

        # If no numeric features found, create default feature vector
        if not features:
            features = [0.0] * 10

        # Pad or truncate to fixed size (e.g., 50 features)
        target_size = 50
        if len(features) < target_size:
            features.extend([0.0] * (target_size - len(features)))
        else:
            features = features[:target_size]

        return features

    def normalize(self) -> Dict[str, Any]:
        """Normalize event data to standard format"""
        return {
            'event_id': self.event_id,
            'event_type': self.event_type,
            'source': self.source,
            'timestamp': self.timestamp.isoformat(),
            'payload': self.payload,
            'metadata': self.metadata
        }

    def is_valid(self) -> bool:
        """Validate that event has required fields"""
        required_fields = ['event_id', 'event_type', 'source', 'timestamp', 'payload']
        for field in required_fields:
            if not getattr(self, field, None):
                return False
        return True

    def calculate_anomaly_score(self, historical_mean: float = 0.0, historical_std: float = 1.0) -> float:
        """
        Calculate simple anomaly score using z-score
        Returns normalized score between 0 and 1
        """
        features = self.extract_features()
        if not features:
            return 0.0

        # Calculate mean of current features
        current_mean = np.mean(features)

        # Calculate z-score
        if historical_std > 0:
            z_score = abs((current_mean - historical_mean) / historical_std)
        else:
            z_score = 0.0

        # Normalize to 0-1 range using sigmoid
        anomaly_score = 1 / (1 + np.exp(-z_score))

        return float(anomaly_score)
