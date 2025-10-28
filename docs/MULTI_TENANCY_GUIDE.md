# Guia de Multi-Tenancy - Neural Hive Mind

## Visão Geral

O Neural Hive Mind implementa multi-tenancy nativo com isolamento completo de dados, modelos e métricas por tenant. Este guia documenta a arquitetura, configuração e uso do sistema multi-tenant.

## Arquitetura

### Camadas de Isolamento

1. **Gateway Layer (Envoy)**
   - Roteamento baseado em header `x-tenant-id`
   - Rate limiting por tenant
   - Validação JWT com tenant context

2. **Application Layer (Specialists)**
   - Modelo ML por tenant
   - Configuração customizada por tenant
   - Métricas isoladas com cardinality cap

3. **Data Layer**
   - Cache Redis segregado por tenant
   - MongoDB com índices compostos por tenant_id
   - Ledger cognitivo isolado

## Configuração

### 1. Configurar Tenants

Adicionar configuração de tenant em `multi_tenant_specialist.py`:

```python
TenantConfig(
    tenant_id='tenant-enterprise-A',
    tenant_name='Enterprise A',
    model_name_override='technical-model-enterprise-a',
    model_version_override='2.0.0',
    is_active=True,
    rate_limit_rps=500,
    cache_ttl_override=7200
)
```

### 2. Configurar Envoy Gateway

O Envoy já está configurado para:

- Extrair `x-tenant-id` do payload JWT via filtro Lua
- Rotear para especialistas baseado em `x-specialist-type`
- Aplicar rate limits por tenant usando `request_headers`

#### Extração de tenant_id do JWT

```yaml
- name: envoy.filters.http.lua
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua
    inline_code: |
      function envoy_on_request(request_handle)
        local metadata = request_handle:streamInfo():dynamicMetadata()
        local jwt_payload = metadata:get("envoy.filters.http.jwt_authn")

        if jwt_payload and jwt_payload["jwt_payload"] then
          local payload = jwt_payload["jwt_payload"]

          -- Extrair tenant_id do payload JWT
          if payload["tenant_id"] then
            request_handle:headers():add("x-tenant-id", payload["tenant_id"])
          end
        end
      end
```

#### Rate Limits por Tenant

**IMPORTANTE**: Usar `request_headers` em vez de `header_value_match` para passar valores reais ao RLS.

Configuração correta em cada rota:

```yaml
routes:
  - match:
      prefix: "/"
      grpc: {}
      headers:
      - name: x-specialist-type
        exact_match: technical
    route:
      cluster: specialist_technical
      rate_limits:
      - actions:
        - request_headers:
            header_name: "x-tenant-id"
            descriptor_key: "tenant_id"
        - request_headers:
            header_name: "x-specialist-type"
            descriptor_key: "specialist_type"
```

Isso envia descritores ao RLS no formato:
- `tenant_id=tenant-A` (valor real do header)
- `specialist_type=technical` (valor real do header)

Editar `infrastructure/envoy/ratelimit-config.yaml`:

```yaml
domain: specialists
descriptors:
  # Rate limit padrão por tenant (100 req/s)
  - key: tenant_id
    rate_limit:
      unit: second
      requests_per_unit: 100

  # Rate limit para tenant premium (500 req/s)
  - key: tenant_id
    value: tenant-enterprise-A
    rate_limit:
      unit: second
      requests_per_unit: 500

  # Rate limit combinado: tenant + specialist_type
  - key: tenant_id
    descriptors:
      - key: specialist_type
        rate_limit:
          unit: second
          requests_per_unit: 50
```

### 3. Configurar Specialist Config

Habilitar multi-tenancy em `config.py`:

```python
enable_multi_tenancy: bool = True
max_tenants: int = 100  # Cardinality cap para métricas
default_tenant_id: str = 'default'
```

## Fluxo de Requisição

### End-to-End com Tenant ID

```
Cliente → Envoy → gRPC Server → MultiTenantSpecialist → BaseSpecialist
   |        |          |                  |                    |
   |        |          |                  |                    ├─> Cache (com tenant_id)
   |        |          |                  |                    ├─> Ledger (com tenant_id)
   |        |          |                  |                    └─> Metrics (com tenant_id)
   |        |          |                  |
   |        |          |                  └─> Carrega modelo do tenant
   |        |          |
   |        |          └─> Injeta x-tenant-id no request.context
   |        |
   |        └─> Valida JWT e rate limiting
   |
   └─> Envia header: x-tenant-id: tenant-A
```

### 1. Cliente Envia Requisição

```bash
grpcurl -H "x-tenant-id: tenant-A" \
        -H "x-specialist-type: technical" \
        -H "Authorization: Bearer $TOKEN" \
        -d '{"plan_id": "plan-123", ...}' \
        localhost:50051 neural_hive.SpecialistService/EvaluatePlan
```

### 2. Envoy Processa

- Valida JWT
- Aplica rate limiting para tenant-A (500 req/s)
- Roteia para specialist-technical

