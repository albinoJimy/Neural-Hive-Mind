"""
Testes unitários para PatternMatcher

Testa detecção de padrões complexos e cálculo de scores.
"""

import pytest
from unittest.mock import MagicMock, patch, mock_open
import yaml

from src.services.pattern_matcher import PatternMatcher, PatternMatch


# Fixtures de padrões de teste
MOCK_PATTERNS_YAML = """
patterns:
  crud_complete:
    name: "CRUD Completo"
    description: "Operações completas de CRUD"
    match_criteria:
      objectives:
        all_of: ["create", "query", "update", "delete"]
      entities:
        min_count: 1
        types: ["table", "model", "resource"]
    template:
      subtasks:
        - id: "validate_schema"
          type: "validate"
          description: "Validar schema"
          dependencies: []
        - id: "create_entity"
          type: "create"
          description: "Criar entidade"
          dependencies: ["validate_schema"]
      estimated_total_duration_ms: 5000
      complexity_multiplier: 1.5

  user_onboarding:
    name: "User Onboarding"
    description: "Processo de cadastro de usuário"
    match_criteria:
      objectives:
        any_of: ["create"]
      entities:
        min_count: 1
        types: ["user", "account", "profile"]
      keywords:
        - "cadastro"
        - "registro"
        - "onboarding"
    template:
      subtasks:
        - id: "validate_email"
          type: "validate"
          description: "Validar email"
          dependencies: []
        - id: "create_user"
          type: "create"
          description: "Criar usuário"
          dependencies: ["validate_email"]
      estimated_total_duration_ms: 3000
      complexity_multiplier: 1.3

  data_migration:
    name: "Data Migration"
    description: "Migração de dados"
    match_criteria:
      objectives:
        any_of: ["transform", "create"]
      keywords:
        - "migrar"
        - "migrate"
        - "migration"
    template:
      subtasks:
        - id: "backup"
          type: "create"
          description: "Criar backup"
          dependencies: []
      estimated_total_duration_ms: 8000
      complexity_multiplier: 2.0

matching_config:
  min_confidence_threshold: 0.7
  keyword_weight: 0.3
  objective_weight: 0.5
  entity_weight: 0.2
  max_patterns_returned: 3
"""


class TestPatternMatcherLoading:
    """Testes para carregamento de padrões"""

    def test_load_patterns_from_default_path(self):
        """Deve carregar patterns.yaml do caminho padrão"""
        with patch('builtins.open', mock_open(read_data=MOCK_PATTERNS_YAML)):
            with patch('pathlib.Path.exists', return_value=True):
                matcher = PatternMatcher()
                assert 'crud_complete' in matcher.patterns
                assert 'user_onboarding' in matcher.patterns
                assert len(matcher.patterns) == 3

    def test_load_patterns_from_custom_path(self):
        """Deve carregar patterns.yaml de caminho customizado"""
        with patch('builtins.open', mock_open(read_data=MOCK_PATTERNS_YAML)):
            with patch('pathlib.Path.exists', return_value=True):
                matcher = PatternMatcher(config_path='/custom/path/patterns.yaml')
                assert 'crud_complete' in matcher.patterns

    def test_load_patterns_file_not_found(self):
        """Deve retornar dict vazio se arquivo não encontrado"""
        with patch('pathlib.Path.exists', return_value=False):
            matcher = PatternMatcher()
            assert matcher.patterns == {}

    def test_load_patterns_invalid_yaml(self):
        """Deve logar erro e retornar dict vazio se YAML inválido"""
        invalid_yaml = "invalid: yaml: content: [["
        with patch('builtins.open', mock_open(read_data=invalid_yaml)):
            with patch('pathlib.Path.exists', return_value=True):
                matcher = PatternMatcher()
                assert matcher.patterns == {}


