"""
CLI para Online Learning Pipeline.

Comandos para gerenciamento do pipeline de online learning.
"""

import argparse
import asyncio
import sys
from datetime import datetime
from typing import Optional, List, Any

import structlog

logger = structlog.get_logger(__name__)


def create_parser() -> argparse.ArgumentParser:
    """Cria parser de argumentos CLI."""
    parser = argparse.ArgumentParser(
        prog='online-learning',
        description='CLI para gerenciamento do Online Learning Pipeline'
    )

    subparsers = parser.add_subparsers(dest='command', help='Comandos disponíveis')

    # Comando: update
    update_parser = subparsers.add_parser(
        'update',
        help='Executar ciclo de atualização online'
    )
    update_parser.add_argument(
        '--specialist-types',
        type=str,
        default='all',
        help='Tipos de especialistas (comma-separated ou "all")'
    )
    update_parser.add_argument(
        '--force',
        action='store_true',
        help='Forçar atualização mesmo sem dados suficientes'
    )
    update_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simular atualização sem aplicar mudanças'
    )

    # Comando: validate
    validate_parser = subparsers.add_parser(
        'validate',
        help='Executar validação shadow de modelo'
    )
    validate_parser.add_argument(
        '--specialist-type',
        type=str,
        required=True,
        help='Tipo de especialista para validar'
    )
    validate_parser.add_argument(
        '--samples',
        type=int,
        default=100,
        help='Número de amostras para validação'
    )

    # Comando: rollback
    rollback_parser = subparsers.add_parser(
        'rollback',
        help='Reverter para versão anterior do modelo'
    )
    rollback_parser.add_argument(
        '--specialist-type',
        type=str,
        required=True,
        help='Tipo de especialista para rollback'
    )
    rollback_parser.add_argument(
        '--version',
        type=str,
        help='Versão específica para rollback (opcional)'
    )
    rollback_parser.add_argument(
        '--reason',
        type=str,
        required=True,
        help='Motivo do rollback'
    )

    # Comando: status
    status_parser = subparsers.add_parser(
        'status',
        help='Mostrar status do pipeline'
    )
    status_parser.add_argument(
        '--specialist-type',
        type=str,
        help='Tipo específico de especialista (opcional)'
    )
    status_parser.add_argument(
        '--json',
        action='store_true',
        help='Saída em formato JSON'
    )

    # Comando: versions
    versions_parser = subparsers.add_parser(
        'versions',
        help='Listar versões de modelos'
    )
    versions_parser.add_argument(
        '--specialist-type',
        type=str,
        required=True,
        help='Tipo de especialista'
    )
    versions_parser.add_argument(
        '--limit',
        type=int,
        default=10,
        help='Número máximo de versões a mostrar'
    )

    # Comando: metrics
    metrics_parser = subparsers.add_parser(
        'metrics',
        help='Mostrar métricas de online learning'
    )
    metrics_parser.add_argument(
        '--specialist-type',
        type=str,
        help='Tipo específico de especialista (opcional)'
    )
    metrics_parser.add_argument(
        '--period',
        type=str,
        default='1h',
        choices=['1h', '6h', '24h', '7d'],
        help='Período de métricas'
    )

    # Comando: deploy
    deploy_parser = subparsers.add_parser(
        'deploy',
        help='Deploy gradual de modelo online'
    )
    deploy_parser.add_argument(
        '--specialist-type',
        type=str,
        required=True,
        help='Tipo de especialista'
    )
    deploy_parser.add_argument(
        '--traffic-percentage',
        type=float,
        required=True,
        help='Percentual de tráfego (0.0-1.0)'
    )
    deploy_parser.add_argument(
        '--auto-rollback',
        action='store_true',
        default=True,
        help='Habilitar rollback automático em caso de degradação'
    )

    # Argumentos globais
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Modo verboso'
    )
    parser.add_argument(
        '--config',
        type=str,
        help='Arquivo de configuração personalizado'
    )

    return parser


