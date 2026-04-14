# Spec: DASH-01 - Executive Evolution Dashboard

**Epic:** Dashboard Executivo Consolidado de Evolução
**Data:** 2026-04-14
**Prioridade:** P1 (Importante)
**Estimativa:** 3-5 dias

---

## 1. Objetivo

Criar um dashboard executivo consolidado que combine métricas de experimentação, hipóteses e impacto em um único painel Grafana.

---

## 2. Status Atual

**O que existe:**
- 11 dashboards individuais em `/monitoring/dashboards/`
- `governance-executive-dashboard.json` (952 linhas)

**O que falta:**
- Dashboard consolidado com 4 painéis principais
- Integração de dados de experimentação + hipóteses + impacto

---

## 3. Estrutura do Dashboard

### 3.1 Painéis Principais

| Painel | Descrição | Fonte de Dados |
|--------|-----------|----------------|
| **Experimentação** | Status de A/B tests, variants, winner | Prometheus, MLflow |
| **Hipóteses** | Status, validation, outcomes | MongoDB (hypothesis-library) |
| **Impacto** | Business metrics, model performance | Prometheus, MongoDB |
| **Timeline** | Model versions, rollouts, rollbacks | Prometheus, MongoDB |

### 3.2 Variáveis do Dashboard

```json
{
  "title": "Neural Hive Mind - Executive Evolution",
  "panels": [
    {
      "title": "Experimentação Ativa",
      "targets": [
        "experiments_active_total",
        "ab_tests_running",
        "experiments_by_status"
      ]
    },
    {
      "title": "Hipóteses por Status",
      "targets": [
        "hypothesis_by_status",
        "hypothesis_approval_rate",
        "hypothesis_testing_rate"
      ]
    },
    {
      "title": "Impacto de Negócio",
      "targets": [
        "ml_prediction_accuracy",
        "business_metric_lift",
        "model_deployment_frequency"
      ]
    },
    {
      "title": "Timeline de Evolução",
      "targets": [
        "model_versions_deployed",
        "rollbacks_count",
        "model_promotions_count"
      ]
    }
  ]
}
```

---

## 4. Tickets (Decomposição)

| Ticket | Descrição | Estimativa |
|--------|-----------|------------|
| DASH-01-01 | Criar dashboard consolidado base | 1 dia |
| DASH-01-02 | Painel de experimentação | 0.5 dia |
| DASH-01-03 | Painel de hipóteses | 0.5 dia |
| DASH-01-04 | Painel de impacto | 0.5 dia |
| DASH-01-05 | Timeline de evolução | 1 dia |

---

## 5. Implementação

### 5.1 Criar Dashboard

**Arquivo:** `/monitoring/dashboards/executive-evolution-dashboard.json`

```json
{
  "dashboard": {
    "title": "Executive Evolution Dashboard",
    "tags": ["evolution", "executive", "ml"],
    "timezone": "browser",
    "panels": [
      {
        "id": 1,
        "title": "Experimentação Ativa",
        "type": "stat",
        "targets": [
          {
            "expr": "experiments_active_total",
            "legendFormat": "Experiments Ativos"
          }
        ]
      },
      {
        "id": 2,
        "title": "Hipóteses por Status",
        "type": "graph",
        "targets": [
          {
            "expr": "hypothesis_status_current{status=\"DRAFT\"}",
            "legendFormat": "Draft"
          },
          {
            "expr": "hypothesis_status_current{status=\"IN_TESTING\"}",
            "legendFormat": "Testing"
          },
          {
            "expr": "hypothesis_status_current{status=\"COMPLETED\"}",
            "legendFormat": "Completed"
          }
        ]
      }
    ]
  }
}
```

### 5.2 Configurar Datasources

- Prometheus: `http://prometheus:9090`
- MongoDB: Usar datasource JSON API do hypothesis-library

---

## 6. Critérios de Aceite

- [ ] Dashboard criado em `/monitoring/dashboards/`
- [ ] 4 painéis implementados
- [ ] Dados de experimentação integrados
- [ ] Dados de hipóteses integrados
- [ ] Timeline de evolução funcional
- [ ] Dashboard carrega corretamente no Grafana

---

## 7. Testes

```bash
# Testes de validação
curl -X POST http://grafana:3000/api/dashboards/import -d @executive-evolution-dashboard.json

# Verificar que dashboard carrega
curl http://grafana:3000/d/executive-evolution-dashboard
```

---

## 8. Handoff para Implementação

**Branch:** `feat/DASH-01-executive-dashboard`

**Comandos:**
```bash
git checkout -b feat/DASH-01-executive-dashboard

# Criar dashboard
# ... monitoring/dashboards/executive-evolution-dashboard.json

# Configurar no Grafana
# ... kubectl apply -f k8s/observability/grafana-dashboard-configmap.yaml

# Testar
curl -X POST http://grafana:3000/api/dashboards/import -d @...

# Commit
git add .
git commit -m "feat(dashboard): create executive evolution dashboard"
```

---

**Spec criada para:** DASH-01
**Data:** 2026-04-14
