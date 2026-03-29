# GAP-03: Dependências Vulneráveis (CVEs)

**Status:** 🔴 Planejado
**Prioridade:** P1 - ALTA (Segurança)
**Esforço Estimado:** 13 dias
**Responsável:** Security Team + Backend Team

---

## Problema

Três dependências críticas com vulnerabilidades conhecidas (CVEs):

| Dependência | Versão Atual | Versão Alvo | CVE | Risco |
|-------------|--------------|-------------|-----|-------|
| **confluent-kafka** | 2.6.1 | 2.8.0+ | RCE potencial | ALTO |
| **python-jose** | 3.3.0 | 4.0.0+ | CVE-2022-24314 | ALTO |
| **FastAPI** | 0.115.6 | 0.115.10+ | Patches segurança | MÉDIO |

### Serviços Afetados

- **confluent-kafka:** 9 serviços (gateway, consensus, STE, approval, workers, orchestrator, etc.)
- **python-jose:** 3 serviços (gateway, code-forge, execution-ticket)
- **FastAPI:** Todos os 20+ serviços Python

---

## Análise de Impacto

### Breaking Changes

**confluent-kafka 2.6.1 → 2.8.0**
- **Risco:** BAIXO
- Código atual deve funcionar sem modificações
- KIP-848 (new consumer rebalance) é opt-in

**python-jose 3.3.0 → 4.0.0**
- **Risco:** BAIXO
- API principal permanece estável
- Exceções mantidas

**FastAPI 0.115.6 → 0.115.10**
- **Risco:** MUITO BAIXO
- Mudanças de patch (backward compatible)

---

## Estratégia de Atualização

### Ordem de Fases

```
FASE 0: Preparação (1 dia)
  └─ Backup, branch, setup ambiente teste

FASE 1: FastAPI (2 dias)
  └─ versions.txt + todos os serviços
  └─ Testes de regressão HTTP

FASE 2: python-jose (2 dias)
  └─ Serviços afetados
  └─ Testes de autenticação/JWT

FASE 3: confluent-kafka (3 dias)
  └─ Todos os serviços Kafka
  └─ Testes de integração

FASE 4: Deploy Staging (2 dias)
  └─ Deploy sequencial
  └─ Testes E2E

FASE 5: Deploy Produção (2 dias)
  └─ Deploy canário
  └─ Monitoramento intensivo
```

---

## Implementação

### Fase 0: Preparação

```bash
# 1. Criar branch
git checkout -b security/dependency-update-2026-03-29

# 2. Backup
cp versions.txt versions.txt.backup-$(date +%Y%m%d)

# 3. Criar ambiente de teste
python -m venv .venv-test
source .venv-test/bin/activate
pip install -r requirements-test.txt
```

### Fase 1: FastAPI

```bash
# Atualizar versions.txt
sed -i 's/fastapi==0.115.6/fastapi==0.115.10/g' versions.txt

# Atualizar todos os requirements.txt
find services -name "requirements.txt" -type f \
  -exec sed -i 's/fastapi==0.115.6/fastapi==0.115.10/g' {} \;

# Testes de regressão HTTP
pytest services/gateway-intencoes/tests/ -v -k "test_http or test_api"
pytest services/consensus-engine/tests/ -v -k "test_http or test_api"
```

### Fase 2: python-jose

```bash
# Atualizar versions.txt
sed -i 's/python-jose\[cryptography\]==3.3.0/python-jose[cryptography]==4.0.0/g' versions.txt

# Atualizar serviços afetados
sed -i 's/python-jose\[cryptography\]==3.3.0/python-jose[cryptography]==4.0.0/g' \
  services/gateway-intencoes/requirements.txt \
  services/execution-ticket-service/requirements.txt

sed -i 's/python-jose\[cryptography\]>=3.3.0/python-jose[cryptography]==4.0.0/g' \
  services/code-forge/requirements.txt

# Testes de autenticação
pytest services/gateway-intencoes/tests/unit/test_oauth2_validator.py -v
pytest services/gateway-intencoes/tests/integration/test_keycloak_integration.py -v
```

### Fase 3: confluent-kafka

