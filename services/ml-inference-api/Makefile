# Makefile para ML Inference API

.PHONY: help install test lint format clean run docker-build docker-run

help: ## Mostra ajuda
	@echo "Comandos disponíveis:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Instala dependências
	pip install -r requirements.txt

test: ## Executa testes
	pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=html

test-unit: ## Executa apenas testes unitários
	pytest tests/unit/ -v

test-integration: ## Executa apenas testes de integração
	pytest tests/integration/ -v

lint: ## Executa linter (ruff)
	ruff check src/ tests/

format: ## Formata código (black e ruff)
	black src/ tests/
	ruff check --fix src/ tests/

type-check: ## Executa verificação de tipos (mypy)
	mypy src/

clean: ## Limpa arquivos gerados
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	rm -rf .pytest_cache .coverage htmlcov/

run: ## Executa serviço localmente
	python -m src.main

dev: ## Executa em modo desenvolvimento com reload
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8010

docker-build: ## Build imagem Docker
	docker build -t ml-inference-api:1.0.0 .

docker-run: ## Executa container Docker
	docker run -p 8010:8010 -p 9091:9091 \
		-v $(PWD)/ml_models:/app/ml_models \
		--env-file .env \
		ml-inference-api:1.0.0

validate: lint type-check test ## Executa todas validações

all: clean install format lint test ## Executa setup completo
