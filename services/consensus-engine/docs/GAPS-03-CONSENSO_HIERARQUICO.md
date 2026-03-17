# Consenso Hierárquico - GAPS-03

## Visão Geral

O **Consenso Hierárquico** é uma funcionalidade do Neural-Hive-Mind que permite que especialistas mais seniores tenham maior peso nas decisões de consenso. Esta feature implementa o ticket **GAPS-03** do roadmap.

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Consensus Orchestrator                          │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │           HierarchicalWeightCalculator                       │  │
│  │                                                              │  │
│  │  weight = pheromone_weight × seniority_multiplier × domain   │  │
│  │                                                              │  │
│  │  normalized = min(1.0, weight / 2.0)                         │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  Entrada: CognitivePlan + SpecialistOpinions                     │
│  Saída:   ConsolidatedDecision (com pesos hierárquicos)          │
└─────────────────────────────────────────────────────────────────────┘
```

## Níveis de Senioridade

| Nível | Multiplicador | Descrição |
|-------|---------------|------------|
| `trainee` | 0.5× | Em treinamento, menor influência |
| `junior` | 0.75× | Júnior, influência reduzida |
| `mid_level` | 1.0× | Nível médio, peso padrão |
| `senior` | 1.5× | Sênior, influência elevada |
| `expert` | 2.0× | Especialista, máxima influência |

## Fórmula de Cálculo

```
peso_bruto = peso_feromônio × multiplicador_senioridade × peso_domínio

peso_final = min(1.0, peso_bruto / 2.0)
```

**Exemplo prático:**
- Architecture (expert) em domínio ARCHITECTURE:
  - peso_feromônio = 1.0
  - multiplicador_senioridade = 2.0 (expert)
  - peso_domínio = 0.30
  - peso_bruto = 1.0 × 2.0 × 0.30 = 0.6
  - peso_final = 0.6 / 2.0 = **0.3**

## Configuração

### Variáveis de Ambiente

```bash
# Feature Flag
ENABLE_HIERARCHICAL_CONSENSUS=true

# Mapeamento de senioridade (JSON)
SPECIALIST_SENIORITY='{"business":"senior","technical":"senior","architecture":"expert"}'

# Nível padrão
DEFAULT_SENIORITY_LEVEL=mid_level

# Pesos por domínio (JSON)
DOMAIN_SPECIALIST_WEIGHTS='{"business_BUSINESS":0.25,"architecture_ARCHITECTURE":0.30}'
```

### Exemplo de Configuração Python

```python
from src.config.settings import Settings

config = Settings()

# Verificar se habilitado
if config.enable_hierarchical_consensus:
    print(f"Business: {config.specialist_seniority['business']}")
    # Output: "senior"

    print(f"Peso Architecture em BUSINESS: {config.domain_specialist_weights.get('architecture_BUSINESS', 'N/A')}")
    # Output: "N/A" (não configurado)

    print(f"Peso Architecture em ARCHITECTURE: {config.domain_specialist_weights.get('architecture_ARCHITECTURE', 'N/A')}")
    # Output: "0.30"
```

## Uso

### Básico

```python
from src.services.consensus_orchestrator import ConsensusOrchestrator

# Inicializar
orchestrator = ConsensusOrchestrator(config, pheromone_client)

# Processar consenso
decision = await orchestrator.process_consensus(
    cognitive_plan=cognitive_plan,
    specialist_opinions=specialist_opinions
)

# Verificar se foi usado consenso hierárquico
if decision.consensus_metrics.weighted_by_seniority:
    print(f"Distribuição: {decision.consensus_metrics.seniority_distribution}")
    # Output: {"senior": 2, "expert": 1}
```

### Campo `seniority_level` na Opinião

Especialistas podem incluir seu nível de senioridade nas opiniões:

```python
opinion = {
    'specialist_type': 'business',
    'opinion_id': 'op-123',
    'opinion': {
        'confidence_score': 0.85,
        'risk_score': 0.2,
        'recommendation': 'approve'
    },
    'seniority_level': 'senior',  # ← Campo opcional
    'processing_time_ms': 100
}
```

Se omitido, o nível configurado em `config.specialist_seniority` será usado.

## Modelos de Dados

### SpecialistVote (extendido)

```python
class SpecialistVote(BaseModel):
    specialist_type: str
    opinion_id: str
    confidence_score: float
    risk_score: float
    recommendation: str
    weight: float
    processing_time_ms: int

    # Campos hierárquicos (GAPS-03)
    seniority_level: Optional[str] = None      # 'trainee', 'junior', ...
    seniority_multiplier: Optional[float] = None  # 0.5, 0.75, 1.0, 1.5, 2.0
```

### ConsensusMetrics (extendido)

```python
class ConsensusMetrics(BaseModel):
    divergence_score: float
    convergence_time_ms: int
    unanimous: bool
    fallback_used: bool
    pheromone_strength: float
    bayesian_confidence: float
    voting_confidence: float

    # Campos hierárquicos (GAPS-03)
    weighted_by_seniority: bool = False
    seniority_distribution: Dict[str, int] = {}  # {'senior': 2, 'expert': 1}
    consensus_method_hierarchical: bool = False
```

## Testes

### Executar Todos os Testes

```bash
# Unitários
PYTHONPATH=src python3 -m pytest tests/seniority_tests/ \
    tests/weights_tests/ \
    tests/decision_hierarchical_tests/ \
    tests/settings_hierarchical_tests/ -v

# Integração
PYTHONPATH=src python3 -m pytest tests/integration_tests/ -v

# Todos
PYTHONPATH=src python3 -m pytest tests/ -v -k "hierarchical"
```

### Cobertura

| Componente | Testes |
|-------------|---------|
| Modelo Senioridade | 24 |
| Calculadora Pesos | 12 |
| Modelo Decisão | 15 |
| Configurações | 10 |
| Integração | 7 |
| **Total** | **68** |

## Backward Compatibility

A feature é **100% backward compatible**:

- Campos novos são `Optional` com default `None`
- Feature flag `enable_hierarchical_consensus` pode ser `False`
- Quando desabilitado, comportamento é idêntico ao anterior

## Deploy

### Checklist

- [ ] Tests passando (68/68)
- [ ] Feature flag configurada
- [ ] Mapeamento de senioridade definido
- [ ] Pesos de domínio configurados (opcional)
- [ ] Documentação atualizada
- [ ] Deploy em staging primeiro
- [ ] Monitoramento de métricas

### Métricas de Sucesso

- `consensus_metrics.weighted_by_seniority == True`
- `consensus_metrics.seniority_distribution` contabilizando votos
- Pesos de experts > pesos de seniors > pesos de juniors

## Troubleshooting

### Pesos menores que esperado

Verifique se `enable_hierarchical_consensus=True`:

```python
from src.config.settings import Settings
config = Settings()
print(config.enable_hierarchical_consensus)  # Deve ser True
```

### Distribuição de senioridade vazia

Verifique se opiniões incluem `seniority_level`:

```python
for opinion in specialist_opinions:
    print(f"{opinion['specialist_type']}: {opinion.get('seniority_level', 'N/A')}")
```

### Avro serialization error

Campos hierárquicos foram adicionados ao schema Avro. Se receber erro de serialização, verifique que a versão do schema está atualizada em todos os serviços consumidores.

## Referências

- Ticket: GAPS-03 (Consenso Hierárquico)
- Implementação: `src/models/seniority.py`, `src/services/hierarchical_weights.py`
- Testes: `tests/integration_tests/test_hierarchical_consensus_integration.py`
