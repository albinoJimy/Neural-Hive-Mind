.PHONY: help install proto lint format test run docker-build deploy validate logs clean

help:
	@echo "Queen Agent - Comandos disponíveis:"
	@echo "  make install       - Instalar dependências Python"
	@echo "  make proto         - Compilar arquivos proto"
	@echo "  make lint          - Executar linters"
	@echo "  make format        - Formatar código"
	@echo "  make test          - Executar testes unitários"
	@echo "  make run           - Executar serviço localmente"
	@echo "  make docker-build  - Build imagem Docker"
	@echo "  make deploy        - Deploy no Kubernetes"
	@echo "  make validate      - Validar deployment"
	@echo "  make logs          - Tail logs do pod"
	@echo "  make clean         - Limpar arquivos temporários"

install:
	pip install --upgrade pip
	pip install -r requirements.txt

proto:
	python3 -m grpc_tools.protoc -I./src/proto --python_out=./src/proto --grpc_python_out=./src/proto --pyi_out=./src/proto ./src/proto/queen_agent.proto
	sed -i 's/^import queen_agent_pb2/from . import queen_agent_pb2/' ./src/proto/queen_agent_pb2_grpc.py

lint:
	flake8 src/
	mypy src/

format:
	black src/
	isort src/

test:
	pytest tests/ -v

run:
	python -m src.main

docker-build:
	docker build -t neural-hive/queen-agent:1.0.0 .

deploy:
	./scripts/deploy-queen-agent.sh

validate:
	./scripts/validate-queen-agent.sh

logs:
	kubectl logs -f -l app=queen-agent -n neural-hive-phase2

clean:
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -delete
	find . -type d -name '*.egg-info' -exec rm -rf {} +
	find . -type d -name '.pytest_cache' -exec rm -rf {} +
	find . -type d -name '.mypy_cache' -exec rm -rf {} +
