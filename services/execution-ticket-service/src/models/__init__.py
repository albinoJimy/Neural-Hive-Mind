"""Modelos de dados do Execution Ticket Service."""

# Reutilizar modelo Pydantic do Orchestrator
import sys
import os
from importlib.util import spec_from_file_location, module_from_spec

# Caminho para o módulo execution_ticket do orchestrator
execution_ticket_path = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        '../../../orchestrator-dynamic/src/models/execution_ticket.py'
    )
)

# Importar diretamente do arquivo para evitar conflito de namespace
spec = spec_from_file_location("orchestrator_execution_ticket", execution_ticket_path)
_orchestrator_models = module_from_spec(spec)
spec.loader.exec_module(_orchestrator_models)

# Expor as classes importadas
ExecutionTicket = _orchestrator_models.ExecutionTicket
TaskType = _orchestrator_models.TaskType
TicketStatus = _orchestrator_models.TicketStatus
Priority = _orchestrator_models.Priority
RiskBand = _orchestrator_models.RiskBand
SecurityLevel = _orchestrator_models.SecurityLevel
DeliveryMode = _orchestrator_models.DeliveryMode
Consistency = _orchestrator_models.Consistency
Durability = _orchestrator_models.Durability
SLA = _orchestrator_models.SLA
QoS = _orchestrator_models.QoS

from .ticket_orm import TicketORM
from .webhook_event import WebhookEvent
from .jwt_token import JWTToken, JWTTokenPayload, generate_token, decode_token

__all__ = [
    'ExecutionTicket',
    'TaskType',
    'TicketStatus',
    'Priority',
    'RiskBand',
    'SecurityLevel',
    'DeliveryMode',
    'Consistency',
    'Durability',
    'SLA',
    'QoS',
    'TicketORM',
    'WebhookEvent',
    'JWTToken',
    'JWTTokenPayload',
    'generate_token',
    'decode_token'
]
