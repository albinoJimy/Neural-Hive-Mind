"""
Testes unitarios para a resiliencia de startup do Kafka (P1 fail-fast).

Valida que ``validate_kafka_topics_exist`` (src/main.py):
    - faz retry com backoff exponencial em falhas transitorias de conexao
      e tem sucesso quando o Kafka recupera;
    - levanta RuntimeError apos esgotar as tentativas;
    - faz fail-fast imediato em topicos em falta quando o retry de topicos
      esta desativado;
    - faz retry e tem sucesso quando os topicos sao criados em paralelo
      durante o arranque do cluster.

Estes testes NAO dependem do fixture partilhado ``mock_settings``: constroem
um mock de settings local para isolamento total (evita tocar em conftest.py).
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from confluent_kafka import KafkaException

# src/main.py instancia Settings() ao nivel do modulo (get_settings na importacao).
# Garantir as env vars obrigatorias antes do import para a coleta nao falhar.
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("APPROVAL_SERVICE_REQUIRE_AUTH", "false")

from src.main import validate_kafka_topics_exist

REQUIRED_TOPICS = [
    "cognitive-plans-approval-requests",
    "cognitive-plans-approval-responses",
]


def _make_settings(
    *,
    max_retries: int = 5,
    retry_missing_topics: bool = True,
):
    """Cria um mock de settings local com os campos minimos necessarios.

    Usa backoff zero para os testes nao introduzirem latencia (a chamada a
    ``asyncio.sleep`` e adicionalmente mockada, mas mantemos 0.0 por seguranca).
    """
    return SimpleNamespace(
        kafka_approval_requests_topic=REQUIRED_TOPICS[0],
        kafka_approval_responses_topic=REQUIRED_TOPICS[1],
        kafka_bootstrap_servers="localhost:9092",
        kafka_security_protocol="PLAINTEXT",
        kafka_sasl_mechanism=None,
        kafka_sasl_username=None,
        kafka_sasl_password=None,
        kafka_startup_max_retries=max_retries,
        kafka_startup_initial_backoff_seconds=0.0,
        kafka_startup_max_backoff_seconds=0.0,
        kafka_startup_retry_missing_topics=retry_missing_topics,
    )


def _metadata_with_topics(topics):
    """Cria um objeto de metadata falso compativel com ``cluster_metadata.topics.keys()``."""
    metadata = MagicMock()
    metadata.topics = {name: MagicMock() for name in topics}
    return metadata


async def test_retry_transitorio_e_sucesso_eventual():
    """Falha transitoria nas 2 primeiras tentativas, sucesso na 3a (sem excecao)."""
    settings = _make_settings(max_retries=5)

    admin_instance = MagicMock()
    # 2 falhas de transporte seguidas de metadata valida com todos os topicos.
    admin_instance.list_topics.side_effect = [
        KafkaException("Broker transport failure"),
        KafkaException("Broker transport failure"),
        _metadata_with_topics(REQUIRED_TOPICS),
    ]

    with patch("src.main.AdminClient", return_value=admin_instance), patch(
        "src.main.asyncio.sleep", new=AsyncMock()
    ) as mock_sleep:
        await validate_kafka_topics_exist(settings)

    assert admin_instance.list_topics.call_count == 3
    # Dois backoffs entre as 3 tentativas.
    assert mock_sleep.await_count == 2


async def test_raise_apos_esgotar_tentativas():
    """Falha de transporte em todas as tentativas leva a RuntimeError."""
    settings = _make_settings(max_retries=3)

    admin_instance = MagicMock()
    admin_instance.list_topics.side_effect = KafkaException("Broker transport failure")

    with patch("src.main.AdminClient", return_value=admin_instance), patch(
        "src.main.asyncio.sleep", new=AsyncMock()
    ) as mock_sleep, pytest.raises(RuntimeError):
        await validate_kafka_topics_exist(settings)

    assert admin_instance.list_topics.call_count == 3
    # Backoff aplicado entre tentativas, mas nao apos a ultima: max_retries - 1.
    assert mock_sleep.await_count == 2


async def test_topicos_em_falta_com_retry_desativado():
    """Topicos ausentes com retry_missing_topics=False => fail-fast imediato."""
    settings = _make_settings(max_retries=5, retry_missing_topics=False)

    admin_instance = MagicMock()
    # Cluster acessivel mas sem os topicos requeridos.
    admin_instance.list_topics.return_value = _metadata_with_topics(["outro-topico"])

    with patch("src.main.AdminClient", return_value=admin_instance), patch(
        "src.main.asyncio.sleep", new=AsyncMock()
    ) as mock_sleep, pytest.raises(RuntimeError):
        await validate_kafka_topics_exist(settings)

    # Fail-fast: uma unica chamada e nenhum backoff.
    assert admin_instance.list_topics.call_count == 1
    assert mock_sleep.await_count == 0


async def test_topicos_em_falta_eventualmente_criados():
    """Topicos criados em paralelo: 1a chamada sem topicos, 2a com topicos => sucesso."""
    settings = _make_settings(max_retries=5, retry_missing_topics=True)

    admin_instance = MagicMock()
    admin_instance.list_topics.side_effect = [
        _metadata_with_topics(["outro-topico"]),
        _metadata_with_topics(REQUIRED_TOPICS),
    ]

    with patch("src.main.AdminClient", return_value=admin_instance), patch(
        "src.main.asyncio.sleep", new=AsyncMock()
    ) as mock_sleep:
        await validate_kafka_topics_exist(settings)

    assert admin_instance.list_topics.call_count == 2
    # Um backoff entre as 2 tentativas.
    assert mock_sleep.await_count == 1
