.PHONY: proto-gen proto-gen-all clean-proto minikube-setup minikube-start minikube-stop minikube-clean minikube-reset minikube-validate minikube-status minikube-dashboard minikube-logs bootstrap-apply bootstrap-validate test test-unit test-integration test-e2e test-phase1 test-phase2 test-specialists test-coverage test-parallel test-dry-run test-clean test-specialists-unit test-phase1-pre-validate help
.PHONY: validate validate-all validate-specialists validate-infrastructure validate-services validate-security validate-observability validate-performance validate-phase validate-e2e validate-report validate-ci

# ============================================================================
# Protobuf Targets
# ============================================================================

# Gerar arquivos protobuf
proto-gen:
	@echo "Gerando arquivos protobuf..."
	@mkdir -p libraries/python/neural_hive_specialists/proto_gen
	@python3 -m grpc_tools.protoc \
		-I./schemas/specialist-opinion \
		--python_out=./libraries/python/neural_hive_specialists/proto_gen \
		--grpc_python_out=./libraries/python/neural_hive_specialists/proto_gen \
		./schemas/specialist-opinion/specialist.proto
	@echo "import sys; import os; sys.path.insert(0, os.path.dirname(__file__))" > libraries/python/neural_hive_specialists/proto_gen/__init__.py
	@echo "Protobuf gerado com sucesso!"

# Compilar todos os protos do projeto
proto-gen-all:
	@echo "Compilando todos os protos do projeto..."
	@./scripts/compile_all_protos.sh

# Limpar arquivos protobuf gerados
clean-proto:
	@rm -rf libraries/python/neural_hive_specialists/proto_gen
	@echo "Arquivos protobuf removidos"

# ============================================================================
# Minikube Local Development Targets
# ============================================================================

## minikube-setup: Complete Minikube setup with bootstrap configuration
minikube-setup:
	@echo "🚀 Setting up Minikube local environment..."
	@./scripts/setup/setup-minikube-local.sh

## minikube-start: Start Minikube cluster only (without bootstrap)
minikube-start:
	@echo "▶️  Starting Minikube..."
	@minikube start --driver=docker --cpus=4 --memory=8192 --disk-size=20g --kubernetes-version=v1.29.0
	@minikube addons enable ingress
	@minikube addons enable metrics-server
	@minikube addons enable storage-provisioner
	@minikube addons enable registry

## minikube-stop: Stop Minikube cluster
minikube-stop:
	@echo "⏸️  Stopping Minikube..."
	@minikube stop

## minikube-clean: Delete Minikube cluster and clean up
minikube-clean:
	@echo "🧹 Cleaning up Minikube..."
	@minikube delete
	@rm -rf .tmp/bootstrap*

## minikube-reset: Clean and setup fresh Minikube environment
minikube-reset: minikube-clean minikube-setup

## minikube-validate: Run bootstrap phase validation
minikube-validate:
	@echo "✅ Validating Minikube bootstrap..."
	@./scripts/validation/validate-bootstrap-phase.sh

## minikube-status: Show Minikube and cluster status
minikube-status:
	@echo "📊 Minikube Status:"
	@minikube status || echo "Minikube not running"
	@echo ""
	@echo "📊 Cluster Status:"
	@kubectl cluster-info || echo "Cannot connect to cluster"
	@echo ""
	@echo "📊 Namespaces:"
	@kubectl get namespaces | grep -E 'NAME|neural-hive|cosign|gatekeeper|cert-manager|auth' || echo "No namespaces found"

## minikube-dashboard: Open Kubernetes dashboard
minikube-dashboard:
	@echo "🎨 Opening Minikube dashboard..."
	@minikube dashboard

## minikube-logs: Show Minikube logs
minikube-logs:
	@echo "📋 Minikube logs:"
	@minikube logs --length=100

## bootstrap-apply: Apply bootstrap manifests to existing cluster
bootstrap-apply:
	@echo "📦 Applying bootstrap manifests..."
	@export ENVIRONMENT=local && ./scripts/deploy/apply-bootstrap-manifests.sh

## bootstrap-validate: Validate bootstrap configuration
bootstrap-validate:
	@echo "✅ Validating bootstrap configuration..."
	@./scripts/validation/validate-bootstrap-phase.sh

# ============================================================================
# EKS Build and Deploy Targets
# ============================================================================

## build-and-deploy-eks: Build local, push to ECR, and update manifests (full workflow)
build-and-deploy-eks:
	@echo "🚀 Executando build e deploy completo para EKS..."
	@./scripts/build-and-deploy-eks.sh

