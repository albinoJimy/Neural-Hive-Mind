SHELL := /bin/bash

ENV ?= local
PHASE ?= 1
VERSION ?= latest
MODEL_NAME ?= default-model
SPECIALIST_TYPE ?= business

BUILD := ./scripts/build.sh
DEPLOY := ./scripts/deploy.sh
TEST := ./tests/run-tests.sh
VALIDATE := ./scripts/validate.sh
SEC := ./scripts/security.sh
OBS := ./scripts/observability.sh
MAINT := ./scripts/maintenance.sh
SETUP := ./scripts/setup.sh
ML := ./ml_pipelines/ml.sh

.PHONY: help help-build help-deploy help-test help-validate help-security help-ml help-observability
help:
	@echo "Neural Hive-Mind Makefile" && \
	echo "Categorias: build, deploy, test, validate, security, ml, observability" && \
	echo "Use make help-<categoria> para detalhes" && \
	echo "Atalhos: build-local | deploy-local | test | validate | security-init"
help-build: ; @$(BUILD) --help
help-deploy: ; @$(DEPLOY) --help
help-test: ; @$(TEST) --help
help-validate: ; @$(VALIDATE) --help
help-security: ; @$(SEC) --help
help-ml: ; @$(ML) --help
help-observability: ; @$(OBS) --help

.PHONY: proto-gen proto-gen-all clean-proto
proto-gen: ; @./scripts/compile_protos.sh --service specialists
proto-gen-all: ; @./scripts/compile_protos.sh --all
clean-proto: ; @rm -rf libraries/python/neural_hive_specialists/proto_gen

.PHONY: minikube-setup minikube-start minikube-stop minikube-clean minikube-reset minikube-validate minikube-status minikube-dashboard
minikube-setup: ; @$(SETUP) minikube
minikube-start:
	@minikube start --driver=docker --cpus=4 --memory=8192 --disk-size=20g --kubernetes-version=v1.29.0
	@minikube addons enable ingress registry
minikube-stop: ; @minikube stop
minikube-clean:
	@minikube delete
	@rm -rf .tmp/bootstrap*
minikube-reset: minikube-clean minikube-setup
minikube-validate: ; @$(VALIDATE) --target infrastructure --quick
minikube-status:
	@minikube status || echo "Minikube not running"
	@kubectl get namespaces | grep -E 'NAME|neural-hive' || true
minikube-dashboard: ; @minikube dashboard

.PHONY: build-ecr build-all build-prod build-local build-images build-frontend build-backend build-specialists build-phase1 build-phase2 build-ci build-dev
build-%: ; @$(BUILD) --target $*
build-ecr: ; @$(BUILD) --target ecr --push
build-all: ; @$(BUILD) --target all --push
build-prod: ; @$(BUILD) --target prod --push

.PHONY: deploy-local deploy-eks deploy-phase1 deploy-phase2
deploy-local: ; @$(DEPLOY) --env local --phase 1
deploy-eks: ; @$(DEPLOY) --env eks --phase all
deploy-phase1: ; @$(DEPLOY) --env $(ENV) --phase 1
deploy-phase2: ; @$(DEPLOY) --env $(ENV) --phase 2

.PHONY: test test-unit test-integration test-e2e test-phase1 test-phase2 test-specialists test-coverage test-parallel test-clean
test: ; @$(TEST) --type all
test-unit: ; @$(TEST) --type unit
test-integration: ; @$(TEST) --type integration
test-e2e: ; @$(TEST) --type e2e
test-phase1: ; @$(TEST) --type e2e --phase 1
test-phase2: ; @$(TEST) --type e2e --phase 2
test-specialists: ; @$(TEST) --component specialists
test-coverage: ; @$(TEST) --type all --coverage
test-parallel: ; @$(TEST) --type all --parallel --jobs 8
test-clean: ; @rm -rf tests/results tests/coverage tests/logs

.PHONY: validate validate-all validate-specialists validate-infrastructure validate-services validate-security validate-observability validate-performance validate-phase validate-e2e
validate: validate-all
validate-all: ; @$(VALIDATE) --target all
validate-specialists: ; @$(VALIDATE) --target specialists
validate-infrastructure: ; @$(VALIDATE) --target infrastructure
validate-services: ; @$(VALIDATE) --target services
validate-security: ; @$(VALIDATE) --target security
validate-observability: ; @$(VALIDATE) --target observability
validate-performance: ; @$(VALIDATE) --target performance
validate-phase: ; @$(VALIDATE) --target phase --phase $(PHASE)
validate-e2e: ; @$(VALIDATE) --target e2e

