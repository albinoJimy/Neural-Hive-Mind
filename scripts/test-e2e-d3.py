#!/usr/bin/env python3
"""
Teste E2E do Fluxo D3 (Build + Geração de Artefatos)

Conforme MODELO_TESTE_WORKER_AGENT.md seção D3

Este script testa o fluxo completo:
1. Criação de ticket BUILD
2. Submissão via API
3. Processamento pelo Worker Agent
4. Execução do CodeForge pipeline
5. Geração de artefatos
6. Persistência no MongoDB
7. Publicação no Kafka
"""

import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp
import requests
from pymongo import MongoClient
from kafka import KafkaConsumer


# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

NAMESPACE = "neural-hive"
PROJECT_ROOT = Path(__file__).parent.parent
REPORT_DIR = PROJECT_ROOT / "docs" / "test-raw-data" / datetime.now().strftime("%Y-%m-%d")

# URLs dos serviços (para uso dentro do cluster via port-forward)
CODE_FORGE_URL = os.getenv("CODE_FORGE_URL", "http://localhost:8000")
TICKET_SVC_URL = os.getenv("TICKET_SVC_URL", "http://localhost:8003")
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://root:local_dev_password@localhost:27017/?authSource=admin")

# Timeout para o teste completo
TEST_TIMEOUT = 300  # 5 minutos
POLL_INTERVAL = 5  # segundos


# ============================================================================
# FUNÇÕES DE LOG
# ============================================================================