class TestPatternMatcherObjectiveMatching:
    """Testes para matching de objectives"""

    @pytest.fixture
    def matcher(self):
        """PatternMatcher com padrões de teste"""
        with patch('builtins.open', mock_open(read_data=MOCK_PATTERNS_YAML)):
            with patch('pathlib.Path.exists', return_value=True):
                return PatternMatcher()

    def test_match_all_of_objectives_success(self, matcher):
        """all_of: todos objectives presentes → score 1.0"""
        criteria = {'all_of': ['create', 'query', 'update', 'delete']}
        objectives = ['create', 'query', 'update', 'delete']
        score = matcher._match_objectives(criteria, objectives)
        assert score == 1.0

    def test_match_all_of_objectives_partial(self, matcher):
        """all_of: alguns objectives faltando → score 0.0"""
        criteria = {'all_of': ['create', 'query', 'update', 'delete']}
        objectives = ['create', 'query']  # faltam update e delete
        score = matcher._match_objectives(criteria, objectives)
        assert score == 0.0

    def test_match_any_of_objectives_full(self, matcher):
        """any_of: todos objectives presentes → score 1.0"""
        criteria = {'any_of': ['create', 'query']}
        objectives = ['create', 'query']
        score = matcher._match_objectives(criteria, objectives)
        assert score == 1.0

    def test_match_any_of_objectives_partial(self, matcher):
        """any_of: alguns objectives presentes → score proporcional"""
        criteria = {'any_of': ['create', 'query', 'update', 'delete']}
        objectives = ['create', 'query']  # 2 de 4
        score = matcher._match_objectives(criteria, objectives)
        assert score == 0.5

    def test_match_any_of_objectives_none(self, matcher):
        """any_of: nenhum objective presente → score 0.0"""
        criteria = {'any_of': ['create', 'query']}
        objectives = ['delete', 'transform']
        score = matcher._match_objectives(criteria, objectives)
        assert score == 0.0

    def test_match_objectives_empty_criteria(self, matcher):
        """Sem critério → score 1.0"""
        score = matcher._match_objectives({}, ['create'])
        assert score == 1.0


class TestPatternMatcherEntityMatching:
    """Testes para matching de entities"""

    @pytest.fixture
    def matcher(self):
        """PatternMatcher com padrões de teste"""
        with patch('builtins.open', mock_open(read_data=MOCK_PATTERNS_YAML)):
            with patch('pathlib.Path.exists', return_value=True):
                return PatternMatcher()

    def test_match_entities_min_count_satisfied(self, matcher):
        """min_count satisfeito → score baseado em types"""
        criteria = {'min_count': 1, 'types': ['user']}
        entities = [{'canonical_type': 'user', 'value': 'john'}]
        score = matcher._match_entities(criteria, entities)
        assert score == 1.0

    def test_match_entities_min_count_not_satisfied(self, matcher):
        """min_count não satisfeito → score 0.0"""
        criteria = {'min_count': 2}
        entities = [{'canonical_type': 'user', 'value': 'john'}]  # apenas 1
        score = matcher._match_entities(criteria, entities)
        assert score == 0.0

    def test_match_entities_types_all_match(self, matcher):
        """Todos entity types esperados presentes → score 1.0"""
        criteria = {'min_count': 1, 'types': ['user', 'account']}
        entities = [
            {'canonical_type': 'user', 'value': 'john'},
            {'canonical_type': 'account', 'value': 'acc123'}
        ]
        score = matcher._match_entities(criteria, entities)
        assert score == 1.0

    def test_match_entities_types_partial_match(self, matcher):
        """Alguns entity types presentes → score proporcional"""
        criteria = {'min_count': 1, 'types': ['user', 'account', 'profile']}
        entities = [{'canonical_type': 'user', 'value': 'john'}]  # 1 de 3
        score = matcher._match_entities(criteria, entities)
        assert pytest.approx(score, 0.01) == 1/3

    def test_match_entities_no_types_criteria(self, matcher):
        """Sem critério de types → score baseado apenas em min_count"""
        criteria = {'min_count': 1}
        entities = [{'canonical_type': 'anything', 'value': 'val'}]
        score = matcher._match_entities(criteria, entities)
        assert score == 1.0

    def test_match_entities_empty_criteria(self, matcher):
        """Sem critério → score 1.0"""
        score = matcher._match_entities({}, [])
        assert score == 1.0


