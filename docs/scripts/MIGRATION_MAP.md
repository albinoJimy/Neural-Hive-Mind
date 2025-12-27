
# Mapeamento de Scripts - Reorganização

## Scripts Movidos

### Build
- `build-fase1-componentes.sh` → `scripts/build/phase1-components.sh`
- `push-images-to-cluster.sh` → `scripts/build/push-to-cluster.sh`
- `import-images-to-containerd.sh` → `scripts/build/import-to-containerd.sh`

### Deploy
- `deploy-local.sh` → `scripts/deploy/local.sh`
- `deploy-fase1-componentes-faltantes.sh` → `scripts/deploy/phase1-missing.sh`

### Testes
- `testar-fase1.sh` → `tests/phase1/quick-test.sh`
- `test-specialists-simple.sh` → `tests/specialists/simple-test.sh`
- `test-specialists-v2.sh` → `tests/specialists/v2-test.sh`
- `test-specialists-connectivity.sh` → `tests/specialists/connectivity-test.sh`
- `test-grpc-specialists.sh` → `tests/specialists/grpc-test.sh`
- `test-grpc-specialists.py` → `tests/specialists/grpc-test.py`
- `test-specialist-business-fix.py` → `tests/specialists/business-fix-test.py`
- `test-fluxo-completo-e2e.py` → `tests/e2e/complete-flow-test.py`
- `test-connectivity-internal.py` → `tests/e2e/connectivity-internal-test.py`
- `test-intent-flow.py` → `tests/e2e/intent-flow-test.py`
- `test-e2e-real.py` → `tests/e2e/real-test.py`
- `test-timestamp-fix-e2e.py` → `tests/e2e/timestamp-fix-test.py`
- `teste-integracao-k8s.py` → `tests/integration/k8s-integration-test.py`

### Validação
- `validar-fase2-k8s.sh` → `scripts/validation/phase2-k8s.sh`
- `validar-fase3-completo.sh` → `scripts/validation/phase3-complete.sh`

### Observabilidade
- `access-dashboards.sh` → `scripts/observability/access-dashboards.sh`
- `stop-dashboards.sh` → `scripts/observability/stop-dashboards.sh`

## Scripts Removidos
- `scripts/deploy/quick-deploy-phase2-stubs.sh.DEPRECATED`

## Período de Transição
Wrappers deprecated na raiz serão mantidos até versão 2.0.0 (3 meses).

## Mapeamento Completo por Categoria

### Build (15 scripts)
| Script Antigo | Novo Comando | Notas |
|---------------|--------------|-------|
| scripts/build-all-optimized-services.sh | ./scripts/build.sh --target local --services optimized --parallel 8 | Serviços otimizados com paralelismo alto |
| scripts/build-and-deploy-eks.sh | ./scripts/build.sh --target ecr --push && ./scripts/deploy.sh --env eks --phase all | Build + deploy completo para EKS |
| scripts/build-and-push-images.sh | ./scripts/build.sh --target ecr --push | Build + push das imagens para ECR |
| scripts/build-and-push-to-registry.sh | ./scripts/build.sh --target registry --push | Build + push para registry local |
| scripts/build-base-images.sh | ./scripts/build.sh --target local --services base | Somente imagens base |
| scripts/build-local-parallel.sh | ./scripts/build.sh --target local --parallel 8 | Mesmo paralelismo do wrapper antigo |
| scripts/build.sh | ./scripts/build.sh --help | Entrypoint do build unificado |
| scripts/compile_all_protos.sh | ./scripts/compile_protos.sh --all | Gera todos os protos |
| scripts/compile_protos.sh | ./scripts/compile_protos.sh --service <specialists|queen-agent|analyst-agents|optimizer-agents> | Escolha --service ou --all conforme cobertura original |
| scripts/export-images-to-workers.sh | ./scripts/build.sh --target registry --push --services all | Exporta imagens para workers |
| scripts/parallel-export-to-workers.sh | ./scripts/build.sh --target registry --push --parallel 8 | Export paralela para workers |
| scripts/pipe-images-to-workers.sh | ./scripts/build.sh --target registry --push | Pipe das imagens para workers |
| scripts/push-to-ecr.sh | ./scripts/build.sh --target ecr --push | Somente push para ECR |
| scripts/rebuild-all-images.sh | ./scripts/build.sh --target local --no-cache | Rebuild completo sem cache |
| scripts/update-manifests-ecr.sh | ./scripts/deploy.sh --env eks --phase all --version <tag> | Aplica manifestos versionados via deploy CLI |

