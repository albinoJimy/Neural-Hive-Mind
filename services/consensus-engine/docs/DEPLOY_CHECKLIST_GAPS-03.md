# Deploy Checklist - GAPS-03 Consenso Hierárquico

## Status: ✅ PRONTO PARA DEPLOY

### Pré-Deploy

- [x] **Código implementado** (GAPS-03-01 a GAPS-03-05)
- [x] **Testes unitários** (61 testes passando)
- [x] **Testes de integração** (7 testes passando)
- [x] **Documentação técnica** criada
- [x] **Backward compatibility** validada
- [x] **Feature flag** implementada

### Configuração Obrigatória

Adicionar ao deployment (Helm values ou env):

```yaml
# Feature Flag
enable_hierarchical_consensus: true

# Mapeamento de senioridade (recomendado)
specialist_seniority:
  business: "senior"
  technical: "senior"
  architecture: "expert"
  behavior: "mid_level"
  evolution: "mid_level"

# Nível padrão
default_seniority_level: "mid_level"

# Pesos por domínio (opcional)
domain_specialist_weights:
  business_BUSINESS: 0.25
  technical_TECHNICAL: 0.25
  architecture_ARCHITECTURE: 0.30
```

### Rollout Strategy

1. **Staging** (primeiro)
   - Habilitar feature flag em staging
   - Validar testes de integração
   - Monitorar métricas de consenso

2. **Produção** (após staging validado)
   - Deploy gradativo (10% → 50% → 100%)
   - Monitorar taxa de aprovação/rejeição
   - Verificar distribuição de senioridade

### Validação em Produção

Após deploy, verificar:

```bash
# Verificar se feature flag está ativa
kubectl logs -n neural-hive consensus-engine-xxx | grep "enable_hierarchical_consensus"

# Verificar distribuição de senioridade nas decisões
# Deve mostrar: weighted_by_seniority=true
```

### Métricas de Sucesso

- `consensus_metrics.weighted_by_seniority == true`
- `consensus_metrics.seniority_distribution` não vazio
- Pesos de experts > pesos de seniors > pesos de juniors
- Taxa de aprovação mantida ou melhorada

### Rollback Plan

Se problemas detectados:

1. **Desabilitar feature flag** via config update:
   ```bash
   enable_hierarchical_consensus: false
   ```

2. **Restart dos pods** para aplicar config

3. **Investigar logs** para identificar causa raiz

### Compatibilidade

| Versão | Compatível |
|---------|------------|
| MongoDB Schema | ✅ Sim (campos novos são Optional) |
| Avro Schema | ✅ Sim (campos adicionais são Optional) |
| Kafka Messages | ✅ Sim (backward compatible) |
| Downstream Consumers | ✅ Sim (ignoram campos novos) |

### Notas de Migração

- **Sem migração de dados necessária** - campos novos são Optional
- **Sem downtime** - feature flag permite ativação dinâmica
- **Sem impacto em performance** - cálculo adicional é leve

### Pós-Deploy

- [ ] Monitorar logs por 24h
- [ ] Validar métricas de consenso
- [ ] Verificar distribuição de senioridade
- [ ] Documentar quaisquer ajustes necessários

### Links Úteis

- Documentação: `docs/GAPS-03-CONSENSO_HIERARQUICO.md`
- Testes: `tests/integration_tests/test_hierarchical_consensus_integration.py`
- Implementação: `src/models/seniority.py`, `src/services/hierarchical_weights.py`
