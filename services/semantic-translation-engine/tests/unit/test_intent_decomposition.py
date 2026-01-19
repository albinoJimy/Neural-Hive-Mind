"""
Testes unitários para decomposição de intents baseada em templates.

Testa:
- IntentClassifier: classificação de intents por tipo
- DecompositionTemplates: geração de tasks a partir de templates
- Integração com DAGGenerator
"""

import pytest
from unittest.mock import MagicMock, patch

from src.services.intent_classifier import IntentClassifier, IntentType, IntentClassification
from src.services.decomposition_templates import DecompositionTemplates, TaskTemplate
from src.services.dag_generator import DAGGenerator


class TestIntentClassifier:
    """Testes para classificação de intents."""

    @pytest.fixture
    def classifier(self):
        """IntentClassifier sem modelo de embeddings (apenas padrões)."""
        return IntentClassifier(config={'intent_classification_min_confidence': 0.3})

    def test_classify_viability_analysis_portuguese(self, classifier):
        """Testa classificação de análise de viabilidade em português."""
        intent = "Analisar viabilidade técnica de migração do sistema de autenticação para OAuth2"

        classification = classifier.classify(intent)

        assert classification.intent_type == IntentType.VIABILITY_ANALYSIS
        assert classification.confidence >= 0.3
        assert classification.recommended_task_count >= 6
        assert 'security' in classification.semantic_domains or 'architecture' in classification.semantic_domains

    def test_classify_migration_portuguese(self, classifier):
        """Testa classificação de migração em português."""
        intent = "Migrar banco de dados de PostgreSQL para MongoDB"

        classification = classifier.classify(intent)

        assert classification.intent_type == IntentType.MIGRATION
        assert classification.confidence >= 0.3

    def test_classify_security_audit_english(self, classifier):
        """Testa classificação de auditoria de segurança em inglês."""
        intent = "Perform security audit on authentication system"

        classification = classifier.classify(intent)

        assert classification.intent_type == IntentType.SECURITY_AUDIT
        assert classification.confidence >= 0.3
        assert 'security' in classification.semantic_domains

    def test_classify_feature_implementation(self, classifier):
        """Testa classificação de implementação de feature."""
        intent = "Implementar novo módulo de relatórios com dashboard interativo"

        classification = classifier.classify(intent)

        assert classification.intent_type == IntentType.FEATURE_IMPLEMENTATION
        assert classification.confidence >= 0.3

    def test_classify_infrastructure_change(self, classifier):
        """Testa classificação de mudança de infraestrutura."""
        intent = "Configurar auto-scaling para microserviços no Kubernetes"

        classification = classifier.classify(intent)

        assert classification.intent_type == IntentType.INFRASTRUCTURE_CHANGE
        assert classification.confidence >= 0.3

    def test_classify_unknown_returns_generic(self, classifier):
        """Testa que intent desconhecido retorna classificação genérica."""
        intent = "xyz abc 123"

        # Mock _score_by_semantics para evitar dependência de ML (problema de ambiente)
        with patch.object(classifier, '_score_by_semantics', return_value={}):
            classification = classifier.classify(intent)

        assert classification.intent_type == IntentType.GENERIC
        assert classification.recommended_task_count >= 4

    def test_get_decomposition_hints(self, classifier):
        """Testa extração de hints para decomposição."""
        intent = "Analisar viabilidade técnica de migração para OAuth2"
        classification = classifier.classify(intent)

        hints = classifier.get_decomposition_hints(classification)

        assert 'intent_type' in hints
        assert 'recommended_task_count' in hints
        assert 'semantic_domains' in hints
        assert 'should_use_template' in hints


