.PHONY: help install test lint format docker-build docker-run proto clean

help:
	@echo "Analyst Agents - Makefile Commands"
	@echo "install       - Install dependencies"
	@echo "test          - Run tests"
	@echo "lint          - Run linters"
	@echo "format        - Format code"
	@echo "docker-build  - Build Docker image"
	@echo "docker-run    - Run Docker container"
	@echo "proto         - Generate gRPC code from proto files"
	@echo "clean         - Clean generated files"

install:
	pip install -r requirements.txt

test:
	pytest tests/ -v --cov=src --cov-report=html

lint:
	flake8 src/ tests/
	mypy src/

format:
	black src/ tests/
	isort src/ tests/

docker-build:
	docker build -t neural-hive/analyst-agents:latest .

docker-run:
	docker run -p 8000:8000 -p 50051:50051 --env-file .env neural-hive/analyst-agents:latest

proto:
	python -m grpc_tools.protoc -I./src/proto --python_out=./src/proto --grpc_python_out=./src/proto ./src/proto/analyst_agent.proto

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
	rm -rf .pytest_cache .coverage htmlcov