### Deploy (38 scripts)
| Script Antigo | Novo Comando | Notas |
|---------------|--------------|-------|
| scripts/deploy-queen-agent.sh | ./scripts/deploy.sh --env eks --services queen-agent | Deploy do queen-agent em EKS |
| scripts/deploy-spire.sh | ./scripts/security.sh spire deploy | Deploy SPIRE movido para security CLI |
| scripts/deploy-to-eks.sh | ./scripts/deploy.sh --env eks --phase all | Deploy completo em EKS |
| scripts/deploy-vault-ha.sh | ./scripts/security.sh vault deploy-ha | Vault HA agora via security CLI |
| scripts/deploy.sh | ./scripts/deploy.sh --help | Entrypoint do deploy unificado |
| scripts/deploy/deploy-all-v1.0.8.sh | ./scripts/deploy.sh --env eks --phase all --version 1.0.8 | Deploy completo com versão fixa |
| scripts/deploy/deploy-code-forge.sh | ./scripts/deploy.sh --env eks --services code-forge | Deploy do Code Forge |
| scripts/deploy/deploy-consensus-engine.sh | ./scripts/deploy.sh --env eks --services consensus | Deploy do consensus-engine |
| scripts/deploy/deploy-eks-complete.sh | ./scripts/deploy.sh --env eks --phase all | Deploy completo em EKS |
| scripts/deploy/deploy-execution-ticket-service.sh | ./scripts/deploy.sh --env eks --services execution-ticket-service | Deploy do execution-ticket-service |
| scripts/deploy/deploy-foundation.sh | ./scripts/deploy.sh --env eks --phase foundation | Deploy da fundação/infra base |
| scripts/deploy/deploy-gateway.sh | ./scripts/deploy.sh --env eks --services gateway | Deploy do gateway |
| scripts/deploy/deploy-guard-agents.sh | ./scripts/deploy.sh --env eks --services guard-agents | Deploy dos guard-agents |
| scripts/deploy/deploy-infrastructure-local.sh | ./scripts/deploy.sh --env local --phase foundation | Infra local completa |
| scripts/deploy/deploy-mcp-tool-catalog.sh | ./scripts/deploy.sh --env eks --services mcp-tool-catalog | Deploy do catálogo MCP |
| scripts/deploy/deploy-memory-layer-api.sh | ./scripts/deploy.sh --env eks --services memory-layer-api | Deploy da API da memory layer |
| scripts/deploy/deploy-memory-layer.sh | ./scripts/deploy.sh --env eks --services memory | Deploy da memory layer |
| scripts/deploy/deploy-memory-sync-jobs.sh | ./scripts/deploy.sh --env eks --services memory-sync-jobs | Deploy dos jobs de sync da memory |
| scripts/deploy/deploy-observability-local.sh | ./scripts/deploy.sh --env local --services observability | Stack de observabilidade local |
| scripts/deploy/deploy-observability.sh | ./scripts/deploy.sh --env eks --services observability | Stack de observabilidade em EKS |
| scripts/deploy/deploy-opa-gatekeeper-local.sh | ./scripts/security.sh policies transition --environment local | Gatekeeper/Opa agora via security CLI |
| scripts/deploy/deploy-orchestrator-dynamic.sh | ./scripts/deploy.sh --env eks --services orchestrator | Deploy do orchestrator-dynamic |
| scripts/deploy/deploy-phase2-integration.sh | ./scripts/deploy.sh --env eks --phase 2 | Deploy dos serviços da fase 2 (integração) |
| scripts/deploy/deploy-phase2-real-services.sh | ./scripts/deploy.sh --env eks --phase 2 --services orchestrator,workers,queen-agent,scout-agents,guard-agents | Deploy completo dos serviços reais da fase 2 |
| scripts/deploy/deploy-scout-agents.sh | ./scripts/deploy.sh --env eks --services scout-agents | Deploy dos scout-agents |
| scripts/deploy/deploy-security.sh | ./scripts/deploy.sh --env eks --services security | Deploy dos componentes de segurança |
| scripts/deploy/deploy-self-healing-engine.sh | ./scripts/deploy.sh --env eks --services self-healing-engine | Deploy do self-healing engine |
| scripts/deploy/deploy-semantic-translation-engine-local.sh | ./scripts/deploy.sh --env local --services semantic-translation-engine | Deploy local do semantic translation engine |
| scripts/deploy/deploy-semantic-translation-engine.sh | ./scripts/deploy.sh --env eks --services semantic-translation-engine | Deploy do semantic translation engine |
| scripts/deploy/deploy-service-registry.sh | ./scripts/deploy.sh --env eks --services service-registry | Deploy do service-registry |
| scripts/deploy/deploy-sla-management-system.sh | ./scripts/deploy.sh --env eks --services sla-management-system | Deploy do SLA management system |
| scripts/deploy/deploy-specialists-local.sh | ./scripts/deploy.sh --env local --services specialists | Deploy local dos specialists |
| scripts/deploy/deploy-specialists.sh | ./scripts/deploy.sh --env eks --services specialists | Deploy dos specialists |
| scripts/deploy/deploy-worker-agents-real-executors.sh | ./scripts/deploy.sh --env eks --services worker-agents --phase 2 | Deploy dos worker-agents com executores reais |
| scripts/deploy/deploy-worker-agents.sh | ./scripts/deploy.sh --env eks --services worker-agents | Deploy padrão dos worker-agents |
| scripts/deploy/local.sh | ./scripts/deploy.sh --env local --phase all | Deploy completo local |
| scripts/deploy/phase1-missing.sh | ./scripts/deploy.sh --env eks --phase 1 | Completa componentes faltantes da fase 1 |
| scripts/deploy/quick-deploy-essentials.sh | ./scripts/deploy.sh --env eks --services foundation,gateway,specialists | Atalho para serviços essenciais |

