# Relatório de Execução de Testes Manual - Fluxos A, B e C
> Data de Início: 2026-02-02
> Executor: Claude (AI Assistant)
> Plano de Referência: docs/PLANO_TESTE_MANUAL_FLUXOS_A_C.md
> Status: Em andamento

---

## Variáveis de Ambiente

| Variável | Valor |
|----------|-------|
| GATEWAY_POD | gateway-intencoes-d65fc898d-nqrl7 |
| STE_POD | semantic-translation-engine-685f556dcb-plprb |
| CONSENSUS_POD | consensus-engine-5fb5fb655-csjzq |
| ORCHESTRATOR_POD | orchestrator-dynamic-6864c7b445-9z6r9 |
| KAFKA_POD | neural-hive-kafka-broker-0 |
| MONGO_POD | mongodb-677c7746c4-tkh9k |
| REDIS_POD | redis-66b84474ff-nfth2 |
| SERVICE_REGISTRY_POD | service-registry-56df7d8dc9-bjsmp |
| WORKER_POD | code-forge-59bf5f5788-f82p8 |

---

## IDs Coletados Durante o Teste

| Campo | Payload 1 (TECHNICAL) | Payload 2 (BUSINESS) | Payload 3 (INFRA) |
|-------|----------------------|---------------------|-------------------|
| `intent_id` | | | |
| `correlation_id` | | | |
| `trace_id` | | | |
| `plan_id` | | | |
| `decision_id` | | | |
| `ticket_id` (primeiro) | | | |
| Domain | technical | business | infrastructure |
| Confidence | | | |
| Final Decision | | | |

---

## 3. FLUXO A - Gateway de Intenções → Kafka

### 3.1 Health Check do Gateway

**INPUT:**
- Comando: `kubectl exec -n neural-hive $GATEWAY_POD -- curl -s http://localhost:8000/health`

**OUTPUT:**
```
[PENDENTE DE EXECUÇÃO]
```

**ANÁLISE PROFUNDA:**
- Status: [AGUARDANDO]
- Componentes verificados: [AGUARDANDO]
- SLOs verificados: [AGUARDANDO]

**EXPLICABILIDADE:**
- [AGUARDANDO]

**Status: [ ] PASSOU / [ ] FALHOU**

---

### 3.2 Enviar Intenção (Payload 1 - TECHNICAL)

**INPUT:**
```json
{
  "text": "Analisar viabilidade técnica de migração do sistema de autenticação para OAuth2 com suporte a MFA",
  "context": {
    "session_id": "test-session-001",
    "user_id": "qa-tester-001",
    "source": "manual-test",
    "metadata": {
      "test_run": "fluxo-a-b-c",
      "environment": "staging"
    }
  },
  "constraints": {
    "priority": "high",
    "security_level": "confidential",
    "deadline": "2026-02-01T00:00:00Z"
  }
}
```

**OUTPUT:**
```
[PENDENTE DE EXECUÇÃO]
```

**ANÁLISE PROFUNDA:**
- intent_id: [AGUARDANDO]
- correlation_id: [AGUARDANDO]
- trace_id: [AGUARDANDO]
- domain: [AGUARDANDO]
- confidence: [AGUARDANDO]
- status: [AGUARDANDO]

**EXPLICABILIDADE:**
- Classificação NLU: [AGUARDANDO]
- Tópico Kafka: [AGUARDANDO]
- Offset: [AGUARDANDO]

**Status: [ ] PASSOU / [ ] FALHOU**

---

[Resto do relatório será preenchido conforme execução...]
