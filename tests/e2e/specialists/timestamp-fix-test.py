#!/usr/bin/env python3
"""
Teste E2E v1.0.8 - Validação da Correção de Timestamp
Verifica que timestamps protobuf são criados e deserializados corretamente

Uso:
    python test-timestamp-fix-e2e.py

Variáveis de ambiente:
    KAFKA_BOOTSTRAP_SERVERS: Endereço do Kafka (padrão: localhost:9092)
    TOPIC_PLANS_READY: Tópico de planos prontos (padrão: plans.ready)
    TOPIC_PLANS_CONSENSUS: Tópico de consenso (padrão: plans.consensus)
"""

import asyncio
import json
import uuid
import sys
import os
import traceback
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
import structlog

# Configurar logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()

# Configurações (podem ser sobrescritas via variáveis de ambiente)
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
TOPIC_PLANS_READY = os.getenv('TOPIC_PLANS_READY', 'plans.ready')
TOPIC_PLANS_CONSENSUS = os.getenv('TOPIC_PLANS_CONSENSUS', 'plans.consensus')


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


class TestTimestampFix:
    """Teste E2E para validar correção de timestamp v1.0.8"""

    def __init__(self):
        self.producer: Optional[AIOKafkaProducer] = None
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.test_plan_id = f"test-timestamp-fix-{uuid.uuid4()}"
        self.results = {
            "plan_sent": False,
            "consensus_received": False,
            "specialists_count": 0,
            "timestamps_valid": 0,
            "errors": []
        }

    async def setup(self):
        """Inicializar conexões Kafka"""
        print(f"\n{Colors.BLUE}{Colors.BOLD}Configurando teste E2E v1.0.8{Colors.RESET}")
        print(f"{Colors.CYAN}Kafka Bootstrap: {KAFKA_BOOTSTRAP_SERVERS}{Colors.RESET}")
        print(f"{Colors.CYAN}Tópico Plans Ready: {TOPIC_PLANS_READY}{Colors.RESET}")
        print(f"{Colors.CYAN}Tópico Consensus: {TOPIC_PLANS_CONSENSUS}{Colors.RESET}")

        # Configurar producer
        self.producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        await self.producer.start()
        logger.info("Producer Kafka iniciado")
        print(f"{Colors.GREEN}✓ Producer Kafka conectado{Colors.RESET}")

        # Configurar consumer
        self.consumer = AIOKafkaConsumer(
            TOPIC_PLANS_CONSENSUS,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='latest',
            group_id=f'test-timestamp-fix-{uuid.uuid4()}'
        )
        await self.consumer.start()
        logger.info("Consumer Kafka iniciado")
        print(f"{Colors.GREEN}✓ Consumer Kafka conectado{Colors.RESET}")

    async def cleanup(self):
        """Fechar conexões"""
        if self.producer:
            await self.producer.stop()
        if self.consumer:
            await self.consumer.stop()
        logger.info("Conexões Kafka fechadas")

    def create_test_plan(self) -> Dict[str, Any]:
        """Criar plano cognitivo de teste"""
        intent_id = f"test-intent-{uuid.uuid4()}"
        correlation_id = f"test-corr-{uuid.uuid4()}"

        plan = {
            "plan_id": self.test_plan_id,
            "intent_id": intent_id,
            "correlation_id": correlation_id,
            "version": "1.0.0",
            "description": "Teste E2E da correção de timestamp protobuf v1.0.8",
            "tasks": [
                {
                    "task_id": f"task-{uuid.uuid4()}",
                    "action_type": "validate_timestamp",
                    "parameters": {
                        "test_type": "timestamp_fix",
                        "version": "1.0.8"
                    },
                    "dependencies": []
                }
            ],
            "metadata": {
                "test_type": "timestamp_fix_e2e",
                "version": "1.0.8",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }

        logger.info(
            "Plano de teste criado",
            plan_id=self.test_plan_id,
            intent_id=intent_id
        )

        return plan

    async def send_plan(self, plan: Dict[str, Any]):
        """Enviar plano para tópico Kafka"""
        print(f"\n{Colors.BLUE}{Colors.BOLD}[1/4] Enviando plano de teste{Colors.RESET}")
        print(f"{Colors.CYAN}Plan ID: {self.test_plan_id}{Colors.RESET}")

        try:
            await self.producer.send_and_wait(TOPIC_PLANS_READY, plan)
            self.results["plan_sent"] = True
            logger.info("Plano enviado", plan_id=self.test_plan_id)
            print(f"{Colors.GREEN}✓ Plano enviado para {TOPIC_PLANS_READY}{Colors.RESET}")
        except Exception as e:
            error_msg = f"Erro ao enviar plano: {e}"
            self.results["errors"].append(error_msg)
            logger.error(error_msg, exc_info=True)
            print(f"{Colors.RED}✗ {error_msg}{Colors.RESET}")
            raise

    async def wait_for_consensus(self, timeout: int = 60) -> Optional[Dict[str, Any]]:
        """Aguardar decisão de consenso"""
        print(f"\n{Colors.BLUE}{Colors.BOLD}[2/4] Aguardando decisão de consenso (timeout: {timeout}s){Colors.RESET}")

        start_time = datetime.now()
        deadline = start_time + timedelta(seconds=timeout)

        try:
            async for msg in self.consumer:
                # Verificar timeout antes de processar mensagem
                if datetime.now() > deadline:
                    error_msg = f"Timeout aguardando consenso ({timeout}s)"
                    self.results["errors"].append(error_msg)
                    logger.error(error_msg, plan_id=self.test_plan_id)
                    print(f"{Colors.RED}✗ {error_msg}{Colors.RESET}")
                    return None

                decision = msg.value

                # Filtrar por plan_id
                if decision.get('plan_id') != self.test_plan_id:
                    continue

                logger.info(
                    "Decisão de consenso recebida",
                    plan_id=self.test_plan_id,
                    decision_id=decision.get('decision_id')
                )
                print(f"{Colors.GREEN}✓ Decisão de consenso recebida{Colors.RESET}")
                self.results["consensus_received"] = True
                return decision

            # Loop terminou sem encontrar decisão
            error_msg = f"Consumer terminou sem receber decisão"
            self.results["errors"].append(error_msg)
            logger.error(error_msg, plan_id=self.test_plan_id)
            print(f"{Colors.RED}✗ {error_msg}{Colors.RESET}")
            return None

        except Exception as e:
            error_msg = f"Erro ao consumir consenso: {e}"
            self.results["errors"].append(error_msg)
            logger.error(error_msg, exc_info=True)
            print(f"{Colors.RED}✗ {error_msg}{Colors.RESET}")
            return None

    def validate_consensus_decision(self, decision: Dict[str, Any]) -> bool:
        """Validar estrutura e timestamps da decisão"""
        print(f"\n{Colors.BLUE}{Colors.BOLD}[3/4] Validando decisão de consenso{Colors.RESET}")

        # Validar campos obrigatórios
        required_fields = ['decision_id', 'plan_id', 'opinions']
        for field in required_fields:
            if field not in decision:
                error_msg = f"Campo obrigatório ausente: {field}"
                self.results["errors"].append(error_msg)
                print(f"{Colors.RED}✗ {error_msg}{Colors.RESET}")
                return False

        print(f"{Colors.GREEN}✓ Campos obrigatórios presentes{Colors.RESET}")

        # Validar opinions
        opinions = decision.get('opinions', [])
        if not isinstance(opinions, list):
            error_msg = f"'opinions' deve ser uma lista, recebido: {type(opinions).__name__}"
            self.results["errors"].append(error_msg)
            print(f"{Colors.RED}✗ {error_msg}{Colors.RESET}")
            return False

        self.results["specialists_count"] = len(opinions)
        print(f"{Colors.CYAN}  Pareceres recebidos: {len(opinions)}/5{Colors.RESET}")

        if len(opinions) < 3:
            error_msg = f"Pareceres insuficientes: {len(opinions)}/5 (mínimo 3)"
            self.results["errors"].append(error_msg)
            print(f"{Colors.RED}✗ {error_msg}{Colors.RESET}")
            return False

        print(f"{Colors.GREEN}✓ Número suficiente de pareceres{Colors.RESET}")

        # Validar timestamps de cada opinion
        print(f"\n{Colors.CYAN}Validando timestamps:{Colors.RESET}")
        all_timestamps_valid = True

        for idx, opinion in enumerate(opinions):
            specialist_type = opinion.get('specialist_type', 'unknown')
            evaluated_at_str = opinion.get('evaluated_at')

            if not evaluated_at_str:
                error_msg = f"Specialist {specialist_type}: evaluated_at ausente"
                self.results["errors"].append(error_msg)
                print(f"{Colors.RED}  ✗ {error_msg}{Colors.RESET}")
                all_timestamps_valid = False
                continue

            try:
                # Tentar parsear timestamp ISO 8601
                evaluated_at = datetime.fromisoformat(evaluated_at_str.replace('Z', '+00:00'))

                # Validar que não é timestamp zero (1970-01-01)
                epoch_start = datetime(1970, 1, 1, tzinfo=timezone.utc)
                if evaluated_at <= epoch_start + timedelta(days=365):
                    error_msg = f"Specialist {specialist_type}: timestamp inválido (muito antigo): {evaluated_at_str}"
                    self.results["errors"].append(error_msg)
                    print(f"{Colors.RED}  ✗ {error_msg}{Colors.RESET}")
                    all_timestamps_valid = False
                    continue

                # Validar que é timestamp recente (últimos 5 minutos)
                now = datetime.now(timezone.utc)
                age = now - evaluated_at
                if age > timedelta(minutes=5):
                    error_msg = f"Specialist {specialist_type}: timestamp muito antigo: {evaluated_at_str} (idade: {age})"
                    self.results["errors"].append(error_msg)
                    print(f"{Colors.YELLOW}  ⚠ {error_msg}{Colors.RESET}")
                    # Não falha o teste, apenas warning

                if age < timedelta(seconds=0):
                    error_msg = f"Specialist {specialist_type}: timestamp no futuro: {evaluated_at_str}"
                    self.results["errors"].append(error_msg)
                    print(f"{Colors.RED}  ✗ {error_msg}{Colors.RESET}")
                    all_timestamps_valid = False
                    continue

                # Timestamp válido
                self.results["timestamps_valid"] += 1
                print(f"{Colors.GREEN}  ✓ {specialist_type}: {evaluated_at_str} (idade: {age.total_seconds():.1f}s){Colors.RESET}")

            except (ValueError, TypeError, AttributeError) as e:
                error_msg = f"Specialist {specialist_type}: erro ao parsear timestamp '{evaluated_at_str}': {e}"
                self.results["errors"].append(error_msg)
                print(f"{Colors.RED}  ✗ {error_msg}{Colors.RESET}")
                all_timestamps_valid = False

        return all_timestamps_valid

    async def run_test(self) -> int:
        """Executar teste completo"""
        print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}TESTE E2E - Correção Timestamp v1.0.8{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")

        exit_code = 1  # Assume falha

        try:
            # Setup
            await self.setup()

            # Criar e enviar plano
            plan = self.create_test_plan()
            await self.send_plan(plan)

            # Aguardar consenso
            decision = await self.wait_for_consensus(timeout=60)

            if decision is None:
                print(f"\n{Colors.RED}{Colors.BOLD}✗ TESTE FALHOU: Consenso não recebido{Colors.RESET}")
                return 1

            # Validar decisão
            if self.validate_consensus_decision(decision):
                print(f"\n{Colors.GREEN}{Colors.BOLD}✓ TESTE PASSOU: Timestamps válidos{Colors.RESET}")
                exit_code = 0
            else:
                print(f"\n{Colors.RED}{Colors.BOLD}✗ TESTE FALHOU: Validação de timestamps{Colors.RESET}")
                exit_code = 1

        except Exception as e:
            error_msg = f"Erro fatal no teste: {e}"
            self.results["errors"].append(error_msg)
            logger.error(error_msg, exc_info=True, traceback=traceback.format_exc())
            print(f"\n{Colors.RED}{Colors.BOLD}✗ ERRO FATAL: {e}{Colors.RESET}")
            exit_code = 1

        finally:
            await self.cleanup()

        # Exibir resumo
        self.print_summary()

        return exit_code

    def print_summary(self):
        """Exibir resumo do teste"""
        print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}RESUMO DO TESTE{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
        print(f"Plan ID: {Colors.YELLOW}{self.test_plan_id}{Colors.RESET}")
        print(f"Plan enviado: {self._status_icon(self.results['plan_sent'])}")
        print(f"Consenso recebido: {self._status_icon(self.results['consensus_received'])}")
        print(f"Specialists responderam: {Colors.CYAN}{self.results['specialists_count']}/5{Colors.RESET}")
        print(f"Timestamps válidos: {Colors.CYAN}{self.results['timestamps_valid']}/{self.results['specialists_count']}{Colors.RESET}")

        if self.results["errors"]:
            print(f"\n{Colors.RED}{Colors.BOLD}Erros ({len(self.results['errors'])}):{ Colors.RESET}")
            for i, error in enumerate(self.results["errors"], 1):
                print(f"{Colors.RED}  {i}. {error}{Colors.RESET}")
        else:
            print(f"\n{Colors.GREEN}{Colors.BOLD}Nenhum erro detectado{Colors.RESET}")

        print(f"{Colors.BOLD}{'='*60}{Colors.RESET}\n")

    def _status_icon(self, status: bool) -> str:
        """Retornar ícone de status"""
        if status:
            return f"{Colors.GREEN}✓{Colors.RESET}"
        else:
            return f"{Colors.RED}✗{Colors.RESET}"


async def main():
    """Entry point"""
    test = TestTimestampFix()

    try:
        exit_code = await test.run_test()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.warning("Teste interrompido pelo usuário")
        print(f"\n{Colors.YELLOW}⚠ Teste interrompido{Colors.RESET}")
        sys.exit(130)
    except Exception as e:
        logger.error("Erro fatal", error=str(e), traceback=traceback.format_exc())
        print(f"\n{Colors.RED}{Colors.BOLD}✗ ERRO FATAL: {e}{Colors.RESET}")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
