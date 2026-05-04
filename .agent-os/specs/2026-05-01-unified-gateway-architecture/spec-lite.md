# Spec Summary (Lite)

## Unified Gateway e Arquitetura Compartilhada

Implementar um ponto único de entrada (:7999) que classifica automaticamente intenções e roteia para fluxos A-F, G ou H, eliminando >3.000 LOC de duplicações em NLU, PII, Approval e autenticação.

### Problema
Múltiplos gateways descentralizados com código duplicado: NLU (~1.700 LOC), PII (~842 LOC), Approval (~2.000 LOC), autenticação em cada serviço.

### Solução
- **Unified Gateway (:7999)** - Classifica e roteia automaticamente
- **NLU Service (:8020)** - Serviço centralizado de NLP
- **PII Service (:8021)** - Serviço centralizado de proteção de dados
- **Approval Core Package** - Biblioteca compartilhada de aprovações

### Impacto
- Latência adicional <20ms (p95)
- >3.000 LOC de duplicação removidos
- Clientes usam único endpoint `/api/v1/nhm/request`
- Classificação automática com >90% confiança

### Timeline
10 semanas (~2.5 meses) em 6 sprints