class TestPatternMatcherKeywordMatching:
    """Testes para matching de keywords"""

    @pytest.fixture
    def matcher(self):
        """PatternMatcher com padrões de teste"""
        with patch('builtins.open', mock_open(read_data=MOCK_PATTERNS_YAML)):
            with patch('pathlib.Path.exists', return_value=True):
                return PatternMatcher()

    def test_match_keywords_all_present(self, matcher):
        """Todas keywords presentes no texto → score 1.0"""
        keywords = ['cadastro', 'registro']
        text = 'Fazer cadastro e registro de usuário'
        score = matcher._match_keywords(keywords, text)
        assert score == 1.0

    def test_match_keywords_partial_present(self, matcher):
        """Algumas keywords presentes → score proporcional"""
        keywords = ['cadastro', 'registro', 'onboarding']
        text = 'Fazer cadastro de usuário'  # 1 de 3
        score = matcher._match_keywords(keywords, text)
        assert pytest.approx(score, 0.01) == 1/3

    def test_match_keywords_none_present(self, matcher):
        """Nenhuma keyword presente → score 0.0"""
        keywords = ['cadastro', 'registro']
        text = 'Deletar entidade do sistema'
        score = matcher._match_keywords(keywords, text)
        assert score == 0.0

    def test_match_keywords_case_insensitive(self, matcher):
        """Keywords devem fazer match case-insensitive"""
        keywords = ['cadastro', 'REGISTRO']
        text = 'CADASTRO e registro'
        score = matcher._match_keywords(keywords, text)
        assert score == 1.0

    def test_match_keywords_word_boundary(self, matcher):
        """Keywords devem respeitar word boundaries"""
        keywords = ['user']
        text = 'username and userid'  # não deve fazer match
        score = matcher._match_keywords(keywords, text)
        assert score == 0.0

    def test_match_keywords_word_boundary_exact(self, matcher):
        """Keyword exata deve fazer match"""
        keywords = ['user']
        text = 'user profile'
        score = matcher._match_keywords(keywords, text)
        assert score == 1.0

    def test_match_keywords_empty_text(self, matcher):
        """Texto vazio → score 0.0"""
        keywords = ['cadastro']
        score = matcher._match_keywords(keywords, '')
        assert score == 0.0

    def test_match_keywords_empty_keywords(self, matcher):
        """Lista de keywords vazia → score 1.0"""
        score = matcher._match_keywords([], 'qualquer texto')
        assert score == 1.0


