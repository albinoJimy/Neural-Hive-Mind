#!/usr/bin/env python3
"""
Script de Teste de Inferência de Modelos dos Especialistas

Este script testa a capacidade de inferência real dos modelos dos especialistas,
enviando planos cognitivos realísticos via gRPC e validando as respostas.

Funcionalidades:
- Gera planos cognitivos variados (simplicidade, risco, domínios diferentes)
- Conecta a cada especialista via gRPC usando SpecialistService
- Chama EvaluatePlan RPC e valida estrutura da resposta
- Valida campos críticos: confidence_score, risk_score, recommendation, reasoning
- Testa casos extremos: planos vazios, malformados, timeouts
- Gera relatório JSON com pass/fail, tempos de resposta e erros

Uso:
  ./test-specialist-inference.py                              # Testa todos os especialistas
  ./test-specialist-inference.py --specialist technical       # Testa apenas um especialista
  ./test-specialist-inference.py --namespace specialist-ns    # Namespace customizado
  ./test-specialist-inference.py --verbose                    # Output detalhado
  ./test-specialist-inference.py --output-json report.json    # Salva relatório JSON
"""

import sys
import os
import json
import time
import uuid
import argparse
import traceback
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

import grpc
import structlog
from google.protobuf.timestamp_pb2 import Timestamp

# Adicionar path das libraries
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../libraries/python'))

from neural_hive_specialists.proto_gen import specialist_pb2, specialist_pb2_grpc

# Configurar logging estruturado
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer()
    ]
)
logger = structlog.get_logger()


