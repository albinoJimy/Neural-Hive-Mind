"""
QueenAgentIntegration - Integração via gRPC com Queen Agent.

Responsável por:
- Registrar scout agent no Queen Agent
- Enviar heartbeats periódicos
- Reportar resultados de explorações
- Receber e executar comandos do Queen Agent
"""

import asyncio
from collections.abc import Callable
from typing import Any, Optional

import structlog

logger = structlog.get_logger()


class QueenAgentIntegration:
    """Integração gRPC com Queen Agent."""

    def __init__(
        self, channel, stub, agent_id: Optional[str] = None, heartbeat_interval_sec: int = 30
    ):
        """
        Inicializa a integração com Queen Agent.

        Args:
            channel: Canal gRPC
            stub: Stub gRPC do Queen Agent
            agent_id: ID do scout agent
            heartbeat_interval_sec: Intervalo de heartbeat
        """
        self.channel = channel
        self.stub = stub
        self.agent_id = agent_id or "scout-agent-unknown"
        self.heartbeat_interval_sec = heartbeat_interval_sec

        # Capacidades do agente
        self.capabilities: list[str] = [
            "codebase_exploration",
            "pattern_discovery",
            "solution_synthesis",
        ]

        # Handlers de comandos
        self.command_handlers: dict[str, Callable] = {}

        # Status atual
        self.current_status: dict[str, Any] = {"status": "ready", "active_explorations": 0}

        # Task de heartbeat
        self._heartbeat_task: Optional[asyncio.Task] = None

    async def register_agent(self) -> dict[str, Any]:
        """
        Registra o scout agent no Queen Agent.

        Returns:
            Dict com resultado do registro
        """
        try:
            # Chamar gRPC RegisterAgent
            # Em produção, isso seria: await self.stub.RegisterAgent(...)
            # Para testes, retornamos mock
            logger.info(
                "registering_in_queen_agent", agent_id=self.agent_id, capabilities=self.capabilities
            )

            # Mock response para testes
            response = {
                "agent_id": f"registered-{self.agent_id}",
                "status": "accepted",
                "heartbeat_interval": self.heartbeat_interval_sec,
            }

            # Iniciar heartbeat
            self._start_heartbeat()

            return response

        except Exception as e:
            logger.error("registration_failed", agent_id=self.agent_id, error=str(e))
            return {"agent_id": self.agent_id, "status": "failed", "error": str(e)}

    async def send_heartbeat(self) -> dict[str, Any]:
        """
        Envia heartbeat para Queen Agent.

        Returns:
            Dict com resposta do heartbeat
        """
        try:
            logger.debug("sending_heartbeat", agent_id=self.agent_id)

            # Em produção: await self.stub.SendHeartbeat(...)
            response = {"acknowledged": True, "timestamp": asyncio.get_event_loop().time()}

            return response

        except Exception as e:
            logger.error("heartbeat_failed", error=str(e))
            return {"acknowledged": False, "error": str(e)}

    def _start_heartbeat(self):
        """Inicia task de heartbeat em background."""
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self):
        """Loop de envio de heartbeats."""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval_sec)
                await self.send_heartbeat()
            except asyncio.CancelledError:
                logger.info("heartbeat_cancelled")
                break
            except Exception as e:
                logger.error("heartbeat_loop_error", error=str(e))

    async def report_exploration_results(self, results: dict[str, Any]) -> dict[str, Any]:
        """
        Reporta resultados de exploração ao Queen Agent.

        Args:
            results: Resultados da exploração

        Returns:
            Dict com confirmação de recebimento
        """
        try:
            logger.info(
                "reporting_exploration_results",
                exploration_id=results.get("exploration_id"),
                status=results.get("status"),
            )

            # Em produção: await self.stub.ReportExploration(...)
            response = {"received": True, "exploration_id": results.get("exploration_id")}

            return response

        except Exception as e:
            logger.error(
                "report_results_failed", exploration_id=results.get("exploration_id"), error=str(e)
            )
            return {"received": False, "error": str(e)}

    def register_command_handler(self, command: str, handler: Callable):
        """
        Registra handler para comando do Queen Agent.

        Args:
            command: Nome do comando
            handler: Função assíncona que processa o comando
        """
        self.command_handlers[command] = handler
        logger.info("command_handler_registered", command=command)

    async def handle_command(self, command: dict[str, Any]) -> dict[str, Any]:
        """
        Processa comando recebido do Queen Agent.

        Args:
            command: Dict com nome e parâmetros do comando

        Returns:
            Dict com resultado do processamento
        """
        command_name = command.get("command")
        params = command.get("params", {})

        logger.info("handling_command", command=command_name, params=params)

        handler = self.command_handlers.get(command_name)

        if handler:
            try:
                result = await handler(command)
                return {"handled": True, "result": result}
            except Exception as e:
                logger.error("command_handler_failed", error=str(e))
                return {"handled": False, "error": str(e)}
        else:
            return {"handled": False, "error": f"No handler for command: {command_name}"}

    async def report_status(self, status: dict[str, Any]) -> dict[str, Any]:
        """
        Reporta status atual ao Queen Agent.

        Args:
            status: Dict com informações de status

        Returns:
            Dict com confirmação
        """
        try:
            logger.info("reporting_status", agent_id=self.agent_id, status=status.get("status"))

            # Atualizar status interno
            self.current_status.update(status)

            # Em produção: await self.stub.ReportStatus(...)
            response = {"received": True, "agent_id": self.agent_id}

            return response

        except Exception as e:
            logger.error("report_status_failed", error=str(e))
            return {"received": False, "error": str(e)}

    async def shutdown(self):
        """Encerra a integração e para o heartbeat."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        logger.info("queen_agent_integration_shutdown", agent_id=self.agent_id)