class TestPatternMatcherScoreCalculation:
    """Testes para cálculo de score agregado"""

    @pytest.fixture
    def matcher(self):
        """PatternMatcher com config de pesos"""
        with patch('builtins.open', mock_open(read_data=MOCK_PATTERNS_YAML)):
            with patch('pathlib.Path.exists', return_value=True):
                return PatternMatcher()

    def test_calculate_score_perfect_match(self, matcher):
        """Match perfeito em todos critérios → score próximo de 1.0"""
        pattern = {
            'match_criteria': {
                'objectives': {'any_of': ['create']},
                'entities': {'min_count': 1, 'types': ['user']},
                'keywords': ['cadastro']
            }
        }
        objectives = ['create']
        entities = [{'canonical_type': 'user', 'value': 'john'}]
        text = 'cadastro de usuário'

        score, matched = matcher._calculate_match_score(
            pattern, objectives, entities, text
        )
        assert score >= 0.9

    def test_calculate_score_weighted_combination(self, matcher):
        """Score deve combinar pesos corretamente"""
        # Config: objective_weight=0.5, entity_weight=0.2, keyword_weight=0.3
        pattern = {
            'match_criteria': {
                'objectives': {'any_of': ['create']},
                'entities': {'min_count': 1},
                'keywords': ['cadastro']
            }
        }

        # 100% objective, 100% entity, 0% keyword
        objectives = ['create']
        entities = [{'canonical_type': 'user', 'value': 'john'}]
        text = 'sem keyword'

        score, _ = matcher._calculate_match_score(
            pattern, objectives, entities, text
        )

        # Expected: 0.5 * 1.0 + 0.2 * 1.0 + 0.3 * 0.0 = 0.7
        assert pytest.approx(score, 0.01) == 0.7

    def test_calculate_score_below_threshold(self, matcher):
        """Score abaixo de threshold não deve ser retornado"""
        intermediate_repr = {
            'objectives': ['delete'],  # não bate com user_onboarding
            'entities': [],
            'text': 'sem keywords relevantes'
        }

        matches = matcher.match(intermediate_repr)
        # Não deve ter matches porque score < 0.7
        assert len(matches) == 0


class TestPatternMatcherIntegration:
    """Testes de integração com intermediate representation real"""

    @pytest.fixture
    def matcher(self):
        """PatternMatcher com padrões reais do YAML"""
        with patch('builtins.open', mock_open(read_data=MOCK_PATTERNS_YAML)):
            with patch('pathlib.Path.exists', return_value=True):
                return PatternMatcher()

    def test_match_user_onboarding_pattern(self, matcher):
        """Deve detectar padrão user_onboarding"""
        # Texto com múltiplas keywords para aumentar score
        intermediate_repr = {
            'intent_id': 'test-123',
            'domain': 'business',
            'objectives': ['create'],
            'entities': [
                {'canonical_type': 'user', 'value': 'novo_usuario'},
                {'canonical_type': 'account', 'value': 'conta_nova'},
                {'canonical_type': 'profile', 'value': 'perfil'}
            ],
            'text': 'Fazer cadastro e registro de usuário no onboarding'
        }

        matches = matcher.match(intermediate_repr)

        assert len(matches) > 0
        assert matches[0].pattern_id == 'user_onboarding'
        assert matches[0].confidence >= 0.7
        assert 'subtasks' in matches[0].template

    def test_match_crud_complete_pattern(self, matcher):
        """Deve detectar padrão crud_complete"""
        intermediate_repr = {
            'intent_id': 'test-456',
            'domain': 'business',
            'objectives': ['create', 'query', 'update', 'delete'],
            'entities': [
                {'canonical_type': 'table', 'value': 'users_table'}
            ],
            'text': 'Operações completas na tabela'
        }

        matches = matcher.match(intermediate_repr)

        assert len(matches) > 0
        assert matches[0].pattern_id == 'crud_complete'
        assert matches[0].confidence >= 0.7

    def test_match_data_migration_pattern(self, matcher):
        """Deve detectar padrão data_migration"""
        # Texto com múltiplas keywords para migration
        intermediate_repr = {
            'intent_id': 'test-789',
            'domain': 'technical',
            'objectives': ['transform', 'create'],
            'entities': [],
            'text': 'Migrar dados usando migration para importar e transferir registros'
        }

        matches = matcher.match(intermediate_repr)

        assert len(matches) > 0
        assert matches[0].pattern_id == 'data_migration'
        assert matches[0].confidence >= 0.7

    def test_match_multiple_patterns(self, matcher):
        """Deve retornar múltiplos padrões ordenados por confiança"""
        intermediate_repr = {
            'intent_id': 'test-multi',
            'domain': 'business',
            'objectives': ['create', 'transform'],
            'entities': [
                {'canonical_type': 'user', 'value': 'usuario'}
            ],
            'text': 'Migrar cadastro de usuário para novo sistema'
        }

        matches = matcher.match(intermediate_repr)

        # Pode ter múltiplos matches
        if len(matches) > 1:
            # Deve estar ordenado por confiança (maior primeiro)
            assert matches[0].confidence >= matches[1].confidence

    def test_match_no_patterns(self, matcher):
        """Deve retornar lista vazia se nenhum padrão detectado"""
        intermediate_repr = {
            'intent_id': 'test-none',
            'domain': 'business',
            'objectives': ['delete'],
            'entities': [],
            'text': 'Operação simples sem keywords'
        }

        matches = matcher.match(intermediate_repr)
        assert matches == []


