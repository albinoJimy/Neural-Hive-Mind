# Sub-Spec: Epic C - Feature Store Funcional

## Objetivo

Transformar o Feature Store de placeholder (237 LOC de definições) em um serviço funcional com API REST, pipeline de computação de 26 features e integração com Approval Service.

## Componentes

### 1. Feature Store Service (NOVO)
**Arquivo:** `services/feature-store/src/main.py`
**Porta:** 8010

**Endpoints API:**
- `GET /health` - Health check
- `GET /features/{plan_id}` - Buscar features de um plano
- `POST /features/{plan_id}` - Salvar features de um plano
- `PUT /features/{plan_id}` - Atualizar features de um plano
- `DELETE /features/{plan_id}` - Deletar features de um plano
- `GET /features/{plan_id}/history` - Histórico de versões

**Schema de Features:**
```python
{
    "plan_id": "uuid",
    "features": {
        "metadata": {
            "num_tasks": 5,
            "priority_score": 0.8,
            "total_duration_ms": 5000
        },
        "ontology": {
            "domain_risk_weight": 0.25,
            "avg_task_complexity_factor": 0.7
        },
        "graph": {
            "num_nodes": 8,
            "density": 0.6,
            "critical_path_length": 4
        },
        "embedding": {
            "mean_norm": 0.5,
            "std_norm": 0.1,
            "avg_diversity": 0.8
        }
    },
    "computed_at": "2026-03-30T12:00:00Z",
    "version": 1
}
```

**Integrações:**
- Redis: Cache com TTL de 1 hora (configurável)
- MongoDB: Persistência durável (coleção "plan_features")
- Schema validation: feature_definitions.py

### 2. Feature Computation Pipeline (NOVO)
**Arquivo:** `services/feature-store/src/computation.py`

**Funcionalidades:**
- Extração de 26 features definidas em feature_definitions.py
- Batch processing para features caras (graph, embedding)
- Cache invalidação estratégica
- Computação incremental (atualiza apenas features modificadas)

**Pipeline:**
```python
class FeatureComputationPipeline:
    async def compute_all_features(self, plan_id: str, cognitive_plan: dict) -> dict:
        """Computa todas as 26 features do plano."""
        features = {}

        # 1. Metadata features (rápido)
        features["metadata"] = self._compute_metadata_features(cognitive_plan)

        # 2. Ontology features (médio)
        features["ontology"] = await self._compute_ontology_features(cognitive_plan)

        # 3. Graph features (lento, cacheable)
        features["graph"] = await self._compute_graph_features(cognitive_plan)

        # 4. Embedding features (muito lento, cacheável)
        features["embedding"] = await self._compute_embedding_features(cognitive_plan)

        return features
```

### 3. Cliente para Approval Service (NOVO)
**Arquivo:** `services/approval-service/src/services/feature_store_client.py`

**Funcionalidades:**
- Client gRPC/REST para Feature Store
- Cache local de features (5 minutos)
- Fallback graceful (retorna features vazias se indisponível)
- Retry com exponential backoff

```python
class FeatureStoreClient:
    async def get_features(self, plan_id: str) -> dict:
        """Busca features do Feature Store com cache local."""
        # 1. Verificar cache local
        cached = self._local_cache.get(plan_id)
        if cached:
            return cached

        # 2. Buscar do Feature Store
        try:
            features = await self._fetch_from_store(plan_id)
            self._local_cache.set(plan_id, features, ttl=300)
            return features
        except Exception as e:
            logger.warning(f"Feature Store unavailable: {e}")
            return {}  # Fallback

    async def save_features(self, plan_id: str, features: dict) -> bool:
        """Salva features no Feature Store."""
        try:
            await self._send_to_store(plan_id, features)
            self._local_cache.delete(plan_id)
            return True
        except Exception as e:
            logger.error(f"Failed to save features: {e}")
            return False
```

### 4. Integração no Approval Service
**Arquivo:** `services/approval-service/src/services/approval_service.py`

**Modificação:** Adicionar busca de features antes de aprovar

```python
class ApprovalService:
    def __init__(self, ..., feature_store_client: FeatureStoreClient):
        ...
        self.feature_store_client = feature_store_client

    async def process_approval(self, plan: CognitivePlan) -> ApprovalDecision:
        # 1. Buscar features do Feature Store
        features = await self.feature_store_client.get_features(plan.plan_id)

        # 2. Enriquecer plano com features
        plan.enriched_features = features

        # 3. Processar aprovação com features
        decision = await self._make_decision(plan, features)

        # 4. Salvar features para histórico
        await self.feature_store_client.save_features(plan.plan_id, features)

        return decision
```

## Estrutura de Diretórios

```
services/feature-store/
├── Dockerfile
├── requirements.txt
├── pyproject.toml
├── src/
│   ├── __init__.py
│   ├── main.py (FastAPI app)
│   ├── computation.py (FeatureComputationPipeline)
│   ├── config/
│   │   └── settings.py
│   ├── clients/
│   │   ├── redis_client.py
│   │   └── mongodb_client.py
│   └── models/
│       └── feature_schemas.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_computation.py
│   └── fixtures.py
└── helm/
    ├── Chart.yaml
    ├── values.yaml
    └── templates/
        ├── deployment.yaml
        ├── service.yaml
        └── ingress.yaml
```

## Verificação

```bash
# Testar API
curl http://feature-store.neural-hive.svc.cluster.local:8010/health
# Esperado: {"status": "healthy", "version": "1.0.0"}

# Testar CRUD
curl -X POST http://feature-store.neural-hive.svc.cluster.local:8010/features/test-plan \
  -H "Content-Type: application/json" \
  -d '{"features": {"metadata": {"num_tasks": 5}}}'

curl http://feature-store.neural-hive.svc.cluster.local:8010/features/test-plan
# Esperado: {"plan_id": "test-plan", "features": {...}}

# Testar cache Redis
redis-cli GET "features:test-plan"
# Esperado: JSON com features

# Testar persistência MongoDB
mongosh neural-hive --eval "db.plan_features.findOne({plan_id: 'test-plan'})"

# Verificar integração com Approval Service
# (logs devem mostrar busca de features)
```

## Testes

```python
@pytest.mark.asyncio
async def test_get_features_cache_hit():
    """Testa cache hit ao buscar features."""
    # Given: feature em cache local
    client = FeatureStoreClient()
    client._local_cache.set("test-plan", {"metadata": {"num_tasks": 5}})

    # When: buscar features
    features = await client.get_features("test-plan")

    # Then: retornar do cache sem chamar API
    assert features["metadata"]["num_tasks"] == 5

@pytest.mark.asyncio
async def test_compute_all_features():
    """Testa computação de todas as 26 features."""
    pipeline = FeatureComputationPipeline()
    cognitive_plan = sample_cognitive_plan()

    features = await pipeline.compute_all_features("test-plan", cognitive_plan)

    assert "metadata" in features
    assert "ontology" in features
    assert "graph" in features
    assert "embedding" in features
    assert len(features["metadata"]) >= 6
```
