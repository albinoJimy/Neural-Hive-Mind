# Scripts de Validação E2E - Neural Hive-Mind

Este diretório contém scripts para validação end-to-end do pipeline Neural Hive-Mind.

## Visão Geral

A validação E2E verifica o fluxo completo de processamento de intenções:

```
Gateway → Semantic Translation → Consensus Engine → Specialists → MongoDB → Memory Layer API
```

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