### 3. gRPC Server Injeta Context

```python
# grpc_server.py
metadata = dict(context.invocation_metadata())
tenant_id = metadata.get('x-tenant-id')
if tenant_id:
    request.context['tenant_id'] = tenant_id
```

### 4. MultiTenantSpecialist Processa

```python
# multi_tenant_specialist.py
tenant_id = request.context.get('tenant_id', 'default')
tenant_config = self._validate_tenant(tenant_id)
tenant_model = self._load_tenant_model(tenant_id)
```

### 5. BaseSpecialist com Isolamento

```python
# base_specialist.py
tenant_id = request.context.get('tenant_id', 'default')

# Cache isolado
cache_key = self.opinion_cache.generate_cache_key(
    plan_bytes=plan_bytes,
    tenant_id=tenant_id
)

# Ledger isolado - SEMPRE passar tenant_id
self.ledger_client.save_opinion(
    opinion=opinion_data,
    plan_id=plan_id,
    intent_id=intent_id,
    specialist_type='technical',
    correlation_id=correlation_id,
    tenant_id=tenant_id  # ✅ Isolamento garantido
)

# Consultas ao ledger - SEMPRE filtrar por tenant_id
opinions = self.ledger_client.get_opinions_by_plan(
    plan_id=plan_id,
    tenant_id=tenant_id  # ✅ Filtra apenas dados deste tenant
)

# Consultar por intent_id também filtra por tenant
opinions = self.ledger_client.get_opinions_by_intent(
    intent_id=intent_id,
    tenant_id=tenant_id  # ✅ Isolamento garantido
)

# Métricas isoladas
self.metrics.increment_tenant_evaluation(tenant_id)
```

### 6. Isolamento no Ledger (MongoDB)

**CRÍTICO**: Todas as consultas ao ledger DEVEM incluir `tenant_id` para prevenir vazamento de dados.

```python
# ✅ CORRETO: Filtra por tenant_id
opinions = ledger_client.get_opinions_by_plan(
    plan_id='plan-123',
    tenant_id='tenant-A'  # Retorna apenas dados do tenant-A
)

# ❌ INCORRETO: Sem tenant_id pode vazar dados!
opinions = ledger_client.get_opinions_by_plan(
    plan_id='plan-123'
    # tenant_id omitido - retorna dados de TODOS os tenants com este plan_id!
)
```

**Implementação interna**:

```python
def get_opinions_by_plan_impl(self, plan_id: str, tenant_id: Optional[str] = None):
    # Construir query com tenant_id se fornecido
    query = {'plan_id': plan_id}
    if tenant_id is not None:
        query['tenant_id'] = tenant_id  # ✅ Filtro de isolamento

    cursor = self.collection.find(query)
    # ... processar resultados
```

**Índices MongoDB para isolamento**:

```python
# Índice único: tenant_id + opinion_id
collection.create_index(
    [("tenant_id", ASCENDING), ("opinion_id", ASCENDING)],
    unique=True,
    name="idx_tenant_opinion_id"
)

# Índice composto: tenant_id + plan_id (performance)
collection.create_index(
    [("tenant_id", ASCENDING), ("plan_id", ASCENDING)],
    name="idx_tenant_plan_id"
)

# Índice composto: tenant_id + specialist_type + evaluated_at
collection.create_index(
    [("tenant_id", ASCENDING), ("specialist_type", ASCENDING), ("evaluated_at", DESCENDING)],
    name="idx_tenant_specialist_evaluated_at"
)
```

## Métricas por Tenant

### Disponíveis

- `neural_hive_tenant_evaluations_total{tenant_id}`
- `neural_hive_tenant_evaluation_duration_seconds{tenant_id}`
- `neural_hive_tenant_errors_total{tenant_id, error_type}`
- `neural_hive_tenant_cache_hits_total{tenant_id}`
- `neural_hive_tenant_cache_misses_total{tenant_id}`

### Cardinality Cap

O sistema rastreia até `max_tenants` (default: 100) tenants distintos. Tenants além desse limite são agregados sob o label `tenant_id="other"`.

### Consultar Métricas

```promql
# Taxa de avaliações por tenant
rate(neural_hive_tenant_evaluations_total[5m])

# P95 de latência por tenant
histogram_quantile(0.95,
  rate(neural_hive_tenant_evaluation_duration_seconds_bucket[5m])
)

# Cache hit ratio por tenant
sum(rate(neural_hive_tenant_cache_hits_total[5m])) by (tenant_id)
/
(
  sum(rate(neural_hive_tenant_cache_hits_total[5m])) by (tenant_id)
  +
  sum(rate(neural_hive_tenant_cache_misses_total[5m])) by (tenant_id)
)
```

## Testes

### Executar Testes de Multi-Tenancy

