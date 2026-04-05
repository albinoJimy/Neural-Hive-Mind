# Feature Flags - Runbook de Operação

Guia passo a passo para operações comuns de Feature Flags.

## Sumário Executivo

Este runbook documenta procedimentos padrão para gestão de Feature Flags Dinâmicas no Neural-Hive-Mind.

## Emergências

### Feature causando problemas em produção

**Sintoma:** Feature está causando erros, lentidão ou comportamento indesejado.

**Severidade:** Crítica

**Passos:**

1. **Identificar a flag problemática**
   ```bash
   # Listar flags ativas recentemente
   kubectl logs -n neural-hive-orchestration deployment/feature-flag-service | grep "feature_flag"
   ```

2. **Rollback imediato (Opção 1 - Toggle)**
   ```bash
   # Desabilitar flag rapidamente
   curl -X POST \
     http://feature-flag-service:8080/api/v1/feature-flags/NOME_DA_FLAG/toggle \
     -H "Content-Type: application/json"
   ```

3. **Rollback imediato (Opção 2 - Update)**
   ```bash
   # Definir enabled=false explicitamente
   curl -X PUT \
     http://feature-flag-service:8080/api/v1/feature-flags/NOME_DA_FLAG \
     -H "Content-Type: application/json" \
     -d '{"enabled": false}'
   ```

4. **Verificar desabilitação**
   ```bash
   curl http://feature-flag-service:8080/api/v1/feature-flags/NOME_DA_FLAG
   ```

5. **Invalidar cache Redis (se necessário)**
   ```bash
   redis-cli -h redis-cluster DEL "feature_flag:NOME_DA_FLAG"
   ```

6. **Monitorar estabilização**
   ```bash
   # Verificar métricas de erro
   kubectl port-forward -n monitoring svc/prometheus 9090:9090
   # Abrir http://localhost:9090 e verificar taxa de erros
   ```

**Tempo estimado:** 2-5 minutos

### Cache desatualizado causando comportamento inconsistente

**Sintoma:** Flag foi atualizada mas comportamento antigo continua.

**Severidade:** Alta

**Passos:**

1. **Verificar configuração atual**
   ```bash
   curl http://feature-flag-service:8080/api/v1/feature-flags/NOME_DA_FLAG
   ```

2. **Invalidar cache Redis**
   ```bash
   redis-cli -h redis-cluster --scan --pattern "feature_flag:*" | \
     xargs redis-cli -h redis-cluster DEL
   ```

3. **Ou invalidar flag específica**
   ```bash
   redis-cli -h redis-cluster DEL "feature_flag:NOME_DA_FLAG"
   ```

4. **Verificar que nova configuração está ativa**
   ```bash
   curl -X POST \
     http://feature-flag-service:8080/api/v1/feature-flags/NOME_DA_FLAG/evaluate \
     -H "Content-Type: application/json" \
     -d '{"tenant_id": "test-tenant", "namespace": "staging"}'
   ```

**Tempo estimado:** 1-2 minutos

## Operações Rotineiras

### Criar Nova Feature Flag

**Quando:** Nova feature precisa ser lançada com controle de rollout.

**Passos:**

1. **Definir configuração da flag**
   ```bash
   cat > new_flag.json << EOF
   {
     "flag_name": "enable_new_feature",
     "description": "Descrição clara do propósito da feature",
     "enabled": false,
     "rollout_strategy": "gradual",
     "rollout_config": {
       "percentage": 10,
       "namespaces": ["staging"]
     },
     "created_by": "seu-nome",
     "owner": "time-responsavel",
     "tags": ["categoria", "feature"]
   }
   EOF
   ```

2. **Criar flag**
   ```bash
   curl -X POST \
     http://feature-flag-service:8080/api/v1/feature-flags \
     -H "Content-Type: application/json" \
     -d @new_flag.json
   ```

3. **Testar avaliação**
   ```bash
   curl -X POST \
     http://feature-flag-service:8080/api/v1/feature-flags/enable_new_feature/evaluate \
     -H "Content-Type: application/json" \
     -d '{"tenant_id": "test-tenant", "namespace": "staging"}'
   ```

4. **Verificar que flag foi criada**
   ```bash
   curl http://feature-flag-service:8080/api/v1/feature-flags/enable_new_feature
   ```

5. **Habilitar quando pronto**
   ```bash
   curl -X POST \
     http://feature-flag-service:8080/api/v1/feature-flags/enable_new_feature/toggle
   ```

**Tempo estimado:** 5-10 minutos

### Atualizar Configuração de Feature Flag

**Quando:** Alterar estratégia de rollout, porcentagem ou condições.

**Passos:**

1. **Obter configuração atual**
   ```bash
   curl -s http://feature-flag-service:8080/api/v1/feature-flags/NOME_DA_FLAG > current_flag.json
   ```

