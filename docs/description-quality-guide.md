# Guia de Qualidade de Descrições de Tarefas

## 1. Problema Identificado

O **Semantic Translation Engine (STE)** gerava descrições de tarefas extremamente pobres (ex: `"Create operation"`), enquanto os **specialists** dependem fortemente de keywords nas descrições para avaliações heurísticas (fallback final quando ML e SemanticPipeline falham).

**Impacto:**
- Heurísticas retornam scores baixos por não encontrarem keywords relevantes
- Dados de treinamento sintéticos são igualmente pobres
- Modelos ML aprendem de dados de baixa qualidade
- Avaliações de risco imprecisas

## 2. Solução Implementada

Enriquecimento de descrições em **3 camadas**:

### Camada 1: DAG Generator
Arquivo: `services/semantic-translation-engine/src/services/dag_generator.py`

- Injeção de contexto estruturado (risk_band, QoS, security_level, domain)
- Mapeamento de objetivos para verbos descritivos
- Hints de segurança/performance baseados em constraints

### Camada 2: Prompts LLM
Arquivo: `ml_pipelines/training/prompts/cognitive_plan_template.txt`

- Requisitos explícitos de qualidade (15-50 palavras)
- Keywords obrigatórias por domínio
- Exemplos de descrições boas vs. ruins

### Camada 3: Validação de Qualidade
Arquivo: `services/semantic-translation-engine/src/services/description_validator.py`

- Scoring baseado em comprimento, diversidade léxica e keywords
- Validação integrada no fluxo de geração
- Sugestões automáticas de melhoria

## 3. Exemplos de Descrições

### Antes vs. Depois

| Domínio | Antes (Ruim) | Depois (Bom) |
|---------|--------------|--------------|
| security-analysis | `"Validate operation"` | `"Validate user credentials and encrypt session tokens with AES-256 with authentication validation and access control audit (confidential, high priority)"` |
| architecture-review | `"Create operation"` | `"Create and initialize service interface resources following microservice patterns and interface contracts (architecture-review, normal priority)"` |
| performance-optimization | `"Query operation"` | `"Retrieve customer data with indexed queries and cache results for 5 minutes using Redis connection pooling (high priority)"` |
| code-quality | `"Transform operation"` | `"Process and convert data formats with comprehensive error handling and test coverage (code-quality, normal priority)"` |
| business-logic | `"Update operation"` | `"Modify and validate workflow configuration aligned with workflow policies and business KPI metrics (business-logic, critical priority)"` |

### Keywords Obrigatórias por Domínio

| Domínio | Keywords Obrigatórias |
|---------|----------------------|
| security-analysis | auth, encrypt, validate, audit, sanitize, permission, token, credential |
| architecture-review | service, interface, pattern, module, component, api, integration, layer |
| performance-optimization | cache, index, optimize, parallel, async, batch, pool, buffer |
| code-quality | test, error, log, coverage, refactor, lint, exception, monitor |
| business-logic | workflow, kpi, cost, efficiency, process, metric, policy, compliance |

### Keywords por Security Level

| Security Level | Keywords Adicionais |
|----------------|---------------------|
| confidential | encrypt, auth, audit, permission, sanitize, secure, private |
| restricted | encrypt, auth, audit, classified, secret, clearance |
| internal | validate, verify, check, access |
| public | (nenhuma obrigatória) |

## 4. Validação de Qualidade

### Thresholds de Score

| Métrica | Score Mínimo | Peso |
|---------|--------------|------|
| Comprimento (15-50 palavras) | 0.6 | 25% |
| Diversidade Léxica (>0.7) | 0.6 | 20% |
| Keywords de Domínio (≥2) | 0.6 | 35% |
| Keywords de Segurança | 0.6 | 15% |
| Keywords de QoS | 0.6 | 10% |

### Score Final
- **≥ 0.75**: Excelente - descrição de alta qualidade
- **0.60 - 0.74**: Bom - descrição aceitável
- **0.40 - 0.59**: Baixo - descrição precisa de melhorias (auto-correção tentada)
- **< 0.40**: Muito baixo - descrição rejeitada e melhorada automaticamente

