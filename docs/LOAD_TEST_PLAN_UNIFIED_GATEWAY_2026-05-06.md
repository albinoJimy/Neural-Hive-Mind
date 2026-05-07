# Plano de Load Testing - Unified Gateway

**Data:** 2026-05-06
**Status:** ⏳ Teste criado, agendando execução
**Ticket:** TICKET-029

---

## 1. Load Test Script

**Localização:** `tests/performance/unified-gateway-load-test.py`

**Características:**
- 730 linhas de código
- Teste de ramp-up gradual
- Validação de requisitos da spec (<20ms p95, >200 req/s)
- Teste de rate limiting
- Métricas completas (latência P50/P90/P95/P99)

### Uso

```bash
# Teste básico (local)
python tests/performance/unified-gateway-load-test.py \
  --url http://localhost:7999 \
  --requests 1000 \
  --concurrent 50 \
  --ramp-up 60

# Teste completo (staging)
python tests/performance/unified-gateway-load-test.py \
  --url https://unified-gateway.staging.example.com \
  --token $AUTH_TOKEN \
  --requests 5000 \
  --concurrent 100 \
  --ramp-up 120 \
  --target-throughput 200 \
  --max-p95-latency 20.0 \
  --output results.json

# Teste de rate limiting
python tests/performance/unified-gateway-load-test.py \
  --url http://localhost:7999 \
  --test-rate-limit \
  --tenant-id test_tenant \
  --user-id test_user \
  --expected-rate-limit 1000
```

---

## 2. Requisitos de Performance (Spec)

| Métrica | Target | Status |
|---------|--------|--------|
| **Latência adicional P95** | <20ms | ⏳ A medir |
| **Throughput** | >200 req/s | ⏳ A medir |
| **Taxa de sucesso** | >99% | ⏳ A medir |
| **Rate limiting** | Funcional | ⏳ A testar |

---

## 3. Status do Ambiente

### Kubernetes (Staging)

```
NAME                               READY   STATUS    RESTARTS   AGE
unified-gateway-5f9897594-xfkfv    0/1     Pending   0          17h
unified-gateway-756c49f498-shgrl   0/1     Pending   0          16h
```

**Problema:** `0/5 nodes are available: 5 Insufficient cpu`

**Ação necessária:** Escalar cluster K8s ou limpar pods não utilizados

### Local

**Docker Compose:** `docker-compose-test.yml` não inclui Unified Gateway

**Ação necessária:** Adicionar serviço Unified Gateway ao docker-compose-test.yml

---

## 4. Passos para Execução

### Opção A: Corrigir K8s Staging

1. Verificar uso de recursos:
   ```bash
   kubectl top nodes
   kubectl top pods -A
   ```

2. Escalar cluster ou remover pods não essenciais

3. Aguardar pods Unified Gateway ficarem Ready

4. Port-forward para teste local:
   ```bash
   kubectl port-forward -n gateway svc/unified-gateway 7999:7999
   ```

5. Executar load test

### Opção B: Criar Ambiente Local com Docker

1. Criar `docker-compose-unified-gateway.yml` com:
   - unified-gateway (:7999)
   - nlu-service (:8020)
   - pii-service (:8021)
   - redis (:6379)
   - kafka (:9092)

2. Executar:
   ```bash
   docker-compose -f docker-compose-unified-gateway.yml up -d
   ```

3. Executar load test

### Opção C: Executar em Staging Externo

1. Configurar URL de staging
2. Usar token de autenticação válido
3. Executar load test

---

## 5. Resultados Esperados

### Cenário de Sucesso

```
       UNIFIED GATEWAY LOAD TEST RESULTS
============================================================

Target URL: http://unified-gateway.staging:7999
Test Duration: 60.00s
Total Requests: 5000
Successful Requests: 4987
Failed Requests: 13
Success Rate: 99.74%
Requests/Second: 83.12  # Nota: ramp-up de 60s

--- SPEC REQUIREMENTS VALIDATION ---
  Throughput >200 req/s: ✅ PASS (234.56 req/s)  # pico após ramp-up
  P95 Latency <20ms: ✅ PASS (18.42 ms)

--- LATENCY STATISTICS ---
  Requests: 4987
  Mean: 12.34ms
  Median: 11.56ms
  P50: 11.56ms
  P90: 16.78ms
  P95: 18.42ms
  P99: 24.15ms
  Min: 5.23ms
  Max: 45.67ms
  StdDev: 4.56ms

--- FLOW CLASSIFICATION DISTRIBUTION ---
  Flow G: 2241 (45.0%)
  Flow F: 1245 (25.0%)
  Flow A: 873 (17.5%)
  Flow H: 628 (12.6%)

============================================================
🟢 EXCELLENT: All requirements met, high success rate
============================================================
```

### Cenário de Falha (Latência)

```
--- SPEC REQUIREMENTS VALIDATION ---
  Throughput >200 req/s: ✅ PASS (245.67 req/s)
  P95 Latency <20ms: ❌ FAIL (34.21 ms)

--- LATENCY STATISTICS ---
  P95: 34.21ms
  P99: 67.89ms

🟠 WARNING: Performance issues detected
```

---

## 6. Próximos Passos

1. **IMEDIATO:** Corrigir ambiente de teste (K8s ou Docker)
2. **CURTO PRAZO:** Executar load test completo
3. **MÉDIO PRAZO:** Otimizar baseado nos resultados
4. **LONGO PRAZO:** Configurar testes periódicos no CI/CD

---

## 7. Critérios de Aceite

O Unified Gateway será considerado **READY FOR PRODUCTION** quando:

- ✅ Throughput >200 req/s
- ✅ P95 latency <20ms
- ✅ Success rate >99%
- ✅ Rate limiting funcional
- ✅ Testes E2E passando
- ✅ Documentação completa

---

## 8. Contingência

Se requisitos não forem atendidos:

| Gap | Mitigação |
|-----|-----------|
| **Latência >20ms** | Otimizar NLU/PII gRPC calls, adicionar cache |
| **Throughput <200/s** | Horizontal pod autoscaling (HPA) |
| **Success rate <99%** | Debugar erros, adicionar retries |
| **Rate limiting broken** | Verificar Redis config |

---

*Este documento será atualizado conforme resultados do load test*
