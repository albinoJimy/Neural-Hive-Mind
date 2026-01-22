from typing import Dict, Optional, Union
from datetime import datetime, timedelta
import json
import structlog

from neural_hive_domain import DomainMapper, UnifiedDomain

from src.models.pheromone_signal import PheromoneSignal, PheromoneType

logger = structlog.get_logger()


class PheromoneClient:
    '''Cliente Redis para gerenciar feromônios digitais'''

    def __init__(self, redis_client, config):
        self.redis = redis_client
        self.config = config

    async def publish_pheromone(
        self,
        specialist_type: str,
        domain: Union[str, UnifiedDomain],
        pheromone_type: PheromoneType,
        strength: float,
        plan_id: str,
        intent_id: str,
        decision_id: Optional[str] = None
    ) -> str:
        '''Publica feromônio no Redis usando chave padronizada via DomainMapper'''
        # Criar PheromoneSignal
        signal = PheromoneSignal(
            specialist_type=specialist_type,
            domain=domain,
            pheromone_type=pheromone_type,
            strength=strength,
            plan_id=plan_id,
            intent_id=intent_id,
            decision_id=decision_id,
            expires_at=datetime.utcnow() + timedelta(seconds=self.config.pheromone_ttl),
            decay_rate=self.config.pheromone_decay_rate
        )

        # Salvar no Redis com TTL (serializar para JSON)
        # Usar model_dump(mode='json') para serialização correta de enums e datetime
        key = signal.get_redis_key()
        signal_json = json.dumps(signal.model_dump(mode='json'))
        await self.redis.set(
            key,
            signal_json,
            ex=self.config.pheromone_ttl
        )

        # Adicionar a lista de feromônios ativos
        list_key = f'pheromones:active:{specialist_type}:{domain}'
        await self.redis.lpush(list_key, signal.signal_id)
        await self.redis.expire(list_key, self.config.pheromone_ttl)

        logger.info(
            'Feromônio publicado',
            specialist_type=specialist_type,
            domain=domain,
            pheromone_type=pheromone_type.value,
            strength=strength,
            signal_id=signal.signal_id
        )

        return signal.signal_id

    async def get_pheromone_strength(
        self,
        specialist_type: str,
        domain: Union[str, UnifiedDomain],
        pheromone_type: PheromoneType
    ) -> float:
        '''Consulta força atual de feromônio (com decay) usando chave padronizada.

        Filtra por specialist_type usando a lista de feromônios ativos para
        garantir que apenas sinais do especialista correto sejam agregados.
        '''
        # Normalizar domain para UnifiedDomain se necessário
        if isinstance(domain, str):
            normalized_domain = DomainMapper.normalize(domain, 'intent_envelope')
        else:
            normalized_domain = domain

        # Usar a lista de feromônios ativos para filtrar por specialist_type
        # Esta lista é mantida em publish_pheromone() com o formato:
        # pheromones:active:{specialist_type}:{domain}
        list_key = f'pheromones:active:{specialist_type}:{normalized_domain.value}'

        # Obter signal_ids do especialista específico
        signal_ids = await self.redis.lrange(list_key, 0, -1)

        if not signal_ids:
            return 0.0

        # Agregar força apenas dos feromônios do especialista específico
        total_strength = 0.0
        count = 0
        for signal_id in signal_ids:
            # Decodificar signal_id se necessário (Redis pode retornar bytes)
            if isinstance(signal_id, bytes):
                signal_id = signal_id.decode('utf-8')

            # Construir a chave Redis usando DomainMapper
            key = DomainMapper.to_pheromone_key(
                domain=normalized_domain,
                layer='consensus',
                pheromone_type=pheromone_type.value,
                id=signal_id
            )

            signal_json = await self.redis.get(key)
            if signal_json:
                signal_data = json.loads(signal_json)
                signal = PheromoneSignal(**signal_data)
                # Verificar se o pheromone_type corresponde ao solicitado
                if signal.pheromone_type == pheromone_type:
                    total_strength += signal.calculate_current_strength()
                    count += 1

        return total_strength / count if count > 0 else 0.0

    async def get_aggregated_pheromone(
        self,
        specialist_type: str,
        domain: Union[str, UnifiedDomain]
    ) -> Dict[str, float]:
        '''Agrega feromônios de todos os tipos para um especialista + domínio'''
        success_strength = await self.get_pheromone_strength(
            specialist_type, domain, PheromoneType.SUCCESS
        )
        failure_strength = await self.get_pheromone_strength(
            specialist_type, domain, PheromoneType.FAILURE
        )
        warning_strength = await self.get_pheromone_strength(
            specialist_type, domain, PheromoneType.WARNING
        )

        # Calcular força líquida (success - failure - warning*0.5)
        net_strength = success_strength - failure_strength - (warning_strength * 0.5)
        net_strength = max(0.0, min(1.0, net_strength))  # Normalizar

        return {
            'success': success_strength,
            'failure': failure_strength,
            'warning': warning_strength,
            'net_strength': net_strength
        }

    async def calculate_dynamic_weight(
        self,
        specialist_type: str,
        domain: Union[str, UnifiedDomain],
        base_weight: float = 0.2
    ) -> float:
        '''Calcula peso dinâmico baseado em feromônios'''
        pheromones = await self.get_aggregated_pheromone(specialist_type, domain)

        # Ajustar peso base com feromônios
        # net_strength positivo aumenta peso, negativo diminui
        adjusted_weight = base_weight * (1.0 + pheromones['net_strength'])

        # Normalizar para [0.05, 0.4] (evitar pesos extremos)
        adjusted_weight = max(0.05, min(0.4, adjusted_weight))

        logger.debug(
            'Peso dinâmico calculado',
            specialist_type=specialist_type,
            domain=domain,
            base_weight=base_weight,
            net_strength=pheromones['net_strength'],
            adjusted_weight=adjusted_weight
        )

        return adjusted_weight

    async def cleanup_expired_pheromones(self):
        '''Limpa feromônios expirados (executar periodicamente)'''
        # Redis TTL já cuida da expiração automática
        pass
