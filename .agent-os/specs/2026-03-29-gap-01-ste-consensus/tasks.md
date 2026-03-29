# Tasks - GAP-01: STE-Consensus Topic Fix

## Tasks

- [ ] 1. Atualizar configuração do Semantic Translation Engine
  - [ ] 1.1 Criar teste para validar configuração atual
  - [ ] 1.2 Modificar `settings.py` linha 51: `kafka_plans_topic='plans.ready'`
  - [ ] 1.3 Atualizar docstring do campo
  - [ ] 1.4 Verificar que módulo carrega sem erros
  - [ ] 1.5 Commit: "fix(ste): alterar kafka_plans_topic de cognitive-plans para plans.ready"

- [ ] 2. Atualizar fixtures de testes do STE
  - [ ] 2.1 Criar teste para validar fixture mock_settings
  - [ ] 2.2 Modificar `conftest.py` linha 127: `kafka_plans_topic='plans.ready'`
  - [ ] 2.3 Buscar referências a `cognitive-plans` em todos os testes
  - [ ] 2.4 Atualizar testes que hardcoded o nome do tópico
  - [ ] 2.5 Executar testes unitários: `pytest tests/unit/`
  - [ ] 2.6 Executar testes de integração: `pytest tests/integration/`
  - [ ] 2.7 Commit: "test(ste): atualizar fixtures para usar plans.ready"

- [ ] 3. Validar configuração de infraestrutura
  - [ ] 3.1 Verificar Helm charts já configurados para `plans.ready`
  - [ ] 3.2 Confirmar que tópico `plans.ready` existe no cluster Kafka
  - [ ] 3.3 Validar Schema Registry para `plans.ready-value`
  - [ ] 3.4 Verificar configuração de partições e replicação
  - [ ] 3.5 Documentar descobertas em notas de implementação

- [ ] 4. Executar testes E2E do fluxo completo
  - [ ] 4.1 Iniciar ambiente local com Docker Compose (se necessário)
  - [ ] 4.2 Enviar intenção de teste via Gateway (mock ou real)
  - [ ] 4.3 Verificar em logs do STE: "Publishing to plans.ready"
  - [ ] 4.4 Verificar em logs do Consensus: "Plan received from plans.ready"
  - [ ] 4.5 Validar que especialistas são invocados
  - [ ] 4.6 Validar que decisão é publicada em `cognitive-plans-consolidated`
  - [ ] 4.7 Coletar métricas de latência e throughput
  - [ ] 4.8 Commit: "test(e2e): validar fluxo STE → Consensus com plans.ready"

- [ ] 5. Atualizar documentação técnica
  - [ ] 5.1 Atualizar diagrama de arquitetura com nome correto do tópico
  - [ ] 5.2 Criar/documentar contrato de tópicos Kafka
  - [ ] 5.3 Adicionar entrada em CHANGELOG.md
  - [ ] 5.4 Atualizar documentação de deploy se necessário
  - [ ] 5.5 Commit: "docs(ste): documentar mudança de tópico plans.ready"

- [ ] 6. Preparar e executar deploy
  - [ ] 6.1 Criar PR com todas as mudanças
  - [ ] 6.2 Solicitar review de código
  - [ ] 6.3 Executar CI/CD pipeline (testes + linting)
  - [ ] 6.4 Aguardar aprovação
  - [ ] 6.5 Merge para main
  - [ ] 6.6 Monitorar deploy automático
  - [ ] 6.7 Verificar rolling update sem downtime
  - [ ] 6.8 Validar logs de produção
  - [ ] 6.9 Verificar métricas Prometheus

- [ ] 7. Validação pós-deploy
  - [ ] 7.1 Monitorar logs por 24 horas
  - [ ] 7.2 Verificar alertas (sem disparos)
  - [ ] 7.3 Validar dashboards Grafana
  - [ ] 7.4 Conferir latência (SLA < 10s)
  - [ ] 7.5 Verificar throughput (>0 msg/s)
  - [ ] 7.6 Validar taxa de erro (0%)
  - [ ] 7.7 Documentar lições aprendidas

- [ ] 8. Cleanup e comunicação
  - [ ] 8.1 Remover referências obsoletas a `cognitive-plans`
  - [ ] 8.2 Comunicar mudança para equipe
  - [ ] 8.3 Arquivar documentação antiga
  - [ ] 8.4 Fechar epic GAP-01
