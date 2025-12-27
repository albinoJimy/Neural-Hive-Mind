# Changelog

All notable changes to the Neural Hive-Mind project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - 2025-12-14

### Changed
- **Phase 2 Deployment**: Substituido deployment de stubs nginx por servicos reais via Helm
  - Removido `scripts/deploy/quick-deploy-phase2-stubs.sh` (deprecated)
  - Adicionado `scripts/deploy/deploy-phase2-real-services.sh` para deployment real
  - Padronizados todos os image repositories para `37.60.241.150:30500`
  - Padronizadas todas as image tags para `1.0.0`
  - Adicionado script de validacao `scripts/validation/validate-phase2-deployment.sh`

### Fixed
- Corrigidas inconsistencias de image repository nos values.yaml de todos os 13 servicos
- Corrigida tag `latest` em analyst-agents para `1.0.0`
- Corrigida tag `1.0.7` em worker-agents para `1.0.0`

### Removed
- Removidos artefatos deprecated de stubs (`scripts/deploy/quick-deploy-phase2-stubs.sh.DEPRECATED` e `scripts/deploy/STUBS_DEPRECATED.md`)

## [Unreleased-previous] - 2025-02-14

### Added
- Script de auditoria automatizada de dependências (`scripts/audit-dependencies.sh`)
- Script de scan de imports não utilizados (`scripts/scan-unused-imports.py`)
- Script de validação de mudanças de dependências (`scripts/validate-dependency-changes.sh`)
- Workflow GitHub Actions (`.github/workflows/dependency-audit.yml`) para auditorias semanais e em PRs
- Documentação abrangente em `docs/DEPENDENCY_AUDIT.md`
- Seção de gerenciamento de dependências no README.md
- **Otimizações de Dependências e Modelos ML**
  - Remoção de `transformers` (~2.5GB) do `gateway-intencoes` (ASR/NLU usa apenas Whisper e spaCy)
  - Remoção de `pyspark` (~300MB) do `analyst-agents` (não utiliza processamento distribuído)
  - Modelo Whisper `tiny` (39MB) com lazy loading e fallback automático para `base` e `small`
  - Init containers para download de modelos ML (Whisper, spaCy) em volumes persistentes (PVC 2Gi)
  - Lock de sincronização (`asyncio.Lock`) em `ASRPipeline` para prevenir carregamentos concorrentes
  - Carregamento de modelos spaCy a partir do volume compartilhado `/app/models/spacy`
  - Separação de dependências dev/prod com `requirements-dev.txt` no `gateway-intencoes`
  - Documentação completa em `docs/DEPENDENCY_OPTIMIZATION.md`
- **Rightsizing & Topology Docs**
  - `docs/RESOURCE_TUNING_GUIDE.md` promovido à versão 2.0 com matriz de serviços, decision tree, consultas Prometheus e capítulo sobre topology spread
  - README destaca o guia para facilitar futuras auditorias de capacidade
- **Probes e Distribuição**
  - Startup/liveness/readiness completos para consensus-engine, memory-layer-api, semantic-translation-engine, orchestrator-dynamic, code-forge, worker-agents e service-registry
  - Startup probes padronizados com `failureThreshold` 20-30 para lidar com Temporal/Kafka/etcd/clone de templates

### Changed
- **[BREAKING]** Consolidação de versões de dependências críticas:
  - grpcio: 1.59.0/1.60.0 → >=1.75.1
  - protobuf: 4.24.0/4.25.0 → >=5.27.0 (requer regeneração de código protobuf)
  - aiokafka: 0.8.x → >=0.10.0
  - pydantic: 2.0.0/2.4.0/2.5.0 → >=2.5.2
  - fastapi: 0.104.0 → >=0.104.1
  - Demais dependências alinhadas (confira `docs/DEPENDENCY_AUDIT.md`)
- Separação de dependências de desenvolvimento:
  - Criados requirements-dev.txt para consensus-engine, orchestrator-dynamic, semantic-translation-engine, sla-management-system, mcp-tool-catalog e code-forge
  - Removidas dependências de teste (pytest, black, flake8, mypy) de requirements.txt de produção
  - Redução estimada de ~50MB por imagem Docker
