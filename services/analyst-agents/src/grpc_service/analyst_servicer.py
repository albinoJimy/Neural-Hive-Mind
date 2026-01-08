import structlog
import grpc
import uuid
from typing import Optional, Dict, List, Any

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from neural_hive_observability.context import set_baggage
from neural_hive_observability.grpc_instrumentation import extract_grpc_context

from ..proto import analyst_agent_pb2, analyst_agent_pb2_grpc
from ..models.insight import InsightType

logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)


class AnalystServicer(analyst_agent_pb2_grpc.AnalystAgentServiceServicer):
    """Servicer gRPC para Analyst Agent"""

    def __init__(
        self,
        mongodb_client,
        redis_client,
        query_engine,
        analytics_engine,
        insight_generator,
        neo4j_client=None
    ):
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        self.query_engine = query_engine
        self.analytics_engine = analytics_engine
        self.insight_generator = insight_generator
        self.neo4j_client = neo4j_client

    async def GetInsight(self, request, context):
        """Buscar insight por ID"""
        extract_grpc_context(context)
        if request.insight_id:
            set_baggage('insight_id', request.insight_id)

        with tracer.start_as_current_span('get_insight') as span:
            try:
                span.set_attribute('insight_id', request.insight_id)
                logger.info('grpc_get_insight_called', insight_id=request.insight_id)

                # Tentar cache primeiro
                cached_insight = await self.redis_client.get_cached_insight(request.insight_id)
                if cached_insight:
                    span.set_attribute('cache_hit', True)
                    logger.debug('insight_cache_hit', insight_id=request.insight_id)
                    proto_insight = self._insight_dict_to_proto(cached_insight)
                    span.set_status(Status(StatusCode.OK))
                    return analyst_agent_pb2.GetInsightResponse(
                        insight=proto_insight,
                        found=True
                    )

                span.set_attribute('cache_hit', False)

                # Buscar no MongoDB
                insight = await self.mongodb_client.get_insight_by_id(request.insight_id)
                if not insight:
                    span.set_attribute('found', False)
                    logger.warning('insight_not_found', insight_id=request.insight_id)
                    span.set_status(Status(StatusCode.OK))
                    return analyst_agent_pb2.GetInsightResponse(
                        found=False
                    )

                # Cachear para proximas consultas
                from ..models.insight import AnalystInsight
                try:
                    insight_model = AnalystInsight(**insight)
                    await self.redis_client.cache_insight(insight_model)
                except Exception as cache_err:
                    logger.warning('cache_insight_failed', error=str(cache_err))

                proto_insight = self._insight_dict_to_proto(insight)
                span.set_attribute('found', True)
                span.set_status(Status(StatusCode.OK))

                logger.info('grpc_get_insight_success', insight_id=request.insight_id)
                return analyst_agent_pb2.GetInsightResponse(
                    insight=proto_insight,
                    found=True
                )

            except Exception as e:
                logger.error('grpc_get_insight_failed', error=str(e))
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(str(e))
                return analyst_agent_pb2.GetInsightResponse(found=False)

    async def QueryInsights(self, request, context):
        """Consultar insights com filtros e enriquecimento opcional via Neo4j"""
        extract_grpc_context(context)

        with tracer.start_as_current_span('query_insights') as span:
            try:
                logger.info('grpc_query_insights_called', filters=str(request))

                # Construir filtros MongoDB
                filters = {}
                if request.insight_type:
                    filters['insight_type'] = request.insight_type
                    span.set_attribute('filter.insight_type', request.insight_type)
                if request.priority:
                    filters['priority'] = request.priority
                    span.set_attribute('filter.priority', request.priority)
                if request.start_timestamp > 0 or request.end_timestamp > 0:
                    filters['created_at'] = {}
                    if request.start_timestamp > 0:
                        filters['created_at']['$gte'] = request.start_timestamp
                        span.set_attribute('filter.start_timestamp', request.start_timestamp)
                    if request.end_timestamp > 0:
                        filters['created_at']['$lte'] = request.end_timestamp
                        span.set_attribute('filter.end_timestamp', request.end_timestamp)

                limit = request.limit if request.limit > 0 else 100
                skip = request.offset if request.offset > 0 else 0

                span.set_attribute('limit', limit)
                span.set_attribute('offset', skip)
                span.set_attribute('use_graph_enrichment', request.use_graph_enrichment)

                # Se usar enriquecimento via Neo4j e tiver entidade relacionada
                if request.use_graph_enrichment and request.related_entity_id and self.neo4j_client:
                    span.set_attribute('graph_enrichment', True)
                    # Buscar insights relacionados via grafo Neo4j
                    related_insight_ids = await self._get_related_insights_from_neo4j(
                        request.related_entity_id
                    )
                    if related_insight_ids:
                        filters['insight_id'] = {'$in': related_insight_ids}
                        logger.info('neo4j_graph_enrichment_applied', related_count=len(related_insight_ids))

                # Buscar insights
                insights = await self.mongodb_client.query_insights(
                    filters=filters,
                    limit=limit,
                    skip=skip
                )

                # Converter para proto
                proto_insights = [self._insight_dict_to_proto(i) for i in insights]
                total_count = len(proto_insights)

                span.set_attribute('results_count', total_count)
                span.set_status(Status(StatusCode.OK))

                logger.info('grpc_query_insights_success', count=total_count)

                return analyst_agent_pb2.QueryInsightsResponse(
                    insights=proto_insights,
                    total_count=total_count
                )

            except Exception as e:
                logger.error('grpc_query_insights_failed', error=str(e))
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(str(e))
                return analyst_agent_pb2.QueryInsightsResponse(insights=[], total_count=0)

    async def _get_related_insights_from_neo4j(self, entity_id: str) -> List[str]:
        """Buscar IDs de insights relacionados a uma entidade via Neo4j"""
        try:
            query = """
            MATCH (e:Entity {entity_id: $entity_id})<-[:RELATED_TO]-(i:Insight)
            RETURN i.insight_id as insight_id
            LIMIT 100
            """
            results = await self.neo4j_client.query_patterns(query, {'entity_id': entity_id})
            return [r['insight_id'] for r in results if r.get('insight_id')]
        except Exception as e:
            logger.warning('neo4j_related_insights_query_failed', error=str(e))
            return []

    async def ExecuteAnalysis(self, request, context):
        """Executar analise ad-hoc"""
        extract_grpc_context(context)

        with tracer.start_as_current_span('execute_analysis') as span:
            try:
                analysis_type = request.analysis_type
                parameters = dict(request.parameters)
                analysis_id = str(uuid.uuid4())

                span.set_attribute('analysis_type', analysis_type)
                span.set_attribute('analysis_id', analysis_id)
                logger.info('grpc_execute_analysis_called', analysis_type=analysis_type, analysis_id=analysis_id)

                results: Dict[str, float] = {}
                confidence = 0.85

                if analysis_type == 'anomaly_detection':
                    metric_name = parameters.get('metric_name', '')
                    threshold = float(parameters.get('threshold', '3.0'))

                    if not metric_name:
                        context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                        context.set_details('metric_name required for anomaly detection')
                        span.set_status(Status(StatusCode.ERROR, 'missing metric_name'))
                        return analyst_agent_pb2.ExecuteAnalysisResponse()

                    # Buscar dados de metricas via query_engine se disponivel
                    try:
                        if hasattr(self.query_engine, 'get_metric_timeseries'):
                            data = await self.query_engine.get_metric_timeseries(metric_name)
                            if data:
                                anomalies = self.analytics_engine.detect_anomalies(
                                    metric_name=metric_name,
                                    values=data,
                                    threshold=threshold
                                )
                                results = {
                                    'anomaly_count': float(len(anomalies)),
                                    'threshold': threshold
                                }
                                confidence = 0.85
                            else:
                                results = {'anomaly_count': 0.0}
                                confidence = 0.5
                        else:
                            results = {'anomaly_count': 0.0, 'status': 1.0}
                            confidence = 0.7
                    except Exception as query_err:
                        logger.warning('query_engine_error', error=str(query_err))
                        results = {'error': 1.0}
                        confidence = 0.3

                elif analysis_type == 'trend_analysis':
                    metric_name = parameters.get('metric_name', '')

                    if not metric_name:
                        context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                        context.set_details('metric_name required for trend analysis')
                        span.set_status(Status(StatusCode.ERROR, 'missing metric_name'))
                        return analyst_agent_pb2.ExecuteAnalysisResponse()

                    try:
                        if hasattr(self.query_engine, 'get_metric_timeseries'):
                            data = await self.query_engine.get_metric_timeseries(metric_name)
                            if data:
                                trend = self.analytics_engine.calculate_trend(
                                    metric_name=metric_name,
                                    values=data
                                )
                                results = {
                                    'slope': trend.get('slope', 0.0),
                                    'direction': float(1 if trend.get('direction') == 'up' else -1 if trend.get('direction') == 'down' else 0)
                                }
                                confidence = trend.get('confidence', 0.8)
                            else:
                                results = {'slope': 0.0, 'direction': 0.0}
                                confidence = 0.5
                        else:
                            results = {'slope': 0.0, 'direction': 0.0}
                            confidence = 0.7
                    except Exception as query_err:
                        logger.warning('trend_analysis_error', error=str(query_err))
                        results = {'error': 1.0}
                        confidence = 0.3

                elif analysis_type == 'correlation':
                    metric1 = parameters.get('metric1', '')
                    metric2 = parameters.get('metric2', '')

                    if not metric1 or not metric2:
                        context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                        context.set_details('metric1 and metric2 required for correlation analysis')
                        span.set_status(Status(StatusCode.ERROR, 'missing metrics'))
                        return analyst_agent_pb2.ExecuteAnalysisResponse()

                    try:
                        if hasattr(self.query_engine, 'get_metric_timeseries'):
                            data1 = await self.query_engine.get_metric_timeseries(metric1)
                            data2 = await self.query_engine.get_metric_timeseries(metric2)
                            if data1 and data2:
                                correlation = self.analytics_engine.calculate_correlation(
                                    values1=data1,
                                    values2=data2
                                )
                                results = {'correlation': correlation}
                                confidence = 0.9
                            else:
                                results = {'correlation': 0.0}
                                confidence = 0.5
                        else:
                            results = {'correlation': 0.0}
                            confidence = 0.7
                    except Exception as query_err:
                        logger.warning('correlation_analysis_error', error=str(query_err))
                        results = {'error': 1.0}
                        confidence = 0.3

                else:
                    context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                    context.set_details(f'Unknown analysis_type: {analysis_type}')
                    span.set_status(Status(StatusCode.ERROR, f'unknown analysis_type: {analysis_type}'))
                    return analyst_agent_pb2.ExecuteAnalysisResponse()

                span.set_attribute('confidence', confidence)
                span.set_status(Status(StatusCode.OK))

                logger.info('grpc_execute_analysis_success', analysis_type=analysis_type, analysis_id=analysis_id)

                return analyst_agent_pb2.ExecuteAnalysisResponse(
                    analysis_id=analysis_id,
                    results=results,
                    confidence=confidence
                )

            except Exception as e:
                logger.error('grpc_execute_analysis_failed', error=str(e))
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(str(e))
                return analyst_agent_pb2.ExecuteAnalysisResponse()

    async def GetStatistics(self, request, context):
        """Obter estatisticas de insights"""
        extract_grpc_context(context)

        with tracer.start_as_current_span('get_statistics') as span:
            try:
                logger.info('grpc_get_statistics_called')

                # Construir filtros de tempo
                time_filter = {}
                if request.start_timestamp > 0 or request.end_timestamp > 0:
                    time_filter['created_at'] = {}
                    if request.start_timestamp > 0:
                        time_filter['created_at']['$gte'] = request.start_timestamp
                        span.set_attribute('start_timestamp', request.start_timestamp)
                    if request.end_timestamp > 0:
                        time_filter['created_at']['$lte'] = request.end_timestamp
                        span.set_attribute('end_timestamp', request.end_timestamp)

                # Buscar estatisticas agregadas
                stats = await self.mongodb_client.get_insight_statistics(time_filter)

                insights_by_type = {k: v for k, v in stats.get('by_type', {}).items()}
                insights_by_priority = {k: v for k, v in stats.get('by_priority', {}).items()}
                avg_confidence = stats.get('avg_confidence', 0.0)
                avg_impact = stats.get('avg_impact', 0.0)

                span.set_attribute('total_insights', sum(insights_by_type.values()))
                span.set_status(Status(StatusCode.OK))

                logger.info('grpc_get_statistics_success', stats=stats)

                return analyst_agent_pb2.GetStatisticsResponse(
                    insights_by_type=insights_by_type,
                    insights_by_priority=insights_by_priority,
                    avg_confidence=avg_confidence,
                    avg_impact=avg_impact
                )

            except Exception as e:
                logger.error('grpc_get_statistics_failed', error=str(e))
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(str(e))
                return analyst_agent_pb2.GetStatisticsResponse()

    async def HealthCheck(self, request, context):
        """Health check do servico"""
        extract_grpc_context(context)

        with tracer.start_as_current_span('health_check') as span:
            try:
                # Verificar componentes
                mongodb_healthy = await self._check_mongodb()
                redis_healthy = await self._check_redis()

                all_healthy = mongodb_healthy and redis_healthy
                status = 'HEALTHY' if all_healthy else 'DEGRADED'

                span.set_attribute('mongodb_healthy', mongodb_healthy)
                span.set_attribute('redis_healthy', redis_healthy)
                span.set_attribute('status', status)
                span.set_status(Status(StatusCode.OK))

                logger.info('grpc_health_check', status=status)

                return analyst_agent_pb2.HealthCheckResponse(
                    healthy=all_healthy,
                    status=status
                )

            except Exception as e:
                logger.error('grpc_health_check_failed', error=str(e))
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                return analyst_agent_pb2.HealthCheckResponse(
                    healthy=False,
                    status='UNHEALTHY'
                )

    async def _check_mongodb(self) -> bool:
        """Verificar conectividade MongoDB"""
        try:
            if self.mongodb_client and self.mongodb_client.client:
                await self.mongodb_client.client.admin.command('ping')
                return True
            return False
        except Exception as e:
            logger.warning('mongodb_health_check_failed', error=str(e))
            return False

    async def _check_redis(self) -> bool:
        """Verificar conectividade Redis"""
        try:
            if self.redis_client and self.redis_client.client:
                await self.redis_client.client.ping()
                return True
            return False
        except Exception as e:
            logger.warning('redis_health_check_failed', error=str(e))
            return False

    async def GenerateInsight(self, request, context):
        """Gerar insight via insight_generator, persistir no MongoDB e cachear no Redis"""
        extract_grpc_context(context)

        with tracer.start_as_current_span('generate_insight') as span:
            try:
                span.set_attribute('insight_type', request.insight_type)
                span.set_attribute('persist_to_neo4j', request.persist_to_neo4j)
                logger.info('grpc_generate_insight_called', insight_type=request.insight_type)

                # Validar insight_type
                try:
                    insight_type = InsightType(request.insight_type)
                except ValueError:
                    context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                    context.set_details(f'Invalid insight_type: {request.insight_type}')
                    span.set_status(Status(StatusCode.ERROR, 'invalid insight_type'))
                    return analyst_agent_pb2.GenerateInsightResponse(
                        success=False,
                        error_message=f'Invalid insight_type: {request.insight_type}'
                    )

                # Preparar dados para geracao de insight
                related_entities = [
                    {'entity_type': e.entity_type, 'entity_id': e.entity_id, 'relationship': e.relationship}
                    for e in request.related_entities
                ]

                data = {
                    'title': request.title,
                    'summary': request.summary,
                    'detailed_analysis': request.detailed_analysis,
                    'data_sources': list(request.data_sources),
                    'metrics': dict(request.metrics),
                    'correlation_id': request.correlation_id or str(uuid.uuid4()),
                    'related_entities': related_entities,
                    'tags': list(request.tags),
                    'metadata': dict(request.metadata)
                }

                # Gerar insight via insight_generator
                insight = await self.insight_generator.generate_insight(
                    data=data,
                    insight_type=insight_type
                )

                # Persistir no MongoDB
                await self.mongodb_client.save_insight(insight)
                span.set_attribute('insight_id', insight.insight_id)

                # Cachear no Redis
                try:
                    await self.redis_client.cache_insight(insight)
                except Exception as cache_err:
                    logger.warning('cache_insight_failed', error=str(cache_err))

                # Persistir relacionamentos no Neo4j se solicitado e disponivel
                if request.persist_to_neo4j and self.neo4j_client:
                    try:
                        await self._persist_insight_to_neo4j(insight)
                        span.set_attribute('neo4j_persisted', True)
                    except Exception as neo4j_err:
                        logger.warning('neo4j_persist_failed', error=str(neo4j_err))
                        span.set_attribute('neo4j_persisted', False)

                # Converter para proto
                insight_dict = insight.model_dump()
                # Converter enums para strings
                insight_dict['insight_type'] = insight_dict['insight_type'].value if hasattr(insight_dict['insight_type'], 'value') else str(insight_dict['insight_type'])
                insight_dict['priority'] = insight_dict['priority'].value if hasattr(insight_dict['priority'], 'value') else str(insight_dict['priority'])
                proto_insight = self._insight_dict_to_proto(insight_dict)

                span.set_status(Status(StatusCode.OK))
                logger.info('grpc_generate_insight_success', insight_id=insight.insight_id)

                return analyst_agent_pb2.GenerateInsightResponse(
                    insight=proto_insight,
                    success=True
                )

            except Exception as e:
                logger.error('grpc_generate_insight_failed', error=str(e))
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(str(e))
                return analyst_agent_pb2.GenerateInsightResponse(
                    success=False,
                    error_message=str(e)
                )

    async def _persist_insight_to_neo4j(self, insight):
        """Persistir insight e relacionamentos no Neo4j"""
        # Criar no do insight
        create_insight_query = """
        MERGE (i:Insight {insight_id: $insight_id})
        SET i.insight_type = $insight_type,
            i.priority = $priority,
            i.title = $title,
            i.confidence_score = $confidence_score,
            i.impact_score = $impact_score,
            i.created_at = $created_at
        RETURN i
        """
        await self.neo4j_client.query_patterns(create_insight_query, {
            'insight_id': insight.insight_id,
            'insight_type': insight.insight_type.value if hasattr(insight.insight_type, 'value') else str(insight.insight_type),
            'priority': insight.priority.value if hasattr(insight.priority, 'value') else str(insight.priority),
            'title': insight.title,
            'confidence_score': insight.confidence_score,
            'impact_score': insight.impact_score,
            'created_at': insight.created_at
        })

        # Criar relacionamentos com entidades relacionadas
        for entity in insight.related_entities:
            relationship_query = """
            MERGE (i:Insight {insight_id: $insight_id})
            MERGE (e:Entity {entity_id: $entity_id, entity_type: $entity_type})
            MERGE (i)-[r:RELATED_TO {relationship: $relationship}]->(e)
            RETURN r
            """
            await self.neo4j_client.query_patterns(relationship_query, {
                'insight_id': insight.insight_id,
                'entity_id': entity.entity_id,
                'entity_type': entity.entity_type,
                'relationship': entity.relationship
            })

    def _insight_dict_to_proto(self, insight_dict: dict) -> analyst_agent_pb2.Insight:
        """Converter dicionario de insight para mensagem proto"""
        # Converter recommendations
        recommendations = []
        for r in insight_dict.get('recommendations', []):
            if isinstance(r, dict):
                recommendations.append(analyst_agent_pb2.Recommendation(
                    action=r.get('action', ''),
                    priority=r.get('priority', 'MEDIUM'),
                    estimated_impact=r.get('estimated_impact', 0.0)
                ))

        # Converter metrics (garantir que sao floats)
        metrics = {}
        for k, v in insight_dict.get('metrics', {}).items():
            try:
                metrics[k] = float(v)
            except (ValueError, TypeError):
                metrics[k] = 0.0

        return analyst_agent_pb2.Insight(
            insight_id=insight_dict.get('insight_id', ''),
            version=insight_dict.get('version', '1.0.0'),
            correlation_id=insight_dict.get('correlation_id', ''),
            trace_id=insight_dict.get('trace_id', ''),
            span_id=insight_dict.get('span_id', ''),
            insight_type=insight_dict.get('insight_type', ''),
            priority=insight_dict.get('priority', 'MEDIUM'),
            title=insight_dict.get('title', ''),
            summary=insight_dict.get('summary', ''),
            detailed_analysis=insight_dict.get('detailed_analysis', ''),
            data_sources=insight_dict.get('data_sources', []),
            metrics=metrics,
            confidence_score=insight_dict.get('confidence_score', 0.0),
            impact_score=insight_dict.get('impact_score', 0.0),
            recommendations=recommendations,
            created_at=insight_dict.get('created_at', 0),
            hash=insight_dict.get('hash', '')
        )