### Test (45 scripts)
| Script Antigo | Novo Comando | Notas |
|---------------|--------------|-------|
| tests/code-forge-e2e-test.sh | ./tests/run-tests.sh --type e2e --component code-forge | Suite equivalente via runner unificado |
| tests/consensus-engine-integration-test.sh | ./tests/run-tests.sh --type integration | Suite equivalente via runner unificado |
| tests/consensus-memory-integration-test.sh | ./tests/run-tests.sh --type integration | Suite equivalente via runner unificado |
| tests/e2e/grpc-debug-test.sh | ./tests/run-tests.sh --type e2e | Suite equivalente via runner unificado |
| tests/e2e/intent-flow-test.py | ./tests/run-tests.sh --type e2e | Suite equivalente via runner unificado |
| tests/e2e/ml-pipeline-test.sh | ./tests/run-tests.sh --type e2e | Suite equivalente via runner unificado |
| tests/fase1-test-corrigido.sh | ./tests/run-tests.sh --type integration | Suite equivalente via runner unificado |
| tests/governance-compliance-test.sh | ./tests/run-tests.sh --type integration | Suite equivalente via runner unificado |
| tests/integration-test.sh | ./tests/run-tests.sh --type integration | Suite equivalente via runner unificado |
| tests/integration/basic-integration-test.sh | ./tests/run-tests.sh --type integration | Suite equivalente via runner unificado |
| tests/integration/code-forge-test.sh | ./tests/run-tests.sh --type integration --component code-forge | Suite equivalente via runner unificado |
| tests/integration/consensus-engine-test.sh | ./tests/run-tests.sh --type integration | Suite equivalente via runner unificado |
| tests/integration/consensus-memory-test.sh | ./tests/run-tests.sh --type integration | Suite equivalente via runner unificado |
| tests/integration/governance-compliance-test.sh | ./tests/run-tests.sh --type integration | Suite equivalente via runner unificado |
| tests/integration/memory-layer-api-test.sh | ./tests/run-tests.sh --type integration --component memory-layer | Suite equivalente via runner unificado |
| tests/integration/pheromone-system-test.sh | ./tests/run-tests.sh --type integration | Suite equivalente via runner unificado |
| tests/integration/security-cli-test.sh | ./tests/run-tests.sh --type integration | Suite equivalente via runner unificado |
| tests/lib/test-runner-lib.sh | ./tests/run-tests.sh --type integration | Suite equivalente via runner unificado |
| tests/memory-layer-api-integration-test.sh | ./tests/run-tests.sh --type integration --component memory-layer | Suite equivalente via runner unificado |
| tests/phase1-end-to-end-test.sh | ./tests/run-tests.sh --type e2e --phase 1 | Suite equivalente via runner unificado |
| tests/phase1-pre-test-validation.sh | ./tests/run-tests.sh --type integration --phase 1 | Suite equivalente via runner unificado |
| tests/phase1/quick-test.sh | ./tests/run-tests.sh --type integration --phase 1 | Suite equivalente via runner unificado |
| tests/phase2-analyst-agents-test.sh | ./tests/run-tests.sh --type integration --phase 2 | Suite equivalente via runner unificado |
| tests/phase2-end-to-end-test.sh | ./tests/run-tests.sh --type e2e --phase 2 | Suite equivalente via runner unificado |
| tests/phase2-execution-ticket-service-test.sh | ./tests/run-tests.sh --type integration --phase 2 | Suite equivalente via runner unificado |
| tests/phase2-flow-c-integration-test.sh | ./tests/run-tests.sh --type integration --phase 2 | Suite equivalente via runner unificado |
| tests/phase2-mcp-integration-test.sh | ./tests/run-tests.sh --type integration --phase 2 | Suite equivalente via runner unificado |
| tests/phase2-orchestrator-test.sh | ./tests/run-tests.sh --type integration --component orchestrator --phase 2 | Suite equivalente via runner unificado |
| tests/phase2-queen-agent-test.sh | ./tests/run-tests.sh --type integration --component queen-agent --phase 2 | Suite equivalente via runner unificado |
| tests/pheromone-system-test.sh | ./tests/run-tests.sh --type integration | Suite equivalente via runner unificado |
| tests/run-tests.sh | ./tests/run-tests.sh --help | Runner unificado de testes |
| tests/services/gateway-local-test.sh | ./tests/run-tests.sh --type integration --component gateway | Suite equivalente via runner unificado |
| tests/services/publish-test-intent.sh | ./tests/run-tests.sh --type integration | Suite equivalente via runner unificado |
| tests/services/semantic-translation-engine-test.sh | ./tests/run-tests.sh --type integration | Suite equivalente via runner unificado |
| tests/specialists/connectivity-test.sh | ./tests/run-tests.sh --type integration --component specialists | Suite equivalente via runner unificado |
| tests/specialists/grpc-test.sh | ./tests/run-tests.sh --type integration --component specialists | Suite equivalente via runner unificado |
| tests/specialists/http-test.sh | ./tests/run-tests.sh --type integration --component specialists | Suite equivalente via runner unificado |
| tests/specialists/integration-test.sh | ./tests/run-tests.sh --type integration --component specialists | Suite equivalente via runner unificado |
| tests/specialists/mongodb-persistence-test.sh | ./tests/run-tests.sh --type integration --component specialists | Suite equivalente via runner unificado |
| tests/specialists/simple-test.sh | ./tests/run-tests.sh --type integration --component specialists | Suite equivalente via runner unificado |
| tests/specialists/v2-test.sh | ./tests/run-tests.sh --type integration --component specialists | Suite equivalente via runner unificado |
| tests/test-semantic-translation-engine-local.sh | ./tests/run-tests.sh --type integration | Suite equivalente via runner unificado |
| tests/unit/test_build_cli.sh | ./tests/run-tests.sh --type unit | Suite equivalente via runner unificado |
| tests/unit/test_test_runner.sh | ./tests/run-tests.sh --type unit | Suite equivalente via runner unificado |
| tests/unit/test_validate_cli.sh | ./tests/run-tests.sh --type unit | Suite equivalente via runner unificado |

