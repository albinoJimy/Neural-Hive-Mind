# EPIC-203: Feature Lineage Tracking

**ID:** EPIC-203
**Status:** Pending
**Priority:** P1 - Alta
**Effort:** L (3 semanas)
**Related Service:** feature-store

---

## Resumo Executivo

Implementar rastreamento completo de lineage para as 26 features do feature-store. Atualmente 0% de implementação - nenhum rastreamento de origem, transformações ou dependências. Referência: memory-layer-api tem lineage completo que pode ser replicado.

---

## Análise Técnica

### Modelo Atual (sem lineage)

```python
class FeatureVector(BaseModel):
    feature_id: str
    plan_id: str
    computed_at: datetime
    
    # 26 features em 4 categorias
    metadata: MetadataFeatures
    ontology: Optional[OntologyFeatures]
    graph: Optional[GraphFeatures]
    embedding: Optional[EmbeddingFeatures]
    
    # ❌ SEM campos de lineage
```

### Campos Ausentes

| Campo | Descrição | Prioridade |
|-------|-----------|------------|
| `lineage_id` | ID único do rastreamento | Alta |
| `source_type` | Tipo de origem (cognitive_plan, derived, etc.) | Alta |
| `source_plan_ids` | IDs dos planos originais | Alta |
| `data_sources` | Fontes de dados (mongodb, neo4j, etc.) | Alta |
| `transformation_type` | Tipo de transformação aplicada | Média |
| `computation_version` | Versão do pipeline | Média |
| `feature_dependencies` | Features que dependem desta | Média |
| `transformation_history` | Histórico de transformações | Baixa |

---

## Ticket EPIC-203-01: Criar Modelos de Lineage

**ID:** TICKET-EPIC-203-01
**Priority:** Alta
**Effort:** S (3 dias)

### Tasks

- [ ] 203.01 Criar `src/models/lineage.py`
- [ ] 203.02 Implementar `FeatureLineage` model
- [ ] 203.03 Implementar `TransformationType` enum
- [ ] 203.04 Implementar `SourceType` enum
- [ ] 203.05 Implementar `LineageMetadata` model
- [ ] 203.06 Estender `FeatureVector` com campos `lineage_id`, `lineage`
- [ ] 203.07 Criar tests/test_lineage_models.py
- [ ] 203.08 Testar validação Pydantic

### Modelo FeatureLineage

```python
class FeatureLineage(BaseModel):
    """Rastreamento de origem e transformações de features"""
    
    # Identificação
    lineage_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    feature_id: str
    plan_id: str
    
    # Origem
    source_type: Literal["cognitive_plan", "derived", "aggregated", "enriched"]
    source_plan_ids: List[str] = Field(default_factory=list)
    data_sources: List[str] = Field(default_factory=list)
    
    # Transformação
    transformation_type: Literal["computed", "merged", "filtered", "enriched"]
    computation_version: str  # "v1.0.0"
    computation_hash: str  # Hash do código de computação
    
    # Dependências
    feature_dependencies: List[str] = Field(default_factory=list)
    parent_lineage_ids: List[str] = Field(default_factory=list)
    
    # Auditoria
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    created_by: str = "feature-store-service"
    modified_at: Optional[datetime] = None
    modified_count: int = Field(default=0)
    
    # Metadados
    transformation_metadata: Dict[str, Any] = Field(default_factory=dict)
```

### Critérios de Aceite
- [ ] Modelos criados
- [ ] Validação Pydantic funcionando
- [ ] Testes passando

---

## Ticket EPIC-203-02: Criar Lineage Tracker

**ID:** TICKET-EPIC-203-02
**Priority:** Alta
**Effort:** XL (1 semana)

### Tasks

- [ ] 203.09 Criar `src/services/lineage_tracker.py`
- [ ] 203.10 Implementar `LineageTracker` class
- [ ] 203.11 Implementar `track_feature()` - rastreia nova feature
- [ ] 203.12 Implementar `update_lineage()` - atualiza lineage existente
- [ ] 203.13 Implementar `get_lineage_tree()` - árvore de dependências
- [ ] 203.14 Implementar `get_impact_analysis()` - impacto downstream
- [ ] 203.15 Implementar `validate_integrity()` - valida ciclos
- [ ] 203.16 Implementar `compute_computation_hash()` - hash do código
- [ ] 203.17 Criar tests/test_lineage_tracker.py
- [ ] 203.18 Testar rastreamento de features
- [ ] 203.19 Testar árvore de dependências
- [ ] 203.20 Testar análise de impacto

### LineageTracker