- Gateway de Intenções: Redução de 60% no tamanho da imagem Docker (4.5GB → 1.8GB)
- Gateway de Intenções: Redução de 86% no tempo de startup (85s → 12s) com lazy loading
- Gateway de Intenções: Redução de 43% no consumo de memória base (2.1GB → 1.2GB)
- Specialist Services: Redução de 22% no tamanho da imagem Docker (3.2GB → 2.5GB)
- Analyst Agents: Redução de 18% no tamanho da imagem Docker (2.8GB → 2.3GB)
- Tempo de build completo reduzido em 38% (45min → 28min)
- Tempo de build incremental reduzido em 42% (12min → 7min)
- Especialistas NLP: requests agora 300m CPU / 768Mi RAM (40% menos CPU garantida, 25% menos memória), mantendo limites 1 vCPU / 2Gi
- camadas core (consensus, memory-layer-api, semantic-translation-engine) com limites reduzidos (até -37%) e probes/topology spread alinhados com perfis de Kafka, Redis, Neo4j
- Execução/Agentes: orchestrator-dynamic, code-forge, worker-agents e service-registry com novos limites (400m/800m requests) e anti-affinity zona-based (service-registry HARD + DoNotSchedule)
- TopologySpreadConstraints aplicados em 20 workloads garantindo fan-out equilibrado entre zonas

### Fixed
- Conflitos de versão entre serviços que causavam falhas em runtime
- Dependências transitivas redundantes (uso padronizado de `--no-deps` em cadeias com Torch/Whisper)

### Security
- Atualização de pacotes críticos para versões com patches recentes
- Auditoria automatizada de vulnerabilidades via pip-audit e safety integrada ao CI

### Performance
- Redução de ~15-20% no tamanho de imagens Docker após remoção de dependências não utilizadas
- Redução de ~10-15% no tempo de build ao instalar somente dependências necessárias
- Direitosizing de especialistas (5 serviços × 2 réplicas) corta CPU garantida de 5 cores para 3 cores (~33% economia) sem degradar consenso
- Novos limites do orchestration/execution layer reduzem custos de Reserva EC2 previstos em ~18% mantendo SLAs de gRPC/Temporal

### Notes
- **Ação requerida**: Regenerar stubs gRPC/protobuf com protoc 6.x para serviços que consumem o Service Registry
- **Validação requerida**: Revisar uso real de `pm4py`, `prophet`, `statsmodels` e `pulp` nos specialists (potencial economia de ~220MB por imagem)
- Consulte `docs/DEPENDENCY_AUDIT.md` para o plano faseado de migração e lista completa de pacotes críticos

### Planned for Phase 2
- Dynamic Orchestrator implementation
- Tool Integration Layer (87 MCP tools)
- SLA Management System
- Execution System with rollback
- Swarm Coordination (Queen, Scout, Worker, Drone agents)

---

## [1.0.0] - 2024-12-17

### Fixed
- **[CRITICAL]** Corrigido conflito entre grpcio 1.60.0 e grpcio-tools 1.68.0 em python-grpc-base
- Atualizado scikit-learn de >=1.4.0 para >=1.5.0 em python-mlops-base para compatibilidade com specialist-base
- Atualizado Python de 3.9 para 3.11 em ml_pipelines/k8s/Dockerfile.monitoring

### Changed
- python-grpc-base: grpcio 1.60.0 → 1.75.1, grpcio-tools 1.68.0 → 1.75.1, grpcio-health-checking 1.60.0 → 1.75.1
- python-mlops-base: scikit-learn >=1.4.0 → >=1.5.0
- ml-monitoring: Python 3.9 → 3.11

---

## [1.0.7] - 2025-11-12

### Added
- Phase 1 final validation script (`scripts/validate-phase1-final.sh`)
- Comprehensive test results directory structure (`tests/results/phase1/`)
- Validation source reference block in executive report
- Metrics refresh instructions in performance documentation
- Security notes for credential management

### Fixed
- **CRITICAL**: TypeError in Timestamp protobuf conversion in all specialists
  - Added extensive validation in `grpc_server.py:380`
  - Added validation in `specialists_grpc_client.py:101-127`
  - Implemented proper datetime → Timestamp conversion
- MongoDB authentication issues in Consensus Engine
  - Updated `values-local.yaml` with full MongoDB URI including auth
- Exposed credentials in documentation
  - Replaced all hardcoded passwords with placeholders
  - Added references to Secrets Management Guide

### Changed
- Updated README.md with Phase 1 completion status and artifacts
- Enhanced executive report with validation methodology
- Improved performance metrics documentation with collection procedures

### Security
- Removed exposed MongoDB credentials from all documentation
- Added security notes for secret management
- Referenced Secrets Management Guide in all credential examples

---

## [1.0.0] - 2025-11-10

### Added - Phase 1 Complete
- **Infrastructure Layer** (5 components)
  - Kafka Cluster (Strimzi operator)
  - MongoDB Cluster (3 replicas)
  - Redis Cluster (hot memory layer)
  - Neo4j Cluster (semantic memory layer)
  - ClickHouse Cluster (optional cold storage)

