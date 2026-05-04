# Neural Hive Approval Common

Unified approval models and decision logic for the Neural Hive Mind system.

## Overview

This library provides centralized approval models, decision logic, and Kafka integration to ensure consistency across all components of the Neural Hive Mind system that require approval workflows.

## Features

- **Unified Models** (R-A1): `UnifiedApprovalRequest`, `UnifiedApprovalDecision` with INV-3 compatibility
- **Decision Logic** (R-A2): Configurable thresholds for auto-approval/rejection
- **Kafka Integration** (R-A3): Producer for `plan_approvals_responses` topic with INV-4 compatibility
- **ML Predictor Interface** (R-A4): Interface for ML-powered approval decisions

## Installation

```bash
pip install neural-hive-approval-common
```

## Usage

### Basic Request and Decision

```python
from neural_hive_approval_common import (
    UnifiedApprovalRequest,
    UnifiedApprovalDecision,
    ApprovalDecisionLogic,
    RiskBand,
)

# Create an approval request
request = UnifiedApprovalRequest(
    plan_id="plan-123",
    intent_id="intent-456",
    original_intent_text="Create a new user account",
    risk_score=0.3,
    risk_band=RiskBand.LOW,
    cognitive_plan={"tasks": []},
)

# Evaluate with decision logic
logic = ApprovalDecisionLogic()
decision, reason, is_auto = await logic.evaluate(request)

if is_auto:
    print(f"Auto-decision: {decision} - {reason}")
else:
    print(f"Manual approval required: {reason}")

# Create decision
approval_decision = logic.create_decision(
    plan_id=request.plan_id,
    decision=decision,
    approved_by="user-123",
    rejection_reason=None if decision == "approved" else "Some reason",
)
```

### Kafka Integration

```python
from neural_hive_approval_common import (
    ApprovalKafkaProducer,
    ApprovalKafkaProducerSettings,
    ApprovalResponse,
)
from datetime import datetime, timezone

# Create producer
settings = ApprovalKafkaProducerSettings(
    bootstrap_servers="localhost:9092",
    approval_responses_topic="plan_approvals_responses",
)
producer = ApprovalKafkaProducer(settings)
await producer.initialize()

# Send response
response = ApprovalResponse(
    plan_id="plan-123",
    intent_id="intent-456",
    decision="approved",
    approved_by="user-123",
    approved_at=datetime.now(timezone.utc),
    cognitive_plan={"tasks": []},
)

await producer.send_approval_response(response)
```

### ML Predictor Integration

```python
from neural_hive_approval_common import MLPredictorInterface

class MyMLPredictor(MLPredictorInterface):
    def is_enabled(self) -> bool:
        return True

    async def predict_from_text(self, intent_text, specialist_confidence):
        # Call your ML model here
        return {
            "decision": "approve",
            "confidence": 0.92,
            "model_version": "v1.0.0",
        }

    async def get_auto_decision(self, intent_text, risk_band, specialist_confidence):
        prediction = await self.predict_from_text(intent_text, specialist_confidence)
        if prediction["confidence"] >= 0.8:
            return {
                "auto_decision": prediction["decision"],
                "confidence": prediction["confidence"],
                "reason": "ML prediction",
            }
        return None

# Use with decision logic
ml_predictor = MyMLPredictor()
decision, reason, is_auto = await logic.evaluate(request, ml_predictor=ml_predictor)
```

## Configuration

### Decision Thresholds

```python
from neural_hive_approval_common import ApprovalDecisionLogic, DecisionConfig

config = DecisionConfig(
    thresholds={
        "auto_approve_max_risk_low": 0.3,      # Auto-approve LOW risk <= 0.3
        "auto_approve_max_risk_medium": 0.2,   # Auto-approve MEDIUM risk <= 0.2
        "auto_approve_max_risk_high": 0.1,     # Auto-approve HIGH risk <= 0.1
        "ml_confidence_threshold": 0.8,        # ML confidence >= 0.8 for auto
        "require_manual_for_destructive": True,  # Destructive needs manual
        "enable_ml_auto_approval": True,        # Enable ML integration
    }
)
logic = ApprovalDecisionLogic(config)
```

## Invariants

This library maintains the following invariants:

- **INV-3**: Produces same `ApprovalDecision` format as existing approval-service
- **INV-4**: Kafka topic contracts remain compatible (`plan_approvals_responses`)
- **INV-6**: Approval request lifecycle (PENDING → APPROVED/REJECTED only)
- **INV-9**: Original intent text preservation through pipeline

## Testing

```bash
pytest
pytest --cov=neural_hive_approval_common
```

## License

Copyright Neural Hive Mind Team.