```python
class LineageTracker:
    def __init__(self, mongo_client, neo4j_client):
        self.mongo_client = mongo_client
        self.neo4j_client = neo4j_client
        self.computation_version = "v1.0.0"
    
    async def track_feature(
        self,
        feature_id: str,
        plan_id: str,
        source_type: SourceType,
        data_sources: List[str],
        transformation_type: TransformationType
    ) -> FeatureLineage:
        """Rastreia nova feature e persiste lineage."""
        
        # Criar lineage
        lineage = FeatureLineage(
            feature_id=feature_id,
            plan_id=plan_id,
            source_type=source_type,
            data_sources=data_sources,
            transformation_type=transformation_type,
            computation_version=self.computation_version,
            computation_hash=self._compute_computation_hash()
        )
        
        # Persistir no MongoDB
        await self.mongo_client.save_lineage(lineage)
        
        # Criar relacionamento no Neo4j
        await self.neo4j_client.create_lineage_relationship(
            feature_id,
            lineage.source_plan_ids,
            "DERIVED_FROM"
        )
        
        return lineage
    
    async def get_lineage_tree(
        self,
        feature_id: str,
        max_depth: int = 5
    ) -> Dict:
        """Obter árvore completa de lineage."""
        
        # Buscar lineage no MongoDB
        lineage = await self.mongo_client.get_lineage(feature_id)
        
        # Buscar pais no Neo4j
        parents = await self.neo4j_client.get_lineage_parents(
            feature_id,
            max_depth=max_depth
        )
        
        # Buscar filhos no Neo4j
        children = await self.neo4j_client.get_lineage_children(
            feature_id,
            max_depth=max_depth
        )
        
        return {
            "feature_id": feature_id,
            "lineage": lineage,
            "upstream": parents,
            "downstream": children,
            "tree_depth": self._calculate_tree_depth(parents, children)
        }
    
    async def get_impact_analysis(
        self,
        feature_id: str
    ) -> Dict:
        """Analisa impacto downstream se feature mudar."""
        
        # Buscar todas as features que dependem desta
        downstream = await self.neo4j_client.get_lineage_children(
            feature_id,
            max_depth=10  # Buscar profundamente
        )
        
        # Categorizar impacto
        impact = {
            "feature_id": feature_id,
            "direct_dependencies": len(downstream.get("depth_1", [])),
            "total_downstream": sum(
                len(v) for v in downstream.values() 
                if isinstance(v, list)
            ),
            "affected_plans": self._extract_affected_plans(downstream),
            "critical_path": self._find_critical_path(downstream)
        }
        
        return impact
    
    async def validate_integrity(
        self,
        feature_id: str
    ) -> Dict:
        """Valida integridade do lineage (sem ciclos, timestamps ok)."""
        
        # Buscar lineage tree
        tree = await self.get_lineage_tree(feature_id)
        
        # Verificar ciclos
        has_cycle = self._check_for_cycles(tree)
        
        # Verificar timestamps
        timestamps_valid = self._validate_timestamps(tree)
        
        # Verificar consistência de datasources
        datasources_consistent = self._validate_datasources(tree)
        
        return {
            "feature_id": feature_id,
            "has_cycle": has_cycle,
            "timestamps_valid": timestamps_valid,
            "datasources_consistent": datasources_consistent,
            "valid": not has_cycle and timestamps_valid and datasources_consistent
        }
    
    def _compute_computation_hash(self) -> str:
        """Computa hash do código de computação."""
        # Ler arquivo computation.py
        computation_code = Path("src/services/computation.py").read_text()
        # Hash do código
        return hashlib.sha256(computation_code.encode()).hexdigest()[:16]
```

### Critérios de Aceite
- [ ] LineageTracker criado
- [ ] Rastreamento funcionando
- [ ] Árvore de dependências funcionando
- [ ] Análise de impacto funcionando
- [ ] Validação de integridade funcionando
- [ ] Integração MongoDB + Neo4j funcionando

---

## Ticket EPIC-203-03: Integrar Lineage no Feature Store

**ID:** TICKET-EPIC-203-03
**Priority:** Alta
**Effort:** M (4 dias)

### Tasks

- [ ] 203.21 Modificar `src/services/feature_store.py`
- [ ] 203.22 Integrar LineageTracker no construtor
- [ ] 203.23 Modificar `save_features()` para rastrear lineage
- [ ] 203.24 Modificar `get_features()` para incluir lineage
- [ ] 203.25 Modificar `src/services/computation.py`
- [ ] 203.26 Adicionar computation_hash no resultado
- [ ] 203.27 Modificar `src/api/routers/features.py`
- [ ] 203.28 Adicionar endpoint `GET /api/v1/features/{plan_id}/lineage`
- [ ] 203.29 Adicionar endpoint `GET /api/v1/features/{plan_id}/lineage/tree`
- [ ] 203.30 Adicionar endpoint `GET /api/v1/features/{plan_id}/lineage/impact`
- [ ] 203.31 Adicionar endpoint `GET /api/v1/lineage/validate/{plan_id}`
- [ ] 203.32 Testar integração completa

