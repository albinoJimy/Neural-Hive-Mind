# Explainability API v3 - Hierarchical Explanation

**Version:** 3.0.0
**Status:** Production Ready
**Last Updated:** 2026-03-21

---

## Overview

Explainability API v3 provides hierarchical explanation capabilities for decision-making in the Neural-Hive-Mind system. It leverages the hierarchical consensus mechanism (GAPS-03) to explain how specialist seniority levels influence decisions.

### Key Features

- **Hierarchical Breakdown:** Statistics by seniority level (trainee to expert)
- **Individual Contributions:** Rank-ordered specialist influence scores
- **Counterfactual Analysis:** "What if" scenarios showing decision sensitivity
- **Temporal Tracking:** Seniority change history and trends
- **Batch Processing:** Compare multiple decisions at once
- **Quality Metrics:** Explanation confidence and completeness scores

---

## Quick Start

### Enable v3 API

Set the environment variable:

```bash
export ENABLE_V3_API=true
```

### Start the Service

```bash
cd services/explainability-api
uvicorn src.main:app --reload --port 8009
```

---

## API Endpoints

### Base URL

```
http://localhost:8009/api/v3
```

---

### 1. Full Explanation

Get complete hierarchical explanation for a decision.

**Endpoint:** `GET /api/v3/explainability/{decision_id}`

**Query Parameters:**
- `include_counterfactuals` (bool, optional): Include counterfactual analysis
- `include_temporal` (bool, optional): Include temporal analysis

**Example:**

```bash
curl -X GET "http://localhost:8009/api/v3/explainability/decision-123?include_counterfactuals=true&include_temporal=true"
```

**Response:**

```json
{
  "decision_id": "decision-123",
  "hierarchical_breakdown": {
    "by_level": {
      "expert": {"count": 3, "total_weight": 0.55, "avg_confidence": 0.92},
      "senior": {"count": 5, "total_weight": 0.30, "avg_confidence": 0.85},
      "mid_level": {"count": 4, "total_weight": 0.15, "avg_confidence": 0.78}
    },
    "dominant_level": "expert",
    "consensus_strength": 0.87
  },
  "individual_contributions": [
    {
      "specialist_id": "arch-specialist-001",
      "seniority_level": "expert",
      "domain": "architecture",
      "rank": 1,
      "contribution_score": 0.234,
      "weight": 0.30
    },
    {
      "specialist_id": "tech-specialist-002",
      "seniority_level": "senior",
      "domain": "technical",
      "rank": 2,
      "contribution_score": 0.189,
      "weight": 0.25
    }
  ],
  "counterfactuals": [
    {
      "scenario": "Remove top expert",
      "flipped_decision": false,
      "confidence_change": -0.15
    }
  ],
  "temporal_analysis": {
    "current_seniority": "expert",
    "history": [
      {
        "timestamp": "2026-03-20T10:00:00Z",
        "previous_level": "senior",
        "new_level": "expert",
        "reason": "performance_based"
      }
    ],
    "trend": "upward",
    "volatility": 0.1
  },
  "explanation_quality": {
    "confidence": 0.92,
    "completeness": 0.95,
    "stability": 0.88
  }
}
```

---

### 2. Hierarchical Breakdown Only

Get just the hierarchical statistics.

**Endpoint:** `GET /api/v3/explainability/{decision_id}/hierarchical`

**Example:**

```bash
curl -X GET "http://localhost:8009/api/v3/explainability/decision-123/hierarchical"
```

**Response:**

```json
{
  "decision_id": "decision-123",
  "hierarchical_breakdown": {
    "by_level": {
      "expert": {"count": 3, "total_weight": 0.55, "avg_confidence": 0.92},
      "senior": {"count": 5, "total_weight": 0.30, "avg_confidence": 0.85},
      "mid_level": {"count": 4, "total_weight": 0.15, "avg_confidence": 0.78}
    },
    "dominant_level": "expert",
    "consensus_strength": 0.87
  }
}
```

---

### 3. Individual Contributions Only

Get rank-ordered specialist contributions.

**Endpoint:** `GET /api/v3/explainability/{decision_id}/individual`

**Example:**

```bash
curl -X GET "http://localhost:8009/api/v3/explainability/decision-123/individual"
```

**Response:**

```json
{
  "decision_id": "decision-123",
  "individual_contributions": [
    {
      "specialist_id": "arch-specialist-001",
      "seniority_level": "expert",
      "domain": "architecture",
      "rank": 1,
      "contribution_score": 0.234,
      "weight": 0.30
    }
  ],
  "total_specialists": 12
}
```

---

### 4. Counterfactuals Only

Get "what if" scenarios.

