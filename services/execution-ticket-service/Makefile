.PHONY: help install dev run test lint format clean proto build push deploy validate

# Variáveis
PYTHON := python3
PIP := $(PYTHON) -m pip
SERVICE_NAME := execution-ticket-service
VERSION := 1.0.0
REGISTRY := localhost:5000
NAMESPACE := neural-hive-orchestration

help: ## Mostra esta mensagem de ajuda
	@echo "Execution Ticket Service - Comandos disponíveis:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Instala dependências de produção
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

dev: ## Instala dependências de desenvolvimento
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PIP) install pytest pytest-asyncio pytest-cov black flake8 mypy

run: ## Executa o serviço localmente
	$(PYTHON) -m src.main

test: ## Executa testes
	pytest tests/ -v --cov=src --cov-report=html

lint: ## Verifica código com flake8
	flake8 src/ --max-line-length=120 --exclude=*_pb2.py,*_pb2_grpc.py

format: ## Formata código com black
	black src/ --line-length=120 --exclude='.*_pb2\.py|.*_pb2_grpc\.py'

clean: ## Remove arquivos temporários
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
	find . -type f -name '*.pyo' -delete
	find . -type f -name '*~' -delete
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ htmlcov/

proto: ## Compila arquivos Protocol Buffers
	@echo "Compilando proto files..."
	$(PYTHON) -m grpc_tools.protoc \
		-I./protos \
		--python_out=./src/grpc_service \
		--grpc_python_out=./src/grpc_service \
		--pyi_out=./src/grpc_service \
		./protos/ticket_service.proto
	@echo "Proto files compilados com sucesso!"

migration-create: ## Cria nova migration (use MSG="description")
	@echo "Criando migration: $(MSG)"
	cd .. && alembic -c execution-ticket-service/alembic.ini revision --autogenerate -m "$(MSG)"

migration-upgrade: ## Aplica migrations
	cd .. && alembic -c execution-ticket-service/alembic.ini upgrade head

migration-downgrade: ## Reverte última migration
	cd .. && alembic -c execution-ticket-service/alembic.ini downgrade -1

build: ## Build da imagem Docker
	docker build -t $(REGISTRY)/$(SERVICE_NAME):$(VERSION) \
		--build-arg GIT_COMMIT=$$(git rev-parse HEAD) \
		--build-arg BUILD_DATE=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") \
		--build-arg VERSION=$(VERSION) \
		.
	@echo "Imagem built: $(REGISTRY)/$(SERVICE_NAME):$(VERSION)"

push: build ## Push da imagem para registry
	docker push $(REGISTRY)/$(SERVICE_NAME):$(VERSION)
	@echo "Imagem pushed para $(REGISTRY)/$(SERVICE_NAME):$(VERSION)"

deploy: ## Deploy no Kubernetes via Helm
	@echo "Deploying $(SERVICE_NAME) to $(NAMESPACE)..."
	../../scripts/deploy/deploy-execution-ticket-service.sh

validate: ## Valida deployment
	@echo "Validating $(SERVICE_NAME) in $(NAMESPACE)..."
	../../scripts/validation/validate-execution-ticket-service.sh

logs: ## Mostra logs do serviço
	kubectl logs -f -l app=$(SERVICE_NAME) -n $(NAMESPACE)

shell: ## Abre shell no pod
	kubectl exec -it $$(kubectl get pods -n $(NAMESPACE) -l app=$(SERVICE_NAME) -o jsonpath='{.items[0].metadata.name}') -n $(NAMESPACE) -- /bin/bash

port-forward: ## Port forward para acesso local
	@echo "Port forwarding $(SERVICE_NAME)..."
	@echo "  - API REST: http://localhost:8000"
	@echo "  - gRPC: localhost:50052"
	@echo "  - Metrics: http://localhost:9090"
	kubectl port-forward -n $(NAMESPACE) svc/$(SERVICE_NAME) 8000:8000 50052:50052 9090:9090
