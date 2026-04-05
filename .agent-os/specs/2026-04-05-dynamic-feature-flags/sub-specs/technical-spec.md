# Technical Specification

Esta é a especificação técnica para a feature Dynamic Feature Flags detalhada em @.agent-os/specs/2026-04-05-dynamic-feature-flags/spec.md

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Feature Flags Flow                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Admin UI ──┐                                                               │
│             │                                                               │
│  REST API ──┼──► FeatureFlagService ──┐                                     │
│             │                         │                                     │
│  Grafana ───┘                         │                                     │
│                                         ▼                                     │
│                              ┌─────────────────┐                            │
│                              │ FeatureFlagRepo │                            │
│                              │   (MongoDB)     │                            │
│                              └────────┬────────┘                            │
│                                       │                                     │
│                                       │ cache write                         │
│                                       ▼                                     │
│                              ┌─────────────────┐                            │
│                              │ FlagCacheManager│                            │
│                              │    (Redis)      │                            │
│                              └────────┬────────┘                            │
│                                       │                                     │
│                                       │ data.external.http                  │
│                                       ▼                                     │
│  Orchestrator ───────────────► OPA ──────────────────────────────► Decision │
│  (input context)              (feature_flags.rego)        (enable/disable)   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Specifications

### 1. Domain Models

```python
# services/feature-flag-service/src/models/feature_flag.py

from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime

class RolloutStrategy(str, Enum):
    """Estratégias de rollout disponíveis."""
    ALL = "all"              # 100% dos usuários
    PERCENTAGE = "percentage"  # X% dos usuários (hash-based)
    WHITELIST = "whitelist"    # Apenas lista permitida
    CANARY = "canary"          # Baseado em host/header
    GRADUAL = "gradual"        # Rampa ao longo do tempo

class ConditionOperator(str, Enum):
    """Operadores para condições."""
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    REGEX_MATCH = "regex_match"

class Condition(BaseModel):
    """Condição para avaliação de flag."""
    field: str = Field(..., description="Campo a avaliar (ex: namespace, tenant_id)")
    operator: ConditionOperator = Field(default=ConditionOperator.EQUALS)
    value: Any = Field(..., description="Valor esperado")

class FeatureFlag(BaseModel):
    """Modelo de Feature Flag."""
    id: str = Field(default_factory=lambda: f"flag_{uuid4().hex[:8]}")
    name: str = Field(..., min_length=1, max_length=100, unique=True)
    description: Optional[str] = Field(None, max_length=500)
    enabled: bool = Field(default=False)

    # Rollout configuration
    rollout_strategy: RolloutStrategy = Field(default=RolloutStrategy.ALL)
    rollout_percentage: Optional[int] = Field(None, ge=0, le=100)
    conditions: list[Condition] = Field(default_factory=list)

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = Field(..., description="User/service que criou")
    owner: Optional[str] = Field(None, description="Time responsável")
    tags: list[str] = Field(default_factory=list)

    # Lifecycle
    expires_at: Optional[datetime] = Field(None, description="Auto-disable após data")
    archived: bool = Field(default=False)

    class Config:
        json_schema_extra = {
            "example": {
                "name": "enable_intelligent_scheduler",
                "description": "Habilita scheduler inteligente baseado em ML",
                "enabled": True,
                "rollout_strategy": "percentage",
                "rollout_percentage": 50,
                "conditions": [
                    {"field": "risk_band", "operator": "in", "value": ["critical", "high"]}
                ],
                "created_by": "platform-team",
                "owner": "orchestrator-team",
                "tags": ["scheduling", "ml", "performance"]
            }
        }
```

### 2. Redis Cache Schema

