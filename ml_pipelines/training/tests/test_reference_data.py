#!/usr/bin/env python3
"""
Testes para Reference Data do Drift Detector

Valida a estrutura e conteúdo dos arquivos de referência usados
para detecção de drift no modelo de aprovação.

Version: 1.0.0
Date: 2026-04-24
"""

import pickle
from pathlib import Path

import pytest


class TestReferenceData:
    """Testes para reference data do drift detector."""

    # Caminho para a reference data
    REFERENCE_DATA_PATH = Path("ml_pipelines/training/reference_data/approval_v7_reference.pkl")

    # Features esperadas (30)
    EXPECTED_FEATURES = [
        "specialist_confidence",
        "domain_security",
        "domain_performance",
        "domain_database",
        "domain_devops",
        "domain_testing",
        "action_create",
        "action_update",
        "action_delete",
        "action_read",
        "action_deploy",
        "has_backup",
        "has_verification",
        "has_all",
        "text_length_chars",
        "text_length_words",
        "risk_high",
        "risk_medium",
        "risk_low",
        "simple_risk_score",
        "primary_domain_security",
        "primary_domain_performance",
        "primary_domain_database",
        "primary_domain_devops",
        "primary_domain_testing",
        "primary_action_create",
        "primary_action_update",
        "primary_action_delete",
        "primary_action_read",
        "primary_action_deploy",
    ]

    @pytest.fixture
    def reference_data(self):
        """Carrega reference data do arquivo."""
        if not self.REFERENCE_DATA_PATH.exists():
            pytest.skip(f"Reference data não encontrada: {self.REFERENCE_DATA_PATH}")

        with open(self.REFERENCE_DATA_PATH, "rb") as f:
            return pickle.load(f)

    def test_reference_data_exists(self):
        """Testa se arquivo de reference data existe."""
        assert self.REFERENCE_DATA_PATH.exists(), (
            f"Reference data não encontrada: {self.REFERENCE_DATA_PATH}. "
            "Execute: python ml_pipelines/training/generate_reference_data.py"
        )

    def test_reference_data_structure(self, reference_data):
        """Testa estrutura da reference data."""
        assert "metadata" in reference_data, "Reference data deve conter 'metadata'"
        assert "data" in reference_data, "Reference data deve conter 'data'"

    def test_metadata_structure(self, reference_data):
        """Testa estrutura dos metadados."""
        metadata = reference_data["metadata"]

        required_fields = [
            "model_name",
            "model_version",
            "created_at",
            "training_samples",
            "features",
            "feature_stats",
        ]

        for field in required_fields:
            assert field in metadata, f"Metadata deve conter '{field}'"

    def test_metadata_values(self, reference_data):
        """Testa valores dos metadados."""
        metadata = reference_data["metadata"]

        assert metadata["model_name"] == "approval_predictor"
        assert metadata["model_version"] == "v7"
        assert metadata["training_samples"] >= 50, "Deve ter pelo menos 50 amostras"
        assert len(metadata["features"]) == 30, "Deve ter 30 features"

    def test_features_list(self, reference_data):
        """Testa lista de features nos metadados."""
        features = reference_data["metadata"]["features"]

        assert len(features) == 30, f"Esperado 30 features, encontrado {len(features)}"

        # Verificar que todas as features esperadas estão presentes
        for expected_feature in self.EXPECTED_FEATURES:
            assert (
                expected_feature in features
            ), f"Feature esperada '{expected_feature}' não encontrada na lista"

    def test_dataframe_structure(self, reference_data):
        """Testa estrutura do DataFrame."""
        df = reference_data["data"]

        # Verificar shape
        assert df.shape[0] >= 50, "DataFrame deve ter pelo menos 50 linhas (amostras)"
        assert df.shape[1] == 30, "DataFrame deve ter 30 colunas (features)"

        # Verificar colunas
        columns = list(df.columns)
        for expected_feature in self.EXPECTED_FEATURES:
            assert (
                expected_feature in columns
            ), f"Coluna esperada '{expected_feature}' não encontrada no DataFrame"

    def test_feature_stats(self, reference_data):
        """Testa estatísticas das features."""
        feature_stats = reference_data["metadata"]["feature_stats"]

        # Verificar que temos stats para todas as 30 features
        assert len(feature_stats) == 30, "Deve ter estatísticas para 30 features"

        # Verificar estrutura das estatísticas de cada feature
        for feature_name, stats in feature_stats.items():
            required_stats = ["mean", "std", "min", "max", "q25", "q50", "q75"]
            for stat in required_stats:
                assert stat in stats, f"Feature '{feature_name}' deve ter estatística '{stat}'"

            # Verificar que são valores numéricos
            for stat_name, stat_value in stats.items():
                assert isinstance(
                    stat_value, (int, float)
                ), f"Stat '{stat_name}' da feature '{feature_name}' deve ser numérico"

    def test_feature_ranges(self, reference_data):
        """Testa ranges válidos para as features."""
        df = reference_data["data"]

        # specialist_confidence deve estar entre 0 e 1
        assert df["specialist_confidence"].min() >= 0.0, "specialist_confidence min >= 0"
        assert df["specialist_confidence"].max() <= 1.0, "specialist_confidence max <= 1"

        # Domínios devem ser binários (0 ou 1)
        domain_features = [f"domain_{d}" for d in ["security", "performance", "database", "devops", "testing"]]
        for feature in domain_features:
            assert df[feature].isin([0.0, 1.0]).all(), f"{feature} deve ser binário (0 ou 1)"

        # Ações devem ser binárias
        action_features = [f"action_{a}" for a in ["create", "update", "delete", "read", "deploy"]]
        for feature in action_features:
            assert df[feature].isin([0.0, 1.0]).all(), f"{feature} deve ser binário (0 ou 1)"

        # text_length_chars deve ser positivo
        assert (df["text_length_chars"] >= 0).all(), "text_length_chars deve ser >= 0"

        # simple_risk_score deve estar entre 0 e 1
        assert df["simple_risk_score"].min() >= 0.0, "simple_risk_score min >= 0"
        assert df["simple_risk_score"].max() <= 1.0, "simple_risk_score max <= 1"

    def test_domain_distribution(self, reference_data):
        """Testa distribuição de domínios (deve ter variedade)."""
        df = reference_data["data"]

        # Cada domínio primário deve ter pelo menos algumas amostras
        primary_domain_features = [f"primary_domain_{d}" for d in ["security", "performance", "database", "devops", "testing"]]

        for feature in primary_domain_features:
            count = df[feature].sum()
            assert count >= 5, f"Domínio primário '{feature}' deve ter pelo menos 5 amostras, encontrado {count}"

    def test_action_distribution(self, reference_data):
        """Testa distribuição de ações (deve ter variedade)."""
        df = reference_data["data"]

        # Cada ação primária deve ter pelo menos algumas amostras
        primary_action_features = [f"primary_action_{a}" for a in ["create", "update", "delete", "read", "deploy"]]

        for feature in primary_action_features:
            count = df[feature].sum()
            assert count >= 2, f"Ação primária '{feature}' deve ter pelo menos 2 amostras, encontrado {count}"

    def test_metadata_file_exists(self):
        """Testa se arquivo de metadados JSON existe."""
        metadata_path = self.REFERENCE_DATA_PATH.with_suffix(".metadata.json")
        assert metadata_path.exists(), f"Metadata JSON não encontrado: {metadata_path}"


