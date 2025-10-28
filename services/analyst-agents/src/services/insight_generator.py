import structlog
import uuid
from typing import Dict, List
from datetime import datetime
from ..models.insight import AnalystInsight, InsightType, Priority, Recommendation, RelatedEntity, TimeWindow

logger = structlog.get_logger()


class InsightGenerator:
    def __init__(self, min_confidence: float = 0.7):
        self.min_confidence = min_confidence

    async def generate_insight(self, data: Dict, insight_type: InsightType, trace_id: str = '', span_id: str = '') -> AnalystInsight:
        """Gerar insight a partir de dados"""
        try:
            # Calcular scores
            confidence_score = self.calculate_confidence_score(data)
            impact_score = self.calculate_impact_score(data)

            # Determinar prioridade
            priority = self._determine_priority(confidence_score, impact_score)

            # Gerar recomendações
            recommendations = self.generate_recommendations(data, insight_type)

            # Encontrar entidades relacionadas
            related_entities = self._find_related_entities(data)

            # Criar insight
            insight = AnalystInsight(
                insight_id=str(uuid.uuid4()),
                version='1.0.0',
                correlation_id=data.get('correlation_id', str(uuid.uuid4())),
                trace_id=trace_id or str(uuid.uuid4()),
                span_id=span_id or str(uuid.uuid4()),
                insight_type=insight_type,
                priority=priority,
                title=data.get('title', 'Insight sem título'),
                summary=data.get('summary', ''),
                detailed_analysis=data.get('detailed_analysis', ''),
                data_sources=data.get('data_sources', []),
                metrics=data.get('metrics', {}),
                confidence_score=confidence_score,
                impact_score=impact_score,
                recommendations=recommendations,
                related_entities=related_entities,
                time_window=TimeWindow(
                    start_timestamp=data.get('time_window', {}).get('start', 0),
                    end_timestamp=data.get('time_window', {}).get('end', 0)
                ),
                tags=data.get('tags', []),
                metadata=data.get('metadata', {})
            )

            logger.info('insight_generated', insight_id=insight.insight_id, type=insight_type, priority=priority)
            return insight

        except Exception as e:
            logger.error('generate_insight_failed', error=str(e))
            raise

    async def generate_anomaly_insight(self, anomaly: Dict) -> AnalystInsight:
        """Gerar insight de anomalia"""
        data = {
            'title': f'Anomalia detectada em {anomaly.get("metric_name")}',
            'summary': f'Valor anômalo de {anomaly.get("value")} detectado (Z-score: {anomaly.get("zscore", 0):.2f})',
            'detailed_analysis': f'Anomalia detectada usando método {anomaly.get("method", "zscore")}. '
                                 f'Valor observado: {anomaly.get("value")}, desvio: {anomaly.get("zscore", 0):.2f} sigmas.',
            'data_sources': ['telemetry', 'analytics_engine'],
            'metrics': {'anomaly_value': anomaly.get('value', 0), 'zscore': anomaly.get('zscore', 0)},
            'correlation_id': anomaly.get('correlation_id', ''),
            'time_window': anomaly.get('time_window', {}),
            'tags': ['anomaly', anomaly.get('metric_name', '')]
        }

        return await self.generate_insight(data, InsightType.ANOMALY)

    def calculate_confidence_score(self, data: Dict) -> float:
        """Calcular score de confiança"""
        try:
            # Baseado em: qualidade dos dados, tamanho da amostra, consistência entre fontes
            data_quality = data.get('data_quality', 0.8)
            sample_size = min(data.get('sample_size', 100) / 1000, 1.0)
            consistency = data.get('consistency_score', 0.9)

            confidence = (data_quality * 0.4) + (sample_size * 0.3) + (consistency * 0.3)
            return max(0.0, min(1.0, confidence))

        except Exception as e:
            logger.error('calculate_confidence_failed', error=str(e))
            return 0.5

    def calculate_impact_score(self, data: Dict) -> float:
        """Calcular score de impacto"""
        try:
            # Baseado em: entidades afetadas, severidade, urgência
            affected_entities = min(data.get('affected_entities', 10) / 100, 1.0)
            severity = data.get('severity', 0.5)
            urgency = data.get('urgency', 0.5)

            impact = (affected_entities * 0.4) + (severity * 0.4) + (urgency * 0.2)
            return max(0.0, min(1.0, impact))

        except Exception as e:
            logger.error('calculate_impact_failed', error=str(e))
            return 0.5

    def generate_recommendations(self, data: Dict, insight_type: InsightType) -> List[Recommendation]:
        """Gerar recomendações acionáveis"""
        recommendations = []

        if insight_type == InsightType.ANOMALY:
            recommendations.append(Recommendation(
                action='Investigar causa raiz da anomalia',
                priority='HIGH',
                estimated_impact=0.8
            ))
            recommendations.append(Recommendation(
                action='Verificar logs e traces relacionados',
                priority='MEDIUM',
                estimated_impact=0.6
            ))

        elif insight_type == InsightType.OPERATIONAL:
            recommendations.append(Recommendation(
                action='Otimizar recursos alocados',
                priority='MEDIUM',
                estimated_impact=0.7
            ))

        return recommendations

    def _determine_priority(self, confidence: float, impact: float) -> Priority:
        """Determinar prioridade baseada em confidence e impact"""
        if impact > 0.8 and confidence > 0.9:
            return Priority.CRITICAL
        elif impact > 0.6 and confidence > 0.8:
            return Priority.HIGH
        elif impact > 0.4 and confidence > 0.7:
            return Priority.MEDIUM
        else:
            return Priority.LOW

    def _find_related_entities(self, data: Dict) -> List[RelatedEntity]:
        """Encontrar entidades relacionadas"""
        entities = []

        if 'intent_id' in data:
            entities.append(RelatedEntity(
                entity_type='intent',
                entity_id=data['intent_id'],
                relationship='source'
            ))

        if 'plan_id' in data:
            entities.append(RelatedEntity(
                entity_type='plan',
                entity_id=data['plan_id'],
                relationship='derived_from'
            ))

        return entities
