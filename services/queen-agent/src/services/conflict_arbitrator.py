import structlog
from typing import List, Dict, Any, Optional, Tuple

from neural_hive_domain import UnifiedDomain

from ..config import Settings
from ..models import Conflict, ConflictResolution
from ..clients import Neo4jClient


logger = structlog.get_logger()


class ConflictArbitrator:
    """Arbitragem de conflitos entre domínios"""

    # Pesos de domínio (configuráveis)
    DOMAIN_WEIGHTS = {
        'security': 0.4,
        'compliance': 0.3,
        'business': 0.2,
        'performance': 0.1
    }

    def __init__(self, neo4j_client: Neo4jClient, settings: Settings):
        self.neo4j_client = neo4j_client
        self.settings = settings

    async def detect_conflicts(self, decisions: List[Dict[str, Any]]) -> List[Conflict]:
        """Detectar conflitos entre decisões de múltiplos planos"""
        conflicts = []

        try:
            if len(decisions) < 2:
                return conflicts

            # Comparar pares de decisões
            for i in range(len(decisions)):
                for j in range(i + 1, len(decisions)):
                    conflict = await self._check_conflict_between(decisions[i], decisions[j])
                    if conflict:
                        conflicts.append(conflict)

            logger.info("conflicts_detected", count=len(conflicts))
            return conflicts

        except Exception as e:
            logger.error("detect_conflicts_failed", error=str(e))
            return []

    async def _check_conflict_between(self, decision1: Dict[str, Any], decision2: Dict[str, Any]) -> Conflict | None:
        """Verificar se há conflito entre duas decisões"""
        try:
            # Determinar domínios
            domain1 = decision1.get('specialist_type', 'unknown')
            domain2 = decision2.get('specialist_type', 'unknown')

            # Mapear para UnifiedDomain
            unified_domains = self._map_to_unified_domains(domain1, domain2)
            if not unified_domains:
                return None

            left_domain, right_domain = unified_domains

            # Criar conflito
            conflict = Conflict(
                left_domain=left_domain,
                right_domain=right_domain,
                entities=[decision1, decision2]
            )

            # Calcular severidade
            conflict.calculate_severity()

            # Se severidade é significativa, retornar conflito
            if conflict.severity > 0.3:
                return conflict

            return None

        except Exception as e:
            logger.error("check_conflict_failed", error=str(e))
            return None

    def _map_to_unified_domains(self, domain1: str, domain2: str) -> Optional[Tuple[UnifiedDomain, UnifiedDomain]]:
        """Mapear par de domínios para UnifiedDomain"""
        # Mapping from specialist types to UnifiedDomain
        domain_mapping = {
            'security': UnifiedDomain.SECURITY,
            'performance': UnifiedDomain.OPERATIONAL,
            'business': UnifiedDomain.BUSINESS,
            'technical': UnifiedDomain.TECHNICAL,
            'engineering': UnifiedDomain.TECHNICAL,
            'infrastructure': UnifiedDomain.INFRASTRUCTURE,
            'compliance': UnifiedDomain.COMPLIANCE,
            'behavior': UnifiedDomain.BEHAVIOR,
            'operational': UnifiedDomain.OPERATIONAL,
        }

        d1_lower = domain1.lower()
        d2_lower = domain2.lower()

        unified1 = domain_mapping.get(d1_lower)
        unified2 = domain_mapping.get(d2_lower)

        # Only return if both domains are recognized and different
        if unified1 and unified2 and unified1 != unified2:
            return (unified1, unified2)

        return None

    async def resolve_conflict(self, conflict: Conflict) -> ConflictResolution:
        """Resolver um conflito específico"""
        try:
            # Consultar histórico de resoluções similares
            historical = await self.neo4j_client.get_domain_conflicts(
                [conflict.left_domain.value, conflict.right_domain.value]
            )

            # Sugerir estratégia
            strategy = conflict.suggest_resolution()

            # Aplicar estratégia
            if strategy == 'PRIORITIZE_SECURITY':
                chosen_entity = self._choose_entity_by_domain(conflict.entities, 'security')
                rationale = 'Segurança priorizada devido à severidade do conflito'
                confidence = 0.9

            elif strategy == 'PRIORITIZE_BUSINESS':
                chosen_entity = self._choose_entity_by_domain(conflict.entities, 'business')
                rationale = 'Objetivos de negócio priorizados devido à baixa severidade'
                confidence = 0.8

            elif strategy == 'PRIORITIZE_COMPLIANCE':
                chosen_entity = self._choose_entity_by_domain(conflict.entities, 'compliance')
                rationale = 'Compliance priorizado por requisitos regulatórios'
                confidence = 0.9

            elif strategy == 'PRIORITIZE_RELIABILITY':
                chosen_entity = self._choose_entity_by_domain(conflict.entities, 'infrastructure')
                rationale = 'Confiabilidade priorizada para estabilidade do sistema'
                confidence = 0.85

            elif strategy == 'COMPROMISE':
                chosen_entity = None
                rationale = 'Solução de compromisso necessária - implementar com controles adicionais'
                confidence = 0.7

            else:  # ESCALATE_HUMAN
                chosen_entity = None
                rationale = 'Conflito complexo requer aprovação humana'
                confidence = 0.5

            resolution = ConflictResolution(
                conflict_id=conflict.conflict_id,
                resolution_strategy=strategy,
                chosen_entity=chosen_entity,
                rationale=rationale,
                confidence=confidence
            )

            logger.info(
                "conflict_resolved",
                conflict_id=conflict.conflict_id,
                strategy=strategy,
                confidence=confidence
            )

            return resolution

        except Exception as e:
            logger.error("resolve_conflict_failed", error=str(e))
            return ConflictResolution(
                conflict_id=conflict.conflict_id,
                resolution_strategy='ESCALATE_HUMAN',
                rationale=f'Erro ao resolver conflito: {str(e)}',
                confidence=0.0
            )

    def _choose_entity_by_domain(self, entities: List[Dict[str, Any]], preferred_domain: str) -> str | None:
        """Escolher entidade baseado em domínio preferido"""
        for entity in entities:
            if entity.get('specialist_type', '').lower() == preferred_domain.lower():
                return entity.get('plan_id') or entity.get('decision_id')

        return None
