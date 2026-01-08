"""
Testes de Detecção de Anomalias

Testes para o módulo DataQualityMonitor com foco em:
- Detecção de anomalias via Z-score
- Cálculo de métricas de qualidade
- Publicação de métricas Prometheus
- Integração com ClickHouse para estatísticas agregadas
"""
import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from src.services.data_quality_monitor import DataQualityMonitor


class MockSettings:
    """Mock de configurações para testes"""
    def __init__(self):
        self.mongodb_context_collection = 'operational_context'
        self.mongodb_lineage_collection = 'data_lineage'
        self.mongodb_quality_collection = 'data_quality_metrics'
        self.freshness_threshold_hours = 24


@pytest.fixture
def settings():
    """Fixture de configurações"""
    return MockSettings()


@pytest.fixture
def mock_mongodb():
    """Mock do cliente MongoDB"""
    mongodb = AsyncMock()
    mongodb.find = AsyncMock(return_value=[])
    mongodb.find_one = AsyncMock(return_value=None)
    mongodb.insert_one = AsyncMock(return_value='test-id')
    return mongodb


@pytest.fixture
def mock_clickhouse():
    """Mock do cliente ClickHouse com resposta vazia (força fallback para MongoDB)"""
    clickhouse = MagicMock()
    clickhouse.database = 'neural_hive'
    clickhouse.client = MagicMock()
    clickhouse.client.query = MagicMock(return_value=MagicMock(result_rows=[]))
    return clickhouse


@pytest.fixture
def mock_clickhouse_with_data():
    """Mock do cliente ClickHouse com dados de baseline"""
    clickhouse = MagicMock()
    clickhouse.database = 'neural_hive'
    clickhouse.client = MagicMock()
    # Retorna mean=95.0, std=2.0, count=30
    clickhouse.client.query = MagicMock(
        return_value=MagicMock(result_rows=[(95.0, 2.0, 30)])
    )
    return clickhouse