### Validation (75 scripts)
| Script Antigo | Novo Comando | Notas |
|---------------|--------------|-------|
| scripts/validate-dependency-changes.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validate-metrics-runtime.py | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validate-observability.sh | ./scripts/validate.sh --target observability | Cobertura migrada para validate.sh |
| scripts/validate-phase1-final.sh | ./scripts/validate.sh --target phase --phase 1 | Cobertura migrada para validate.sh |
| scripts/validate-phase2-secrets.sh | ./scripts/validate.sh --target phase --phase 2 | Cobertura migrada para validate.sh |
| scripts/validate-phase4-bases.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validate-phase5-resources.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validate-queen-agent.sh | ./scripts/validate.sh --target services --component queen-agent | Cobertura migrada para validate.sh |
| scripts/validate-vault-spiffe-integration.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validate.sh | ./scripts/validate.sh --help | Entrada principal da CLI de validação |
| scripts/validation/audit-phase2-resources.sh | ./scripts/validate.sh --target phase --phase 2 | Cobertura migrada para validate.sh |
| scripts/validation/generate-e2e-validation-report.py | ./scripts/validate.sh --target e2e | Cobertura migrada para validate.sh |
| scripts/validation/phase2-k8s.sh | ./scripts/validate.sh --target phase --phase 2 | Cobertura migrada para validate.sh |
| scripts/validation/phase3-complete.sh | ./scripts/validate.sh --target e2e --phase 3 | Cobertura migrada para validate.sh |
| scripts/validation/run-e2e-validation-suite.sh | ./scripts/validate.sh --target e2e | Cobertura migrada para validate.sh |
| scripts/validation/test-autoscaler.sh | ./scripts/validate.sh --target performance | Cobertura migrada para validate.sh |
| scripts/validation/test-consensus-engine-e2e.py | ./scripts/validate.sh --target e2e | Cobertura migrada para validate.sh |
| scripts/validation/test-correlation.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/test-disaster-recovery.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/test-e2e-validation-complete.py | ./scripts/validate.sh --target e2e | Cobertura migrada para validate.sh |
| scripts/validation/test-gateway-routing-thresholds.py | ./scripts/validate.sh --target services --component gateway | Cobertura migrada para validate.sh |
| scripts/validation/test-mtls-connectivity.sh | ./scripts/validate.sh --target security | Cobertura migrada para validate.sh |
| scripts/validation/test-resource-quotas.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/test-semantic-fallback.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/test-sigstore-verification.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/test-slos.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/test-specialist-inference.py | ./scripts/validate.sh --target specialists | Cobertura migrada para validate.sh |
| scripts/validation/test_database_connectivity.py | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/test_grpc_communication.py | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/test_kafka_consumers.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-all-specialists.sh | ./scripts/validate.sh --target specialists | Cobertura migrada para validate.sh |
| scripts/validation/validate-bootstrap-phase.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-build-executor.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-cluster-health.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-complete-flow-e2e.sh | ./scripts/validate.sh --target e2e | Cobertura migrada para validate.sh |
| scripts/validation/validate-comprehensive-suite.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-consensus-engine.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-coverage.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-data-governance-crds.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-deploy-executor.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-envelope.py | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-execution-ticket-service.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-gateway-integration.sh | ./scripts/validate.sh --target services --component gateway | Cobertura migrada para validate.sh |
| scripts/validation/validate-guard-agents.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-ha-connectivity.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-infrastructure-local.sh | ./scripts/validate.sh --target infrastructure | Cobertura migrada para validate.sh |
| scripts/validation/validate-mcp-tool-catalog.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-memory-layer-integration.sh | ./scripts/validate.sh --target services --component memory-layer | Cobertura migrada para validate.sh |
| scripts/validation/validate-memory-layer.sh | ./scripts/validate.sh --target services --component memory-layer | Cobertura migrada para validate.sh |
| scripts/validation/validate-namespace-isolation.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-oauth2-flow.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-observability.sh | ./scripts/validate.sh --target observability | Cobertura migrada para validate.sh |
| scripts/validation/validate-orchestrator-dynamic.sh | ./scripts/validate.sh --target services --component orchestrator-dynamic | Cobertura migrada para validate.sh |
| scripts/validation/validate-performance-benchmarks.sh | ./scripts/validate.sh --target performance | Cobertura migrada para validate.sh |
| scripts/validation/validate-phase2-deployment.sh | ./scripts/validate.sh --target phase --phase 2 | Cobertura migrada para validate.sh |
| scripts/validation/validate-phase2-integration.sh | ./scripts/validate.sh --target phase --phase 2 | Cobertura migrada para validate.sh |
| scripts/validation/validate-phase2-services.sh | ./scripts/validate.sh --target phase --phase 2 | Cobertura migrada para validate.sh |
| scripts/validation/validate-policy-enforcement.sh | ./scripts/validate.sh --target security | Cobertura migrada para validate.sh |
| scripts/validation/validate-prometheus-metrics.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-redis-cluster.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-scout-agents.sh | ./scripts/validate.sh --target services --component scout-agents | Cobertura migrada para validate.sh |
| scripts/validation/validate-semantic-translation-engine.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-service-registry.sh | ./scripts/validate.sh --target services --component service-registry | Cobertura migrada para validate.sh |
| scripts/validation/validate-sla-management-system.sh | ./scripts/validate.sh --target services --component sla-management-system | Cobertura migrada para validate.sh |
| scripts/validation/validate-specialist-health.sh | ./scripts/validate.sh --target specialists | Cobertura migrada para validate.sh |
| scripts/validation/validate-specialists-deployment.sh | ./scripts/validate.sh --target specialists | Cobertura migrada para validate.sh |
| scripts/validation/validate-specialists.sh | ./scripts/validate.sh --target specialists | Cobertura migrada para validate.sh |
| scripts/validation/validate-terraform.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-test-executor.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-validate-executor.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate-worker-agents-real-executors.sh | ./scripts/validate.sh --target services --component worker-agents | Cobertura migrada para validate.sh |
| scripts/validation/validate-worker-agents.sh | ./scripts/validate.sh --target services --component worker-agents | Cobertura migrada para validate.sh |
| scripts/validation/validate_ml_metrics.sh | ./scripts/validate.sh --target services | Cobertura migrada para validate.sh |
| scripts/validation/validate_opa_policies.sh | ./scripts/validate.sh --target security | Cobertura migrada para validate.sh |
| scripts/validation/validate_orchestrator_ml.sh | ./scripts/validate.sh --target services --component orchestrator-dynamic | Cobertura migrada para validate.sh |

