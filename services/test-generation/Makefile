.PHONY: test lint format run build install

# Variáveis
PYTHON := python3
PYTHONPATH := src
SERVICE_NAME := test-generation
PORT := 8013

# Instalar dependências
install:
	pip3 install -e .

# Rodar testes
test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/ -v --no-cov

# Testes com coverage
test-cov:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/ -v --cov=src --cov-report=html --cov-report=term

# Lint
lint:
	ruff check src/ tests/

# Format
format:
	black src/ tests/
	ruff check --fix src/ tests/

# Rodar serviço localmente
run:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m uvicorn main:app --reload --port $(PORT)

# Build Docker image
build:
	docker build -t nhm/$(SERVICE_NAME):v0.1.0 .

# Deploy para Kubernetes
deploy:
	kubectl apply -f deployment/k8s-deployment.yaml

# Logs do pod Kubernetes
logs:
	kubectl logs -l app=$(SERVICE_NAME) -n neural-hive-mind -f

# Limpar cache
clean:
	rm -rf .pytest_cache __pycache__ src/__pycache__ tests/__pycache__
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete

# Ajuda
help:
	@echo "Comandos disponíveis:"
	@echo "  make install   - Instalar dependências"
	@echo "  make test      - Rodar testes"
	@echo "  make test-cov  - Rodar testes com coverage"
	@echo "  make lint      - Verificar código com ruff"
	@echo "  make format    - Format código com black e ruff"
	@echo "  make run       - Rodar serviço localmente"
	@echo "  make build     - Build Docker image"
	@echo "  make deploy    - Deploy para Kubernetes"
	@echo "  make logs      - Ver logs Kubernetes"
	@echo "  make clean     - Limpar cache"
