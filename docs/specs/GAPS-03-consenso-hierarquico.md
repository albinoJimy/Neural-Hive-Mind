# Plano de Implementação: GAPS-03 - Consenso Hierárquico

**Ticket:** GAPS-03
**Prioridade:** Crítico (Must)
**Estimativa:** M (1 semana)
**Data Criação:** 2026-03-17

---

## 1. Visão Geral

Implementar sistema de **hierarquia de especialistas** baseado em níveis de senioridade, permitindo que opiniões de especialistas seniores tenham maior peso no consenso do que especialistas juniores.

### Motivação
Atualmente, todos os especialistas têm peso igual no consenso (ou pesos dinâmicos baseados apenas em feromônios). Especialistas mais experientes deveriam ter sua opinião mais valorizada, refletindo sistemas hierárquicos reais.

### Objetivos
1. Definir níveis de senioridade para especialistas
2. Calcular pesos hierárquicos no consenso
3. Adicionar metadados de senioridade nas decisões
4. Manter backward compatibility

---

## 2. Análise Técnica Atual

### 2.1 Código Existente

**Arquivo:** `services/consensus-engine/src/services/consensus_orchestrator.py`

```python
# Cálculo atual de pesos (linha 243-280)
async def _calculate_dynamic_weights(self, ...) -> Dict[str, float]:
    for opinion in specialist_opinions:
        if self.config.enable_pheromones:
            weight = await self.pheromone_client.calculate_dynamic_weight(
                specialist_type, domain, base_weight=0.2
            )
        else:
            weight = 0.2  # Todos têm mesmo peso base
```

### 2.2 Estruturas de Dados

**SpecialistVote** (`consolidated_decision.py`):
```python
class SpecialistVote(BaseModel):
    specialist_type: str
    confidence_score: float
    risk_score: float
    recommendation: str
    weight: float  # ← Peso calculado
    # NÃO TEM campo de senioridade
```

### 2.3 Especialistas Atuais

| Tipo | Endpoint | Descrição |
|------|-----------|------------|
| business | `specialist-business` | Análise de negócio |
| technical | `specialist-technical` | Análise técnica |
| behavior | `specialist-behavior` | Análise comportamental |
| evolution | `specialist-evolution` | Análise evolutiva |
| architecture | `specialist-architecture` | Análise arquitetural |

---

## 3. Design da Solução

### 3.1 Níveis de Senioridade

```python
class SeniorityLevel(str, Enum):
    """Nível de senioridade do especialista"""
    TRAINEE = 'trainee'      # Aprendiz (peso: 0.5x)
    JUNIOR = 'junior'        # Júnior (peso: 0.75x)
    MID_LEVEL = 'mid_level'  # Pleno (peso: 1.0x)
    SENIOR = 'senior'        # Sénior (peso: 1.5x)
    EXPERT = 'expert'        # Especialista (peso: 2.0x)
```

### 3.2 Configuração de Senioridade por Tipo

```python
# config/settings.py
specialist_seniority: Dict[str, SeniorityLevel] = Field(
    default={
        'business': 'senior',
        'technical': 'senior',
        'behavior': 'mid_level',
        'evolution': 'mid_level',
        'architecture': 'expert',
    },
    description='Senioridade base de cada tipo de especialista'
)
```

### 3.3 Pesos Hierárquicos

```python
SENIORITY_MULTIPLIERS = {
    SeniorityLevel.TRAINEE: 0.5,
    SeniorityLevel.JUNIOR: 0.75,
    SeniorityLevel.MID_LEVEL: 1.0,
    SeniorityLevel.SENIOR: 1.5,
    SeniorityLevel.EXPERT: 2.0,
}
```

### 3.4 Fórmula de Peso Hierárquico

```python
weight_final = weight_pheromone × multiplier_seniority × weight_domain
```

Onde:
- `weight_pheromone`: Peso dinâmico baseado em feromônios (0.0 - 1.0)
- `multiplier_seniority`: Multiplicador baseado no nível (0.5 - 2.0)
- `weight_domain`: Peso base do especialista no domínio (configurável, padrão 0.2)

---

## 4. Implementação

### 4.1 Arquivos a Criar/Modificar

| Arquivo | Ação | Descrição |
|---------|------|------------|
| `src/models/seniority.py` | **NOVO** | Enum e configurações de senioridade |
| `src/services/hierarchical_weights.py` | **NOVO** | Cálculo de pesos hierárquicos |
| `src/services/consensus_orchestrator.py` | **ALTERAR** | Integrar pesos hierárquicos |
| `src/models/consolidated_decision.py` | **ALTERAR** | Adicionar senioridade em SpecialistVote |
| `src/config/settings.py` | **ALTERAR** | Configurações de senioridade |
| `tests/test_hierarchical_weights.py` | **NOVO** | Testes unitários |
| `tests/test_consensus_hierarchical.py` | **NOVO** | Testes integração |