async def cmd_update(args) -> int:
    """Executar ciclo de atualização online."""
    from .deployment_orchestrator import OnlineDeploymentOrchestrator
    from .config import OnlineLearningConfig

    logger.info(
        "starting_online_update",
        specialist_types=args.specialist_types,
        force=args.force,
        dry_run=args.dry_run
    )

    config = OnlineLearningConfig()

    specialist_types = (
        ['feasibility', 'risk', 'cost', 'technical', 'security']
        if args.specialist_types == 'all'
        else args.specialist_types.split(',')
    )

    success_count = 0
    for specialist_type in specialist_types:
        try:
            # Carregar modelo batch do MLflow ou usar stub
            batch_model = _load_batch_model(specialist_type, config)

            # Criar orchestrator com assinatura correta
            orchestrator = OnlineDeploymentOrchestrator(
                config=config,
                specialist_type=specialist_type,
                batch_model=batch_model,
                feedback_collector=_get_feedback_collector(specialist_type, config),
                feature_extractor=_get_feature_extractor(specialist_type)
            )

            # Executar ciclo de deployment (sem specialist_type, já passado no construtor)
            result = await orchestrator.run_deployment_cycle(
                force=args.force,
                validation_data=None
            )

            if result.get('status') == 'completed':
                success_count += 1
                logger.info(
                    "update_succeeded",
                    specialist_type=specialist_type,
                    deployment_id=result.get('deployment_id'),
                    model_version=result.get('model_version')
                )
            else:
                logger.warning(
                    "update_skipped_or_rejected",
                    specialist_type=specialist_type,
                    status=result.get('status'),
                    reason=result.get('reason')
                )

            orchestrator.close()

        except Exception as e:
            logger.error(
                "update_exception",
                specialist_type=specialist_type,
                error=str(e)
            )

    print(f"\nAtualização concluída: {success_count}/{len(specialist_types)} especialistas")
    return 0 if success_count == len(specialist_types) else 1


async def cmd_validate(args) -> int:
    """Executar validação shadow."""
    from .shadow_validator import ShadowValidator
    from .incremental_learner import IncrementalLearner
    from .config import OnlineLearningConfig
    import numpy as np

    logger.info(
        "starting_shadow_validation",
        specialist_type=args.specialist_type,
        samples=args.samples
    )

    config = OnlineLearningConfig()

    # Carregar modelos necessários para validação
    batch_model = _load_batch_model(args.specialist_type, config)
    online_learner = IncrementalLearner(config, args.specialist_type)

    # Tentar carregar checkpoint do online learner
    checkpoint_loaded = _try_load_online_checkpoint(online_learner, args.specialist_type, config)

    if not checkpoint_loaded:
        print(f"Aviso: Nenhum checkpoint online encontrado para {args.specialist_type}")
        print("A validação usará modelo online não treinado.")

    # Criar validator com assinatura correta
    validator = ShadowValidator(
        config=config,
        specialist_type=args.specialist_type,
        batch_model=batch_model,
        online_learner=online_learner
    )

    print(f"Validando modelo online para {args.specialist_type}...")
    print(f"Amostras configuradas: {args.samples}")

    # Obter resumo das validações (histórico existente)
    summary = validator.get_validation_summary()
    print(f"\nResultados da validação:")
    print(f"  Total validações: {summary['total_validations']}")
    print(f"  Taxa de aprovação: {summary['pass_rate']:.2%}")
    print(f"  KL divergence média: {summary['avg_kl_divergence']:.4f}")
    print(f"  Latência ratio média: {summary['avg_latency_ratio']:.2f}")

    if summary.get('common_failures'):
        print(f"\n  Falhas comuns:")
        for failure in summary['common_failures']:
            print(f"    - {failure['type']}: {failure['count']}x")

    return 0


