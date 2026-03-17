# Spec Requirements Document

> Spec: GAPS-04 Explainability API Enhancement
> Created: 2026-03-17
> Status: Planning

## Overview

Completar a implementação da Explainability API do Neural-Hive-Mind, integrando com o consenso hierárquico (GAPS-03) e adicionando métodos de explicação avançados (LIME/SHAP) para fornecer transparência completa nas decisões multi-agente.

## User Stories

### História 1: Auditor Explica Decisões

Como auditor de compliance, quero visualizar a contribuição detalhada de cada especialista na decisão final, incluindo pesos hierárquicos e fatores de reasoning, para validar que decisões críticas seguem regulamentos.

**Fluxo:**
1. Auditor consulta decisão por decision_id
2. Sistema retorna explicação completa com:
   - Peso de cada especialista (incluindo senioridade)
   - Fatores que influenciaram cada opinião
   - Atribuição de features (SHAP values)
   - Justificativa narrativa

### História 2: Desenvolvedor Debuga Decisão

Como desenvolvedor, quero entender porque uma intenção foi rejeitada, com análise de contribuição de cada fator, para ajustar o sistema.

**Fluxo:**
1. Desenvolvedor consulta explicação por plan_id
2. Sistema retorna análise de contribuição:
   - Features que mais contribuíram (positivo/negativo)
   - Opiniões divergentes e seus motivos
   - Sugestões de ajuste

### História 3: Analista Monitora Qualidade

Como analista de operações, quero métricas de qualidade das explicações geradas, para garantir transparência adequada.

**Fluxo:**
1. Analista consulta endpoint de métricas
2. Sistema retorna:
   - Taxa de explicações completas vs parciais
   - Score médio de explicabilidade
   - Decisões sem explicação adequada

## Spec Scope

1. **Integração Hierárquica** - Adicionar campos de senioridade e pesos hierárquicos nas explicações geradas
2. **Feature Attribution** - Implementar cálculo de SHAP values para atribuição de features nas decisões
3. **Reasoning Extraction** - Extrair e estruturar reasoning factors das opiniões dos especialistas
4. **Explanation Quality Metrics** - Calcular scores de qualidade das explicações (completude, clareza, especificidade)
5. **Multi-Format Output** - Suportar JSON (API), texto (narrativa) e HTML (dashboard)

## Out of Scope

- Interface visual de dashboard (apenas API)
- Re-treino de modelos baseado em explicações
- Explicações em tempo real (streaming) - pode ser GAPS-05
- Multi-idioma nas explicações

## Expected Deliverable

1. API expõe endpoint `/api/v1/explainability/{decision_id}` com campos hierárquicos
2. SHAP calculator gera attribution scores para cada opinião de especialista
3. Explanation quality metrics calculadas e armazenadas no ledger
4. Testes de integração validam fluxo completo desde consenso até explicação