.PHONY: security-init security-validate security-audit security-vault-init security-vault-populate security-spire-deploy security-spire-register security-certs-setup security-certs-validate security-secrets-create security-secrets-validate security-validate-mtls
security-init:
	@$(SEC) vault init
	@$(SEC) spire deploy
security-validate: ; @$(SEC) validate all
security-audit: ; @$(SEC) audit report --output reports/security-audit-$(shell date +%Y%m%d).html
security-vault-init: ; @$(SEC) vault init
security-vault-populate: ; @$(SEC) vault populate --mode static --environment dev
security-spire-deploy: ; @$(SEC) spire deploy --namespace spire-system
security-spire-register: ; @$(SEC) spire register --service all
security-certs-setup: ; @$(SEC) certs setup --environment production
security-certs-validate: ; @$(SEC) certs validate --check-expiry --days 30
security-secrets-create: ; @$(SEC) secrets create --phase 2 --mode static
security-secrets-validate: ; @$(SEC) secrets validate --phase 2
security-validate-mtls: ; @$(SEC) validate mtls

.PHONY: ml-train ml-validate ml-promote ml-retrain ml-rollback ml-generate-dataset
ml-train: ; @$(ML) train --specialist $(SPECIALIST_TYPE)
ml-validate: ; @$(ML) validate --all
ml-promote: ; @$(ML) promote --model $(MODEL_NAME) --version $(VERSION)
ml-retrain: ; @$(ML) retrain --specialist $(SPECIALIST_TYPE)
ml-rollback: ; @$(ML) rollback --specialist $(SPECIALIST_TYPE)
ml-generate-dataset: ; @$(ML) generate-dataset --specialist $(SPECIALIST_TYPE)

.PHONY: business-metrics-collect anomaly-detector-train deploy-business-metrics-cronjob view-business-metrics
business-metrics-collect: ; @$(ML) business-metrics collect --window-hours 24
anomaly-detector-train: ; @$(ML) anomaly-detector train --window-days 30
deploy-business-metrics-cronjob: ; @kubectl apply -f k8s/cronjobs/business-metrics-collector-job.yaml
view-business-metrics: ; @$(OBS) dashboards access --dashboard business-metrics

.PHONY: continuous-learning-trigger deploy-retraining-cronjob continuous-learning-feedback continuous-learning-monitor view-continuous-learning
continuous-learning-trigger: ; @$(ML) retrain --specialist $(SPECIALIST_TYPE) --force
deploy-retraining-cronjob: ; @kubectl apply -f k8s/cronjobs/retraining-trigger-job.yaml
continuous-learning-feedback: ; @$(ML) feedback submit --specialist $(SPECIALIST_TYPE)
continuous-learning-monitor: ; @$(ML) status --all --verbose
view-continuous-learning: ; @$(OBS) dashboards access --dashboard continuous-learning

.PHONY: deploy-envoy-gateway migrate-ledger-multi-tenancy test-multi-tenancy deploy-tenant-configs view-multi-tenancy-stats
deploy-envoy-gateway: ; @$(DEPLOY) --services envoy-gateway --env $(ENV)
migrate-ledger-multi-tenancy: ; @python scripts/migrate_ledger_add_tenant_id.py
test-multi-tenancy: ; @$(TEST) --component multi-tenancy
deploy-tenant-configs: ; @kubectl apply -f k8s/configmaps/tenant-configs.yaml
view-multi-tenancy-stats: ; @$(OBS) dashboards access --dashboard multi-tenancy

.PHONY: dr-backup dr-restore dr-test deploy-dr-cronjobs dr-status
dr-backup: ; @$(MAINT) backup --type full --output /backup/dr-$(shell date +%Y%m%d).tar.gz
dr-restore: ; @$(MAINT) restore --input $(BACKUP_FILE)
dr-test: ; @$(ML) disaster-recovery test --specialist $(SPECIALIST_TYPE)
deploy-dr-cronjobs:
	@kubectl apply -f k8s/cronjobs/disaster-recovery-backup-job.yaml
	@kubectl apply -f k8s/cronjobs/disaster-recovery-test-job.yaml
dr-status: ; @$(MAINT) disaster-recovery status

.PHONY: observability-setup observability-validate observability-dashboards observability-test-slos observability-test-correlation
observability-setup: ; @$(OBS) setup
observability-validate: ; @$(OBS) validate
observability-dashboards: ; @$(OBS) dashboards access
observability-test-slos: ; @$(OBS) test slos
observability-test-correlation: ; @$(OBS) test correlation
