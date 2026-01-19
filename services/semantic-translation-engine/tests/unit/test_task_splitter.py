"""
Testes unitarios para TaskSplitter

Testa decomposicao de tasks complexas em subtasks atomicas.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.models.cognitive_plan import TaskNode
from src.services.task_splitter import TaskSplitter, ComplexityAnalysis
from src.services.pattern_matcher import PatternMatch


class TestTaskSplitterComplexityAnalysis:
    """Testes para analise de complexidade"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.task_splitting_enabled = True
        settings.task_splitting_max_depth = 3
        settings.task_splitting_complexity_threshold = 0.6
        settings.task_splitting_min_entities_for_split = 2
        settings.task_splitting_description_length_threshold = 150
        return settings

    @pytest.fixture
    def splitter(self, settings):
        """Create TaskSplitter instance"""
        return TaskSplitter(settings)

    def test_analyze_complexity_simple_task(self, splitter):
        """Task simples deve ter score baixo"""
        task = TaskNode(
            task_id='task-1',
            task_type='query',
            description='Get user by id',
            dependencies=[],
            parameters={'entities': []}
        )

        analysis = splitter._analyze_complexity(task)

        assert analysis.score < 0.6
        assert analysis.should_split is False

    def test_analyze_complexity_long_description(self, splitter):
        """Task com descricao longa deve ter score alto"""
        long_desc = 'A' * 200  # 200 caracteres
        task = TaskNode(
            task_id='task-1',
            task_type='create',
            description=long_desc,
            dependencies=[],
            parameters={'entities': []}
        )

        analysis = splitter._analyze_complexity(task)

        assert analysis.factors['description_length'] > 0.2

    def test_analyze_complexity_multiple_entities(self, splitter):
        """Task com multiplas entidades deve ter score alto"""
        task = TaskNode(
            task_id='task-1',
            task_type='create',
            description='Create user and profile',
            dependencies=[],
            parameters={
                'entities': [
                    {'type': 'user', 'value': 'john'},
                    {'type': 'profile', 'value': 'profile1'},
                    {'type': 'account', 'value': 'acc1'}
                ]
            }
        )

        analysis = splitter._analyze_complexity(task)

        assert analysis.factors['entity_count'] > 0.2

    def test_analyze_complexity_multiple_dependencies(self, splitter):
        """Task com multiplas dependencias deve ter score alto"""
        task = TaskNode(
            task_id='task-1',
            task_type='update',
            description='Update records',
            dependencies=['task-0', 'task-1', 'task-2', 'task-3'],
            parameters={'entities': []}
        )

        analysis = splitter._analyze_complexity(task)

        assert analysis.factors['dependency_count'] > 0.15

    def test_analyze_complexity_multiple_action_verbs(self, splitter):
        """Task com multiplos verbos de acao deve ter score alto"""
        task = TaskNode(
            task_id='task-1',
            task_type='transform',
            description='Create user, send email, update profile, validate data',
            dependencies=[],
            parameters={'entities': []}
        )

        analysis = splitter._analyze_complexity(task)

        assert analysis.factors['action_verb_count'] > 0.15


