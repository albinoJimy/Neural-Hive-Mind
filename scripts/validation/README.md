# Scripts de Validação - Neural Hive-Mind

Este diretório contém scripts para validação completa do sistema Neural Hive-Mind, incluindo validações de especialistas, modelos ML, infraestrutura e fluxos end-to-end.

## Visão Geral

### Arquitetura de Validação

A suite de validação cobre múltiplas camadas do sistema:

```
┌──────────────────────────────────────────────────────────────┐
│  Master Orchestrator: validate-all-specialists.sh            │
├──────────────────────────────────────────────────────────────┤
│  Fase 1: Modelos ML         (validate_models_loaded.sh)     │
│  Fase 2: Saúde Specialists  (validate-specialist-health.sh)  │
│  Fase 3: Inferência Modelos (test-specialist-inference.py)   │
│  Fase 4: E2E Consensus      (test-consensus-engine-e2e.py)   │
│  Fase 5: Métricas           (validate-prometheus-metrics.sh) │
└──────────────────────────────────────────────────────────────┘
```

### Fluxo E2E Completo

```
Gateway → Semantic Translation → Consensus Engine → Specialists (5) → MongoDB → Memory Layer API
                                       ↓
                                   Pheromone Trails (Redis)
                                       ↓
                                   Prometheus Metrics
```

---

## 🆕 Scripts de Validação de Especialistas

### validate-all-specialists.sh (Master Orchestrator)

**Propósito**: Orquestrador mestre que executa toda a suite de validação de especialistas em sequência

**Uso**:
```bash
# Executar validação completa
./scripts/validation/validate-all-specialists.sh

# Modo rápido (pula testes de inferência e E2E)
./scripts/validation/validate-all-specialists.sh --quick

# Validar apenas um especialista
./scripts/validation/validate-all-specialists.sh --specialist technical

# Modo CI/CD (output JSON)
./scripts/validation/validate-all-specialists.sh --ci-mode --output-dir ./reports
```

**Fases de Validação**:
1. **Pré-requisitos**: Valida kubectl, jq, curl, python3, acesso ao cluster
2. **Modelos ML**: Verifica modelos no MLflow e carregamento nos specialists
3. **Saúde dos Specialists**: Pods, containers, endpoints, dependências
4. **Inferência de Modelos**: Testa inferência real via gRPC com planos cognitivos
5. **Métricas Prometheus**: Valida coleta de métricas e dashboards Grafana

**Exit Codes**:
- `0`: Sucesso (taxa ≥ 80%)
- `1`: Falha (taxa < 50%)
- `2`: Avisos (taxa entre 50-79%)

**Output**:
- `validation-reports/validation-run-YYYYMMDD_HHMMSS.log`
- `validation-reports/ci-report-YYYYMMDD_HHMMSS.json` (se --ci-mode)

---

### validate_models_loaded.sh

**Propósito**: Valida que os modelos ML foram carregados com sucesso em todos os especialistas

**Localização**: `ml_pipelines/training/validate_models_loaded.sh`

**Uso**:
```bash
# Validar modelos em namespace padrão
NAMESPACE=semantic-translation ./ml_pipelines/training/validate_models_loaded.sh

# Especificar MLflow URI customizado
MLFLOW_URI=http://mlflow:5000 ./ml_pipelines/training/validate_models_loaded.sh
```

**O que valida**:
1. Modelos registrados no MLflow (5 modelos: technical, business, behavior, evolution, architecture)
2. Versão Production de cada modelo
3. Status dos pods dos especialistas
4. Endpoint `/status` de cada pod (campos: `model_loaded`, `mlflow_connected`, `ledger_connected`)
5. Estado SERVING do especialista

**Diagnóstico**:
- Se `model_loaded = False`: Modelo não existe no MLflow ou não está em Production
- Se `mlflow_connected = False`: MLflow não está acessível
- Se `status != SERVING`: Especialista não está pronto para receber requisições

**Exit Code**: `0` se 5/5 especialistas carregaram modelos, `1` caso contrário

---

### validate-specialist-health.sh

**Propósito**: Validação abrangente de saúde dos especialistas (9 categorias)

**Uso**:
```bash
# Validação completa
./scripts/validation/validate-specialist-health.sh --namespace semantic-translation

# Pular testes de integração
./scripts/validation/validate-specialist-health.sh --skip-integration

# Modo verbose (inclui testes de inferência)
./scripts/validation/validate-specialist-health.sh --verbose
```