### FeatureStore Refatorado

```python
class FeatureStore:
    def __init__(
        self,
        mongo_client,
        neo4j_client,
        redis_client,
        lineage_tracker  # NOVO
    ):
        self.lineage_tracker = lineage_tracker
        # ...
    
    async def save_features(
        self,
        plan_id: str,
        features: Dict[str, Any]
    ) -> FeatureVector:
        # Computar features (existente)
        computed_features = await self.computation_pipeline.compute(plan_id)
        
        # NOVO: Rastrear lineage
        lineage = await self.lineage_tracker.track_feature(
            feature_id=computed_features.feature_id,
            plan_id=plan_id,
            source_type=SourceType.COGNITIVE_PLAN,
            data_sources=["mongodb", "neo4j"],
            transformation_type=TransformationType.COMPUTED
        )
        
        # Salvar features com lineage
        feature_vector = FeatureVector(
            feature_id=computed_features.feature_id,
            plan_id=plan_id,
            metadata=computed_features.metadata,
            ontology=computed_features.ontology,
            graph=computed_features.graph,
            embedding=computed_features.embedding,
            lineage_id=lineage.lineage_id,  # NOVO
            lineage=lineage  # NOVO
        )
        
        await self.mongo_client.save_feature(feature_vector)
        return feature_vector
    
    async def get_features(
        self,
        plan_id: str,
        include_lineage: bool = False
    ) -> FeatureVector:
        feature_vector = await self.mongo_client.get_feature(plan_id)
        
        # NOVO: Incluir lineage se solicitado
        if include_lineage and feature_vector.lineage_id:
            lineage_tree = await self.lineage_tracker.get_lineage_tree(
                feature_vector.feature_id
            )
            feature_vector.lineage_tree = lineage_tree
        
        return feature_vector
```

### Critérios de Aceite
- [ ] LineageTracker integrado
- [ ] save_features() rastreia lineage
- [ ] get_features() inclui lineage
- [ ] Endpoints novos funcionando
- [ ] Testes E2E passando

---

## Ticket EPIC-203-04: Export/Import Lineage

**ID:** TICKET-EPIC-203-04
**Priority:** Média
**Effort:** S (3 dias)

### Tasks

- [ ] 203.33 Implementar `export_lineage()` - exporta JSON
- [ ] 203.34 Implementar `import_lineage()` - importa JSON
- [ ] 203.35 Adicionar endpoint `POST /api/v1/lineage/export`
- [ ] 203.36 Adicionar endpoint `POST /api/v1/lineage/import`
- [ ] 203.37 Validar schema de export/import
- [ ] 203.38 Testar round-trip

### Critérios de Aceite
- [ ] Export funcionando
- [ ] Import funcionando
- [ ] Round-trip validado

---

## Resumo do Epic

| Ticket | Descrição | Effort | Deliverables |
|--------|-----------|--------|--------------|
| EPIC-203-01 | Modelos de Lineage | 3 dias | FeatureLineage model |
| EPIC-203-02 | Lineage Tracker | 1 semana | Serviço completo |
| EPIC-203-03 | Integração Feature Store | 4 dias | Integração + API |
| EPIC-203-04 | Export/Import | 3 dias | Endpoints |
| **TOTAL** | | **3 semanas** | **Lineage completo** |

---

## Arquitetura Final

```
                    ┌─────────────────────────────────────┐
                    │            API Layer                │
                    │  GET /api/v1/features/{id}/lineage  │
                    │  GET /api/v1/features/{id}/impact   │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────▼───────────────────┐
                    │           FeatureStore               │
                    │  - save_features() + lineage        │
                    │  - get_features() + lineage         │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────▼───────────────────┐
                    │          LineageTracker              │
                    │  - track_feature()                  │
                    │  - get_lineage_tree()              │
                    │  - get_impact_analysis()           │
                    │  - validate_integrity()            │
                    └─────────────────┬───────────────────┘
                                      │
              ┌───────────────────────┴───────────────────────┐
              ▼                                               ▼
    ┌───────────────────┐                          ┌───────────────────┐
    │  MongoDB          │                          │  Neo4j            │
    │  feature_lineage  │                          │  DERIVED_FROM    │
    │  collection      │                          │  relationships   │
    └───────────────────┘                          └───────────────────┘
```

---

## Handoff para Claude Code

```
@~/.agent-os/instructions/execute-tasks.md

Epic: EPIC-203 - Feature Lineage Tracking
Spec: .agent-os/specs/2026-03-31-sprint2-features-incompletas/
```
