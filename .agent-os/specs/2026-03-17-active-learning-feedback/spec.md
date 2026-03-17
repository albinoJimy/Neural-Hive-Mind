# Spec Requirements Document

> Spec: Active Learning Feedback Collector
> Created: 2026-03-17
> Status: ✅ COMPLETED + v8 Integration
> Testes: 76/76 passando

## Overview

Implementar sistema de Active Learning para coletar feedbacks balanceados que maximizem a qualidade do dataset ML, priorizando casos sub-representados (baixa confiança, rejeições, domínios específicos) e fornecendo métricas de balanceamento em tempo real.

## User Stories

### Como Data Scientist, quero identificar casos sub-representados

Como Data Scientist, quero que o sistema identifique automaticamente quais tipos de casos precisam de mais feedback (ex: rejeições, baixa confiança, domínios específicos), para que eu possa priorizar a coleta de dados que mais impactam a qualidade do modelo.

**Workflow:**
1. Sistema analisa dataset atual e calcula balanceamento por classe
2. Casos com baixa representação são marcados como "prioritários"
3. Dashboard mostra métricas de balanceamento em tempo real
4. Alertas são gerados quando um tipo de caso atinge threshold crítico

### Como Engenheiro de ML, quero fila de prioridade para revisão manual

Como Engenheiro de ML, quero uma fila ordenada de casos que precisam de revisão manual, ordenada por "valor informacional" (incerteza do modelo), para maximizar o impacto de cada feedback coletado.

**Workflow:**
1. Sistema calcula "valor informacional" baseado em:
   - Confiança da predição (mais baixa = maior valor)
   - Representação no dataset (menos representado = maior valor)
   - Diversidade de domínios (novos domínios = maior valor)
2. Casos são enfileirados por ordem de valor
3. API permite pegar próximo caso da fila
4. Feedback submetido marca caso como coletado

## Spec Scope

1. **DatasetBalanceAnalyzer** - Analisa balanceamento atual do dataset por classe, confiança e domínio
2. **PriorityFeedbackQueue** - Fila de prioridade para casos que precisam de revisão manual
3. **ActiveLearningStrategy** - Calcula "valor informacional" de cada caso baseado em incerteza e representação
4. **Metrics API** - Endpoints para consultar métricas de balanceamento em tempo real
5. **Feedback Enrichment** - Marca feedbacks coletados via active learning com flag `balanced_dataset=True`

## Out of Scope

- Modificação do modelo ML existente
- Alteração do fluxo de aprovação/rejeição
- Interface UI para revisão manual (usar API existente)
- Retreino automático de modelos

## Expected Deliverable

1. DatasetBalanceAnalyzer funcional com cálculo de métricas de balanceamento por classe, confiança e domínio
2. PriorityFeedbackQueue persistida em MongoDB com ordenação por valor informacional
3. API REST `/api/v1/active-learning/queue` para obter próximos casos prioritários
4. API REST `/api/v1/active-learning/metrics` para consultar métricas de balanceamento
5. Integração com ApprovalService para marcar feedbacks coletados via active learning
6. **Script de retraining v8** - `ml_pipelines/training/retrain_v8_balanced.py` com filtro `balanced_dataset=True`
