# Spec Requirements Document

> Spec: GAP-01 STE-Consensus Topic Fix
> Created: 2026-03-29
> Status: Planning
> Epic: Corrigir fluxo principal do Neural-Hive-Mind

## Overview

Corrigir inconsistência de configuração do Semantic Translation Engine, onde o default hardcoded em código Python (`cognitive-plans`) diverge da configuração Helm/K8s (`plans.ready`), criando um problema em ambientes locais e eliminando a dependência silenciosa de env var para o fluxo funcionar corretamente.

**Problema:** Default hardcoded `cognitive-plans` em settings.py diverge do Helm chart `plans.ready`
**Impacto:** Fluxo quebrado em ambientes locais (docker-compose, dev puro); inconsistência código-config
**Solução:** Alinhar default do settings.py com `plans.ready` (igual ao Helm chart)
**Benefício:** Comportamento consistente em todos os ambientes; eliminação de "armadilha" de configuração

## User Stories

### Como Operador de Sistema

Como operador de sistema, quero que o fluxo principal (Gateway → STE → Consensus → Specialists → Orchestrator) funcione corretamente, para que intenções de usuários sejam processadas sem erros de timeout ou mensagens perdidas.

**Workflow Atual (QUEBRADO):**
1. Usuário envia intenção → Gateway
2. Gateway processa → STE
3. STE produz em `cognitive-plans` ❌
4. Consensus aguarda em `plans.ready` (nunca recebe)
5. Timeout/falha silenciosa

**Workflow Corrigido:**
1. Usuário envia intenção → Gateway
2. Gateway processa → STE
3. STE produz em `plans.ready` ✅
4. Consensus recebe e processa ✅
5. Especialistas são invocados
6. Decisão consolidada publicada

### Como Desenvolvedor

Como desenvolvedor, quero que a configuração de tópicos Kafka seja consistente entre código Python e Helm charts, para evitar confusão e erros de deploy.

**Dor Atual:**
- Helm charts: `plans.ready` (correto)
- Código Python: `cognitive-plans` (incorreto)
- Divergência causa falhas silenciosas

### Como Engenheiro de Observabilidade

Como engenheiro de observabilidade, quero que todas as mensagens do fluxo principal sejam rastreáveis de ponta a ponta, permitindo detecção de falhas e medição de latência.

## Spec Scope

### In Scope

1. **Alteração de Configuração STE**
   - `services/semantic-translation-engine/src/config/settings.py` (linha 51)
   - Mudar default de `kafka_plans_topic` de `'cognitive-plans'` para `'plans.ready'`
   - Alinhar com configuração Helm chart já existente

2. **Atualização de Testes STE**
   - `services/semantic-translation-engine/tests/conftest.py` (linha 127)
   - Atualizar mock settings
   - Revisar testes que hardcoded referência ao tópico antigo

3. **Validação de Consistência**
   - Confirmar que Helm charts já usam `plans.ready` (já está correto)
   - Validar que env var `KAFKA_PLANS_TOPIC` sobrescreve o default em K8s
   - Documentar o comportamento esperado em cada ambiente

4. **Testes de Ambiente Local**
   - Validar funcionamento em docker-compose (sem Helm)
   - Garantir que testes de integração funcionam localmente

### Contexto Importante

**Status Atual por Ambiente:**
- ✅ **Produção/K8s (com Helm):** Funciona corretamente (env var sobrescreve default)
- ❌ **Local/docker-compose:** Quebrado (usa default `cognitive-plans`)
- ⚠️ **Testes isolados:** Inconsistentes (dependem de mock correto)

**Por que a correção ainda é necessária:**
- Eliminar dependência silenciosa de env var (armadilha)
- Comportamento consistente entre ambientes
- Evitar confusão em desenvolvimento local
- Melhorar DX (developer experience)

### Out of Scope

- Mudanças no Consensus Engine (já está correto)
- Alteração de schema de mensagens
- Criação de novos tópicos Kafka
- Mudanças em outros produtores/consumidores

## Expected Deliverable

1. **Código Modificado**
   - `settings.py` com `kafka_plans_topic='plans.ready'`
   - `conftest.py` com mock atualizado
   - Todos os testes passando

2. **Validação Funcional**
   - STE produz em `plans.ready`
   - Consensus consome de `plans.ready`
   - Fluxo completo sem erros

3. **Documentação Atualizada**
   - CHANGELOG.md com entrada
   - Diagrama de arquitetura corrigido

4. **Deploy Validado**
   - Rolling update sem downtime
   - Métricas normais
   - Logs sem erros
