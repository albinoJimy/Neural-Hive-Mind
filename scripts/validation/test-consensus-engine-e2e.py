#!/usr/bin/env python3
"""
Script de Teste End-to-End do Consensus Engine

Testa o fluxo completo de consenso:
1. Publica plano cognitivo no tópico Kafka cognitive-plans
2. Monitora tópico de decisions para resultado do consenso
3. Valida que todos os 5 especialistas foram invocados
4. Verifica decisão de consenso no MongoDB
5. Valida atualização de pheromone trails no Redis

Uso:
  ./test-consensus-engine-e2e.py
  ./test-consensus-engine-e2e.py --kafka-bootstrap kafka:9092
  ./test-consensus-engine-e2e.py --scenarios simple,high_risk
  ./test-consensus-engine-e2e.py --timeout 10
"""

import sys
import os
import json
import time
import uuid
import argparse
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer()
    ]
)
logger = structlog.get_logger()

try:
    from kafka import KafkaProducer, KafkaConsumer
    from kafka.errors import KafkaError
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    logger.warning("kafka-python não disponível - instale com: pip install kafka-python")

try:
    import pymongo
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    logger.warning("pymongo não disponível - instale com: pip install pymongo")

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("redis não disponível - instale com: pip install redis")


class ConsensusEngineE2ETester:
    """Testa end-to-end o Consensus Engine"""

    def __init__(
        self,
        kafka_bootstrap: str = "kafka.kafka:9092",
        mongodb_uri: str = "mongodb://mongodb.mongodb-cluster:27017",
        redis_host: str = "redis-cluster.redis:6379",
        timeout: int = 10
    ):
        self.kafka_bootstrap = kafka_bootstrap
        self.mongodb_uri = mongodb_uri
        self.redis_host = redis_host
        self.timeout = timeout
        logger.info(
            "Iniciando E2E tester do Consensus Engine",
            kafka=kafka_bootstrap,
            mongodb=mongodb_uri,
            timeout=timeout
        )

    def generate_test_plan(self, scenario: str) -> Dict[str, Any]:
        """Gera plano cognitivo para teste"""
        plan_id = f"e2e-test-{scenario}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        if scenario == "simple":
            return {
                "version": "1.0.0",
                "plan_id": plan_id,
                "intent_id": f"intent-{plan_id}",
                "original_domain": "system",
                "original_priority": "normal",
                "tasks": [{
                    "task_id": f"{plan_id}-task-1",
                    "name": "Simple Task",
                    "task_type": "system_query",
                    "description": "Tarefa simples para teste E2E",
                    "estimated_duration_ms": 100,
                    "dependencies": []
                }],
                "execution_order": [f"{plan_id}-task-1"],
                "risk_score": 0.2,
                "risk_band": "low",
                "risk_factors": {},
                "explainability_token": f"exp-{plan_id}",
                "reasoning_summary": "Teste E2E simples",
                "status": "pending_evaluation",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "metadata": {"test": "e2e", "scenario": scenario}
            }
        elif scenario == "high_risk":
            return {
                "version": "1.0.0",
                "plan_id": plan_id,
                "intent_id": f"intent-{plan_id}",
                "original_domain": "critical",
                "original_priority": "high",
                "tasks": [{
                    "task_id": f"{plan_id}-task-1",
                    "name": "High Risk Task",
                    "task_type": "critical_operation",
                    "description": "Operação crítica de alto risco",
                    "estimated_duration_ms": 5000,
                    "dependencies": []
                }],
                "execution_order": [f"{plan_id}-task-1"],
                "risk_score": 0.9,
                "risk_band": "high",
                "risk_factors": {"criticality": 0.95},
                "explainability_token": f"exp-{plan_id}",
                "reasoning_summary": "Teste E2E alto risco",
                "status": "pending_evaluation",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "metadata": {"test": "e2e", "scenario": scenario}
            }
        else:
            raise ValueError(f"Cenário desconhecido: {scenario}")

    def test_consensus_flow(self, scenario: str) -> Dict[str, Any]:
        """
        Testa fluxo completo de consenso

        Returns:
            Dicionário com resultado do teste
        """
        result = {
            "scenario": scenario,
            "status": "unknown",
            "plan_id": None,
            "specialists_invoked": [],
            "consensus_decision": None,
            "processing_time_ms": 0,
            "errors": []
        }

        # Verificar dependências
        if not KAFKA_AVAILABLE:
            result["status"] = "skipped"
            result["errors"].append("kafka-python não disponível")
            return result

        try:
            # Gerar plano de teste
            plan = self.generate_test_plan(scenario)
            result["plan_id"] = plan["plan_id"]

            logger.info(
                "Publicando plano cognitivo no Kafka",
                plan_id=plan["plan_id"],
                scenario=scenario
            )

            start_time = time.time()

            # Publicar plano no Kafka
            producer = KafkaProducer(
                bootstrap_servers=self.kafka_bootstrap.split(','),
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None
            )

            producer.send('cognitive-plans', key=plan["plan_id"], value=plan)
            producer.flush()

            logger.info("Plano publicado no Kafka", plan_id=plan["plan_id"])

            # Monitorar tópico de decisões
            consumer = KafkaConsumer(
                'consensus-decisions',
                bootstrap_servers=self.kafka_bootstrap.split(','),
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                auto_offset_reset='latest',
                enable_auto_commit=True,
                consumer_timeout_ms=self.timeout * 1000
            )

            # Aguardar decisão de consenso (com timeout)
            logger.info(
                "Aguardando decisão de consenso",
                plan_id=plan["plan_id"],
                timeout=self.timeout
            )

            # Poll de decisões
            decision = None
            for message in consumer:
                if message.value.get('plan_id') == plan['plan_id']:
                    decision = message.value
                    break

            consumer.close()
            producer.close()

            processing_time = (time.time() - start_time) * 1000
            result["processing_time_ms"] = round(processing_time, 2)

            if decision is None:
                result["status"] = "failed"
                result["errors"].append("Timeout: decisão de consenso não recebida")
                logger.error("Timeout aguardando decisão", plan_id=plan["plan_id"])
                return result

            result["consensus_decision"] = decision

            # Validar decisão - verificar que todos os 5 especialistas foram invocados
            specialists_in_decision = decision.get("specialists", [])
            result["specialists_invoked"] = [s.get("specialist_type") for s in specialists_in_decision]

            expected_specialists = 5
            if len(specialists_in_decision) < expected_specialists:
                result["status"] = "failed"
                result["errors"].append(
                    f"Apenas {len(specialists_in_decision)} especialistas invocados, esperado {expected_specialists}"
                )
                logger.error(
                    "Número insuficiente de especialistas",
                    invoked=len(specialists_in_decision),
                    expected=expected_specialists
                )
            else:
                # Consultar MongoDB para verificar persistência
                mongo_ok = True
                redis_ok = True

                if MONGODB_AVAILABLE:
                    try:
                        mongo_client = pymongo.MongoClient(self.mongodb_uri, serverSelectionTimeoutMS=5000)
                        db = mongo_client["consensus_engine"]
                        decisions_collection = db["decisions"]

                        stored_decision = decisions_collection.find_one({"plan_id": plan["plan_id"]})
                        if stored_decision is None:
                            mongo_ok = False
                            result["errors"].append("Decisão não encontrada no MongoDB")
                        else:
                            logger.info("Decisão encontrada no MongoDB", plan_id=plan["plan_id"])

                        mongo_client.close()
                    except Exception as e:
                        mongo_ok = False
                        result["errors"].append(f"Erro ao verificar MongoDB: {str(e)}")
                        logger.error("Erro ao verificar MongoDB", error=str(e))

                # Verificar Redis para pheromone trails
                if REDIS_AVAILABLE:
                    try:
                        redis_host, redis_port = self.redis_host.split(':')
                        redis_client = redis.Redis(
                            host=redis_host,
                            port=int(redis_port),
                            decode_responses=True,
                            socket_connect_timeout=5
                        )

                        # Verificar se há pheromone trails atualizados
                        pheromone_key = f"pheromone:{plan['plan_id']}*"
                        keys = redis_client.keys(pheromone_key)

                        if not keys:
                            redis_ok = False
                            result["errors"].append("Pheromone trails não encontrados no Redis")
                        else:
                            logger.info("Pheromone trails encontrados no Redis", count=len(keys))

                        redis_client.close()
                    except Exception as e:
                        redis_ok = False
                        result["errors"].append(f"Erro ao verificar Redis: {str(e)}")
                        logger.error("Erro ao verificar Redis", error=str(e))

                # Definir status final
                if mongo_ok and redis_ok and len(result["errors"]) == 0:
                    result["status"] = "passed"
                    logger.info("Teste E2E passou", plan_id=plan["plan_id"])
                else:
                    result["status"] = "failed"
                    logger.error("Teste E2E falhou", plan_id=plan["plan_id"], errors=result["errors"])

        except KafkaError as e:
            result["status"] = "error"
            result["errors"].append(f"Erro Kafka: {str(e)}")
            logger.error("Erro Kafka no teste E2E", scenario=scenario, error=str(e))
        except Exception as e:
            result["status"] = "error"
            result["errors"].append(str(e))
            logger.error("Erro no teste E2E", scenario=scenario, error=str(e))

        return result

    def run_all_scenarios(self, scenarios: List[str]) -> Dict[str, Any]:
        """Executa teste para todos os cenários"""
        report = {
            "test_run_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scenarios": [],
            "summary": {
                "total": len(scenarios),
                "passed": 0,
                "failed": 0,
                "not_implemented": 0
            }
        }

        for scenario in scenarios:
            result = self.test_consensus_flow(scenario)
            report["scenarios"].append(result)

            if result["status"] == "passed":
                report["summary"]["passed"] += 1
            elif result["status"] == "not_implemented":
                report["summary"]["not_implemented"] += 1
            else:
                report["summary"]["failed"] += 1

        return report


