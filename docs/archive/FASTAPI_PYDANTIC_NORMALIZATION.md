# FastAPI/Pydantic Normalization

Versoes canonicas por `versions.txt`: FastAPI 0.104.1, Uvicorn 0.24.0, Pydantic 2.5.3. Tabela abaixo resume ajustes e status de testes.

| Servico | FastAPI Antes | FastAPI Depois | Pydantic Antes | Pydantic Depois | Status Testes |
|---------|---------------|----------------|----------------|-----------------|---------------|
| explainability-api | 0.109.0 | 0.104.1 | 2.5.3 | 2.5.3 | Pendente |
| code-forge | >=0.104.0 | 0.104.1 | >=2.4.0 | 2.5.3 | Pendente |
| guard-agents | 0.104.1 | 0.104.1 | 2.5.0 | 2.5.3 | Pendente |
| sla-management-system | 0.104.1 | 0.104.1 | 2.5.0 | 2.5.3 | Pendente |
| mcp-tool-catalog | 0.104.1 | 0.104.1 | 2.5.0 | 2.5.3 | Pendente |
| orchestrator-dynamic | >=0.104.0 | 0.104.1 | >=2.5.0 | 2.5.3 | Pendente |
| consensus-engine | >=0.104.1 | 0.104.1 | >=2.5.2 | 2.5.3 | Pendente |
| specialist-behavior | >=0.104.1 | 0.104.1 | >=2.5.2 | 2.5.3 | Pendente |
| specialist-business | >=0.104.1 | 0.104.1 | >=2.5.2 | 2.5.3 | Pendente |
| specialist-architecture | >=0.104.1 | 0.104.1 | >=2.5.2 | 2.5.3 | Pendente |
| specialist-technical | >=0.104.1 | 0.104.1 | >=2.5.2 | 2.5.3 | Pendente |
| specialist-evolution | >=0.104.1 | 0.104.1 | >=2.5.2 | 2.5.3 | Pendente |
| semantic-translation-engine | >=0.104.1 | 0.104.1 | >=2.5.2 | 2.5.3 | Pendente |
| memory-layer-api | >=0.104.1 | 0.104.1 | >=2.5.2 | 2.5.3 | Pendente |
| scout-agents | >=0.104.1 | 0.104.1 | >=2.5.2 | 2.5.3 | Pendente |
| worker-agents | >=0.104.1 | 0.104.1 | >=2.5.2 | 2.5.3 | Pendente |
| self-healing-engine | >=0.104.1 | 0.104.1 | >=2.5.0 | 2.5.3 | Pendente |
| queen-agent | 0.104.1 | 0.104.1 | >=2.5.2 | 2.5.3 | Pendente |
| execution-ticket-service | 0.104.1 | 0.104.1 | >=2.5.2 | 2.5.3 | Pendente |
| analyst-agents | 0.104.1 | 0.104.1 | >=2.5.2 | 2.5.3 | Pendente |
| gateway-intencoes | 0.104.1 | 0.104.1 | pydantic[email]>=2.5.2 | pydantic[email]==2.5.3 | Pendente |

## Checklist de Validacao
- [ ] Todos os requirements.txt atualizados
- [ ] Builds Docker bem-sucedidos
- [ ] Testes unitarios passando
- [ ] Testes de integracao passando
- [ ] Validacoes Pydantic funcionando corretamente
- [ ] Endpoints FastAPI respondendo corretamente
- [ ] Documentacao atualizada
