import structlog
import grpc
from typing import Optional

logger = structlog.get_logger()


class AnalystServicer:
    """Servicer gRPC para Analyst Agent"""

    def __init__(
        self,
        mongodb_client,
        redis_client,
        query_engine,
        analytics_engine,
        insight_generator
    ):
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        self.query_engine = query_engine
        self.analytics_engine = analytics_engine
        self.insight_generator = insight_generator

    async def GetInsight(self, request, context):
        """Buscar insight por ID"""
        try:
            logger.info('grpc_get_insight_called', insight_id=request.insight_id)

            # Tentar cache primeiro
            cached_insight = await self.redis_client.get_cached_insight(request.insight_id)
            if cached_insight:
                logger.debug('insight_cache_hit', insight_id=request.insight_id)
                return self._insight_to_proto(cached_insight)

            # Buscar no MongoDB
            insight = await self.mongodb_client.get_insight_by_id(request.insight_id)
            if not insight:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f'Insight {request.insight_id} not found')
                logger.warning('insight_not_found', insight_id=request.insight_id)
                return None

            # Cachear
            await self.redis_client.cache_insight(insight)

            logger.info('grpc_get_insight_success', insight_id=request.insight_id)
            return self._insight_to_proto(insight)

        except Exception as e:
            logger.error('grpc_get_insight_failed', error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return None

    async def QueryInsights(self, request, context):
        """Consultar insights com filtros"""
        try:
            logger.info('grpc_query_insights_called', filters=str(request))

            # Construir filtros
            filters = {}
            if request.insight_type:
                filters['insight_type'] = request.insight_type
            if request.priority:
                filters['priority'] = request.priority
            if request.entity_id:
                filters['entity_id'] = request.entity_id
            if request.start_time > 0:
                filters['start_time'] = request.start_time
            if request.end_time > 0:
                filters['end_time'] = request.end_time

            # Buscar insights
            insights = await self.mongodb_client.query_insights(
                filters=filters,
                limit=request.limit if request.limit > 0 else 100
            )

            logger.info('grpc_query_insights_success', count=len(insights))

            # Converter para proto
            response = QueryInsightsResponse()
            for insight in insights:
                proto_insight = self._insight_to_proto(insight)
                response.insights.append(proto_insight)
            response.total_count = len(insights)

            return response

        except Exception as e:
            logger.error('grpc_query_insights_failed', error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return QueryInsightsResponse(insights=[], total_count=0)

    async def ExecuteAnalysis(self, request, context):
        """Executar análise ad-hoc"""
        try:
            logger.info('grpc_execute_analysis_called', analysis_type=request.analysis_type)

            result = {}

            if request.analysis_type == 'anomaly_detection':
                # Detecção de anomalias
                if not request.metric_values:
                    context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                    context.set_details('metric_values required for anomaly detection')
                    return None

                anomalies = self.analytics_engine.detect_anomalies(
                    metric_name=request.metric_name,
                    values=list(request.metric_values),
                    method=request.method or 'zscore',
                    threshold=request.threshold or 3.0
                )
                result = {'anomalies': anomalies}

            elif request.analysis_type == 'trend_analysis':
                # Análise de tendência
                if not request.metric_values:
                    context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                    context.set_details('metric_values required for trend analysis')
                    return None

                trend = self.analytics_engine.calculate_trend(
                    metric_name=request.metric_name,
                    values=list(request.metric_values)
                )
                result = {'trend': trend}

            elif request.analysis_type == 'correlation':
                # Análise de correlação
                if not request.metric_values or not request.other_metric_values:
                    context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                    context.set_details('Both metric_values and other_metric_values required')
                    return None

                correlation = self.analytics_engine.calculate_correlation(
                    values1=list(request.metric_values),
                    values2=list(request.other_metric_values)
                )
                result = {'correlation': correlation}

            else:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details(f'Unknown analysis_type: {request.analysis_type}')
                return None

            logger.info('grpc_execute_analysis_success', analysis_type=request.analysis_type)

            # Criar resposta
            response = AnalysisResponse()
            response.analysis_type = request.analysis_type
            response.result_json = str(result)
            return response

        except Exception as e:
            logger.error('grpc_execute_analysis_failed', error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return None

    async def GetStatistics(self, request, context):
        """Obter estatísticas de insights"""
        try:
            logger.info('grpc_get_statistics_called')

            # Buscar estatísticas agregadas
            stats = await self.mongodb_client.get_insight_statistics()

            logger.info('grpc_get_statistics_success', stats=stats)

            # Criar resposta
            response = StatisticsResponse()
            response.total_insights = stats.get('total_insights', 0)
            response.insights_by_type = stats.get('by_type', {})
            response.insights_by_priority = stats.get('by_priority', {})
            response.avg_confidence_score = stats.get('avg_confidence', 0.0)
            response.avg_impact_score = stats.get('avg_impact', 0.0)

            return response

        except Exception as e:
            logger.error('grpc_get_statistics_failed', error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return StatisticsResponse()

    async def HealthCheck(self, request, context):
        """Health check"""
        try:
            # Verificar componentes
            mongodb_healthy = await self.mongodb_client.health_check()
            redis_healthy = await self.redis_client.health_check()

            status = 'HEALTHY' if (mongodb_healthy and redis_healthy) else 'UNHEALTHY'

            response = HealthCheckResponse()
            response.status = status
            response.components = {
                'mongodb': 'healthy' if mongodb_healthy else 'unhealthy',
                'redis': 'healthy' if redis_healthy else 'unhealthy'
            }

            logger.info('grpc_health_check', status=status)
            return response

        except Exception as e:
            logger.error('grpc_health_check_failed', error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return HealthCheckResponse(status='UNHEALTHY')

    def _insight_to_proto(self, insight):
        """Converter AnalystInsight para mensagem proto (stub)"""
        # TODO: Implementar conversão quando proto estiver compilado
        # Por enquanto retorna dict
        return insight


# Stub classes para tipos proto (serão substituídas após compilação)
class QueryInsightsResponse:
    def __init__(self, insights=None, total_count=0):
        self.insights = insights or []
        self.total_count = total_count


class AnalysisResponse:
    def __init__(self):
        self.analysis_type = ''
        self.result_json = ''


class StatisticsResponse:
    def __init__(self):
        self.total_insights = 0
        self.insights_by_type = {}
        self.insights_by_priority = {}
        self.avg_confidence_score = 0.0
        self.avg_impact_score = 0.0


class HealthCheckResponse:
    def __init__(self, status='UNKNOWN', components=None):
        self.status = status
        self.components = components or {}
