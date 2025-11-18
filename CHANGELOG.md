# Changelog

All notable changes to the Neural Hive-Mind project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned for Phase 2
- Dynamic Orchestrator implementation
- Tool Integration Layer (87 MCP tools)
- SLA Management System
- Execution System with rollback
- Swarm Coordination (Queen, Scout, Worker, Drone agents)

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
