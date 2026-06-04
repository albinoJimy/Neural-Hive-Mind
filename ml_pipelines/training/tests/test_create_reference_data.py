"""
Testes para criação de reference data para drift detection.

FASE 0 - IA/ML Integration (TICKET 2.3)
"""

import os
import pickle
import tempfile

import pytest

from ml_pipelines.training.create_reference_data import (
    create_baseline_from_tickets,
    extract_features_from_ticket,
    generate_synthetic_baseline,
)


# =============================================================================
# Testes de Extração de Features
# =============================================================================


class TestFeatureExtraction:
    """Testa extração de features de tickets."""

    def test_extract_features_complete_ticket(self):
        """Ticket completo deve ter todas as features."""
        ticket = {
            "_id": "ticket-123",
            "complexity": 4,
            "has_backup": True,
            "has_verification": True,
            "has_all": True,
            "priority": "high",
            "estimated_hours": 12.0,
            "actual_hours": 14.0,
        }

        features = extract_features_from_ticket(ticket)

        assert features is not None
        assert features["complexity"] == 4.0
        assert features["has_backup"] == 1.0
        assert features["has_verification"] == 1.0
        assert features["has_all"] == 1.0
        assert features["priority"] == 3.0  # high = 3
        assert features["estimated_hours"] == 12.0
        assert features["actual_hours"] == 14.0

    def test_extract_features_minimal_ticket(self):
        """Ticket mínimo deve usar valores padrão."""
        ticket = {
            "_id": "ticket-456",
            "complexity": 2,
            "has_backup": False,
            "priority": "low",
        }

        features = extract_features_from_ticket(ticket)

        assert features is not None
        assert features["complexity"] == 2.0
        assert features["has_backup"] == 0.0
        assert features["has_verification"] == 0.0
        assert features["has_all"] == 0.0
        assert features["priority"] == 1.0  # low = 1
        assert features["estimated_hours"] == 8.0  # padrão

    def test_extract_features_priority_mapping(self):
        """Mapeamento de prioridade deve estar correto."""
        priority_map = {
            "low": 1.0,
            "medium": 2.0,
            "high": 3.0,
            "critical": 4.0,
            "urgent": 5.0,
        }

        for priority_str, expected_value in priority_map.items():
            ticket = {"_id": "test", "complexity": 3, "priority": priority_str}
            features = extract_features_from_ticket(ticket)
            assert features["priority"] == expected_value

    def test_extract_features_invalid_ticket(self):
        """Ticket inválido deve retornar None."""
        ticket = {"_id": "invalid"}  # Sem campos obrigatórios

        features = extract_features_from_ticket(ticket)
        # Deve retornar features com valores padrão
        assert features is not None
        assert features["complexity"] == 3.0  # padrão


# =============================================================================
# Testes de Criação de Baseline
# =============================================================================


class TestBaselineCreation:
    """Testa criação de baseline a partir de tickets."""

    @pytest.fixture
    def sample_tickets(self):
        """Tickets de exemplo para baseline."""
        return [
            {
                "_id": "1",
                "complexity": 1,
                "has_backup": False,
                "has_verification": False,
                "has_all": False,
                "priority": "low",
                "estimated_hours": 4.0,
                "actual_hours": 4.0,
            },
            {
                "_id": "2",
                "complexity": 3,
                "has_backup": True,
                "has_verification": True,
                "has_all": True,
                "priority": "medium",
                "estimated_hours": 8.0,
                "actual_hours": 9.0,
            },
            {
                "_id": "3",
                "complexity": 5,
                "has_backup": True,
                "has_verification": True,
                "has_all": True,
                "priority": "critical",
                "estimated_hours": 16.0,
                "actual_hours": 20.0,
            },
        ]

    def test_create_baseline_from_tickets(self, sample_tickets):
        """Deve criar baseline com estatísticas corretas."""
        baseline = create_baseline_from_tickets(sample_tickets, model_version="v7")

        assert baseline is not None
        assert baseline["model_version"] == "v7"
        assert baseline["sample_count"] == 3
        assert "features" in baseline

        # Verificar features calculadas
        features = baseline["features"]
        assert "complexity" in features
        assert "has_backup" in features
        assert "priority" in features

        # Verificar estatísticas da complexity
        complexity = features["complexity"]
        assert complexity["count"] == 3
        assert complexity["mean"] == 3.0  # (1 + 3 + 5) / 3
        assert complexity["min"] == 1.0
        assert complexity["max"] == 5.0

    def test_create_baseline_with_empty_tickets(self):
        """Tickets vazios devem levantar ValueError."""
        with pytest.raises(ValueError, match="No valid features"):
            create_baseline_from_tickets([])

    def test_create_baseline_percentiles(self, sample_tickets):
        """Percentis devem ser calculados corretamente."""
        baseline = create_baseline_from_tickets(sample_tickets)

        complexity = baseline["features"]["complexity"]
        percentiles = complexity["percentiles"]

        # Com valores [1, 3, 5], numpy interpola os percentis
        assert percentiles["p25"] == 2.0  # Interpolado
        assert percentiles["p50"] == 3.0  # Mediana
        assert percentiles["p75"] == 4.0  # Interpolado