**Categorias de Validação**:
1. **Pod Status**: Deployment, replicas, pod phase, readiness
2. **Container Health**: Restart count, estado dos containers
3. **Logs Validation**: Erros críticos, conexões com MongoDB
4. **Endpoint Validation**: `/health`, `/ready`, `/metrics` (Prometheus), gRPC (50051)
5. **Dependency Connectivity**: MongoDB, Redis, Neo4j
6. **Resource Usage**: CPU, memória
7. **Configuration Validation**: Imagens, variáveis de ambiente
8. **Integration Testing**: (Opcional, customizável)
9. **🆕 Model & ML Pipeline Health**:
   - Model loaded status
   - MLflow connectivity
   - Serving status (SERVING/NOT_SERVING)
   - Degraded mode detection
   - Inference test (se --verbose)

**Output**:
- `logs/validation-YYYYMMDD-HHMMSS/VALIDATION_REPORT.md`
- Logs individuais por especialista
- Sumário com contadores (Passed, Failed, Warnings)

---

### test-specialist-inference.py

**Propósito**: Testa inferência real dos modelos via gRPC com planos cognitivos variados

**Uso**:
```bash
# Testar todos os especialistas
./scripts/validation/test-specialist-inference.py

# Testar apenas um especialista
./scripts/validation/test-specialist-inference.py --specialist technical

# Cenários específicos
./scripts/validation/test-specialist-inference.py --scenarios simple high_risk complex

# Verbose + JSON output
./scripts/validation/test-specialist-inference.py --verbose --output-json inference-report.json

# Namespace customizado
./scripts/validation/test-specialist-inference.py --namespace specialist-ns
```

**Cenários de Teste**:
1. **Simple**: Plano de baixo risco, aprovação esperada
2. **High Risk**: Plano de alto risco, rejeição/review esperado
3. **Complex**: Plano com múltiplas tarefas e dependências
4. **Malformed**: (Futuro) Plano malformado para teste de error handling

**Validação da Resposta**:
- ✅ `opinion_id` presente e não vazio
- ✅ `specialist_type` correto
- ✅ `confidence_score` no range [0.0-1.0]
- ✅ `risk_score` no range [0.0-1.0]
- ✅ `recommendation` em ['approve', 'reject', 'review_required', 'conditional']
- ✅ `reasoning_summary` não vazio
- ✅ `evaluated_at` timestamp válido
- ✅ `processing_time_ms` > 0

**Output JSON** (se `--output-json`):
```json
{
  "test_run_id": "uuid",
  "timestamp": "ISO-8601",
  "namespace": "semantic-translation",
  "results": [
    {
      "specialist_type": "technical",
      "scenarios": [
        {
          "scenario": "simple",
          "status": "passed",
          "response_time_ms": 245.67,
          "opinion": {
            "confidence_score": 0.87,
            "risk_score": 0.12,
            "recommendation": "approve"
          }
        }
      ],
      "summary": {"total": 3, "passed": 3, "failed": 0}
    }
  ],
  "overall_summary": {
    "total_tests": 15,
    "passed": 14,
    "failed": 1,
    "success_rate": 93.33
  }
}
```

---

### test-consensus-engine-e2e.py

**Propósito**: Teste end-to-end do Consensus Engine (Kafka → Especialistas → MongoDB → Redis)

**Status**: ⚠️ Parcialmente implementado (estrutura pronta, integração Kafka/MongoDB pendente)

**Uso**:
```bash
# Teste E2E com cenários padrão
./scripts/validation/test-consensus-engine-e2e.py

# Cenários customizados
./scripts/validation/test-consensus-engine-e2e.py --scenarios simple,high_risk

# Kafka/MongoDB customizados
./scripts/validation/test-consensus-engine-e2e.py \
  --kafka-bootstrap kafka:9092 \
  --mongodb-uri mongodb://mongo:27017 \
  --timeout 15
```

**Fluxo de Teste**:
1. Publica plano cognitivo no tópico `cognitive-plans` (Kafka)
2. Monitora tópico `consensus-decisions` para decisão
3. Valida que 5/5 especialistas foram invocados
4. Verifica decisão de consenso no MongoDB
5. Valida pheromone trails atualizados no Redis
6. Mede tempo de processamento fim-a-fim

**Exit Codes**:
- `0`: Todos os testes passaram
- `1`: Falhas detectadas
- `2`: Implementação pendente

---

### validate-prometheus-metrics.sh

**Propósito**: Valida coleta de métricas Prometheus e dashboards Grafana