**Endpoint:** `GET /api/v3/explainability/{decision_id}/counterfactuals`

**Example:**

```bash
curl -X GET "http://localhost:8009/api/v3/explainability/decision-123/counterfactuals"
```

**Response:**

```json
{
  "decision_id": "decision-123",
  "counterfactuals": [
    {
      "scenario": "Remove top expert",
      "flipped_decision": false,
      "confidence_change": -0.15,
      "affected_specialists": ["arch-specialist-001"]
    },
    {
      "scenario": "Remove all experts",
      "flipped_decision": true,
      "confidence_change": -0.45,
      "affected_specialists": ["arch-specialist-001", "expert-002", "expert-003"]
    }
  ],
  "sensitivity_score": 0.35
}
```

---

### 5. Temporal Analysis Only

Get seniority change history.

**Endpoint:** `GET /api/v3/explainability/{decision_id}/temporal`

**Example:**

```bash
curl -X GET "http://localhost:8009/api/v3/explainability/decision-123/temporal"
```

**Response:**

```json
{
  "decision_id": "decision-123",
  "temporal_analysis": {
    "current_seniority": "expert",
    "history": [
      {
        "timestamp": "2026-03-20T10:00:00Z",
        "previous_level": "senior",
        "new_level": "expert",
        "reason": "performance_based",
        "decision_context": {
          "approval_rate": 0.95,
          "consensus_participation": 0.98
        }
      }
    ],
    "trend": "upward",
    "volatility": 0.1
  }
}
```

---

### 6. Batch Explanation

Compare multiple decisions at once.

**Endpoint:** `POST /api/v3/explainability/batch`

**Request Body:**

```json
{
  "decision_ids": ["decision-123", "decision-456", "decision-789"],
  "include_counterfactuals": false,
  "include_temporal": false
}
```

**Example:**

```bash
curl -X POST "http://localhost:8009/api/v3/explainability/batch" \
  -H "Content-Type: application/json" \
  -d '{
    "decision_ids": ["decision-123", "decision-456"],
    "include_counterfactuals": true,
    "include_temporal": true
  }'
```

**Response:**

```json
{
  "explanations": [
    {
      "decision_id": "decision-123",
      "hierarchical_breakdown": {...},
      "individual_contributions": [...]
    },
    {
      "decision_id": "decision-456",
      "hierarchical_breakdown": {...},
      "individual_contributions": [...]
    }
  ],
  "failed_ids": [],
  "summary": {
    "total_requested": 2,
    "successful": 2,
    "failed": 0
  }
}
```

---

## Seniority Levels

| Level | Weight Range | Description |
|-------|--------------|-------------|
| `trainee` | 0.05 - 0.10 | Learning specialists |
| `junior` | 0.10 - 0.15 | Entry-level contributors |
| `mid_level` | 0.15 - 0.20 | Established specialists |
| `senior` | 0.20 - 0.30 | Experienced contributors |
| `expert` | 0.30 - 0.40 | Domain authorities |

---

## Metrics

### Consensus Strength

Measures agreement across seniority levels:
- `> 0.9`: Strong consensus
- `0.7 - 0.9`: Moderate consensus
- `< 0.7`: Weak consensus

### Sensitivity Score

Measures decision stability:
- `< 0.2`: Stable decision
- `0.2 - 0.5`: Moderately sensitive
- `> 0.5`: Highly sensitive

### Volatility

Measures seniority change frequency:
- `< 0.1`: Stable specialist
- `0.1 - 0.3`: Moderate change
- `> 0.3`: High volatility

---

## Python Client Example

```python
import httpx

async def get_explanation(decision_id: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"http://localhost:8009/api/v3/explainability/{decision_id}",
            params={"include_counterfactuals": True, "include_temporal": True}
        )
        return response.json()

# Usage
explanation = await get_explanation("decision-123")
print(f"Dominant level: {explanation['hierarchical_breakdown']['dominant_level']}")
print(f"Top contributor: {explanation['individual_contributions'][0]['specialist_id']}")
```

---

## Testing

Run the test suite:

```bash
cd services/explainability-api
pytest tests/ -v --cov=src --cov-report=term
```

Expected: 82 tests passing

---

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_V3_API` | `false` | Enable v3 endpoints |
| `MONGODB_URL` | - | MongoDB connection string |
| `KAFKA_BOOTSTRAP_SERVERS` | - | Kafka bootstrap servers |

---

## Related Documentation

- [GAPS-03: Consenso Hierárquico](../../../docs/specs/2026-03-17-hierarchical-consensus/)
- [GAPS-04: Explainability API](../../../docs/specs/2026-03-17-explainability-api/)
- [Feature Map](../../../docs/feature-map.md)