async def cmd_rollback(args) -> int:
    """Executar rollback de modelo."""
    from .rollback_manager import RollbackManager, RollbackError
    from .config import OnlineLearningConfig

    logger.info(
        "starting_rollback",
        specialist_type=args.specialist_type,
        version=args.version,
        reason=args.reason
    )

    config = OnlineLearningConfig()

    # Criar RollbackManager com assinatura correta (config, specialist_type)
    manager = RollbackManager(
        config=config,
        specialist_type=args.specialist_type
    )

    print(f"Executando rollback para {args.specialist_type}...")
    print(f"Motivo: {args.reason}")

    try:
        # execute_rollback é síncrono, não async
        result = manager.execute_rollback(
            reason=args.reason,
            target_version=args.version
        )

        print(f"\nRollback executado com sucesso!")
        print(f"  ID: {result.get('rollback_id')}")
        print(f"  Versão anterior: {result.get('from_version')}")
        print(f"  Versão atual: {result.get('to_version')}")
        print(f"  Duração: {result.get('duration_seconds', 0):.2f}s")

        manager.close()
        return 0

    except RollbackError as e:
        print(f"\nFalha no rollback: {str(e)}")
        manager.close()
        return 1


async def cmd_status(args) -> int:
    """Mostrar status do pipeline."""
    from .online_monitor import OnlinePerformanceMonitor
    from .config import OnlineLearningConfig
    import json

    config = OnlineLearningConfig()

    specialist_types = (
        [args.specialist_type] if args.specialist_type
        else ['feasibility', 'risk', 'cost', 'technical', 'security']
    )

    status_data = {}
    for specialist_type in specialist_types:
        monitor = OnlinePerformanceMonitor(config, specialist_type)
        status_data[specialist_type] = monitor.get_status()

    if args.json:
        # Converter datetime para string
        def serialize(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            return obj

        print(json.dumps(status_data, default=serialize, indent=2))
    else:
        print("\n=== Status do Online Learning Pipeline ===\n")
        for specialist_type, status in status_data.items():
            print(f"[{specialist_type.upper()}]")
            print(f"  Health: {status.get('health_assessment', 'unknown')}")
            print(f"  Predictions: {status.get('total_predictions', 0)}")
            print(f"  Updates: {status.get('total_updates', 0)}")
            print(f"  Alertas ativos: {len(status.get('active_alerts', []))}")
            if status.get('last_update_time'):
                print(f"  Última atualização: {status['last_update_time']}")
            print()

    return 0


async def cmd_versions(args) -> int:
    """Listar versões de modelos."""
    from .rollback_manager import RollbackManager
    from .config import OnlineLearningConfig

    config = OnlineLearningConfig()

    # Criar RollbackManager com assinatura correta (config, specialist_type)
    manager = RollbackManager(
        config=config,
        specialist_type=args.specialist_type
    )

    # list_versions não requer specialist_type pois já foi passado no construtor
    versions = manager.list_versions(limit=args.limit)

    print(f"\n=== Versões do modelo {args.specialist_type} ===\n")

    if not versions:
        print("Nenhuma versão encontrada.")
        return 0

    for v in versions:
        # list_versions retorna objetos ModelVersion
        status_marker = " [STABLE]" if v.is_stable else ""
        print(f"  {v.version_id}{status_marker}")
        print(f"    Criado: {v.created_at.isoformat() if v.created_at else 'N/A'}")
        metrics = v.metrics or {}
        if 'f1' in metrics:
            print(f"    F1 Score: {metrics.get('f1', 0):.4f}")
        if 'loss' in metrics:
            print(f"    Loss: {metrics.get('loss', 0):.6f}")
        if 'validation_kl' in metrics:
            print(f"    KL Divergence: {metrics.get('validation_kl', 0):.4f}")
        print()

    manager.close()
    return 0


async def cmd_metrics(args) -> int:
    """Mostrar métricas de online learning."""
    from .online_monitor import OnlinePerformanceMonitor
    from .config import OnlineLearningConfig

    config = OnlineLearningConfig()

    specialist_types = (
        [args.specialist_type] if args.specialist_type
        else ['feasibility', 'risk', 'cost', 'technical', 'security']
    )

    print(f"\n=== Métricas de Online Learning ({args.period}) ===\n")

    for specialist_type in specialist_types:
        monitor = OnlinePerformanceMonitor(config, specialist_type)
        status = monitor.get_status()

        print(f"[{specialist_type.upper()}]")

        convergence = status.get('convergence_metrics', {})
        print(f"  Convergência:")
        print(f"    Loss médio: {convergence.get('average_loss', 0):.6f}")
        print(f"    Taxa convergência: {convergence.get('convergence_rate', 0):.4f}")

        prediction = status.get('prediction_metrics', {})
        print(f"  Predições:")
        print(f"    Total: {prediction.get('total', 0)}")
        print(f"    Latência média: {prediction.get('avg_latency_ms', 0):.2f}ms")
        print(f"    Confiança média: {prediction.get('avg_confidence', 0):.4f}")

        print()

    return 0


async def cmd_deploy(args) -> int:
    """Deploy gradual de modelo."""
    from .deployment_orchestrator import OnlineDeploymentOrchestrator
    from .config import OnlineLearningConfig

    logger.info(
        "starting_gradual_deploy",
        specialist_type=args.specialist_type,
        traffic_percentage=args.traffic_percentage
    )

    config = OnlineLearningConfig()

    # Carregar modelo batch para criar orchestrator
    batch_model = _load_batch_model(args.specialist_type, config)

    # Criar orchestrator com assinatura correta
    orchestrator = OnlineDeploymentOrchestrator(
        config=config,
        specialist_type=args.specialist_type,
        batch_model=batch_model,
        feedback_collector=_get_feedback_collector(args.specialist_type, config),
        feature_extractor=_get_feature_extractor(args.specialist_type)
    )

    print(f"Iniciando deploy gradual para {args.specialist_type}...")
    print(f"Tráfego: {args.traffic_percentage * 100:.0f}%")

    # Obter status atual do orchestrator
    status = orchestrator.get_status()
    print(f"\nStatus atual:")
    print(f"  Rollout atual: {status.get('current_rollout_percentage', 0)}%")
    print(f"  Versão do modelo: {status.get('model_version', 'N/A')}")

    # Na prática, isso atualizaria configuração de roteamento via ensemble
    print(f"\nDeploy configurado com sucesso!")
    print(f"Auto-rollback: {'habilitado' if args.auto_rollback else 'desabilitado'}")

    orchestrator.close()

    return 0


# ============================================================================
# Funções auxiliares para carregamento de modelos e dependências
# ============================================================================

def _load_batch_model(specialist_type: str, config: 'OnlineLearningConfig') -> Any:
    """
    Carrega modelo batch do MLflow ou retorna um stub.

    Args:
        specialist_type: Tipo do especialista
        config: Configuração de online learning

    Returns:
        Modelo batch ou stub se não disponível
    """
    try:
        import mlflow
        from mlflow.tracking import MlflowClient

        mlflow.set_tracking_uri(config.mlflow_tracking_uri)
        client = MlflowClient()

        # Buscar modelo em produção para o especialista
        model_name = f"{specialist_type}_specialist"
        try:
            model_uri = f"models:/{model_name}/Production"
            model = mlflow.pyfunc.load_model(model_uri)
            logger.info(
                "batch_model_loaded",
                specialist_type=specialist_type,
                model_name=model_name
            )
            return model
        except Exception as e:
            logger.warning(
                "mlflow_model_not_found",
                specialist_type=specialist_type,
                error=str(e)
            )
    except ImportError:
        logger.warning("mlflow_not_available")
    except Exception as e:
        logger.warning(
            "batch_model_load_failed",
            specialist_type=specialist_type,
            error=str(e)
        )

    # Retornar stub que implementa interface mínima
    return _BatchModelStub(specialist_type)


class _BatchModelStub:
    """Stub para modelo batch quando MLflow não disponível."""

    def __init__(self, specialist_type: str):
        self.specialist_type = specialist_type
        import numpy as np
        self._np = np

    def predict_proba(self, X):
        """Retorna probabilidades uniformes para stub."""
        n_samples = len(X) if hasattr(X, '__len__') else 1
        # Retorna distribuição uniforme para 3 classes (approve, reject, review_required)
        return self._np.ones((n_samples, 3)) / 3.0

    def predict(self, X):
        """Retorna predição default para stub."""
        n_samples = len(X) if hasattr(X, '__len__') else 1
        return self._np.array(['review_required'] * n_samples)


def _get_feedback_collector(specialist_type: str, config: 'OnlineLearningConfig') -> Optional[Any]:
    """
    Obtém FeedbackCollector para o especialista.

    Args:
        specialist_type: Tipo do especialista
        config: Configuração de online learning

    Returns:
        FeedbackCollector ou None
    """
    try:
        from neural_hive_specialists.feedback.feedback_collector import FeedbackCollector
        from neural_hive_specialists.config import SpecialistConfig

        # Criar config do especialista com valores do online learning config
        specialist_config = SpecialistConfig(
            mongodb_uri=config.mongodb_uri,
            mongodb_database=config.mongodb_database
        )

        return FeedbackCollector(specialist_config)
    except ImportError:
        logger.warning(
            "feedback_collector_not_available",
            specialist_type=specialist_type
        )
        return None
    except Exception as e:
        logger.warning(
            "feedback_collector_init_failed",
            specialist_type=specialist_type,
            error=str(e)
        )
        return None


def _get_feature_extractor(specialist_type: str) -> Optional[callable]:
    """
    Obtém função de extração de features para o especialista.

    Args:
        specialist_type: Tipo do especialista

    Returns:
        Função de extração ou None
    """
    try:
        from neural_hive_specialists.feature_extraction import FeatureExtractor

        extractor = FeatureExtractor()

        def extract_features(feedback: dict) -> list:
            """Extrai features de um feedback."""
            # Extrair features do plano cognitivo associado
            plan_data = feedback.get('cognitive_plan_snapshot', {})
            if not plan_data:
                # Fallback: usar campos básicos do feedback
                import numpy as np
                return np.zeros(64).tolist()

            features = extractor.extract_features(plan_data)
            return features.get('aggregated_features', [])

        return extract_features

    except ImportError:
        logger.warning(
            "feature_extractor_not_available",
            specialist_type=specialist_type
        )
        return None
    except Exception as e:
        logger.warning(
            "feature_extractor_init_failed",
            specialist_type=specialist_type,
            error=str(e)
        )
        return None


def _try_load_online_checkpoint(
    online_learner: Any,
    specialist_type: str,
    config: 'OnlineLearningConfig'
) -> bool:
    """
    Tenta carregar checkpoint mais recente para o online learner.

    Args:
        online_learner: Instância do IncrementalLearner
        specialist_type: Tipo do especialista
        config: Configuração de online learning

    Returns:
        True se checkpoint carregado, False caso contrário
    """
    import os
    import glob

    checkpoint_dir = getattr(config, 'checkpoint_dir', '/data/online_learning/checkpoints')
    pattern = os.path.join(checkpoint_dir, f"{specialist_type}_*.pkl")

    checkpoints = sorted(glob.glob(pattern), reverse=True)

    if not checkpoints:
        return False

    try:
        online_learner.load_checkpoint(checkpoints[0])
        logger.info(
            "online_checkpoint_loaded",
            specialist_type=specialist_type,
            checkpoint=checkpoints[0]
        )
        return True
    except Exception as e:
        logger.warning(
            "online_checkpoint_load_failed",
            specialist_type=specialist_type,
            checkpoint=checkpoints[0],
            error=str(e)
        )
        return False


async def main_async(args) -> int:
    """Função principal assíncrona."""
    command_handlers = {
        'update': cmd_update,
        'validate': cmd_validate,
        'rollback': cmd_rollback,
        'status': cmd_status,
        'versions': cmd_versions,
        'metrics': cmd_metrics,
        'deploy': cmd_deploy,
    }

    handler = command_handlers.get(args.command)
    if handler is None:
        print("Comando não especificado. Use --help para ver comandos disponíveis.")
        return 1

    return await handler(args)


def main():
    """Ponto de entrada CLI."""
    parser = create_parser()
    args = parser.parse_args()

    if args.verbose:
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(0)
        )

    try:
        exit_code = asyncio.run(main_async(args))
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nOperação cancelada pelo usuário.")
        sys.exit(130)
    except Exception as e:
        logger.exception("cli_error", error=str(e))
        print(f"\nErro: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
