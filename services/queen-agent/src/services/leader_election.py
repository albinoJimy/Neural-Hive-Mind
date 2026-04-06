"""
Protocolo de Eleição de Líder para Queen Agent

Implementa eleição distribuída usando Redis para alta disponibilidade.
Usa o padrão "Leader Election with Redis" baseado em locks distribuídos.
"""
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
UTC = timezone.utc  # type: ignore
from enum import Enum
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from src.clients import RedisClient
    from src.config import Settings


logger = structlog.get_logger()


class NodeRole(Enum):
    """Papel de um nó no cluster"""

    LEADER = "leader"
    FOLLOWER = "follower"
    CANDIDATE = "candidate"


@dataclass
class ElectionState:
    """Estado da eleição"""

    role: NodeRole = NodeRole.FOLLOWER
    leader_id: str | None = None
    term: int = 0
    last_heartbeat: datetime | None = None
    voted_for: str | None = None


class LeaderElection:
    """
    Gerencia eleição de líder usando Redis para coordenação distribuída.

    Usa o padrão "lease-based" onde o líder deve renovar seu lease periodicamente.
    Se o lease expirar, outros nós podem iniciar eleição.
    """

    # Chave Redis para lock de liderança
    LEADER_LOCK_KEY = "queen_agent:leader_election:lock"
    # Chave Redis para metadados do líder
    LEADER_META_KEY = "queen_agent:leader_election:meta"
    # Chave Redis para heartbeat
    LEADER_HEARTBEAT_KEY = "queen_agent:leader_election:heartbeat"

    def __init__(
        self,
        redis_client: "RedisClient",
        settings: "Settings",
        node_id: str,
    ):
        self.redis_client = redis_client
        self.settings = settings
        self.node_id = node_id

        # Configurações com defaults
        self.lease_ttl_seconds = getattr(settings, "ELECTION_LEASE_TTL_SECONDS", 10)
        self.heartbeat_interval_seconds = getattr(
            settings, "ELECTION_HEARTBEAT_INTERVAL_SECONDS", 2
        )
        self.election_timeout_seconds = getattr(settings, "ELECTION_TIMEOUT_SECONDS", 5)

        # Estado local
        self.state = ElectionState()
        self.is_running = False
        self.election_task: asyncio.Task | None = None
        self.heartbeat_task: asyncio.Task | None = None

        # Callbacks
        self.on_become_leader: callable | None = None
        self.on_become_follower: callable | None = None
        self.on_leader_change: callable | None = None

        logger.info(
            "leader_election_initialized",
            node_id=node_id,
            lease_ttl=self.lease_ttl_seconds,
            heartbeat_interval=self.heartbeat_interval_seconds,
        )

    async def start(self) -> None:
        """Iniciar o processo de eleição"""
        if self.is_running:
            logger.warning("leader_election_already_running")
            return

        self.is_running = True

        # Iniciar heartbeat task
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # Iniciar election task
        self.election_task = asyncio.create_task(self._election_loop())

        logger.info("leader_election_started", node_id=self.node_id)

    async def stop(self) -> None:
        """Parar o processo de eleição"""
        self.is_running = False

        # Cancelar tasks
        if self.election_task:
            self.election_task.cancel()
        if self.heartbeat_task:
            self.heartbeat_task.cancel()

        # Se somos o líder, liberar o lock
        if self.state.role == NodeRole.LEADER:
            await self._resign_leadership()

        logger.info("leader_election_stopped", node_id=self.node_id)

    async def _election_loop(self) -> None:
        """
        Loop principal de eleição.

        Tenta adquirir liderança periodicamente ou renova lease se já é líder.
        """
        while self.is_running:
            try:
                current_leader = await self._get_current_leader()

                if current_leader == self.node_id:
                    # Somos o líder - renovar lease
                    await self._renew_leadership()
                    self.state.role = NodeRole.LEADER

                elif current_leader is None:
                    # Nenhum líder - tentar adquirir
                    acquired = await self._acquire_leadership()
                    if acquired:
                        self.state.role = NodeRole.LEADER
                        logger.info("became_leader", node_id=self.node_id)
                        if self.on_become_leader:
                            await self.on_become_leader()
                    else:
                        self.state.role = NodeRole.FOLLOWER

                # Outro nó é líder
                elif self.state.role != NodeRole.FOLLOWER:
                    self.state.role = NodeRole.FOLLOWER
                    logger.info(
                        "became_follower",
                        node_id=self.node_id,
                        leader=current_leader,
                    )
                    if self.on_become_follower:
                        await self.on_become_follower()

                self.state.leader_id = current_leader

            except Exception as e:
                logger.exception("election_loop_error", error=str(e))

            # Aguardar próxima iteração
            await asyncio.sleep(self.election_timeout_seconds)

    async def _heartbeat_loop(self) -> None:
        """
        Loop de heartbeat do líder.

        Atualiza timestamp no Redis para indicar que o líder está ativo.
        """
        while self.is_running:
            try:
                if self.state.role == NodeRole.LEADER:
                    await self._send_heartbeat()
            except Exception as e:
                logger.exception("heartbeat_loop_error", error=str(e))

            await asyncio.sleep(self.heartbeat_interval_seconds)

    async def _acquire_leadership(self) -> bool:
        """
        Tentar adquirir liderança usando SET NX (SET if Not Exists).

        Returns:
            True se adquiriu liderança, False caso contrário
        """
        try:
            # Usar SET NX para tentar adquirir lock
            result = await self.redis_client.client.set(
                self.LEADER_LOCK_KEY,
                self.node_id,
                nx=True,  # Only set if key doesn't exist
                ex=self.lease_ttl_seconds,  # Expire in TTL seconds
            )

            if result:
                # Armazenar metadados do líder
                meta = {
                    "node_id": self.node_id,
                    "term": self.state.term + 1,
                    "acquired_at": datetime.now(UTC).isoformat(),
                    "ttl": self.lease_ttl_seconds,
                }
                await self.redis_client.client.hset(self.LEADER_META_KEY, mapping=meta)
                await self.redis_client.client.expire(self.LEADER_META_KEY, self.lease_ttl_seconds)
                self.state.term = meta["term"]
                self.state.role = NodeRole.LEADER

                logger.info(
                    "leadership_acquired",
                    node_id=self.node_id,
                    term=self.state.term,
                )
                return True

            return False

        except Exception as e:
            logger.exception("acquire_leadership_failed", error=str(e))
            return False

    async def _renew_leadership(self) -> bool:
        """
        Renovar lease de liderança.

        Returns:
            True se renovou com sucesso, False se perdeu liderança
        """
        try:
            # Verificar se ainda somos o dono do lock
            current_owner_bytes = await self.redis_client.client.get(self.LEADER_LOCK_KEY)
            current_owner = current_owner_bytes.decode() if current_owner_bytes else None

            if current_owner != self.node_id:
                # Perdemos a liderança
                logger.warning(
                    "leadership_lost",
                    node_id=self.node_id,
                    current_owner=current_owner,
                )
                self.state.role = NodeRole.FOLLOWER
                if self.on_become_follower:
                    await self.on_become_follower()
                return False

            # Renovar lease
            await self.redis_client.client.expire(self.LEADER_LOCK_KEY, self.lease_ttl_seconds)
            await self.redis_client.client.expire(self.LEADER_META_KEY, self.lease_ttl_seconds)

            logger.debug("leadership_renewed", node_id=self.node_id)
            return True

        except Exception as e:
            logger.exception("renew_leadership_failed", error=str(e))
            return False

    async def _resign_leadership(self) -> None:
        """Renunciar à liderança (liberar lock)"""
        try:
            await self.redis_client.client.delete(self.LEADER_LOCK_KEY)
            await self.redis_client.client.delete(self.LEADER_META_KEY)
            await self.redis_client.client.delete(self.LEADER_HEARTBEAT_KEY)

            logger.info("leadership_resigned", node_id=self.node_id)
        except Exception as e:
            logger.exception("resign_leadership_failed", error=str(e))

    async def _send_heartbeat(self) -> None:
        """Enviar heartbeat para indicar líder ativo"""
        try:
            heartbeat = {
                "node_id": self.node_id,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            await self.redis_client.client.hset(self.LEADER_HEARTBEAT_KEY, mapping=heartbeat)
            await self.redis_client.client.expire(self.LEADER_HEARTBEAT_KEY, self.lease_ttl_seconds)
        except Exception as e:
            logger.exception("send_heartbeat_failed", error=str(e))

    async def _get_current_leader(self) -> str | None:
        """
        Obter o ID do líder atual.

        Returns:
            ID do líder ou None se não houver líder
        """
        try:
            leader_id = await self.redis_client.client.get(self.LEADER_LOCK_KEY)
            return leader_id.decode() if leader_id else None
        except Exception as e:
            logger.exception("get_current_leader_failed", error=str(e))
            return None

    async def get_leader_metadata(self) -> dict:
        """
        Obter metadados do líder atual.

        Returns:
            Dicionário com metadados do líder ou dict vazio se não houver líder
        """
        try:
            meta = await self.redis_client.client.hgetall(self.LEADER_META_KEY)
            return {k.decode(): v.decode() for k, v in meta.items()} if meta else {}
        except Exception as e:
            logger.exception("get_leader_metadata_failed", error=str(e))
            return {}

    async def get_leader_heartbeat(self) -> dict:
        """
        Obter heartbeat do líder atual.

        Returns:
            Dicionário com heartbeat ou dict vazio se não houver
        """
        try:
            heartbeat = await self.redis_client.client.hgetall(self.LEADER_HEARTBEAT_KEY)
            return {k.decode(): v.decode() for k, v in heartbeat.items()} if heartbeat else {}
        except Exception as e:
            logger.exception("get_leader_heartbeat_failed", error=str(e))
            return {}

    def is_leader(self) -> bool:
        """Verifica se este nó é o líder"""
        return self.state.role == NodeRole.LEADER

    def get_role(self) -> NodeRole:
        """Obter papel atual deste nó"""
        return self.state.role

    def get_state(self) -> ElectionState:
        """Obter estado completo da eleição"""
        return self.state