```python
# services/feature-flag-service/src/services/cache_manager.py

import json
from datetime import timedelta
from typing import Optional
from redis.asyncio import Redis
from .models import FeatureFlag

class FlagCacheManager:
    """Gerenciador de cache para feature flags em Redis."""

    FLAG_KEY_PREFIX = "feature_flag:"
    DEFAULT_TTL = timedelta(seconds=60)
    ALL_FLAGS_KEY = "feature_flags:all"

    def __init__(self, redis: Redis):
        self.redis = redis

    def make_key(self, flag_name: str) -> str:
        """Cria chave Redis para flag."""
        return f"{self.FLAG_KEY_PREFIX}{flag_name}"

    async def get_flag(self, flag_name: str) -> Optional[dict]:
        """Obtém flag do cache."""
        key = self.make_key(flag_name)
        data = await self.redis.get(key)
        return json.loads(data) if data else None

    async def set_flag(self, flag: FeatureFlag, ttl: timedelta = None) -> None:
        """Salva flag no cache."""
        key = self.make_key(flag.name)
        ttl = ttl or self.DEFAULT_TTL
        await self.redis.setex(
            key,
            int(ttl.total_seconds()),
            flag.model_dump_json()
        )

    async def invalidate_flag(self, flag_name: str) -> None:
        """Invalida flag do cache."""
        key = self.make_key(flag_name)
        await self.redis.delete(key)

    async def warm_cache(self, flags: list[FeatureFlag]) -> None:
        """Popula cache com todas as flags."""
        pipeline = self.redis.pipeline()
        for flag in flags:
            key = self.make_key(flag.name)
            pipeline.setex(
                key,
                int(self.DEFAULT_TTL.total_seconds()),
                flag.model_dump_json()
            )
        await pipeline.execute()

    async def get_all_flags_cached(self) -> Optional[dict]:
        """Obtém todas as flags do cache (usado por OPA)."""
        data = await self.redis.get(self.ALL_FLAGS_KEY)
        return json.loads(data) if data else None

    async def set_all_flags(self, flags: dict) -> None:
        """Salva snapshot de todas as flags."""
        await self.redis.setex(
            self.ALL_FLAGS_KEY,
            int(self.DEFAULT_TTL.total_seconds()),
            json.dumps(flags)
        )
```

### 3. Rollout Strategy Engine

```python
# services/feature-flag-service/src/services/rollout_engine.py

import hashlib
from typing import Optional
from .models import FeatureFlag, RolloutStrategy, Condition, ConditionOperator

class RolloutEngine:
    """Motor de avaliação de estratégias de rollout."""

    @staticmethod
    def hash_value(value: str, seed: str = "") -> float:
        """Gera hash determinístico (0-1)."""
        combined = f"{seed}:{value}"
        hash_hex = hashlib.sha256(combined.encode()).hexdigest()
        return int(hash_hex[:8], 16) / 2**32

    def evaluate_conditions(
        self,
        conditions: list[Condition],
        context: dict
    ) -> bool:
        """Avalia todas as condições AND lógico."""
        if not conditions:
            return True

        for condition in conditions:
            field_value = context.get(condition.field)
            if not self._evaluate_condition(condition, field_value):
                return False
        return True

    def _evaluate_condition(
        self,
        condition: Condition,
        field_value: Any
    ) -> bool:
        """Avalia uma condição individual."""
        if condition.operator == ConditionOperator.EQUALS:
            return field_value == condition.value
        elif condition.operator == ConditionOperator.NOT_EQUALS:
            return field_value != condition.value
        elif condition.operator == ConditionOperator.IN:
            return field_value in condition.value
        elif condition.operator == ConditionOperator.NOT_IN:
            return field_value not in condition.value
        elif condition.operator == ConditionOperator.CONTAINS:
            return condition.value in str(field_value)
        elif condition.operator == ConditionOperator.REGEX_MATCH:
            import re
            return bool(re.match(condition.value, str(field_value)))
        return False

    def evaluate_rollout(
        self,
        flag: FeatureFlag,
        context: dict
    ) -> bool:
        """Avalia se flag está ativa para o contexto."""
        if not flag.enabled:
            return False

        # Verifica condições primeiro
        if not self.evaluate_conditions(flag.conditions, context):
            return False

        # Aplica estratégia de rollout
        if flag.rollout_strategy == RolloutStrategy.ALL:
            return True

        elif flag.rollout_strategy == RolloutStrategy.PERCENTAGE:
            if flag.rollout_percentage is None:
                return True
            # Hash-based deterministic usando tenant_id ou request_id
            key = context.get("tenant_id") or context.get("request_id", "unknown")
            hash_val = self.hash_value(key, flag.name)
            return hash_val * 100 < flag.rollout_percentage

        elif flag.rollout_strategy == RolloutStrategy.WHITELIST:
            # Condições já validadas acima
            return True

        elif flag.rollout_strategy == RolloutStrategy.CANARY:
            host = context.get("host", "")
            return host.endswith("-canary") or "canary" in host

        elif flag.rollout_strategy == RolloutStrategy.GRADUAL:
            # Time-based ramp up
            from datetime import datetime
            now = datetime.utcnow()
            if flag.created_at:
                elapsed = (now - flag.created_at).total_seconds()
                # Ramp up over 24 hours
                ramp_percentage = min(100, int(elapsed / 864))  # 86400s = 24h
                key = context.get("tenant_id") or "unknown"
                hash_val = self.hash_value(key, flag.name)
                return hash_val * 100 < ramp_percentage

        return False
```