**Uso**:
```bash
# Validação completa
./scripts/validation/validate-prometheus-metrics.sh

# URLs customizadas
./scripts/validation/validate-prometheus-metrics.sh \
  --prometheus-url http://prometheus:9090 \
  --grafana-url http://grafana:3000

# Namespace específico
./scripts/validation/validate-prometheus-metrics.sh --namespace specialist-ns
```

**Métricas Validadas**:
- `specialist_evaluations_total` (counter)
- `specialist_evaluation_duration_seconds` (histogram)
- `specialist_model_inference_duration_seconds` (histogram)
- `specialist_cache_hits_total` / `specialist_cache_misses_total`
- `specialist_errors_total` (por error_type)

**Validações**:
1. ✅ Prometheus está acessível (`/-/healthy`)
2. ✅ Métricas existem para todos os 5 especialistas
3. ✅ Freshness das métricas (última coleta < 2 minutos)
4. ✅ Grafana está acessível (`/api/health`)
5. ✅ Alerting rules configurados (specialist_down, model_not_loaded)

---

## Quick Start - Validação Completa

### Opção 1: Validação Rápida (5 minutos)

```bash
cd /jimy/Neural-Hive-Mind/scripts/validation

# Executar validação completa em modo quick (pula inferência E2E)
./validate-all-specialists.sh --quick
```

### Opção 2: Validação Completa (15 minutos)

```bash
cd /jimy/Neural-Hive-Mind/scripts/validation

# Executar todas as fases incluindo testes de inferência
./validate-all-specialists.sh --output-dir ./reports
```

### Opção 3: Validação Individual

```bash
# 1. Validar apenas modelos ML
NAMESPACE=semantic-translation ../../ml_pipelines/training/validate_models_loaded.sh

# 2. Validar apenas saúde dos specialists
./validate-specialist-health.sh --namespace semantic-translation --verbose

# 3. Testar apenas inferência
./test-specialist-inference.py --specialist technical --verbose

# 4. Validar apenas métricas
./validate-prometheus-metrics.sh
```

---

## Troubleshooting - Validação de Especialistas

### Problema: "Model not loaded" (model_loaded = False)

**Diagnóstico**:
```bash
# 1. Verificar se modelo existe no MLflow
curl -s http://mlflow:5000/api/2.0/mlflow/registered-models/get?name=technical-evaluator | jq

# 2. Verificar se está em Production
curl -s http://mlflow:5000/api/2.0/mlflow/registered-models/get?name=technical-evaluator \
  | jq '.registered_model.latest_versions[] | select(.current_stage == "Production")'

# 3. Verificar logs do specialist
kubectl logs -n semantic-translation -l app=specialist-technical --tail=50 | grep -i "model\|mlflow"
```

**Solução**:
- Se modelo não existe: Executar treinamento (`ml_pipelines/training/train_specialist_model.py`)
- Se não está em Production: Promover modelo no MLflow UI
- Se erro ao carregar: Verificar compatibilidade de versão (protobuf, mlflow, pandas)

---

### Problema: "Specialist timeout" durante inferência

**Diagnóstico**:
```bash
# 1. Verificar se pod está Ready
kubectl get pods -n semantic-translation -l app=specialist-technical

# 2. Testar endpoint gRPC manualmente
kubectl port-forward -n semantic-translation svc/specialist-technical 50051:50051 &
grpcurl -plaintext localhost:50051 neural_hive.specialist.SpecialistService/HealthCheck

# 3. Verificar logs de erro
kubectl logs -n semantic-translation -l app=specialist-technical --tail=100 | grep -i "error\|timeout\|exception"
```

**Solução**:
- Aumentar timeout no teste (`--timeout` parameter)
- Verificar recursos do pod (CPU/memória)
- Verificar circuit breakers abertos (`/status` endpoint)

---

### Problema: "Prometheus metrics not found"

**Diagnóstico**:
```bash
# 1. Verificar ServiceMonitor configurado
kubectl get servicemonitor -n semantic-translation

# 2. Verificar target no Prometheus
# Acessar Prometheus UI → Status → Targets → Buscar "specialist"

# 3. Testar endpoint /metrics diretamente
kubectl port-forward -n semantic-translation svc/specialist-technical 8000:8000 &
curl -s localhost:8000/metrics | grep specialist_
```

**Solução**:
- Criar ServiceMonitor se não existe
- Verificar labels do Service match com ServiceMonitor selector
- Aguardar intervalo de scrape (default: 30s)