## build-and-deploy-eks-version: Build and deploy with specific version
build-and-deploy-eks-version:
	@if [ -z "$(VERSION)" ]; then \
		echo "❌ Erro: VERSION não definido. Use: make build-and-deploy-eks-version VERSION=1.0.8"; \
		exit 1; \
	fi
	@echo "🚀 Executando build e deploy para EKS (versão $(VERSION))..."
	@./scripts/build-and-deploy-eks.sh --version $(VERSION)

## build-and-push-only: Build local and push to ECR (skip manifest update)
build-and-push-only:
	@echo "🔨 Build local e push para ECR..."
	@./scripts/build-and-deploy-eks.sh --skip-update

## update-manifests-only: Update manifests only (skip build and push)
update-manifests-only:
	@echo "📝 Atualizando manifestos..."
	@./scripts/build-and-deploy-eks.sh --skip-build --skip-push

## preview-manifest-changes: Preview manifest changes without applying
preview-manifest-changes:
	@echo "👀 Preview de mudanças nos manifestos..."
	@./scripts/build-and-deploy-eks.sh --skip-build --skip-push --dry-run

.PHONY: build-and-deploy-eks build-and-deploy-eks-version build-and-push-only update-manifests-only preview-manifest-changes

# ============================================================================
# Build Targets (Unified CLI)
# ============================================================================

## build-local: Build local apenas (sem push)
build-local:
	@echo "🔨 Building local..."
	@./scripts/build.sh --target local

## build-local-version: Build local com versão específica
build-local-version:
	@if [ -z "$(VERSION)" ]; then \
		echo "❌ Erro: VERSION não definido. Use: make build-local-version VERSION=1.0.8"; \
		exit 1; \
	fi
	@./scripts/build.sh --target local --version $(VERSION)

## build-ecr: Build e push para ECR
build-ecr:
	@echo "🚀 Building e pushing para ECR..."
	@./scripts/build.sh --target ecr

## build-ecr-version: Build e push para ECR com versão específica
build-ecr-version:
	@if [ -z "$(VERSION)" ]; then \
		echo "❌ Erro: VERSION não definido. Use: make build-ecr-version VERSION=1.0.8"; \
		exit 1; \
	fi
	@./scripts/build.sh --target ecr --version $(VERSION)

## build-registry: Build e push para registry local
build-registry:
	@echo "🚀 Building e pushing para registry local..."
	@./scripts/build.sh --target registry

## build-all: Build e push para ECR e registry local
build-all:
	@echo "🚀 Building e pushing para todos os registries..."
	@./scripts/build.sh --target all

## build-services: Build serviços específicos
build-services:
	@if [ -z "$(SERVICES)" ]; then \
		echo "❌ Erro: SERVICES não definido. Use: make build-services SERVICES=gateway-intencoes,consensus-engine"; \
		exit 1; \
	fi
	@./scripts/build.sh --target local --services $(SERVICES)

## build-no-cache: Build sem cache
build-no-cache:
	@./scripts/build.sh --target local --no-cache

## build-parallel: Build com paralelização customizada
build-parallel:
	@if [ -z "$(JOBS)" ]; then \
		echo "❌ Erro: JOBS não definido. Use: make build-parallel JOBS=8"; \
		exit 1; \
	fi
	@./scripts/build.sh --target local --parallel $(JOBS)

.PHONY: build-local build-local-version build-ecr build-ecr-version build-registry build-all build-services build-no-cache build-parallel

# ============================================================================
# Help Target
# ============================================================================

