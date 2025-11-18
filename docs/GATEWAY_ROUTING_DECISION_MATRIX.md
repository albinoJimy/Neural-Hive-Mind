# Gateway de Intenções - Matriz de Decisão de Roteamento

## 1. Visão Geral

Este documento descreve como o Gateway de Intenções roteia intents baseado em scores de confiança (confidence). O sistema usa thresholds configuráveis para decidir se uma intent deve ser processada normalmente, processada com baixa confiança, ou roteada para validação manual.

### Propósito do Confidence-Based Routing

- **Precisão**: Garantir que intents com alta confiança sejam processadas automaticamente
- **Segurança**: Rotear intents incertas para revisão humana
- **Eficiência**: Minimizar volume de validação manual sem sacrificar qualidade

### Diferença entre Análise NLU e Decisão de Roteamento

- **Análise NLU** (`nlu_pipeline.py`): Classifica domínio, extrai entidades, calcula confidence
- **Decisão de Roteamento** (`main.py`): Usa thresholds para decidir qual tópico Kafka enviar

### Fluxo de Processamento

```
Texto de Entrada
      ↓
  NLU Pipeline
      ↓
  Classificação (domínio, confidence)
      ↓
  Decisão de Roteamento (baseada em thresholds)
      ↓
  Kafka Topic (intentions.captured ou intentions.validation)
```

## 2. Matriz de Decisão de Roteamento

### Tabela de Decisão

| Confidence Range | Status | Kafka Topic | Requires Validation | Descrição |
|-----------------|--------|-------------|---------------------|------------|
| >= `routingThresholdHigh` (0.5) | `processed` | `intentions.captured` | false | Processamento normal - alta/média confiança |
| `routingThresholdLow` (0.3) - `routingThresholdHigh` (0.5) | `processed_low_confidence` | `intentions.captured` | true | Processado mas marcado para revisão posterior |
| < `routingThresholdLow` (0.3) | `routed_to_validation` | `intentions.validation` | true | Roteado para validação manual imediata |

### Fluxograma de Decisão

```
Intent Received
      |
      v
  NLU Processing
      |
      v
  Calculate Confidence
      |
      v
  confidence >= routingThresholdHigh?
      |
      +-- YES --> processed --> intentions.captured
      |
      +-- NO --> confidence >= routingThresholdLow?
                    |
                    +-- YES --> processed_low_confidence --> intentions.captured (flagged)
                    |
                    +-- NO --> routed_to_validation --> intentions.validation
```

### Exemplo Prático

**Cenário**: Intent com confidence 0.45

**Thresholds Configurados**:
- `routingThresholdHigh` = 0.5
- `routingThresholdLow` = 0.3

**Decisão**:
1. 0.45 >= 0.5? ❌ NÃO
2. 0.45 >= 0.3? ✅ SIM
3. **Resultado**: `processed_low_confidence` → `intentions.captured` (com flag de validação)

**Com Thresholds Ajustados** (0.4, 0.2):
1. 0.45 >= 0.4? ✅ SIM
2. **Resultado**: `processed` → `intentions.captured` (processamento normal)

## 3. Configuração de Thresholds

### Parâmetros Configuráveis

#### `nlu_routing_threshold_high` (default: 0.5)

**Descrição**: Threshold mínimo para processamento normal

**Valores Típicos**:
- Dev: 0.4 (mais permissivo)
- Staging: 0.5 (balanceado)
- Prod: 0.6 (mais conservador)

**Impacto de Reduzir**:
- ✅ Mais intents processadas automaticamente
- ⚠️ Maior risco de classificação incorreta

**Impacto de Aumentar**:
- ✅ Maior precisão de classificação
- ⚠️ Mais intents vão para low confidence ou validação manual

#### `nlu_routing_threshold_low` (default: 0.3)

**Descrição**: Threshold mínimo para processamento com baixa confiança

**Valores Típicos**:
- Dev: 0.2 (mais permissivo)
- Staging: 0.3 (balanceado)
- Prod: 0.35 (mais conservador)

**Impacto de Reduzir**:
- ✅ Menos intents roteadas para validação manual
- ⚠️ Mais intents processadas com flag (possível aumento de erros)

**Impacto de Aumentar**:
- ✅ Maior qualidade de intents processadas
- ⚠️ Mais volume de validação manual

#### `nlu_routing_use_adaptive_for_decisions` (default: false)

**Descrição**: Se habilitado, usa adaptive threshold calculado pelo NLU ao invés de threshold fixo

**Como Funciona**: Adaptive threshold ajusta dinamicamente baseado em:
- Tamanho do texto (textos maiores = threshold menor)
- Número de entidades (mais entidades = threshold menor)
- Contexto do usuário (contexto rico = threshold menor)

