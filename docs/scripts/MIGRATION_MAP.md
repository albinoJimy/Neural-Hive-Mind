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
