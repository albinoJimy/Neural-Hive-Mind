# EPIC-301: Workflow Generation - architect-agent

**ID:** EPIC-301
**Priority:** P1 - Alta
**Effort:** L (3 semanas)
**Service:** architect-agent

## Resumo

Completar workflow generation em architect-agent. Atualmente 50% implementado com básico de workflows lineares. Precisa: workflows condicionais, paralelos, loops, retries, e compensação.

## Arquivos a Criar/Modificar

### Novos:
- `src/workflows/conditional_workflow.py` - Workflows com branches
- `src/workflows/parallel_workflow.py` - Workflows paralelos
- `src/workflows/compensation_workflow.py` - Saga compensation
- `src/generators/temporal_generator.py` - Gera código Temporal

### Modificar:
- `src/services/architect_engine.py` - Integrar novos tipos
- `src/api/workflows.py` - Novos endpoints

## Critérios
- [ ] Workflows condicionais (if/else)
- [ ] Workflows paralelos (fan-out/fan-in)
- [ ] Loops e iterações
- [ ] Retries com backoff
- [ ] Saga compensation
- [ ] Geração de código Temporal