- **Cognitive Services Layer** (9 components)
  - Gateway de Intenções v1.0.0
  - Semantic Translation Engine v1.0.0
  - Specialist Business v1.0.0
  - Specialist Technical v1.0.0
  - Specialist Behavior v1.0.0
  - Specialist Evolution v1.0.0
  - Specialist Architecture v1.0.0
  - Consensus Engine v1.0.0
  - Memory Layer API v1.0.0

- **Governance & Observability**
  - OPA Gatekeeper deployment
  - 28 Grafana dashboards
  - 19 Prometheus alert rule files
  - 9+ ServiceMonitors for metrics collection
  - ConstraintTemplates for policy enforcement

- **Documentation**
  - Phase 1 Executive Report
  - Phase 1 Testing Guide
  - Phase 1 Performance Metrics
  - Operational Runbook
  - Multiple troubleshooting guides

### Features
- **Multi-perspective Decision Making**: 5 neural specialists with domain expertise
- **4-Tier Memory Architecture**: HOT (Redis), WARM (MongoDB), SEMANTIC (Neo4j), COLD (ClickHouse)
- **Bayesian Consensus**: Model averaging and voting ensemble
- **Digital Pheromones**: Redis-based swarm coordination protocol
- **Explainability**: 100% coverage with SHAP/LIME integration
- **Audit Trail**: Immutable ledger with SHA-256 hashes
- **Event-Driven Architecture**: Kafka backbone with 15 topics

### Performance
- **Latency**: 66ms average (67% below 200ms threshold)
- **Availability**: 100% uptime (zero crashes in testing)
- **Success Rate**: 100% (23/23 E2E tests passed)
- **Ledger Integrity**: 100% (all records with valid hashes)

### Known Limitations
- Single-node deployment (multi-node recommended for production)
- CPU utilization at 94% (limited scalability)
- Domain classification ~80% accuracy (retraining needed)
- Prometheus stack deployment pending for full P95/P99 metrics
- ClickHouse optional (not required for Phase 1 completion)

---

## [0.1.0] - 2025-10-15

### Added - Phase 0 Bootstrap
- Initial Kubernetes cluster setup (Minikube/Kind)
- Namespace structure (9 namespaces)
- RBAC configuration
- Network policies (zero-trust foundation)
- Resource quotas and limits
- Kafka deployment via Strimzi
- Gateway de Intenções initial implementation

### Infrastructure
- VPC and networking setup
- EKS cluster configuration
- ECR container registry
- Istio service mesh (planned)
- Basic monitoring setup

---

## Version History Summary

| Version | Release Date | Key Features | Status |
|---------|--------------|--------------|--------|
| **1.0.7** | 2025-11-12 | Timestamp fix, validation improvements, security hardening | ✅ Current |
| **1.0.0** | 2025-11-10 | Phase 1 complete: 13 components deployed | ✅ Stable |
| **0.1.0** | 2025-10-15 | Phase 0 bootstrap: cluster and infra | ✅ Deprecated |

---

## Migration Guides

### Upgrading from 1.0.0 to 1.0.7

1. **Rebuild specialist images** with timestamp fix:
   ```bash
   for specialist in business technical behavior evolution architecture; do
     docker build -f services/specialist-$specialist/Dockerfile \
       -t neural-hive-mind/specialist-$specialist:1.0.7 .
   done
   ```

2. **Update MongoDB URIs** to include authentication:
   ```bash
   # Update values-local.yaml for consensus-engine
   # Change: mongodb://mongodb...
   # To: mongodb://<user>:<password>@mongodb...?authSource=admin
   ```

3. **Redeploy affected services**:
   ```bash
   for specialist in business technical behavior evolution architecture; do
     helm upgrade specialist-$specialist helm-charts/specialist-$specialist/ \
       -n specialist-$specialist \
       -f helm-charts/specialist-$specialist/values-local.yaml
   done

   helm upgrade consensus-engine helm-charts/consensus-engine/ \
     -n consensus-engine \
     -f helm-charts/consensus-engine/values-local.yaml
   ```

4. **Verify deployment**:
   ```bash
   ./scripts/validate-phase1-final.sh
   ```

### Breaking Changes

None. Version 1.0.7 is a patch release with bug fixes only.

---

## Support & Contact

- **Documentation**: [README.md](README.md)
- **Issues**: [GitHub Issues](https://github.com/anthropics/neural-hive-mind/issues) (if applicable)
- **Discussions**: Contact DevOps/SRE team

---

**Maintained by**: Neural Hive-Mind Team
**Last Updated**: 2025-11-12
