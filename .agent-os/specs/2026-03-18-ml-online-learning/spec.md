# Spec Requirements Document

> Spec: ML Online Learning - Retreinamento Contínuo de Modelos
> Created: 2026-03-18
> Status: Planning

## Overview

Implementar sistema de retreinamento contínuo (online learning) para os modelos de aprovação do Neural-Hive-Mind, permitindo que os modelos se atualizem automaticamente com novos feedbacks coletados via Active Learning, mantendo a acurácia e reduzindo o desbalanceamento de classes.

## User Stories

### Manutenção Automática de Modelos

Como **engenheiro de ML**, quero que os modelos de aprovação sejam retreinados automaticamente quando novos dados estão disponíveis, para que a acurácia do modelo se mantenha alta sem intervenção manual manual.

**Fluxo:**
1. Active Learning coleta feedbacks balanceados
2. Quando atinge threshold (ex: 100 novos feedbacks), aciona retreinamento
3. Pipeline de treino executa com dados enriquecidos
4. Novo modelo é avaliado (F1-score, accuracy)
5. Se melhor que atual, faz deploy automático (canary)

### Monitoramento de Model Drift

Como **engenheiro de ML**, quero ser alertado quando o desempenho do modelo degrada, para que possa investigar causas e retreinar se necessário.

**Fluxo:**
1. Métricas de produção são monitoradas (approve rate, prediction confidence)
2. Se drift detectado (ex: drop >10% em F1), alerta é enviado
3. Dashboard mostra drift e sugere retreinamento

### Versionamento de Modelos

Como **engenheiro de ML**, quero rastrear versões de modelos e suas performances, para que possa reverter para versões anteriores se necessário.

**Fluxo:**
1. Cada modelo treinado recebe versão única (v9, v10, etc.)
2. MLflow armazena metadados (data, F1, accuracy, features)
3. Deploy canary permite teste em produção
4. Rollback rápido se problema detectado

## Spec Scope

1. **Auto-Retraining Pipeline** - Pipeline de retreinamento automático acionado por threshold de dados
2. **Model Registry com MLflow** - Versionamento e rastreamento de modelos treinados
3. **Drift Detection** - Monitoramento de degradation de performance em produção
4. **Canary Deployment** - Deploy gradual de novos modelos com rollback automático
5. **API de Gestão** - Endpoints para forçar retreinamento, listar versões, promover modelo

## Out of Scope

- Treino de novos tipos de modelos (apenas GradientBoosting/RandomForest existentes)
- Auto-tuning de hiperparâmetros (mantém valores atuais)
- Feature engineering automático (usa features existentes)
- Deploy multi-region (apenas single cluster)
- UI de monitoring (apenas API + Grafana existing)

## Expected Deliverable

1. Sistema que retreina modelos automaticamente quando 100+ novos feedbacks coletados
2. MLflow registry com versionamento de modelos e metadados de performance
3. API REST para gestão de modelos (POST /retrain, GET /versions, POST /promote)
4. CronJob Kubernetes para execução periódica (diária)
5. Métricas Prometheus para drift detection
6. Canary deployment com rollback automático