2. **Editar configuração**
   ```bash
   # Editar current_flag.json com as mudanças desejadas
   vi current_flag.json
   ```

3. **Aplicar atualização**
   ```bash
   curl -X PUT \
     http://feature-flag-service:8080/api/v1/feature-flags/NOME_DA_FLAG \
     -H "Content-Type: application/json" \
     -d @current_flag.json
   ```

4. **Verificar atualização**
   ```bash
   curl http://feature-flag-service:8080/api/v1/feature-flags/NOME_DA_FLAG
   ```

**Tempo estimado:** 3-5 minutos

### Aumentar Rollout Gradualmente

**Quando:** Feature está estável e pronta para mais tráfego.

**Passos:**

1. **Verificar rollout atual**
   ```bash
   curl -s http://feature-flag-service:8080/api/v1/feature-flags/NOME_DA_FLAG | \
     jq '.rollout_config'
   ```

2. **Aumentar porcentagem**
   ```bash
   # De 10% para 25%
   curl -X PUT \
     http://feature-flag-service:8080/api/v1/feature-flags/NOME_DA_FLAG \
     -H "Content-Type: application/json" \
     -d '{"rollout_config": {"percentage": 25}}'
   ```

3. **Monitorar métricas**
   ```bash
   # Verificar taxa de erros
   kubectl exec -n monitoring prometheus-0 -- promtool-query \
     'rate(http_requests_total{status="5m"}[5m])'
   ```

4. **Repetir gradualmente** (25% → 50% → 75% → 100%)

**Tempo estimado:** Por fase (monitorar 15-30 minutos entre fases)

### Remover Feature Flag

**Quando:** Feature não é mais necessária ou foi completamente integrada.

**Passos:**

1. **Verificar se flag ainda está em uso**
   ```bash
   # Consultar codebase por referências à flag
   git grep "NOME_DA_FLAG"
   ```

2. **Se em uso, remover código dependente**
   - Criar PR para remover dependências
   - Code review e testes
   - Merge e deploy

3. **Deletar flag**
   ```bash
   curl -X DELETE \
     http://feature-flag-service:8080/api/v1/feature-flags/NOME_DA_FLAG
   ```

4. **Limpar cache**
   ```bash
   redis-cli -h redis-cluster DEL "feature_flag:NOME_DA_FLAG"
   ```

5. **Documentar remoção**
   - Atualizar documentação
   - Comentar em changelog

**Tempo estimado:** 30-60 minutos (incluindo remoção de código)

## Diagnóstico

### Investigar Flag Não Funcionando

**Sintoma:** Flag deveria estar ativa mas retorna desativada.

**Passos:**

1. **Verificar estado da flag**
   ```bash
   curl -s http://feature-flag-service:8080/api/v1/feature-flags/NOME_DA_FLAG | jq '.enabled'
   ```

2. **Verificar rollout strategy**
   ```bash
   curl -s http://feature-flag-service:8080/api/v1/feature-flags/NOME_DA_FLAG | jq '.rollout_strategy'
   ```

3. **Testar com diferentes contextos**
   ```bash
   # Com namespace correto
   curl -X POST \
     http://feature-flag-service:8080/api/v1/feature-flags/NOME_DA_FLAG/evaluate \
     -H "Content-Type: application/json" \
     -d '{"tenant_id": "test", "namespace": "staging"}'

   # Sem namespace
   curl -X POST \
     http://feature-flag-service:8080/api/v1/feature-flags/NOME_DA_FLAG/evaluate \
     -H "Content-Type: application/json" \
     -d '{"tenant_id": "test"}'
   ```

4. **Verificar cache**
   ```bash
   redis-cli -h redis-cluster GET "feature_flag:NOME_DA_FLAG"
   ```

5. **Verificar logs do serviço**
   ```bash
   kubectl logs -n neural-hive-orchestration deployment/feature-flag-service --tail=100
   ```

### Alta Latência de Avaliação

**Sintoma:** Avaliações de flag estão lentas (> 100ms).

**Passos:**

1. **Verificar hit ratio do cache**
   ```bash
   # Query Prometheus
   rate(feature_flag_cache_hits_total[5m]) /
   (rate(feature_flag_cache_hits_total[5m]) + rate(feature_flag_cache_misses_total[5m]))
   ```

2. **Se hit ratio baixo (< 90%):**
   - Verificar se TTL está muito curto
   - Verificar se flags estão sendo atualizadas com muita frequência
   - Considerar aumentar TTL

3. **Verificar latência do Redis**
   ```bash
   kubectl exec -n neural-hive-orchestration redis-0 -- redis-cli PING
   kubectl exec -n neural-hive-orchestration redis-0 -- redis-cli LATENCY
   ```

4. **Verificar latência do MongoDB** (se cache miss)
   ```bash
   kubectl exec -n neural-hive-orchestration mongodb-0 -- \
     mongo --eval "db.feature_flags.stats()"
   ```

