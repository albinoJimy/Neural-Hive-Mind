# ML Inference API - Documentação

Bem-vindo à documentação completa do serviço ML Inference API do Neural Hive-Mind.

## Índice da Documentação

### [API REST](./API.md)

Documentação completa da API REST incluindo:
- Visão geral e autenticação
- Rate limiting
- Todos os endpoints com exemplos
- Schemas de request/response
- Códigos de erro
- Exemplos em cURL, Python, JavaScript e Go

**Quando consultar:** Ao integrar com a API ou ao implementar clientes.

---

### [Deployment Guide](./DEPLOYMENT.md)

Guia completo de deployment em diferentes ambientes:
- Requisitos de sistema
- Variáveis de ambiente
- Deploy local
- Deploy com Docker
- Deploy Kubernetes (Helm)
- Configuração de MLflow
- GPU support
- Troubleshooting

**Quando consultar:** Ao fazer deploy do serviço em qualquer ambiente.

---

### [Development Guide](./DEVELOPMENT.md)

Guia para desenvolvedores:
- Setup do ambiente de desenvolvimento
- Estrutura do projeto
- Como executar testes
- Adicionar novos endpoints
- Padrões de código
- Debugging
- Workflow de contribuição

**Quando consultar:** Ao desenvolver novas funcionalidades ou corrigir bugs.

---

### [Metrics Documentation](./METRICS.md)

Documentação de métricas e observabilidade:
- Métricas Prometheus disponíveis
- Queries Grafana
- Dashboards
- Configuração de alertas
- Boas práticas

**Quando consultar:** Ao configurar monitoramento, dashboards ou alertas.

---

## Visão Rápida

### O que é o ML Inference API?

Serviço FastAPI que fornece inferência ML para predição de aprovação de planos cognitivos no Neural Hive-Mind.

### Principais Funcionalidades

- **Predição Individual:** `/api/v1/inference/predict`
- **Predição em Batch:** `/api/v1/inference/predict-batch`
- **Circuit Breaker:** Proteção contra falhas em cascata
- **Rate Limiting:** Prevenção de abuso
- **Métricas Prometheus:** Observabilidade completa
- **GPU Support:** Inferência acelerada opcional

### Stack Tecnológica

| Componente | Tecnologia |
|------------|------------|
| Framework | FastAPI |
| ML Model | scikit-learn (GradientBoosting) |
| Model Registry | MLflow |
| Observabilidade | Prometheus + OpenTelemetry |
| Rate Limiting | SlowAPI |
| Container | Docker |
| Orchestration | Kubernetes + Helm |

### Portas Padrão

| Serviço | Porta |
|---------|-------|
| API HTTP | 8010 |
| Metrics | 9091 |

### Serviços Integrados

```
┌─────────────────────────────────────────────────────────────┐
│                     Neural Hive-Mind                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐      ┌──────────────┐                    │
│  │  Gateway     │─────▶│  STE         │                    │
│  └──────────────┘      └──────────────┘                    │
│                               │                             │
│                               ▼                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            ML Inference API (porta 8010)              │  │
│  │  • Predict / Predict-Batch                            │  │
│  │  • Circuit Breaker                                    │  │
│  │  • Rate Limiting                                      │  │
│  │  • Metrics Prometheus                                 │  │
│  └──────────────────────────────────────────────────────┘  │
│                               │                             │
│                               ▼                             │
│  ┌──────────────┐      ┌──────────────┐                    │
│  │ Consensus    │      │ Approval     │                    │
│  │ Engine       │      │ Service     │                    │
│  └──────────────┘      └──────────────┘                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Links Úteis

- **Repository:** [github.com/albinojimy/Neural-Hive-Mind](https://github.com/albinojimy/Neural-Hive-Mind)
- **Main README:** [`../README.md`](../README.md)
- **Helm Chart:** [`../helm/ml-inference-api/`](../helm/ml-inference-api/)
- **Environment Example:** [`../.env.example`](../.env.example)

### Suporte

Para questões ou problemas:
1. Consulte a documentação relevante acima
2. Verifique o [Deployment Guide - Troubleshooting](./DEPLOYMENT.md#troubleshooting)
3. Abra uma issue no GitHub

---

## Quick Start

### 1. Clone e Setup

```bash
cd services/ml-inference-api
cp .env.example .env
```

### 2. Instale Dependências

```bash
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Execute

```bash
python -m src.main
```

### 4. Teste

```bash
curl http://localhost:8010/health

curl -X POST http://localhost:8010/api/v1/inference/predict \
  -H "Content-Type: application/json" \
  -d '{"intent_text": "Create user account", "specialist_confidence": 0.7}'
```

---

**Última atualização:** 2026-04-04
**Versão da API:** 1.0.0
**Versão do documento:** 1.0