---

## Scripts E2E Legados

Os scripts abaixo focam na validação do fluxo Gateway → Consensus → Memory Layer:

## Scripts Disponíveis

### 1. execute-e2e-validation-v1.0.9.sh

**Propósito**: Executar validação automatizada completa do pipeline

**Uso**:
```bash
./scripts/validation/execute-e2e-validation-v1.0.9.sh
```

**O que faz**:
1. Valida pré-requisitos (kubectl, jq, curl)
2. Executa 7 passos de validação:
   - Gateway health check
   - Envio de intent de teste
   - Verificação de logs do gateway
   - Verificação do Semantic Translation Engine
   - Verificação do Consensus Engine
   - Verificação dos 5 Specialists
   - Verificação de persistência MongoDB
   - Verificação da Memory Layer API
3. Coleta logs e métricas de todos os componentes
4. Gera artefatos em `logs/validation-e2e-v1.0.9-<timestamp>/`
5. Exibe resumo no terminal

**Output**:
- Diretório: `logs/validation-e2e-v1.0.9-<timestamp>/`
- Arquivos:
  - `validation.log` - Log consolidado
  - `correlation-ids.txt` - IDs para correlação
  - `01-gateway-health.json` - Health check
  - `02-gateway-response.json` - Response do intent
  - `03-gateway-logs.txt` - Logs do gateway
  - `04-semantic-logs.txt` - Logs do semantic translation
  - `05-consensus-logs.txt` - Logs do consensus engine
  - `06-specialist-*.txt` - Logs de cada specialist
  - `06.5-mongodb-persistence.txt` - Logs de persistência
  - `07-memory-*.json` - Responses da Memory Layer API
  - `SUMMARY.txt` - Resumo executivo

**Exit Codes**:
- `0` - Todos os passos passaram
- `1` - Algum passo falhou

---

### 2. generate-e2e-report-v1.0.9.sh

**Propósito**: Gerar relatório markdown estruturado a partir dos artefatos coletados

**Uso**:
```bash
./scripts/validation/generate-e2e-report-v1.0.9.sh <output_dir>
```

**Exemplo**:
```bash
./scripts/validation/generate-e2e-report-v1.0.9.sh logs/validation-e2e-v1.0.9-20251110-153000
```

**O que faz**:
1. Processa artefatos do diretório de input
2. Extrai métricas e evidências
3. Gera análise comparativa com v1.0.7
4. Cria relatório estruturado em markdown
5. Salva em `RELATORIO_VALIDACAO_E2E_POS_CORRECAO.md`

**Output**:
- Arquivo: `RELATORIO_VALIDACAO_E2E_POS_CORRECAO.md`
- Formato: Markdown estruturado com:
  - Sumário executivo
  - Análise passo a passo
  - Métricas comparativas
  - Evidências de logs
  - Conclusão e recomendações

---

## Fluxo de Trabalho Completo

### Passo 1: Preparar Ambiente

```bash
# Verificar conectividade com cluster
kubectl cluster-info

# Verificar pods estão rodando
kubectl get pods -A | grep -E "gateway|semantic|consensus|specialist|memory"

# Verificar versões das imagens (deve ser 1.0.9)
kubectl get pods -n default -o jsonpath='{.items[*].spec.containers[*].image}' | tr ' ' '\n' | grep -E 'consensus-engine|specialist'
```

### Passo 2: Executar Validação

```bash
cd /jimy/Neural-Hive-Mind
./scripts/validation/execute-e2e-validation-v1.0.9.sh
```

**Tempo estimado**: 2-3 minutos

### Passo 3: Gerar Relatório

```bash
# Usar o diretório de output exibido no passo anterior
OUTPUT_DIR="logs/validation-e2e-v1.0.9-<timestamp>"
./scripts/validation/generate-e2e-report-v1.0.9.sh $OUTPUT_DIR
```

**Tempo estimado**: 30 segundos

### Passo 4: Revisar Resultados

```bash
# Ver resumo
cat $OUTPUT_DIR/SUMMARY.txt

# Ver relatório completo
cat RELATORIO_VALIDACAO_E2E_POS_CORRECAO.md

# Ou abrir em editor markdown
code RELATORIO_VALIDACAO_E2E_POS_CORRECAO.md
```

---

## Critérios de Sucesso

### Validação v1.0.9 - Objetivos

