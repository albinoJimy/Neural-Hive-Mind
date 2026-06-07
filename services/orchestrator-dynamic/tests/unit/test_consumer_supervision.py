"""
Testes unitários para a supervisão de tasks de consumo e para a lógica de
health/readiness do consumer approval-responses.

Cobre o fix [P0-consumer]: "Consumer approval-responses morre silenciosamente;
planos aprovados nunca executam".

Valida:
- ``_spawn_supervised`` recria a task quando esta termina por exceção.
- ``_spawn_supervised`` NÃO recria quando a task é cancelada.
- ``_spawn_supervised`` NÃO recria durante shutdown (is_shutting_down=True).
- ``_is_consumer_task_alive`` reflete corretamente o estado vivo do consumer.
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

# As settings são avaliadas no import de src.main; definir env mínimo antes.
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("REDIS_CLUSTER_NODES", "localhost:6379")

from src.integration.flow_c_consumer import FlowCApprovalResponseConsumer
from src.main import (
    _is_consumer_task_alive,
    _register_supervised_task,
    _spawn_supervised,
    app_state,
)


@pytest.fixture(autouse=True)
def _reset_app_state():
    """Garante estado limpo entre testes."""
    app_state.is_shutting_down = False
    app_state.supervised_tasks = {}
    app_state.approval_response_task = None
    yield
    app_state.is_shutting_down = False
    app_state.supervised_tasks = {}
    app_state.approval_response_task = None


class TestSpawnSupervised:
    """Testes da helper de supervisão de tasks."""

    @pytest.mark.asyncio
    async def test_recria_task_apos_excecao(self):
        """Se a coroutine termina por exceção, a task deve ser recriada."""
        call_count = {"n": 0}
        recreated = asyncio.Event()

        async def _coro():
            call_count["n"] += 1
            if call_count["n"] == 1:
                # Primeira execução: falha imediatamente.
                raise RuntimeError("falha simulada do consumer")
            # Segunda execução (recriada): sinaliza e fica viva.
            recreated.set()
            await asyncio.sleep(3600)

        task = _spawn_supervised("approval_response_task", _coro)

        # Aguardar a recriação (callback é agendado no loop após a exceção).
        await asyncio.wait_for(recreated.wait(), timeout=2.0)

        assert call_count["n"] == 2, "A task deveria ter sido recriada após a exceção"

        # A task registada deve ser a nova (viva), não a original.
        current = app_state.supervised_tasks["approval_response_task"]
        assert current is not task
        assert not current.done()

        # Limpeza.
        current.cancel()
        with pytest.raises(asyncio.CancelledError):
            await current

    @pytest.mark.asyncio
    async def test_nao_recria_em_cancelamento(self):
        """Cancelamento (shutdown gracioso) NÃO deve recriar a task."""
        started = asyncio.Event()

        async def _coro():
            started.set()
            await asyncio.sleep(3600)

        task = _spawn_supervised("flow_c_task", _coro)
        await asyncio.wait_for(started.wait(), timeout=2.0)

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # Dar oportunidade ao callback de correr.
        await asyncio.sleep(0.05)

        # A task registada deve continuar a ser a cancelada — não houve recriação.
        assert app_state.supervised_tasks["flow_c_task"] is task
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_nao_recria_durante_shutdown(self):
        """Durante shutdown, exceção na task NÃO deve recriá-la."""
        app_state.is_shutting_down = True
        call_count = {"n": 0}

        async def _coro():
            call_count["n"] += 1
            raise RuntimeError("falha durante shutdown")

        task = _spawn_supervised("approval_response_task", _coro)

        # Aguardar a task terminar (por exceção).
        with pytest.raises(RuntimeError):
            await task

        # Dar oportunidade ao callback de correr.
        await asyncio.sleep(0.05)

        assert call_count["n"] == 1, "Não deveria recriar durante shutdown"
        assert app_state.supervised_tasks["approval_response_task"] is task


class TestIsConsumerTaskAlive:
    """Testes da lógica de health do consumer usada no /ready."""

    class _FakeConsumer:
        def __init__(self, running: bool):
            self.running = running

    @pytest.mark.asyncio
    async def test_vivo_quando_running_e_task_ativa(self):
        async def _coro():
            await asyncio.sleep(3600)

        task = asyncio.create_task(_coro())
        try:
            assert _is_consumer_task_alive(self._FakeConsumer(True), task) is True
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    @pytest.mark.asyncio
    async def test_morto_quando_task_terminou(self):
        """Task morta silenciosamente (done) => consumer reportado como não vivo."""

        async def _coro():
            return None

        task = asyncio.create_task(_coro())
        await task  # task termina (done)

        assert _is_consumer_task_alive(self._FakeConsumer(True), task) is False

    def test_morto_quando_consumer_none(self):
        assert _is_consumer_task_alive(None, None) is False

    def test_morto_quando_task_none(self):
        assert _is_consumer_task_alive(self._FakeConsumer(True), None) is False

    @pytest.mark.asyncio
    async def test_morto_quando_running_false(self):
        async def _coro():
            await asyncio.sleep(3600)

        task = asyncio.create_task(_coro())
        try:
            assert _is_consumer_task_alive(self._FakeConsumer(False), task) is False
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


class TestReadinessRefleteTaskRecriada:
    """
    [P0-consumer] Garante que, APÓS o supervisor recriar a task, o caminho de
    readiness (atributo fixo ``app_state.approval_response_task`` lido pelo
    /ready e pelo shutdown) reflete a task NOVA (viva) e não a antiga ``.done()``.

    Sem a sincronização do atributo fixo, o /ready devolveria 503 de forma
    permanente após qualquer recriação bem-sucedida — anulando o próprio
    supervisor que o fix introduz.
    """

    class _FakeConsumer:
        def __init__(self, running: bool):
            self.running = running

    @pytest.mark.asyncio
    async def test_atributo_fixo_aponta_para_task_recriada(self):
        """Após recriação, app_state.approval_response_task é a task viva."""
        call_count = {"n": 0}
        recreated = asyncio.Event()

        async def _coro():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("falha simulada do consumer")
            recreated.set()
            await asyncio.sleep(3600)

        original = _spawn_supervised("approval_response_task", _coro)

        # No spawn inicial, o atributo fixo já aponta para a task original.
        assert app_state.approval_response_task is original

        await asyncio.wait_for(recreated.wait(), timeout=2.0)

        current = app_state.supervised_tasks["approval_response_task"]
        # DEFEITO original: o atributo fixo ficava preso à task original morta.
        assert app_state.approval_response_task is current
        assert app_state.approval_response_task is not original
        assert original.done()
        assert not app_state.approval_response_task.done()

        # E o readiness, lendo o atributo fixo, reporta o consumer como vivo.
        consumer = self._FakeConsumer(True)
        assert _is_consumer_task_alive(consumer, app_state.approval_response_task) is True
        # A referência antiga (morta) reportaria not_ready — comprova o contraste.
        assert _is_consumer_task_alive(consumer, original) is False

        current.cancel()
        with pytest.raises(asyncio.CancelledError):
            await current


class TestConsumeTimeoutPorMensagem:
    """
    [P0-consumer] Garante que uma mensagem "venenosa" cujo processamento bloqueia
    além de ``process_timeout_s`` NÃO congela o poll loop: o timeout é apanhado,
    registado, e o offset é avançado (commit) para desbloquear o consumo.
    """

    @pytest.mark.asyncio
    async def test_poison_message_e_saltada_com_commit(self):
        consumer = FlowCApprovalResponseConsumer(kafka_bootstrap_servers="localhost:9092")
        consumer.process_timeout_s = 0.05
        consumer.running = True

        msg = MagicMock()
        msg.topic = "cognitive-plans-approval-responses"
        msg.partition = 0
        msg.offset = 1
        msg.key = None
        msg.value = b"{}"
        tp = MagicMock()

        chamadas = {"n": 0}

        def _getmany_side(*_args, **_kwargs):
            chamadas["n"] += 1
            if chamadas["n"] == 1:
                return {tp: [msg]}
            # Segunda iteração: termina o loop.
            consumer.running = False
            return {}

        consumer.consumer = MagicMock()
        consumer.consumer.getmany = AsyncMock(side_effect=_getmany_side)
        consumer.consumer.commit = AsyncMock()

        async def _processamento_lento(_message):
            # Bloqueia muito além do timeout configurado (poison message).
            await asyncio.sleep(5)

        consumer._process_approval_response = _processamento_lento

        # Não deve ficar preso: o timeout salta a mensagem e o loop termina.
        await asyncio.wait_for(consumer.consume(), timeout=3.0)

        # O offset foi committed apesar do timeout (mensagem saltada).
        consumer.consumer.commit.assert_awaited()


class TestRegisterSupervisedTask:
    """Testes da helper que sincroniza mapa + atributo fixo de AppState."""

    @pytest.mark.asyncio
    async def test_atualiza_mapa_e_atributo(self):
        async def _coro():
            await asyncio.sleep(3600)

        task = asyncio.create_task(_coro())
        try:
            _register_supervised_task("approval_response_task", task)
            assert app_state.supervised_tasks["approval_response_task"] is task
            assert app_state.approval_response_task is task
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    @pytest.mark.asyncio
    async def test_nome_sem_atributo_so_atualiza_mapa(self):
        """Nome sem atributo homónimo em AppState não levanta erro."""

        async def _coro():
            await asyncio.sleep(3600)

        task = asyncio.create_task(_coro())
        try:
            _register_supervised_task("nome_inexistente_xyz", task)
            assert app_state.supervised_tasks["nome_inexistente_xyz"] is task
            assert not hasattr(app_state, "nome_inexistente_xyz")
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