## help: Show this help message
help:
	@echo "Neural Hive-Mind Makefile"
	@echo ""
	@echo "Protobuf Targets:"
	@echo "  make proto-gen           - Generate protobuf files"
	@echo "  make proto-gen-all       - Compile all protobuf files (services + libraries)"
	@echo "  make clean-proto         - Remove generated protobuf files"
	@echo ""
	@echo "Build Targets (Unified CLI):"
	@echo "  make build-local              - Build local apenas"
	@echo "  make build-local-version      - Build local com versão específica (requer VERSION=x.y.z)"
	@echo "  make build-ecr                - Build e push para ECR"
	@echo "  make build-ecr-version        - Build e push para ECR com versão (requer VERSION=x.y.z)"
	@echo "  make build-registry           - Build e push para registry local"
	@echo "  make build-all                - Build e push para todos os registries"
	@echo "  make build-services           - Build serviços específicos (requer SERVICES=svc1,svc2)"
	@echo "  make build-no-cache           - Build sem cache"
	@echo "  make build-parallel           - Build com paralelização customizada (requer JOBS=n)"
	@echo ""
	@echo "Minikube Local Development:"
	@echo "  make minikube-setup      - Complete Minikube setup with bootstrap"
	@echo "  make minikube-start      - Start Minikube cluster"
	@echo "  make minikube-stop       - Stop Minikube cluster"
	@echo "  make minikube-clean      - Delete Minikube cluster"
	@echo "  make minikube-reset      - Clean and setup fresh environment"
	@echo "  make minikube-validate   - Validate bootstrap phase"
	@echo "  make minikube-status     - Show cluster status"
	@echo "  make minikube-dashboard  - Open Kubernetes dashboard"
	@echo "  make minikube-logs       - Show Minikube logs"
	@echo ""
	@echo "Bootstrap Targets:"
	@echo "  make bootstrap-apply     - Apply bootstrap manifests"
	@echo "  make bootstrap-validate  - Validate bootstrap configuration"
	@echo ""
	@echo "EKS Build and Deploy:"
	@echo "  make build-and-deploy-eks           - Build, push e update manifestos (fluxo completo)"
	@echo "  make build-and-deploy-eks-version   - Build e deploy com versão específica (requer VERSION=x.y.z)"
	@echo "  make build-and-push-only            - Apenas build e push (sem atualizar manifestos)"
	@echo "  make update-manifests-only          - Apenas atualizar manifestos (sem build/push)"
	@echo "  make preview-manifest-changes       - Preview de mudanças nos manifestos"
	@echo ""
	@echo "Testing (Unified CLI):"
	@echo "  make test                - Run all tests"
	@echo "  make test-unit           - Run unit tests only"
	@echo "  make test-integration    - Run integration tests only"
	@echo "  make test-e2e            - Run E2E tests only"
	@echo "  make test-phase1         - Run Phase 1 tests"
	@echo "  make test-phase2         - Run Phase 2 tests"
	@echo "  make test-specialists    - Run specialist tests"
	@echo "  make test-coverage       - Run tests with coverage"
	@echo "  make test-parallel       - Run tests in parallel"
	@echo "  make test-dry-run        - Show which tests would run"
	@echo "  make test-clean          - Clean test results"
	@echo ""
	@echo "Phase 1 Testing:"
	@echo "  make test-phase1-pre-validate  - Run pre-test validation"
	@echo "  make test-phase1               - Run Phase 1 end-to-end test"
	@echo "  make test-phase1-debug         - Run Phase 1 test in debug mode"
	@echo "  make test-phase1-full          - Run full Phase 1 test suite"
	@echo "  make test-phase1-results       - Show latest test results"
	@echo "  make test-phase1-clean         - Clean test results"
	@echo ""
	@echo "Continuous Learning & Feedback:"
	@echo "  make submit-feedback           - Submit feedback via API (requires OPINION_ID, RATING, RECOMMENDATION)"
	@echo "  make train-model               - Train/retrain specialist model (requires SPECIALIST_TYPE)"
	@echo "  make view-continuous-learning  - Open Continuous Learning Grafana dashboard"
	@echo "  make monitor-retraining-runs   - Monitor MLflow retraining runs status"
	@echo "  make check-retraining-trigger  - Check retraining threshold (dry-run)"
	@echo "  make trigger-retraining        - Trigger retraining manually (requires SPECIALIST_TYPE)"
	@echo "  make deploy-retraining-cronjob - Deploy retraining CronJob to Kubernetes"
	@echo "  make test-feedback             - Run feedback system tests"
	@echo ""
	@echo "Security (Unified CLI):"
	@echo "  make security-init             - Inicializar Vault e SPIRE"
	@echo "  make security-validate         - Validar todos os componentes de seguranca"
	@echo "  make security-audit            - Gerar relatorio de auditoria de seguranca"
	@echo "  make security-vault-init       - Inicializar Vault (auth, engines, policies, roles)"
	@echo "  make security-vault-backup     - Criar backup do Vault"
	@echo "  make security-vault-populate   - Popular secrets no Vault"
	@echo "  make security-spire-deploy     - Deploy SPIRE"
	@echo "  make security-spire-register   - Registrar workload entries no SPIRE"
	@echo "  make security-certs-setup      - Setup cert-manager"
	@echo "  make security-certs-validate   - Validar certificados (expiracao)"
	@echo "  make security-secrets-create   - Criar secrets Phase 2"
	@echo "  make security-secrets-validate - Validar secrets"
	@echo "  make security-policies-transition - Transicionar politicas warn -> enforce"
	@echo "  make security-validate-mtls    - Validar conectividade mTLS"
	@echo "  make security-validate-vault   - Validar Vault + SPIFFE"
	@echo "  make security-dry-run          - Executar validacao em modo dry-run"
	@echo "  make security-test             - Executar testes de integracao do CLI"
	@echo ""
	@echo "Use 'make help' to see this message again."

# ============================================================================
# Testing Targets (Unified CLI)
# ============================================================================

## test: Run all tests
test:
	@./tests/run-tests.sh --type all

## test-unit: Run unit tests only
test-unit:
	@./tests/run-tests.sh --type unit