### Security (23 scripts)
| Script Antigo | Novo Comando | Notas |
|---------------|--------------|-------|
| scripts/create-phase2-secrets.sh | ./scripts/security.sh secrets create --phase 2 | Criação de secrets da fase 2 |
| scripts/deploy-spire.sh | ./scripts/security.sh spire deploy | Deploy SPIRE via security CLI |
| scripts/deploy-vault-ha.sh | ./scripts/security.sh vault deploy-ha | Provisiona Vault HA |
| scripts/enable-vault-spiffe-services.sh | ./scripts/security.sh validate mtls | Validação mTLS Vault/SPIRE |
| scripts/security.sh | ./scripts/security.sh --help | Entrada principal do security CLI |
| scripts/security/modules/certificates.sh | ./scripts/security.sh certs setup | Setup/rotação de certificados |
| scripts/security/modules/policies.sh | ./scripts/security.sh policies validate | Validação/Auditoria de policies |
| scripts/security/modules/policies/transition.sh | ./scripts/security.sh policies transition | Transição gradual de policies |
| scripts/security/modules/secrets/create-phase2.sh | ./scripts/security.sh secrets create --phase 2 | Geração de secrets fase 2 |
| scripts/security/modules/secrets/validate-phase2.sh | ./scripts/security.sh secrets validate --phase 2 | Validação de secrets fase 2 |
| scripts/security/modules/spire/deploy.sh | ./scripts/security.sh spire deploy | Deploy SPIRE |
| scripts/security/modules/spire/register-entries.sh | ./scripts/security.sh spire register | Registro de entries SPIRE |
| scripts/security/modules/vault/configure.sh | ./scripts/security.sh vault configure | Configuração de policies do Vault |
| scripts/security/modules/vault/deploy-ha.sh | ./scripts/security.sh vault deploy-ha | Provisiona Vault HA |
| scripts/security/modules/vault/init.sh | ./scripts/security.sh vault init | Inicialização de Vault |
| scripts/security/modules/vault/pki.sh | ./scripts/security.sh certs setup | Configuração de PKI/cert-manager |
| scripts/security/modules/vault/populate.sh | ./scripts/security.sh vault populate | Popula secrets e roles no Vault |
| scripts/security/setup-cert-manager.sh | ./scripts/security.sh certs setup | Setup cert-manager consolidado |
| scripts/security/setup-observability-secrets.sh | ./scripts/security.sh secrets create --phase 2 --target observability | Secrets de observabilidade |
| scripts/security/transition-policies-to-enforce.sh | ./scripts/security.sh policies transition | Transição de policies para enforce |
| scripts/spire-create-entries.sh | ./scripts/security.sh spire register | Registro de entries SPIRE |
| scripts/test-vault-spiffe-connectivity.sh | ./scripts/security.sh validate mtls | Validação de conectividade Vault/SPIRE |
| scripts/vault-init.sh | ./scripts/security.sh vault init | Inicialização de Vault |