### 4.2 Estrutura do Novo Serviço

```python
# src/services/hierarchical_weights.py

class HierarchicalWeightCalculator:
    """Calcula pesos hierárquicos baseados em senioridade"""

    def __init__(self, config: Settings):
        self.config = config
        self.multipliers = SENIORITY_MULTIPLIERS
        self.domain_weights = config.domain_specialist_weights

    async def calculate_hierarchical_weight(
        self,
        specialist_type: str,
        domain: UnifiedDomain,
        pheromone_weight: float,
        seniority: Optional[SeniorityLevel] = None
    ) -> float:
        """
        Calcula peso final hierárquico

        Args:
            specialist_type: Tipo do especialista
            domain: Domínio da intenção
            pheromone_weight: Peso baseado em feromônios
            seniority: Nível de senioridade (opcional, usa config se omitido)

        Returns:
            Peso final calculado (0.0 - 1.0)
        """
        # Usar senioridade configurada se não fornecida
        if seniority is None:
            seniority = self.config.specialist_seniority.get(
                specialist_type,
                SeniorityLevel.MID_LEVEL
            )

        # Multiplicador de senioridade
        seniority_multiplier = self.multipliers[seniority]

        # Peso base do especialista neste domínio
        domain_weight = self.domain_weights.get(
            f"{specialist_type}_{domain.value}",
            0.2  # Peso padrão
        )

        # Aplicar normalização para manter peso em [0, 1]
        raw_weight = pheromone_weight * seniority_multiplier * domain_weight
        normalized_weight = min(1.0, raw_weight / 2.0)  # Normalizar por max possível

        return normalized_weight
```

### 4.3 Integração no ConsensusOrchestrator

```python
# services/consensus-engine/src/services/consensus_orchestrator.py

from src.services.hierarchical_weights import HierarchicalWeightCalculator

class ConsensusOrchestrator:
    def __init__(self, config, pheromone_client):
        # ... código existente ...
        self.hierarchical = HierarchicalWeightCalculator(config)

    async def _calculate_dynamic_weights(self, ...) -> Dict[str, float]:
        """Calcula pesos dinâmicos com hierarquia de senioridade"""
        weights = {}
        domain = DomainMapper.normalize(domain_str, 'intent_envelope')

        for opinion in specialist_opinions:
            specialist_type = opinion['specialist_type']

            # 1. Obter peso baseado em feromônios
            if self.config.enable_pheromones:
                pheromone_weight = await self.pheromone_client.calculate_dynamic_weight(
                    specialist_type, domain, base_weight=0.2
                )
            else:
                pheromone_weight = 0.2

            # 2. Aplicar multiplicador hierárquico
            hierarchical_weight = await self.hierarchical.calculate_hierarchical_weight(
                specialist_type=specialist_type,
                domain=domain,
                pheromone_weight=pheromone_weight,
                seniority=opinion.get('seniority_level')  # Opcional: da opinião
            )

            weights[specialist_type] = hierarchical_weight

        return weights
```

---

## 5. Esquema de Dados

### 5.1 SpecialistVote Atualizado

```python
class SpecialistVote(BaseModel):
    specialist_type: str
    opinion_id: str
    confidence_score: float
    risk_score: float
    recommendation: str
    weight: float
    processing_time_ms: int

    # NOVO CAMPO
    seniority_level: Optional[str] = Field(
        default=None,
        description='Nível de senioridade aplicado (trainee/junior/mid_level/senior/expert)'
    )
    seniority_multiplier: Optional[float] = Field(
        default=None,
        description='Multiplicador de senioridade aplicado (0.5-2.0)'
    )
```

### 5.2 ConsolidatedDecision Atualizado

```python
class ConsensusMetrics(BaseModel):
    # ... campos existentes ...

    # NOVOS CAMPOS
    consensus_method_hierarchical: bool = Field(
        default=False,
        description='Indica se consenso usou hierarquia de senioridade'
    )
    seniority_distribution: Dict[str, int] = Field(
        default_factory=dict,
        description='Distribuição de votos por nível de senioridade'
    )
    weighted_by_seniority: bool = Field(
        default=False,
        description='Indica se pesos foram ajustados por senioridade'
    )
```

---

## 6. Configurações

### 6.1 Variáveis de Ambiente

```bash
# .env
ENABLE_HIERARCHICAL_CONSENSUS=true
DEFAULT_SENIORITY_LEVEL=mid_level
SENIORITY_WEIGHT_FACTOR=1.0

# Sobrescrever senioridade por tipo (opcional)
SPECIALIST_BUSINESS_SENIORITY=senior
SPECIALIST_TECHNICAL_SENIORITY=senior
SPECIALIST_ARCHITECTURE_SENIORITY=expert
SPECIALIST_BEHAVIOR_SENIORITY=mid_level
SPECIALIST_EVOLUTION_SENIORITY=mid_level

# Pesos base por domínio (opcional)
DOMAIN_WEIGHT_BUSINESS_BUSINESS=0.25
DOMAIN_WEIGHT_TECHNICAL_SECURITY=0.30
DOMAIN_WEIGHT_ARCHITECTURE_ARCHITECTURE=0.35
```

