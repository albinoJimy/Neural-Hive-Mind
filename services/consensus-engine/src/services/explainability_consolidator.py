import uuid
import asyncio
from typing import List, Dict, Any, Tuple
from datetime import datetime
from collections import Counter
import structlog
from src.models.consolidated_decision import ConsensusMethod

logger = structlog.get_logger()


class ExplainabilityConsolidator:
    '''Consolidador de explicabilidade para decisões de consenso'''

    def __init__(self, mongodb_client):
        self.mongodb = mongodb_client

    def generate(
        self,
        opinions: List[Dict[str, Any]],
        aggregated_confidence: float,
        aggregated_risk: float,
        divergence: float,
        final_decision: str,
        consensus_method: ConsensusMethod,
        violations: List[str]
    ) -> Tuple[str, str]:
        '''Gera token e resumo de explicabilidade consolidada'''
        # Gerar token único
        explainability_token = str(uuid.uuid4())

        # Gerar resumo narrativo
        reasoning_summary = self._generate_reasoning_summary(
            opinions,
            aggregated_confidence,
            aggregated_risk,
            divergence,
            final_decision,
            consensus_method,
            violations
        )

        # Gerar explicação detalhada
        detailed_explanation = self._generate_detailed_explanation(
            opinions,
            aggregated_confidence,
            aggregated_risk,
            divergence,
            final_decision,
            consensus_method,
            violations
        )

        # Persistir explicação
        asyncio.create_task(
            self._persist_explanation(explainability_token, detailed_explanation)
        )

        return explainability_token, reasoning_summary

    def _generate_reasoning_summary(
        self,
        opinions: List[Dict[str, Any]],
        aggregated_confidence: float,
        aggregated_risk: float,
        divergence: float,
        final_decision: str,
        consensus_method: ConsensusMethod,
        violations: List[str]
    ) -> str:
        '''Gera resumo narrativo da decisão'''
        # Contar recomendações
        recommendations = [op['opinion']['recommendation'] for op in opinions]
        rec_counts = Counter(recommendations)

        summary = f'Decisão de consenso: {final_decision}. '
        summary += f'Método: {consensus_method.value}. '
        summary += f'Avaliado por {len(opinions)} especialistas. '
        summary += f'Confiança agregada: {aggregated_confidence:.2f}, '
        summary += f'Risco agregado: {aggregated_risk:.2f}, '
        summary += f'Divergência: {divergence:.2f}. '

        # Distribuição de recomendações
        summary += f'Recomendações: '
        for rec, count in rec_counts.items():
            summary += f'{rec}={count}, '

        # Violações de compliance
        if violations:
            summary += f'Violações de compliance: {len(violations)}. '

        return summary

    def _generate_detailed_explanation(
        self,
        opinions: List[Dict[str, Any]],
        aggregated_confidence: float,
        aggregated_risk: float,
        divergence: float,
        final_decision: str,
        consensus_method: ConsensusMethod,
        violations: List[str]
    ) -> Dict[str, Any]:
        '''Gera explicação detalhada para auditoria'''
        return {
            'consensus_process': {
                'method': consensus_method.value,
                'num_specialists': len(opinions),
                'aggregation': {
                    'confidence': aggregated_confidence,
                    'risk': aggregated_risk,
                    'divergence': divergence
                }
            },
            'specialist_opinions': [
                {
                    'specialist_type': op['specialist_type'],
                    'opinion_id': op['opinion_id'],
                    'confidence': op['opinion']['confidence_score'],
                    'risk': op['opinion']['risk_score'],
                    'recommendation': op['opinion']['recommendation'],
                    'reasoning_summary': op['opinion']['reasoning_summary'],
                    'explainability_token': op['opinion']['explainability_token']
                }
                for op in opinions
            ],
            'final_decision': {
                'decision': final_decision,
                'rationale': self._generate_decision_rationale(
                    final_decision,
                    aggregated_confidence,
                    aggregated_risk,
                    divergence
                )
            },
            'compliance': {
                'is_compliant': len(violations) == 0,
                'violations': violations
            },
            'timestamp': datetime.utcnow().isoformat(),
            'version': '1.0.0'
        }

    def _generate_decision_rationale(
        self,
        decision: str,
        confidence: float,
        risk: float,
        divergence: float
    ) -> str:
        '''Gera justificativa da decisão final'''
        if decision == 'approve':
            return f'Plano aprovado com confiança {confidence:.2f} e risco {risk:.2f}. Divergência aceitável ({divergence:.2f}).'
        elif decision == 'reject':
            return f'Plano rejeitado devido a risco elevado ({risk:.2f}) ou baixa confiança ({confidence:.2f}).'
        elif decision == 'review_required':
            return f'Revisão humana necessária devido a divergência ({divergence:.2f}) ou violações de compliance.'
        else:  # conditional
            return f'Aprovação condicional com confiança {confidence:.2f} e risco {risk:.2f}. Requer monitoramento.'

    async def _persist_explanation(self, token: str, explanation: Dict):
        '''Persiste explicação detalhada no MongoDB'''
        try:
            collection = self.mongodb.db['consensus_explainability']
            await collection.insert_one({
                'token': token,
                'explanation': explanation,
                'timestamp': datetime.utcnow()
            })
            logger.info('Explicação consolidada persistida', token=token)
        except Exception as e:
            logger.error('Erro persistindo explicação', token=token, error=str(e))