**Recomendação**:
- ✅ Dev/Staging: true (para testes)
- ⚠️ Prod: false (previsibilidade)

### Configuração por Ambiente

#### Development

```yaml
routingThresholdHigh: 0.4  # Permissivo
routingThresholdLow: 0.2
routingUseAdaptiveForDecisions: true
```

**Objetivo**: Facilitar testes, reduzir fricção
**Trade-off**: Aceitar menor precisão em troca de velocidade

#### Staging

```yaml
routingThresholdHigh: 0.5  # Balanceado
routingThresholdLow: 0.3
routingUseAdaptiveForDecisions: false
```

**Objetivo**: Simular produção, validar comportamento
**Trade-off**: Balancear precisão e volume de validação manual

#### Production

```yaml
routingThresholdHigh: 0.6  # Conservador
routingThresholdLow: 0.35
routingUseAdaptiveForDecisions: false
```

**Objetivo**: Maximizar precisão, minimizar erros
**Trade-off**: Mais validação manual, menos erros de classificação

## 4. Adaptive Threshold

### Como Funciona

O adaptive threshold ajusta dinamicamente o threshold base considerando:

#### 1. Tamanho do texto

**Código**: `nlu_pipeline.py` linhas 571-575

```python
word_count = len(text.split())
if word_count > 20:
    adjustments.append(-0.10)  # Reduzir threshold em 0.10
elif word_count > 10:
    adjustments.append(-0.05)  # Reduzir threshold em 0.05
```

**Justificativa**: Textos maiores fornecem mais contexto, aumentando confiabilidade

#### 2. Presença de entidades

**Código**: `nlu_pipeline.py` linhas 577-581

```python
if len(entities) >= 3:
    adjustments.append(-0.10)
elif len(entities) >= 1:
    adjustments.append(-0.05)
```

**Justificativa**: Entidades aumentam confiança na classificação

#### 3. Contexto rico

**Código**: `nlu_pipeline.py` linhas 583-587

```python
if context:
    context_fields = sum(1 for v in context.values() if v is not None and v != "")
    if context_fields >= 3:
        adjustments.append(-0.05)
```

**Justificativa**: Contexto do usuário melhora precisão

### Exemplo de Cálculo

```
Base threshold: 0.5
Texto: 25 palavras → -0.10
Entidades: 2 → -0.05
Contexto: 4 campos → -0.05
---
Adaptive threshold: 0.5 - 0.10 - 0.05 - 0.05 = 0.30
```

**Intent com confidence 0.35**:
- Com threshold fixo (0.5): `processed_low_confidence`
- Com adaptive threshold (0.30): `processed` (normal)

### Quando Usar Adaptive Threshold

**✅ Usar quando**:
- Ambiente dev/staging para testes
- Textos muito variados em tamanho
- Contexto de usuário disponível

**❌ Evitar quando**:
- Ambiente produção (previsibilidade)
- Auditoria rigorosa necessária
- SLAs estritamente definidos

## 5. Métricas e Observabilidade

### Métricas Prometheus

#### Taxa de intents por status de roteamento

```promql
rate(intent_counter{status="processed"}[5m])
rate(intent_counter{status="processed_low_confidence"}[5m])
rate(intent_counter{status="routed_to_validation"}[5m])
```

#### Distribuição de confidence

```promql
histogram_quantile(0.5, confidence_histogram)  # Mediana
histogram_quantile(0.95, confidence_histogram)  # P95
```

#### Taxa de validação manual

```promql
sum(rate(low_confidence_routed_counter[5m])) /
sum(rate(intent_counter[5m])) * 100
```

### Logs Estruturados

Exemplo de log de decisão de roteamento:

```json
{
  "message": "⚡ Routing decision",
  "confidence": 0.45,
  "threshold_high": 0.5,
  "threshold_low": 0.3,
  "adaptive_enabled": false,
  "decision": "processed_low_confidence",
  "intent_id": "uuid",
  "domain": "TECHNICAL"
}
```

### Dashboards Recomendados

#### 1. Routing Decision Distribution

**Tipo**: Pie Chart
**Métrica**: `intent_counter` groupby `status`
**Objetivo**: Visualizar distribuição de decisões de roteamento

#### 2. Confidence Distribution

**Tipo**: Histogram
**Métrica**: `confidence_histogram`
**Objetivo**: Entender distribuição de confidence scores

#### 3. Validation Queue Size

**Tipo**: Gauge
**Métrica**: Kafka consumer lag em `intentions.validation`
**Objetivo**: Monitorar fila de validação manual

#### 4. Threshold Effectiveness

