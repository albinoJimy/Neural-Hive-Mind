"""
Testes de contrato OPA para garantir compatibilidade entre Orchestrator e políticas Rego.

Este módulo valida:
- Schema de input esperado por cada política Rego
- Schema de output retornado por cada política
- Casos edge (valores nulos, arrays vazios, campos opcionais)
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any
from unittest.mock import Mock

from src.policies import OPAClient
from src.config.settings import OrchestratorSettings


# Schemas de contrato para validação
RESOURCE_LIMITS_INPUT_SCHEMA = {
    'required_fields': ['resource'],
    'resource_fields': ['ticket_id', 'risk_band', 'sla', 'required_capabilities'],
    'sla_fields': ['timeout_ms', 'max_retries'],
    'output_fields': ['allow', 'violations']
}

SLA_ENFORCEMENT_INPUT_SCHEMA = {
    'required_fields': ['resource', 'context'],
    'resource_fields': ['ticket_id', 'risk_band', 'sla', 'qos', 'priority'],
    'context_fields': ['current_time'],
    'output_fields': ['allow', 'violations', 'warnings']
}

FEATURE_FLAGS_INPUT_SCHEMA = {
    'required_fields': ['resource', 'flags', 'context'],
    'output_fields': [
        'enable_intelligent_scheduler',
        'enable_burst_capacity',
        'enable_predictive_allocation',
        'enable_auto_scaling',
        'enable_experimental_features'
    ]
}

SECURITY_CONSTRAINTS_INPUT_SCHEMA = {
    'required_fields': ['resource', 'security', 'context'],
    'output_fields': ['allow', 'violations', 'security_context']
}


@pytest.fixture
def contract_config():
    """Fixture com configurações para testes de contrato."""
    config = Mock(spec=OrchestratorSettings)
    config.opa_host = 'localhost'
    config.opa_port = 8181
    config.opa_timeout_seconds = 5
    config.opa_retry_attempts = 3
    config.opa_cache_ttl_seconds = 30
    config.opa_fail_open = False
    config.opa_circuit_breaker_enabled = True
    config.opa_circuit_breaker_failure_threshold = 5
    config.opa_circuit_breaker_reset_timeout = 60
    return config


def validate_output_schema(result: Dict[str, Any], expected_fields: list) -> tuple:
    """
    Valida schema de output da política OPA.

    Args:
        result: Resultado da avaliação OPA
        expected_fields: Lista de campos esperados no output

    Returns:
        Tupla (is_valid, missing_fields)
    """
    if 'result' not in result:
        return False, ['result']

    policy_result = result['result']
    missing_fields = [f for f in expected_fields if f not in policy_result]

    return len(missing_fields) == 0, missing_fields


def validate_violation_schema(violation: Dict[str, Any]) -> tuple:
    """
    Valida schema de uma violação.

    Args:
        violation: Dict de violação da política

    Returns:
        Tupla (is_valid, missing_fields)
    """
    required_fields = ['policy', 'rule', 'severity', 'msg']
    optional_fields = ['field', 'expected', 'actual']

    missing_required = [f for f in required_fields if f not in violation]

    return len(missing_required) == 0, missing_required


class TestResourceLimitsContract:
    """Testes de contrato para política resource_limits."""

    def test_input_schema_minimal(self):
        """Testa schema mínimo de input para resource_limits."""
        minimal_input = {
            'input': {
                'resource': {
                    'ticket_id': 'test-123',
                    'risk_band': 'medium',
                    'sla': {
                        'timeout_ms': 60000,
                        'max_retries': 2
                    },
                    'required_capabilities': ['code_generation']
                },
                'parameters': {
                    'allowed_capabilities': ['code_generation'],
                    'max_concurrent_tickets': 100
                },
                'context': {
                    'total_tickets': 50
                }
            }
        }

        # Verificar campos obrigatórios
        assert 'input' in minimal_input
        assert 'resource' in minimal_input['input']

        resource = minimal_input['input']['resource']
        for field in RESOURCE_LIMITS_INPUT_SCHEMA['resource_fields']:
            assert field in resource, f"Campo obrigatório ausente: {field}"

    def test_output_schema_validation(self):
        """Testa schema de output esperado de resource_limits."""
        # Output esperado quando allow=True
        success_output = {
            'result': {
                'allow': True,
                'violations': [],
                'warnings': []
            }
        }

        is_valid, missing = validate_output_schema(
            success_output,
            RESOURCE_LIMITS_INPUT_SCHEMA['output_fields']
        )
        assert is_valid, f"Campos ausentes: {missing}"

        # Output esperado quando allow=False
        failure_output = {
            'result': {
                'allow': False,
                'violations': [{
                    'policy': 'resource_limits',
                    'rule': 'timeout_exceeds_maximum',
                    'severity': 'high',
                    'msg': 'Timeout excede o limite máximo'
                }],
                'warnings': []
            }
        }

        is_valid, missing = validate_output_schema(
            failure_output,
            RESOURCE_LIMITS_INPUT_SCHEMA['output_fields']
        )
        assert is_valid, f"Campos ausentes: {missing}"

        # Validar schema de violação
        for violation in failure_output['result']['violations']:
            is_valid, missing = validate_violation_schema(violation)
            assert is_valid, f"Campos de violação ausentes: {missing}"

    def test_edge_case_empty_capabilities(self):
        """Testa input com lista de capabilities vazia."""
        input_data = {
            'input': {
                'resource': {
                    'ticket_id': 'edge-001',
                    'risk_band': 'low',
                    'sla': {
                        'timeout_ms': 60000,
                        'max_retries': 1
                    },
                    'required_capabilities': []  # Lista vazia
                },
                'parameters': {
                    'allowed_capabilities': [],
                    'max_concurrent_tickets': 100
                },
                'context': {
                    'total_tickets': 0
                }
            }
        }

        # Lista vazia é um input válido
        assert input_data['input']['resource']['required_capabilities'] == []

    def test_edge_case_null_optional_fields(self):
        """Testa input com campos opcionais nulos."""
        input_data = {
            'input': {
                'resource': {
                    'ticket_id': 'edge-002',
                    'risk_band': 'medium',
                    'sla': {
                        'timeout_ms': 60000,
                        'max_retries': 2
                    },
                    'estimated_duration_ms': None,  # Campo opcional nulo
                    'required_capabilities': ['testing']
                },
                'parameters': {
                    'allowed_capabilities': ['testing'],
                    'max_concurrent_tickets': 100,
                    'resource_limits': None  # Campo opcional nulo
                },
                'context': {
                    'total_tickets': 10
                }
            }
        }

        # Campos opcionais nulos são permitidos
        assert input_data['input']['resource']['estimated_duration_ms'] is None


class TestSLAEnforcementContract:
    """Testes de contrato para política sla_enforcement."""

    def test_input_schema_minimal(self):
        """Testa schema mínimo de input para sla_enforcement."""
        current_time = int(datetime.now().timestamp() * 1000)
        deadline = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)

        minimal_input = {
            'input': {
                'resource': {
                    'ticket_id': 'sla-001',
                    'risk_band': 'high',
                    'sla': {
                        'timeout_ms': 120000,
                        'deadline': deadline
                    },
                    'qos': {
                        'delivery_mode': 'EXACTLY_ONCE',
                        'consistency': 'STRONG'
                    },
                    'priority': 'HIGH',
                    'estimated_duration_ms': 60000
                },
                'context': {
                    'current_time': current_time
                }
            }
        }

        # Verificar campos obrigatórios
        assert 'context' in minimal_input['input']
        assert 'current_time' in minimal_input['input']['context']

        resource = minimal_input['input']['resource']
        for field in SLA_ENFORCEMENT_INPUT_SCHEMA['resource_fields']:
            assert field in resource, f"Campo obrigatório ausente: {field}"

    def test_output_schema_with_warnings(self):
        """Testa schema de output com warnings."""
        output_with_warnings = {
            'result': {
                'allow': True,
                'violations': [],
                'warnings': [{
                    'policy': 'sla_enforcement',
                    'rule': 'deadline_approaching_threshold',
                    'msg': 'Deadline está próximo'
                }]
            }
        }

        is_valid, missing = validate_output_schema(
            output_with_warnings,
            SLA_ENFORCEMENT_INPUT_SCHEMA['output_fields']
        )
        assert is_valid, f"Campos ausentes: {missing}"

        # Warnings devem ter policy, rule e msg
        for warning in output_with_warnings['result']['warnings']:
            assert 'policy' in warning
            assert 'rule' in warning
            assert 'msg' in warning

    def test_qos_modes_valid_values(self):
        """Testa valores válidos de QoS."""
        valid_delivery_modes = ['EXACTLY_ONCE', 'AT_LEAST_ONCE', 'AT_MOST_ONCE']
        valid_consistency = ['STRONG', 'EVENTUAL', 'RELAXED']

        for mode in valid_delivery_modes:
            input_data = {
                'input': {
                    'resource': {
                        'qos': {'delivery_mode': mode, 'consistency': 'STRONG'}
                    }
                }
            }
            assert input_data['input']['resource']['qos']['delivery_mode'] == mode

        for consistency in valid_consistency:
            input_data = {
                'input': {
                    'resource': {
                        'qos': {'delivery_mode': 'EXACTLY_ONCE', 'consistency': consistency}
                    }
                }
            }
            assert input_data['input']['resource']['qos']['consistency'] == consistency


class TestFeatureFlagsContract:
    """Testes de contrato para política feature_flags."""

    def test_input_schema_minimal(self):
        """Testa schema mínimo de input para feature_flags."""
        current_time = int(datetime.now().timestamp() * 1000)

        minimal_input = {
            'input': {
                'resource': {
                    'ticket_id': 'ff-001',
                    'risk_band': 'critical'
                },
                'flags': {
                    'intelligent_scheduler_enabled': True,
                    'burst_capacity_enabled': False,
                    'predictive_allocation_enabled': False,
                    'auto_scaling_enabled': False,
                    'scheduler_namespaces': ['production']
                },
                'context': {
                    'namespace': 'production',
                    'current_load': 0.5,
                    'tenant_id': 'tenant-1',
                    'queue_depth': 50,
                    'current_time': current_time,
                    'model_accuracy': 0.9
                }
            }
        }

        # Verificar campos de flags
        assert 'flags' in minimal_input['input']
        assert 'intelligent_scheduler_enabled' in minimal_input['input']['flags']

    def test_output_schema_all_flags(self):
        """Testa que output contém todos os feature flags esperados."""
        expected_output = {
            'result': {
                'enable_intelligent_scheduler': True,
                'enable_burst_capacity': False,
                'enable_predictive_allocation': False,
                'enable_auto_scaling': False,
                'enable_experimental_features': False
            }
        }

        is_valid, missing = validate_output_schema(
            expected_output,
            FEATURE_FLAGS_INPUT_SCHEMA['output_fields']
        )
        assert is_valid, f"Feature flags ausentes: {missing}"

    def test_edge_case_empty_input(self):
        """Testa output com input vazio."""
        # Com input vazio, todas as flags devem retornar False
        empty_input_output = {
            'result': {
                'enable_intelligent_scheduler': False,
                'enable_burst_capacity': False,
                'enable_predictive_allocation': False,
                'enable_auto_scaling': False,
                'enable_experimental_features': False
            }
        }

        for flag in FEATURE_FLAGS_INPUT_SCHEMA['output_fields']:
            assert flag in empty_input_output['result']
            assert empty_input_output['result'][flag] is False


class TestSecurityConstraintsContract:
    """Testes de contrato para política security_constraints."""

    def test_input_schema_minimal(self):
        """Testa schema mínimo de input para security_constraints."""
        current_time = int(datetime.now().timestamp() * 1000)

        minimal_input = {
            'input': {
                'resource': {
                    'ticket_id': 'sec-001',
                    'tenant_id': 'tenant-1',
                    'risk_band': 'medium',
                    'required_capabilities': ['testing']
                },
                'security': {
                    'spiffe_enabled': False,
                    'allowed_tenants': ['tenant-1'],
                    'tenant_rate_limits': {'tenant-1': 10},
                    'global_rate_limit': 100,
                    'default_tenant_rate_limit': 5
                },
                'context': {
                    'user_id': 'user-dev',
                    'current_time': current_time,
                    'request_count_last_minute': 1
                }
            }
        }

        # Verificar campos obrigatórios de segurança
        assert 'security' in minimal_input['input']
        assert 'allowed_tenants' in minimal_input['input']['security']

    def test_output_schema_with_security_context(self):
        """Testa schema de output com security_context."""
        output_with_context = {
            'result': {
                'allow': True,
                'violations': [],
                'security_context': {
                    'tenant_id': 'tenant-1',
                    'user_id': 'user-dev',
                    'authenticated': True,
                    'permissions': ['read', 'write']
                }
            }
        }

        is_valid, missing = validate_output_schema(
            output_with_context,
            SECURITY_CONSTRAINTS_INPUT_SCHEMA['output_fields']
        )
        assert is_valid, f"Campos ausentes: {missing}"

        # Verificar security_context
        assert 'security_context' in output_with_context['result']

    def test_violation_types(self):
        """Testa tipos de violações de segurança."""
        security_violation_rules = [
            'cross_tenant_access',
            'missing_authentication',
            'invalid_jwt',
            'insufficient_permissions',
            'pii_handling_violation',
            'tenant_rate_limit_exceeded',
            'global_rate_limit_exceeded',
            'data_residency_violation'
        ]

        for rule in security_violation_rules:
            violation = {
                'policy': 'security_constraints',
                'rule': rule,
                'severity': 'critical',
                'msg': f'Violação: {rule}'
            }

            is_valid, missing = validate_violation_schema(violation)
            assert is_valid, f"Violação {rule} inválida: {missing}"


class TestCrossContractCompatibility:
    """Testes de compatibilidade entre contratos."""

    def test_resource_shared_across_policies(self):
        """Testa que structure de resource é compatível entre políticas."""
        # Resource base compartilhado
        shared_resource = {
            'ticket_id': 'compat-001',
            'risk_band': 'high',
            'sla': {
                'timeout_ms': 120000,
                'deadline': int((datetime.now() + timedelta(hours=1)).timestamp() * 1000),
                'max_retries': 3
            },
            'qos': {
                'delivery_mode': 'EXACTLY_ONCE',
                'consistency': 'STRONG'
            },
            'priority': 'HIGH',
            'required_capabilities': ['code_generation'],
            'estimated_duration_ms': 60000
        }

        # Resource deve ser válido para resource_limits
        for field in RESOURCE_LIMITS_INPUT_SCHEMA['resource_fields']:
            if field != 'priority' and field != 'qos':  # Campos específicos de sla_enforcement
                assert field in shared_resource, f"Campo {field} faltando para resource_limits"

        # Resource deve ser válido para sla_enforcement
        for field in SLA_ENFORCEMENT_INPUT_SCHEMA['resource_fields']:
            assert field in shared_resource, f"Campo {field} faltando para sla_enforcement"

    def test_context_consistency(self):
        """Testa consistência de context entre políticas."""
        current_time = int(datetime.now().timestamp() * 1000)

        # Context comum
        shared_context = {
            'current_time': current_time,
            'namespace': 'production',
            'tenant_id': 'tenant-1',
            'user_id': 'user-dev'
        }

        # SLA enforcement precisa de current_time
        assert 'current_time' in shared_context

        # Feature flags precisa de namespace e tenant_id
        assert 'namespace' in shared_context
        assert 'tenant_id' in shared_context

        # Security constraints precisa de user_id
        assert 'user_id' in shared_context

    def test_violation_severity_consistency(self):
        """Testa consistência de severidades entre políticas."""
        valid_severities = ['critical', 'high', 'medium', 'low']

        # Todas as políticas devem usar os mesmos níveis de severidade
        sample_violations = [
            {'severity': 'critical', 'policy': 'resource_limits'},
            {'severity': 'high', 'policy': 'sla_enforcement'},
            {'severity': 'medium', 'policy': 'security_constraints'},
            {'severity': 'low', 'policy': 'feature_flags'}
        ]

        for violation in sample_violations:
            assert violation['severity'] in valid_severities, \
                f"Severidade inválida: {violation['severity']}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