class TestTaskSplitterShouldSplit:
    """Testes para decisao de splitting"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.task_splitting_enabled = True
        settings.task_splitting_max_depth = 3
        settings.task_splitting_complexity_threshold = 0.6
        settings.task_splitting_min_entities_for_split = 2
        settings.task_splitting_description_length_threshold = 150
        return settings

    @pytest.fixture
    def splitter(self, settings):
        """Create TaskSplitter instance"""
        return TaskSplitter(settings)

    def test_should_split_complex_task(self, splitter):
        """Task complexa deve ser dividida"""
        task = TaskNode(
            task_id='task-1',
            task_type='create',
            description='A' * 200 + ' create user and send email and update profile',
            dependencies=[],
            parameters={
                'entities': [
                    {'type': 'user'},
                    {'type': 'email'},
                    {'type': 'profile'}
                ]
            }
        )

        assert splitter.should_split(task) is True

    def test_should_not_split_simple_task(self, splitter):
        """Task simples nao deve ser dividida"""
        task = TaskNode(
            task_id='task-1',
            task_type='query',
            description='Get user by id',
            dependencies=[],
            parameters={'entities': []}
        )

        assert splitter.should_split(task) is False


class TestTaskSplitterPatternBased:
    """Testes para splitting baseado em padroes"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.task_splitting_enabled = True
        settings.task_splitting_max_depth = 3
        settings.task_splitting_complexity_threshold = 0.6
        settings.task_splitting_min_entities_for_split = 2
        settings.task_splitting_description_length_threshold = 150
        return settings

    @pytest.fixture
    def pattern_matcher(self):
        """Mock PatternMatcher"""
        matcher = MagicMock()
        return matcher

    @pytest.fixture
    def splitter(self, settings, pattern_matcher):
        """Create TaskSplitter with PatternMatcher"""
        return TaskSplitter(settings, pattern_matcher)

    def test_split_by_pattern_detected(self, splitter, pattern_matcher):
        """Deve usar template quando padrao detectado"""
        # Mock pattern match
        pattern_match = PatternMatch(
            pattern_id='user_onboarding',
            pattern_name='User Onboarding',
            confidence=0.85,
            template={
                'subtasks': [
                    {
                        'id': 'validate_email',
                        'type': 'validate',
                        'description': 'Validate email',
                        'dependencies': []
                    },
                    {
                        'id': 'create_user',
                        'type': 'create',
                        'description': 'Create user',
                        'dependencies': ['validate_email']
                    }
                ]
            }
        )
        pattern_matcher.match.return_value = [pattern_match]

        # Task complexa para passar should_split
        task = TaskNode(
            task_id='task-1',
            task_type='create',
            description='A' * 200,  # Descricao longa para atingir threshold
            dependencies=[],
            parameters={'entities': [{'type': 'user'}, {'type': 'profile'}]}
        )

        intermediate_repr = {'objectives': ['create'], 'entities': [{'type': 'user'}]}

        # Mock should_split para subtasks nao dividirem recursivamente
        # (subtasks do template sao simples)
        original_should_split = splitter.should_split
        call_count = [0]

        def mock_should_split(t):
            call_count[0] += 1
            if call_count[0] == 1:
                return True  # Task original deve dividir
            return False  # Subtasks nao dividem

        splitter.should_split = mock_should_split

        subtasks = splitter.split(task, intermediate_repr, current_depth=0)

        assert len(subtasks) == 2
        assert subtasks[0].task_id == 'task-1_sub0'
        assert subtasks[0].metadata['parent_task_id'] == 'task-1'
        assert subtasks[0].metadata['split_method'] == 'pattern_based'
        assert subtasks[1].dependencies == ['task-1_sub0']

    def test_split_by_pattern_no_match(self, splitter, pattern_matcher):
        """Deve usar heuristica quando nenhum padrao detectado"""
        pattern_matcher.match.return_value = []

        task = TaskNode(
            task_id='task-1',
            task_type='create',
            description='A' * 200,  # Complexo
            dependencies=[],
            parameters={'entities': [{'type': 'user'}, {'type': 'profile'}]}
        )

        intermediate_repr = {'objectives': ['create']}

        # Mock should_split para evitar recursao infinita no teste
        # (apenas task original deve dividir)
        call_count = [0]

        def mock_should_split(t):
            call_count[0] += 1
            if call_count[0] == 1:
                return True  # Task original deve dividir
            return False  # Subtasks nao dividem

        splitter.should_split = mock_should_split

        subtasks = splitter.split(task, intermediate_repr, current_depth=0)

        # Deve ter 3 subtasks (validate, main, verify) sem recursao adicional
        assert len(subtasks) == 3
        assert subtasks[0].metadata['split_method'] == 'heuristic_based'


