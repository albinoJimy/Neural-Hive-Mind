# Technical Specification

This is the technical specification for the spec detailed in @.agent-os/specs/2026-03-17-gaps-04-explainability-api/spec.md

## Technical Requirements

### GAPS-04-01: Integração Hierárquica
- Estender `ExplainabilityConsolidator` para incluir campos de senioridade
- Adicionar `seniority_distribution` na explicação detalhada
- Incluir `seniority_multiplier` para cada opinião de especialista
- Mostrar peso final calculado (pheromone × seniority × domain)

### GAPS-04-02: Feature Attribution Calculator
- Criar `ShapCalculator` em `explainability-api/src/services/shap_calculator.py`
- Implementar Kernel SHAP para explicação de decisões não-lineares
- Gerar attribution scores por feature (confidence, risk, reasoning_factors)
- Suportar batch processing para múltiplas decisões

### GAPS-04-03: Reasoning Extraction
- Criar `ReasoningExtractor` em `consensus-engine/src/services/reasoning_extractor.py`
- Extrair factores-chave do texto de reasoning
- Categorizar factores: técnico, negócio, segurança, compliance
- Gerar structured output com citations

### GAPS-04-04: Explanation Quality Metrics
- Criar `ExplanationQualityScorer` em `explainability-api/src/services/quality_scorer.py`
- Métricas: completude (0-1), clareza (0-1), especificidade (0-1)
- Score agregado = média ponderada das 3 métricas
- Armazenar score no ledger `explainability_ledger`

### GAPS-04-05: Multi-Format Output
- JSON: formato padrão da API (existente)
- Texto: narrativa natural para humanos
- HTML: para integração com dashboard

## External Dependencies

- **shap** - Biblioteca para SHAP values (já em requirements.txt de ML)
- **Justification:** Método padrão de indústria para feature attribution em modelos de ML

## API Extensions

### GET /api/v1/explainability/{decision_id}
**Response extendido:**
```json
{
  "explainability_token": "...",
  "decision_id": "...",
  "consensus_process": {
    "method": "hierarchical_bayesian",
    "hierarchical_weights": {
      "enabled": true,
      "seniority_distribution": {
        "senior": 2,
        "expert": 1,
        "mid_level": 2
      }
    }
  },
  "specialist_opinions": [
    {
      "specialist_type": "business",
      "seniority_level": "senior",
      "seniority_multiplier": 1.5,
      "domain_weight": 0.25,
      "final_weight": 0.1875,
      "shap_values": {
        "confidence": 0.35,
        "risk": -0.15,
        "technical_factor": 0.05
      }
    }
  ],
  "explanation_quality": {
    "completeness": 0.92,
    "clarity": 0.85,
    "specificity": 0.78,
    "overall_score": 0.85
  }
}
```

### POST /api/v1/explainability/generate
**Novo endpoint para gerar explicação sob demanda:**
```json
{
  "decision_id": "...",
  "format": "html",
  "include_shap": true,
  "include_reasoning_extraction": true
}
```

## Integration Points

### Consensus Engine → Explainability API
- `ConsensusOrchestrator` publica evento `consensus.decision.created`
- `ExplainabilityAPI` consome e gera explicação detalhada
- Tópico Kafka: `consensus.explanations`

### Approval Service → Explainability API
- `ApprovalService` envia `approval_request_id` na consulta
- `ExplainabilityAPI` enriquece com contexto de aprovação

## Performance Requirements

- Tempo de geração de explicação < 500ms (sem SHAP)
- Tempo de geração de explicação < 2s (com SHAP)
- Throughput: >100 explicações/segundo
- Cache: TTL 1h para explicações frequentes