**Tipo**: Time Series
**Métrica**: Taxa de sucesso por faixa de confidence
**Objetivo**: Validar se thresholds estão calibrados

## 6. Testes A/B

### Procedimento para Ajuste de Thresholds

#### Fase 1: Baseline (1 semana)

1. Coletar métricas com thresholds atuais (0.5, 0.3)
2. Medir:
   - Taxa de validação manual
   - Taxa de erros de classificação
   - Latência de processamento
3. Estabelecer baselines de qualidade

#### Fase 2: Teste A/B (2 semanas)

1. Dividir tráfego:
   - **Grupo A** (50%): thresholds atuais (0.5, 0.3)
   - **Grupo B** (50%): thresholds reduzidos (0.45, 0.25)
2. Comparar métricas:
   - Volume de validação manual
   - Precisão de classificação
   - Satisfação do usuário
3. Monitorar alertas e incidentes

#### Fase 3: Análise e Decisão

**Critérios de Sucesso** (Grupo B vs Grupo A):
- Precisão aceitável (>90%)
- Redução de validação manual (>20%)
- Latência similar (< 10% diferença)
- Sem aumento de incidentes

**Decisão**:
- Se Grupo B atende critérios: Adotar novos thresholds
- Se Grupo B não atende: Manter thresholds atuais ou testar valores intermediários

### Métricas de Sucesso

| Métrica | Target | Alerta | Crítico |
|---------|--------|--------|---------|
| Taxa de validação manual | < 10% | > 15% | > 25% |
| Precisão de classificação | > 90% | < 85% | < 80% |
| Latência p95 | < 200ms | > 300ms | > 500ms |
| Taxa de reprocessamento | < 5% | > 10% | > 15% |

## 7. Troubleshooting

### Problema: Taxa de validação manual muito alta (>20%)

#### Diagnóstico

```bash
# Verificar distribuição de confidence
kubectl logs -n neural-hive-gateway <pod> | \
  grep "confidence=" | \
  awk '{print $5}' | \
  sort | uniq -c

# Verificar thresholds configurados
kubectl exec -n neural-hive-gateway <pod> -- env | grep ROUTING_THRESHOLD
```

#### Soluções

1. **Reduzir `routingThresholdLow`** (ex: 0.3 → 0.25)
2. **Habilitar `routingUseAdaptiveForDecisions`**
3. **Melhorar regras de classificação NLU** (adicionar keywords, patterns)
4. **Treinar modelo NLU com mais dados**

### Problema: Muitos erros de classificação

#### Diagnóstico

```bash
# Analisar intents com baixa confidence que foram processadas
kubectl logs -n neural-hive-gateway <pod> | \
  grep "processed_low_confidence"
```

#### Soluções

1. **Aumentar `routingThresholdHigh`** (ex: 0.5 → 0.6)
2. **Desabilitar `routingUseAdaptiveForDecisions`** em prod
3. **Revisar e melhorar regras de classificação**
4. **Adicionar validação humana para confidence 0.4-0.6**

### Problema: Adaptive threshold não está funcionando

#### Diagnóstico

```bash
# Verificar se adaptive está habilitado
kubectl exec -n neural-hive-gateway <pod> -- env | grep ADAPTIVE

# Verificar logs de cálculo de adaptive threshold
kubectl logs -n neural-hive-gateway <pod> | \
  grep "adaptive_threshold"
```

#### Soluções

1. Verificar `nlu_adaptive_threshold_enabled: true` em values.yaml
2. Verificar `routingUseAdaptiveForDecisions: true` se quiser usar para roteamento
3. Verificar se `NLUResult.adaptive_threshold` está sendo populado

## 8. Referências

### Código

- **Routing Logic**: `services/gateway-intencoes/src/main.py` linhas 699-761 (texto), 971-1043 (voz)
- **Configuração**: `services/gateway-intencoes/src/config/settings.py` linhas 46-62
- **NLU Pipeline**: `services/gateway-intencoes/src/pipelines/nlu_pipeline.py` linhas 276-310
- **Adaptive Threshold**: `nlu_pipeline.py` linhas 562-593

### Helm Charts

- **Values**: `helm-charts/gateway-intencoes/values.yaml` linhas 175-192
- **Deployment**: `helm-charts/gateway-intencoes/templates/deployment.yaml` linhas 351-357
- **ConfigMap**: `helm-charts/gateway-intencoes/templates/configmap.yaml` linhas 75-78

### Documentação Externa

- Confidence-based routing patterns: https://martinfowler.com/articles/patterns-of-distributed-systems/
- A/B testing best practices: https://www.optimizely.com/optimization-glossary/ab-testing/
- Threshold calibration: https://en.wikipedia.org/wiki/Calibration_(statistics)
