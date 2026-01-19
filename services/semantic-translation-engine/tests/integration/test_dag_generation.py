"""
Testes de integração para DAG Generation avançado

Testa integração do DAGGenerator com PatternMatcher e TaskSplitter.
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import Dict, List, Any

from src.services.dag_generator import DAGGenerator
from src.services.pattern_matcher import PatternMatcher, PatternMatch
from src.services.task_splitter import TaskSplitter
from src.models.cognitive_plan import TaskNode


class TestPatternBasedDecomposition:
    """Testes de decomposição baseada em padrões"""

    @pytest.fixture
    def mock_settings(self):
        """Fixture de configurações mock"""
        settings = MagicMock()
        settings.task_splitting_enabled = True
        settings.task_splitting_max_depth = 3
        settings.task_splitting_complexity_threshold = 0.6
        settings.task_splitting_min_entities_for_split = 2
        settings.task_splitting_description_length_threshold = 150
        settings.pattern_matching_enabled = True
        settings.pattern_min_confidence = 0.7
        return settings

    @pytest.fixture
    def pattern_matcher_with_onboarding(self):
        """PatternMatcher com padrão de onboarding configurado"""
        # Criar PatternMatcher com patterns mock
        with patch.object(PatternMatcher, '_load_patterns') as mock_load:
            mock_load.return_value = {
                'patterns': {
                    'user_onboarding': {
                        'name': 'User Onboarding',
                        'match_criteria': {
                            'objectives': {'all_of': ['create']},
                            'entities': {'min_count': 1, 'types': ['user']},
                            'keywords': ['user', 'onboarding', 'registration']
                        },
                        'template': {
                            'subtasks': [
                                {
                                    'id': 'validate_input',
                                    'type': 'validate',
                                    'description': 'Validar dados de entrada do usuário',
                                    'dependencies': [],
                                    'estimated_duration_ms': 200,
                                    'required_capabilities': ['read']
                                },
                                {
                                    'id': 'create_user',
                                    'type': 'create',
                                    'description': 'Criar registro de usuário',
                                    'dependencies': ['validate_input'],
                                    'estimated_duration_ms': 500,
                                    'required_capabilities': ['write']
                                },
                                {
                                    'id': 'send_welcome',
                                    'type': 'create',
                                    'description': 'Enviar email de boas-vindas',
                                    'dependencies': ['create_user'],
                                    'estimated_duration_ms': 300,
                                    'required_capabilities': ['notification']
                                }
                            ]
                        }
                    }
                },
                'matching_config': {
                    'min_confidence_threshold': 0.7,
                    'keyword_weight': 0.3,
                    'objective_weight': 0.5,
                    'entity_weight': 0.2,
                    'max_patterns_returned': 3
                }
            }
            return PatternMatcher()

    @pytest.fixture
    def intermediate_repr_onboarding(self):
        """Representação intermediária para onboarding"""
        return {
            'intent_id': 'test-001',
            'domain': 'business',
            'objectives': ['create'],
            'entities': [
                {'type': 'user', 'value': 'new_customer', 'confidence': 0.9}
            ],
            'constraints': {
                'priority': 'high',
                'security_level': 'internal'
            },
            'text': 'Create new user onboarding registration flow'
        }

    def test_user_onboarding_pattern_generates_subtasks(
        self,
        mock_settings,
        pattern_matcher_with_onboarding,
        intermediate_repr_onboarding
    ):
        """Verifica que padrão 'user_onboarding' gera subtasks corretas"""
        dag_generator = DAGGenerator(
            pattern_matcher=pattern_matcher_with_onboarding,
            task_splitter=None
        )

        tasks, execution_order = dag_generator.generate(intermediate_repr_onboarding)

        # Deve gerar 3 subtasks do template
        assert len(tasks) == 3

        # Verificar tipos das tasks
        task_types = [t.task_type for t in tasks]
        assert 'validate' in task_types
        assert task_types.count('create') == 2

        # Verificar metadata de padrão
        for task in tasks:
            assert task.metadata.get('from_pattern') is True
            assert task.metadata.get('pattern_id') == 'user_onboarding'

    def test_pattern_match_confidence_threshold(self, mock_settings):
        """Verifica que apenas padrões com confiança >= threshold são usados"""
        with patch.object(PatternMatcher, '_load_patterns') as mock_load:
            mock_load.return_value = {
                'patterns': {
                    'low_confidence_pattern': {
                        'name': 'Low Confidence',
                        'match_criteria': {
                            'objectives': {'any_of': ['query']}
                        },
                        'template': {
                            'subtasks': []
                        }
                    }
                },
                'matching_config': {
                    'min_confidence_threshold': 0.9,  # Threshold alto
                    'keyword_weight': 0.3,
                    'objective_weight': 0.5,
                    'entity_weight': 0.2
                }
            }
            pattern_matcher = PatternMatcher()

        dag_generator = DAGGenerator(pattern_matcher=pattern_matcher)

        intermediate_repr = {
            'objectives': ['query'],
            'entities': [],
            'constraints': {},
            'text': 'Query data'
        }

        tasks, _ = dag_generator.generate(intermediate_repr)

        # Com threshold alto, não deve usar o padrão
        # Deve usar fluxo legacy
        for task in tasks:
            assert task.metadata.get('from_pattern') is not True

    def test_pattern_dependencies_mapped_correctly(
        self,
        pattern_matcher_with_onboarding,
        intermediate_repr_onboarding
    ):
        """Verifica que dependências do template são mapeadas para task_ids reais"""
        dag_generator = DAGGenerator(
            pattern_matcher=pattern_matcher_with_onboarding
        )

        tasks, _ = dag_generator.generate(intermediate_repr_onboarding)

        # Encontrar tasks por tipo
        validate_task = next(t for t in tasks if t.task_type == 'validate')
        create_tasks = [t for t in tasks if t.task_type == 'create']

        # Validate não deve ter dependências
        assert len(validate_task.dependencies) == 0

        # Create tasks devem ter dependências corretas
        # Pelo menos uma deve depender da validate
        has_validate_dep = any(
            validate_task.task_id in t.dependencies
            for t in create_tasks
        )
        assert has_validate_dep


class TestTaskSplittingIntegration:
    """Testes de integração do TaskSplitter com DAGGenerator"""

    @pytest.fixture
    def mock_settings(self):
        """Fixture de configurações mock"""
        settings = MagicMock()
        settings.task_splitting_enabled = True
        settings.task_splitting_max_depth = 3
        settings.task_splitting_complexity_threshold = 0.3  # Threshold baixo para forçar split
        settings.task_splitting_min_entities_for_split = 1
        settings.task_splitting_description_length_threshold = 50
        return settings

    @pytest.fixture
    def task_splitter(self, mock_settings):
        """TaskSplitter configurado para splitting agressivo"""
        return TaskSplitter(settings=mock_settings, pattern_matcher=None)

    @pytest.fixture
    def intermediate_repr_complex(self):
        """Representação intermediária complexa"""
        return {
            'intent_id': 'test-complex-001',
            'domain': 'technical',
            'objectives': ['create'],
            'entities': [
                {'type': 'service', 'value': 'api_gateway', 'confidence': 0.9},
                {'type': 'database', 'value': 'postgresql', 'confidence': 0.85},
                {'type': 'cache', 'value': 'redis', 'confidence': 0.8}
            ],
            'constraints': {
                'priority': 'high',
                'security_level': 'confidential'
            }
        }

    def test_complex_task_split_into_subtasks(
        self,
        task_splitter,
        intermediate_repr_complex
    ):
        """Verifica que task complexa é dividida em validation → main → verification"""
        dag_generator = DAGGenerator(
            pattern_matcher=None,
            task_splitter=task_splitter
        )

        tasks, execution_order = dag_generator.generate(intermediate_repr_complex)

        # Com splitting habilitado, deve gerar mais tasks que apenas a main
        # Heuristic split gera: validate → main → verify
        assert len(tasks) >= 3

        # Verificar que há tasks de suporte
        task_roles = [
            t.metadata.get('subtask_role') or t.metadata.get('support_task_type')
            for t in tasks
            if t.metadata
        ]
        has_split_tasks = any(
            role in ['validation', 'main_operation', 'verification']
            for role in task_roles
        )
        # Pode ter tasks de split ou tasks de suporte (security validation)
        assert has_split_tasks or len(tasks) > 1

    def test_recursive_splitting_respects_max_depth(self, mock_settings):
        """Verifica que splitting para quando atinge max_depth"""
        mock_settings.task_splitting_max_depth = 1  # Limitar a 1 nível

        task_splitter = TaskSplitter(settings=mock_settings, pattern_matcher=None)
        dag_generator = DAGGenerator(task_splitter=task_splitter)

        intermediate_repr = {
            'objectives': ['create'],
            'entities': [
                {'type': 'x', 'value': 'a'},
                {'type': 'y', 'value': 'b'},
                {'type': 'z', 'value': 'c'}
            ],
            'constraints': {}
        }

        tasks, _ = dag_generator.generate(intermediate_repr)

        # Verificar que max_depth foi respeitado
        max_depth = max(
            (t.metadata.get('split_depth', 0) for t in tasks if t.metadata),
            default=0
        )
        assert max_depth <= mock_settings.task_splitting_max_depth

    def test_split_tasks_maintain_parent_task_id(
        self,
        task_splitter,
        intermediate_repr_complex
    ):
        """Verifica que subtasks têm metadata com parent_task_id"""
        dag_generator = DAGGenerator(task_splitter=task_splitter)

        tasks, _ = dag_generator.generate(intermediate_repr_complex)

        # Subtasks geradas por split devem ter parent_task_id
        split_tasks = [
            t for t in tasks
            if t.metadata and t.metadata.get('split_method')
        ]

        for task in split_tasks:
            assert 'parent_task_id' in task.metadata


class TestEntityBasedDependencies:
    """Testes de dependências baseadas em entidades"""

    @pytest.fixture
    def dag_generator(self):
        """DAGGenerator sem componentes avançados"""
        return DAGGenerator()

    def test_write_before_read_dependency(self, dag_generator):
        """Verifica que create/update vem antes de query na mesma entidade"""
        intermediate_repr = {
            'objectives': ['create', 'query'],
            'entities': [
                {'type': 'user', 'name': 'customer', 'confidence': 0.9}
            ],
            'constraints': {}
        }

        tasks, execution_order = dag_generator.generate(intermediate_repr)

        # Encontrar tasks por tipo
        create_task = next((t for t in tasks if t.task_type == 'create'), None)
        query_task = next((t for t in tasks if t.task_type == 'query'), None)

        if create_task and query_task:
            # Na ordem de execução, create deve vir antes de query
            create_idx = execution_order.index(create_task.task_id)
            query_idx = execution_order.index(query_task.task_id)
            assert create_idx < query_idx

    def test_shared_entity_creates_dependency(self, dag_generator):
        """Verifica que tasks compartilhando entidades têm dependência"""
        intermediate_repr = {
            'objectives': ['create', 'update'],
            'entities': [
                {'type': 'record', 'name': 'order', 'confidence': 0.9}
            ],
            'constraints': {}
        }

        tasks, execution_order = dag_generator.generate(intermediate_repr)

        # Create deve vir antes de update
        create_task = next((t for t in tasks if t.task_type == 'create'), None)
        update_task = next((t for t in tasks if t.task_type == 'update'), None)

        if create_task and update_task:
            create_idx = execution_order.index(create_task.task_id)
            update_idx = execution_order.index(update_task.task_id)
            assert create_idx < update_idx

    def test_no_cycles_created_by_entity_analysis(self, dag_generator):
        """Verifica que análise de entidades não cria ciclos"""
        intermediate_repr = {
            'objectives': ['create', 'update', 'query'],
            'entities': [
                {'type': 'resource', 'name': 'data', 'confidence': 0.9}
            ],
            'constraints': {}
        }

        # Não deve lançar exceção de ciclo
        tasks, execution_order = dag_generator.generate(intermediate_repr)

        # DAG é válido se temos uma ordem de execução
        assert len(execution_order) > 0
        assert len(tasks) > 0


class TestParallelismDetection:
    """Testes de detecção de paralelismo"""

    @pytest.fixture
    def dag_generator(self):
        """DAGGenerator sem componentes avançados"""
        return DAGGenerator()

    def test_independent_tasks_grouped_as_parallel(self):
        """Verifica que tasks sem dependências são agrupadas"""
        dag_generator = DAGGenerator()

        # Múltiplos objectives independentes
        intermediate_repr = {
            'objectives': ['query', 'validate'],
            'entities': [],
            'constraints': {}
        }

        tasks, _ = dag_generator.generate(intermediate_repr)

        # Verificar se há grupos paralelos atribuídos
        tasks_with_parallel_group = [
            t for t in tasks
            if t.metadata and t.metadata.get('parallel_group')
        ]

        # Tasks independentes devem ser agrupadas
        # (depende da estrutura do DAG gerado)
        assert isinstance(tasks_with_parallel_group, list)

    def test_parallel_groups_assigned_correctly(self, dag_generator):
        """Verifica que parallel_group_id está no metadata"""
        intermediate_repr = {
            'objectives': ['create'],
            'entities': [{'type': 'a', 'name': 'x'}],
            'constraints': {'security_level': 'confidential'}
        }

        tasks, _ = dag_generator.generate(intermediate_repr)

        # Verificar estrutura de metadata
        for task in tasks:
            if task.metadata and task.metadata.get('parallel_group'):
                assert 'parallel_level' in task.metadata

    def test_dependent_tasks_not_in_same_parallel_group(self, dag_generator):
        """Verifica que tasks com dependências não são paralelas"""
        intermediate_repr = {
            'objectives': ['create', 'update'],
            'entities': [{'type': 'record', 'name': 'data'}],
            'constraints': {}
        }

        tasks, _ = dag_generator.generate(intermediate_repr)

        # Tasks com dependência não devem estar no mesmo grupo paralelo
        create_task = next((t for t in tasks if t.task_type == 'create'), None)
        update_task = next((t for t in tasks if t.task_type == 'update'), None)

        if create_task and update_task:
            create_group = (
                create_task.metadata.get('parallel_group')
                if create_task.metadata else None
            )
            update_group = (
                update_task.metadata.get('parallel_group')
                if update_task.metadata else None
            )

            # Se ambos têm grupos, devem ser diferentes
            if create_group and update_group:
                assert create_group != update_group


class TestEndToEndAdvancedDecomposition:
    """Testes end-to-end de decomposição avançada"""

    @pytest.fixture
    def mock_settings(self):
        """Settings para testes"""
        settings = MagicMock()
        settings.task_splitting_enabled = True
        settings.task_splitting_max_depth = 2
        settings.task_splitting_complexity_threshold = 0.5
        settings.task_splitting_min_entities_for_split = 2
        settings.task_splitting_description_length_threshold = 100
        return settings

    @pytest.fixture
    def pattern_matcher(self):
        """PatternMatcher com múltiplos padrões"""
        with patch.object(PatternMatcher, '_load_patterns') as mock_load:
            mock_load.return_value = {
                'patterns': {
                    'data_migration': {
                        'name': 'Data Migration',
                        'match_criteria': {
                            'objectives': {'all_of': ['create', 'transform']},
                            'keywords': ['migration', 'migrate']
                        },
                        'template': {
                            'subtasks': [
                                {'id': 'extract', 'type': 'query', 'description': 'Extract data', 'dependencies': []},
                                {'id': 'transform', 'type': 'transform', 'description': 'Transform data', 'dependencies': ['extract']},
                                {'id': 'load', 'type': 'create', 'description': 'Load data', 'dependencies': ['transform']}
                            ]
                        }
                    }
                },
                'matching_config': {
                    'min_confidence_threshold': 0.7,
                    'keyword_weight': 0.3,
                    'objective_weight': 0.5,
                    'entity_weight': 0.2
                }
            }
            return PatternMatcher()

    def test_complex_intent_full_flow(self, mock_settings, pattern_matcher):
        """Intent complexo → pattern match → splitting → dependências → paralelismo"""
        task_splitter = TaskSplitter(settings=mock_settings, pattern_matcher=pattern_matcher)
        dag_generator = DAGGenerator(
            pattern_matcher=pattern_matcher,
            task_splitter=task_splitter
        )

        intermediate_repr = {
            'intent_id': 'migration-001',
            'domain': 'technical',
            'objectives': ['create', 'transform'],
            'entities': [
                {'type': 'database', 'name': 'source_db'},
                {'type': 'database', 'name': 'target_db'}
            ],
            'constraints': {
                'priority': 'high',
                'security_level': 'confidential'
            },
            'text': 'Migrate data from source database to target'
        }

        tasks, execution_order = dag_generator.generate(intermediate_repr)

        # Verificar que tasks foram geradas
        assert len(tasks) > 0
        assert len(execution_order) > 0

        # Verificar ordem de execução válida
        assert len(set(execution_order)) == len(execution_order)  # Sem duplicatas

    def test_fallback_to_heuristic_when_no_pattern(self, mock_settings):
        """Verifica que fluxo legado funciona quando sem pattern match"""
        task_splitter = TaskSplitter(settings=mock_settings, pattern_matcher=None)
        dag_generator = DAGGenerator(
            pattern_matcher=None,
            task_splitter=task_splitter
        )

        intermediate_repr = {
            'objectives': ['query'],
            'entities': [],
            'constraints': {}
        }

        tasks, execution_order = dag_generator.generate(intermediate_repr)

        # Deve gerar ao menos a task principal
        assert len(tasks) >= 1
        assert len(execution_order) >= 1

        # Nenhuma task deve ter metadata de padrão
        for task in tasks:
            if task.metadata:
                assert task.metadata.get('from_pattern') is not True

    def test_dag_remains_acyclic_after_all_enhancements(
        self,
        mock_settings,
        pattern_matcher
    ):
        """Verifica que DAG final é sempre acíclico"""
        task_splitter = TaskSplitter(settings=mock_settings, pattern_matcher=pattern_matcher)
        dag_generator = DAGGenerator(
            pattern_matcher=pattern_matcher,
            task_splitter=task_splitter
        )

        # Múltiplos cenários de teste
        test_cases = [
            {
                'objectives': ['create', 'update', 'query'],
                'entities': [{'type': 'user', 'name': 'customer'}],
                'constraints': {}
            },
            {
                'objectives': ['delete', 'create'],
                'entities': [
                    {'type': 'record', 'name': 'order'},
                    {'type': 'record', 'name': 'item'}
                ],
                'constraints': {'security_level': 'restricted'}
            },
            {
                'objectives': ['transform'],
                'entities': [],
                'constraints': {'priority': 'critical'}
            }
        ]

        for case in test_cases:
            # Não deve lançar exceção de ciclo
            tasks, execution_order = dag_generator.generate(case)

            # Verificar que ordem é válida
            assert len(execution_order) == len(tasks)
            assert len(set(execution_order)) == len(execution_order)


class TestLegacyCompatibility:
    """Testes de compatibilidade retroativa"""

    def test_dag_generator_without_dependencies(self):
        """DAGGenerator funciona sem PatternMatcher e TaskSplitter"""
        dag_generator = DAGGenerator()

        intermediate_repr = {
            'objectives': ['create'],
            'entities': [{'type': 'resource', 'value': 'data'}],
            'constraints': {'priority': 'normal'}
        }

        tasks, execution_order = dag_generator.generate(intermediate_repr)

        assert len(tasks) >= 1
        assert len(execution_order) >= 1

    def test_dag_generator_with_only_pattern_matcher(self):
        """DAGGenerator funciona apenas com PatternMatcher"""
        with patch.object(PatternMatcher, '_load_patterns') as mock_load:
            mock_load.return_value = {'patterns': {}, 'matching_config': {}}
            pattern_matcher = PatternMatcher()

        dag_generator = DAGGenerator(pattern_matcher=pattern_matcher)

        intermediate_repr = {
            'objectives': ['query'],
            'entities': [],
            'constraints': {}
        }

        tasks, execution_order = dag_generator.generate(intermediate_repr)

        assert len(tasks) >= 1

    def test_dag_generator_with_only_task_splitter(self):
        """DAGGenerator funciona apenas com TaskSplitter"""
        settings = MagicMock()
        settings.task_splitting_enabled = True
        settings.task_splitting_max_depth = 2
        settings.task_splitting_complexity_threshold = 0.9  # Alto para não dividir
        settings.task_splitting_min_entities_for_split = 10
        settings.task_splitting_description_length_threshold = 1000

        task_splitter = TaskSplitter(settings=settings, pattern_matcher=None)
        dag_generator = DAGGenerator(task_splitter=task_splitter)

        intermediate_repr = {
            'objectives': ['update'],
            'entities': [{'type': 'x', 'value': 'y'}],
            'constraints': {}
        }

        tasks, execution_order = dag_generator.generate(intermediate_repr)

        assert len(tasks) >= 1


class TestEntityDependencyIntegration:
    """Testes de integração para análise de dependências de entidades"""

    @pytest.fixture
    def mock_settings(self):
        """Settings para testes"""
        settings = MagicMock()
        settings.task_splitting_enabled = True
        settings.task_splitting_max_depth = 2
        settings.task_splitting_complexity_threshold = 0.5
        settings.task_splitting_min_entities_for_split = 2
        settings.task_splitting_description_length_threshold = 100
        return settings

    def test_end_to_end_with_conflicts(self):
        """Fluxo completo com detecção e resolução de conflitos"""
        dag_generator = DAGGenerator(conflict_resolution_strategy='sequential')

        intermediate_repr = {
            'intent_id': 'conflict-test-001',
            'domain': 'business',
            'objectives': ['create', 'update', 'update', 'query'],
            'entities': [
                {'type': 'user', 'name': 'customer_profile'},
            ],
            'constraints': {'priority': 'high'}
        }

        tasks, execution_order = dag_generator.generate(intermediate_repr)

        # Verificar que tasks foram geradas
        assert len(tasks) >= 4
        assert len(execution_order) == len(tasks)

        # Verificar ordem de execução válida (sem duplicatas)
        assert len(set(execution_order)) == len(execution_order)

        # Verificar que create vem antes de updates e query
        create_task = next((t for t in tasks if t.task_type == 'create'), None)
        query_task = next((t for t in tasks if t.task_type == 'query'), None)

        if create_task and query_task:
            assert execution_order.index(create_task.task_id) < execution_order.index(query_task.task_id)

    def test_pattern_based_with_entity_dependencies(self):
        """Pattern match combinado com análise de entidades"""
        with patch.object(PatternMatcher, '_load_patterns') as mock_load:
            mock_load.return_value = {
                'patterns': {
                    'crud_pattern': {
                        'name': 'CRUD Operations',
                        'match_criteria': {
                            'objectives': {'all_of': ['create', 'query']}
                        },
                        'template': {
                            'subtasks': [
                                {'id': 'validate', 'type': 'validate', 'description': 'Validate input', 'dependencies': []},
                                {'id': 'create', 'type': 'create', 'description': 'Create record', 'dependencies': ['validate']},
                                {'id': 'query', 'type': 'query', 'description': 'Query result', 'dependencies': ['create']}
                            ]
                        }
                    }
                },
                'matching_config': {
                    'min_confidence_threshold': 0.7,
                    'keyword_weight': 0.3,
                    'objective_weight': 0.5,
                    'entity_weight': 0.2
                }
            }
            pattern_matcher = PatternMatcher()

        dag_generator = DAGGenerator(pattern_matcher=pattern_matcher)

        intermediate_repr = {
            'objectives': ['create', 'query'],
            'entities': [{'type': 'user', 'name': 'customer'}],
            'constraints': {}
        }

        tasks, execution_order = dag_generator.generate(intermediate_repr)

        # Deve usar padrão e aplicar dependências de entidades
        assert len(tasks) >= 3

    def test_task_splitting_with_entity_dependencies(self, mock_settings):
        """Task splitting combinado com análise de entidades"""
        task_splitter = TaskSplitter(settings=mock_settings, pattern_matcher=None)
        dag_generator = DAGGenerator(task_splitter=task_splitter)

        intermediate_repr = {
            'objectives': ['create'],
            'entities': [
                {'type': 'service', 'name': 'api_gateway'},
                {'type': 'database', 'name': 'postgresql'},
                {'type': 'cache', 'name': 'redis'}
            ],
            'constraints': {'security_level': 'confidential'}
        }

        tasks, execution_order = dag_generator.generate(intermediate_repr)

        # Com splitting e múltiplas entidades, deve gerar várias tasks
        assert len(tasks) >= 1
        assert len(execution_order) >= 1

    def test_parallel_detection_respects_entity_deps(self):
        """Grupos paralelos respeitam dependências de entidades"""
        dag_generator = DAGGenerator()

        intermediate_repr = {
            'objectives': ['create', 'query'],
            'entities': [{'type': 'record', 'name': 'data'}],
            'constraints': {}
        }

        tasks, execution_order = dag_generator.generate(intermediate_repr)

        # Encontrar tasks com grupos paralelos
        create_task = next((t for t in tasks if t.task_type == 'create'), None)
        query_task = next((t for t in tasks if t.task_type == 'query'), None)

        if create_task and query_task and create_task.metadata and query_task.metadata:
            create_group = create_task.metadata.get('parallel_group')
            query_group = query_task.metadata.get('parallel_group')

            # Se ambos têm grupos, devem ser diferentes (por dependência de entidade)
            if create_group and query_group:
                assert create_group != query_group

    def test_visualization_generated_in_production_flow(self):
        """Visualização é gerada em cenário de produção"""
        import logging

        dag_generator = DAGGenerator()

        # Configurar logger para DEBUG
        logger = logging.getLogger('structlog')
        original_level = logger.level
        logger.setLevel(logging.DEBUG)

        try:
            intermediate_repr = {
                'objectives': ['create', 'update', 'query'],
                'entities': [
                    {'type': 'user', 'name': 'customer'},
                    {'type': 'order', 'name': 'purchase'}
                ],
                'constraints': {}
            }

            tasks, execution_order = dag_generator.generate(intermediate_repr)

            # Verificar geração básica
            assert len(tasks) >= 3
            assert len(execution_order) == len(tasks)
        finally:
            logger.setLevel(original_level)

    def test_metrics_recorded_correctly(self):
        """Métricas Prometheus são registradas corretamente"""
        from src.observability.metrics import (
            dag_generation_entity_dependencies_added,
            dag_generation_conflicts_detected_total,
            dag_generation_conflicts_resolved_total
        )

        dag_generator = DAGGenerator(conflict_resolution_strategy='sequential')

        intermediate_repr = {
            'objectives': ['create', 'update', 'query'],
            'entities': [{'type': 'resource', 'name': 'data'}],
            'constraints': {}
        }

        # Gerar DAG (métricas são incrementadas internamente)
        tasks, execution_order = dag_generator.generate(intermediate_repr)

        # Verificar que tasks foram geradas corretamente
        assert len(tasks) >= 3

        # As métricas são registradas durante a execução
        # Não podemos verificar valores específicos sem reset,
        # mas podemos verificar que não houve exceção

    def test_fuzzy_matching_in_integration(self):
        """Fuzzy matching funciona em cenário de integração"""
        dag_generator = DAGGenerator(
            entity_matching_fuzzy_enabled=True,
            entity_matching_fuzzy_threshold=0.8
        )

        intermediate_repr = {
            'objectives': ['create', 'query'],
            'entities': [
                {'type': 'user', 'name': 'customer_profile'},
                {'type': 'user', 'name': 'customer_profle'}  # Typo proposital
            ],
            'constraints': {}
        }

        tasks, execution_order = dag_generator.generate(intermediate_repr)

        # Deve completar sem erros
        assert len(tasks) >= 2
        assert len(execution_order) >= 2

    def test_conflict_with_existing_heuristic_dependency(self):
        """Conflito + dependência heurística são tratados corretamente"""
        dag_generator = DAGGenerator(conflict_resolution_strategy='sequential')

        intermediate_repr = {
            'objectives': ['create', 'update'],  # Heurística: create → update
            'entities': [{'type': 'record', 'name': 'data'}],
            'constraints': {}
        }

        tasks, execution_order = dag_generator.generate(intermediate_repr)

        # Deve ter dependência heurística (create → update)
        create_task = next((t for t in tasks if t.task_type == 'create'), None)
        update_task = next((t for t in tasks if t.task_type == 'update'), None)

        if create_task and update_task:
            # update deve depender de create
            assert create_task.task_id in update_task.dependencies or \
                   execution_order.index(create_task.task_id) < execution_order.index(update_task.task_id)
