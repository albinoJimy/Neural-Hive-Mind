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
