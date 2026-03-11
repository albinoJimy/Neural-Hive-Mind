# Tasks

- [x] 1. **Completar Approval Gate** - Implementar commit + push antes de criar MR
  - [x] 1.1 Escrever testes para ApprovalGate._commit_and_push()
  - [x] 1.2 Implementar método `_commit_and_push()` em approval_gate.py
  - [x] 1.3 Modificar `check_approval()` para chamar `_commit_and_push()` antes de criar MR
  - [x] 1.4 Adicionar parâmetro `target_repo` aos Execution Tickets de teste
  - [x] 1.5 Verificar se métodos GitClient necessários existem e funcionam
  - [x] 1.6 Testar fluxo completo: generate → commit → push → MR
  - [x] 1.7 Verificar todos os testes passan

- [x] 2. **Corrigir TODO validator.py** - Medir execution_time_ms real
  - [x] 2.1 Escrever testes para medição de tempo de validação
  - [x] 2.2 Implementar wrapper `run_with_timing()` para medir tempo de cada validação
  - [x] 2.3 Substituir hardcoded `0` por tempo medido no feedback MCP
  - [x] 2.4 Adicionar métrica Prometheus de tempo por ferramenta
  - [x] 2.5 Verificar todos os testes passan

- [x] 3. **Habilitar workspace cleanup** - Evitar vazamento de disco
  - [x] 3.1 Escrever testes para cleanup com retry
  - [x] 3.2 Melhorar método `_cleanup_workspace()` com retry e tratamento de PermissionError
  - [x] 3.3 Descomentar chamada de cleanup no finally de `run_tests()`
  - [x] 3.4 Adicionar configuração para desabilitar cleanup se necessário (debug)
  - [x] 3.5 Testar com múltiplas execuções simultâneas
  - [x] 3.6 Verificar todos os testes passan

- [x] 4. **Implementar validação de licenças** - Detectar licenças problemáticas
  - [x] 4.1 Criar arquivo license_validator.py com classe LicenseValidator
  - [x] 4.2 Implementar método validate_licenses() que analisa SBOM
  - [x] 4.3 Adicionar método get_artifact_sbom() em MongoDBClient
  - [x] 4.4 Integrar LicenseValidator no Validator principal
  - [x] 4.5 Definir listas de licenças permitidas/problemáticas
  - [x] 4.6 Escrever testes unitários para LicenseValidator
  - [x] 4.7 Verificar todos os testes passam

- [x] 5. **Expandir Test Runner** - Suportar JavaScript/TypeScript
  - [x] 5.1 Implementar método _run_nodejs_tests() com Jest
  - [x] 5.2 Modificar run_tests() para selecionar executor baseado na linguagem
  - [x] 5.3 Adicionar geração de package.json mínimo
  - [x] 5.4 Implementar parse de cobertura do Jest
  - [x] 5.5 Escrever testes para executor Node.js
  - [x] 5.6 Verificar todos os testes passan

- [ ] 6. **Templates versionados** - Usar Git tags para versionamento
  - [ ] 6.1 Adicionar método list_tags() em GitClient
  - [ ] 6.2 Adicionar método checkout_tag() em GitClient
  - [ ] 6.3 Modificar _load_and_index_templates() para suportar tags
  - [ ] 6.4 Adicionar parâmetro template_version nos Execution Tickets
  - [ ] 6.5 Escrever testes para versionamento de templates
  - [ ] 6.6 Documentar como usar templates versionados
  - [ ] 6.7 Verificar todos os testes passam

- [ ] 7. **Testes E2E e Integração**
  - [ ] 7.1 Escrever teste E2E do pipeline completo com Approval Gate
  - [ ] 7.2 Escrever teste E2E com validação de licenças
  - [ ] 7.3 Escrever teste E2E para múltiplas linguagens
  - [ ] 7.4 Executar suite completa de testes
  - [ ] 7.5 Gerar relatório de cobertura
