#!/usr/bin/env python3
"""
Game Day Runner CLI.

Ferramenta de linha de comando para execução de Game Days de Chaos Engineering.
Permite executar cenários automatizados e gerar relatórios consolidados.

Uso:
    python -m src.chaos.game_day_runner run --scenario pod_failure --target worker-agents
    python -m src.chaos.game_day_runner list-scenarios
    python -m src.chaos.game_day_runner validate-playbook --playbook restart-pod --target worker-agents
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from .chaos_engine import (
    ChaosEngine,
    GAME_DAY_SCENARIOS_TOTAL,
    GAME_DAY_SCENARIOS_FAILED,
    GAME_DAY_DURATION,
    GAME_DAY_INFO,
)
from .chaos_models import (
    ChaosExperimentRequest,
    ChaosExperimentStatus,
    ExperimentReport,
    FaultInjection,
    FaultParameters,
    FaultType,
    RollbackStrategy,
    ScenarioConfig,
    TargetSelector,
    ValidationCriteria,
)
from .scenarios.scenario_library import ScenarioLibrary

logger = structlog.get_logger(__name__)


class GameDayRunner:
    """
    Executor de Game Days para Chaos Engineering.

    Permite executar cenários de chaos de forma automatizada,
    seja individualmente ou em sequência como parte de um Game Day.
    """

    def __init__(
        self,
        environment: str = "staging",
        k8s_in_cluster: bool = True,
        max_concurrent: int = 1,
        default_timeout: int = 600,
        require_opa: bool = True,
        blast_radius_limit: int = 5,
    ):
        """
        Inicializa o Game Day Runner.

        Args:
            environment: Ambiente de execução (staging, development, etc.)
            k8s_in_cluster: Se está executando dentro do cluster K8s
            max_concurrent: Máximo de experimentos concorrentes
            default_timeout: Timeout padrão em segundos
            require_opa: Se requer aprovação OPA
            blast_radius_limit: Limite de blast radius
        """
        self.environment = environment
        self.k8s_in_cluster = k8s_in_cluster
        self.max_concurrent = max_concurrent
        self.default_timeout = default_timeout
        self.require_opa = require_opa
        self.blast_radius_limit = blast_radius_limit

        self.chaos_engine: Optional[ChaosEngine] = None
        self.scenario_library = ScenarioLibrary()
        self.reports: List[ExperimentReport] = []

    async def initialize(self) -> None:
        """Inicializa o ChaosEngine e dependências."""
        logger.info("game_day_runner.initializing")

        self.chaos_engine = ChaosEngine(
            k8s_in_cluster=self.k8s_in_cluster,
            playbook_executor=None,
            service_registry_client=None,
            opa_client=None,
            max_concurrent_experiments=self.max_concurrent,
            default_timeout_seconds=self.default_timeout,
            require_opa_approval=self.require_opa,
            blast_radius_limit=self.blast_radius_limit,
        )
        await self.chaos_engine.initialize()

        logger.info("game_day_runner.initialized")

    async def close(self) -> None:
        """Fecha conexões e recursos."""
        if self.chaos_engine:
            await self.chaos_engine.close()
        logger.info("game_day_runner.closed")

    def list_scenarios(self) -> List[Dict[str, Any]]:
        """Lista cenários disponíveis."""
        scenarios = []
        for name in self.scenario_library.list_scenarios():
            info = self.scenario_library.get_scenario_info(name)
            if info:
                scenarios.append({
                    "name": name,
                    **info
                })
        return scenarios

    async def run_scenario(
        self,
        scenario_name: str,
        target_service: str,
        target_namespace: str = "default",
        playbook_to_validate: Optional[str] = None,
        custom_parameters: Optional[Dict[str, Any]] = None,
        executed_by: Optional[str] = None,
    ) -> ExperimentReport:
        """
        Executa um cenário de chaos.

        Args:
            scenario_name: Nome do cenário a executar
            target_service: Serviço alvo
            target_namespace: Namespace do serviço
            playbook_to_validate: Playbook a validar (opcional)
            custom_parameters: Parâmetros customizados
            executed_by: Identificador do executor

        Returns:
            ExperimentReport com resultados
        """
        if not self.chaos_engine:
            raise RuntimeError("ChaosEngine não inicializado. Chame initialize() primeiro.")

        config = ScenarioConfig(
            name=f"GameDay - {scenario_name} - {target_service}",
            description=f"Execução de Game Day: {scenario_name}",
            target_service=target_service,
            target_namespace=target_namespace,
            playbook_to_validate=playbook_to_validate,
            custom_parameters=custom_parameters or {},
        )

        logger.info(
            "game_day_runner.running_scenario",
            scenario=scenario_name,
            target=target_service,
            namespace=target_namespace
        )

        report = await self.chaos_engine.execute_scenario(
            scenario_name,
            config,
            executed_by=executed_by or "game-day-runner"
        )

        self.reports.append(report)
        return report

    async def run_game_day(
        self,
        scenarios: List[Dict[str, Any]],
        executed_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executa um Game Day completo com múltiplos cenários.

        Args:
            scenarios: Lista de cenários a executar
            executed_by: Identificador do executor

        Returns:
            Relatório consolidado do Game Day
        """
        start_time = datetime.utcnow()
        results = []
        success_count = 0
        failure_count = 0

        logger.info(
            "game_day_runner.starting_game_day",
            scenario_count=len(scenarios),
            executed_by=executed_by
        )

        for scenario_config in scenarios:
            try:
                report = await self.run_scenario(
                    scenario_name=scenario_config["scenario_name"],
                    target_service=scenario_config["target_service"],
                    target_namespace=scenario_config.get("target_namespace", "default"),
                    playbook_to_validate=scenario_config.get("playbook_to_validate"),
                    custom_parameters=scenario_config.get("custom_parameters"),
                    executed_by=executed_by,
                )

                # Determinar sucesso baseado no status do experimento
                is_success = report.status == ChaosExperimentStatus.COMPLETED
                if is_success:
                    success_count += 1
                else:
                    failure_count += 1

                # Derivar tempo de recuperação das validações
                recovery_time = None
                if report.validations:
                    recovery_times = [
                        v.recovery_time_seconds
                        for v in report.validations
                        if v.recovery_time_seconds is not None
                    ]
                    if recovery_times:
                        recovery_time = max(recovery_times)

                # Derivar issues do failure_reason e observações das validações
                issues = []
                if report.failure_reason:
                    issues.append(report.failure_reason)
                for v in report.validations:
                    if not v.success:
                        issues.extend(v.observations)

                results.append({
                    "scenario": scenario_config["scenario_name"],
                    "target": scenario_config["target_service"],
                    "success": is_success,
                    "duration_seconds": report.duration_seconds,
                    "recovery_time_seconds": recovery_time,
                    "issues": issues,
                })

            except Exception as e:
                failure_count += 1
                results.append({
                    "scenario": scenario_config["scenario_name"],
                    "target": scenario_config["target_service"],
                    "success": False,
                    "error": str(e),
                })
                logger.error(
                    "game_day_runner.scenario_failed",
                    scenario=scenario_config["scenario_name"],
                    error=str(e)
                )

        end_time = datetime.utcnow()
        total_duration = (end_time - start_time).total_seconds()

        game_day_id = f"gd-{start_time.strftime('%Y%m%d-%H%M%S')}"
        success_rate = (success_count / len(scenarios) * 100) if scenarios else 0

        game_day_report = {
            "game_day_id": game_day_id,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": total_duration,
            "environment": self.environment,
            "executed_by": executed_by,
            "summary": {
                "total_scenarios": len(scenarios),
                "successful": success_count,
                "failed": failure_count,
                "success_rate": success_rate,
            },
            "results": results,
        }

        # Registrar métricas de Game Day
        GAME_DAY_SCENARIOS_TOTAL.labels(game_day_id=game_day_id).set(len(scenarios))
        GAME_DAY_SCENARIOS_FAILED.labels(game_day_id=game_day_id).set(failure_count)
        GAME_DAY_DURATION.labels(game_day_id=game_day_id).set(total_duration)
        GAME_DAY_INFO.labels(
            game_day_id=game_day_id,
            scenarios_total=str(len(scenarios)),
            scenarios_passed=str(success_count),
            scenarios_failed=str(failure_count),
            success_rate=f"{success_rate / 100:.2f}"
        ).set(1)

        logger.info(
            "game_day_runner.game_day_completed",
            game_day_id=game_day_id,
            success_count=success_count,
            failure_count=failure_count,
            duration=total_duration
        )

        return game_day_report

    async def validate_playbook(
        self,
        playbook_name: str,
        target_service: str,
        target_namespace: str = "default",
        scenario_name: str = "pod_failure",
    ) -> Dict[str, Any]:
        """
        Valida eficácia de um playbook usando chaos engineering.

        Args:
            playbook_name: Nome do playbook a validar
            target_service: Serviço alvo
            target_namespace: Namespace do serviço
            scenario_name: Cenário a usar para validação

        Returns:
            Resultado da validação
        """
        if not self.chaos_engine:
            raise RuntimeError("ChaosEngine não inicializado")

        result = await self.chaos_engine.validate_playbook(
            playbook_name=playbook_name,
            scenario_name=scenario_name,
            target_service=target_service,
            target_namespace=target_namespace,
        )

        return result.model_dump(mode="json")


