"""Testes unitários para ArchitectureSpecialist._log_low_confidence_diagnostic.

Cobre o comportamento observável do diagnóstico de baixa confiança introduzido
para confirmar o desalinhamento treino/runtime (architecture-cal-0.025-confidence):
- threshold de 0.3 (early return sem log);
- ``gap_severity`` correcto consoante o modelo está ou não carregado;
- campos do log estruturado;
- robustez (nunca propaga excepção).
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

# Configurar paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
sys.path.insert(0, "/app/libraries/python")

from specialist import ArchitectureSpecialist


def _make_specialist(model, expected_names, expected_n):
    """Cria um ArchitectureSpecialist sem invocar __init__ (deps pesadas).

    Apenas os atributos/métodos tocados por _log_low_confidence_diagnostic são
    definidos: self.model e self._get_expected_model_features().
    """
    specialist = object.__new__(ArchitectureSpecialist)
    specialist.model = model
    specialist._get_expected_model_features = MagicMock(return_value=(expected_names, expected_n))
    return specialist


EXPECTED_NAMES = [
    "design_patterns_score",
    "solid_score",
    "coupling_cohesion_score",
    "separation_score",
    "modularity_score",
    "modularity_extra",
]


class TestLowConfidenceDiagnostic:
    """Testes do diagnóstico estruturado de baixa confiança."""

    def test_above_threshold_does_not_log(self):
        """Confiança >= 0.3 retorna sem emitir warning de diagnóstico."""
        specialist = _make_specialist(MagicMock(), EXPECTED_NAMES, len(EXPECTED_NAMES))
        logger_mock = MagicMock()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("specialist.logger", logger_mock)
            specialist._log_low_confidence_diagnostic({"plan_id": "p-1"}, 0.5)

        logger_mock.warning.assert_not_called()

    def test_at_threshold_does_not_log(self):
        """Confiança exactamente 0.3 está fora do diagnóstico (>=)."""
        specialist = _make_specialist(MagicMock(), EXPECTED_NAMES, len(EXPECTED_NAMES))
        logger_mock = MagicMock()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("specialist.logger", logger_mock)
            specialist._log_low_confidence_diagnostic({"plan_id": "p-1"}, 0.3)

        logger_mock.warning.assert_not_called()

    def test_low_confidence_with_model_loaded_is_critical(self):
        """Modelo carregado + confiança ~0.025 => gap_severity CRITICAL.

        Valida o caso grave (architecture-cal-0.025-confidence): a branch
        'CRITICAL' deixa de ser código morto.
        """
        specialist = _make_specialist(MagicMock(), EXPECTED_NAMES, len(EXPECTED_NAMES))
        logger_mock = MagicMock()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("specialist.logger", logger_mock)
            specialist._log_low_confidence_diagnostic({"plan_id": "p-low"}, 0.025)

        logger_mock.warning.assert_called_once()
        kwargs = logger_mock.warning.call_args.kwargs
        assert logger_mock.warning.call_args.args[0] == "diagnostic_low_confidence"
        assert kwargs["plan_id"] == "p-low"
        assert kwargs["confidence_score"] == 0.025
        assert kwargs["model_loaded"] is True
        assert kwargs["feature_alignment_gap_severity"] == "CRITICAL"
        assert kwargs["model_feature_schema"] == sorted(EXPECTED_NAMES)
        assert kwargs["model_feature_count"] == len(EXPECTED_NAMES)

    def test_low_confidence_without_model_is_partial(self):
        """Sem modelo carregado mas com schema esperado => PARTIAL.

        Caso defensivo: expected_names presente embora self.model seja None
        (improvável em runtime). Cobre o ramo alternativo da condição.
        """
        specialist = _make_specialist(None, EXPECTED_NAMES, len(EXPECTED_NAMES))
        logger_mock = MagicMock()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("specialist.logger", logger_mock)
            specialist._log_low_confidence_diagnostic({"plan_id": "p-part"}, 0.1)

        logger_mock.warning.assert_called_once()
        kwargs = logger_mock.warning.call_args.kwargs
        assert kwargs["model_loaded"] is False
        assert kwargs["feature_alignment_gap_severity"] == "PARTIAL"

    def test_low_confidence_without_expected_schema_is_unknown(self):
        """Sem schema esperado determinável => gap_severity UNKNOWN."""
        specialist = _make_specialist(None, None, None)
        logger_mock = MagicMock()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("specialist.logger", logger_mock)
            specialist._log_low_confidence_diagnostic({"plan_id": "p-unk"}, 0.1)

        logger_mock.warning.assert_called_once()
        kwargs = logger_mock.warning.call_args.kwargs
        assert kwargs["feature_alignment_gap_severity"] == "UNKNOWN"
        assert kwargs["model_feature_schema"] is None
        assert kwargs["model_feature_count"] is None

    def test_diagnostic_never_propagates_exception(self):
        """Falhas internas do diagnóstico não interrompem a avaliação."""
        specialist = object.__new__(ArchitectureSpecialist)
        specialist.model = MagicMock()
        # Forçar excepção dentro do try defensivo.
        specialist._get_expected_model_features = MagicMock(side_effect=RuntimeError("boom"))

        # Não deve levantar.
        specialist._log_low_confidence_diagnostic({"plan_id": "p-err"}, 0.01)
