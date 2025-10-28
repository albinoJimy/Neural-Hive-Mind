"""Implementação do gRPC Servicer para Queen Agent"""
import grpc
import structlog
from typing import TYPE_CHECKING
from datetime import datetime

from ..proto import queen_agent_pb2, queen_agent_pb2_grpc
from ..models import ExceptionApproval, ExceptionType, RiskAssessment

if TYPE_CHECKING:
    from ..clients import MongoDBClient, Neo4jClient
    from ..services import ExceptionApprovalService, TelemetryAggregator

logger = structlog.get_logger()


class QueenAgentServicer(queen_agent_pb2_grpc.QueenAgentServicer):
    """Implementação do serviço gRPC Queen Agent"""

    def __init__(
        self,
        mongodb_client: 'MongoDBClient',
        neo4j_client: 'Neo4jClient',
        exception_service: 'ExceptionApprovalService',
        telemetry_aggregator: 'TelemetryAggregator'
    ):
        self.mongodb_client = mongodb_client
        self.neo4j_client = neo4j_client
        self.exception_service = exception_service
        self.telemetry_aggregator = telemetry_aggregator

    async def GetStrategicDecision(self, request, context):
        """Buscar decisão estratégica por ID"""
        try:
            decision = await self.mongodb_client.get_strategic_decision(request.decision_id)

            if not decision:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Decision {request.decision_id} not found")
                return queen_agent_pb2.StrategicDecisionResponse()

            # Converter para resposta gRPC
            return queen_agent_pb2.StrategicDecisionResponse(
                decision_id=decision.get('decision_id', ''),
                decision_type=decision.get('decision_type', ''),
                confidence_score=decision.get('confidence_score', 0.0),
                risk_score=decision.get('risk_assessment', {}).get('risk_score', 0.0),
                reasoning_summary=decision.get('reasoning_summary', ''),
                created_at=decision.get('created_at', 0),
                target_entities=decision.get('decision', {}).get('target_entities', []),
                action=decision.get('decision', {}).get('action', '')
            )

        except Exception as e:
            logger.error("grpc_get_strategic_decision_failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return queen_agent_pb2.StrategicDecisionResponse()

    async def ListStrategicDecisions(self, request, context):
        """Listar decisões estratégicas recentes"""
        try:
            # Construir filtros
            filters = {}
            if request.decision_type:
                filters['decision_type'] = request.decision_type
            if request.start_date or request.end_date:
                filters['created_at'] = {}
                if request.start_date:
                    filters['created_at']['$gte'] = request.start_date
                if request.end_date:
                    filters['created_at']['$lte'] = request.end_date

            limit = request.limit if request.limit > 0 else 50
            offset = request.offset if request.offset >= 0 else 0

            decisions = await self.mongodb_client.list_strategic_decisions(
                filters,
                limit=limit,
                skip=offset
            )

            # Converter para resposta gRPC
            decision_responses = []
            for decision in decisions:
                decision_responses.append(
                    queen_agent_pb2.StrategicDecisionResponse(
                        decision_id=decision.get('decision_id', ''),
                        decision_type=decision.get('decision_type', ''),
                        confidence_score=decision.get('confidence_score', 0.0),
                        risk_score=decision.get('risk_assessment', {}).get('risk_score', 0.0),
                        reasoning_summary=decision.get('reasoning_summary', ''),
                        created_at=decision.get('created_at', 0),
                        target_entities=decision.get('decision', {}).get('target_entities', []),
                        action=decision.get('decision', {}).get('action', '')
                    )
                )

            return queen_agent_pb2.ListStrategicDecisionsResponse(
                decisions=decision_responses,
                total=len(decisions)
            )

        except Exception as e:
            logger.error("grpc_list_strategic_decisions_failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return queen_agent_pb2.ListStrategicDecisionsResponse()

    async def GetSystemStatus(self, request, context):
        """Obter status geral do sistema"""
        try:
            health = await self.telemetry_aggregator.aggregate_system_health()

            return queen_agent_pb2.SystemStatusResponse(
                system_score=health.get('system_score', 0.0),
                sla_compliance=health.get('sla_compliance', 0.0),
                error_rate=health.get('error_rate', 0.0),
                resource_saturation=health.get('resource_saturation', 0.0),
                active_incidents=health.get('active_incidents', 0),
                timestamp=health.get('timestamp', 0)
            )

        except Exception as e:
            logger.error("grpc_get_system_status_failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return queen_agent_pb2.SystemStatusResponse()

    async def RequestExceptionApproval(self, request, context):
        """Solicitar aprovação de exceção"""
        try:
            # Criar ExceptionApproval
            exception = ExceptionApproval(
                exception_type=ExceptionType(request.exception_type),
                plan_id=request.plan_id,
                justification=request.justification,
                guardrails_affected=list(request.guardrails_affected),
                risk_assessment=RiskAssessment(risk_score=0.0, risk_factors=[], mitigations=[]),
                expires_at=request.expires_at
            )

            exception_id = await self.exception_service.request_exception(exception)

            return queen_agent_pb2.RequestExceptionResponse(
                exception_id=exception_id,
                status="pending"
            )

        except Exception as e:
            logger.error("grpc_request_exception_approval_failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return queen_agent_pb2.RequestExceptionResponse()

    async def ApproveException(self, request, context):
        """Aprovar exceção"""
        try:
            exception = await self.exception_service.approve_exception(
                request.exception_id,
                request.decision_id,
                list(request.conditions)
            )

            return queen_agent_pb2.ApproveExceptionResponse(
                exception_id=exception.exception_id,
                status="approved",
                approved_at=int(datetime.now().timestamp() * 1000)
            )

        except ValueError as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return queen_agent_pb2.ApproveExceptionResponse()
        except Exception as e:
            logger.error("grpc_approve_exception_failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return queen_agent_pb2.ApproveExceptionResponse()

    async def RejectException(self, request, context):
        """Rejeitar exceção"""
        try:
            exception = await self.exception_service.reject_exception(
                request.exception_id,
                request.reason
            )

            return queen_agent_pb2.RejectExceptionResponse(
                exception_id=exception.exception_id,
                status="rejected",
                rejected_at=int(datetime.now().timestamp() * 1000)
            )

        except ValueError as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return queen_agent_pb2.RejectExceptionResponse()
        except Exception as e:
            logger.error("grpc_reject_exception_failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return queen_agent_pb2.RejectExceptionResponse()

    async def GetActiveConflicts(self, request, context):
        """Obter conflitos ativos"""
        try:
            # Usar o helper do Neo4j client
            results = await self.neo4j_client.list_active_conflicts()

            conflicts = []
            for record in results:
                conflicts.append(
                    queen_agent_pb2.ConflictInfo(
                        decision_id=record.get("decision_id", ""),
                        conflicts_with=record.get("conflicts_with", ""),
                        created_at=record.get("created_at", 0)
                    )
                )

            return queen_agent_pb2.GetActiveConflictsResponse(conflicts=conflicts)

        except Exception as e:
            logger.error("grpc_get_active_conflicts_failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return queen_agent_pb2.GetActiveConflictsResponse()

    async def SubmitInsight(self, request, context):
        """Receber insight de Analyst Agent"""
        try:
            # Converter request proto para dict
            insight_data = {
                'insight_id': request.insight_id,
                'version': request.version,
                'correlation_id': request.correlation_id,
                'trace_id': request.trace_id,
                'span_id': request.span_id,
                'insight_type': request.insight_type,
                'priority': request.priority,
                'title': request.title,
                'summary': request.summary,
                'detailed_analysis': request.detailed_analysis,
                'data_sources': list(request.data_sources),
                'metrics': dict(request.metrics),
                'confidence_score': request.confidence_score,
                'impact_score': request.impact_score,
                'recommendations': [
                    {
                        'action': rec.action,
                        'priority': rec.priority,
                        'estimated_impact': rec.estimated_impact
                    } for rec in request.recommendations
                ],
                'related_entities': [
                    {
                        'entity_type': entity.entity_type,
                        'entity_id': entity.entity_id,
                        'relationship': entity.relationship
                    } for entity in request.related_entities
                ],
                'time_window': {
                    'start_timestamp': request.time_window.start_timestamp,
                    'end_timestamp': request.time_window.end_timestamp
                },
                'created_at': request.created_at,
                'valid_until': request.valid_until if request.HasField('valid_until') else None,
                'tags': list(request.tags),
                'metadata': dict(request.metadata),
                'hash': request.hash,
                'schema_version': request.schema_version
            }

            # Armazenar insight no MongoDB
            await self.mongodb_client.db.analyst_insights.insert_one(insight_data)

            logger.info("analyst_insight_received",
                       insight_id=request.insight_id,
                       insight_type=request.insight_type,
                       priority=request.priority,
                       confidence_score=request.confidence_score)

            return queen_agent_pb2.SubmitInsightResponse(
                accepted=True,
                insight_id=request.insight_id,
                message=f"Insight {request.insight_id} aceito com sucesso"
            )

        except Exception as e:
            logger.error("grpc_submit_insight_failed", error=str(e), insight_id=request.insight_id)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return queen_agent_pb2.SubmitInsightResponse(
                accepted=False,
                insight_id=request.insight_id,
                message=f"Erro ao processar insight: {str(e)}"
            )