class CognitivePlanGenerator:
    """Gerador de planos cognitivos para testes de inferência"""

    def __init__(self):
        self.counter = 0

    def _next_id(self) -> str:
        """Gera ID único para teste"""
        self.counter += 1
        return f"inference-test-{datetime.now().strftime('%Y%m%d%H%M%S')}-{self.counter:04d}"

    def generate_simple_plan(self) -> Dict[str, Any]:
        """Gera plano cognitivo simples (baixo risco, aprovação esperada)"""
        plan_id = self._next_id()
        return {
            "version": "1.0.0",
            "plan_id": plan_id,
            "intent_id": f"intent-{plan_id}",
            "original_domain": "system",
            "original_priority": "normal",
            "tasks": [
                {
                    "task_id": f"{plan_id}-task-1",
                    "name": "Simple System Task",
                    "task_type": "system_query",
                    "description": "Consultar status do sistema - operação de baixo risco",
                    "estimated_duration_ms": 500,
                    "dependencies": []
                }
            ],
            "execution_order": [f"{plan_id}-task-1"],
            "risk_score": 0.15,
            "risk_band": "low",
            "risk_factors": {"complexity": 0.1, "data_sensitivity": 0.2},
            "explainability_token": f"exp-{plan_id}",
            "reasoning_summary": "Plano simples de consulta ao sistema",
            "status": "pending_evaluation",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metadata": {"test_type": "simple_inference"}
        }

    def generate_high_risk_plan(self) -> Dict[str, Any]:
        """Gera plano cognitivo de alto risco (rejeição/review esperado)"""
        plan_id = self._next_id()
        return {
            "version": "1.0.0",
            "plan_id": plan_id,
            "intent_id": f"intent-{plan_id}",
            "original_domain": "data_management",
            "original_priority": "high",
            "tasks": [
                {
                    "task_id": f"{plan_id}-task-1",
                    "name": "Database Migration Task",
                    "task_type": "data_migration",
                    "description": "Migrar dados sensíveis de produção - alto risco de perda de dados",
                    "estimated_duration_ms": 3600000,
                    "dependencies": [],
                    "required_capabilities": ["database_admin", "data_migration"],
                    "parameters": {"target_env": "production", "data_volume": "10TB"}
                },
                {
                    "task_id": f"{plan_id}-task-2",
                    "name": "Schema Update",
                    "task_type": "schema_change",
                    "description": "Atualizar schema de banco de dados em produção",
                    "estimated_duration_ms": 1800000,
                    "dependencies": [f"{plan_id}-task-1"],
                    "required_capabilities": ["database_admin"]
                }
            ],
            "execution_order": [f"{plan_id}-task-1", f"{plan_id}-task-2"],
            "risk_score": 0.85,
            "risk_band": "high",
            "risk_factors": {
                "complexity": 0.9,
                "data_sensitivity": 0.95,
                "operational_impact": 0.8,
                "rollback_difficulty": 0.85
            },
            "explainability_token": f"exp-{plan_id}",
            "reasoning_summary": "Plano de migração de dados com alto risco operacional",
            "status": "pending_evaluation",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metadata": {"test_type": "high_risk_inference", "environment": "production"}
        }

    def generate_complex_plan(self) -> Dict[str, Any]:
        """Gera plano cognitivo complexo com múltiplas tarefas e dependências"""
        plan_id = self._next_id()
        tasks = []

        # Criar 5 tarefas com dependências em cadeia
        for i in range(1, 6):
            task = {
                "task_id": f"{plan_id}-task-{i}",
                "name": f"Complex Task {i}",
                "task_type": "business_process",
                "description": f"Tarefa de negócio complexa {i} com múltiplas integrações",
                "estimated_duration_ms": 5000 * i,
                "dependencies": [f"{plan_id}-task-{j}" for j in range(1, i)] if i > 1 else [],
                "required_capabilities": [f"capability-{j}" for j in range(1, min(i+1, 4))],
                "parameters": {"step": str(i), "criticality": "medium"}
            }
            tasks.append(task)

        return {
            "version": "1.0.0",
            "plan_id": plan_id,
            "intent_id": f"intent-{plan_id}",
            "original_domain": "business",
            "original_priority": "high",
            "tasks": tasks,
            "execution_order": [f"{plan_id}-task-{i}" for i in range(1, 6)],
            "risk_score": 0.55,
            "risk_band": "medium",
            "risk_factors": {
                "complexity": 0.7,
                "data_sensitivity": 0.5,
                "dependency_count": 0.6
            },
            "explainability_token": f"exp-{plan_id}",
            "reasoning_summary": "Plano de processo de negócio com múltiplas etapas e dependências",
            "status": "pending_evaluation",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metadata": {"test_type": "complex_inference", "task_count": "5"}
        }

    def generate_malformed_plan(self) -> Dict[str, Any]:
        """Gera plano cognitivo malformado para teste de tratamento de erros"""
        plan_id = self._next_id()
        return {
            "version": "1.0.0",
            "plan_id": plan_id,
            # Faltando campos obrigatórios: intent_id, tasks, etc
            "metadata": {"test_type": "malformed_inference"}
        }


