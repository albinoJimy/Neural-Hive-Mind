.PHONY: install proto test lint format docker-build docker-push helm-lint helm-install helm-upgrade clean

install:
	pip install -r requirements.txt

proto:
	python -m grpc_tools.protoc -I./src/proto --python_out=./src/proto --grpc_python_out=./src/proto ./src/proto/optimizer_agent.proto
	python -m grpc_tools.protoc -I./proto --python_out=./proto --grpc_python_out=./proto ./proto/consensus_engine_extensions.proto
	python -m grpc_tools.protoc -I./proto --python_out=./proto --grpc_python_out=./proto ./proto/orchestrator_extensions.proto
	@echo "Proto files compiled successfully"

test:
	pytest

lint:
	flake8 src/ tests/
	black --check src/ tests/
	isort --check-only src/ tests/

format:
	black src/ tests/
	isort src/ tests/

docker-build:
	docker build -t optimizer-agents:latest .

docker-push:
	docker tag optimizer-agents:latest registry.neuralhivemind.io/optimizer-agents:latest
	docker push registry.neuralhivemind.io/optimizer-agents:latest

helm-lint:
	helm lint helm-chart/

helm-install:
	helm install optimizer-agents helm-chart/ -n optimizer-agents --create-namespace

helm-upgrade:
	helm upgrade optimizer-agents helm-chart/ -n optimizer-agents

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
