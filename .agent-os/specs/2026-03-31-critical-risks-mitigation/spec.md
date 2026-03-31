# Spec Requirements Document

> Spec: Mitigação de Riscos Críticos NHM
> Created: 2026-03-31
> Status: Planning

---

## Overview

Implementar correções para os 4 riscos críticos identificados na análise consolidada do Neural-Hive-Mind: (1) remover credenciais hardcoded, (2) aumentar cobertura de testes para ≥70% em módulos críticos, (3) implementar versão rápida de testes E2E, e (4) completar Kafka Consumer dos Scout Agents.

## User Stories

### US-1: Remover Credenciais Hardcoded

Como **engenheiro de DevOps**, quero **remover todas as credenciais hardcoded do código**, para que o sistema seja seguro em produção.

**Workflow actual:**
- JWT secrets em `auth.py` e `settings.py`
- API keys em ficheiros de configuração
- Risco de exposição em repositório

**Workflow desejado:**
- Todas as credenciais via Vault
- Rotação automática de credenciais
- Validação no CI/CD

### US-2: Aumentar Cobertura de Testes

Como **engenheiro de QA**, quero **aumentar cobertura de testes para ≥70%** em módulos críticos, para garantir confiança nas mudanças.

**Workflow actual:**
- Cobertura de 10-15% global
- Módulos críticos com 0-5% (drift_monitoring, observability, compliance, ledger)

**Workflow desejado:**
- Cobertura ≥70% em módulos críticos
- Testes unitários + integração
- Pipeline de CI bloqueando sem cobertura mínima

### US-3: Testes E2E Rápidos

Como **engenheiro de CI/CD**, quero **testes E2E com duração <30min**, para ter feedback rápido.

**Workflow actual:**
- Testes E2E desabilitados (>180min)
- Smoke tests inexistentes

**Workflow desejado:**
- Smoke tests (<10min) para validação rápida
- E2E completos (<30min) para validação full
- Pipeline rodando em cada commit

### US-4: Scout Consumer Completo

Como **engenheiro de streaming**, quero **Kafka Consumer funcional dos Scout Agents**, para consumir eventos reais de canais digitais.

**Workflow actual:**
- Consumer ainda é stub
- Scouts não consomem eventos reais

**Workflow desejado:**
- Consumer completo integrado
- Deserialização Avro
- Error handling + DLQ

---

## Spec Scope

1. **Credenciais Hardcoded** — Remover JWT secrets e API keys, migrar para Vault
2. **Cobertura de Testes** — Escrever testes para drift_monitoring, observability, compliance, ledger
3. **Testes E2E** — Criar smoke tests (<10min) e E2E completos (<30min)
4. **Scout Consumer** — Implementar consumer Kafka completo com Avro

## Out of Scope

- Refactor de arquitectura
- Novas features não relacionadas a segurança/qualidade
- Módulos não críticos (podem esperar)

---

## Expected Deliverable

1. Zero credenciais hardcoded no código
2. Cobertura de testes ≥70% em módulos críticos (drift_monitoring, observability, compliance, ledger)
3. Testes E2E executando em <30min no CI/CD
4. Scout Agents consumindo eventos reais do Kafka