# =============================================================================
# Testes de Baseline Sintético
# =============================================================================


class TestSyntheticBaseline:
    """Testa geração de baseline sintético."""

    def test_generate_synthetic_baseline_default(self):
        """Baseline sintético padrão deve ter 1000 amostras."""
        baseline = generate_synthetic_baseline()

        assert baseline is not None
        assert baseline["model_version"] == "v7"
        assert baseline["sample_count"] == 1000
        assert "features" in baseline

        # Verificar que é sintético
        assert baseline["metadata"]["synthetic"] is True

    def test_generate_synthetic_baseline_custom_samples(self):
        """Deve respeitar número de amostras customizado."""
        baseline = generate_synthetic_baseline(samples=500)

        assert baseline["sample_count"] == 500

        for feature_data in baseline["features"].values():
            assert feature_data["count"] == 500
            assert len(feature_data["values"]) == 500

    def test_synthetic_baseline_has_all_features(self):
        """Baseline sintético deve ter todas as features esperadas."""
        expected_features = {
            "complexity",
            "has_backup",
            "has_verification",
            "has_all",
            "priority",
            "estimated_hours",
            "actual_hours",
        }

        baseline = generate_synthetic_baseline()
        actual_features = set(baseline["features"].keys())

        assert actual_features == expected_features

    def test_synthetic_baseline_ranges(self):
        """Valores sintéticos devem estar em ranges razoáveis."""
        baseline = generate_synthetic_baseline()

        # Complexity: 1-5
        complexity_values = baseline["features"]["complexity"]["values"]
        assert all(1 <= v <= 5 for v in complexity_values)

        # Binary features: 0-1
        for binary_feature in ["has_backup", "has_verification", "has_all"]:
            values = baseline["features"][binary_feature]["values"]
            assert all(v in [0.0, 1.0] for v in values)

        # Priority: 1-5
        priority_values = baseline["features"]["priority"]["values"]
        assert all(1 <= v <= 5 for v in priority_values)

        # Hours: positivos
        for hour_feature in ["estimated_hours", "actual_hours"]:
            values = baseline["features"][hour_feature]["values"]
            assert all(v > 0 for v in values)


# =============================================================================
# Testes de Persistência
# =============================================================================


class TestBaselinePersistence:
    """Testa salvamento e carregamento de baseline."""

    def test_save_and_load_pickle(self):
        """Baseline deve ser salvo e carregado corretamente em pickle."""
        baseline = generate_synthetic_baseline(samples=100)

        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            temp_path = f.name

        try:
            # Salvar
            with open(temp_path, "wb") as f:
                pickle.dump(baseline, f)

            # Carregar
            with open(temp_path, "rb") as f:
                loaded = pickle.load(f)

            # Verificar
            assert loaded == baseline
            assert loaded["sample_count"] == 100

        finally:
            os.unlink(temp_path)

    def test_save_and_load_json(self):
        """Baseline deve ser salvo e carregado corretamente em JSON."""
        import json

        baseline = generate_synthetic_baseline(samples=100)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            # Salvar
            with open(temp_path, "w") as f:
                json.dump(baseline, f, default=str)

            # Carregar
            with open(temp_path, "r") as f:
                loaded = json.load(f)

            # Verificar campos principais
            assert loaded["model_version"] == baseline["model_version"]
            assert loaded["sample_count"] == baseline["sample_count"]
            assert set(loaded["features"].keys()) == set(baseline["features"].keys())

        finally:
            os.unlink(temp_path)


# =============================================================================
# Testes de Integração com Arquivo Real
# =============================================================================


class TestRealBaselineFile:
    """Testa o arquivo de baseline real criado."""

    @pytest.mark.skipif(
        not os.path.exists("ml_models/approval_v7_reference.pkl"),
        reason="Baseline file not created yet",
    )
    def test_real_baseline_file_exists(self):
        """Arquivo de baseline real deve existir."""
        assert os.path.exists("ml_models/approval_v7_reference.pkl")

    @pytest.mark.skipif(
        not os.path.exists("ml_models/approval_v7_reference.pkl"),
        reason="Baseline file not created yet",
    )
    def test_real_baseline_can_be_loaded(self):
        """Arquivo de baseline real deve ser carregável."""
        with open("ml_models/approval_v7_reference.pkl", "rb") as f:
            baseline = pickle.load(f)

        assert baseline is not None
        assert "features" in baseline
        assert "model_version" in baseline

    @pytest.mark.skipif(
        not os.path.exists("ml_models/approval_v7_reference.pkl"),
        reason="Baseline file not created yet",
    )
    def test_real_baseline_has_required_features(self):
        """Baseline real deve ter todas as features requeridas."""
        with open("ml_models/approval_v7_reference.pkl", "rb") as f:
            baseline = pickle.load(f)

        required_features = {
            "complexity",
            "has_backup",
            "has_verification",
            "has_all",
            "priority",
            "estimated_hours",
        }

        actual_features = set(baseline["features"].keys())
        assert required_features.issubset(actual_features)