1. ✅ **0 TypeErrors de timestamp**
   - Validações defensivas em `specialists_grpc_client.py` devem prevenir erros
   - Buscar nos logs: "TypeError", "AttributeError", "evaluated_at"
   - Esperado: 0 ocorrências

2. ✅ **5/5 specialists respondendo**
   - Todos os 5 specialists devem responder sem timeout
   - Buscar nos logs: "EvaluatePlan completed successfully"
   - Esperado: 5 ocorrências

3. ✅ **MongoDB persistence funcionando**
   - Decisão de consenso deve ser salva no ledger
   - Buscar nos logs: "Decisão salva no ledger" ou "save_consensus_decision"
   - Esperado: 1 ocorrência

4. ✅ **Memory Layer API operacional**
   - Dados devem ser recuperáveis via query
   - Verificar: HTTP 200 + dados completos no response
   - Esperado: Query bem-sucedida

5. ✅ **Pipeline E2E completo**
   - Todos os 7 passos devem passar
   - Taxa de sucesso: 100%
   - Esperado: 7/7 passos PASS

---

## Troubleshooting

### Problema: Script não encontra pods

**Sintoma**: "Nenhum pod encontrado para gateway-intencoes"

**Solução**:
```bash
# Verificar namespaces corretos
kubectl get pods -A | grep gateway

# Ajustar variável NAMESPACE no script se necessário
```

### Problema: Timeout ao enviar intent

**Sintoma**: "Timeout ao conectar ao gateway"

**Solução**:
```bash
# Verificar se gateway está rodando
kubectl get pods -n gateway-intencoes

# Verificar logs do gateway
kubectl logs -n gateway-intencoes -l app=gateway-intencoes --tail=50

# Tentar port-forward
kubectl port-forward -n gateway-intencoes svc/gateway-intencoes 8000:8000
```

### Problema: Specialists não respondem

**Sintoma**: "Pareceres insuficientes: 2/5"

**Solução**:
```bash
# Verificar se specialists estão rodando
kubectl get pods -A | grep specialist

# Verificar logs de um specialist
kubectl logs -n specialist-business -l app=specialist-business --tail=100

# Verificar conectividade gRPC
kubectl exec -n default consensus-engine-XXX -- nc -zv specialist-business.specialist-business.svc.cluster.local 50051
```

### Problema: Memory Layer API não retorna dados

**Sintoma**: "HTTP 404 - Intent not found"

**Solução**:
```bash
# Verificar se Memory Layer está rodando
kubectl get pods -n memory-layer-api

# Verificar readiness
kubectl exec -n memory-layer-api memory-layer-api-XXX -- curl -s http://localhost:8000/ready

# Verificar MongoDB está conectado
kubectl logs -n memory-layer-api -l app=memory-layer-api --tail=50 | grep -i mongodb

# Aguardar mais tempo (dados podem levar 30-60s para serem indexados)
sleep 60
```

---

## Comparação com Validação Anterior

### v1.0.7 (Baseline)

- **Taxa de Sucesso**: 62.5% (5/8 passos)
- **Bloqueio**: Timeout em 3/5 specialists
- **Specialists Response Rate**: 40% (2/5)
- **MongoDB**: ⏸️ Não testado
- **Memory Layer**: ⏸️ Não testado
- **TypeErrors**: N/A (problema não identificado ainda)

### v1.0.9 (Atual)

- **Taxa de Sucesso**: [A ser determinado]
- **Bloqueio**: [A ser determinado]
- **Specialists Response Rate**: [A ser determinado]
- **MongoDB**: [A ser testado]
- **Memory Layer**: [A ser testado]
- **TypeErrors**: 0 (esperado - validações defensivas implementadas)

**Objetivo**: Alcançar 100% de sucesso com 0 erros de timestamp

---

## Referências

- **Guia de Validação Manual**: `../../VALIDACAO_E2E_MANUAL.md`
- **Relatório Anterior**: `../../RELATORIO_VALIDACAO_E2E.md`
- **Análise de Debug**: `../../ANALISE_DEBUG_GRPC_TYPEERROR.md`
- **Correções v1.0.9**: `../../RELATORIO_SESSAO_CORRECAO_V1.0.9.md`
- **Código Relevante**:
  - `../../services/consensus-engine/src/clients/specialists_grpc_client.py`
  - `../../libraries/python/neural_hive_specialists/grpc_server.py`
  - `../../services/consensus-engine/src/consumers/plan_consumer.py`

---

**Última Atualização**: 2025-11-10
**Versão**: 1.0.0
**Autor**: Neural Hive-Mind Team