class TestTaskSplitterHeuristicBased:
    """Testes para splitting heuristico"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.task_splitting_enabled = True
        settings.task_splitting_max_depth = 3
        settings.task_splitting_complexity_threshold = 0.6
        settings.task_splitting_min_entities_for_split = 2
        settings.task_splitting_description_length_threshold = 150
        return settings

    @pytest.fixture
    def splitter(self, settings):
        """Create TaskSplitter without PatternMatcher"""
        return TaskSplitter(settings)

    def test_split_by_heuristics_generates_three_subtasks(self, splitter):
        """Splitting heuristico deve gerar 3 subtasks"""
        task = TaskNode(
            task_id='task-1',
            task_type='create',
            description='Complex operation',
            dependencies=[],
            parameters={'entities': []}
        )

        subtasks = splitter._split_by_heuristics(task, current_depth=0)

        assert len(subtasks) == 3
        assert subtasks[0].task_type == 'validate'
        assert subtasks[1].task_type == 'create'
        assert subtasks[2].task_type == 'validate'

    def test_split_by_heuristics_maintains_dependencies(self, splitter):
        """Subtasks devem ter dependencias corretas"""
        task = TaskNode(
            task_id='task-1',
            task_type='update',
            description='Update operation',
            dependencies=[],
            parameters={'entities': []}
        )

        subtasks = splitter._split_by_heuristics(task, current_depth=0)

        # Validate -> Main -> Verify
        assert subtasks[0].dependencies == []
        assert subtasks[1].dependencies == [subtasks[0].task_id]
        assert subtasks[2].dependencies == [subtasks[1].task_id]

    def test_split_by_heuristics_sets_metadata(self, splitter):
        """Subtasks devem ter metadata correto"""
        task = TaskNode(
            task_id='task-1',
            task_type='create',
            description='Create operation',
            dependencies=[],
            parameters={'entities': []}
        )

        subtasks = splitter._split_by_heuristics(task, current_depth=1)

        for subtask in subtasks:
            assert subtask.metadata['parent_task_id'] == 'task-1'
            assert subtask.metadata['split_depth'] == 2
            assert subtask.metadata['split_method'] == 'heuristic_based'


class TestTaskSplitterRecursion:
    """Testes para splitting recursivo"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.task_splitting_enabled = True
        settings.task_splitting_max_depth = 2
        settings.task_splitting_complexity_threshold = 0.6
        settings.task_splitting_min_entities_for_split = 2
        settings.task_splitting_description_length_threshold = 150
        return settings

    @pytest.fixture
    def splitter(self, settings):
        """Create TaskSplitter instance"""
        return TaskSplitter(settings)

    def test_split_respects_max_depth(self, splitter):
        """Nao deve dividir quando max_depth atingido"""
        task = TaskNode(
            task_id='task-1',
            task_type='create',
            description='A' * 200,  # Complexo
            dependencies=[],
            parameters={'entities': [{'type': 'user'}, {'type': 'profile'}]}
        )

        # current_depth = max_depth
        subtasks = splitter.split(task, current_depth=2)

        # Deve retornar task original
        assert len(subtasks) == 1
        assert subtasks[0].task_id == 'task-1'

    def test_recursive_splitting_generates_nested_subtasks(self, settings):
        """Splitting recursivo deve gerar subtasks aninhadas ate max_depth"""
        # Configurar max_depth = 2 para permitir 2 niveis de splitting
        settings.task_splitting_max_depth = 2
        splitter = TaskSplitter(settings)

        # Mock should_split para retornar True apenas nos primeiros niveis
        # Depth 0: task original -> deve dividir
        # Depth 1: subtasks -> main_task deve dividir (descricao longa)
        # Depth 2: sub-subtasks -> nao deve dividir (max_depth)
        original_should_split = splitter.should_split

        def mock_should_split(task):
            # A task _main sempre herda a descricao original que e complexa
            # Validation e verification tasks tem descricoes curtas
            if task.metadata.get('subtask_role') == 'main_operation':
                return True
            return original_should_split(task)

        splitter.should_split = mock_should_split

        # Task complexa inicial
        task = TaskNode(
            task_id='task-1',
            task_type='create',
            description='A' * 200 + ' create user and send email and update profile',
            dependencies=[],
            parameters={
                'entities': [
                    {'type': 'user'},
                    {'type': 'email'},
                    {'type': 'profile'}
                ]
            }
        )

        subtasks = splitter.split(task, current_depth=0)

        # Deve ter mais de 3 subtasks devido ao splitting recursivo
        # Depth 0: task-1 -> validate, main, verify (3)
        # Depth 1: main -> validate_sub, main_sub, verify_sub (expande para 5 total)
        assert len(subtasks) > 3, f"Esperado mais de 3 subtasks com recursao, obteve {len(subtasks)}"

        # Verificar que existem subtasks com split_depth = 2
        depth_2_tasks = [t for t in subtasks if t.metadata.get('split_depth') == 2]
        assert len(depth_2_tasks) > 0, "Deve haver subtasks com split_depth = 2"

        # Verificar parent_task_id das subtasks de profundidade 2
        for task in depth_2_tasks:
            parent_id = task.metadata.get('parent_task_id')
            assert parent_id is not None, "Subtask deve ter parent_task_id"
            assert parent_id.startswith('task-1_'), f"Parent deve ser subtask de task-1, obteve {parent_id}"

    def test_recursive_splitting_stops_at_max_depth(self, settings):
        """Splitting recursivo deve parar em max_depth"""
        settings.task_splitting_max_depth = 1
        splitter = TaskSplitter(settings)

        # Forcar should_split a retornar True sempre
        splitter.should_split = lambda task: True

        task = TaskNode(
            task_id='task-1',
            task_type='create',
            description='Complex task',
            dependencies=[],
            parameters={'entities': []}
        )

        subtasks = splitter.split(task, current_depth=0)

        # Com max_depth=1, so deve haver um nivel de splitting
        # Todas subtasks devem ter split_depth = 1
        for subtask in subtasks:
            assert subtask.metadata.get('split_depth') == 1, \
                f"Com max_depth=1, split_depth deve ser 1, obteve {subtask.metadata.get('split_depth')}"

    def test_recursive_splitting_preserves_parent_task_id_chain(self, settings):
        """Splitting recursivo deve preservar cadeia de parent_task_id"""
        settings.task_splitting_max_depth = 2
        splitter = TaskSplitter(settings)

        # Mock para forcar splitting apenas na subtask main
        original_should_split = splitter.should_split
        call_count = [0]

        def mock_should_split(task):
            call_count[0] += 1
            # Primeira chamada: task original deve dividir
            if call_count[0] == 1:
                return True
            # Subtask main deve dividir
            if '_main' in task.task_id:
                return True
            return False

        splitter.should_split = mock_should_split

        task = TaskNode(
            task_id='root-task',
            task_type='create',
            description='Root complex task',
            dependencies=[],
            parameters={'entities': []}
        )

        subtasks = splitter.split(task, current_depth=0)

        # Verificar que subtasks de depth 1 tem parent_task_id = root-task
        depth_1_tasks = [t for t in subtasks if t.metadata.get('split_depth') == 1]
        for task in depth_1_tasks:
            assert task.metadata['parent_task_id'] == 'root-task', \
                f"Subtask depth 1 deve ter parent root-task, obteve {task.metadata['parent_task_id']}"

        # Verificar que subtasks de depth 2 tem parent_task_id correto (subtask de root)
        depth_2_tasks = [t for t in subtasks if t.metadata.get('split_depth') == 2]
        for task in depth_2_tasks:
            parent_id = task.metadata['parent_task_id']
            assert parent_id.startswith('root-task_'), \
                f"Subtask depth 2 deve ter parent que e subtask de root, obteve {parent_id}"