class TestDecompositionTemplates:
    """Testes para templates de decomposição."""

    @pytest.fixture
    def templates(self):
        """Instância de DecompositionTemplates."""
        return DecompositionTemplates()

    def test_get_viability_analysis_template(self, templates):
        """Testa obtenção de template para análise de viabilidade."""
        template = templates.get_template(IntentType.VIABILITY_ANALYSIS)

        assert template is not None
        assert template.intent_type == IntentType.VIABILITY_ANALYSIS
        assert len(template.tasks) >= 6

        # Verificar que há diversidade de domínios semânticos
        domains = {t.semantic_domain for t in template.tasks}
        assert len(domains) >= 3  # security, architecture, quality, etc.

    def test_get_migration_template(self, templates):
        """Testa obtenção de template para migração."""
        template = templates.get_template(IntentType.MIGRATION)

        assert template is not None
        assert len(template.tasks) >= 6

    def test_get_generic_template_fallback(self, templates):
        """Testa que template genérico é usado como fallback."""
        template = templates.get_template(IntentType.GENERIC)

        assert template is not None
        assert len(template.tasks) >= 3

    def test_generate_tasks_viability_analysis(self, templates):
        """Testa geração de tasks para análise de viabilidade."""
        classification = IntentClassification(
            intent_type=IntentType.VIABILITY_ANALYSIS,
            confidence=0.8,
            matched_patterns=['analisar viabilidade'],
            recommended_task_count=8,
            semantic_domains=['security', 'architecture', 'quality']
        )

        tasks = templates.generate_tasks(
            classification=classification,
            intent_text="Analisar viabilidade de migração do sistema de autenticação para OAuth2",
            entities=['autenticação', 'OAuth2'],
            base_task_id=0
        )

        # Deve gerar 8 tasks
        assert len(tasks) == 8

        # Verificar que tasks têm IDs sequenciais
        task_ids = [t.task_id for t in tasks]
        assert task_ids == [f"task_{i}" for i in range(8)]

        # Verificar que dependências são válidas
        for task in tasks:
            for dep_id in task.dependencies:
                assert dep_id in task_ids

        # Verificar metadata de decomposição
        for task in tasks:
            assert 'template_id' in task.metadata
            assert 'semantic_domain' in task.metadata
            assert task.metadata['decomposition_method'] == 'template_based'

    def test_generate_tasks_with_subject_target_extraction(self, templates):
        """Testa extração de subject e target do texto do intent."""
        classification = IntentClassification(
            intent_type=IntentType.MIGRATION,
            confidence=0.8,
            matched_patterns=['migração'],
            recommended_task_count=8,
            semantic_domains=['security', 'architecture']
        )

        tasks = templates.generate_tasks(
            classification=classification,
            intent_text="Migrar sistema de autenticação de LDAP para OAuth2 com MFA",
            entities=['autenticação', 'LDAP', 'OAuth2'],
            base_task_id=0
        )

        # Verificar que subject e target foram extraídos e usados nas descrições
        descriptions = ' '.join(t.description for t in tasks)
        assert 'LDAP' in descriptions or 'autenticação' in descriptions
        assert 'OAuth2' in descriptions or 'MFA' in descriptions

    def test_get_semantic_coverage(self, templates):
        """Testa obtenção de cobertura semântica."""
        coverage = templates.get_semantic_coverage(IntentType.VIABILITY_ANALYSIS)

        assert isinstance(coverage, dict)
        assert sum(coverage.values()) >= 6  # Total de tasks
        assert 'security' in coverage or 'architecture' in coverage


