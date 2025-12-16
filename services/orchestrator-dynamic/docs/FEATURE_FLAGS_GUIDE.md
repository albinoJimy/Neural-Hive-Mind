# Feature Flags Guide

Guia para configuração e uso de feature flags controladas por OPA.

## Visão Geral
- Feature flags são decisões booleanas derivadas de políticas OPA.
- Permitem habilitar/desabilitar funcionalidades dinamicamente sem redeploy.
- Suportam rollout gradual, testes A/B e habilitações específicas por tenant/namespace.

## Feature Flags Disponíveis
- `enable_intelligent_scheduler`: habilita o scheduler inteligente baseado em ML.
- `enable_burst_capacity`: ativa burst capacity para tenants premium ou risk_band crítico.
- `enable_predictive_allocation`: habilita alocação preditiva quando a acurácia do modelo > 0.85.
- `enable_auto_scaling`: habilita auto-scaling baseado em profundidade de fila e janelas de negócio.
- `enable_experimental_features`: libera features experimentais para namespaces de desenvolvimento ou tenants early access.

## Como Configurar
- Edite `policies/rego/orchestrator/feature_flags.rego` para ajustar regras por namespace, tenant ou métricas.
- Ajuste variáveis de entrada:
  - `flags.intelligent_scheduler_enabled`, `flags.burst_capacity_enabled`, `flags.predictive_allocation_enabled`, `flags.auto_scaling_enabled`
  - `flags.scheduler_namespaces`, `flags.premium_tenants`, `flags.scaling_threshold`, `flags.burst_threshold`
- Teste localmente: `opa eval -d feature_flags.rego -i input.json "data.neuralhive.orchestrator.feature_flags.result"`.

## Exemplos de Uso
- Habilitar intelligent scheduler apenas em `production`/`staging`.
- Habilitar burst capacity somente para tenants premium com `current_load < burst_threshold`.
- Habilitar predictive allocation quando `model_accuracy > 0.85` em namespaces `staging`/`beta`.
- Habilitar auto-scaling apenas durante business hours com `queue_depth > scaling_threshold`.
- Habilitar experimental features para tenants em early access ou namespaces `dev`/`staging`.

## Integração com Código
- Feature flags são avaliadas em `ticket_generation.allocate_resources` e retornadas em `policy_decisions['feature_flags']`.
- Flags são usadas para decidir uso do `IntelligentScheduler` (ex.: `enable_intelligent_scheduler`) e capacidades como burst ou auto-scaling.
- As decisões são anexadas em `ticket['metadata']['policy_decisions']['feature_flags']` para downstream.