class TestTaskSplitterDisabled:
    """Testes para comportamento com splitting desabilitado"""

    @pytest.fixture
    def settings_disabled(self):
        """Mock Settings com splitting desabilitado"""
        settings = MagicMock()
        settings.task_splitting_enabled = False
        return settings

    @pytest.fixture
    def splitter_disabled(self, settings_disabled):
        """Create TaskSplitter com splitting desabilitado"""
        return TaskSplitter(settings_disabled)

    def test_disabled_returns_original_task(self, splitter_disabled):
        """Com splitting desabilitado, deve retornar task original"""
        task = TaskNode(
            task_id='task-1',
            task_type='create',
            description='A' * 200,  # Complexo
            dependencies=[],
            parameters={'entities': [{'type': 'user'}, {'type': 'profile'}]}
        )

        subtasks = splitter_disabled.split(task)

        assert len(subtasks) == 1
        assert subtasks[0].task_id == 'task-1'


class TestTaskSplitterMetrics:
    """Testes para metricas Prometheus"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.task_splitting_enabled = True
        settings.task_splitting_max_depth = 3
        settings.task_splitting_complexity_threshold = 0.6
        settings.task_splitting_min_entities_for_split = 2
        settings.task_splitting_description_length_threshold = 150
        return settings

    @pytest.fixture
    def splitter(self, settings):
        """Create TaskSplitter instance"""
        return TaskSplitter(settings)

    @patch('src.services.task_splitter.tasks_split_total')
    @patch('src.services.task_splitter.subtasks_generated_total')
    @patch('src.services.task_splitter.task_splitting_depth')
    def test_metrics_recorded_on_split(
        self,
        mock_depth,
        mock_subtasks,
        mock_split,
        splitter
    ):
        """Verificar que metricas sao registradas no splitting"""
        task = TaskNode(
            task_id='task-1',
            task_type='create',
            description='Complex operation',
            dependencies=[],
            parameters={'entities': []}
        )

        splitter._split_by_heuristics(task, current_depth=0)

        mock_split.labels.assert_called()
        mock_subtasks.labels.assert_called()
        mock_depth.observe.assert_called_with(1)