class SpecialistInferenceTester:
    """Testa inferência de modelos dos especialistas via gRPC"""

    SPECIALISTS = ["technical", "business", "behavior", "evolution", "architecture"]
    GRPC_PORT = 50051
    DEFAULT_TIMEOUT = 30

    def __init__(
        self,
        namespace: str = "semantic-translation",
        verbose: bool = False
    ):
        self.namespace = namespace
        self.verbose = verbose
        self.plan_generator = CognitivePlanGenerator()
        self.results: List[Dict[str, Any]] = []

    def _get_specialist_address(self, specialist_type: str) -> str:
        """Retorna endereço do especialista no cluster"""
        return f"specialist-{specialist_type}.{self.namespace}.svc.cluster.local:{self.GRPC_PORT}"

    def _create_grpc_request(
        self,
        cognitive_plan: Dict[str, Any]
    ) -> specialist_pb2.EvaluatePlanRequest:
        """Cria EvaluatePlanRequest protobuf a partir do plano cognitivo"""
        plan_bytes = json.dumps(cognitive_plan, default=str).encode('utf-8')

        return specialist_pb2.EvaluatePlanRequest(
            plan_id=cognitive_plan.get('plan_id', str(uuid.uuid4())),
            intent_id=cognitive_plan.get('intent_id', str(uuid.uuid4())),
            correlation_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            cognitive_plan=plan_bytes,
            plan_version=cognitive_plan.get('version', '1.0.0'),
            context={},
            timeout_ms=self.DEFAULT_TIMEOUT * 1000
        )

    def _validate_response(
        self,
        response: specialist_pb2.EvaluatePlanResponse,
        specialist_type: str
    ) -> Tuple[bool, List[str]]:
        """
        Valida estrutura da resposta de inferência

        Returns:
            Tuple[bool, List[str]]: (passou_validacao, lista_de_erros)
        """
        errors = []

        # Validar campos obrigatórios no nível raiz
        if not response.opinion_id:
            errors.append("Campo 'opinion_id' está vazio")

        if response.specialist_type != specialist_type:
            errors.append(
                f"Campo 'specialist_type' incorreto: esperado '{specialist_type}', "
                f"recebido '{response.specialist_type}'"
            )

        if not response.specialist_version:
            errors.append("Campo 'specialist_version' está vazio")

        if response.processing_time_ms <= 0:
            errors.append(f"Campo 'processing_time_ms' inválido: {response.processing_time_ms}")

        # Validar campos da opinion
        if not response.opinion:
            errors.append("Campo 'opinion' não existe na resposta")
            return (False, errors)

        opinion = response.opinion

        # Validar confidence_score
        if not (0.0 <= opinion.confidence_score <= 1.0):
            errors.append(
                f"Campo 'confidence_score' fora do range [0.0-1.0]: {opinion.confidence_score}"
            )

        # Validar risk_score
        if not (0.0 <= opinion.risk_score <= 1.0):
            errors.append(
                f"Campo 'risk_score' fora do range [0.0-1.0]: {opinion.risk_score}"
            )

        # Validar recommendation
        valid_recommendations = ['approve', 'reject', 'review_required', 'conditional']
        if opinion.recommendation not in valid_recommendations:
            errors.append(
                f"Campo 'recommendation' inválido: '{opinion.recommendation}'. "
                f"Valores aceitos: {valid_recommendations}"
            )

        # Validar reasoning_summary
        if not opinion.reasoning_summary or len(opinion.reasoning_summary.strip()) == 0:
            errors.append("Campo 'reasoning_summary' está vazio")

        # Validar evaluated_at timestamp
        if not response.evaluated_at:
            errors.append("Campo 'evaluated_at' não existe")
        else:
            # Verificar se timestamp é válido
            try:
                timestamp_seconds = response.evaluated_at.seconds
                if timestamp_seconds <= 0:
                    errors.append(f"Campo 'evaluated_at.seconds' inválido: {timestamp_seconds}")
            except Exception as e:
                errors.append(f"Erro ao acessar 'evaluated_at': {str(e)}")

        return (len(errors) == 0, errors)

    def test_specialist_inference(
        self,
        specialist_type: str,
        test_scenarios: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Testa inferência de um especialista com múltiplos cenários

        Args:
            specialist_type: Tipo do especialista (technical, business, etc)
            test_scenarios: Lista de cenários a testar (None = todos)

        Returns:
            Dicionário com resultados dos testes
        """
        if test_scenarios is None:
            test_scenarios = ["simple", "high_risk", "complex", "malformed"]

        address = self._get_specialist_address(specialist_type)
        logger.info(
            "Testando inferência do especialista",
            specialist=specialist_type,
            address=address,
            scenarios=test_scenarios
        )

        results = {
            "specialist_type": specialist_type,
            "address": address,
            "scenarios": [],
            "summary": {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "errors": 0
            }
        }

        try:
            # Conectar via gRPC
            channel = grpc.insecure_channel(
                address,
                options=[
                    ('grpc.max_send_message_length', 10 * 1024 * 1024),
                    ('grpc.max_receive_message_length', 10 * 1024 * 1024),
                ]
            )
            stub = specialist_pb2_grpc.SpecialistServiceStub(channel)

            # Testar cada cenário
            for scenario in test_scenarios:
                results["summary"]["total"] += 1
                scenario_result = self._test_scenario(
                    stub,
                    specialist_type,
                    scenario
                )
                results["scenarios"].append(scenario_result)

                if scenario_result["status"] == "passed":
                    results["summary"]["passed"] += 1
                elif scenario_result["status"] == "failed":
                    results["summary"]["failed"] += 1
                else:
                    results["summary"]["errors"] += 1

            channel.close()

        except Exception as e:
            logger.error(
                "Erro ao testar especialista",
                specialist=specialist_type,
                error=str(e),
                traceback=traceback.format_exc()
            )
            results["error"] = str(e)
            results["summary"]["errors"] = len(test_scenarios)

        return results

    def _test_scenario(
        self,
        stub: specialist_pb2_grpc.SpecialistServiceStub,
        specialist_type: str,
        scenario: str
    ) -> Dict[str, Any]:
        """Testa um cenário específico de inferência"""

        # Gerar plano cognitivo baseado no cenário
        if scenario == "simple":
            cognitive_plan = self.plan_generator.generate_simple_plan()
        elif scenario == "high_risk":
            cognitive_plan = self.plan_generator.generate_high_risk_plan()
        elif scenario == "complex":
            cognitive_plan = self.plan_generator.generate_complex_plan()
        elif scenario == "malformed":
            cognitive_plan = self.plan_generator.generate_malformed_plan()
        else:
            raise ValueError(f"Cenário desconhecido: {scenario}")

        result = {
            "scenario": scenario,
            "plan_id": cognitive_plan.get("plan_id"),
            "status": "unknown",
            "errors": [],
            "response_time_ms": 0,
            "opinion": {}
        }

        try:
            # Criar request gRPC
            request = self._create_grpc_request(cognitive_plan)

            # Executar chamada gRPC e medir tempo
            start_time = time.time()
            response = stub.EvaluatePlan(request, timeout=self.DEFAULT_TIMEOUT)
            response_time = (time.time() - start_time) * 1000

            result["response_time_ms"] = round(response_time, 2)

            # Validar resposta
            passed, errors = self._validate_response(response, specialist_type)
            result["errors"] = errors

            if passed:
                result["status"] = "passed"
                result["opinion"] = {
                    "opinion_id": response.opinion_id,
                    "confidence_score": response.opinion.confidence_score,
                    "risk_score": response.opinion.risk_score,
                    "recommendation": response.opinion.recommendation,
                    "reasoning_summary": response.opinion.reasoning_summary[:100] + "..."
                    if len(response.opinion.reasoning_summary) > 100
                    else response.opinion.reasoning_summary
                }

                if self.verbose:
                    logger.info(
                        "Cenário passou na validação",
                        specialist=specialist_type,
                        scenario=scenario,
                        response_time_ms=result["response_time_ms"],
                        confidence=response.opinion.confidence_score,
                        risk=response.opinion.risk_score,
                        recommendation=response.opinion.recommendation
                    )
            else:
                result["status"] = "failed"
                logger.warning(
                    "Cenário falhou na validação",
                    specialist=specialist_type,
                    scenario=scenario,
                    errors=errors
                )

        except grpc.RpcError as e:
            result["status"] = "error"
            result["errors"] = [f"gRPC Error: {e.code()} - {e.details()}"]
            logger.error(
                "Erro gRPC ao testar cenário",
                specialist=specialist_type,
                scenario=scenario,
                code=e.code(),
                details=e.details()
            )

        except Exception as e:
            result["status"] = "error"
            result["errors"] = [f"Exception: {str(e)}"]
            logger.error(
                "Erro ao testar cenário",
                specialist=specialist_type,
                scenario=scenario,
                error=str(e),
                traceback=traceback.format_exc()
            )

        return result

    def run_all_tests(
        self,
        specialists: Optional[List[str]] = None,
        scenarios: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Executa testes de inferência para todos os especialistas

        Args:
            specialists: Lista de especialistas a testar (None = todos)
            scenarios: Lista de cenários a testar (None = padrão)

        Returns:
            Dicionário com resultados completos dos testes
        """
        if specialists is None:
            specialists = self.SPECIALISTS

        report = {
            "test_run_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "namespace": self.namespace,
            "specialists_tested": specialists,
            "results": [],
            "overall_summary": {
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "errors": 0,
                "success_rate": 0.0
            }
        }

        for specialist_type in specialists:
            specialist_result = self.test_specialist_inference(
                specialist_type,
                scenarios
            )
            report["results"].append(specialist_result)

            # Agregar estatísticas
            report["overall_summary"]["total_tests"] += specialist_result["summary"]["total"]
            report["overall_summary"]["passed"] += specialist_result["summary"]["passed"]
            report["overall_summary"]["failed"] += specialist_result["summary"]["failed"]
            report["overall_summary"]["errors"] += specialist_result["summary"]["errors"]

        # Calcular taxa de sucesso
        total = report["overall_summary"]["total_tests"]
        if total > 0:
            passed = report["overall_summary"]["passed"]
            report["overall_summary"]["success_rate"] = round((passed / total) * 100, 2)

        return report


def main():
    """Função principal"""
    parser = argparse.ArgumentParser(
        description="Testa inferência de modelos dos especialistas Neural Hive"
    )
    parser.add_argument(
        "--specialist",
        type=str,
        help="Testar apenas um especialista específico"
    )
    parser.add_argument(
        "--namespace",
        type=str,
        default="semantic-translation",
        help="Namespace Kubernetes (padrão: semantic-translation)"
    )
    parser.add_argument(
        "--scenarios",
        type=str,
        nargs="+",
        choices=["simple", "high_risk", "complex", "malformed"],
        help="Cenários específicos a testar"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Output detalhado"
    )
    parser.add_argument(
        "--output-json",
        type=str,
        help="Salvar relatório JSON em arquivo"
    )

    args = parser.parse_args()

    # Configurar tester
    tester = SpecialistInferenceTester(
        namespace=args.namespace,
        verbose=args.verbose
    )

    # Determinar especialistas a testar
    specialists = [args.specialist] if args.specialist else None

    # Executar testes
    logger.info("Iniciando testes de inferência de especialistas")
    report = tester.run_all_tests(specialists, args.scenarios)

    # Exibir resumo
    print("\n" + "=" * 80)
    print("RELATÓRIO DE TESTES DE INFERÊNCIA DE ESPECIALISTAS")
    print("=" * 80)
    print(f"\nID da execução: {report['test_run_id']}")
    print(f"Timestamp: {report['timestamp']}")
    print(f"Namespace: {report['namespace']}")
    print(f"\nEspecialistas testados: {', '.join(report['specialists_tested'])}")
    print(f"\n{'Resumo Geral':^80}")
    print("-" * 80)
    print(f"Total de testes: {report['overall_summary']['total_tests']}")
    print(f"✅ Passou: {report['overall_summary']['passed']}")
    print(f"❌ Falhou: {report['overall_summary']['failed']}")
    print(f"⚠️  Erros: {report['overall_summary']['errors']}")
    print(f"Taxa de sucesso: {report['overall_summary']['success_rate']}%")
    print("=" * 80)

    # Exibir detalhes por especialista
    for result in report["results"]:
        specialist = result["specialist_type"]
        summary = result["summary"]
        print(f"\n{specialist.upper()}: {summary['passed']}/{summary['total']} passou")

        if args.verbose:
            for scenario in result["scenarios"]:
                status_icon = "✅" if scenario["status"] == "passed" else "❌"
                print(
                    f"  {status_icon} {scenario['scenario']:15s} "
                    f"{scenario['response_time_ms']:6.2f}ms "
                    f"{'- ' + str(scenario['errors'][0]) if scenario['errors'] else ''}"
                )

    # Salvar relatório JSON se solicitado
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.write_text(json.dumps(report, indent=2, default=str))
        print(f"\n✅ Relatório JSON salvo em: {output_path}")

    # Exit code baseado em sucesso
    if report['overall_summary']['errors'] > 0 or report['overall_summary']['failed'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