class TestPatternMatcherGetTemplate:
    """Testes para recuperação de templates"""

    @pytest.fixture
    def matcher(self):
        """PatternMatcher com padrões de teste"""
        with patch('builtins.open', mock_open(read_data=MOCK_PATTERNS_YAML)):
            with patch('pathlib.Path.exists', return_value=True):
                return PatternMatcher()

    def test_get_template_existing_pattern(self, matcher):
        """Deve retornar template para padrão existente"""
        template = matcher.get_template('user_onboarding')
        assert template is not None
        assert 'subtasks' in template

    def test_get_template_non_existing_pattern(self, matcher):
        """Deve retornar None para padrão inexistente"""
        template = matcher.get_template('non_existent_pattern')
        assert template is None

    def test_template_structure_validation(self, matcher):
        """Template deve conter campos obrigatórios"""
        template = matcher.get_template('crud_complete')
        assert template is not None
        assert 'subtasks' in template
        assert 'estimated_total_duration_ms' in template
        assert 'complexity_multiplier' in template


class TestPatternMatcherEdgeCases:
    """Testes para casos edge"""

    @pytest.fixture
    def matcher(self):
        """PatternMatcher com padrões de teste"""
        with patch('builtins.open', mock_open(read_data=MOCK_PATTERNS_YAML)):
            with patch('pathlib.Path.exists', return_value=True):
                return PatternMatcher()

    def test_match_empty_intermediate_repr(self, matcher):
        """Deve lidar com IR vazio sem erro"""
        intermediate_repr = {}
        matches = matcher.match(intermediate_repr)
        assert isinstance(matches, list)

    def test_match_missing_objectives(self, matcher):
        """Deve lidar com objectives ausentes"""
        intermediate_repr = {
            'entities': [{'canonical_type': 'user'}],
            'text': 'cadastro'
        }
        matches = matcher.match(intermediate_repr)
        assert isinstance(matches, list)

    def test_match_missing_entities(self, matcher):
        """Deve lidar com entities ausentes"""
        intermediate_repr = {
            'objectives': ['create'],
            'text': 'cadastro'
        }
        matches = matcher.match(intermediate_repr)
        assert isinstance(matches, list)

    def test_match_empty_text(self, matcher):
        """Deve lidar com texto vazio"""
        intermediate_repr = {
            'objectives': ['create'],
            'entities': [{'canonical_type': 'user'}],
            'text': ''
        }
        matches = matcher.match(intermediate_repr)
        assert isinstance(matches, list)

    def test_match_none_values(self, matcher):
        """Deve lidar com valores None"""
        intermediate_repr = {
            'objectives': None,
            'entities': None,
            'text': None
        }
        matches = matcher.match(intermediate_repr)
        assert isinstance(matches, list)
        assert matches == []

    def test_match_with_empty_patterns(self):
        """Deve retornar vazio se não há padrões carregados"""
        with patch('pathlib.Path.exists', return_value=False):
            matcher = PatternMatcher()
            intermediate_repr = {
                'objectives': ['create'],
                'entities': [{'canonical_type': 'user'}],
                'text': 'cadastro de usuário'
            }
            matches = matcher.match(intermediate_repr)
            assert matches == []


