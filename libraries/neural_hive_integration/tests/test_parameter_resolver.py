"""
Testes unitários para a camada de tradução semântica→técnica de parâmetros.

Cobre a lacuna corrigida: o caminho heurístico do STE gera parâmetros semânticos
(objective/entities/constraints) que os executores do worker não conseguem processar
(query_executor exige `collection`). O resolver completa-os para o contrato técnico.
"""

import pytest

from neural_hive_integration.orchestration.parameter_resolver import (
    DEFAULT_QUERY_DATABASE,
    DEFAULT_QUERY_LIMIT,
    FALLBACK_COLLECTION,
    resolve_ticket_parameters,
)


class TestResolveQueryHeuristico:
    """Caminho heurístico: params semânticos → contrato técnico."""

    def test_query_security_mapeia_para_security_incidents(self):
        params = {"objective": "query", "entities": ["OAuth2", "MFA"], "constraints": {}}
        result = resolve_ticket_parameters("QUERY", params, domain="SECURITY")

        assert result["query_type"] == "mongodb"
        assert result["collection"] == "security_incidents"
        assert result["database"] == DEFAULT_QUERY_DATABASE
        assert result["limit"] == DEFAULT_QUERY_LIMIT
        assert result["filter"] == {}
        assert result["resolved_from_entities"] == ["OAuth2", "MFA"]

    def test_dominio_desconhecido_usa_fallback(self):
        result = resolve_ticket_parameters("QUERY", {"objective": "q"}, domain=None)
        assert result["collection"] == FALLBACK_COLLECTION

    @pytest.mark.parametrize(
        ("domain", "expected"),
        [
            ("security", "security_incidents"),
            ("business", "insights"),
            ("evolution", "optimization_ledger"),
            ("behavior", "specialist_feedback"),
            ("architecture", "operational_context"),
        ],
    )
    def test_mapeamento_por_dominio(self, domain, expected):
        result = resolve_ticket_parameters("QUERY", {"objective": "q"}, domain=domain)
        assert result["collection"] == expected

    def test_dominio_case_insensitive(self):
        result = resolve_ticket_parameters("QUERY", {"objective": "q"}, domain="Security")
        assert result["collection"] == "security_incidents"


class TestNormalizacaoEntities:
    """O campo entities pode chegar em vários formatos (efeito do schema Avro)."""

    def test_string_serializada_aspas_simples(self):
        # Formato observado no smoke real (str com aspas simples).
        params = {"objective": "q", "entities": "[{'value': 'OAuth2'}, {'value': 'MFA'}]"}
        result = resolve_ticket_parameters("QUERY", params, domain="security")
        assert result["resolved_from_entities"] == ["OAuth2", "MFA"]

    def test_lista_de_dicts(self):
        params = {"objective": "q", "entities": [{"value": "A"}, {"name": "B"}]}
        result = resolve_ticket_parameters("QUERY", params, domain="security")
        assert result["resolved_from_entities"] == ["A", "B"]

    def test_lista_de_strings(self):
        params = {"objective": "q", "entities": ["X", "Y"]}
        result = resolve_ticket_parameters("QUERY", params, domain="security")
        assert result["resolved_from_entities"] == ["X", "Y"]

    def test_entities_vazio_ou_ausente(self):
        result = resolve_ticket_parameters("QUERY", {"objective": "q"}, domain="security")
        assert result["resolved_from_entities"] == []


class TestIdempotencia:
    """Caminho template: collection/filter/limit preservados; query_type/database garantidos."""

    def test_query_com_collection_preserva_e_garante_db(self):
        params = {"collection": "ldap", "filter": {"x": 1}, "limit": 100}
        result = resolve_ticket_parameters("QUERY", params, domain="SECURITY")
        # collection/filter/limit do template são preservados
        assert result["collection"] == "ldap"
        assert result["filter"] == {"x": 1}
        assert result["limit"] == 100
        # query_type e database são garantidos (template não os fornece)
        assert result["query_type"] == "mongodb"
        assert result["database"] == "neural_hive"

    def test_query_type_existente_preservado(self):
        params = {"query_type": "neo4j", "cypher_query": "MATCH (n) RETURN n", "collection": "x"}
        result = resolve_ticket_parameters("QUERY", params, domain="security")
        assert result["query_type"] == "neo4j"

    def test_database_explicito_preservado(self):
        params = {"objective": "q", "database": "custom_db"}
        result = resolve_ticket_parameters("QUERY", params, domain="security")
        assert result["database"] == "custom_db"


class TestOutrosTaskTypes:
    """Task types sem resolução dedicada passam intactos."""

    @pytest.mark.parametrize("task_type", ["TRANSFORM", "VALIDATE", "EXECUTE", "BUILD", "DEPLOY"])
    def test_passa_intacto(self, task_type):
        params = {"policy_path": "/x", "input_data": {"a": 1}}
        result = resolve_ticket_parameters(task_type, params, domain="security")
        assert result == params

    def test_task_type_lowercase_normalizado(self):
        # O dispatcher normaliza para upper; "query" deve ser tratado como QUERY.
        result = resolve_ticket_parameters("query", {"objective": "q"}, domain="security")
        assert result["collection"] == "security_incidents"


class TestEntradasDegeneradas:
    """Robustez a entradas nulas/vazias."""

    def test_parameters_none(self):
        result = resolve_ticket_parameters("QUERY", None, domain="security")
        assert result["collection"] == "security_incidents"

    def test_parameters_vazio(self):
        result = resolve_ticket_parameters("QUERY", {}, domain="security")
        assert result["collection"] == "security_incidents"

    def test_nao_muta_input_original(self):
        params = {"objective": "q", "entities": ["A"]}
        original = dict(params)
        resolve_ticket_parameters("QUERY", params, domain="security")
        assert params == original  # input não foi mutado