def main():
    """Função principal"""
    parser = argparse.ArgumentParser(
        description="Teste E2E do Consensus Engine"
    )
    parser.add_argument(
        "--kafka-bootstrap",
        type=str,
        default="kafka.kafka:9092",
        help="Kafka bootstrap servers"
    )
    parser.add_argument(
        "--mongodb-uri",
        type=str,
        default="mongodb://mongodb.mongodb-cluster:27017",
        help="MongoDB URI"
    )
    parser.add_argument(
        "--redis-host",
        type=str,
        default="redis-cluster.redis:6379",
        help="Redis host"
    )
    parser.add_argument(
        "--scenarios",
        type=str,
        default="simple,high_risk",
        help="Cenários de teste separados por vírgula"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Timeout em segundos para aguardar decisão"
    )
    parser.add_argument(
        "--namespace",
        type=str,
        default="semantic-translation",
        help="Namespace Kubernetes (não usado diretamente neste script)"
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Caminho para salvar relatório em JSON"
    )

    args = parser.parse_args()

    scenarios = args.scenarios.split(',')

    tester = ConsensusEngineE2ETester(
        kafka_bootstrap=args.kafka_bootstrap,
        mongodb_uri=args.mongodb_uri,
        redis_host=args.redis_host,
        timeout=args.timeout
    )

    logger.info("Iniciando testes E2E do Consensus Engine")
    report = tester.run_all_scenarios(scenarios)

    # Salvar relatório JSON se solicitado
    if args.output_json:
        with open(args.output_json, 'w') as f:
            json.dump(report, f, indent=2)
        logger.info("Relatório JSON salvo", path=args.output_json)

    # Exibir relatório
    print("\n" + "=" * 80)
    print("RELATÓRIO DE TESTES E2E - CONSENSUS ENGINE")
    print("=" * 80)
    print(f"\nID: {report['test_run_id']}")
    print(f"Timestamp: {report['timestamp']}")
    print(f"\nResumo:")
    print(f"  Total: {report['summary']['total']}")
    print(f"  ✅ Passou: {report['summary']['passed']}")
    print(f"  ❌ Falhou: {report['summary']['failed']}")
    print(f"  ⚠️  Não implementado: {report['summary']['not_implemented']}")
    print("=" * 80)

    for scenario in report["scenarios"]:
        print(f"\nCenário: {scenario['scenario']}")
        print(f"  Status: {scenario['status']}")
        print(f"  Plan ID: {scenario['plan_id']}")
        if scenario["errors"]:
            print(f"  Erros: {', '.join(scenario['errors'])}")

    # Exit code
    if report["summary"]["failed"] > 0:
        sys.exit(1)
    elif report["summary"]["not_implemented"] > 0:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
