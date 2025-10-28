# ADR-0010: Abordagem para Catálogo de APIs e Dados

## Status

Aceito

## Contexto

O documento-05-implementacao-e-operacao especifica necessidade de catálogo de APIs com classificação de dados, SLA tiers e políticas de retenção para governança. Solução deve integrar com OPA para enforcement automático de políticas.

## Decisão

Implementar catálogo baseado em CRDs Kubernetes + OPA ao invés de soluções como Backstage ou ferramentas SaaS.

## Justificativa

### CRDs + OPA vs. Alternativas

**CRDs + OPA (Escolhido)**
- Integração nativa com políticas existentes
- Enforcement automático via Gatekeeper
- Versionamento GitOps
- Baixa complexidade operacional
- Alinhamento com arquitetura existente

**Backstage**
- Complexidade operacional alta
- Stack adicional (Node.js, PostgreSQL)
- Catálogo separado das políticas
- Overhead desnecessário

**Soluções SaaS (Apigee, Kong)**
- Vendor lock-in
- Custos elevados
- Integração complexa com OPA
- Dados sensíveis externos

## Estrutura de Metadados

### ApiAsset CRD
```yaml
apiVersion: catalog.neural-hive.io/v1alpha1
kind: ApiAsset
metadata:
  name: gateway-intencoes-api
spec:
  owner: team-core
  classification: internal  # public|internal|confidential|restricted
  pii_fields: ["user_id", "email"]
  sla_tier: gold           # bronze|silver|gold|platinum
  retention_policy: "90d"
  endpoints:
    - path: "/intentions"
      method: "POST"
      sensitive_data: true
```

### DataAsset CRD
```yaml
apiVersion: catalog.neural-hive.io/v1alpha1
kind: DataAsset
metadata:
  name: user-intentions-data
spec:
  owner: team-core
  classification: confidential
  pii_fields: ["user_id", "intention_content"]
  retention_policy: "365d"
  storage_location: "kafka://intentions-topic"
```

## Governança Automática

### Tags Obrigatórias
- `data_owner`: Equipe responsável
- `data_classification`: Nível de sensibilidade
- `pii_fields`: Campos de dados pessoais
- `sla_tier`: Nível de serviço
- `retention_policy`: Política de retenção

### Validação OPA
- Enforcement via Gatekeeper
- Validação em tempo de deploy
- Relatórios de compliance automáticos
- Alertas para recursos não-conformes

## Consequências

### Positivas
- Integração perfeita com OPA/Gatekeeper
- Simplicidade operacional
- Versionamento via Git
- Enforcement automático de políticas
- Baixo overhead de recursos

### Negativas
- Interface não gráfica
- Funcionalidades limitadas vs. soluções completas
- Dependência de conhecimento Kubernetes
- Necessidade de tooling customizado

## Implementação

### Fase 1: CRDs Básicos
- ApiAsset e DataAsset CRDs
- Validação de schema
- Políticas OPA básicas

### Fase 2: Enforcement
- Gatekeeper constraints
- Validação obrigatória de tags
- Relatórios de compliance

### Fase 3: Automação
- Discovery automático de APIs
- Integração com CI/CD
- Dashboards de governança

## Integração com Pipeline

```yaml
# .github/workflows/api-governance.yml
- name: Validate API Assets
  run: |
    kubectl apply --dry-run=client -f k8s/catalog/
    opa test policies/catalog/
```

## Exemplo de Uso

```bash
# Registrar nova API
kubectl apply -f - <<EOF
apiVersion: catalog.neural-hive.io/v1alpha1
kind: ApiAsset
metadata:
  name: user-service-api
spec:
  owner: team-identity
  classification: internal
  pii_fields: ["user_id", "email", "phone"]
  sla_tier: gold
EOF
```