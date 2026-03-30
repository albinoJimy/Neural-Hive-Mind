# Sub-Spec: Epic G - Activar Features Fase 3

## Objetivo

Activar features da Fase 3 (Auto-Recuperação e Governança) que estão implementadas mas desactivadas por padrão: Active Learning, Evolution Hooks e Chaos Engineering.

## Tickets

### 1. Activar Active Learning em Produção
**Arquivo:** `services/approval-service/src/config/settings.py`

**Pré-condições:**
- [x] Epic D (Online Learning) implementado
- [ ] Testes E2E passando

**Mudança:**
```python
# ANTES
ENABLE_ACTIVE_LEARNING: bool = Field(default=False)

# DEPOIS (após validação)
ENABLE_ACTIVE_LEARNING: bool = Field(default=True)
```

**Validação:**
```bash
# Verificar que Active Learning está activo
curl http://approval-service/api/v1/active-learning/metrics
# Deve retornar métricas de balanceamento

# Verificar queue de feedback
# (deve ter itens se houve feedbacks)
```

### 2. Activar Evolution Hooks
**Arquivo:** `services/specialist-evolution/src/config/settings.py`

**Pré-condições:**
- [ ] Import path corrigido (evolution_hooks)
- [ ] Testes E2E passando

**Mudança:**
```python
# ANTES
evolution_hooks_enabled: bool = Field(default=False)

# DEPOIS (após validação)
evolution_hooks_enabled: bool = Field(default=True)
```

**Correção do import path:**
```python
# ANTES (services/specialist-evolution/src/specialist.py)
try:
    from neural_hive_specialists.evolution_hooks import ...
except ImportError:
    EVOLUTION_HOOKS_AVAILABLE = False

# DEPOIS (corrigir path)
try:
    from neural_hive_specialists.evolution_hooks import ...
    # OU mover evolution_hooks para dentro de neural_hive_specialists/
    EvolutionHooksAvailable = True
except ImportError:
    EvolutionHooksAvailable = False
```

**Validação:**
```bash
# Verificar logs do specialist-evolution
kubectl logs -f specialist-evolution | grep "EvolutionHooks"

# Verificar se patterns estão sendo registrados
# (logs devem mostrar "Pattern registered" ou similar)
```

### 3. Activar Chaos Engineering (staging apenas)
**Arquivo:** `services/self-healing-engine/src/config/settings.py`

**Pré-condições:**
- [ ] Epic F (Injectors) implementado
- [ ] Testes E2E passando

**Mudança:**
```python
# ANTES
chaos_enabled: bool = Field(default=False)

# DEPOIS (apenas em staging)
# Em staging:
chaos_enabled: bool = Field(default=True)

# Em production (manter False):
# chaos_enabled: bool = Field(default=False)
```

**Configuração via environment:**
```bash
# staging
CHAOS_ENABLED=true

# production
CHAOS_ENABLED=false
```

**Validação:**
```bash
# Verificar que chaos está activo (staging)
kubectl logs -f self-healing-engine -n staging | grep "ChaosEngine"

# Verificar playbooks sendo executados
# (logs devem mostrar "Playbook executed" ou similar)

# NÃO activar em produção sem aprovação explícita
```

## Ordem de Activação

1. **Epic G002 (Evolution Hooks) PRIMEIRO**
   - Menos arriscado (apenas specialist-evolution)
   - Pode ser activado em produção imediatamente

2. **Epic G001 (Active Learning) SEGUNDO**
   - Requer Epic D (Online Learning)
   - Requer validação de testes
   - Activar em produção após validação

3. **Epic G003 (Chaos Engineering) TERCEIRO**
   - Requer Epic F (Injectors)
   - Activar APENAS em staging
   - NUNCA activar em produção sem aprovação

## Rollback Plan

Se algo der errado:

```bash
# Desactivar via ConfigMap/Secret
kubectl set env deployment/approval-service ENABLE_ACTIVE_LEARNING=false

# Ou editar values.yaml e fazer helm upgrade
helm upgrade approval-service ./helm/approval-service --set enableActiveLearning=false

# Verificar rollback
kubectl rollout status deployment/approval-service
```

## Validação por Feature

### Active Learning
- [ ] BalanceAnalyzer funcionando (dataset balanceado)
- [ ] PriorityFeedbackQueue com itens
- [ ] API REST respondendo
- [ ] ML model treinando com novos dados

### Evolution Hooks
- [ ] FingerprintExtractor funcionando
- [ ] PatternMatcher encontrando padrões
- [ ] WeightAdapter ajustando pesos
- [ ] PatternRegistry persistindo patterns

### Chaos Engineering
- [ ] ChaosEngine injectando falhas
- [ ] PlaybookExecutor executando playbooks
- [ ] Incidents sendo reportados
- [ ] Auto-recuperação funcionando

## Checkpoint de Validação

Antes de activar qualquer feature:

1. **Executar testes E2E**
   ```bash
   pytest services/approval-service/tests/test_e2e.py
   pytest services/specialist-evolution/tests/test_e2e.py
   pytest services/self-healing-engine/tests/test_e2e.py
   ```

2. **Validar em staging**
   - Deploy para staging
   - Executar smoke tests
   - Monitorar por 24h
   - Verificar métricas

3. **Aprovação**
   - Review de métricas
   - Sign-off de engenharia
   - Sign-off de produto
   - Deploy para produção