### ML (25 scripts)
| Script Antigo | Novo Comando | Notas |
|---------------|--------------|-------|
| ml_pipelines/commands/anomaly_detector.sh | ./ml_pipelines/ml.sh anomaly-detector train | Fluxo de treino do detector de anomalia |
| ml_pipelines/commands/business_metrics.sh | ./ml_pipelines/ml.sh business-metrics collect | Coleta métricas de negócio |
| ml_pipelines/commands/disaster_recovery.sh | ./ml_pipelines/ml.sh disaster-recovery test | Testa playbook de DR |
| ml_pipelines/commands/feedback.sh | ./ml_pipelines/ml.sh feedback ingest | Ingestão de feedbacks para retraining |
| ml_pipelines/commands/generate_dataset.sh | ./ml_pipelines/ml.sh generate-dataset --all | Gera datasets completos |
| ml_pipelines/commands/promote.sh | ./ml_pipelines/ml.sh promote --model <name> --version <n> | Promoção de modelos com versionamento |
| ml_pipelines/commands/retrain.sh | ./ml_pipelines/ml.sh retrain --specialist <name> | Retreino de especialista específico |
| ml_pipelines/commands/rollback.sh | ./ml_pipelines/ml.sh rollback --specialist <name> | Rollback para versão anterior |
| ml_pipelines/commands/status.sh | ./ml_pipelines/ml.sh status --all | Status agregado dos modelos |
| ml_pipelines/commands/train.sh | ./ml_pipelines/ml.sh train --all | Treino completo dos especialistas/modelos preditivos |
| ml_pipelines/commands/validate.sh | ./ml_pipelines/ml.sh validate --all | Validação de alinhamento/modelos carregados |
| ml_pipelines/examples/complete_workflow.sh | ./ml_pipelines/ml.sh --help | Fluxo coberto pelo CLI ml.sh |
| ml_pipelines/ml.sh | ./ml_pipelines/ml.sh --help | Entrypoint do CLI ML unificado |
| ml_pipelines/scripts/check_model_status.sh | ./ml_pipelines/ml.sh status --all | Status agregado dos modelos |
| ml_pipelines/scripts/retrain_specialist.sh | ./ml_pipelines/ml.sh retrain --specialist <name> | Retreino de especialista específico |
| ml_pipelines/scripts/rollback_model.sh | ./ml_pipelines/ml.sh rollback --specialist <name> | Rollback para versão anterior |
| ml_pipelines/training/generate_all_datasets.sh | ./ml_pipelines/ml.sh generate-dataset --all | Gera datasets completos |
| ml_pipelines/training/generate_all_specialists.sh | ./ml_pipelines/ml.sh --help | Fluxo coberto pelo CLI ml.sh |
| ml_pipelines/training/generate_training_datasets.py | ./ml_pipelines/ml.sh generate-dataset --all | Gera datasets completos |
| ml_pipelines/training/train_all_specialists.sh | ./ml_pipelines/ml.sh train --all | Treino completo dos especialistas/modelos preditivos |
| ml_pipelines/training/train_predictive_models.py | ./ml_pipelines/ml.sh train --all | Treino completo dos especialistas/modelos preditivos |
| ml_pipelines/training/train_specialist_model.py | ./ml_pipelines/ml.sh train --all | Treino completo dos especialistas/modelos preditivos |
| ml_pipelines/training/validate_feature_alignment.py | ./ml_pipelines/ml.sh validate --all | Validação de alinhamento/modelos carregados |
| ml_pipelines/training/validate_model_promotion.sh | ./ml_pipelines/ml.sh validate --all | Validação de alinhamento/modelos carregados |
| ml_pipelines/training/validate_models_loaded.sh | ./ml_pipelines/ml.sh validate --all | Validação de alinhamento/modelos carregados |

