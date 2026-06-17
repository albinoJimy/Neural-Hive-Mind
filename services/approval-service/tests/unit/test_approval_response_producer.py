"""
Testes unitarios para ApprovalResponseProducer

Foco: resiliencia do producer transacional a invalidacao do producer id pelo
broker (INVALID_PRODUCER_ID_MAPPING / producer fenced). Ao detetar o erro, o
producer deve recriar-se (re-init transactions) e re-tentar a publicacao uma vez.
"""

from unittest.mock import MagicMock

import pytest
from confluent_kafka import KafkaException
from src.producers.approval_response_producer import ApprovalResponseProducer


@pytest.fixture()
def producer():
    """Instancia do producer com settings/contexto mockados (sem Kafka real)"""
    settings = MagicMock()
    return ApprovalResponseProducer(settings=settings, context_manager=None)


class TestIsRecoverableProducerError:
    """Classificacao de erros recuperaveis do producer transacional"""

    @pytest.mark.parametrize(
        "marker",
        [
            "INVALID_PRODUCER_ID_MAPPING",
            "INVALID_PRODUCER_EPOCH",
            "Producer FENCED by broker",
            "requires epoch bump",
        ],
    )
    def test_reconhece_erros_de_producer_id(self, marker):
        exc = KafkaException(marker)
        assert ApprovalResponseProducer._is_recoverable_producer_error(exc) is True

    def test_kafka_exception_generica_nao_e_recuperavel(self):
        exc = KafkaException("Local: Message timed out")
        assert ApprovalResponseProducer._is_recoverable_producer_error(exc) is False

    def test_excecao_nao_kafka_nao_e_recuperavel(self):
        assert ApprovalResponseProducer._is_recoverable_producer_error(ValueError("x")) is False


class TestSendApprovalResponseRetry:
    """Comportamento de retry com re-inicializacao do producer"""

    @pytest.mark.asyncio()
    async def test_reinicializa_e_retenta_em_producer_id_invalido(self, producer):
        response = MagicMock()
        response.plan_id = "plan-123"

        # 1a tentativa falha com erro recuperavel; 2a sucede
        producer._produce_in_transaction = MagicMock(
            side_effect=[KafkaException("INVALID_PRODUCER_ID_MAPPING (requires epoch bump)"), None]
        )
        producer._reinitialize_producer = MagicMock()

        await producer.send_approval_response(response)

        assert producer._produce_in_transaction.call_count == 2
        producer._reinitialize_producer.assert_called_once()

    @pytest.mark.asyncio()
    async def test_sucesso_na_primeira_tentativa_nao_reinicializa(self, producer):
        response = MagicMock()
        response.plan_id = "plan-123"

        producer._produce_in_transaction = MagicMock(return_value=None)
        producer._reinitialize_producer = MagicMock()

        await producer.send_approval_response(response)

        producer._produce_in_transaction.assert_called_once()
        producer._reinitialize_producer.assert_not_called()

    @pytest.mark.asyncio()
    async def test_erro_nao_recuperavel_propaga_sem_retry(self, producer):
        response = MagicMock()
        response.plan_id = "plan-123"

        producer._produce_in_transaction = MagicMock(
            side_effect=KafkaException("Local: Message timed out")
        )
        producer._reinitialize_producer = MagicMock()

        with pytest.raises(KafkaException):
            await producer.send_approval_response(response)

        producer._produce_in_transaction.assert_called_once()
        producer._reinitialize_producer.assert_not_called()
