"""Activity para publicar eventos de Saga no Kafka."""
import logging
from typing import Any, Dict

from src.config.settings import get_settings
from src.saga.saga_producer import SagaProducer
from src.saga.saga_metrics import get_saga_metrics

logger = logging.getLogger(__name__)

# Producer singleton
_producer: SagaProducer | None = None


async def get_saga_producer() -> SagaProducer:
    """Retorna instância singleton do SagaProducer."""
    global _producer
    if _producer is None:
        settings = get_settings()
        _producer = SagaProducer(settings)
        await _producer.initialize()

        # Conectar com metrics singleton
        metrics = get_saga_metrics()
        _producer.set_metrics(metrics)

    return _producer


async def publish_saga_created(
    saga_id: str,
    workflow_id: str,
    plan_id: str,
    intent_id: str,
    steps_count: int,
    metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Publica evento saga.created no Kafka para observabilidade.

    Args:
        saga_id: ID da Saga criada
        workflow_id: ID do workflow Temporal
        plan_id: ID do Cognitive Plan
        intent_id: ID da intenção
        steps_count: Número de steps da Saga
        metadata: Metadados adicionais

    Returns:
        Dict com status da publicação
    """
    logger.info(
        f'publishing_saga_created saga_id={saga_id} '
        f'workflow_id={workflow_id} plan_id={plan_id}'
    )

    try:
        producer = await get_saga_producer()

        # Criar SagaState mínimo para publicação
        from src.saga.saga_state import SagaState, SagaStatus

        saga = SagaState(
            saga_id=saga_id,
            workflow_id=workflow_id,
            plan_id=plan_id,
            intent_id=intent_id,
            status=SagaStatus.PENDING,
            steps=[],
            compensation_order=[],
            created_at=0,  # Não usado para evento
            metadata=metadata or {}
        )

        # Sobrescrever steps_count para o evento
        await producer.publish_saga_created(saga)

        logger.info(
            f'saga_created_publishedSuccessfully saga_id={saga_id} '
            f'workflow_id={workflow_id}'
        )

        return {
            'success': True,
            'saga_id': saga_id,
            'workflow_id': workflow_id,
        }

    except Exception as e:
        logger.error(
            f'failed_to_publish_saga_created saga_id={saga_id} '
            f'workflow_id={workflow_id} error={e}'
        )
        # Não falhar o workflow se a publicação falhar
        return {
            'success': False,
            'saga_id': saga_id,
            'workflow_id': workflow_id,
            'error': str(e),
        }


async def publish_saga_started(
    saga_id: str,
    workflow_id: str,
    plan_id: str,
    steps_count: int
) -> Dict[str, Any]:
    """
    Publica evento saga.started no Kafka.

    Args:
        saga_id: ID da Saga iniciada
        workflow_id: ID do workflow Temporal
        plan_id: ID do Cognitive Plan
        steps_count: Número de steps da Saga

    Returns:
        Dict com status da publicação
    """
    logger.info(
        f'publishing_saga_started saga_id={saga_id} '
        f'workflow_id={workflow_id}'
    )

    try:
        producer = await get_saga_producer()

        from src.saga.saga_state import SagaState, SagaStatus

        saga = SagaState(
            saga_id=saga_id,
            workflow_id=workflow_id,
            plan_id=plan_id,
            intent_id='',
            status=SagaStatus.STARTED,
            steps=[],
            compensation_order=[],
            created_at=0,
            started_at=0,
        )

        await producer.publish_saga_started(saga)

        logger.info(
            f'saga_started_publishedSuccessfully saga_id={saga_id}'
        )

        return {
            'success': True,
            'saga_id': saga_id,
        }

    except Exception as e:
        logger.error(
            f'failed_to_publish_saga_started saga_id={saga_id} error={e}'
        )
        return {
            'success': False,
            'saga_id': saga_id,
            'error': str(e),
        }


async def publish_saga_completed(
    saga_id: str,
    workflow_id: str,
    plan_id: str,
    steps_completed: int
) -> Dict[str, Any]:
    """
    Publica evento saga.completed no Kafka.

    Args:
        saga_id: ID da Saga completada
        workflow_id: ID do workflow Temporal
        plan_id: ID do Cognitive Plan
        steps_completed: Número de steps completados

    Returns:
        Dict com status da publicação
    """
    logger.info(
        f'publishing_saga_completed saga_id={saga_id} '
        f'workflow_id={workflow_id} steps={steps_completed}'
    )

    try:
        producer = await get_saga_producer()

        from src.saga.saga_state import SagaState, SagaStatus

        saga = SagaState(
            saga_id=saga_id,
            workflow_id=workflow_id,
            plan_id=plan_id,
            intent_id='',
            status=SagaStatus.COMPLETED,
            steps=[],
            compensation_order=[],
            created_at=0,
            completed_at=0,
        )

        await producer.publish_saga_completed(saga)

        logger.info(
            f'saga_completed_publishedSuccessfully saga_id={saga_id}'
        )

        return {
            'success': True,
            'saga_id': saga_id,
        }

    except Exception as e:
        logger.error(
            f'failed_to_publish_saga_completed saga_id={saga_id} error={e}'
        )
        return {
            'success': False,
            'saga_id': saga_id,
            'error': str(e),
        }


async def publish_saga_failed(
    saga_id: str,
    workflow_id: str,
    plan_id: str,
    error: str,
    retry_count: int = 0,
    max_retries: int = 1
) -> Dict[str, Any]:
    """
    Publica evento saga.failed no Kafka.

    Args:
        saga_id: ID da Saga falhada
        workflow_id: ID do workflow Temporal
        plan_id: ID do Cognitive Plan
        error: Erro que causou a falha
        retry_count: Número de tentativas realizadas
        max_retries: Número máximo de tentativas

    Returns:
        Dict com status da publicação
    """
    logger.info(
        f'publishing_saga_failed saga_id={saga_id} '
        f'workflow_id={workflow_id} error={error}'
    )

    try:
        producer = await get_saga_producer()

        from src.saga.saga_state import SagaState, SagaStatus

        saga = SagaState(
            saga_id=saga_id,
            workflow_id=workflow_id,
            plan_id=plan_id,
            intent_id='',
            status=SagaStatus.FAILED,
            steps=[],
            compensation_order=[],
            created_at=0,
            failed_at=0,
            retry_count=retry_count,
            max_retries=max_retries,
            error=error,
        )

        await producer.publish_saga_failed(saga, error)

        logger.info(
            f'saga_failed_publishedSuccessfully saga_id={saga_id}'
        )

        return {
            'success': True,
            'saga_id': saga_id,
        }

    except Exception as e:
        logger.error(
            f'failed_to_publish_saga_failed saga_id={saga_id} error={e}'
        )
        return {
            'success': False,
            'saga_id': saga_id,
            'error': str(e),
        }
