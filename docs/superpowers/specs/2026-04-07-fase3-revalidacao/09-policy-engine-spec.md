# Spec Requirements Document

> Spec: Dynamic Policy Engine (OPA)
> Created: 2026-04-07
> Status: Validation Completed

## Overview

Implementar e validar um motor de políticas dinâmico centralizado usando Open Policy Agent (OPA) e linguagem Rego para enforce de segurança, compliance e governança em toda a plataforma Neural Hive Mind, garantindo decisões consistentes, auditáveis e escaláveis across 8 serviços core e 47 políticas implementadas.

## User Stories

### História 1: Validação Centralizada de Políticas

Como **arquiteto de segurança**, quero um motor de políticas centralizado que valide ExecutionTickets, workflows e decisões de especialistas contra regras consistentes, para garantir que todos os serviços sigam os mesmos padrões de segurança e compliance.

**Workflow:**
1. Guard Agents recebe ExecutionTicket
2. Extrai dados do ticket (container spec, recursos, compliance)
3. Envia para OPA via POST /v1/data/neuralhive/guard/security_policies
4. OPA avalia 20+ regras de segurança (privileged, root_user, capabilities)
5. Retorna violações com severity (CRITICAL/HIGH/MEDIUM/LOW)
6. Guard Agents decide (APPROVED/REJECTED/REQUIRES_APPROVAL)
7. Decisão é auditada no MongoDB

### História 2: Autorização HTTP com JWT-SVID

Como **serviço Orchestrator**, quero validar requisições HTTP usando JWT-SVIDs emitidos pelo SPIRE, para garantir que apenas workloads autenticados e autorizados possam criar workflows e executar tickets.

**Workflow:**
1. Worker Agent obtém JWT-SVID do SPIRE Agent via Workload API
2. Envia requisição HTTP com header `Authorization: Bearer <jwt>`
3. Orchestrator extrai JWT e passa para OPA
4. OPA valida assinatura via JWKS do SPIRE Server
5. OPA verifica claims (sub, iss, aud, exp, tenant_id, roles)
6. OPA retorna allow/deny com violações (se houver)
7. Orchestrator permite/bloqueia requisição
8. Decisão é auditada

### História 3: SLA Enforcement Automático

Como **SRE**, quero que o OPA enforce automaticamente limites de SLO e quotas, para prevenir que tickets excedam recursos permitidos ou violem SLAs estabelecidos.

**Workflow:**
1. Ticket com recursos (CPU, memória, replicas)
2. OPA avalia contra quotas do namespace
3. OPA verifica SLOs (latency, availability, error rate)
4. Retorna violações se exceder limites
5. Orchestrator rejeita ou requer aprovação

## Spec Scope

1. **OPA Integration Layer** - Clientes HTTP assíncronos para 3 serviços (Orchestrator, Guard, Queen) com connection pooling, cache LRU, circuit breaker e retry logic

2. **Security Policy Enforcement** - 20+ regras de segurança para validação de ExecutionTickets (container security, network policies, image security, secret management)

3. **Compliance Policy Enforcement** - 15+ regras de compliance (GDPR, HIPAA, PCI-DSS, SOX) validando PII, encryption, audit logging, data retention

4. **Resource Policy Enforcement** - 15+ regras de recursos (CPU/memory limits, quotas, HPA, efficiency) para garantir uso eficiente de cluster

5. **HTTP Authorization with JWT-SVID** - Validação de JWTs emitidos pelo SPIRE com verificação de assinatura via JWKS, claims obrigatórios e mTLS

6. **SLA Enforcement** - Validação de SLOs e quotas com alertas automáticos quando tickets violam limites estabelecidos

7. **Chaos Engineering Validation** - 2 políticas para validação de experimentos (blast radius limits, experiment validation) garantindo segurança em testes de resiliência

8. **Self-Healing Playbook Validation** - Política para validar playbooks de autocura antes da execução, garantindo segurança e eficácia

## Out of Scope

- Implementação de políticas específicas de negócio (delegadas a cada domínio)
- UI para visualização/editação de políticas (apenas API)
- Versionamento avançado de políticas (apenas revision ID básico)
- Policy testing automatizado em pipeline CI/CD

## Expected Deliverable

1. **47 políticas Rego implementadas** organizadas em 8 categorias (orchestrator, guard-agents, gatekeeper, chaos, self_healing, queen, segurança base)

2. **3 clientes OPA integrados** em serviços core (Orchestrator, Guard, Queen) com cache, circuit breaker e audit logging

3. **Testes automatizados** para todas as políticas (50+ testes Rego + integração Python)

4. **Documentação completa** para cada categoria de política (READMEs com exemplos, troubleshooting)

5. **Métricas e observabilidade** para decisões OPA (cache hit ratio, circuit breaker state, decision duration)

6. **Deploy OPA** em Kubernetes com bundles sincronizados via ConfigMap/Secret