```bash
# Testes de multi-tenant specialist
pytest libraries/python/neural_hive_specialists/tests/test_multi_tenant_specialist.py -v

# Testes de isolamento
pytest libraries/python/neural_hive_specialists/tests/test_tenant_isolation.py -v
```

### Validar Isolamento

```python
# Verificar que cache keys são diferentes
assert cache_key_tenant_a != cache_key_tenant_b

# Verificar que ledger tem tenant_id
assert document['tenant_id'] == 'tenant-A'

# Verificar cardinality cap
assert len(metrics._known_tenants) <= config.max_tenants
```

### Teste Crítico: Prevenção de Vazamento no Ledger

O teste `test_no_ledger_leakage_between_tenants` valida que dois tenants com mesmo `plan_id` não vazam dados:

```python
def test_no_ledger_leakage_between_tenants(self, mock_mongo_client, config):
    """Verifica que consultas ao ledger filtram por tenant_id."""
    # Simular dois tenants com MESMO plan_id
    tenant_a_doc = {
        'opinion_id': 'opinion-a-123',
        'plan_id': 'shared-plan-999',  # ⚠️  Mesmo plan_id!
        'tenant_id': 'tenant-A',
        'opinion': {'recommendation': 'approve'}
    }
    tenant_b_doc = {
        'opinion_id': 'opinion-b-456',
        'plan_id': 'shared-plan-999',  # ⚠️  Mesmo plan_id!
        'tenant_id': 'tenant-B',
        'opinion': {'recommendation': 'reject'}
    }

    # Consulta com tenant_id = 'tenant-A'
    opinions_a = ledger.get_opinions_by_plan('shared-plan-999', tenant_id='tenant-A')

    # ✅ Deve retornar APENAS opinião do tenant-A
    assert len(opinions_a) == 1
    assert opinions_a[0]['tenant_id'] == 'tenant-A'
    assert opinions_a[0]['opinion_id'] == 'opinion-a-123'

    # Consulta com tenant_id = 'tenant-B'
    opinions_b = ledger.get_opinions_by_plan('shared-plan-999', tenant_id='tenant-B')

    # ✅ Deve retornar APENAS opinião do tenant-B
    assert len(opinions_b) == 1
    assert opinions_b[0]['tenant_id'] == 'tenant-B'
    assert opinions_b[0]['opinion_id'] == 'opinion-b-456'
```

Este teste garante que **mesmo com identificadores idênticos** (plan_id, intent_id), os dados permanecem isolados por tenant.

## Tratamento de Erros

### Tenant Desconhecido

```python
# Retorna gRPC StatusCode.INVALID_ARGUMENT
ValueError("Tenant desconhecido: tenant-XYZ")
```

### Tenant Inativo

```python
# Retorna gRPC StatusCode.PERMISSION_DENIED
ValueError("Tenant inativo: tenant-B")
```

### Sem Tenant ID

```python
# Usa default_tenant_id do config
tenant_id = context.get('tenant_id', config.default_tenant_id)
```

## Segurança

### Isolamento de Dados

- ✅ Cache: Chaves incluem `tenant_id` no prefixo
- ✅ Ledger: Índices compostos `tenant_id + opinion_id` (unique)
- ✅ Métricas: Labels com `tenant_id` + cardinality cap
- ✅ Modelos: Cache local por `tenant_id`

### Validação

- ✅ JWT validado pelo Envoy antes de chegar ao specialist
- ✅ Tenant validado contra lista conhecida
- ✅ Status ativo verificado antes de processar

## Troubleshooting

### Tenant não recebe requisições

1. Verificar header `x-tenant-id` está sendo enviado
2. Verificar tenant está configurado em `tenant_configs`
3. Verificar `is_active=True` no tenant config

### Cache não isola tenants

1. Verificar `generate_cache_key()` recebe `tenant_id`
2. Verificar chave inclui tenant no formato: `opinion:{tenant_id}:{type}:{version}:{hash}`

### Métricas não aparecem para tenant

1. Verificar tenant não foi agregado em 'other' por cardinality cap
2. Verificar `increment_tenant_evaluation()` está sendo chamado
3. Verificar `max_tenants` no config

### Rate limiting não funciona

1. Verificar `ratelimit-config.yaml` tem entrada para o tenant
2. Verificar Envoy está enviando descritores corretos
3. Verificar rate limit service está rodando

## Próximos Passos

### Monitoramento (TODO)

- Dashboard Grafana para métricas por tenant
- Alertas para tenants específicos
- Visualização de uso de recursos

### Expansões Futuras

- Suporte a multi-region por tenant
- Quotas customizadas por tenant
- SLA tracking por tenant
- Billing/metering por tenant

## Referências

- [Protobuf Definitions](../protos/specialist.proto)
- [Multi-Tenant Specialist Code](../libraries/python/neural_hive_specialists/multi_tenant_specialist.py)
- [Envoy Configuration](../infrastructure/envoy/envoy-specialists-gateway.yaml)
- [Rate Limit Config](../infrastructure/envoy/ratelimit-config.yaml)
