"""
Testes para SignalDetector.
Detecção de sinais de mudança em código.
"""
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

from src.signals.signal_detector import SignalDetector, FileSignal


@pytest.fixture
def signal_detector():
    """Instância de SignalDetector para testes."""
    return SignalDetector(window_minutes=60)


@pytest.fixture
def temp_codebase():
    """Cria codebase temporário para testes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Criar alguns arquivos
        (Path(tmpdir) / 'simple.py').write_text('x = 1\ny = 2')
        (Path(tmpdir) / 'complex.py').write_text('''
class Repository:
    def find(self):
        pass

class Service:
    def __init__(self, repo):
        self.repo = repo
''')
        yield tmpdir


class TestSignalDetection:
    """Testes de detecção de sinais."""

    def test_detect_new_files(self, signal_detector, temp_codebase):
        """Testa detecção de arquivos novos."""
        signals = signal_detector.scan_directory(temp_codebase)

        # Deve detectar criação dos arquivos
        created = [s for s in signals if s.signal_type == 'created']
        assert len(created) >= 2

    def test_detect_modified_files(self, signal_detector, temp_codebase):
        """Testa detecção de arquivos modificados."""
        # Primeira scan - arquivos novos
        signal_detector.scan_directory(temp_codebase)

        # Modificar um arquivo
        (Path(temp_codebase) / 'simple.py').write_text('x = 2\ny = 3\nz = 4')

        # Segunda scan - deve detectar modificação
        signals = signal_detector.scan_directory(temp_codebase)

        modified = [s for s in signals if s.signal_type == 'modified']
        assert len(modified) == 1
        assert modified[0].filepath.endswith('simple.py')

    def test_detect_deleted_files(self, signal_detector, temp_codebase):
        """Testa detecção de arquivos deletados."""
        # Primeira scan
        signal_detector.scan_directory(temp_codebase)

        # Deletar arquivo
        (Path(temp_codebase) / 'simple.py').unlink()

        # Segunda scan
        signals = signal_detector.scan_directory(temp_codebase)

        deleted = [s for s in signals if s.signal_type == 'deleted']
        assert len(deleted) == 1
        assert 'simple.py' in deleted[0].filepath

    def test_scan_with_extensions_filter(self, signal_detector, temp_codebase):
        """Testa filtro por extensão de arquivo."""
        # Criar arquivo .txt que não deve ser detectado
        (Path(temp_codebase) / 'readme.txt').write_text('Some text')

        signals = signal_detector.scan_directory(temp_codebase, extensions={'.py'})

        # Não deve detectar .txt
        detected_paths = [s.filepath for s in signals]
        assert not any('readme.txt' in path for path in detected_paths)


class TestSignalIntensity:
    """Testes de cálculo de intensidade de sinais."""

    def test_creation_intensity_small_file(self, signal_detector):
        """Testa intensidade de criação para arquivo pequeno."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / 'small.py'
            filepath.write_text('x = 1')

            signals = signal_detector.scan_directory(tmpdir)
            created = [s for s in signals if s.signal_type == 'created']

            assert len(created) == 1
            # Arquivo pequeno tem intensidade baixa
            assert created[0].intensity < 0.5

    def test_creation_intensity_large_file(self, signal_detector):
        """Testa intensidade de criação para arquivo grande."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / 'large.py'
            # Criar arquivo grande com muitas classes
            content = '\n'.join([
                f'class Class{i}:\n    def method{j}(self): pass'
                for i in range(20)
                for j in range(5)
            ])
            filepath.write_text(content)

            signals = signal_detector.scan_directory(tmpdir)
            created = [s for s in signals if s.signal_type == 'created']

            assert len(created) == 1
            # Arquivo grande tem intensidade maior
            assert created[0].intensity > 0.3

    def test_modification_intensity(self, signal_detector, temp_codebase):
        """Testa intensidade de modificação."""
        # Primeira scan
        signal_detector.scan_directory(temp_codebase)

        # Modificar significativamente
        large_content = '\n'.join([f'def func{i}(): pass' for i in range(50)])
        (Path(temp_codebase) / 'simple.py').write_text(large_content)

        # Segunda scan
        signals = signal_detector.scan_directory(temp_codebase)
        modified = [s for s in signals if s.signal_type == 'modified']

        assert len(modified) == 1
        # Modificação grande aumenta intensidade
        assert modified[0].intensity > 0.2


class TestSignalAggregation:
    """Testes de agregação de sinais."""

    def test_get_signals_in_window(self, signal_detector, temp_codebase):
        """Testa recuperar sinais dentro da janela de tempo."""
        signal_detector.scan_directory(temp_codebase)

        signals = signal_detector.get_signals_in_window(minutes=60)

        # Deve ter pelo menos os sinais da scan
        assert len(signals) >= 2

    def test_get_signals_outside_window(self, signal_detector):
        """Testa que sinais antigos são excluídos."""
        # Criar sinal antigo
        old_signal = FileSignal('old.py', 'created', 0.5)
        old_signal.timestamp = datetime.now() - timedelta(minutes=120)
        signal_detector._signals.append(old_signal)

        # Criar sinal recente
        recent_signal = FileSignal('new.py', 'created', 0.5)
        signal_detector._signals.append(recent_signal)

        # Buscar últimos 60 minutos
        signals = signal_detector.get_signals_in_window(minutes=60)

        # Apenas o sinal recente deve aparecer
        assert len(signals) == 1

    def test_get_signal_summary(self, signal_detector, temp_codebase):
        """Testa resumo de sinais."""
        signal_detector.scan_directory(temp_codebase)

        summary = signal_detector.get_signal_summary(minutes=60)

        assert 'total_signals' in summary
        assert 'by_type' in summary
        assert 'by_file' in summary
        assert 'total_intensity' in summary
        assert summary['total_signals'] >= 2

    def test_get_hotspots(self, signal_detector, temp_codebase):
        """Testa identificação de hotspots."""
        # Fazer múltiplas scans para gerar atividade
        for _ in range(3):
            signal_detector.scan_directory(temp_codebase)
            # Modificar arquivo para gerar mais sinais
            (Path(temp_codebase) / 'simple.py').write_text(f'x = {datetime.now().second}')

        hotspots = signal_detector.get_hotspots(limit=5)

        assert len(hotspots) > 0
        assert 'filepath' in hotspots[0]
        assert 'activity_count' in hotspots[0]
        assert 'total_intensity' in hotspots[0]


class TestHighActivityDetection:
    """Testes de detecção de alta atividade."""

    def test_get_high_activity_files(self, signal_detector, temp_codebase):
        """Testa recuperar arquivos com alta atividade."""
        # Gerar atividade múltipla
        for _ in range(6):
            signal_detector.scan_directory(temp_codebase)
            (Path(temp_codebase) / 'simple.py').write_text(f'x = {datetime.now().microsecond}')

        high_activity = signal_detector.get_high_activity_files(threshold=5)

        # Deve ter pelo menos um arquivo com alta atividade
        assert len(high_activity) >= 1

    def test_detect_burst_activity(self, signal_detector, temp_codebase):
        """Testa detecção de burst de atividade."""
        # Criar atividade concentrada em um arquivo
        filepath = Path(temp_codebase) / 'burst.py'
        filepath.write_text('initial')

        for _ in range(10):
            signal_detector.scan_directory(temp_codebase)
            filepath.write_text(f'version{_}')

        burst_files = signal_detector.detect_burst_activity(threshold=2.0)

        # Arquivo burst deve estar na lista
        assert any('burst.py' in f for f in burst_files)


class TestFileSignal:
    """Testes da classe FileSignal."""

    def test_to_dict(self):
        """Testa conversão para dicionário."""
        signal = FileSignal('/path/to/file.py', 'created', 0.75, {'size': 100})

        result = signal.to_dict()

        assert result['filepath'] == '/path/to/file.py'
        assert result['signal_type'] == 'created'
        assert result['intensity'] == 0.75
        assert result['metadata']['size'] == 100
        assert 'timestamp' in result


class TestDetectorReset:
    """Testes de reset do detector."""

    def test_reset_clears_state(self, signal_detector, temp_codebase):
        """Testa que reset limpa todo o estado."""
        # Gerar sinais
        signal_detector.scan_directory(temp_codebase)

        assert len(signal_detector._signals) > 0
        assert len(signal_detector._file_hashes) > 0

        # Reset
        signal_detector.reset()

        assert len(signal_detector._signals) == 0
        assert len(signal_detector._file_hashes) == 0
        assert len(signal_detector._activity_counts) == 0


class TestSignalFiltering:
    """Testes de filtragem de sinais."""

    def test_filter_by_intensity(self, signal_detector, temp_codebase):
        """Testa filtro por intensidade mínima."""
        signal_detector.scan_directory(temp_codebase)

        # Filtrar sinais com intensidade > 0.1
        filtered = signal_detector.filter_signals(min_intensity=0.1)

        # Todos os sinais com intensidade maior que 0.1
        for signal in filtered:
            assert signal.intensity >= 0.1

    def test_filter_by_type(self, signal_detector, temp_codebase):
        """Testa filtro por tipo de sinal."""
        signal_detector.scan_directory(temp_codebase)

        created_signals = signal_detector.filter_signals(signal_type='created')

        # Todos devem ser do tipo created
        for signal in created_signals:
            assert signal.signal_type == 'created'

    def test_filter_by_path_pattern(self, signal_detector, temp_codebase):
        """Testa filtro por padrão de caminho."""
        signal_detector.scan_directory(temp_codebase)

        # Filtrar apenas arquivos .py
        py_signals = signal_detector.filter_signals(path_pattern='*.py')

        # Todos devem terminar com .py
        for signal in py_signals:
            assert signal.filepath.endswith('.py')


class TestSignalStatistics:
    """Testes de estatísticas de sinais."""

    def test_get_activity_trend(self, signal_detector, temp_codebase):
        """Testa cálculo de tendência de atividade."""
        # Gerar atividade em múltiplos pontos
        for i in range(5):
            signal_detector.scan_directory(temp_codebase)
            (Path(temp_codebase) / 'simple.py').write_text(f'x = {i}')

        trend = signal_detector.get_activity_trend()

        assert 'trend' in trend  # 'increasing', 'decreasing', 'stable'
        assert 'average_intensity' in trend
        assert 'total_signals' in trend

    def test_get_most_changed_files(self, signal_detector, temp_codebase):
        """Testa identificar arquivos mais modificados."""
        # Modificar simple.py múltiplas vezes
        for i in range(8):
            signal_detector.scan_directory(temp_codebase)
            (Path(temp_codebase) / 'simple.py').write_text(f'x = {i}')

        most_changed = signal_detector.get_most_changed_files(limit=5)

        assert len(most_changed) > 0
        assert 'filepath' in most_changed[0]
        assert 'change_count' in most_changed[0]
        # simple.py deve estar no topo
        assert any('simple.py' in f['filepath'] for f in most_changed)


class TestSignalCorrelation:
    """Testes de correlação entre sinais."""

    def test_detect_related_changes(self, signal_detector, temp_codebase):
        """Testa detecção de mudanças relacionadas."""
        # Criar múltiplos arquivos em sequência
        for i in range(3):
            filepath = Path(temp_codebase) / f'module_{i}.py'
            filepath.write_text(f'class Module{i}: pass')
            signal_detector.scan_directory(temp_codebase)

        # Detectar grupos de mudanças relacionadas
        related = signal_detector.detect_related_changes(time_window_seconds=60)

        # Deve identificar ao menos um grupo
        assert len(related) >= 1


class TestSignalExport:
    """Testes de exportação de sinais."""

    def test_export_to_json(self, signal_detector, temp_codebase):
        """Testa exportação de sinais para JSON."""
        signal_detector.scan_directory(temp_codebase)

        import json
        json_str = signal_detector.export_to_json()

        # Validar JSON
        data = json.loads(json_str)
        assert 'signals' in data
        assert 'metadata' in data
        assert len(data['signals']) >= 2

    def test_export_to_csv(self, signal_detector, temp_codebase, tmp_path):
        """Testa exportação de sinais para CSV."""
        signal_detector.scan_directory(temp_codebase)

        csv_path = tmp_path / 'signals.csv'
        signal_detector.export_to_csv(str(csv_path))

        # Validar arquivo criado
        assert csv_path.exists()

        # Validar conteúdo
        content = csv_path.read_text()
        assert 'filepath' in content
        assert 'signal_type' in content
        assert 'intensity' in content


class TestSignalValidation:
    """Testes de validação de sinais."""

    def test_validate_signal_integrity(self, signal_detector):
        """Testa validação de integridade do sinal."""
        signal = FileSignal('/valid/path.py', 'created', 0.5)

        is_valid = signal_detector.validate_signal(signal)

        assert is_valid is True

    def test_validate_invalid_signal(self, signal_detector):
        """Testa validação de sinal inválido."""
        # Criar sinal com intensidade negativa (inválida)
        signal = FileSignal('/path.py', 'created', -0.1)

        is_valid = signal_detector.validate_signal(signal)

        assert is_valid is False

    def test_validate_signal_without_filepath(self, signal_detector):
        """Testa validação de sinal sem filepath."""
        signal = FileSignal('', 'created', 0.5)

        is_valid = signal_detector.validate_signal(signal)

        assert is_valid is False


class TestSignalClustering:
    """Testes de agrupamento de sinais."""

    def test_cluster_signals_by_directory(self, signal_detector, temp_codebase):
        """Testa agrupamento de sinais por diretório."""
        signal_detector.scan_directory(temp_codebase)

        clusters = signal_detector.cluster_signals_by_directory()

        assert len(clusters) > 0
        assert 'directory' in clusters[0]
        assert 'signal_count' in clusters[0]

    def test_cluster_signals_by_extension(self, signal_detector, temp_codebase):
        """Testa agrupamento de sinais por extensão."""
        signal_detector.scan_directory(temp_codebase)

        clusters = signal_detector.cluster_signals_by_extension()

        assert len(clusters) > 0
        assert 'extension' in clusters[0]
        assert 'signal_count' in clusters[0]
        # Deve ter .py
        assert any(c['extension'] == '.py' for c in clusters)