class TestPatternMatchDataclass:
    """Testes para o dataclass PatternMatch"""

    def test_pattern_match_creation(self):
        """Deve criar PatternMatch corretamente"""
        match = PatternMatch(
            pattern_id='test_pattern',
            pattern_name='Test Pattern',
            confidence=0.85,
            template={'subtasks': []},
            matched_criteria={'objectives': {'score': 1.0}}
        )

        assert match.pattern_id == 'test_pattern'
        assert match.pattern_name == 'Test Pattern'
        assert match.confidence == 0.85
        assert match.template == {'subtasks': []}
        assert match.matched_criteria == {'objectives': {'score': 1.0}}

    def test_pattern_match_default_criteria(self):
        """matched_criteria deve ter default vazio"""
        match = PatternMatch(
            pattern_id='test',
            pattern_name='Test',
            confidence=0.5,
            template={}
        )

        assert match.matched_criteria == {}


class TestRealPatternsYamlFile:
    """
    Testes que leem o arquivo patterns.yaml real (sem mock_open).

    Valida que todos os padrões definidos no arquivo retornam templates
    válidos com os campos obrigatórios.
    """

    @pytest.fixture
    def real_matcher(self):
        """
        PatternMatcher carregado com o arquivo patterns.yaml real.

        Não utiliza mock_open para validar a integração com o arquivo real.
        """
        from pathlib import Path

        # Caminho para o patterns.yaml real
        config_path = Path(__file__).parent.parent.parent / 'config' / 'patterns.yaml'

        # Verificar que o arquivo existe antes do teste
        if not config_path.exists():
            pytest.skip(f'Arquivo patterns.yaml não encontrado em {config_path}')

        return PatternMatcher(config_path=str(config_path))

    def test_real_patterns_file_loaded(self, real_matcher):
        """Arquivo patterns.yaml real deve ser carregado com sucesso"""
        assert real_matcher.patterns is not None
        assert len(real_matcher.patterns) > 0

    def test_all_patterns_have_required_template_fields(self, real_matcher):
        """
        Todos os padrões devem ter templates com campos obrigatórios:
        - subtasks
        - estimated_total_duration_ms
        - complexity_multiplier
        """
        required_fields = ['subtasks', 'estimated_total_duration_ms', 'complexity_multiplier']

        for pattern_id, pattern in real_matcher.patterns.items():
            template = pattern.get('template', {})
            for field in required_fields:
                assert field in template, (
                    f"Padrão '{pattern_id}' não possui campo obrigatório "
                    f"'{field}' no template"
                )

    def test_api_integration_pattern_exists(self, real_matcher):
        """Padrão api_integration deve existir no arquivo real"""
        assert 'api_integration' in real_matcher.patterns, (
            "Padrão 'api_integration' não encontrado no patterns.yaml"
        )

    def test_api_integration_template_valid(self, real_matcher):
        """Template do padrão api_integration deve ser válido"""
        template = real_matcher.get_template('api_integration')
        assert template is not None, "Template de api_integration é None"
        assert 'subtasks' in template
        assert 'estimated_total_duration_ms' in template
        assert 'complexity_multiplier' in template

        # Verificar que subtasks não está vazio
        assert len(template['subtasks']) > 0, (
            "Template api_integration deve ter pelo menos uma subtask"
        )

    def test_all_patterns_subtasks_not_empty(self, real_matcher):
        """Todos os padrões devem ter pelo menos uma subtask"""
        for pattern_id, pattern in real_matcher.patterns.items():
            template = pattern.get('template', {})
            subtasks = template.get('subtasks', [])
            assert len(subtasks) > 0, (
                f"Padrão '{pattern_id}' deve ter pelo menos uma subtask"
            )

    def test_all_expected_patterns_present(self, real_matcher):
        """
        Verifica que todos os padrões esperados estão presentes no arquivo.

        Padrões esperados:
        - crud_complete
        - user_onboarding
        - data_migration
        - api_integration
        """
        expected_patterns = [
            'crud_complete',
            'user_onboarding',
            'data_migration',
            'api_integration'
        ]

        for pattern_id in expected_patterns:
            assert pattern_id in real_matcher.patterns, (
                f"Padrão esperado '{pattern_id}' não encontrado no patterns.yaml"
            )

    def test_matching_config_present(self, real_matcher):
        """Configuração de matching deve estar presente"""
        assert real_matcher.config is not None
        assert 'min_confidence_threshold' in real_matcher.config
        assert 'keyword_weight' in real_matcher.config
        assert 'objective_weight' in real_matcher.config
        assert 'entity_weight' in real_matcher.config

    def test_min_confidence_override_applied(self):
        """min_confidence_override deve sobrescrever valor do YAML"""
        from pathlib import Path

        config_path = Path(__file__).parent.parent.parent / 'config' / 'patterns.yaml'
        if not config_path.exists():
            pytest.skip(f'Arquivo patterns.yaml não encontrado em {config_path}')

        custom_threshold = 0.85
        matcher = PatternMatcher(
            config_path=str(config_path),
            min_confidence_override=custom_threshold
        )

        assert matcher.config['min_confidence_threshold'] == custom_threshold