### Interpretando Logs

```json
{
  "event": "low_quality_task_description",
  "task_id": "task_0",
  "score": 0.35,
  "issues": ["Descrição muito curta (2 palavras)", "Nenhuma keyword de domínio para security-analysis"],
  "original_description": "Create operation"
}
```

## 5. Impacto em Heurísticas

### Mapeamento de Keywords para Scores de Specialists

**Technical Specialist:**
| Categoria | Keywords | Impacto |
|-----------|----------|---------|
| Security | auth, encrypt, validate, sanitize | +security_score |
| Performance | cache, index, optimize, async | +performance_score |
| Quality | test, error, log, coverage | +code_quality_score |
| Architecture | service, interface, pattern | +architecture_score |

**Business Specialist:**
| Categoria | Keywords | Impacto |
|-----------|----------|---------|
| Value | workflow, kpi, cost, efficiency | +business_value_score |
| Compliance | policy, compliance, audit, regulation | +compliance_score |
| Operations | pipeline, transaction, batch | +operational_score |

### Exemplo de Melhoria

```
Descrição genérica: "Create operation"
- security_score: 0.0 (nenhuma keyword encontrada)
- confidence_score: 0.07 (apenas 2 palavras)

Descrição enriquecida: "Create and initialize user profile with authentication and AES-256 encryption..."
- security_score: 1.0 (5+ keywords: auth, encrypt, profile, user)
- confidence_score: 0.87 (26 palavras)
```

## 6. Retreinamento de Modelos

### Após Enriquecimento

1. **Regenerar datasets:**
```bash
cd ml_pipelines/training
python generate_training_datasets.py \
  --specialist-type technical \
  --num-samples 1000 \
  --validate-schemas true
```

2. **Verificar qualidade dos dados:**
```
📝 Qualidade de Descrições:
  Score médio: 0.825
  Score mínimo: 0.620
  Score máximo: 0.950
  Rejeitados por baixa qualidade: 12
```

3. **Comparar métricas de modelos:**
- Modelos treinados com dados antigos vs. novos
- Espera-se melhoria em accuracy e F1-score

4. **Promover para produção:**
```bash
mlflow models serve -m models:/specialist-technical-model/Production -p 5001
```

## 7. Troubleshooting

### Heurísticas ainda retornam scores baixos

1. Verificar logs do `DescriptionQualityValidator`:
```bash
kubectl logs -n neural-hive semantic-translation-engine-xxx | grep "description_validated"
```

2. Verificar se descrições contêm keywords esperadas:
```bash
kubectl logs -n neural-hive semantic-translation-engine-xxx | grep "domain_keywords_found"
```

3. Verificar score médio de qualidade:
```bash
kubectl logs -n neural-hive semantic-translation-engine-xxx | grep "avg_score"
```

### LLM gera descrições ruins

1. **Ajustar temperatura** (reduzir para mais consistência):
```bash
export LLM_TEMPERATURE=0.5
```

2. **Trocar provider** (usar modelo mais capaz):
```bash
export LLM_PROVIDER=anthropic
export LLM_MODEL=claude-3-sonnet
```

3. **Verificar prompt template** contém requisitos de qualidade:
```bash
cat ml_pipelines/training/prompts/cognitive_plan_template.txt | grep -A 20 "DESCRIPTION QUALITY"
```

### Testes de integração falham

1. Executar testes de comparação:
```bash
pytest tests/integration/test_description_enrichment_impact.py -v
```

2. Verificar arquivo de comparação gerado:
```bash
cat tests/integration/description_enrichment_comparison.json
```

3. Verificar métricas de melhoria:
- security_score improvement ≥ 20%
- confidence_score improvement ≥ 15%
- mitigations_count ≥ 2x

## Referências

- [dag_generator.py](../services/semantic-translation-engine/src/services/dag_generator.py)
- [description_validator.py](../services/semantic-translation-engine/src/services/description_validator.py)
- [cognitive_plan_template.txt](../ml_pipelines/training/prompts/cognitive_plan_template.txt)
- [test_description_enrichment_impact.py](../tests/integration/test_description_enrichment_impact.py)
