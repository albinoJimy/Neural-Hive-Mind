"""Service Registry client for Analyst Agents - uses canonical client from neural_hive_integration"""
import structlog
from typing import List, Dict, Optional
from datetime import datetime

from neural_hive_integration.clients import ServiceRegistryClient as CanonicalClient
from neural_hive_integration.clients import AgentInfo, HealthStatus

logger = structlog.get_logger()


class ServiceRegistryClient:
    """Cliente para Service Registry - registro dinamico de agentes.

    Utiliza o cliente canonico da biblioteca neural_hive_integration
    para garantir consistencia com outros servicos.
    """

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._client: Optional[CanonicalClient] = None
        self.agent_id: Optional[str] = None

    async def initialize(self):
        """Inicializar cliente gRPC"""
        try:
            self._client = CanonicalClient(host=self.host, port=self.port)
            logger.info('service_registry_client_initialized', host=self.host, port=self.port)
        except Exception as e:
            logger.error('service_registry_client_initialization_failed', error=str(e))
            raise

    async def close(self):
        """Fechar conexao gRPC"""
        if self.agent_id and self._client:
            await self.deregister_agent()

        if self._client:
            await self._client.close()
        logger.info('service_registry_client_closed')

    async def register_agent(self, agent_info: Dict) -> Optional[str]:
        """Registrar Analyst Agent com capacidades"""
        try:
            if not self._client:
                logger.warning('service_registry_channel_not_initialized')
                return None

            agent = AgentInfo(
                agent_id='',  # Sera gerado pelo servidor
                agent_type='analyst',
                capabilities=[
                    'analytics',
                    'insights_generation',
                    'graph_queries',
                    'causal_analysis',
                    'anomaly_detection',
                    'trend_analysis'
                ],
                endpoint=f"{agent_info.get('host', 'localhost')}:{agent_info.get('port', 8000)}",
                metadata={
                    'version': agent_info.get('version', '1.0.0'),
                    'namespace': agent_info.get('namespace', 'default'),
                    'cluster': agent_info.get('cluster', 'default')
                }
            )

            success = await self._client.register_agent(agent)
            if success:
                self.agent_id = agent.agent_id
                logger.info('agent_registered', agent_id=self.agent_id)
                return self.agent_id

            logger.warning('agent_registration_failed')
            return None

        except Exception as e:
            logger.error('register_agent_failed', error=str(e))
            return None

    async def update_health_status(self, status: str) -> bool:
        """Atualizar status de saude"""
        try:
            if not self._client or not self.agent_id:
                return False

            health = HealthStatus(
                status=status,
                last_heartbeat=datetime.utcnow().isoformat(),
                metrics={
                    'success_rate': 0.95,
                    'avg_duration_ms': 150.0,
                    'total_executions': 100.0,
                    'failed_executions': 5.0
                }
            )

            await self._client.update_health(self.agent_id, health)
            logger.debug('health_status_updated', status=status, agent_id=self.agent_id)
            return True

        except Exception as e:
            logger.error('update_health_status_failed', error=str(e))
            return False

    async def deregister_agent(self) -> bool:
        """Desregistrar ao shutdown"""
        try:
            if not self._client or not self.agent_id:
                return False

            await self._client.deregister_agent(self.agent_id)
            logger.info('agent_deregistered', agent_id=self.agent_id)
            self.agent_id = None
            return True

        except Exception as e:
            logger.error('deregister_agent_failed', error=str(e))
            return False

    async def get_available_agents(self, agent_type: str) -> List[Dict]:
        """Obter lista de agentes disponiveis"""
        try:
            if not self._client:
                return []

            agents = await self._client.discover_agents(
                capabilities=[agent_type],
                filters={'status': 'healthy'}
            )

            result = []
            for agent in agents:
                result.append({
                    'agent_id': agent.agent_id,
                    'agent_type': agent.agent_type,
                    'capabilities': agent.capabilities,
                    'endpoint': agent.endpoint,
                    'metadata': agent.metadata
                })

            logger.debug('agents_discovered', agent_type=agent_type, count=len(result))
            return result

        except Exception as e:
            logger.error('get_available_agents_failed', error=str(e))
            return []

    async def heartbeat(self) -> bool:
        """Enviar heartbeat periodico"""
        return await self.update_health_status('healthy')