```bash
# Atualizar versions.txt
sed -i 's/confluent-kafka==2.6.1/confluent-kafka==2.8.0/g' versions.txt

# Atualizar requirements com avro
find services -name "requirements.txt" -type f \
  -exec sed -i 's/confluent-kafka\[avro\]==2.6.1/confluent-kafka[avro]==2.8.0/g' {} \;

find services -name "requirements.txt" -type f \
  -exec sed -i 's/confluent-kafka==2.6.1/confluent-kafka==2.8.0/g' {} \;

# Testes de integração Kafka
pytest services/consensus-engine/tests/ -v -k kafka
pytest services/worker-agents/tests/ -v -k kafka
```

---

## Ordem de Deploy

```
1. optimizer-agents (Médio impacto)
2. architect-agent (Médio impacto)
3. approval-service (Alto impacto)
4. consensus-engine (Alto impacto)
5. execution-ticket-service (Alto impacto)
6. worker-agents (Alto impacto)
7. orchestrator-dynamic (Alto impacto)
8. semantic-translation-engine (Alto impacto)
9. gateway-intencoes (ÚLTIMO - CRÍTICO)
```

---

## Testes de Validação

### Confluent Kafka

```bash
# Teste básico de produtor/consumidor
python -c "
from confluent_kafka import Producer, Consumer
print('confluent-kafka import OK')
"

# Teste de serialização Avro
python -c "
from confluent_kafka.schema_registry.avro import AvroSerializer
print('Avro serialization OK')
"
```

### python-jose

```bash
# Teste de JWT
python -c "
from jose import jwt
from datetime import datetime, timedelta

secret = 'test-secret'
payload = {'user': 'test', 'exp': datetime.utcnow() + timedelta(hours=1)}

# Encode
token = jwt.encode(payload, secret, algorithm='HS256')
print(f'Encoded: {token[:50]}...')

# Decode
decoded = jwt.decode(token, secret, algorithms=['HS256'])
print(f'Decoded: {decoded}')
print('python-jose upgrade OK!')
"
```

### FastAPI

```bash
# Teste de servidor
pytest services/gateway-intencoes/tests/ -v -k "test_main"
```

---

## Rollback Plan

```bash
# Rollback individual
kubectl rollout undo deployment/gateway-intencoes -n neural-hive-mind

# Rollback em lote
for service in gateway-intencoes consensus-engine semantic-translation-engine; do
  kubectl rollout undo deployment/$service -n neural-hive-mind
done

# Rollback versions.txt
git checkout HEAD~1 versions.txt
```

### Critérios de Rollback

- Erro rate > 1% em qualquer serviço crítico
- Latência P95 > 2x baseline
- Pods não readiness por > 5 minutos
- Erros de Kafka consumer/producer

---

## Checklist

**Pre-Deploy:**
- [ ] Branch criada
- [ ] versions.txt atualizado
- [ ] Todos os requirements.txt atualizados
- [ ] Testes unitários passando
- [ ] Testes de integração passando
- [ ] Imagens Docker rebuildadas
- [ ] Documentação atualizada
- [ ] Code review aprovado

**Pos-Deploy:**
- [ ] Todos pods Ready
- [ ] Health checks OK
- [ ] Erro rate dentro baseline
- [ ] Logs sem erros críticos
- [ ] Testes de smoke passando
- [ ] Monitoramento ativo
- [ ] Rollback testado (em staging)

---

## Arquivos Críticos

| Ação | Arquivo |
|------|---------|
| **MODIFICAR** | `versions.txt` (arquivo canônico) |
| **MODIFICAR** | `services/*/requirements.txt` (todos) |
| **TESTAR** | `services/gateway-intencoes/src/security/oauth2_validator.py` |
| **TESTAR** | `services/*/tests/test_kafka*.py` |

---

## Cronograma

| Fase | Dias | Deliverable |
|------|------|-------------|
| 0 - Preparação | 1 | Branch criada |
| 1 - FastAPI | 2 | FastAPI 0.115.10 |
| 2 - python-jose | 2 | python-jose 4.0.0 |
| 3 - confluent-kafka | 3 | confluent-kafka 2.8.0 |
| 4 - Staging | 2 | Validado em staging |
| 5 - Produção | 2 | Deploy completo |
| **TOTAL** | **12** | **Zero CVEs** |

---

**Documento baseado em análise do agente Plan (2026-03-29)**
