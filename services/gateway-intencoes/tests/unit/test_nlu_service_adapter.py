"""Testes unitários para o NLUServiceAdapter.

Cobre a lacuna que originou os bugs #131/#132/#133: a resposta do NLU Service
chega como protobuf, onde os campos enum (`UnifiedDomain`, `EntityType`) são
representados em Python como `int`. O adapter tem de os converter para os tipos
que o modelo Pydantic local (`UnifiedDomain` / `Entity.type: str`) espera.

Antes da correção, o adapter usava o int cru:
  - `_convert_domain(4)` → `(4).upper()` → AttributeError → fallback silencioso.
  - `Entity(type=4)` → Pydantic ValidationError → fallback silencioso.

O `try/except` amplo do `process()` mascarava ambos como "low confidence 0.4",
escondendo a classificação real (ex.: SECURITY). Estes testes garantem que a
desserialização proto→Pydantic permanece correta.
"""

from proto import nlu_pb2
from services.nlu_service_adapter import NLUServiceAdapter


def _adapter() -> NLUServiceAdapter:
    """Adapter sem clients — os métodos de conversão são puros."""
    return NLUServiceAdapter(nlu_client=None, pii_client=None)


class TestConvertDomainEnumProto:
    """`domain` chega como enum proto UnifiedDomain (int)."""

    def test_security_int_mapeia_para_security(self):
        # SECURITY = 4 no proto; tem de resolver para UnifiedDomain.SECURITY.
        result = _adapter()._convert_domain(nlu_pb2.UnifiedDomain.SECURITY)
        assert result.value.upper() == "SECURITY"

    def test_business_int(self):
        result = _adapter()._convert_domain(nlu_pb2.UnifiedDomain.BUSINESS)
        assert result.value.upper() == "BUSINESS"

    def test_domain_unknown_int_cai_em_technical(self):
        result = _adapter()._convert_domain(nlu_pb2.UnifiedDomain.DOMAIN_UNKNOWN)
        assert result.value.upper() == "TECHNICAL"

    def test_aceita_string_por_robustez(self):
        # Caminho legado/robustez: string já com o nome do domínio.
        result = _adapter()._convert_domain("SECURITY")
        assert result.value.upper() == "SECURITY"

    def test_int_invalido_cai_em_technical(self):
        # Valor fora do enum não deve rebentar — fallback TECHNICAL.
        result = _adapter()._convert_domain(9999)
        assert result.value.upper() == "TECHNICAL"


class TestEntityTypeNameEnumProto:
    """`entity.type` chega como enum proto EntityType (int)."""

    def test_loc_int_mapeia_para_nome(self):
        # LOC = 4 no proto.
        assert _adapter()._entity_type_name(nlu_pb2.EntityType.LOC) == "LOC"

    def test_person_int(self):
        assert _adapter()._entity_type_name(nlu_pb2.EntityType.PERSON) == "PERSON"

    def test_unknown_int(self):
        assert (
            _adapter()._entity_type_name(nlu_pb2.EntityType.ENTITY_UNKNOWN)
            == "ENTITY_UNKNOWN"
        )

    def test_aceita_string_por_robustez(self):
        assert _adapter()._entity_type_name("ORG") == "ORG"

    def test_int_invalido_cai_em_unknown(self):
        assert _adapter()._entity_type_name(9999) == "ENTITY_UNKNOWN"
