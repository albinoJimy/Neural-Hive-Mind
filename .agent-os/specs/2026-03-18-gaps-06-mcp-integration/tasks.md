# Spec Tasks

## Tasks

- [x] 1. Scout MCP Server - Servidor MCP para descoberta de código ✅
  - [x] 1.1 Write tests para Scout MCP Server
  - [x] 1.2 Implementar ferramenta `list_files`
  - [x] 1.3 Implementar ferramenta `search_code`
  - [x] 1.4 Implementar ferramenta `analyze_structure`
  - [x] 1.5 Implementar handler JSON-RPC 2.0
  - [x] 1.6 Configurar stdio transport
  - [x] 1.7 Verificar todos os testes passam

- [x] 2. Optimizer MCP Server - Servidor MCP para otimização ✅
  - [x] 2.1 Write tests para Optimizer MCP Server
  - [x] 2.2 Implementar ferramenta `suggest_refactors`
  - [x] 2.3 Implementar ferramenta `analyze_performance`
  - [x] 2.4 Implementar ferramenta `optimize_queries`
  - [x] 2.5 Implementar handler JSON-RPC 2.0
  - [x] 2.6 Configurar stdio transport
  - [x] 2.7 Verificar todos os testes passam

- [ ] 3. MCP Client SDK - Biblioteca para agentes especializados
  - [ ] 3.1 Write tests para MCPClient
  - [ ] 3.2 Implementar classe MCPClient
  - [ ] 3.3 Implementar execute_tool()
  - [ ] 3.4 Implementar list_tools()
  - [ ] 3.5 Implementar execute_batch()
  - [ ] 3.6 Criar pacote pip instalável
  - [ ] 3.7 Verificar todos os testes passam

- [ ] 4. Queen Agent MCP Orchestration - Integração Queen Agent
  - [ ] 4.1 Write tests para MCPToolOrchestrator
  - [ ] 4.2 Implementar MCPToolOrchestrator
  - [ ] 4.3 Implementar execute_tools_parallel()
  - [ ] 4.4 Implementar execute_tools_sequence()
  - [ ] 4.5 Implementar agregação de resultados
  - [ ] 4.6 Integrar com Queen Agent main.py
  - [ ] 4.7 Verificar todos os testes passam

- [ ] 5. MongoDB Persistence - Logs e métricas MCP
  - [ ] 5.1 Write tests para MCPExecutionRepository
  - [ ] 5.2 Criar migrations para coleções MCP
  - [ ] 5.3 Implementar MCPExecutionRepository
  - [ ] 5.4 Implementar log de execuções
  - [ ] 5.5 Implementar agregação de métricas
  - [ ] 5.6 Implementar TTL em mcp_tool_executions
  - [ ] 5.7 Verificar todos os testes passam

- [ ] 6. REST API - Endpoints MCP Queen Agent
  - [ ] 6.1 Write tests para MCP Router
  - [ ] 6.2 Implementar POST /api/v1/mcp/execute
  - [ ] 6.3 Implementar GET /api/v1/mcp/tools
  - [ ] 6.4 Implementar POST /api/v1/mcp/tools/{server}/execute
  - [ ] 6.5 Implementar error handlers
  - [ ] 6.6 Verificar todos os testes passam

- [ ] 7. Testes de Integração E2E
  - [ ] 7.1 Escrever teste E2E: Scout MCP → Queen Agent → Result
  - [ ] 7.2 Escrever teste E2E: Optimizer MCP → Queen Agent → Result
  - [ ] 7.3 Escrever teste E2E: Paralelismo de tools
  - [ ] 7.4 Escrever teste E2E: Timeout e error handling
  - [ ] 7.5 Escrever teste E2E: SDK Client → MCP Server
  - [ ] 7.6 Verificar todos os testes passam

- [ ] 8. Docker e Deploy
  - [x] 8.1 Criar Dockerfile para Scout MCP Server ✅
  - [x] 8.2 Criar Dockerfile para Optimizer MCP Server ✅
  - [ ] 8.3 Atualizar docker-compose para MCP servers
  - [ ] 8.4 Configurar health checks
  - [ ] 8.5 Verificar deploy local

## Progresso GAPS-06: 25% (2/8 tasks)

**Concluído:**
- Task 1: Scout MCP Server (20 testes) ✅
- Task 2: Optimizer MCP Server (19 testes) ✅
- Task 8.1: Dockerfile Scout MCP Server ✅
- Task 8.2: Dockerfile Optimizer MCP Server ✅
