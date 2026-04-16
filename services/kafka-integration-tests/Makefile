# Makefile para Kafka Integration Tests

.PHONY: help up down test test-unit test-integration test-e2e clean logs

# Variáveis
COMPOSE_FILE = docker-compose.test.yml
PROJECT_NAME = nhm-kafka-tests

# Ajuda
help:
	@echo "Comandos disponíveis:"
	@echo "  make up           - Sobe infraestrutura de teste (Kafka, MongoDB, Redis)"
	@echo "  make down         - Para infraestrutura de teste"
	@echo "  make logs         - Mostra logs dos containers"
	@echo "  make test         - Executa todos os testes"
	@echo "  make test-unit    - Executa testes unitários"
	@echo "  make test-integration - Executa testes de integração"
	@echo "  make test-e2e     - Executa testes E2E"
	@echo "  make clean        - Para e remove containers/volumes"

# Infraestrutura
up:
	docker-compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) up -d
	@echo "Aguardando Kafka ficar pronto..."
	@sleep 10
	@echo "Infraestrutura pronta!"

down:
	docker-compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) down

logs:
	docker-compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) logs -f

restart: down up

# Testes
test:
	@echo "Executando todos os testes..."
	pytest tests/ -v

test-unit:
	@echo "Executando testes unitários..."
	pytest tests/ -v -m unit

test-integration:
	@echo "Executando testes de integração..."
	pytest tests/ -v -m integration

test-e2e:
	@echo "Executando testes E2E..."
	pytest tests/ -v -m e2e

test-kafka:
	@echo "Executando testes que requerem Kafka..."
	pytest tests/ -v -m kafka

test-coverage:
	@echo "Executando testes com coverage..."
	pytest tests/ -v --cov=../architect-agent --cov=../software-engineering-pipeline --cov-report=html

# Limpeza
clean:
	docker-compose -f $(COMPOSE_FILE) -p $(PROJECT_NAME) down -v
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