def test_reference_data_validation():
    """
    Teste rápido de validação da reference data.

    Pode ser executado standalone para verificar se a reference data está válida.
    """
    reference_path = Path("ml_pipelines/training/reference_data/approval_v7_reference.pkl")

    if not reference_path.exists():
        print(f"❌ Reference data não encontrada: {reference_path}")
        print("   Execute: python ml_pipelines/training/generate_reference_data.py")
        assert False, "Reference data não encontrada"

    with open(reference_path, "rb") as f:
        reference_data = pickle.load(f)

    metadata = reference_data["metadata"]
    df = reference_data["data"]

    # Validações básicas
    checks = [
        (df.shape[0] >= 50, f"Amostras: {df.shape[0]} >= 50"),
        (df.shape[1] == 30, f"Features: {df.shape[1]} == 30"),
        (len(metadata["features"]) == 30, f"Metadata features: {len(metadata['features'])} == 30"),
    ]

    all_passed = True
    for passed, description in checks:
        status = "✅" if passed else "❌"
        print(f"{status} {description}")
        if not passed:
            all_passed = False

    if all_passed:
        print(f"\n✅ Reference data válida: {metadata['training_samples']} amostras, {df.shape[1]} features")

    assert all_passed, "Reference data inválida"


if __name__ == "__main__":
    import sys

    success = test_reference_data_validation()
    sys.exit(0 if success else 1)