### 4. OPA Integration

```rego
# policies/rego/orchestrator/feature_flags_dynamic.rego

package neuralhive.orchestrator.feature_flags_dynamic

import data.external.flags

# Obter flags do Redis via data.external
flags_from_cache := flags.get_all()

# Avaliar flag específica
default is_enabled := false

is_enabled {
    flag_name := input.flag_name
    all_flags := flags_from_cache
    flag := all_flags[flag_name]

    # Flag está globalmente habilitada
    flag.enabled == true

    # Avaliar condições
    eval_conditions(flag.conditions, input.context)

    # Avaliar estratégia de rollout
    eval_rollout_strategy(flag, input.context)
}

# Avaliar lista de condições
eval_conditions(conditions, context) {
    not conditions
}

eval_conditions(conditions, context) {
    count(conditions) > 0
    all_conditions_match(conditions, context)
}

all_conditions_match(conditions, context) {
    foreach condition in conditions {
        match_condition(condition, context[condition.field])
    }
}

match_condition(condition, value) {
    condition.operator == "equals"
    value == condition.value
}

match_condition(condition, value) {
    condition.operator == "in"
    condition.value[value]
}

# Avaliar estratégia de rollout
eval_rollout_strategy(flag, context) {
    flag.rollout_strategy == "all"
}

eval_rollout_strategy(flag, context) {
    flag.rollout_strategy == "percentage"
    hash := hash_value(context.tenant_id, flag.name)
    hash * 100 < flag.rollout_percentage
}

# Função de hash determinística (mesma lógica do Python)
hash_value(value, seed) := hash {
    h := sha256(concat(seed, ":", value))
    hash := to_number(substr(h, 0, 8), 16) / 4294967296
}
```

### 5. REST API Endpoints

```python
# services/feature-flag-service/src/api/routes/feature_flags.py

from fastapi import APIRouter, HTTPException, status
from typing import list
from ..models import FeatureFlag, FeatureFlagCreate, FeatureFlagUpdate
from ..services import FeatureFlagService

router = APIRouter(prefix="/api/v1/feature-flags", tags=["Feature Flags"])

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_flag(payload: FeatureFlagCreate) -> FeatureFlag:
    """Cria nova feature flag."""
    return await feature_flag_service.create_flag(payload)

@router.get("", response_model=list[FeatureFlag])
async def list_flags(
    enabled: Optional[bool] = None,
    owner: Optional[str] = None,
    tag: Optional[str] = None,
    archived: bool = False
) -> list[FeatureFlag]:
    """Lista flags com filtros opcionais."""
    return await feature_flag_service.list_filters(
        enabled=enabled, owner=owner, tag=tag, archived=archived
    )

@router.get("/{flag_id}", response_model=FeatureFlag)
async def get_flag(flag_id: str) -> FeatureFlag:
    """Obtém flag por ID ou nome."""
    return await feature_flag_service.get_flag(flag_id)

@router.put("/{flag_id}", response_model=FeatureFlag)
async def update_flag(flag_id: str, payload: FeatureFlagUpdate) -> FeatureFlag:
    """Atualiza flag existente (invalida cache)."""
    return await feature_flag_service.update_flag(flag_id, payload)

@router.delete("/{flag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_flag(flag_id: str) -> None:
    """Remove flag (limpa cache e MongoDB)."""
    await feature_flag_service.delete_flag(flag_id)

@router.post("/{flag_id}/toggle", response_model=FeatureFlag)
async def toggle_flag(flag_id: str) -> FeatureFlag:
    """Ativa/desativa flag rapidamente."""
    return await feature_flag_service.toggle_flag(flag_id)

@router.post("/evaluate", response_model=dict[str, bool])
async def evaluate_flags(
    flag_names: list[str],
    context: dict
) -> dict[str, bool]:
    """Avalia múltiplas flags para um contexto."""
    return await feature_flag_service.evaluate_batch(flag_names, context)

@router.post("/batch", response_model=list[FeatureFlag])
async def batch_update(updates: list[FeatureFlagUpdate]) -> list[FeatureFlag]:
    """Atualiza múltiplas flags em uma transação."""
    return await feature_flag_service.batch_update(updates)
```