def parse_args() -> argparse.Namespace:
    """Parse argumentos de linha de comando."""
    parser = argparse.ArgumentParser(
        description="Game Day Runner - Chaos Engineering para Neural Hive Mind"
    )

    subparsers = parser.add_subparsers(dest="command", help="Comandos disponíveis")

    # Comando: list-scenarios
    subparsers.add_parser(
        "list-scenarios",
        help="Lista cenários disponíveis"
    )

    # Comando: run
    run_parser = subparsers.add_parser(
        "run",
        help="Executa um cenário de chaos"
    )
    run_parser.add_argument(
        "--scenario", "-s",
        required=True,
        help="Nome do cenário a executar"
    )
    run_parser.add_argument(
        "--target", "-t",
        required=True,
        help="Serviço alvo"
    )
    run_parser.add_argument(
        "--namespace", "-n",
        default="default",
        help="Namespace do serviço (default: default)"
    )
    run_parser.add_argument(
        "--playbook", "-p",
        help="Playbook a validar"
    )
    run_parser.add_argument(
        "--environment", "-e",
        default="staging",
        help="Ambiente de execução (default: staging)"
    )
    run_parser.add_argument(
        "--executed-by",
        default="cli",
        help="Identificador do executor"
    )
    run_parser.add_argument(
        "--params",
        type=json.loads,
        default={},
        help="Parâmetros customizados em JSON"
    )

    # Comando: game-day
    gd_parser = subparsers.add_parser(
        "game-day",
        help="Executa um Game Day com múltiplos cenários"
    )
    gd_parser.add_argument(
        "--config", "-c",
        required=True,
        help="Arquivo JSON com configuração do Game Day"
    )
    gd_parser.add_argument(
        "--environment", "-e",
        default="staging",
        help="Ambiente de execução"
    )
    gd_parser.add_argument(
        "--executed-by",
        default="cli",
        help="Identificador do executor"
    )
    gd_parser.add_argument(
        "--output", "-o",
        help="Arquivo para salvar relatório"
    )

    # Comando: validate-playbook
    vp_parser = subparsers.add_parser(
        "validate-playbook",
        help="Valida eficácia de um playbook"
    )
    vp_parser.add_argument(
        "--playbook", "-p",
        required=True,
        help="Nome do playbook a validar"
    )
    vp_parser.add_argument(
        "--target", "-t",
        required=True,
        help="Serviço alvo"
    )
    vp_parser.add_argument(
        "--namespace", "-n",
        default="default",
        help="Namespace do serviço"
    )
    vp_parser.add_argument(
        "--scenario", "-s",
        default="pod_failure",
        help="Cenário a usar (default: pod_failure)"
    )

    # Opções globais
    parser.add_argument(
        "--in-cluster",
        action="store_true",
        default=False,
        help="Executar dentro do cluster K8s"
    )
    parser.add_argument(
        "--no-opa",
        action="store_true",
        default=False,
        help="Desabilitar validação OPA"
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=1,
        help="Máximo de experimentos concorrentes"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Timeout padrão em segundos"
    )
    parser.add_argument(
        "--blast-radius-limit",
        type=int,
        default=5,
        help="Limite de blast radius"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output em formato JSON"
    )

    return parser.parse_args()