## Mapeamento de Variáveis de Ambiente
| Variável Antiga | Nova Variável/Flag | Notas |
|---------------|------------------|-----|
| BUILD_TARGET | --target (build.sh) | Destino de build (local/ecr/registry/all) |
| BUILD_VERSION | --version (build.sh) | Tag das imagens |
| BUILD_PARALLEL_JOBS | --parallel (build.sh) | Paralelismo de build |
| BUILD_SERVICES | --services (build.sh) | Lista de serviços para build |
| BUILD_NO_CACHE | --no-cache (build.sh) | Build sem cache |
| BUILD_SKIP_BASE_IMAGES | --skip-base-images (build.sh) | Pular imagens base |
| PUSH_IMAGES | --push (build.sh) | Habilita push |
| DOCKER_REGISTRY | --registry (build.sh) | Registry local |
| DEPLOY_ENV | --env (deploy.sh) | Ambiente destino |
| DEPLOY_PHASE | --phase (deploy.sh) | Fase/onda de deploy |
| DEPLOY_SERVICES | --services (deploy.sh) | Serviços específicos |
| DEPLOY_VERSION | --version (deploy.sh) | Versão/manifest usada no deploy |
| DEPLOY_SKIP_VALIDATION | --skip-validation (deploy.sh) | Ignora dependências |
| DEPLOY_DRY_RUN | --dry-run (deploy.sh) | Executa apenas simulação |
| VALIDATE_TARGET | --target (validate.sh) | Escopo de validação |
| VALIDATE_PHASE | --phase (validate.sh) | Fase da validação |
| VALIDATE_COMPONENT | --component (validate.sh) | Componente específico |
| VALIDATE_NAMESPACE | --namespace (validate.sh) | Namespace Kubernetes |
| VALIDATE_REPORT_FORMAT | --report (validate.sh) | Formato do relatório |
| VALIDATE_REPORT_FILE | --report-file (validate.sh) | Destino do relatório |
| VALIDATE_QUICK_MODE | --quick (validate.sh) | Modo rápido |
| VALIDATE_VERBOSE | --verbose (validate.sh) | Logs detalhados |
| SECURITY_ENVIRONMENT | --environment/--env (security.sh) | Ambiente para operações de segurança |
| SECURITY_NAMESPACE | --namespace (security.sh) | Namespace dos componentes de segurança |
| SECURITY_MODE | --mode (security.sh secrets/vault) | Modo de criação/rotina de secrets |
| SECURITY_PHASE | --phase (security.sh secrets) | Fase aplicada (1/2) |
| SECURITY_BACKUP_PATH | --output/--input (security.sh vault backup/restore) | Caminho de backup/restore |
| ML_EXPERIMENT | --model (ml.sh promote) | Nome do modelo no MLFlow |
| ML_VERSION | --version (ml.sh promote) | Versão do modelo |
| ML_SPECIALIST | --specialist (ml.sh retrain/rollback) | Especialista alvo |
| TEST_TYPE | --type (run-tests.sh) | Tipo de suite (unit/integration/e2e/performance) |
| TEST_COMPONENT | --component (run-tests.sh) | Componente alvo |
| TEST_PHASE | --phase (run-tests.sh) | Fase de testes |
| TEST_REPORT_FORMAT | --report (run-tests.sh) | Formato de relatório de testes |
| TEST_COVERAGE | --coverage (run-tests.sh) | Coleta de cobertura |