### 6. Metrics Specification

```python
# services/feature-flag-service/src/observability/metrics.py

from prometheus_client import Counter, Gauge, Histogram

class FeatureFlagMetrics:
    """Métricas Prometheus para Feature Flags."""

    # Toggle count (por flag e ação)
    flag_toggles = Counter(
        "feature_flag_toggles_total",
        "Total de toggle operations",
        ["flag_name", "action", "user"]
    )

    # Evaluation latency
    evaluation_latency = Histogram(
        "feature_flag_evaluation_seconds",
        "Latência de avaliação de flag",
        ["flag_name"],
        buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
    )

    # Cache hit/miss ratio
    cache_hits = Counter(
        "feature_flag_cache_hits_total",
        "Total de cache hits",
        ["flag_name"]
    )

    cache_misses = Counter(
        "feature_flag_cache_misses_total",
        "Total de cache misses",
        ["flag_name"]
    )

    # Flags ativas por status
    active_flags = Gauge(
        "feature_flags_active",
        "Número de flags ativas",
        ["rollout_strategy", "owner"]
    )

    # Evaluation result
    evaluation_result = Counter(
        "feature_flag_evaluations_total",
        "Total de avaliações de flag",
        ["flag_name", "result"]  # result: enabled/disabled
    )

    # Rollout percentage
    rollout_percentage = Gauge(
        "feature_flag_rollout_percentage",
        "Percentual de rollout configurado",
        ["flag_name"]
    )
```

## Deployment Configuration

### Kubernetes ConfigMap

```yaml
# helm/feature-flag-service/templates/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: feature-flag-service-config
data:
  REDIS_CLUSTER_NODES: "redis-cluster.redis.svc.cluster.local:6379"
  REDIS_PASSWORD: ""
  REDIS_SSL_ENABLED: "false"
  REDIS_CACHE_TTL_SECONDS: "60"
  MONGODB_URI: "mongodb://mongodb:27017"
  MONGODB_DATABASE: "feature_flags"
  OPA_URL: "http://opa.opa.svc.cluster.local:8181"
  LOG_LEVEL: "INFO"
```

### Environment Variables

```bash
# .env.example
FEATURE_FLAG_SERVICE_PORT=8080
FEATURE_FLAG_SERVICE_HOST=0.0.0.0

# Redis
REDIS_CLUSTER_NODES=redis-cluster.redis.svc.cluster.local:6379
REDIS_PASSWORD=${REDIS_PASSWORD}
REDIS_SSL_ENABLED=true
REDIS_CACHE_TTL_SECONDS=60

# MongoDB
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/feature_flags
MONGODB_DATABASE=feature_flags

# OPA
OPA_URL=http://opa.opa.svc.cluster.local:8181
OPA_POLICY_PATH=neuralhive/orchestrator/feature_flags_dynamic

# Observability
ENABLE_METRICS=true
ENABLE_TRACING=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector.observability.svc.cluster.local:4317
```

## External Dependencies

Nenhuma dependência externa nova além das já listadas na spec principal.