### 6.2 Feature Flag

```python
# config/settings.py
enable_hierarchical_consensus: bool = Field(
    default=True,
    description='Habilitar consenso hierárquico (senioridade)'
)
```

---

## 7. Testes

### 7.1 Testes Unitários

```python
# tests/test_hierarchical_weights.py

@pytest.mark.unit
class TestHierarchicalWeightCalculator:
    """Testes de cálculo de pesos hierárquicos"""

    def test_senior_has_more_weight_than_junior(self):
        """Senior deve ter peso 2x maior que junior"""
        # ... implementação ...

    def test_expert_has_max_weight(self):
        """Expert deve ter multiplicador 2.0"""
        # ... implementação ...

    def test_trainee_has_min_weight(self):
        """Trainee deve ter multiplicador 0.5"""
        # ... implementação ...

    def test_weights_normalized_to_max_one(self):
        """Pesos devem ser normalizados para máximo 1.0"""
        # ... implementação ...
```

### 7.2 Testes de Integração

```python
# tests/test_consensus_hierarchical.py

@pytest.mark.integration
class TestConsensusHierarchicalIntegration:
    """Testes de integração do consenso hierárquico"""

    @pytest.mark.asyncio
    async def test_consensus_with_mixed_seniority(self):
        """Testa consenso com especialistas de níveis diferentes"""
        # ... implementação ...

    @pytest.mark.asyncio
    async def test_senior_opinion_overrules_juniors(self):
        """Testa que opinião sénior tem mais peso"""
        # ... implementação ...
```

---

## 8. Métricas e Observabilidade

### 8.1 Métricas Prometheus

```python
# Novas métricas
consensus_hierarchical_weight_total = Histogram(
    'consensus_hierarchical_weight_distribution',
    'Distribuição de pesos hierárquicos aplicados',
    ['seniority_level', 'specialist_type']
)

consensus_seniority_participation = Counter(
    'consensus_seniority_participation_total',
    'Participação de especialistas por senioridade',
    ['seniority_level']
)

consensus_weight_by_seniority = Gauge(
    'consensus_weight_by_seniority',
    'Peso final aplicado por nível de senioridade',
    ['seniority_level']
)
```

### 8.2 Logging

```python
logger.info(
    'Hierarchical consensus applied',
    specialist_type=specialist_type,
    seniority=seniority.value,
    base_weight=pheromone_weight,
    seniority_multiplier=seniority_multiplier,
    final_weight=hierarchical_weight
)
```

---

## 9. Rollback Plan

Se algo der errado:

1. **Feature Flag**: Desabilitar via `ENABLE_HIERARCHICAL_CONSENSUS=false`
2. **Config Revert**: Voltar para pesos estáticos (0.2)
3. **Código**: Commit de rollback preparado

---

## 10. Dependências

- ✅ Código do `ConsensusOrchestrator` existente
- ✅ Sistema de feromônios implementado
- ✅ Structlog configurado
- ✅ Prometheus configurado

---

## 11. Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|------------|
| Pesos muito discrepantes | Média | Alto | Normalização + limites |
| Configuração complexa | Baixa | Médio | Defaults sensatos |
| Performance | Baixa | Baixo | Cache de senioridade |
| Backward compatibility | Baixa | Alto | Feature flag |

---

## 12. Critérios de Aceite

- [ ] Especialistas `senior` têm peso ≥ 1.5x de `mid_level`
- [ ] Especialistas `expert` têm peso 2x de `mid_level`
- [ ] Especialistas `trainee` têm peso 0.5x de `mid_level`
- [ ] Pesos finais são normalizados para máximo 1.0
- [ ] `SpecialistVote` inclui `seniority_level`
- [ ] `ConsensusMetrics` inclui `seniority_distribution`
- [ ] Feature flag permite desabilitar funcionalidade
- [ ] Todos os testes passam (unitários + integração)
- [ ] Métricas Prometheus são registadas

---

## 13. Próximos Passos

1. Criar `src/models/seniority.py` com enums e configurações
2. Criar `src/services/hierarchical_weights.py`
3. Modificar `ConsensusOrchestrator` para integrar pesos hierárquicos
4. Atualizar `SpecialistVote` e `ConsolidatedDecision`
5. Adicionar configurações em `settings.py`
6. Escrever testes unitários e integração
7. Atualizar documentação e feature-map
8. Deploy para staging
9. Validar com testes E2E
10. Deploy para produção

---

**Estado:** Pronto para implementação
**Atribuído:** TBD
**Sprint:** FASE-3