## Mapeamento de Flags
| Flag Antiga | Nova Flag | Notas |
|-----------|---------|-----|
| --local/--eks (build wrappers) | --target local|ecr | Target de build padronizado |
| --registry | --target registry --registry <url> | Registry local via build CLI |
| --push | --push | Flag unificada para push |
| --parallel N | --parallel N | Paralelismo em build |
| --no-cache | --no-cache | Build sem cache |
| --services "a,b" | --services "a,b" | Lista CSV compartilhada entre CLIs |
| --env <env> | --env <env> | Ambiente em deploy/security |
| --phase1/--phase2 | --phase 1|2 | Fases padronizadas |
| --skip-validation | --skip-validation | Pular validação de dependências |
| --dry-run | --dry-run | Dry-run suportado em deploy/security |
| --report <fmt> | --report <fmt> | Formato de relatório (validate/tests) |
| --report-file <file> | --report-file <file> | Destino do relatório (validate) |
| --component <name> | --component <name> | Componentes específicos |
| --namespace <ns> | --namespace <ns> | Namespace Kubernetes (validate/security) |
| --fix | --fix | Autofix disponível em validate.sh |
| --quick | --quick | Modo rápido em validate.sh |
| --verbose | --verbose | Logs detalhados |
| --model <name> | --model <name> | Modelos em ml.sh promote |
| --version <tag> | --version <tag> | Versionamento em build/deploy/ml |
| --specialist <id> | --specialist <id> | Escopo para retrain/rollback em ml.sh |
