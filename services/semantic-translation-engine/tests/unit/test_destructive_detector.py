"""
Testes unitários para o DestructiveDetector

Testa detecção de operações destrutivas por task type e keywords.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.models.cognitive_plan import TaskNode
from src.services.destructive_detector import DestructiveDetector


class TestDestructiveDetectorBasicDetection:
    """Testes para detecção básica de operações destrutivas"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.destructive_detection_enabled = True
        settings.destructive_detection_strict_mode = False
        return settings

    @pytest.fixture
    def detector(self, settings):
        """Create DestructiveDetector instance"""
        return DestructiveDetector(settings)

    def test_detect_delete_task_type(self, detector):
        """Task com task_type='delete' deve ser detectada"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='delete',
                description='Delete old records',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        assert 'task-1' in result['destructive_tasks']
        assert result['total_destructive_count'] == 1
        assert len(result['details']) == 1
        assert result['details'][0]['reason'] == 'task_type_match'

    def test_detect_drop_task_type(self, detector):
        """Task com task_type='drop' deve ser detectada"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='drop',
                description='Drop database table',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        assert 'task-1' in result['destructive_tasks']
        assert result['severity'] == 'high'  # drop triggers high severity

    def test_detect_truncate_task_type(self, detector):
        """Task com task_type='truncate' deve ser detectada"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='truncate',
                description='Truncate table data',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        assert 'task-1' in result['destructive_tasks']
        assert result['severity'] == 'high'  # truncate triggers high severity

    def test_detect_keyword_portuguese(self, detector):
        """Descrição 'deletar todos os registros' deve ser detectada"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Deletar todos os registros antigos',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        assert 'task-1' in result['destructive_tasks']
        assert result['details'][0]['reason'] == 'keyword_match'
        assert 'deletar' in result['details'][0]['matched_keywords']

    def test_detect_keyword_english(self, detector):
        """Descrição 'remove all records' deve ser detectada"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Remove all records from database',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        assert 'task-1' in result['destructive_tasks']
        assert result['details'][0]['reason'] == 'keyword_match'
        assert 'remove' in result['details'][0]['matched_keywords']

    def test_no_detection_safe_operations(self, detector):
        """Tasks com task_type='query' ou 'create' não devem ser detectadas"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Buscar usuários ativos',
                dependencies=[]
            ),
            TaskNode(
                task_id='task-2',
                task_type='create',
                description='Criar novo registro',
                dependencies=['task-1']
            ),
            TaskNode(
                task_id='task-3',
                task_type='transform',
                description='Transformar dados',
                dependencies=['task-2']
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is False
        assert result['destructive_tasks'] == []
        assert result['total_destructive_count'] == 0


class TestDestructiveDetectorSeverityCalculation:
    """Testes para cálculo de severidade"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.destructive_detection_enabled = True
        settings.destructive_detection_strict_mode = False
        return settings

    @pytest.fixture
    def detector(self, settings):
        """Create DestructiveDetector instance"""
        return DestructiveDetector(settings)

    def test_severity_low_single_task(self, detector):
        """1 task destrutiva → severity='low'"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='delete',
                description='Delete one record',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['severity'] == 'low'

    def test_severity_medium_two_tasks(self, detector):
        """2 tasks destrutivas → severity='medium'"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='delete',
                description='Delete record 1',
                dependencies=[]
            ),
            TaskNode(
                task_id='task-2',
                task_type='delete',
                description='Delete record 2',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['severity'] == 'medium'

    def test_severity_high_three_tasks(self, detector):
        """3 tasks destrutivas → severity='high'"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='delete',
                description='Delete record 1',
                dependencies=[]
            ),
            TaskNode(
                task_id='task-2',
                task_type='delete',
                description='Delete record 2',
                dependencies=[]
            ),
            TaskNode(
                task_id='task-3',
                task_type='delete',
                description='Delete record 3',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['severity'] == 'high'

    def test_severity_critical_five_tasks(self, detector):
        """5+ tasks destrutivas → severity='critical'"""
        tasks = [
            TaskNode(
                task_id=f'task-{i}',
                task_type='delete',
                description=f'Delete record {i}',
                dependencies=[]
            )
            for i in range(5)
        ]
        result = detector.detect(tasks)

        assert result['severity'] == 'critical'

    def test_severity_critical_high_impact_indicator(self, detector):
        """Task com 'delete all production' → severity='critical'"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Delete all production data',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        assert result['severity'] == 'critical'
        assert result['details'][0]['has_high_impact_indicators'] is True

    def test_severity_high_drop_operation(self, detector):
        """Task com task_type='drop' → severity='high'"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='drop',
                description='Drop temporary table',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['severity'] == 'high'


class TestDestructiveDetectorEdgeCases:
    """Testes para casos edge"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.destructive_detection_enabled = True
        settings.destructive_detection_strict_mode = False
        return settings

    @pytest.fixture
    def detector(self, settings):
        """Create DestructiveDetector instance"""
        return DestructiveDetector(settings)

    def test_empty_task_list(self, detector):
        """Lista vazia de tasks deve retornar is_destructive=False"""
        result = detector.detect([])

        assert result['is_destructive'] is False
        assert result['destructive_tasks'] == []
        assert result['total_destructive_count'] == 0
        assert result['details'] == []

    def test_task_with_empty_description(self, detector):
        """Task com descrição vazia não deve causar erro"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is False

    def test_task_with_empty_task_type(self, detector):
        """Task com task_type vazio não deve causar erro"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='',
                description='Some description',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is False

    def test_mixed_destructive_and_safe_tasks(self, detector):
        """Detectar apenas as destrutivas em lista mista"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Query users',
                dependencies=[]
            ),
            TaskNode(
                task_id='task-2',
                task_type='delete',
                description='Delete old records',
                dependencies=['task-1']
            ),
            TaskNode(
                task_id='task-3',
                task_type='create',
                description='Create backup',
                dependencies=['task-1']
            ),
            TaskNode(
                task_id='task-4',
                task_type='remove',
                description='Remove duplicates',
                dependencies=['task-2']
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        assert result['total_destructive_count'] == 2
        assert 'task-2' in result['destructive_tasks']
        assert 'task-4' in result['destructive_tasks']
        assert 'task-1' not in result['destructive_tasks']
        assert 'task-3' not in result['destructive_tasks']

    def test_case_insensitive_detection(self, detector):
        """'DELETE', 'Delete', 'delete' devem ser detectados"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='DELETE',
                description='Delete records',
                dependencies=[]
            ),
            TaskNode(
                task_id='task-2',
                task_type='Delete',
                description='Delete more records',
                dependencies=[]
            ),
            TaskNode(
                task_id='task-3',
                task_type='delete',
                description='Delete even more records',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        assert result['total_destructive_count'] == 3
        assert 'task-1' in result['destructive_tasks']
        assert 'task-2' in result['destructive_tasks']
        assert 'task-3' in result['destructive_tasks']

    def test_partial_keyword_match(self, detector):
        """'deleted' deve fazer match com 'delete'"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Mark records as deleted',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        # 'deleted' contains 'delete' so it matches
        assert result['is_destructive'] is True
        assert 'delete' in result['details'][0]['matched_keywords']

    def test_multiple_keywords_in_description(self, detector):
        """Descrição com múltiplas keywords deve registrar todas"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Delete and remove all old data',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        matched = result['details'][0]['matched_keywords']
        assert 'delete' in matched
        assert 'remove' in matched

    def test_portuguese_keyword_remover(self, detector):
        """Keyword 'remover' em português deve ser detectada"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Remover registros duplicados',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        assert 'remover' in result['details'][0]['matched_keywords']

    def test_portuguese_keyword_apagar(self, detector):
        """Keyword 'apagar' em português deve ser detectada"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Apagar dados temporários',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        assert 'apagar' in result['details'][0]['matched_keywords']

    def test_high_impact_indicator_todos(self, detector):
        """Indicador 'todos' deve triggerar critical severity"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Deletar todos os dados',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        assert result['severity'] == 'critical'
        assert result['details'][0]['has_high_impact_indicators'] is True

    def test_high_impact_indicator_production(self, detector):
        """Indicador 'production' deve triggerar critical severity"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='delete',
                description='Delete production database',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        assert result['severity'] == 'critical'
        assert result['details'][0]['has_high_impact_indicators'] is True


class TestDestructiveDetectorMetrics:
    """Testes para métricas Prometheus"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.destructive_detection_enabled = True
        settings.destructive_detection_strict_mode = False
        return settings

    @pytest.fixture
    def detector(self, settings):
        """Create DestructiveDetector instance"""
        return DestructiveDetector(settings)

    @patch('src.services.destructive_detector.destructive_operations_detected_total')
    @patch('src.services.destructive_detector.destructive_tasks_per_plan')
    def test_metrics_incremented_on_detection(
        self,
        mock_histogram,
        mock_counter,
        detector
    ):
        """Verificar que destructive_operations_detected_total é incrementado"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='delete',
                description='Delete records',
                dependencies=[]
            )
        ]
        detector.detect(tasks)

        mock_counter.labels.assert_called()
        mock_counter.labels().inc.assert_called()

    @patch('src.services.destructive_detector.destructive_operations_detected_total')
    @patch('src.services.destructive_detector.destructive_tasks_per_plan')
    def test_histogram_observes_count(
        self,
        mock_histogram,
        mock_counter,
        detector
    ):
        """Verificar que destructive_tasks_per_plan registra contagem correta"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='delete',
                description='Delete record 1',
                dependencies=[]
            ),
            TaskNode(
                task_id='task-2',
                task_type='delete',
                description='Delete record 2',
                dependencies=[]
            )
        ]
        detector.detect(tasks)

        mock_histogram.observe.assert_called_with(2)

    @patch('src.services.destructive_detector.destructive_operations_detected_total')
    @patch('src.services.destructive_detector.destructive_tasks_per_plan')
    def test_metrics_labels_correct(
        self,
        mock_histogram,
        mock_counter,
        detector
    ):
        """Verificar labels severity e detection_type corretos"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='delete',
                description='Delete records',
                dependencies=[]
            )
        ]
        detector.detect(tasks)

        # Check that labels were called with correct values
        mock_counter.labels.assert_called_with(
            severity='low',
            detection_type='task_type_match'
        )

    @patch('src.services.destructive_detector.destructive_operations_detected_total')
    @patch('src.services.destructive_detector.destructive_tasks_per_plan')
    def test_metrics_not_incremented_for_safe_operations(
        self,
        mock_histogram,
        mock_counter,
        detector
    ):
        """Verificar que métricas não são incrementadas para operações seguras"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Query users',
                dependencies=[]
            )
        ]
        detector.detect(tasks)

        # Counter should not be called for safe operations
        mock_counter.labels.assert_not_called()
        # Histogram should still observe 0
        mock_histogram.observe.assert_called_with(0)


