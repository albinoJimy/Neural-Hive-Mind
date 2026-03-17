# Exemplo de Configuração - Consenso Hierárquico

Este arquivo demonstra como configurar o Consensus Engine para utilizar o consenso hierárquico.

## Variáveis de Ambiente

### Feature Flag

```bash
# Habilita/desabilita consenso hierárquico
ENABLE_HIERARCHICAL_CONSENSUS=true
```

### Mapeamento de Senioridade

```bash
# Define o nível de senioridade padrão para cada especialista
# Formato JSON: {"specialist_type": "seniority_level"}
SPECIALIST_SENIORITY='{
  "business": "senior",
  "technical": "senior",
  "architecture": "expert",
  "behavior": "mid_level",
  "evolution": "mid_level"
}'
```

**Níveis disponíveis:**
- `trainee` - Aprendiz (0.5× peso)
- `junior` - Júnior (0.75× peso)
- `mid_level` - Nível médio (1.0× peso)
- `senior` - Sênior (1.5× peso)
- `expert` - Especialista (2.0× peso)

### Nível Padrão

```bash
# Nível usado quando um especialista não tem mapeamento explícito
DEFAULT_SENIORITY_LEVEL=mid_level
```

### Pesos por Domínio

```bash
# Peso adicional quando o especialista está no seu domínio de especialização
# Formato JSON: {"specialist_type_DOMAIN": weight}
DOMAIN_SPECIALIST_WEIGHTS='{
  "business_BUSINESS": 0.25,
  "technical_TECHNICAL": 0.25,
  "architecture_ARCHITECTURE": 0.30
}'
```

## Exemplos de Uso

### Cenário 1: Configuração Padrão

```yaml
# .env ou values.yaml
enable_hierarchical_consensus: true
specialist_seniority:
  business: "senior"
  technical: "senior"
  architecture: "expert"
```

**Resultado:**
- Architecture experts têm 2× o peso de outros especialistas
- Business e Technical seniors têm 1.5× o peso de juniors

### Cenário 2: Time Balanceado

```yaml
enable_hierarchical_consensus: true
specialist_seniority:
  business: "senior"
  technical: "senior"
  architecture: "senior"
  behavior: "senior"
  evolution: "senior"
```

**Resultado:**
- Todos têm 1.5× peso (equilibrado)
- Útil quando não há especialista "expert" disponível

### Cenário 3: Hierarquia Explícita por Domínio

```yaml
enable_hierarchical_consensus: true
specialist_seniority:
  business: "expert"
  technical: "expert"

domain_specialist_weights:
  business_BUSINESS: 0.30
  technical_TECHNICAL: 0.30
  architecture_ARCHITECTURE: 0.35
```

**Resultado:**
- Business expert em domínio BUSINESS tem peso máximo: 1.0 × 2.0 × 0.30 = 0.3
- Architecture experts recebem bônus de domínio quando em ARCHITECTURE

### Cenário 4: Desabilitado (Comportamento Legado)

```yaml
enable_hierarchical_consensus: false
```

**Resultado:**
- Todos os especialistas têm peso igual (baseado apenas em feromônios)
- Comportamento idêntico ao antes da feature

## Validação

### Verificar Configuração

```python
from src.config.settings import Settings

config = Settings()

# Verificar feature flag
print(f"Consenso Hierárquico: {config.enable_hierarchical_consensus}")

# Verificar mapeamentos
for specialist, level in config.specialist_seniority.items():
    print(f"{specialist}: {level}")

# Verificar pesos de domínio
for domain, weight in config.domain_specialist_weights.items():
    print(f"{domain}: {weight}")
```

### Verificar Pesos em Tempo de Execução

```python
decision = await orchestrator.process_consensus(
    cognitive_plan,
    specialist_opinions
)

# Verificar se hierárquico foi usado
print(f"Weighted by seniority: {decision.consensus_metrics.weighted_by_seniority}")

# Verificar distribuição
print(f"Seniority distribution: {decision.consensus_metrics.seniority_distribution}")

# Verificar pesos individuais
for vote in decision.specialist_votes:
    print(f"{vote.specialist_type}: weight={vote.weight:.3f}, "
          f"seniority={vote.seniority_level}, "
          f"multiplier={vote.seniority_multiplier}")
```

## Monitoramento

### Métricas Prometheus

O Consensus Engine expõe as seguintes métricas quando o consenso hierárquico está habilitado:

```
# Percentual de decisões usando consenso hierárquico
hierarchical_consensus_enabled{service="consensus-engine"} 1

# Distribuição de senioridade nas decisões
seniority_distribution_total{seniority_level="senior"} 42
seniority_distribution_total{seniority_level="expert"} 15
seniority_distribution_total{seniority_level="junior"} 8

# Peso médio por nível de senioridade
hierarchical_weight_avg{seniority_level="senior"} 0.075
hierarchical_weight_avg{seniority_level="expert"} 0.12
```

## Troubleshooting

### Problema: Pesos hierárquicos não estão sendo aplicados

**Sintoma:** Todos os especialistas têm o mesmo peso.

**Solução:**
1. Verifique que `ENABLE_HIERARCHICAL_CONSENSUS=true`
2. Verifique que `SPECIALIST_SENIORITY` está configurado
3. Verifique logs para mensagens sobre "hierarchical_weight_calculated"

### Problema: Distribuição de senioridade vazia

**Sintoma:** `seniority_distribution` aparece vazio.

**Solução:**
1. Verifique que as opiniões dos especialistas incluem `seniority_level`
2. Se não incluírem, será usado o padrão de `config.specialist_seniority`
3. Verifique se a configuração está sendo carregada corretamente

### Problema: ValueError ao configurar senioridade inválida

**Sintoma:** erro ao definir `SPECIALIST_SENIORITY` com nível inválido.

**Solução:**
- Use apenas níveis válidos: `trainee`, `junior`, `mid_level`, `senior`, `expert`
- A configuração será validada e rejeitará níveis inválidos

## Referências

- [Documentação Completa](../docs/GAPS-03-CONSENSO_HIERARQUICO.md)
- [Deploy Checklist](../docs/DEPLOY_CHECKLIST_GAPS-03.md)
- [Feature Map](../feature-map.md)
