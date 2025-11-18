# Gateway de Intenções - Guia de Tuning de Thresholds

## 1. Quick Start

### Ajuste Rápido para Reduzir Validação Manual

**Problema**: Taxa de validação manual muito alta (>15%)

**Solução rápida (dev/staging)**:

```bash
# Editar values override
helm upgrade gateway-intencoes ./helm-charts/gateway-intencoes \
  --set config.nlu.routingThresholdHigh=0.45 \
  --set config.nlu.routingThresholdLow=0.25 \
  -n neural-hive-gateway

# Aguardar rollout
kubectl rollout status deployment/gateway-intencoes -n neural-hive-gateway

# Monitorar impacto
kubectl logs -f deployment/gateway-intencoes -n neural-hive-gateway | grep "Routing decision"
```

**Validação**:

```bash
# Verificar taxa de validação manual (deve reduzir)
kubectl logs deployment/gateway-intencoes -n neural-hive-gateway --since=10m | \
  grep -c "routed_to_validation"

# Verificar taxa de processamento normal (deve aumentar)
kubectl logs deployment/gateway-intencoes -n neural-hive-gateway --since=10m | \
  grep -c '"status": "processed"'
```

## 2. Estratégias de Tuning

### Estratégia 1: Redução Gradual (Recomendada)

**Objetivo**: Reduzir validação manual mantendo precisão aceitável

**Passos**:

1. **Baseline**: Medir taxa atual de validação manual e precisão
2. **Reduzir** `routingThresholdLow` em 0.05 (ex: 0.3 → 0.25)
3. **Monitorar** por 24h
4. **Se precisão > 85%**, repetir passo 2
5. **Se precisão < 85%**, reverter e tentar reduzir `routingThresholdHigh` ao invés

**Exemplo**:

```yaml
# Iteração 1
routingThresholdHigh: 0.5
routingThresholdLow: 0.25  # Reduzido de 0.3

# Iteração 2 (se precisão OK)
routingThresholdHigh: 0.45  # Reduzido de 0.5
routingThresholdLow: 0.25

# Iteração 3 (se precisão OK)
routingThresholdHigh: 0.45
routingThresholdLow: 0.2  # Reduzido de 0.25
```

### Estratégia 2: Adaptive Threshold (Experimental)

**Objetivo**: Usar threshold dinâmico baseado em qualidade do texto

**Passos**:

1. Habilitar adaptive em dev: `routingUseAdaptiveForDecisions: true`
2. Monitorar distribuição de adaptive thresholds calculados
3. Se comportamento estável, habilitar em staging
4. Validar por 1 semana antes de considerar prod

**Prós**:
- Mais inteligente: textos ricos têm threshold menor
- Reduz validação manual sem sacrificar precisão

**Contras**:
- Menos previsível
- Mais difícil de auditar
- Não recomendado para prod (ainda)

## 3. Monitoramento e Alertas

### Métricas Chave

**Taxa de Validação Manual**:

```promql
sum(rate(low_confidence_routed_counter[5m])) /
sum(rate(intent_counter[5m])) * 100
```

Target: < 10% | Warning: > 15% | Critical: > 25%

**Distribuição de Confidence**:

```promql
histogram_quantile(0.5, confidence_histogram)  # Mediana
histogram_quantile(0.95, confidence_histogram)  # P95
```

Target mediana: > 0.6 | Warning: < 0.5

### Alertas Recomendados

```yaml
# Alert 1: Alta Taxa de Validação Manual
alert: HighManualValidationRate
expr: |
  sum(rate(low_confidence_routed_counter[10m])) /
  sum(rate(intent_counter[10m])) > 0.20
for: 15m
annotations:
  summary: "Taxa de validação manual acima de 20%"
  description: "Considere reduzir routing thresholds"

# Alert 2: Confidence Muito Baixa
alert: LowConfidenceMedian
expr: histogram_quantile(0.5, confidence_histogram) < 0.4
for: 30m
annotations:
  summary: "Mediana de confidence abaixo de 0.4"
  description: "Possível problema com modelo NLU ou qualidade de dados"
```

## 4. Rollback Procedures

### Rollback Rápido

```bash
# Reverter para versão anterior
helm rollback gateway-intencoes -n neural-hive-gateway

# Ou reverter apenas thresholds
helm upgrade gateway-intencoes ./helm-charts/gateway-intencoes \
  --set config.nlu.routingThresholdHigh=0.5 \
  --set config.nlu.routingThresholdLow=0.3 \
  --reuse-values \
  -n neural-hive-gateway
```

### Critérios para Rollback

**Rollback imediato se**:
- Taxa de erros de classificação > 20%
- Latência p95 > 500ms (aumento de 2x)
- Taxa de reprocessamento > 10%

**Rollback planejado se**:
- Precisão < 85% após 24h
- Feedback negativo de usuários > 15%
- Volume de validação manual não reduziu significativamente (<5%)

## 5. Best Practices

### DO's

✅ **Testar em dev/staging antes de prod**
✅ **Monitorar métricas por 24-48h após mudança**
✅ **Documentar mudanças e resultados**
✅ **Fazer mudanças incrementais (0.05 por vez)**
✅ **Validar precisão com amostragem manual**
✅ **Ter plano de rollback pronto**

### DON'Ts

❌ **Não reduzir thresholds drasticamente (>0.1) de uma vez**
❌ **Não mudar thresholds em prod sem testar em staging**
❌ **Não ignorar alertas de baixa precisão**
❌ **Não habilitar adaptive em prod sem validação extensa**
❌ **Não fazer mudanças durante horário de pico**
❌ **Não esquecer de documentar configuração atual antes de mudar**

## 6. Referências

- **Decision Matrix**: `docs/GATEWAY_ROUTING_DECISION_MATRIX.md`
- **Configuration**: `helm-charts/gateway-intencoes/values.yaml`
- **Code**: `services/gateway-intencoes/src/main.py` (routing logic)
- **NLU Pipeline**: `services/gateway-intencoes/src/pipelines/nlu_pipeline.py`
