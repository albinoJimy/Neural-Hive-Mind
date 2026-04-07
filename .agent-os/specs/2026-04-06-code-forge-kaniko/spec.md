# Spec: Code Forge - Kaniko Production-Ready & Private Registries

> **Epic:** Fase 2.4–2.13 Execução - code-forge completion
> **Ticket:** CF-001
> **Priority:** Média
> **Status:** Planning

## Overview

Implementar Kaniko production-ready com suporte a registries privados (ECR, GCR, ACR).

## Contexto

O code-forge está a 95% completo mas tem gaps críticos para produção enterprise:

**Gaps Identificados:**
1. Kaniko limitado a ~1MB (ConfigMap, sem fallback PVC)
2. Sem suporte a autenticação específica para ECR/GCR/ACR
3. Credenciais em plaintext
4. Sem rotação automática de tokens
5. Builds multi-arch lentos (sem paralelização)

**Problema:**
```python
# container_builder.py - Autenticação básica apenas
if username and password:
    # Basic auth apenas - não funciona com ECR IAM roles
    # nem com GCR service accounts, nem ACR managed identities
```

## User Stories

### US1: Kaniko com Grandes Contextos

Como **devops**, quero **fazer builds Kaniko com contextos >1MB**, para **suportar projetos enterprise grandes**.

**Fluxo:**
1. Pipeline detecta contexto >1MB
2. Sistema cria PVC para armazenar contexto
3. Kaniko pod monta PVC
4. Build executa normalmente
5. PVC é limpo após build

### US2: Autenticação ECR com IAM Roles

Como **devops AWS**, quero **usar IAM roles para ECR**, para **evitar gerir credenciais estáticas**.

**Fluxo:**
1. Pod em Kubernetes com IRSA (IAM Roles for Service Accounts)
2. Código obtém credenciais temporárias via AWS SDK
3. Token é usado para login no ECR
4. Token expira e é renovado automaticamente

### US3: Autenticação GCR com Service Accounts

Como **devops GCP**, quero **usar service accounts para GCR**, para **autenticação segura sem segredos**.

**Fluxo:**
1. Service account JSON é montado via secret
2. Código obtém access token usando OAuth2
3. Token é usado para login no GCR
4. Token é renovado antes de expirar

### US4: Autenticação ACR com Managed Identities

Como **devops Azure**, quero **usar managed identities para ACR**, para **autenticação integrada do Azure**.

**Fluxo:**
1. Pod com Azure Workload Identity
2. Código obtém token do Azure IMDS
3. Token é usado para login no ACR
4. Token é renovado automaticamente

### US5: Builds Multi-Arch Paralelos

Como **devops**, quero **builds multi-arch em paralelo**, para **reduzir tempo de build**.

**Fluxo:**
1. Pipeline detecta múltiplas plataformas
2. Builds são lançados em paralelo
3. Resultados são agregados
4. Manifest multi-arch é criado e pushado

## Spec Scope

### Componentes a Implementar

**1. PVC Fallback for Large Contexts**
- Ficheiro: `src/services/kaniko/pvc_manager.py`
- Deteta quando ConfigMap excede 1MB
- Cria PVC dinamicamente
- Limpa PVC após build
- Timeout e cleanup em caso de falha

**2. ECR IAM Integration**
- Ficheiro: `src/clients/ecr_client.py`
- Usa boto3 para obter token ECR
- Renova token automaticamente (12h validity)
- Fallback para credenciais estáticas se IRSA indisponível

**3. GCR Service Account Integration**
- Ficheiro: `src/clients/gcr_client.py`
- Usa Google Cloud SDK para OAuth2
- Renova token automaticamente (1h validity)
- Suporte workload identity federation

**4. ACR Managed Identity Integration**
- Ficheiro: `src/clients/acr_client.py`
- Usa Azure SDK para managed identity
- Renova token automaticamente
- Fallback para service principal se necessário

**5. Multi-Arch Parallel Builds**
- Ficheiro: `src/services/kaniko/parallel_builder.py`
- Lança builds em paralelo (asyncio)
- Aguarda todos builds completarem
- Cria manifest e push
- Falha graciosa se algum build falhar

### Integrações Necessárias

- **Kubernetes** - PVCs, pods, service accounts
- **AWS SDK** - boto3 para ECR
- **GCP SDK** - google-auth para GCR
- **Azure SDK** - azure-identity para ACR
- **Docker Registry API** - Validar autenticação

## Out of Scope

- Suporte a outros registries (Harbor, Artifactory, etc.) - futuro
- Cache distribuído entre arquiteturas - futuro
- Auto-scaling de builds - futuro

## Expected Deliverable

1. PVC Manager para contextos grandes
2. Clients específicos para ECR/GCR/ACR
3. Sistema de renovação de tokens
4. Builder multi-arch paralelo
5. Testes E2E para cada cenário
6. Documentação de configuração

## Technical Constraints

- Python 3.12+
- Kubernetes 1.25+ para PVCs dinâmicos
- Async/await para builds paralelos
- Secret management via Kubernetes Secrets
- Métricas Prometheus para tempo de build

## Security Considerations

- Nunca logar credenciais ou tokens
- Tokens em memória apenas (nunca persistidos)
- Rotação automática de tokens
- RBAC apropriado no Kubernetes
