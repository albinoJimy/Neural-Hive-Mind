# Napkin Runbook — Neural-Hive-Mind

## Curation Rules
- Re-priorizar a cada leitura.
- Manter apenas notas recorrentes e de alto valor.
- Máximo 10 itens por categoria.
- Cada item inclui data + "Do instead".
- Documentar sempre em português.

---

## Deploy & CI/CD (Highest Priority)

1. **[2026-03-17] Deploy via commit + push apenas**
   O CI/CD é automático. Nunca fazer builds manuais ou deploys directos.
   Do instead: `git commit` + `git push` → pipeline activa automaticamente.

2. **[2026-03-17] Verificar pipeline após push**
   Nunca declarar ticket completo sem verificar status do pipeline.
   Do instead: `gh run list --limit 1` ou aguardar notificação.

3. **[2026-03-17]kubectl rollout restart para deployments**
   Para actualização de serviços, usar rollout restart não full delete.
   Do instead: `kubectl rollout restart deployment/<nome> -n <namespace>`.

4. **[2026-03-17] CI validation jobs podem falhar sem bloquear**
   Hadolint e base image checks falham mas não bloqueiam código ML.
   Do instead: Focar nos testes unitários/E2E para validar código.

---

## Motor MongoDB 3.x

1. **[2026-03-09] Database objects não implementam truthiness**
   Motor 3.7.1+ lança erro se usar `if not db:` para validar.
   Do instead: Comparar com `None`: `if db is None:` ou remover verificação.

2. **[2026-03-09] Acesso MongoDB: client[db_name][collection]**
   Nova sintaxe requer acesso via client em vez de `.db[collection]`.
   Do instead: `client[db_name][collection]` em vez de `motor_client.db[collection]`.

---

## Testing & Validation

1. **[2026-03-04] Validação E2E: fluxo aprovação completo**
   Teste deve seguir: Intent → Gateway → STE → Consensus → Orchestrator → Approval → Worker.
   Do instead: Usar IDs fixos do teste em `docs/test-raw-data/` para rastreio.

2. **[2026-03-06] Worker Agents: validar parâmetros antes de executar**
   Executores exigem parâmetros específicos (collection, input_data, policy_path).
   Do instead: Chamar `validate_required_parameters()` antes de cada execução.

---

## ML & Features

1. **[2026-03-16] Dados sintéticos = scores constantes (0.5)**
   Modelos treinados com dados sintéticos retornam sempre confiança 0.5.
   Do instead: Coletar feedbacks humanos reais antes de treinar.

2. **[2026-03-16] Features NLP requerem texto original**
   `nlp_features` só são geradas se `intent_raw_text` estiver presente.
   Do instead: Garantir que `original_intent_text` flui pelo pipeline completo.

3. **[2026-03-17] Modelo v6 com NLP: F1-Score 0.91**
   Treinado com 75 feedbacks reais contendo features NLP (text_length, domain, action).
   Do instead: Usar `ml_pipelines/training/retrain_v6_with_nlp.py` para retraining.

---

## Code Conventions

1. **[2026-03-17] Português para documentação**
   Todo o código, comentários e docs devem ser em português.
   Do instead: Sempre escrever em PT, exceto nomes técnicos/variáveis.

2. **[2026-03-17] Verificar duplicações antes de criar**
   Nunca assumir que componente não existe.
   Do instead: `Grep` + `Glob` para verificar duplicação antes de criar novo arquivo.

---

## MCP Integration

1. **[2026-03-18] MCP Servers: HTTP REST (não FastMCP)**
   FastMCP usa stdio/SSE incompatível com Kubernetes probes.
   Do instead: Usar `http.server.HTTPServer` com endpoints `/health`, `/tools`, `/execute`.

2. **[2026-03-18] HTTPMCPClient para comunicação MCP**
   Clientes queen-agent usam REST em vez de stdio.
   Do instead: `HTTPMCPClient(server_url, timeout)` com métodos `connect()`, `list_tools()`, `execute_tool()`.

3. **[2026-03-18] Helm ConfigMaps para injetar código MCP**
   Código montado em `/app/src` via ConfigMap (sem PVC).
   Do instead: Criar ConfigMap com código, montar `readOnly: true` no pod.

---

## Shell & Tools

1. **[2026-03-17] dev-planner skill para planeamento**
   Usar dev-planner para specs, tickets e handoffs.
   Do instead: Activar skill dev-planner para tarefas de desenvolvimento.

---

## User Directives

1. **[2026-03-17] Fazer exactamente o solicitado**
   Nada mais, nada menos.
   Do instead: Confirmar requisitos antes de expandir scope.

2. **[2026-03-17] Nunca modificar ficheiros em /tests**
   Testes são o contrato de implementação.
   Do instead: Escrever testes antes, implementar depois.
