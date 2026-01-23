# Neural Hive Domain

Unified domain definitions for the Neural Hive Mind system.

## Purpose

This library provides centralized domain definitions and mapping utilities to ensure consistency across all components of the Neural Hive Mind system, including:

- Intent Envelope processing
- Scout Agent signals
- Risk scoring calculations
- Pheromone trail management
- Specialist routing

## Installation

```bash
pip install -e libraries/python/neural_hive_domain
```

Or add to your requirements:

```
-e ../libraries/python/neural_hive_domain
```

## Usage

### UnifiedDomain Enum

The `UnifiedDomain` enum provides the canonical list of all domains in the system:

```python
from neural_hive_domain import UnifiedDomain

# Use domain values directly
domain = UnifiedDomain.SECURITY

# Serialize to string
print(str(domain))  # "SECURITY"

# Use in Pydantic models
from pydantic import BaseModel

class MyModel(BaseModel):
    domain: UnifiedDomain

model = MyModel(domain="SECURITY")
print(model.domain)  # UnifiedDomain.SECURITY
```

### DomainMapper

The `DomainMapper` class provides utilities for normalizing domains and generating Redis keys:

#### Normalizing Domains

```python
from neural_hive_domain import DomainMapper, UnifiedDomain

# Normalize from Intent Envelope
domain = DomainMapper.normalize('business', 'intent_envelope')
assert domain == UnifiedDomain.BUSINESS

# Normalize from Scout Signal
domain = DomainMapper.normalize('BEHAVIOR', 'scout_signal')
assert domain == UnifiedDomain.BEHAVIOR

# Normalize from Risk Scoring
domain = DomainMapper.normalize('operational', 'risk_scoring')
assert domain == UnifiedDomain.OPERATIONAL

# Normalize from Ontology
domain = DomainMapper.normalize('security-analysis', 'ontology')
assert domain == UnifiedDomain.SECURITY
```

#### Generating Redis Pheromone Keys

```python
from neural_hive_domain import DomainMapper, UnifiedDomain

# Basic key without ID
key = DomainMapper.to_pheromone_key(
    domain=UnifiedDomain.BUSINESS,
    layer='strategic',
    pheromone_type='SUCCESS',
)
# Result: "pheromone:strategic:BUSINESS:SUCCESS"

# Key with ID
key = DomainMapper.to_pheromone_key(
    domain=UnifiedDomain.BEHAVIOR,
    layer='exploration',
    pheromone_type='ANOMALY_POSITIVE',
    id='uuid-123',
)
# Result: "pheromone:exploration:BEHAVIOR:ANOMALY_POSITIVE:uuid-123"
```

#### Mapping from Ontology

```python
from neural_hive_domain import DomainMapper, UnifiedDomain

# Map ontology domain names to UnifiedDomain
domain = DomainMapper.from_ontology('security-analysis')
assert domain == UnifiedDomain.SECURITY

domain = DomainMapper.from_ontology('architecture-review')
assert domain == UnifiedDomain.TECHNICAL
```

## Domain Reference

### Unified Domains

| Domain | Description |
|--------|-------------|
| `BUSINESS` | Business logic, requirements, and process analysis |
| `TECHNICAL` | Code quality, architecture, and technical implementation |
| `SECURITY` | Security vulnerabilities, authentication, and authorization |
| `INFRASTRUCTURE` | Deployment, scaling, and infrastructure concerns |
| `BEHAVIOR` | Runtime behavior patterns and anomaly detection |
| `OPERATIONAL` | Performance optimization and operational efficiency |
| `COMPLIANCE` | Regulatory compliance and policy adherence |

### Domain Mapping Table

| Source | Original Value | UnifiedDomain |
|--------|---------------|---------------|
| Intent Envelope | `business` | `BUSINESS` |
| Intent Envelope | `technical` | `TECHNICAL` |
| Intent Envelope | `security` | `SECURITY` |
| Intent Envelope | `infrastructure` | `INFRASTRUCTURE` |
| Scout Signal | `BEHAVIOR` | `BEHAVIOR` |
| Risk Scoring | `operational` | `OPERATIONAL` |
| Risk Scoring | `compliance` | `COMPLIANCE` |
| Ontology | `security-analysis` | `SECURITY` |
| Ontology | `architecture-review` | `TECHNICAL` |
| Ontology | `performance-optimization` | `OPERATIONAL` |
| Ontology | `code-quality` | `TECHNICAL` |
| Ontology | `code-review` | `TECHNICAL` |
| Ontology | `dependency-analysis` | `SECURITY` |
| Ontology | `infrastructure-review` | `INFRASTRUCTURE` |
| Ontology | `compliance-check` | `COMPLIANCE` |
| Ontology | `business-analysis` | `BUSINESS` |
| Ontology | `behavior-analysis` | `BEHAVIOR` |

## Redis Pheromone Key Format

```
pheromone:{layer}:{domain}:{type}:{id?}
```

### Components

- **layer**: `strategic`, `exploration`, `consensus`, or `specialist`
- **domain**: One of the `UnifiedDomain` values (uppercase)
- **type**: Pheromone type (`SUCCESS`, `FAILURE`, `WARNING`, `ANOMALY_POSITIVE`, `ANOMALY_NEGATIVE`, `CONFIDENCE`, `RISK`)
- **id**: Optional unique identifier

### Examples

```
pheromone:strategic:BUSINESS:SUCCESS
pheromone:exploration:BEHAVIOR:ANOMALY_POSITIVE:uuid-123
pheromone:consensus:SECURITY:WARNING
pheromone:specialist:TECHNICAL:SUCCESS:plan-456
```

## Valid Sources

The following sources are valid for `DomainMapper.normalize()`:

- `intent_envelope` - Domain from Intent Envelope messages
- `scout_signal` - Domain from Scout Agent signals
- `risk_scoring` - Domain from Risk Scoring calculations
- `ontology` - Domain from intents taxonomy ontology

## Valid Pheromone Layers

- `strategic` - Strategic-level decisions
- `exploration` - Exploration and discovery
- `consensus` - Consensus building
- `specialist` - Specialist-specific trails

## Valid Pheromone Types

- `SUCCESS` - Successful operation
- `FAILURE` - Failed operation
- `WARNING` - Warning condition
- `ANOMALY_POSITIVE` - Positive anomaly detected
- `ANOMALY_NEGATIVE` - Negative anomaly detected
- `CONFIDENCE` - Confidence signal
- `RISK` - Risk signal

## Running Tests

```bash
cd libraries/python/neural_hive_domain
pytest tests/ -v --cov=. --cov-report=term-missing
```

## Dependencies

- Python >= 3.11
- pydantic >= 2.5.2
- structlog >= 23.2.0
