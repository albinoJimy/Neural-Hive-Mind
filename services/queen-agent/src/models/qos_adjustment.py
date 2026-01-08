from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field
from uuid import uuid4

from ..proto import orchestrator_strategic_pb2


class AdjustmentType(str, Enum):
    """Tipos de ajustes de QoS"""
    INCREASE_PRIORITY = "INCREASE_PRIORITY"
    DECREASE_PRIORITY = "DECREASE_PRIORITY"
    EXTEND_DEADLINE = "EXTEND_DEADLINE"
    ALLOCATE_MORE_RESOURCES = "ALLOCATE_MORE_RESOURCES"
    PAUSE_EXECUTION = "PAUSE_EXECUTION"
    RESUME_EXECUTION = "RESUME_EXECUTION"
    CANCEL_WORKFLOW = "CANCEL_WORKFLOW"
    TRIGGER_REPLANNING = "TRIGGER_REPLANNING"


class QoSAdjustment(BaseModel):
    """Ajuste de QoS no Orchestrator"""

    adjustment_id: str = Field(default_factory=lambda: str(uuid4()), description="ID único do ajuste")
    adjustment_type: AdjustmentType = Field(..., description="Tipo de ajuste")

    target_workflow_id: str = Field(..., description="Workflow Temporal a ajustar")
    target_plan_id: str = Field(default='', description="Plano cognitivo relacionado")

    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parâmetros do ajuste")
    reason: str = Field(..., description="Motivo do ajuste")

    requested_by: str = Field(default='queen-agent', description="Quem solicitou")

    applied_at: Optional[datetime] = Field(None, description="Quando foi aplicado")
    status: str = Field(default='PENDING', description="Status da aplicação")
    error_message: Optional[str] = Field(None, description="Mensagem de erro se falhou")

    def to_grpc_request(self) -> Union[
        orchestrator_strategic_pb2.AdjustPrioritiesRequest,
        orchestrator_strategic_pb2.PauseWorkflowRequest,
        orchestrator_strategic_pb2.ResumeWorkflowRequest,
        orchestrator_strategic_pb2.RebalanceResourcesRequest,
        orchestrator_strategic_pb2.TriggerReplanningRequest,
        Dict[str, Any]
    ]:
        """
        Converter para mensagem gRPC proto para Orchestrator.

        Mapeia cada AdjustmentType para o request proto correspondente.
        """
        if self.adjustment_type in (AdjustmentType.INCREASE_PRIORITY, AdjustmentType.DECREASE_PRIORITY):
            # Ajuste de prioridade
            priority = self.parameters.get('priority', 5)
            if self.adjustment_type == AdjustmentType.INCREASE_PRIORITY:
                priority = min(10, priority + self.parameters.get('increment', 2))
            elif self.adjustment_type == AdjustmentType.DECREASE_PRIORITY:
                priority = max(1, priority - self.parameters.get('decrement', 2))

            return orchestrator_strategic_pb2.AdjustPrioritiesRequest(
                workflow_id=self.target_workflow_id,
                plan_id=self.target_plan_id,
                new_priority=priority,
                reason=self.reason,
                adjustment_id=self.adjustment_id
            )

        elif self.adjustment_type == AdjustmentType.PAUSE_EXECUTION:
            # Pausar workflow
            return orchestrator_strategic_pb2.PauseWorkflowRequest(
                workflow_id=self.target_workflow_id,
                reason=self.reason,
                pause_duration_seconds=self.parameters.get('duration_seconds'),
                adjustment_id=self.adjustment_id
            )

        elif self.adjustment_type == AdjustmentType.RESUME_EXECUTION:
            # Retomar workflow
            return orchestrator_strategic_pb2.ResumeWorkflowRequest(
                workflow_id=self.target_workflow_id,
                reason=self.reason,
                adjustment_id=self.adjustment_id
            )

        elif self.adjustment_type == AdjustmentType.ALLOCATE_MORE_RESOURCES:
            # Rebalancear recursos
            allocation = {
                self.target_workflow_id: orchestrator_strategic_pb2.ResourceAllocation(
                    cpu_millicores=self.parameters.get('cpu_millicores', 2000),
                    memory_mb=self.parameters.get('memory_mb', 4096),
                    max_parallel_tickets=self.parameters.get('max_parallel_tickets', 20),
                    scheduling_priority=self.parameters.get('scheduling_priority', 8)
                )
            }
            return orchestrator_strategic_pb2.RebalanceResourcesRequest(
                workflow_ids=[self.target_workflow_id],
                target_allocation=allocation,
                reason=self.reason,
                rebalance_id=self.adjustment_id,
                force=self.parameters.get('force', False)
            )

        elif self.adjustment_type == AdjustmentType.TRIGGER_REPLANNING:
            # Acionar replanejamento
            trigger_type = orchestrator_strategic_pb2.TRIGGER_TYPE_STRATEGIC
            trigger_str = self.parameters.get('trigger_type', 'STRATEGIC').upper()
            trigger_map = {
                'DRIFT': orchestrator_strategic_pb2.TRIGGER_TYPE_DRIFT,
                'FAILURE': orchestrator_strategic_pb2.TRIGGER_TYPE_FAILURE,
                'STRATEGIC': orchestrator_strategic_pb2.TRIGGER_TYPE_STRATEGIC,
                'SLA_VIOLATION': orchestrator_strategic_pb2.TRIGGER_TYPE_SLA_VIOLATION,
                'RESOURCE_CONSTRAINT': orchestrator_strategic_pb2.TRIGGER_TYPE_RESOURCE_CONSTRAINT,
            }
            trigger_type = trigger_map.get(trigger_str, orchestrator_strategic_pb2.TRIGGER_TYPE_STRATEGIC)

            return orchestrator_strategic_pb2.TriggerReplanningRequest(
                plan_id=self.target_plan_id,
                reason=self.reason,
                trigger_type=trigger_type,
                adjustment_id=self.adjustment_id,
                context=self.parameters.get('context', {}),
                preserve_progress=self.parameters.get('preserve_progress', True),
                priority=self.parameters.get('priority', 5)
            )

        else:
            # Fallback para dict genérico (compatibilidade)
            return {
                'adjustment_id': self.adjustment_id,
                'adjustment_type': self.adjustment_type.value,
                'workflow_id': self.target_workflow_id,
                'plan_id': self.target_plan_id,
                'parameters': self.parameters,
                'reason': self.reason
            }

    def mark_applied(self) -> None:
        """Marcar como aplicado"""
        self.status = 'APPLIED'
        self.applied_at = datetime.now()

    def mark_failed(self, error: str) -> None:
        """Marcar como falho"""
        self.status = 'FAILED'
        self.error_message = error