## test-integration: Run integration tests only
test-integration:
	@./tests/run-tests.sh --type integration

## test-e2e: Run E2E tests only
test-e2e:
	@./tests/run-tests.sh --type e2e

## test-phase1: Run Phase 1 tests
test-phase1:
	@./tests/run-tests.sh --type e2e --phase 1

## test-phase2: Run Phase 2 tests
test-phase2:
	@./tests/run-tests.sh --type e2e --phase 2

## test-specialists: Run specialist tests
test-specialists:
	@./tests/run-tests.sh --component specialists

## test-coverage: Run tests with coverage
test-coverage:
	@./tests/run-tests.sh --type all --coverage

## test-parallel: Run tests in parallel
test-parallel:
	@./tests/run-tests.sh --type all --parallel --jobs 8

## test-dry-run: Show which tests would run
test-dry-run:
	@./tests/run-tests.sh --type all --dry-run

## test-clean: Clean test results
test-clean:
	@rm -rf tests/results/*.json tests/results/*.md tests/results/*.xml
	@rm -rf tests/coverage tests/logs
	@rm -rf tests/results/coverage
	@echo "Test results cleaned."

## test-specialists-unit: [DEPRECATED] Use 'make test-unit'
test-specialists-unit:
	@echo "⚠️  DEPRECATED: Use 'make test-unit' instead"
	@./tests/run-tests.sh --type unit

## test-phase1-pre-validate: [DEPRECATED] Use 'make test-phase1'
test-phase1-pre-validate:
	@echo "⚠️  DEPRECATED: Use 'make test-phase1' instead"
	@./tests/run-tests.sh --type e2e --phase 1

# ============================================================================
# Business Metrics Targets
# ============================================================================

## business-metrics-collect: Executar coleta de business metrics manualmente
business-metrics-collect:
	@echo "Coletando business metrics..."
	cd libraries/python/neural_hive_specialists && \
	python -m scripts.run_business_metrics_collector --window-hours 24

## business-metrics-collect-dry-run: Simular coleta de business metrics
business-metrics-collect-dry-run:
	@echo "Simulando coleta de business metrics (dry-run)..."
	cd libraries/python/neural_hive_specialists && \
	python -m scripts.run_business_metrics_collector --window-hours 24 --dry-run

## anomaly-detector-train: Treinar modelo de anomaly detection
anomaly-detector-train:
	@echo "Treinando modelo de anomaly detection..."
	cd libraries/python/neural_hive_specialists && \
	python -m scripts.train_anomaly_detector --window-days 30

## test-business-metrics: Executar testes de business metrics
test-business-metrics:
	cd libraries/python/neural_hive_specialists && \
	pytest tests/test_business_metrics_collector.py \
	       tests/test_anomaly_detector.py \
	       -v --cov=neural_hive_specialists/observability

## deploy-business-metrics-cronjob: Deploy CronJob de business metrics
deploy-business-metrics-cronjob:
	@echo "Deploying business metrics CronJob..."
	kubectl apply -f k8s/cronjobs/business-metrics-collector-job.yaml
	@echo "✅ CronJob deployed"

## view-business-metrics: Abrir dashboard de business metrics no Grafana
view-business-metrics:
	@echo "Abrindo dashboard de business metrics..."
	@open http://localhost:3000/d/business-metrics 2>/dev/null || \
	 xdg-open http://localhost:3000/d/business-metrics 2>/dev/null || \
	 echo "Abra http://localhost:3000/d/business-metrics manualmente"

# ============================================================================
# Ensemble & A/B Testing Targets
# ============================================================================

## analyze-ab-test: Analisar resultados de A/B test para specialist type
analyze-ab-test:
	@echo "Analisando resultados de A/B test..."
	@if [ ! -f scripts/analyze_ab_test_results.py ]; then \
		echo "❌ Erro: scripts/analyze_ab_test_results.py não encontrado"; \
		echo "   Este script ainda não foi implementado."; \
		exit 1; \
	fi
	@if [ ! -s scripts/analyze_ab_test_results.py ]; then \
		echo "❌ Erro: scripts/analyze_ab_test_results.py está vazio"; \
		echo "   Este script ainda não foi implementado."; \
		exit 1; \
	fi
	@if [ -z "$(SPECIALIST_TYPE)" ]; then \
		echo "Erro: SPECIALIST_TYPE não definido. Use: make analyze-ab-test SPECIALIST_TYPE=technical"; \
		exit 1; \
	fi
	python3 scripts/analyze_ab_test_results.py \
	  --specialist-type $(SPECIALIST_TYPE) \
	  --window-days 7 \
	  --output-format markdown

## analyze-ab-test-json: Analisar A/B test e gerar JSON
analyze-ab-test-json:
	@echo "Analisando A/B test e gerando JSON..."
	@if [ ! -f scripts/analyze_ab_test_results.py ]; then \
		echo "❌ Erro: scripts/analyze_ab_test_results.py não encontrado"; \
		echo "   Este script ainda não foi implementado."; \
		exit 1; \
	fi
	@if [ ! -s scripts/analyze_ab_test_results.py ]; then \
		echo "❌ Erro: scripts/analyze_ab_test_results.py está vazio"; \
		echo "   Este script ainda não foi implementado."; \
		exit 1; \
	fi
	@if [ -z "$(SPECIALIST_TYPE)" ]; then \
		echo "Erro: SPECIALIST_TYPE não definido. Use: make analyze-ab-test-json SPECIALIST_TYPE=technical"; \
		exit 1; \
	fi
	python3 scripts/analyze_ab_test_results.py \
	  --specialist-type $(SPECIALIST_TYPE) \
	  --window-days 7 \
	  --output-format json \
	  --output-file ab_test_report_$(SPECIALIST_TYPE).json

## test-ensemble: Executar testes de ensemble specialist
test-ensemble:
	@echo "Executando testes de ensemble specialist..."
	@if [ ! -f libraries/python/neural_hive_specialists/tests/test_ensemble_specialist.py ]; then \
		echo "❌ Erro: test_ensemble_specialist.py não encontrado"; \
		echo "   Este arquivo de testes ainda não foi implementado."; \
		exit 1; \
	fi
	@if [ ! -s libraries/python/neural_hive_specialists/tests/test_ensemble_specialist.py ]; then \
		echo "❌ Erro: test_ensemble_specialist.py está vazio"; \
		echo "   Os testes ainda não foram implementados."; \
		exit 1; \
	fi
	cd libraries/python/neural_hive_specialists && \
	pytest tests/test_ensemble_specialist.py -v

## test-ab-testing: Executar testes de A/B testing specialist
test-ab-testing:
	@echo "Executando testes de A/B testing specialist..."
	@if [ ! -f libraries/python/neural_hive_specialists/tests/test_ab_testing_specialist.py ]; then \
		echo "❌ Erro: test_ab_testing_specialist.py não encontrado"; \
		echo "   Este arquivo de testes ainda não foi implementado."; \
		exit 1; \
	fi
	@if [ ! -s libraries/python/neural_hive_specialists/tests/test_ab_testing_specialist.py ]; then \
		echo "❌ Erro: test_ab_testing_specialist.py está vazio"; \
		echo "   Os testes ainda não foram implementados."; \
		exit 1; \
	fi
	cd libraries/python/neural_hive_specialists && \
	pytest tests/test_ab_testing_specialist.py -v

## view-model-comparison: Abrir dashboard de comparação de modelos
view-model-comparison:
	@echo "Abrindo dashboard de comparação de modelos..."
	@open http://localhost:3000/d/model-comparison 2>/dev/null || \
	 xdg-open http://localhost:3000/d/model-comparison 2>/dev/null || \
	 echo "Abra http://localhost:3000/d/model-comparison manualmente"

# ============================================================================
# Continuous Learning Targets
# ============================================================================

## check-retraining-trigger: Verificar threshold de re-treinamento (dry-run)
check-retraining-trigger:
	@echo "Verificando threshold de re-treinamento..."
	cd libraries/python/neural_hive_specialists && \
	python -m scripts.run_retraining_trigger --dry-run

## trigger-retraining: Disparar re-treinamento manualmente
trigger-retraining:
	@echo "Disparando re-treinamento..."
	@if [ -z "$(SPECIALIST_TYPE)" ]; then \
		echo "Erro: SPECIALIST_TYPE não definido. Use: make trigger-retraining SPECIALIST_TYPE=technical"; \
		exit 1; \
	fi
	cd libraries/python/neural_hive_specialists && \
	python -m scripts.run_retraining_trigger --specialist-type $(SPECIALIST_TYPE) --force

## deploy-retraining-cronjob: Deploy CronJob de re-treinamento
deploy-retraining-cronjob:
	@echo "Deploying retraining trigger CronJob..."
	kubectl apply -f k8s/cronjobs/retraining-trigger-job.yaml
	@echo "✅ CronJob deployed"

## test-feedback: Executar testes de feedback
test-feedback:
	@echo "Executando testes de feedback..."
	cd libraries/python/neural_hive_specialists && \
	pytest tests/test_feedback_collector.py \
	       tests/test_retraining_trigger.py \
	       tests/test_feedback_api.py \
	       -v --cov=neural_hive_specialists/feedback

## submit-feedback: Submeter feedback manualmente via API
submit-feedback:
	@echo "Submetendo feedback humano..."
	@if [ -z "$(OPINION_ID)" ]; then \
		echo "Erro: OPINION_ID não definido."; \
		echo "Uso: make submit-feedback OPINION_ID=opinion-abc123 RATING=0.9 RECOMMENDATION=approve"; \
		exit 1; \
	fi
	@if [ -z "$(RATING)" ]; then \
		echo "Erro: RATING não definido (0.0-1.0)."; \
		exit 1; \
	fi
	@if [ -z "$(RECOMMENDATION)" ]; then \
		echo "Erro: RECOMMENDATION não definido (approve|reject|review_required)."; \
		exit 1; \
	fi
	@SPECIALIST_URL=$${SPECIALIST_URL:-http://localhost:8000}; \
	JWT_TOKEN=$${JWT_TOKEN:-demo-token}; \
	NOTES=$${NOTES:-"Feedback via make target"}; \
	curl -X POST "$$SPECIALIST_URL/api/v1/feedback" \
		-H "Authorization: Bearer $$JWT_TOKEN" \
		-H "Content-Type: application/json" \
		-d '{ \
			"opinion_id": "$(OPINION_ID)", \
			"human_rating": $(RATING), \
			"human_recommendation": "$(RECOMMENDATION)", \
			"feedback_notes": "'"$$NOTES"'" \
		}' | jq .

## train-model: Treinar/re-treinar modelo de especialista via MLflow
train-model:
	@echo "Treinando modelo de especialista..."
	@if [ -z "$(SPECIALIST_TYPE)" ]; then \
		echo "Erro: SPECIALIST_TYPE não definido."; \
		echo "Uso: make train-model SPECIALIST_TYPE=technical"; \
		exit 1; \
	fi
	@MLFLOW_URI=$${MLFLOW_TRACKING_URI:-http://localhost:5000}; \
	PROJECT_URI=$${MLFLOW_PROJECT_URI:-./mlflow_projects/specialist_retraining}; \
	echo "MLflow Tracking URI: $$MLFLOW_URI"; \
	echo "Project URI: $$PROJECT_URI"; \
	mlflow run $$PROJECT_URI \
		--experiment-name "specialist-retraining-$(SPECIALIST_TYPE)" \
		-P specialist_type=$(SPECIALIST_TYPE) \
		-P feedback_window_days=30

## view-continuous-learning: Abrir dashboard de continuous learning no Grafana
view-continuous-learning:
	@echo "Abrindo dashboard de Continuous Learning..."
	@GRAFANA_URL=$${GRAFANA_URL:-http://localhost:3000}; \
	open "$$GRAFANA_URL/d/continuous-learning" 2>/dev/null || \
	xdg-open "$$GRAFANA_URL/d/continuous-learning" 2>/dev/null || \
	echo "Abra $$GRAFANA_URL/d/continuous-learning manualmente"

## monitor-retraining-runs: Executar monitoramento de runs MLflow manualmente
monitor-retraining-runs:
	@echo "Monitorando runs MLflow de re-treinamento..."
	@MONGODB_URI=$${MONGODB_URI:-mongodb://localhost:27017}; \
	MLFLOW_URI=$${MLFLOW_TRACKING_URI:-http://localhost:5000}; \
	cd libraries/python/neural_hive_specialists && \
	python -m scripts.monitor_retraining_runs \
		--mongodb-uri $$MONGODB_URI \
		--mlflow-tracking-uri $$MLFLOW_URI \
		--max-run-age-hours 24

.PHONY: check-retraining-trigger trigger-retraining deploy-retraining-cronjob test-feedback submit-feedback train-model view-continuous-learning monitor-retraining-runs

# ============================================================================
# Multi-Tenancy & API Gateway Targets
# ============================================================================

## deploy-envoy-gateway: Deploy Envoy API Gateway
deploy-envoy-gateway:
	@echo "Deploying Envoy Gateway..."
	helm install envoy-gateway ./helm-charts/envoy-gateway \
		--namespace default \
		--create-namespace
	@echo "✅ Envoy Gateway deployed"

## upgrade-envoy-gateway: Upgrade Envoy API Gateway
upgrade-envoy-gateway:
	@echo "Upgrading Envoy Gateway..."
	helm upgrade envoy-gateway ./helm-charts/envoy-gateway \
		--namespace default
	@echo "✅ Envoy Gateway upgraded"

## migrate-ledger-tenant-id: Migrar ledger para adicionar tenant_id
migrate-ledger-tenant-id:
	@echo "Migrando ledger para multi-tenancy..."
	@if [ -z "$(MONGODB_URI)" ]; then \
		echo "❌ Erro: MONGODB_URI não definido"; \
		echo "   Use: make migrate-ledger-tenant-id MONGODB_URI=mongodb://localhost:27017"; \
		exit 1; \
	fi
	python scripts/migrate_ledger_add_tenant_id.py \
		--mongodb-uri $(MONGODB_URI) \
		--dry-run
	@read -p "Confirmar migração? (y/N): " confirm && \
	  if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
	    python scripts/migrate_ledger_add_tenant_id.py --mongodb-uri $(MONGODB_URI); \
	  else \
	    echo "Migração cancelada"; \
	  fi

## test-multi-tenancy: Executar testes de multi-tenancy
test-multi-tenancy:
	@echo "Executando testes de multi-tenancy..."
	cd libraries/python/neural_hive_specialists && \
	pytest tests/test_multi_tenant_specialist.py \
	       tests/test_tenant_isolation.py \
	       -v --cov=neural_hive_specialists

## deploy-tenant-configs: Deploy ConfigMap de configurações de tenants
deploy-tenant-configs:
	@echo "Deploying tenant configs ConfigMap..."
	kubectl apply -f k8s/configmaps/tenant-configs.yaml
	@echo "✅ Tenant configs ConfigMap deployed"

## view-envoy-stats: Visualizar estatísticas do Envoy
view-envoy-stats:
	@echo "Abrindo Envoy admin interface..."
	@kubectl port-forward svc/envoy-gateway 9901:9901 &
	@sleep 2
	@open http://localhost:9901/stats/prometheus 2>/dev/null || \
	 xdg-open http://localhost:9901/stats/prometheus 2>/dev/null || \
	 echo "Abra http://localhost:9901/stats/prometheus manualmente"

## view-multi-tenancy-dashboard: Abrir dashboard de multi-tenancy
view-multi-tenancy-dashboard:
	@echo "Abrindo dashboard de multi-tenancy..."
	@open http://localhost:3000/d/multi-tenancy 2>/dev/null || \
	 xdg-open http://localhost:3000/d/multi-tenancy 2>/dev/null || \
	 echo "Abra http://localhost:3000/d/multi-tenancy manualmente"

## add-tenant: Adicionar novo tenant (interativo)
add-tenant:
	@echo "Adicionando novo tenant..."
	@read -p "Tenant ID: " tenant_id && \
	 read -p "Tenant Name: " tenant_name && \
	 read -p "Rate Limit (req/s): " rate_limit && \
	 echo "Editando ConfigMap..." && \
	 kubectl edit configmap specialist-tenant-configs

.PHONY: deploy-envoy-gateway upgrade-envoy-gateway migrate-ledger-tenant-id test-multi-tenancy deploy-tenant-configs view-envoy-stats view-multi-tenancy-dashboard add-tenant

# ============================================================================
# Disaster Recovery Targets
# ============================================================================

## dr-backup: Executar backup de disaster recovery
dr-backup:
	@echo "Executando backup de disaster recovery..."
	cd libraries/python/neural_hive_specialists && \
	python -m scripts.run_disaster_recovery_backup --verbose

## dr-backup-dry-run: Simular backup (dry-run)
dr-backup-dry-run:
	@echo "Simulando backup de disaster recovery..."
	cd libraries/python/neural_hive_specialists && \
	python -m scripts.run_disaster_recovery_backup --dry-run

## dr-list-backups: Listar backups disponíveis
dr-list-backups:
	@echo "Listando backups disponíveis..."
	cd libraries/python/neural_hive_specialists && \
	python -m scripts.run_disaster_recovery_restore --list --specialist-type business

## dr-restore: Restaurar backup mais recente
dr-restore:
	@echo "Restaurando backup mais recente..."
	cd libraries/python/neural_hive_specialists && \
	python -m scripts.run_disaster_recovery_restore --latest --specialist-type business

## dr-restore-force: Restaurar backup sem confirmação (cuidado!)
dr-restore-force:
	@echo "Restaurando backup (modo force, sem confirmação)..."
	cd libraries/python/neural_hive_specialists && \
	python -m scripts.run_disaster_recovery_restore --latest --specialist-type business --force

## dr-test-recovery: Testar recovery do backup mais recente
dr-test-recovery:
	@echo "Testando recovery de backup..."
	cd libraries/python/neural_hive_specialists && \
	python -m scripts.run_disaster_recovery_test --specialist-type business --verbose

## deploy-dr-cronjobs: Deploy CronJobs de disaster recovery
deploy-dr-cronjobs:
	@echo "Deploying disaster recovery CronJobs..."
	kubectl apply -f k8s/cronjobs/disaster-recovery-backup-job.yaml
	kubectl apply -f k8s/cronjobs/disaster-recovery-test-job.yaml
	@echo "✅ Disaster recovery CronJobs deployed"

## check-dr-status: Verificar status de disaster recovery
check-dr-status:
	@echo "Verificando status de disaster recovery..."
	@echo "\n=== CronJobs ==="
	kubectl get cronjobs -n neural-hive-mind | grep disaster-recovery
	@echo "\n=== Jobs Recentes ==="
	kubectl get jobs -n neural-hive-mind | grep disaster-recovery | head -5
	@echo "\n=== Último Backup ==="
	kubectl logs -n neural-hive-mind -l app=disaster-recovery --tail=50 || echo "Nenhum log encontrado"

## dr-logs: Ver logs de disaster recovery
dr-logs:
	@echo "Logs de disaster recovery..."
	kubectl logs -n neural-hive-mind -l app=disaster-recovery -f

.PHONY: dr-backup dr-backup-dry-run dr-list-backups dr-restore dr-restore-force dr-test-recovery deploy-dr-cronjobs check-dr-status dr-logs

# ============================================================================
# Security Targets (Unified CLI)
# ============================================================================

## security-init: Inicializar Vault e SPIRE
security-init:
	@echo "Inicializando componentes de segurança..."
	@./scripts/security.sh vault init
	@./scripts/security.sh spire deploy

## security-validate: Validar todos os componentes de segurança
security-validate:
	@./scripts/security.sh validate all

## security-audit: Gerar relatório de auditoria de segurança
security-audit:
	@./scripts/security.sh audit report --output reports/security-audit-$(shell date +%Y%m%d).html
	@echo "Relatório gerado: reports/security-audit-$(shell date +%Y%m%d).html"

## security-vault-init: Inicializar Vault (auth, engines, policies, roles)
security-vault-init:
	@./scripts/security.sh vault init

## security-vault-backup: Criar backup do Vault
security-vault-backup:
	@./scripts/security.sh vault backup --output /tmp/vault-backup-$(shell date +%Y%m%d).tar.gz

## security-vault-populate: Popular secrets no Vault
security-vault-populate:
	@./scripts/security.sh vault populate --mode static --environment dev

## security-spire-deploy: Deploy SPIRE
security-spire-deploy:
	@./scripts/security.sh spire deploy --namespace spire-system

## security-spire-register: Registrar workload entries no SPIRE
security-spire-register:
	@./scripts/security.sh spire register --service all

## security-certs-setup: Setup cert-manager
security-certs-setup:
	@./scripts/security.sh certs setup --environment production

## security-certs-validate: Validar certificados (expiração)
security-certs-validate:
	@./scripts/security.sh certs validate --check-expiry --days 30

## security-secrets-create: Criar secrets Phase 2
security-secrets-create:
	@./scripts/security.sh secrets create --phase 2 --mode static

## security-secrets-validate: Validar secrets
security-secrets-validate:
	@./scripts/security.sh secrets validate --phase 2

## security-policies-transition: Transicionar políticas warn -> enforce
security-policies-transition:
	@./scripts/security.sh policies transition --dry-run

## security-validate-mtls: Validar conectividade mTLS
security-validate-mtls:
	@./scripts/security.sh validate mtls

## security-validate-vault: Validar Vault + SPIFFE
security-validate-vault:
	@./scripts/security.sh validate vault

## security-dry-run: Executar validação em modo dry-run
security-dry-run:
	@./scripts/security.sh --dry-run validate all

## security-test: Executar testes de integração do CLI de segurança
security-test:
	@echo "Executando testes de integração do CLI de segurança..."
	@./tests/integration/security-cli-test.sh

.PHONY: security-init security-validate security-audit security-vault-init security-vault-backup security-vault-populate
.PHONY: security-spire-deploy security-spire-register security-certs-setup security-certs-validate
.PHONY: security-secrets-create security-secrets-validate security-policies-transition
.PHONY: security-validate-mtls security-validate-vault security-dry-run security-test

# ============================================================================
# Validation Targets
# ============================================================================

# Validação
validate: validate-all

validate-all:
	@./scripts/validate.sh --target all

validate-specialists:
	@./scripts/validate.sh --target specialists

validate-infrastructure:
	@./scripts/validate.sh --target infrastructure

validate-services:
	@./scripts/validate.sh --target services

validate-security:
	@./scripts/validate.sh --target security

validate-observability:
	@./scripts/validate.sh --target observability

validate-performance:
	@./scripts/validate.sh --target performance

validate-phase:
	@./scripts/validate.sh --target phase --phase $(PHASE)

validate-e2e:
	@./scripts/validate.sh --target e2e

# Validação com relatórios
validate-report:
	@./scripts/validate.sh --target all --report html --report-file /tmp/validation-report.html
	@echo "Relatório gerado: /tmp/validation-report.html"

validate-ci:
	@./scripts/validate.sh --target all --report json --report-file /tmp/validation-report.json
