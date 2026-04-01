# Análise: Padrões de Tópicos Kafka

**Data:** 2026-04-01
**Espec:** Platform Standardization - R7
**Status:** ⚠️ INCONSISTÊNCIAS IDENTIFICADAS

---

## Resumo Executivo

Foram identificados **3 padrões diferentes** de nomes de tópicos Kafka no código, violando a regra definida no `CODE_STYLE_GUIDE.md` que especifica `{domain}.{event}`.

---

## Padrões Encontrados

### 1. Padrão com Pontos (Dot-Notation) ✅ CORRETO

| Tópico | Serviço | Status |
|--------|---------|--------|
| `plans.ready` | consensus-engine | ✅ OK |
| `plans.ready.dlq` | consensus-engine | ✅ OK |
| `plans.consensus` | consensus-engine | ✅ OK |
| `execution.tickets` | guard-agents, execution-ticket-service | ✅ OK |
| `execution.tickets.validated` | guard-agents | ✅ OK |
| `execution.tickets.rejected` | guard-agents | ✅ OK |
| `execution.tickets.pending_approval` | guard-agents | ✅ OK |
| `security.validations` | guard-agents | ✅ OK |
| `insights.generated` | optimizer-agents | ✅ OK |
| `telemetry.aggregated` | optimizer-agents | ✅ OK |
| `optimization.applied` | optimizer-agents | ✅ OK |
| `experiments.results` | optimizer-agents | ✅ OK |

### 2. Padrão com Hífens (Kebab-Case) ❌ INCORRETO

| Tópico | Serviço | Deveria ser |
|--------|---------|-------------|
| `cognitive-plans-approval-requests` | approval-service, semantic-translation-engine | `cognitive-plans.approval-requests` |
| `cognitive-plans-approval-responses` | approval-service, semantic-translation-engine | `cognitive-plans.approval-responses` |
| `cognitive-plans-approval-dlq` | semantic-translation-engine | `cognitive-plans.approval-dlq` |
| `security-incidents` | guard-agents | `security.incidents` |
| `orchestration-incidents` | guard-agents | `orchestration.incidents` |
| `remediation-actions` | guard-agents | `remediation.actions` |

### 3. Padrão Dinâmico com Hífens ⚠️ PARCIAL

| Padrão | Uso | Observação |
|--------|-----|------------|
| `intentions.{domain}` | gateway-intencoes | Usa kebab-case para domain |
| `dlq.intentions.{domain}` | gateway-intencoes | DLQ também com hífens |

---

## Inconsistências Detalhadas

### cognitive-plans vs cognitive.plans

**Atual:** `cognitive-plans-approval-requests`
**Deveria ser:** `cognitive.plans.approval-requests`

**Arquivos afetados:**
- `services/semantic-translation-engine/src/config/settings.py`
- `services/approval-service/src/config/settings.py`
- Vários testes em ambos os serviços

### security-incidents vs security.incidents

**Atual:** `security-incidents`
**Deveria ser:** `security.incidents`

**Arquivos afetados:**
- `services/guard-agents/src/config/settings.py`
- `services/guard-agents/tests/consumers/test_incident_feedback_consumer.py`

### remediation-actions vs remediation.actions

**Atual:** `remediation-actions`
**Deveria ser:** `remediation.actions`

**Arquivos afetados:**
- `services/guard-agents/src/config/settings.py`

---

## Impacto da Mudança

### Serviços Afetados

1. **semantic-translation-engine**
   - 4 tópicos com hífens
   - 15+ testes usando tópicos antigos

2. **approval-service**
   - 3 tópicos com hífens
   - 20+ testes usando tópicos antigos

3. **guard-agents**
   - 3 tópicos com hífens
   - 5+ testes usando tópicos antigos

4. **gateway-intencoes**
   - Padrão dinâmico com hífens no domain
   - Alto risco de breaking change

### Riscos

- **Alto:** Mudança de tópicos Kafka requer migração coordenada
- **Alto:** Consumers/producers antigos não receberão mensagens dos tópicos novos
- **Médio:** Testes E2E podem falhar após mudança

---

## Plano de Migração Sugerido

### Fase 1: Preparação (Sem Breaking Changes)

1. **Adicionar aliases** nos settings:
   ```python
   # NOVOS (padrão correto)
   kafka_cognitive_plans_topic: str = "cognitive.plans"
   kafka_approval_requests_topic: str = "cognitive.plans.approval-requests"

   # ANTIGOS (para compatibilidade)
   kafka_approval_requests_topic_legacy: str = "cognitive-plans-approval-requests"
   ```

2. **Documentar** os tópicos corretos no CODE_STYLE_GUIDE.md

### Fase 2: Migração Gradual

1. **Atualizar consumers** para ouvir de ambos os tópicos
2. **Atualizar producers** para enviar para o novo tópico
3. **Testar** com ambos os tópicos ativos
4. **Remover** tópicos antigos após validação

### Fase 3: Limpeza

1. Remover aliases de compatibilidade
2. Atualizar todos os testes
3. Remover referências a tópicos antigos

---

## Recomendação

**NÃO implementar imediatamente** - Esta é uma mudança de alto risco que requer:

1. Planejamento detalhado de migração
2. Janela de manutenção
3. Coordenação entre equipes
4. Testes E2E completos

**Prioridade:** P2 (Médio Prazo)
**Estimativa:** 16-24 horas para migração completa

---

## Alternativa: Aceitar Hífens

Considerando que:
- Muitos tópicos já usam hífens em produção
- A mudança é de alto risco
- Hífens são mais legíveis para humanos

**Sugestão:** Atualizar o `CODE_STYLE_GUIDE.md` para aceitar ambos:
- `{domain}.{event}` para eventos simples
- `{domain}-{sub-event}` para eventos com subcategorias
- `dlq.{domain}-{event}` para dead-letter queues

---

**Relatório gerado:** 2026-04-01
**Análise:** 50+ arquivos verificados
**Tópicos identificados:** 20+