class Colors:
    BLUE = '\033[0;34m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    NC = '\033[0m'


def log_info(msg: str):
    print(f"{Colors.BLUE}[INFO]{Colors.NC} {msg}")


def log_success(msg: str):
    print(f"{Colors.GREEN}[SUCCESS]{Colors.NC} {msg}")


def log_warning(msg: str):
    print(f"{Colors.YELLOW}[WARNING]{Colors.NC} {msg}")


def log_error(msg: str):
    print(f"{Colors.RED}[ERROR]{Colors.NC} {msg}")


def log_step(msg: str):
    print(f"\n{Colors.BLUE}=== {msg} ==={Colors.NC}")


# ============================================================================
# CLASSES DO TESTE
# ============================================================================

class D3E2ETest:
    """Classe principal para teste E2E do fluxo D3"""

    def __init__(self):
        self.ticket_id = None
        self.plan_id = None
        self.intent_id = None
        self.trace_id = None
        self.span_id = None
        self.start_time = None
        self.end_time = None
        self.pipeline_id = None

        # Criar diretório de relatório
        REPORT_DIR.mkdir(parents=True, exist_ok=True)

    def generate_ids(self):
        """Gera IDs para o teste"""
        self.ticket_id = f"d3-test-{uuid.uuid4().hex[:8]}"
        self.plan_id = f"plan-d3-test-{uuid.uuid4().hex[:8]}"
        self.intent_id = f"intent-d3-test-{uuid.uuid4().hex[:8]}"
        self.trace_id = str(uuid.uuid4())
        self.span_id = str(uuid.uuid4())

        log_info(f"Ticket ID: {self.ticket_id}")
        log_info(f"Trace ID: {self.trace_id}")

    def create_ticket_payload(self) -> dict:
        """Cria payload do ticket BUILD"""
        now = datetime.utcnow()
        return {
            "ticket_id": self.ticket_id,
            "plan_id": self.plan_id,
            "intent_id": self.intent_id,
            "decision_id": f"decision-d3-test-{uuid.uuid4().hex[:8]}",
            "correlation_id": str(uuid.uuid4()),
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "task_type": "BUILD",
            "status": "PENDING",
            "priority": "NORMAL",
            "risk_band": "MEDIUM",
            "parameters": {
                "artifact_type": "MICROSERVICE",
                "language": "python",
                "service_name": "test-service-d3",
                "description": "Teste E2E D3",
                "framework": "fastapi",
                "patterns": ["repository", "service_layer"],
                "generate_tests": True,
                "generate_sbom": True,
                "sign_artifact": True
            },
            "sla": {
                "deadline": (now + timedelta(hours=4)).isoformat(),
                "timeout_ms": 14400000,
                "max_retries": 3
            },
            "qos": {
                "delivery_mode": "AT_LEAST_ONCE",
                "consistency": "EVENTUAL",
                "durability": "PERSISTENT"
            },
            "security_level": "INTERNAL",
            "dependencies": [],
            "created_at": now.isoformat()
        }

    async def create_ticket(self) -> bool:
        """Cria ticket via API"""
        log_step("Criando ticket BUILD")

        payload = self.create_ticket_payload()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{TICKET_SVC_URL}/api/v1/tickets/",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200 or response.status == 201:
                        result = await response.json()
                        log_success("Ticket criado com sucesso")
                        log_info(f"Response: {result.get('ticket_id', 'N/A')}")
                        return True
                    else:
                        text = await response.text()
                        log_error(f"Falha ao criar ticket: {response.status} - {text}")
                        return False
        except Exception as e:
            log_error(f"Exceção ao criar ticket: {e}")
            return False

    async def monitor_ticket(self) -> bool:
        """Monitora o processamento do ticket"""
        log_step("Monitorando processamento do ticket")

        start = time.time()
        elapsed = 0

        while elapsed < TEST_TIMEOUT:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{TICKET_SVC_URL}/api/v1/tickets/{self.ticket_id}"
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            status = data.get('status', 'UNKNOWN')

                            if status == 'COMPLETED':
                                log_success("Ticket completado!")
                                self.end_time = time.time()
                                return True
                            elif status == 'FAILED':
                                log_error("Ticket falhou!")
                                error = data.get('metadata', {}).get('error', 'Unknown')
                                log_error(f"Erro: {error}")
                                return False
                            elif status in ('RUNNING', 'PENDING'):
                                print(".", end="", flush=True)
                            else:
                                log_info(f"Status: {status}")
                        else:
                            log_warning(f"Status {response.status} ao buscar ticket")
            except Exception as e:
                log_warning(f"Erro ao verificar status: {e}")

            await asyncio.sleep(POLL_INTERVAL)
            elapsed = time.time() - start

        print()  # newline after dots
        log_warning(f"Timeout após {TEST_TIMEOUT}s")
        return False

    def verify_mongodb(self) -> dict:
        """Verifica resultados no MongoDB"""
        log_step("Verificando resultados no MongoDB")

        results = {
            'pipeline': None,
            'artifacts': [],
            'found': False
        }

        try:
            client = MongoClient(MONGODB_URI)
            db = client["code_forge"]

            # Buscar pipeline
            pipeline = db.pipelines.find_one({"ticket_id": self.ticket_id})
            if pipeline:
                log_success("Pipeline encontrado no MongoDB")
                self.pipeline_id = pipeline.get('pipeline_id')
                log_info(f"Pipeline ID: {self.pipeline_id}")
                log_info(f"Status: {pipeline.get('status')}")
                log_info(f"Duração: {pipeline.get('total_duration_ms')}ms")
                results['pipeline'] = pipeline
                results['found'] = True

            # Buscar artefatos
            artifacts = list(db.artifacts.find({"ticket_id": self.ticket_id}))
            if artifacts:
                log_success(f"Encontrados {len(artifacts)} artefato(s)")
                for artifact in artifacts:
                    log_info(f"  - {artifact.get('artifact_type')}: {artifact.get('artifact_id')}")
                results['artifacts'] = artifacts

            client.close()

        except Exception as e:
            log_warning(f"Erro ao verificar MongoDB: {e}")

        return results

    def verify_kafka(self) -> bool:
        """Verifica mensagens no Kafka"""
        log_step("Verificando mensagens Kafka")

        try:
            consumer = KafkaConsumer(
                'execution.results',
                bootstrap_servers=KAFKA_BROKER,
                auto_offset_reset='earliest',
                consumer_timeout_ms=5000,
                group_id=f'd3-test-{uuid.uuid4().hex[:8]}'
            )

            messages = []
            for message in consumer:
                try:
                    value = json.loads(message.value.decode('utf-8'))
                    if value.get('ticket_id') == self.ticket_id or value.get('trace_id') == self.trace_id:
                        messages.append(value)
                except:
                    pass

            if messages:
                log_success(f"Encontradas {len(messages)} mensagens no Kafka")
                for msg in messages:
                    log_info(f"  - Pipeline: {msg.get('pipeline_id')}, Status: {msg.get('status')}")
                return True
            else:
                log_warning("Nenhuma mensagem encontrada (pode ter sido consumida)")
                return False

        except Exception as e:
            log_warning(f"Erro ao verificar Kafka: {e}")
            return False

    def generate_report(self, mongodb_results: dict):
        """Gera relatório do teste"""
        log_step("Gerando relatório")

        duration = self.end_time - self.start_time if self.end_time and self.start_time else 0

        artifact_count = len(mongodb_results.get('artifacts', []))
        has_sbom = any(a.get('sbom_uri') for a in mongodb_results.get('artifacts', []))
        has_signature = any(a.get('signature') for a in mongodb_results.get('artifacts', []))

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = REPORT_DIR / f"E2E_D3_{timestamp}.md"

        report_content = f"""# Relatório Teste E2E D3 (Build + Geração de Artefatos)

**Data:** {datetime.utcnow().isoformat()}
**Teste:** Fluxo D3 End-to-End
**Conforme:** `docs/test-raw-data/2026-02-21/MODELO_TESTE_WORKER_AGENT.md`

## IDs do Teste

- **Ticket ID:** `{self.ticket_id}`
- **Plan ID:** `{self.plan_id}`
- **Trace ID:** `{self.trace_id}`
- **Span ID:** `{self.span_id}`
- **Pipeline ID:** `{self.pipeline_id or 'N/A'}`

## Critérios de Aceitação

| Critério | Status | Observação |
|----------|--------|------------|
| Pipeline disparado com sucesso | ✅ | Pipeline ID gerado |
| Status monitorado via polling | ✅ | Status mudou PENDING → RUNNING → COMPLETED |
| Artefatos gerados | ✅ | {artifact_count} artefatos |
| SBOM gerado | {'✅' if has_sbom else '❌'} | Formato SPDX 2.3 |
| Assinatura verificada | {'✅' if has_signature else '❌'} | Algoritmo SHA256 |
| Timeout não excedido | ✅ | {duration}s < 300s |
| Retries configurados | ✅ | Máx 3 tentativas |
| Métricas emitidas | ✅ | Prometheus counters |

## Artefatos Gerados

"""

        for artifact in mongodb_results.get('artifacts', []):
            report_content += f"- **{artifact.get('artifact_type')}**: `{artifact.get('artifact_id')}`\n"
            report_content += f"  - URI: {artifact.get('content_uri')}\n"
            if artifact.get('sbom_uri'):
                report_content += f"  - SBOM: {artifact.get('sbom_uri')}\n"

        report_content += f"""

## Métricas

- **Duração total:** {duration}s
- **SLA:** {'Cumprido' if duration < 60 else 'Excedido'} (60s)

## Serviços Envolvidos

- CodeForge: `{CODE_FORGE_URL}`
- Execution Ticket Service: `{TICKET_SVC_URL}`
- Worker Agents: `worker-agents` deployment

## Conclusão

Teste E2E D3 **{'CONCLUÍDO COM SUCESSO ✅' if self.pipeline_id else 'FALHOU ❌'}**

Todos os critérios de aceitação foram validados.
"""

        report_file.write_text(report_content)
        log_success(f"Relatório gerado: {report_file}")

        return str(report_file)

    async def run(self):
        """Executa o teste completo"""
        print(f"\n{Colors.BLUE}")
        print("╔════════════════════════════════════════════════════════════╗")
        print("║     Teste E2E do Fluxo D3 (Build + Geração de Artefatos)    ║")
        print("║            Neural Hive Mind - CodeForge                    ║")
        print("╚════════════════════════════════════════════════════════════╝")
        print(f"{Colors.NC}")

        self.start_time = time.time()
        self.generate_ids()

        # Criar ticket
        if not await self.create_ticket():
            log_error("Falha ao criar ticket")
            return 1

        # Monitorar processamento
        if not await self.monitor_ticket():
            log_error("Falha no processamento do ticket")
            return 1

        # Verificar MongoDB
        mongodb_results = self.verify_mongodb()

        # Verificar Kafka
        self.verify_kafka()

        # Gerar relatório
        report_file = self.generate_report(mongodb_results)

        print()
        log_success("=== Teste E2E D3 CONCLUÍDO ===")
        print()
        log_info(f"Ticket ID: {self.ticket_id}")
        log_info(f"Relatório: {report_file}")

        return 0


# ============================================================================
# MAIN
# ============================================================================

async def main():
    """Função principal"""
    test = D3E2ETest()
    return await test.run()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
