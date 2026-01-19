"""
Testes unitarios para models do Approval Service

Testa serializacao e validacao de modelos.
"""

import pytest
import json
from datetime import datetime
from src.models.approval import (
    ApprovalRequest,
    ApprovalResponse,
    RiskBand,
    ApprovalStatus
)


class TestApprovalResponseKafkaDict:
    """Testes para serializacao ApprovalResponse para Kafka/Avro"""

    def test_to_kafka_dict_with_cognitive_plan(self):
        """Teste serializacao com cognitive_plan como JSON string"""
        cognitive_plan = {
            'plan_id': 'plan-001',
            'intent_id': 'intent-001',
            'tasks': [
                {'task_id': 'task-1', 'type': 'query'},
                {'task_id': 'task-2', 'type': 'delete'}
            ],
            'nested': {
                'key': 'value',
                'list': [1, 2, 3]
            }
        }

        response = ApprovalResponse(
            plan_id='plan-001',
            intent_id='intent-001',
            decision='approved',
            approved_by='admin@example.com',
            approved_at=datetime(2024, 1, 15, 12, 0, 0),
            cognitive_plan=cognitive_plan
        )

        kafka_dict = response.to_kafka_dict()

        # Verifica campos basicos
        assert kafka_dict['plan_id'] == 'plan-001'
        assert kafka_dict['intent_id'] == 'intent-001'
        assert kafka_dict['decision'] == 'approved'
        assert kafka_dict['approved_by'] == 'admin@example.com'
        assert kafka_dict['rejection_reason'] is None

        # Verifica cognitive_plan_json e string JSON valida
        assert 'cognitive_plan_json' in kafka_dict
        assert isinstance(kafka_dict['cognitive_plan_json'], str)

        # Verifica que JSON e deserializavel e contem dados corretos
        deserialized = json.loads(kafka_dict['cognitive_plan_json'])
        assert deserialized['plan_id'] == 'plan-001'
        assert deserialized['tasks'][0]['task_id'] == 'task-1'
        assert deserialized['nested']['key'] == 'value'

    def test_to_kafka_dict_without_cognitive_plan(self):
        """Teste serializacao sem cognitive_plan (rejeicao)"""
        response = ApprovalResponse(
            plan_id='plan-001',
            intent_id='intent-001',
            decision='rejected',
            approved_by='admin@example.com',
            approved_at=datetime(2024, 1, 15, 12, 0, 0),
            rejection_reason='Risco muito alto',
            cognitive_plan=None
        )

        kafka_dict = response.to_kafka_dict()

        assert kafka_dict['decision'] == 'rejected'
        assert kafka_dict['rejection_reason'] == 'Risco muito alto'
        assert kafka_dict['cognitive_plan_json'] is None

    def test_to_kafka_dict_timestamp_format(self):
        """Teste que approved_at e serializado como milliseconds"""
        response = ApprovalResponse(
            plan_id='plan-001',
            intent_id='intent-001',
            decision='approved',
            approved_by='admin@example.com',
            approved_at=datetime(2024, 1, 15, 12, 0, 0),
            cognitive_plan={'plan_id': 'plan-001'}
        )

        kafka_dict = response.to_kafka_dict()

        # Verifica que e um inteiro (milliseconds)
        assert isinstance(kafka_dict['approved_at'], int)
        # Verifica valor aproximado (1705320000000 = 2024-01-15 12:00:00 UTC em ms)
        assert kafka_dict['approved_at'] > 0


class TestApprovalRequestValidation:
    """Testes para validacao de ApprovalRequest"""

    def test_approval_request_risk_band_enum(self):
        """Teste que risk_band aceita enum e string"""
        request_enum = ApprovalRequest(
            plan_id='plan-001',
            intent_id='intent-001',
            risk_score=0.8,
            risk_band=RiskBand.HIGH,
            cognitive_plan={}
        )
        assert request_enum.risk_band == RiskBand.HIGH

        request_str = ApprovalRequest(
            plan_id='plan-002',
            intent_id='intent-002',
            risk_score=0.3,
            risk_band='low',
            cognitive_plan={}
        )
        assert request_str.risk_band == RiskBand.LOW

    def test_approval_request_default_status(self):
        """Teste que status padrao e PENDING"""
        request = ApprovalRequest(
            plan_id='plan-001',
            intent_id='intent-001',
            risk_score=0.5,
            risk_band=RiskBand.MEDIUM,
            cognitive_plan={}
        )
        assert request.status == ApprovalStatus.PENDING

    def test_approval_request_auto_generated_approval_id(self):
        """Teste que approval_id e gerado automaticamente"""
        request1 = ApprovalRequest(
            plan_id='plan-001',
            intent_id='intent-001',
            risk_score=0.5,
            risk_band=RiskBand.MEDIUM,
            cognitive_plan={}
        )
        request2 = ApprovalRequest(
            plan_id='plan-002',
            intent_id='intent-002',
            risk_score=0.5,
            risk_band=RiskBand.MEDIUM,
            cognitive_plan={}
        )

        assert request1.approval_id is not None
        assert request2.approval_id is not None
        assert request1.approval_id != request2.approval_id