class TestMinCountValidationEarlyExit:
    """
    Testes para validação precoce de min_count em _calculate_match_score.

    Garante que padrões com min_count não fazem match sem entidades suficientes.
    """

    @pytest.fixture
    def matcher(self):
        """PatternMatcher com padrões de teste"""
        with patch('builtins.open', mock_open(read_data=MOCK_PATTERNS_YAML)):
            with patch('pathlib.Path.exists', return_value=True):
                return PatternMatcher()

    def test_min_count_blocks_match_without_entities(self, matcher):
        """Padrão com min_count deve retornar score 0 sem entidades"""
        # user_onboarding requer min_count: 1
        intermediate_repr = {
            'intent_id': 'test-no-entities',
            'objectives': ['create'],
            'entities': [],  # Sem entidades
            'text': 'cadastro registro onboarding'  # Keywords corretas
        }

        matches = matcher.match(intermediate_repr)

        # user_onboarding não deve fazer match por falta de entidades
        user_onboarding_match = [
            m for m in matches if m.pattern_id == 'user_onboarding'
        ]
        assert len(user_onboarding_match) == 0, (
            "user_onboarding não deveria fazer match sem entidades (min_count=1)"
        )

    def test_min_count_allows_match_with_enough_entities(self, matcher):
        """Padrão com min_count deve fazer match com entidades suficientes"""
        intermediate_repr = {
            'intent_id': 'test-with-entities',
            'objectives': ['create'],
            'entities': [
                {'canonical_type': 'user', 'value': 'usuario'},
                {'canonical_type': 'account', 'value': 'conta'}
            ],
            'text': 'cadastro registro onboarding de usuário'
        }

        matches = matcher.match(intermediate_repr)

        # user_onboarding deve fazer match com entidades
        user_onboarding_match = [
            m for m in matches if m.pattern_id == 'user_onboarding'
        ]
        assert len(user_onboarding_match) > 0, (
            "user_onboarding deveria fazer match com entidades suficientes"
        )

    def test_calculate_score_returns_zero_below_min_count(self, matcher):
        """_calculate_match_score deve retornar 0.0 se len(entities) < min_count"""
        pattern = {
            'match_criteria': {
                'objectives': {'any_of': ['create']},
                'entities': {'min_count': 2},  # Requer 2 entidades
                'keywords': ['teste']
            }
        }

        objectives = ['create']
        entities = [{'canonical_type': 'user'}]  # Apenas 1 entidade
        text = 'teste'

        score, matched_criteria = matcher._calculate_match_score(
            pattern, objectives, entities, text
        )

        assert score == 0.0
        assert matched_criteria.get('entities', {}).get('reason') == 'min_count não satisfeito'