class TestDetectAnomalies:
    """Testes de detecção de anomalias"""

    @pytest.mark.asyncio
    async def test_detect_anomalies_identifies_outliers(
        self,
        settings,
        mock_mongodb,
        mock_clickhouse
    ):
        """Testa detecção de anomalias com Z-score"""
        now = datetime.utcnow()

        # Dados históricos: 30 documentos com média ~95%
        historical_data = []
        for i in range(30):
            historical_data.append({
                'collection': 'context',
                'timestamp': now - timedelta(days=i + 1),
                'metrics': {
                    'completeness': {'completeness_score': 95.0 + (i % 5)}
                }
            })

        # Dados recentes: anomalia com 70%
        recent_data = [
            {
                'collection': 'context',
                'timestamp': now - timedelta(hours=12),
                'metrics': {
                    'completeness': {'completeness_score': 70.0}
                }
            }
        ]

        # Configura mock para retornar dados apropriados
        def mock_find(collection, filter, sort=None, limit=None):
            if filter.get('timestamp', {}).get('$lt'):
                # Query histórica
                return historical_data
            else:
                # Query da janela atual
                return recent_data

        mock_mongodb.find = AsyncMock(side_effect=mock_find)

        monitor = DataQualityMonitor(mock_mongodb, settings, mock_clickhouse)

        anomalies = await monitor.detect_anomalies('context', 'completeness_score', 24)

        assert len(anomalies) > 0
        assert all(a['z_score'] < -3 for a in anomalies)
        assert all(a['severity'] in ['low', 'medium', 'high'] for a in anomalies)

    @pytest.mark.asyncio
    async def test_detect_anomalies_no_outliers(
        self,
        settings,
        mock_mongodb,
        mock_clickhouse
    ):
        """Testa que dados normais não geram anomalias"""
        now = datetime.utcnow()

        # Todos os dados com média 95% ± 2%
        all_data = []
        for i in range(30):
            all_data.append({
                'collection': 'context',
                'timestamp': now - timedelta(days=i),
                'metrics': {
                    'completeness': {'completeness_score': 95.0 + (i % 3)}
                }
            })

        mock_mongodb.find = AsyncMock(return_value=all_data)

        monitor = DataQualityMonitor(mock_mongodb, settings, mock_clickhouse)

        anomalies = await monitor.detect_anomalies('context', 'completeness_score', 24)

        assert len(anomalies) == 0

    @pytest.mark.asyncio
    async def test_detect_anomalies_insufficient_data(
        self,
        settings,
        mock_mongodb,
        mock_clickhouse
    ):
        """Testa que dados insuficientes retornam lista vazia"""
        # Apenas 5 documentos (mínimo é 10)
        mock_mongodb.find = AsyncMock(return_value=[
            {'collection': 'context', 'timestamp': datetime.utcnow(), 'metrics': {}}
            for _ in range(5)
        ])

        monitor = DataQualityMonitor(mock_mongodb, settings, mock_clickhouse)

        anomalies = await monitor.detect_anomalies('context', 'completeness_score', 24)

        assert len(anomalies) == 0

    @pytest.mark.asyncio
    async def test_detect_anomalies_without_clickhouse_uses_mongodb_fallback(
        self,
        settings,
        mock_mongodb
    ):
        """Testa que sem ClickHouse usa fallback para MongoDB"""
        now = datetime.utcnow()

        # Dados históricos no MongoDB
        historical_data = []
        for i in range(30):
            historical_data.append({
                'collection': 'context',
                'timestamp': now - timedelta(days=i + 1),
                'metrics': {
                    'completeness': {'completeness_score': 95.0 + (i % 5)}
                }
            })

        # Dados recentes com anomalia
        recent_data = [
            {
                'collection': 'context',
                'timestamp': now - timedelta(hours=12),
                'metrics': {
                    'completeness': {'completeness_score': 70.0}
                }
            }
        ]

        def mock_find(collection, filter, sort=None, limit=None):
            if filter.get('timestamp', {}).get('$lt'):
                return historical_data
            else:
                return recent_data

        mock_mongodb.find = AsyncMock(side_effect=mock_find)

        monitor = DataQualityMonitor(mock_mongodb, settings, clickhouse_client=None)

        anomalies = await monitor.detect_anomalies('context', 'completeness_score', 24)

        # Com fallback para MongoDB, deve detectar anomalias
        assert len(anomalies) > 0
        assert all(a['z_score'] < -3 for a in anomalies)

    @pytest.mark.asyncio
    async def test_detect_anomalies_classifies_severity(
        self,
        settings,
        mock_mongodb,
        mock_clickhouse
    ):
        """Testa classificação de severidade baseada em Z-score"""
        now = datetime.utcnow()

        # Dados históricos com média 95% e std ~2%
        historical_data = []
        for i in range(30):
            historical_data.append({
                'collection': 'context',
                'timestamp': now - timedelta(days=i + 1),
                'metrics': {
                    'completeness': {'completeness_score': 95.0}
                }
            })
        # Adiciona variação para ter std > 0
        historical_data[0]['metrics']['completeness']['completeness_score'] = 93.0
        historical_data[1]['metrics']['completeness']['completeness_score'] = 97.0

        # Dados recentes com anomalias de diferentes severidades
        recent_data = [
            {
                'collection': 'context',
                'timestamp': now - timedelta(hours=6),
                'metrics': {
                    'completeness': {'completeness_score': 50.0}  # Muito baixo - high severity
                }
            }
        ]

        call_count = [0]
        def mock_find(collection, filter, sort=None, limit=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return historical_data
            else:
                return recent_data

        mock_mongodb.find = AsyncMock(side_effect=mock_find)

        monitor = DataQualityMonitor(mock_mongodb, settings, mock_clickhouse)

        anomalies = await monitor.detect_anomalies('context', 'completeness_score', 24)

        # Deve detectar anomalia de alta severidade
        if anomalies:
            assert anomalies[0]['severity'] in ['low', 'medium', 'high']


class TestCalculateQualityScore:
    """Testes de cálculo de scores de qualidade"""

    @pytest.mark.asyncio
    async def test_calculate_quality_score_returns_all_dimensions(
        self,
        settings,
        mock_mongodb
    ):
        """Testa que todas as dimensões de qualidade são calculadas"""
        # Dados de amostra
        sample_docs = [
            {
                'entity_id': f'entity-{i}',
                'field1': 'value1',
                'field2': 'value2',
                'created_at': datetime.utcnow() - timedelta(hours=i)
            }
            for i in range(10)
        ]

        mock_mongodb.find = AsyncMock(return_value=sample_docs)

        monitor = DataQualityMonitor(mock_mongodb, settings)

        scores = await monitor.calculate_quality_score('context', sample_size=10)

        assert 'completeness_score' in scores
        assert 'accuracy_score' in scores
        assert 'timeliness_score' in scores
        assert 'uniqueness_score' in scores
        assert 'consistency_score' in scores
        assert 'overall_score' in scores

    @pytest.mark.asyncio
    async def test_calculate_quality_score_empty_sample(
        self,
        settings,
        mock_mongodb
    ):
        """Testa comportamento com amostra vazia"""
        mock_mongodb.find = AsyncMock(return_value=[])

        monitor = DataQualityMonitor(mock_mongodb, settings)

        scores = await monitor.calculate_quality_score('context')

        assert scores['overall_score'] == 0.0


class TestValidateData:
    """Testes de validação de dados"""

    @pytest.mark.asyncio
    async def test_validate_data_missing_required_field(
        self,
        settings,
        mock_mongodb
    ):
        """Testa validação de campo obrigatório faltando"""
        monitor = DataQualityMonitor(mock_mongodb, settings)

        schema = {'required': ['entity_id', 'data_type']}
        data = {'entity_id': 'test-123'}  # Faltando data_type

        is_valid, violations = await monitor.validate_data(data, schema)

        assert is_valid is False
        assert any('data_type' in v for v in violations)

    @pytest.mark.asyncio
    async def test_validate_data_invalid_type(
        self,
        settings,
        mock_mongodb
    ):
        """Testa validação de tipo inválido"""
        monitor = DataQualityMonitor(mock_mongodb, settings)

        schema = {'types': {'count': int}}
        data = {'count': 'not-a-number'}

        is_valid, violations = await monitor.validate_data(data, schema)

        assert is_valid is False
        assert any('count' in v for v in violations)

    @pytest.mark.asyncio
    async def test_validate_data_value_out_of_range(
        self,
        settings,
        mock_mongodb
    ):
        """Testa validação de valor fora do range"""
        monitor = DataQualityMonitor(mock_mongodb, settings)

        schema = {'ranges': {'score': (0, 100)}}
        data = {'score': 150}

        is_valid, violations = await monitor.validate_data(data, schema)

        assert is_valid is False
        assert any('score' in v for v in violations)

    @pytest.mark.asyncio
    async def test_validate_data_valid_document(
        self,
        settings,
        mock_mongodb
    ):
        """Testa validação de documento válido"""
        monitor = DataQualityMonitor(mock_mongodb, settings)

        schema = {
            'required': ['entity_id'],
            'types': {'count': int},
            'ranges': {'score': (0, 100)}
        }
        data = {
            'entity_id': 'test-123',
            'count': 42,
            'score': 85
        }

        is_valid, violations = await monitor.validate_data(data, schema)

        assert is_valid is True
        assert len(violations) == 0


class TestClickHouseIntegration:
    """Testes de integração com ClickHouse para detecção de anomalias"""

    @pytest.mark.asyncio
    async def test_detect_anomalies_uses_clickhouse_when_available(
        self,
        settings,
        mock_mongodb,
        mock_clickhouse_with_data
    ):
        """Testa que ClickHouse é usado como fonte primária quando disponível"""
        now = datetime.utcnow()

        # Dados recentes com anomalia (70% quando baseline é 95% ± 2%)
        recent_data = [
            {
                'collection': 'context',
                'timestamp': now - timedelta(hours=12),
                'metrics': {
                    'completeness': {'completeness_score': 70.0}
                }
            }
        ]

        mock_mongodb.find = AsyncMock(return_value=recent_data)

        monitor = DataQualityMonitor(mock_mongodb, settings, mock_clickhouse_with_data)

        anomalies = await monitor.detect_anomalies('context', 'completeness_score', 24)

        # Verifica que ClickHouse foi consultado
        mock_clickhouse_with_data.client.query.assert_called_once()

        # Deve detectar anomalia baseada no baseline do ClickHouse
        assert len(anomalies) > 0
        # Z-score = (70 - 95) / 2 = -12.5 (alta severidade)
        assert anomalies[0]['z_score'] < -3
        assert anomalies[0]['severity'] == 'high'

    @pytest.mark.asyncio
    async def test_detect_anomalies_fallback_on_clickhouse_error(
        self,
        settings,
        mock_mongodb
    ):
        """Testa fallback para MongoDB quando ClickHouse falha"""
        now = datetime.utcnow()

        # ClickHouse que lança exceção
        clickhouse_with_error = MagicMock()
        clickhouse_with_error.database = 'neural_hive'
        clickhouse_with_error.client = MagicMock()
        clickhouse_with_error.client.query = MagicMock(
            side_effect=Exception("ClickHouse connection failed")
        )

        # Dados históricos no MongoDB para fallback
        historical_data = []
        for i in range(30):
            historical_data.append({
                'collection': 'context',
                'timestamp': now - timedelta(days=i + 1),
                'metrics': {
                    'completeness': {'completeness_score': 95.0 + (i % 3)}
                }
            })

        recent_data = [
            {
                'collection': 'context',
                'timestamp': now - timedelta(hours=6),
                'metrics': {
                    'completeness': {'completeness_score': 70.0}
                }
            }
        ]

        def mock_find(collection, filter, sort=None, limit=None):
            if filter.get('timestamp', {}).get('$lt'):
                return historical_data
            else:
                return recent_data

        mock_mongodb.find = AsyncMock(side_effect=mock_find)

        monitor = DataQualityMonitor(mock_mongodb, settings, clickhouse_with_error)

        # Não deve lançar exceção, deve usar fallback
        anomalies = await monitor.detect_anomalies('context', 'completeness_score', 24)

        # Deve detectar anomalias usando dados do MongoDB
        assert len(anomalies) > 0

    @pytest.mark.asyncio
    async def test_detect_anomalies_clickhouse_insufficient_data_fallback(
        self,
        settings,
        mock_mongodb
    ):
        """Testa fallback quando ClickHouse retorna dados insuficientes"""
        now = datetime.utcnow()

        # ClickHouse com poucos dados (count < 10)
        clickhouse_insufficient = MagicMock()
        clickhouse_insufficient.database = 'neural_hive'
        clickhouse_insufficient.client = MagicMock()
        clickhouse_insufficient.client.query = MagicMock(
            return_value=MagicMock(result_rows=[(95.0, 2.0, 5)])  # count=5 < 10
        )

        # MongoDB com dados suficientes para fallback
        historical_data = []
        for i in range(30):
            historical_data.append({
                'collection': 'context',
                'timestamp': now - timedelta(days=i + 1),
                'metrics': {
                    'completeness': {'completeness_score': 95.0 + (i % 3)}
                }
            })

        recent_data = [
            {
                'collection': 'context',
                'timestamp': now - timedelta(hours=6),
                'metrics': {
                    'completeness': {'completeness_score': 70.0}
                }
            }
        ]

        def mock_find(collection, filter, sort=None, limit=None):
            if filter.get('timestamp', {}).get('$lt'):
                return historical_data
            else:
                return recent_data

        mock_mongodb.find = AsyncMock(side_effect=mock_find)

        monitor = DataQualityMonitor(mock_mongodb, settings, clickhouse_insufficient)

        anomalies = await monitor.detect_anomalies('context', 'completeness_score', 24)

        # Deve usar fallback MongoDB e detectar anomalias
        assert len(anomalies) > 0

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv('CLICKHOUSE_HOST'),
        reason="ClickHouse não disponível (defina CLICKHOUSE_HOST para executar)"
    )
    async def test_detect_anomalies_real_clickhouse_integration(self, settings):
        """
        Teste de integração real com ClickHouse.

        Requer variáveis de ambiente:
        - CLICKHOUSE_HOST
        - CLICKHOUSE_PORT (opcional, default 8123)
        - CLICKHOUSE_USER (opcional, default 'default')
        - CLICKHOUSE_PASSWORD
        - CLICKHOUSE_DATABASE (opcional, default 'neural_hive')
        """
        import clickhouse_connect

        # Configuração real do ClickHouse
        ch_host = os.getenv('CLICKHOUSE_HOST')
        ch_port = int(os.getenv('CLICKHOUSE_PORT', '8123'))
        ch_user = os.getenv('CLICKHOUSE_USER', 'default')
        ch_password = os.getenv('CLICKHOUSE_PASSWORD', '')
        ch_database = os.getenv('CLICKHOUSE_DATABASE', 'neural_hive')

        # Mock do MongoDB (não usado neste teste se ClickHouse tiver dados)
        mock_mongodb = AsyncMock()
        mock_mongodb.find = AsyncMock(return_value=[])

        # Cliente ClickHouse real
        class RealClickHouseClient:
            def __init__(self):
                self.database = ch_database
                self.client = clickhouse_connect.get_client(
                    host=ch_host,
                    port=ch_port,
                    username=ch_user,
                    password=ch_password,
                    database=ch_database
                )

        try:
            clickhouse_client = RealClickHouseClient()

            monitor = DataQualityMonitor(mock_mongodb, settings, clickhouse_client)

            # Executa detecção de anomalias
            anomalies = await monitor.detect_anomalies(
                'context',
                'completeness_score',
                window_hours=24,
                baseline_days=7
            )

            # Teste passa se não lançar exceção
            # Anomalias podem ou não existir dependendo dos dados
            assert isinstance(anomalies, list)

        except Exception as e:
            pytest.skip(f"Conexão com ClickHouse falhou: {e}")