class TestDAGGeneratorIntentDecomposition:
    """Testes de integração com DAGGenerator."""

    @pytest.fixture
    def dag_generator(self):
        """DAGGenerator com decomposição por intent habilitada."""
        return DAGGenerator(intent_decomposition_enabled=True)

    @pytest.fixture
    def dag_generator_disabled(self):
        """DAGGenerator com decomposição por intent desabilitada."""
        return DAGGenerator(intent_decomposition_enabled=False)

    def test_generate_uses_intent_decomposition(self, dag_generator):
        """Testa que generate() usa decomposição por intent quando disponível."""
        intermediate_repr = {
            'original_text': 'Analisar viabilidade técnica de migração para OAuth2 com MFA',
            'objectives': ['analyze'],
            'entities': [
                {'type': 'system', 'name': 'autenticação'},
                {'type': 'technology', 'name': 'OAuth2'}
            ],
            'constraints': {'domain': 'security'}
        }

        tasks, execution_order = dag_generator.generate(intermediate_repr)

        # Com intent_decomposition, deve gerar múltiplas tasks
        assert len(tasks) >= 6

        # Verificar que tasks têm metadata de decomposição por template
        template_tasks = [t for t in tasks if t.metadata.get('decomposition_method') == 'template_based']
        assert len(template_tasks) >= 6

    def test_generate_falls_back_without_original_text(self, dag_generator):
        """Testa fallback quando original_text não está disponível."""
        intermediate_repr = {
            'objectives': ['create', 'query'],
            'entities': [
                {'type': 'user', 'name': 'customer'}
            ],
            'constraints': {}
        }

        tasks, execution_order = dag_generator.generate(intermediate_repr)

        # Sem original_text, deve usar fluxo legado
        assert len(tasks) >= 1
        # Tasks não devem ter metadata de template
        template_tasks = [t for t in tasks if t.metadata.get('decomposition_method') == 'template_based']
        assert len(template_tasks) == 0

    def test_generate_disabled_uses_legacy_flow(self, dag_generator_disabled):
        """Testa que fluxo legado é usado quando decomposição está desabilitada."""
        intermediate_repr = {
            'original_text': 'Analisar viabilidade técnica de migração para OAuth2',
            'objectives': ['analyze'],
            'entities': [],
            'constraints': {}
        }

        tasks, execution_order = dag_generator_disabled.generate(intermediate_repr)

        # Deve gerar tasks pelo fluxo legado (poucos tasks)
        assert len(tasks) >= 1

        # Tasks não devem ter metadata de template
        template_tasks = [t for t in tasks if t.metadata.get('decomposition_method') == 'template_based']
        assert len(template_tasks) == 0


class TestIntentDecompositionEndToEnd:
    """Testes end-to-end de decomposição de intents reais."""

    @pytest.fixture
    def dag_generator(self):
        """DAGGenerator completo."""
        return DAGGenerator(intent_decomposition_enabled=True)

    def test_oauth2_migration_viability(self, dag_generator):
        """Testa decomposição completa de análise de viabilidade OAuth2."""
        intermediate_repr = {
            'original_text': 'Analisar viabilidade técnica de migração do sistema de autenticação para OAuth2 com suporte a MFA',
            'objectives': ['analyze_viability'],
            'entities': [
                {'type': 'system', 'name': 'autenticação'},
                {'type': 'technology', 'name': 'OAuth2'},
                {'type': 'feature', 'name': 'MFA'}
            ],
            'constraints': {
                'domain': 'security',
                'priority': 'high'
            }
        }

        tasks, execution_order = dag_generator.generate(intermediate_repr)

        # Deve gerar 8 tasks do template de viabilidade
        assert len(tasks) == 8

        # Verificar ordem topológica válida
        assert len(execution_order) == len(tasks)

        # Verificar diversidade de domínios semânticos
        domains = {t.metadata.get('semantic_domain') for t in tasks if t.metadata}
        assert len(domains) >= 3

        # Verificar que há tasks de diferentes tipos
        task_types = {t.task_type for t in tasks}
        assert len(task_types) >= 2  # query, validate, transform, etc.

    def test_infrastructure_autoscaling(self, dag_generator):
        """Testa decomposição de mudança de infraestrutura."""
        intermediate_repr = {
            'original_text': 'Projetar estratégia de auto-scaling para microserviços com base em métricas de CPU e memória',
            'objectives': ['design_infrastructure'],
            'entities': [
                {'type': 'component', 'name': 'microserviços'},
                {'type': 'metric', 'name': 'CPU'},
                {'type': 'metric', 'name': 'memória'}
            ],
            'constraints': {
                'domain': 'infrastructure',
                'priority': 'high'
            }
        }

        tasks, execution_order = dag_generator.generate(intermediate_repr)

        # Deve gerar tasks do template de infraestrutura
        assert len(tasks) >= 5

        # Verificar que há tasks relacionadas a capacidade/performance
        descriptions = ' '.join(t.description.lower() for t in tasks)
        assert 'capacidade' in descriptions or 'capacity' in descriptions or 'scaling' in descriptions.lower()
