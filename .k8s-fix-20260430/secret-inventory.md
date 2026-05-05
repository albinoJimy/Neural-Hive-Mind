# Inventário de Segredos GHCR - Neural-Hive-Mind
# Gerado: 2026-04-30

## Segredos Existentes por Namespace

| Namespace | Secret | Tipo | Age |
|-----------|--------|------|-----|
| neural-hive | ghcr-secret | dockerconfigjson | 77d |
| neural-hive | ghcr-pull | dockerconfigjson | 91d |
| neural-hive | ghcr-secret-fixed | dockerconfigjson | 78d |
| neural-hive | ghcr-token-new | dockerconfigjson | 78d |
| **neural-hive-mind** | **ghcr-credentials** | dockerconfigjson | 11d |
| neural-hive-staging | ghcr-secret | dockerconfigjson | 87d |
| approval | ghcr-secret | dockerconfigjson | 88d |
| docker-build | ghcr-secret | dockerconfigjson | 82d |

## Problema Identificado
- Namespace `neural-hive` NÃO tem `ghcr-credentials`
- Charts como `data-migration`, `doc-ingestion`, `test-generation` usam `ghcr-credentials`
- Mas estão no namespace `neural-hive` onde o secret não existe

## Ação Necessária
Criar `ghcr-credentials` no namespace `neural-hive` copiando de `neural-hive-mind` ou `ghcr-secret`

## Charts por tipo de secret (baseado na análise)
- Usam `ghcr-credentials`: approval-gateway, architect-agent, data-migration, doc-ingestion, documentation-generation, fluxo-g-dashboard, knowledge-graph-rag, requirements-engineering, test-generation
- Usam `ghcr-secret`: analyst-agents, approval-service, code-forge, consensus-engine, gateway-intencoes, guard-agents, etc.