class TestDestructiveDetectorTaskTypeVariants:
    """Testes para variantes de task types destrutivos"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.destructive_detection_enabled = True
        settings.destructive_detection_strict_mode = False
        return settings

    @pytest.fixture
    def detector(self, settings):
        """Create DestructiveDetector instance"""
        return DestructiveDetector(settings)

    def test_detect_remove_task_type(self, detector):
        """Task com task_type='remove' deve ser detectada"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='remove',
                description='Remove item',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        assert result['details'][0]['reason'] == 'task_type_match'

    def test_detect_purge_task_type(self, detector):
        """Task com task_type='purge' deve ser detectada"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='purge',
                description='Purge cache',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        assert result['details'][0]['reason'] == 'task_type_match'


class TestDestructiveDetectorKeywordVariants:
    """Testes para variantes de keywords destrutivas"""

    @pytest.fixture
    def settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.destructive_detection_enabled = True
        settings.destructive_detection_strict_mode = False
        return settings

    @pytest.fixture
    def detector(self, settings):
        """Create DestructiveDetector instance"""
        return DestructiveDetector(settings)

    def test_detect_keyword_destroy(self, detector):
        """Keyword 'destroy' deve ser detectada"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Destroy old sessions',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        assert 'destroy' in result['details'][0]['matched_keywords']

    def test_detect_keyword_erase(self, detector):
        """Keyword 'erase' deve ser detectada"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Erase temporary files',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        assert 'erase' in result['details'][0]['matched_keywords']

    def test_detect_keyword_wipe(self, detector):
        """Keyword 'wipe' deve ser detectada"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Wipe all data',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        assert 'wipe' in result['details'][0]['matched_keywords']

    def test_detect_keyword_excluir(self, detector):
        """Keyword 'excluir' em português deve ser detectada"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Excluir usuários inativos',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        assert 'excluir' in result['details'][0]['matched_keywords']

    def test_detect_keyword_destruir(self, detector):
        """Keyword 'destruir' em português deve ser detectada"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Destruir arquivos temporários',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        assert 'destruir' in result['details'][0]['matched_keywords']

    def test_detect_keyword_eliminar(self, detector):
        """Keyword 'eliminar' em português deve ser detectada"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Eliminar duplicatas',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        assert 'eliminar' in result['details'][0]['matched_keywords']

    def test_detect_keyword_limpar(self, detector):
        """Keyword 'limpar' em português deve ser detectada"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Limpar cache do sistema',
                dependencies=[]
            )
        ]
        result = detector.detect(tasks)

        assert result['is_destructive'] is True
        assert 'limpar' in result['details'][0]['matched_keywords']