async def main() -> int:
    """Função principal do CLI."""
    args = parse_args()

    if not args.command:
        print("Uso: game_day_runner.py <command> [options]")
        print("Use --help para ver comandos disponíveis")
        return 1

    runner = GameDayRunner(
        environment=getattr(args, "environment", "staging"),
        k8s_in_cluster=args.in_cluster,
        max_concurrent=args.max_concurrent,
        default_timeout=args.timeout,
        require_opa=not args.no_opa,
        blast_radius_limit=args.blast_radius_limit,
    )

    try:
        if args.command == "list-scenarios":
            scenarios = runner.list_scenarios()
            if args.json:
                print(json.dumps(scenarios, indent=2))
            else:
                print("\nCenários disponíveis:")
                print("-" * 60)
                for s in scenarios:
                    print(f"\n  {s['name']}: {s.get('description', '')}")
                    print(f"    Playbook: {s.get('playbook', 'N/A')}")
                    print(f"    Risco: {s.get('risk_level', 'N/A')}")
                    print(f"    Duração típica: {s.get('typical_duration', 'N/A')}s")
            return 0

        await runner.initialize()

        if args.command == "run":
            report = await runner.run_scenario(
                scenario_name=args.scenario,
                target_service=args.target,
                target_namespace=args.namespace,
                playbook_to_validate=args.playbook,
                custom_parameters=args.params,
                executed_by=args.executed_by,
            )

            if args.json:
                print(json.dumps(report.model_dump(mode="json"), indent=2))
            else:
                # Determinar sucesso baseado no status
                is_success = report.status == ChaosExperimentStatus.COMPLETED

                # Derivar tempo de recuperação das validações
                recovery_time = None
                if report.validations:
                    recovery_times = [
                        v.recovery_time_seconds
                        for v in report.validations
                        if v.recovery_time_seconds is not None
                    ]
                    if recovery_times:
                        recovery_time = max(recovery_times)

                # Derivar issues
                issues = []
                if report.failure_reason:
                    issues.append(report.failure_reason)
                for v in report.validations:
                    if not v.success:
                        issues.extend(v.observations)

                print(f"\n{'='*60}")
                print(f"Cenário: {args.scenario}")
                print(f"Target: {args.target}")
                print(f"Status: {'SUCESSO' if is_success else 'FALHA'}")
                print(f"Duração: {report.duration_seconds:.2f}s")
                if recovery_time:
                    print(f"Tempo de recuperação: {recovery_time:.2f}s")
                if issues:
                    print(f"Problemas: {', '.join(issues)}")
                print(f"{'='*60}\n")

            return 0 if report.status == ChaosExperimentStatus.COMPLETED else 1

        elif args.command == "game-day":
            with open(args.config) as f:
                config = json.load(f)

            report = await runner.run_game_day(
                scenarios=config.get("scenarios", []),
                executed_by=args.executed_by,
            )

            if args.output:
                with open(args.output, "w") as f:
                    json.dump(report, f, indent=2)
                print(f"Relatório salvo em: {args.output}")

            if args.json:
                print(json.dumps(report, indent=2))
            else:
                print(f"\n{'='*60}")
                print(f"Game Day ID: {report['game_day_id']}")
                print(f"Duração: {report['duration_seconds']:.2f}s")
                print(f"Cenários: {report['summary']['total_scenarios']}")
                print(f"Sucesso: {report['summary']['successful']}")
                print(f"Falhas: {report['summary']['failed']}")
                print(f"Taxa de sucesso: {report['summary']['success_rate']:.1f}%")
                print(f"{'='*60}\n")

            return 0 if report["summary"]["failed"] == 0 else 1

        elif args.command == "validate-playbook":
            result = await runner.validate_playbook(
                playbook_name=args.playbook,
                target_service=args.target,
                target_namespace=args.namespace,
                scenario_name=args.scenario,
            )

            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(f"\n{'='*60}")
                print(f"Playbook: {args.playbook}")
                print(f"Cenário: {args.scenario}")
                print(f"Target: {args.target}")
                print(f"Validação: {'PASSOU' if result.get('passed') else 'FALHOU'}")
                if result.get("recovery_time_seconds"):
                    print(f"Tempo de recuperação: {result['recovery_time_seconds']:.2f}s")
                if result.get("findings"):
                    print("Descobertas:")
                    for finding in result["findings"]:
                        print(f"  - {finding}")
                print(f"{'='*60}\n")

            return 0 if result.get("passed") else 1

    except Exception as e:
        logger.error("game_day_runner.error", error=str(e))
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Erro: {e}")
        return 1

    finally:
        await runner.close()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