### Muitas Flags Zombies

**Sintoma:** Flags antigas não utilizadas acumulando no sistema.

**Passos:**

1. **Listar todas as flags**
   ```bash
   curl -s http://feature-flag-service:8080/api/v1/feature-flags | \
     jq -r '.[] | select(.enabled == false) | .flag_name'
   ```

2. **Identificar flags não usadas** (filtrar por data de atualização)
   ```bash
   curl -s http://feature-flag-service:8080/api/v1/feature-flags | \
     jq -r '.[] | select(.updated_at < "2024-01-01") | .flag_name'
   ```

3. **Consultar time responsável** antes de deletar

4. **Criar processo de limpeza periódica** (recomendado: mensal)

## Comandos Úteis

### kubectl

```bash
# Port forward para serviço local
kubectl port-forward -n neural-hive-orchestration svc/feature-flag-service 8080:8080

# Logs do serviço
kubectl logs -n neural-hive-orchestration deployment/feature-flag-service -f

# Executar pod interativo
kubectl exec -it -n neural-hive-orchestration deployment/feature-flag-service -- /bin/sh
```

### redis-cli

```bash
# Ver todas as flags no cache
redis-cli -h redis-cluster --scan --pattern "feature_flag:*"

# Ver flag específica
redis-cli -h redis-cluster GET "feature_flag:NOME_DA_FLAG"

# Limpar cache específico
redis-cli -h redis-cluster DEL "feature_flag:NOME_DA_FLAG"

# Limpar todo o cache
redis-cli -h redis-cluster --scan --pattern "feature_flag:*" | \
  xargs redis-cli -h redis-cluster DEL
```

### curl

```bash
# Listar todas as flags (formatado)
curl -s http://feature-flag-service:8080/api/v1/feature-flags | jq

# Avaliar flag
curl -X POST \
  http://feature-flag-service:8080/api/v1/feature-flags/NOME_DA_FLAG/evaluate \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "test"}' | jq

# Toggle flag
curl -X POST \
  http://feature-flag-service:8080/api/v1/feature-flags/NOME_DA_FLAG/toggle | jq
```

## Alertas e Monitoramento

### Alertas Recomendados

**Latência Alta (P95 > 100ms):**
```promql
histogram_quantile(0.95, rate(feature_flag_evaluation_duration_seconds_bucket[5m])) > 0.1
```

**Cache Hit Ratio Baixo (< 80%):**
```promql
rate(feature_flag_cache_hits_total[5m]) /
(rate(feature_flag_cache_hits_total[5m]) + rate(feature_flag_cache_misses_total[5m])) < 0.8
```

**Error Rate Alto (> 1%):**
```promql
rate(feature_flag_evaluations_total{result="error"}[5m]) /
rate(feature_flag_evaluations_total[5m]) > 0.01
```

### Dashboards Grafana

1. **Feature Flags Overview**
   - Flags ativas por status
   - Distribuição por rollout strategy
   - Toggle count (últimas 24h)

2. **Performance**
   - Latência de avaliação (P50, P95, P99)
   - Cache hit ratio
   - Requests por segundo

3. **Usage**
   - Top flags mais avaliadas
   - Flags por owner
   - Taxa de habilitação

## Contingência

### Serviço Indisponível

**Se Feature Flag Service está indisponível:**

1. **Fallback para valores default** (configurado no código)
2. **OPA usa última configuração conhecida** (cache bundle)
3. **Serviços continuam operando** com configuração fallback

### Redis Indisponível

**Comportamento:**
- Cache miss para todas as requisições
- Serviço busca diretamente do MongoDB
- Maior latência mas funcional

**Mitigação:**
- Verificar status do Redis cluster
- Reiniciar serviço se necessário
- Considerar aumentar réplicas do Redis

## Procedimentos de Manutenção

### Limpeza Mensal de Flags

1. **Gerar relatório de flags não utilizadas**
2. **Confirmar com owners**
3. **Deletar flags aprovadas**
4. **Documentar limpeza**

### Backup de Configurações

```bash
# Exportar todas as flags
curl -s http://feature-flag-service:8080/api/v1/feature-flags > flags_backup_$(date +%Y%m%d).json
```

### Atualização de Serviço

```bash
# Rollout sem downtime
kubectl rollout restart deployment/feature-flag-service -n neural-hive-orchestration

# Verificar status
kubectl rollout status deployment/feature-flag-service -n neural-hive-orchestration
```

## Referências

- [Feature Flags Dynamic Guide](./FEATURE_FLAGS_DYNAMIC_GUIDE.md)
- [Feature Flags Original Guide](./FEATURE_FLAGS_GUIDE.md)
- [OpenAPI Spec](http://feature-flag-service:8080/docs)
- [Prometheus Metrics](http://feature-flag-service:8080/metrics)