class TestDestructiveDetectorDisabled:
    """Testes para comportamento com detector desabilitado"""

    @pytest.fixture
    def settings_disabled(self):
        """Mock Settings com detector desabilitado"""
        settings = MagicMock()
        settings.destructive_detection_enabled = False
        settings.destructive_detection_strict_mode = False
        return settings

    @pytest.fixture
    def detector_disabled(self, settings_disabled):
        """Create DestructiveDetector com detecção desabilitada"""
        return DestructiveDetector(settings_disabled)

    def test_disabled_returns_non_destructive(self, detector_disabled):
        """Com detector desabilitado, deve retornar resultado não destrutivo"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='delete',
                description='Delete all production data',
                dependencies=[]
            )
        ]
        result = detector_disabled.detect(tasks)

        assert result['is_destructive'] is False
        assert result['destructive_tasks'] == []
        assert result['severity'] == 'low'
        assert result['total_destructive_count'] == 0
        assert result['details'] == []

    def test_disabled_empty_list(self, detector_disabled):
        """Com detector desabilitado e lista vazia, deve retornar resultado não destrutivo"""
        result = detector_disabled.detect([])

        assert result['is_destructive'] is False
        assert result['destructive_tasks'] == []
        assert result['total_destructive_count'] == 0

    @patch('src.services.destructive_detector.destructive_operations_detected_total')
    @patch('src.services.destructive_detector.destructive_tasks_per_plan')
    def test_disabled_no_metrics_recorded(
        self,
        mock_histogram,
        mock_counter,
        detector_disabled
    ):
        """Com detector desabilitado, métricas não devem ser registradas"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='delete',
                description='Delete all data',
                dependencies=[]
            )
        ]
        detector_disabled.detect(tasks)

        # Nenhuma métrica deve ser registrada
        mock_counter.labels.assert_not_called()
        mock_histogram.observe.assert_not_called()

    def test_disabled_multiple_destructive_tasks(self, detector_disabled):
        """Com detector desabilitado, múltiplas tasks destrutivas devem ser ignoradas"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='delete',
                description='Delete records',
                dependencies=[]
            ),
            TaskNode(
                task_id='task-2',
                task_type='drop',
                description='Drop table',
                dependencies=[]
            ),
            TaskNode(
                task_id='task-3',
                task_type='truncate',
                description='Truncate all production data',
                dependencies=[]
            )
        ]
        result = detector_disabled.detect(tasks)

        assert result['is_destructive'] is False
        assert result['total_destructive_count'] == 0


class TestDestructiveDetectorStrictMode:
    """Testes para modo estrito de detecção"""

    @pytest.fixture
    def settings_strict(self):
        """Mock Settings com strict mode ativado"""
        settings = MagicMock()
        settings.destructive_detection_enabled = True
        settings.destructive_detection_strict_mode = True
        return settings

    @pytest.fixture
    def detector_strict(self, settings_strict):
        """Create DestructiveDetector com strict mode"""
        return DestructiveDetector(settings_strict)

    @pytest.fixture
    def settings_normal(self):
        """Mock Settings com strict mode desativado"""
        settings = MagicMock()
        settings.destructive_detection_enabled = True
        settings.destructive_detection_strict_mode = False
        return settings

    @pytest.fixture
    def detector_normal(self, settings_normal):
        """Create DestructiveDetector sem strict mode"""
        return DestructiveDetector(settings_normal)

    def test_strict_mode_detects_high_impact_alone(self, detector_strict):
        """Strict mode: HIGH_IMPACT_INDICATORS devem ser detectados sem keyword/task_type"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Process all records from production database',
                dependencies=[]
            )
        ]
        result = detector_strict.detect(tasks)

        assert result['is_destructive'] is True
        assert 'task-1' in result['destructive_tasks']
        assert result['details'][0]['reason'] == 'high_impact_indicator_strict'
        assert result['details'][0]['has_high_impact_indicators'] is True

    def test_strict_mode_detects_todos_indicator(self, detector_strict):
        """Strict mode: indicador 'todos' deve ser detectado mesmo sem keyword destrutiva"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='update',
                description='Atualizar todos os registros',
                dependencies=[]
            )
        ]
        result = detector_strict.detect(tasks)

        assert result['is_destructive'] is True
        assert result['details'][0]['reason'] == 'high_impact_indicator_strict'
        assert 'todos' in result['details'][0]['matched_keywords']

    def test_strict_mode_detects_production_indicator(self, detector_strict):
        """Strict mode: indicador 'production' deve ser detectado mesmo sem keyword destrutiva"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='update',
                description='Update production config',
                dependencies=[]
            )
        ]
        result = detector_strict.detect(tasks)

        assert result['is_destructive'] is True
        assert result['details'][0]['reason'] == 'high_impact_indicator_strict'
        assert 'production' in result['details'][0]['matched_keywords']

    def test_strict_mode_detects_prod_indicator(self, detector_strict):
        """Strict mode: indicador 'prod' deve ser detectado mesmo sem keyword destrutiva"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Query prod database',
                dependencies=[]
            )
        ]
        result = detector_strict.detect(tasks)

        assert result['is_destructive'] is True
        assert result['details'][0]['reason'] == 'high_impact_indicator_strict'
        assert 'prod' in result['details'][0]['matched_keywords']

    def test_normal_mode_ignores_high_impact_alone(self, detector_normal):
        """Normal mode: HIGH_IMPACT_INDICATORS sem keyword/task_type não devem ser detectados"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Process all records from production database',
                dependencies=[]
            )
        ]
        result = detector_normal.detect(tasks)

        assert result['is_destructive'] is False
        assert result['destructive_tasks'] == []

    def test_strict_mode_keeps_original_reason_when_keyword_present(self, detector_strict):
        """Strict mode: se keyword destrutiva presente, mantém reason original"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='delete',
                description='Delete all production data',
                dependencies=[]
            )
        ]
        result = detector_strict.detect(tasks)

        assert result['is_destructive'] is True
        # Reason deve ser 'task_type_match' pois delete foi detectado primeiro
        assert result['details'][0]['reason'] == 'task_type_match'
        assert result['details'][0]['has_high_impact_indicators'] is True

    def test_strict_mode_severity_critical_for_high_impact(self, detector_strict):
        """Strict mode: detecção por high impact deve resultar em severity critical"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Process all records',
                dependencies=[]
            )
        ]
        result = detector_strict.detect(tasks)

        assert result['is_destructive'] is True
        # high_impact_indicators presente = severity critical
        assert result['severity'] == 'critical'

    def test_strict_mode_multiple_indicators(self, detector_strict):
        """Strict mode: múltiplos indicadores devem ser registrados"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Process all production data',
                dependencies=[]
            )
        ]
        result = detector_strict.detect(tasks)

        assert result['is_destructive'] is True
        matched_keywords = result['details'][0]['matched_keywords']
        assert 'all' in matched_keywords
        assert 'production' in matched_keywords

    def test_strict_mode_safe_task_without_indicators(self, detector_strict):
        """Strict mode: task sem indicators deve continuar segura"""
        tasks = [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Get user by id',
                dependencies=[]
            )
        ]
        result = detector_strict.detect(tasks)

        assert result['is_destructive'] is False
        assert result['destructive_tasks'] == []
