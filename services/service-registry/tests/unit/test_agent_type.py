"""
Testes unitários para AgentType.from_proto_value()

Este módulo testa a conversão de valores protobuf (int) para AgentType enum.
"""

import pytest
import sys
import os

# Adicionar src ao path para importação
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from models.agent import AgentType


class TestAgentTypeFromProtoValue:
    """Testes para o método from_proto_value()"""

    # Testes com valores inteiros válidos (protobuf enum values)

    def test_int_1_returns_worker(self):
        """Testa que int 1 retorna WORKER"""
        result = AgentType.from_proto_value(1)
        assert result == AgentType.WORKER
        assert result.value == "WORKER"

    def test_int_2_returns_scout(self):
        """Testa que int 2 retorna SCOUT"""
        result = AgentType.from_proto_value(2)
        assert result == AgentType.SCOUT
        assert result.value == "SCOUT"

    def test_int_3_returns_guard(self):
        """Testa que int 3 retorna GUARD"""
        result = AgentType.from_proto_value(3)
        assert result == AgentType.GUARD
        assert result.value == "GUARD"

    def test_int_4_returns_analyst(self):
        """Testa que int 4 retorna ANALYST"""
        result = AgentType.from_proto_value(4)
        assert result == AgentType.ANALYST
        assert result.value == "ANALYST"

    # Testes com valores inteiros inválidos

    def test_int_0_raises_value_error(self):
        """Testa que int 0 (UNSPECIFIED) levanta ValueError"""
        with pytest.raises(ValueError) as exc_info:
            AgentType.from_proto_value(0)
        assert "Invalid AgentType int value: 0" in str(exc_info.value)

    def test_int_5_raises_value_error(self):
        """Testa que int 5 (fora do range) levanta ValueError"""
        with pytest.raises(ValueError) as exc_info:
            AgentType.from_proto_value(5)
        assert "Invalid AgentType int value: 5" in str(exc_info.value)

    def test_int_negative_raises_value_error(self):
        """Testa que int negativo levanta ValueError"""
        with pytest.raises(ValueError) as exc_info:
            AgentType.from_proto_value(-1)
        assert "Invalid AgentType int value: -1" in str(exc_info.value)

    def test_int_99_raises_value_error(self):
        """Testa que int 99 levanta ValueError"""
        with pytest.raises(ValueError) as exc_info:
            AgentType.from_proto_value(99)
        assert "Invalid AgentType int value: 99" in str(exc_info.value)

    # Testes com strings válidas

    def test_string_worker_returns_worker(self):
        """Testa que string 'WORKER' retorna WORKER"""
        result = AgentType.from_proto_value("WORKER")
        assert result == AgentType.WORKER

    def test_string_scout_returns_scout(self):
        """Testa que string 'SCOUT' retorna SCOUT"""
        result = AgentType.from_proto_value("SCOUT")
        assert result == AgentType.SCOUT

    def test_string_guard_returns_guard(self):
        """Testa que string 'GUARD' retorna GUARD"""
        result = AgentType.from_proto_value("GUARD")
        assert result == AgentType.GUARD

    def test_string_analyst_returns_analyst(self):
        """Testa que string 'ANALYST' retorna ANALYST"""
        result = AgentType.from_proto_value("ANALYST")
        assert result == AgentType.ANALYST

    def test_string_lowercase_worker_returns_worker(self):
        """Testa que string 'worker' (lowercase) retorna WORKER"""
        result = AgentType.from_proto_value("worker")
        assert result == AgentType.WORKER

    def test_string_mixed_case_scout_returns_scout(self):
        """Testa que string 'Scout' (mixed case) retorna SCOUT"""
        result = AgentType.from_proto_value("Scout")
        assert result == AgentType.SCOUT

    # Testes com strings inválidas

    def test_string_invalid_raises_value_error(self):
        """Testa que string inválida levanta ValueError"""
        with pytest.raises(ValueError) as exc_info:
            AgentType.from_proto_value("INVALID")
        assert "Invalid AgentType string value: 'INVALID'" in str(exc_info.value)

    def test_string_empty_raises_value_error(self):
        """Testa que string vazia levanta ValueError"""
        with pytest.raises(ValueError) as exc_info:
            AgentType.from_proto_value("")
        assert "Invalid AgentType string value: ''" in str(exc_info.value)

    def test_string_with_spaces_raises_value_error(self):
        """Testa que string com espaços levanta ValueError"""
        with pytest.raises(ValueError) as exc_info:
            AgentType.from_proto_value("WORKER ")
        assert "Invalid AgentType string value" in str(exc_info.value)

    # Testes com AgentType enum (passthrough)

    def test_agent_type_worker_returns_same(self):
        """Testa que AgentType.WORKER retorna o mesmo objeto"""
        input_value = AgentType.WORKER
        result = AgentType.from_proto_value(input_value)
        assert result == AgentType.WORKER
        assert result is input_value

    def test_agent_type_scout_returns_same(self):
        """Testa que AgentType.SCOUT retorna o mesmo objeto"""
        input_value = AgentType.SCOUT
        result = AgentType.from_proto_value(input_value)
        assert result == AgentType.SCOUT
        assert result is input_value

    def test_agent_type_guard_returns_same(self):
        """Testa que AgentType.GUARD retorna o mesmo objeto"""
        input_value = AgentType.GUARD
        result = AgentType.from_proto_value(input_value)
        assert result == AgentType.GUARD
        assert result is input_value

    def test_agent_type_analyst_returns_same(self):
        """Testa que AgentType.ANALYST retorna o mesmo objeto"""
        input_value = AgentType.ANALYST
        result = AgentType.from_proto_value(input_value)
        assert result == AgentType.ANALYST
        assert result is input_value

    # Testes com tipos inválidos

    def test_float_raises_value_error(self):
        """Testa que float levanta ValueError"""
        with pytest.raises(ValueError) as exc_info:
            AgentType.from_proto_value(1.5)
        assert "Cannot convert float to AgentType" in str(exc_info.value)

    def test_none_raises_value_error(self):
        """Testa que None levanta ValueError"""
        with pytest.raises(ValueError) as exc_info:
            AgentType.from_proto_value(None)
        assert "Cannot convert NoneType to AgentType" in str(exc_info.value)

    def test_list_raises_value_error(self):
        """Testa que list levanta ValueError"""
        with pytest.raises(ValueError) as exc_info:
            AgentType.from_proto_value([1])
        assert "Cannot convert list to AgentType" in str(exc_info.value)

    def test_dict_raises_value_error(self):
        """Testa que dict levanta ValueError"""
        with pytest.raises(ValueError) as exc_info:
            AgentType.from_proto_value({"type": 1})
        assert "Cannot convert dict to AgentType" in str(exc_info.value)


class TestAgentTypeEnumValues:
    """Testes para verificar valores do enum AgentType"""

    def test_worker_value_is_string_worker(self):
        """Verifica que WORKER.value é 'WORKER'"""
        assert AgentType.WORKER.value == "WORKER"

    def test_scout_value_is_string_scout(self):
        """Verifica que SCOUT.value é 'SCOUT'"""
        assert AgentType.SCOUT.value == "SCOUT"

    def test_guard_value_is_string_guard(self):
        """Verifica que GUARD.value é 'GUARD'"""
        assert AgentType.GUARD.value == "GUARD"

    def test_analyst_value_is_string_analyst(self):
        """Verifica que ANALYST.value é 'ANALYST'"""
        assert AgentType.ANALYST.value == "ANALYST"

    def test_enum_has_exactly_four_members(self):
        """Verifica que o enum tem exatamente 4 membros"""
        assert len(AgentType) == 4

    def test_enum_is_str_enum(self):
        """Verifica que AgentType é um str enum"""
        assert isinstance(AgentType.WORKER, str)
        assert isinstance(AgentType.SCOUT, str)
        assert isinstance(AgentType.GUARD, str)
        assert isinstance(AgentType.ANALYST, str)
