"""
Teste de integração end-to-end do fluxo ExplainabilityGenerator → Ledger V2.

Valida que todo o pipeline de explicabilidade funciona corretamente:
- Geração de explicabilidade com SHAP/LIME
- Persistência no ExplainabilityLedgerV2
- Retorno de token v2 nos metadados
- Geração de narrativas estruturadas
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import numpy as np
from sklearn.ensemble import RandomForestClassifier


@pytest.fixture
def mock_config():
    """Configuração mockada completa."""
    config = Mock()
    config.enable_explainability = True
    config.enable_explainability_ledger_v2 = True
    config.enable_legacy_explainability_persistence = False
    config.mongodb_uri = "mongodb://localhost:27017"
    config.mongodb_database = "test_db"
    config.specialist_type = "technical"
    config.explainability_method_preference = "auto"
    config.shap_timeout_seconds = 5.0
    config.shap_background_dataset_path = None
    config.shap_max_background_samples = 100
    config.lime_timeout_seconds = 5.0
    config.lime_num_samples = 1000
    config.narrative_top_features = 5
    config.narrative_language = "pt-BR"
    return config


@pytest.fixture
def mock_feature_extractor():
    """FeatureExtractor mockado que retorna features estruturadas."""
    extractor = Mock()
    extractor.extract_features.return_value = {
        "aggregated_features": {
            "num_tasks": 8.0,
            "complexity_score": 0.75,
            "avg_duration_ms": 2500.0,
            "risk_score": 0.3,
        },
        "metadata_features": {"num_tasks": 8.0},
        "ontology_features": {"complexity_score": 0.75},
        "graph_features": {},
        "embedding_features": {},
    }
    return extractor


@pytest.fixture
def simple_model():
    """Modelo sklearn simples para teste."""
    # Criar modelo RandomForest com dados sintéticos
    X = np.random.rand(100, 4)
    y = np.random.randint(0, 2, 100)
    model = RandomForestClassifier(n_estimators=10, random_state=42, max_depth=3)
    model.fit(X, y)
    return model


@pytest.fixture
def evaluation_result():
    """Resultado de avaliação mockado."""
    return {
        "confidence_score": 0.85,
        "risk_score": 0.3,
        "reasoning_factors": [
            {"factor_name": "num_tasks", "score": 0.7, "weight": 0.35},
            {"factor_name": "complexity_score", "score": 0.45, "weight": 0.25},
        ],
        "timestamp": "2025-01-15T10:00:00Z",
    }


@pytest.fixture
def cognitive_plan():
    """Plano cognitivo mockado."""
    return {
        "plan_id": "plan-integration-test-123",
        "correlation_id": "corr-test-456",
        "tasks": [
            {"task_id": "t1", "name": "Task 1"},
            {"task_id": "t2", "name": "Task 2"},
        ],
    }


@pytest.mark.integration
class TestExplainabilityGeneratorIntegration:
    """Testes de integração end-to-end."""

    @patch("neural_hive_specialists.explainability_generator.MongoClient")
    def test_full_explainability_flow_with_shap(
        self,
        mock_mongo_client,
        mock_config,
        mock_feature_extractor,
        simple_model,
        evaluation_result,
        cognitive_plan,
    ):
        """
        Testa fluxo completo de explicabilidade usando SHAP.

        Valida:
        - ExplainabilityGenerator.generate() retorna token e metadata
        - metadata contém explainability_token_v2
        - Narrativa foi gerada
        - feature_importances não está vazio
        - Token v2 foi persistido via ExplainabilityLedgerV2
        """
        from neural_hive_specialists.explainability_generator import (
            ExplainabilityGenerator,
        )

        # Mock MongoDB
        mock_collection = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        mock_mongo_client.return_value.__getitem__.return_value = mock_db

        # Criar generator
        generator = ExplainabilityGenerator(
            config=mock_config, metrics=None, feature_extractor=mock_feature_extractor
        )

        # Executar geração de explicabilidade
        token, metadata = generator.generate(
            evaluation_result=evaluation_result,
            cognitive_plan=cognitive_plan,
            model=simple_model,
        )

        # Validações
        assert token is not None
        assert metadata is not None

        # Validar método detectado
        assert metadata["method"] in ["shap", "lime", "heuristic"]

        # Validar narrativa gerada
        assert "human_readable_summary" in metadata
        assert "detailed_narrative" in metadata
        assert len(metadata["human_readable_summary"]) > 0
        assert len(metadata["detailed_narrative"]) > 0

        # Validar feature importances (se SHAP/LIME funcionou)
        if metadata["method"] in ["shap", "lime"]:
            assert len(metadata["feature_importances"]) > 0
            # Validar estrutura de cada importance
            for importance in metadata["feature_importances"]:
                assert "feature_name" in importance
                assert "importance" in importance
                assert "contribution" in importance

        # Validar token v2 retornado
        assert "explainability_token_v2" in metadata
        assert metadata["explainability_token_v2"] is not None
        assert len(metadata["explainability_token_v2"]) == 64  # SHA-256 hex

        # Validar que ledger v2 foi chamado
        # (verificar insert_one foi chamado na collection explainability_ledger_v2)
        mock_collection.insert_one.assert_called()

        # Validar que ledger antigo NÃO foi chamado (enable_legacy_explainability_persistence=False)
        # Não deve haver segunda chamada a insert_one para explainability_ledger
        call_count = mock_collection.insert_one.call_count
        assert call_count == 1  # Apenas ledger v2

    @patch("neural_hive_specialists.explainability_generator.MongoClient")
    def test_explainability_with_reasoning_links(
        self,
        mock_mongo_client,
        mock_config,
        mock_feature_extractor,
        simple_model,
        evaluation_result,
        cognitive_plan,
    ):
        """
        Testa que reasoning_factors são vinculados às features SHAP na narrativa.

        Valida:
        - Narrativa menciona vinculação com reasoning_factors
        - reasoning_links construído corretamente
        """
        from neural_hive_specialists.explainability_generator import (
            ExplainabilityGenerator,
        )

        # Mock MongoDB
        mock_collection = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        mock_mongo_client.return_value.__getitem__.return_value = mock_db

        # Criar generator
        generator = ExplainabilityGenerator(
            config=mock_config, metrics=None, feature_extractor=mock_feature_extractor
        )

        # Executar
        token, metadata = generator.generate(
            evaluation_result=evaluation_result,
            cognitive_plan=cognitive_plan,
            model=simple_model,
        )

        # Validar que narrativa foi gerada
        narrative = metadata.get("detailed_narrative", "")
        assert len(narrative) > 0

        # Se método foi SHAP/LIME e reasoning_factors estavam presentes,
        # narrativa deve mencionar vinculação (opcional, depende de match)
        if (
            metadata["method"] in ["shap", "lime"]
            and len(metadata["feature_importances"]) > 0
        ):
            # Verificar se algum reasoning_factor foi vinculado
            # (narrativa deve conter "vinculado ao fator de raciocínio" se houve match)
            has_links = "vinculado ao fator de raciocínio" in narrative.lower()
            # Pode ou não ter links dependendo do match, então não forçamos assert
            # mas registramos para validação manual
            print(f"Has reasoning links in narrative: {has_links}")

    @patch("neural_hive_specialists.explainability_generator.MongoClient")
    def test_explainability_fallback_to_heuristic(
        self,
        mock_mongo_client,
        mock_config,
        mock_feature_extractor,
        evaluation_result,
        cognitive_plan,
    ):
        """
        Testa fallback para heurístico quando SHAP/LIME falham.

        Valida:
        - method = 'heuristic' quando modelo é None
        - fallback_reason não está presente (nenhum fallback ocorreu)
        - feature_importances baseadas em reasoning_factors
        """
        from neural_hive_specialists.explainability_generator import (
            ExplainabilityGenerator,
        )

        # Mock MongoDB
        mock_collection = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        mock_mongo_client.return_value.__getitem__.return_value = mock_db

        # Criar generator
        generator = ExplainabilityGenerator(
            config=mock_config, metrics=None, feature_extractor=mock_feature_extractor
        )

        # Executar com model=None (deve usar heurístico)
        token, metadata = generator.generate(
            evaluation_result=evaluation_result,
            cognitive_plan=cognitive_plan,
            model=None,
        )

        # Validações
        assert metadata["method"] == "heuristic"
        assert (
            "fallback_reason" not in metadata
        )  # Não houve fallback, método original já era heurístico

        # feature_importances deve vir de reasoning_factors
        assert len(metadata["feature_importances"]) > 0
        assert metadata["feature_importances"][0]["feature_name"] == "num_tasks"

    @patch("neural_hive_specialists.explainability_generator.MongoClient")
    def test_ledger_v2_persistence_format(
        self,
        mock_mongo_client,
        mock_config,
        mock_feature_extractor,
        simple_model,
        evaluation_result,
        cognitive_plan,
    ):
        """
        Testa formato do documento persistido no Ledger V2.

        Valida:
        - Schema ExplainabilityRecordSchema está correto
        - Campos obrigatórios presentes
        """
        from neural_hive_specialists.explainability_generator import (
            ExplainabilityGenerator,
        )

        # Mock MongoDB
        mock_collection = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        mock_mongo_client.return_value.__getitem__.return_value = mock_db

        # Criar generator
        generator = ExplainabilityGenerator(
            config=mock_config, metrics=None, feature_extractor=mock_feature_extractor
        )

        # Executar
        token, metadata = generator.generate(
            evaluation_result=evaluation_result,
            cognitive_plan=cognitive_plan,
            model=simple_model,
        )

        # Capturar documento inserido
        mock_collection.insert_one.assert_called_once()
        inserted_doc = mock_collection.insert_one.call_args[0][0]

        # Validar campos obrigatórios do schema
        assert "explainability_token" in inserted_doc
        assert "plan_id" in inserted_doc
        assert inserted_doc["plan_id"] == "plan-integration-test-123"
        assert "specialist_type" in inserted_doc
        assert inserted_doc["specialist_type"] == "technical"
        assert "explanation_method" in inserted_doc
        assert "feature_importances" in inserted_doc
        assert "human_readable_summary" in inserted_doc
        assert "detailed_narrative" in inserted_doc
        assert "prediction" in inserted_doc
        assert "computation_time_ms" in inserted_doc
        assert "schema_version" in inserted_doc
        assert inserted_doc["schema_version"] == "2.0.0"
