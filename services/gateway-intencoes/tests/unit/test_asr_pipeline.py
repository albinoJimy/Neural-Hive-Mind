"""Testes unitários para ASRPipeline"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np

from pipelines.asr_pipeline import ASRPipeline, ASRResult


class TestASRPipeline:
    """Testes para a classe ASRPipeline"""

    @pytest.fixture
    def asr_pipeline(self):
        """Fixture do pipeline ASR"""
        return ASRPipeline(
            model_name="base",
            device="cpu"
        )

    @pytest.mark.asyncio
    async def test_initialize_pipeline(self, asr_pipeline):
        """Teste de inicialização do pipeline"""
        with patch('whisper.load_model') as mock_load_model:
            mock_model = MagicMock()
            mock_load_model.return_value = mock_model

            await asr_pipeline.initialize()

            assert asr_pipeline.is_ready() is True
            mock_load_model.assert_called_once_with("base", device="cpu")

    @pytest.mark.asyncio
    async def test_process_audio_success(self, asr_pipeline):
        """Teste de processamento de áudio bem-sucedido"""
        # Mock do modelo Whisper
        mock_model = MagicMock()
        mock_transcribe_result = {
            'text': 'Esta é uma transcrição de teste',
            'language': 'pt',
            'segments': [
                {
                    'start': 0.0,
                    'end': 2.5,
                    'text': 'Esta é uma transcrição de teste'
                }
            ]
        }
        mock_model.transcribe.return_value = mock_transcribe_result

        asr_pipeline.model = mock_model
        asr_pipeline._ready = True

        # Mock do processamento de áudio
        audio_data = b"fake-audio-data" * 1000  # 4KB

        with patch('tempfile.NamedTemporaryFile') as mock_temp_file, \
             patch('librosa.load') as mock_librosa_load:

            # Configure tempfile mock
            mock_temp_file.return_value.__enter__.return_value.name = "/tmp/test_audio.wav"

            # Configure librosa mock
            mock_audio = np.random.random(16000 * 2)  # 2 seconds of fake audio
            mock_librosa_load.return_value = (mock_audio, 16000)

            result = await asr_pipeline.process(
                audio_data=audio_data,
                language="pt-BR"
            )

            assert isinstance(result, ASRResult)
            assert result.text == 'Esta é uma transcrição de teste'
            assert result.confidence > 0
            assert result.language == 'pt'
            assert result.duration == 2.5
            assert result.processing_time_ms > 0

    @pytest.mark.asyncio
    async def test_process_audio_empty_result(self, asr_pipeline):
        """Teste com resultado de transcrição vazio"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            'text': '',
            'language': 'pt',
            'segments': []
        }

        asr_pipeline.model = mock_model
        asr_pipeline._ready = True

        audio_data = b"fake-audio-data"

        with patch('tempfile.NamedTemporaryFile') as mock_temp_file, \
             patch('librosa.load') as mock_librosa_load:

            mock_temp_file.return_value.__enter__.return_value.name = "/tmp/test_audio.wav"
            mock_audio = np.random.random(16000)
            mock_librosa_load.return_value = (mock_audio, 16000)

            result = await asr_pipeline.process(
                audio_data=audio_data,
                language="pt-BR"
            )

            assert result.text == ''
            assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_process_audio_not_ready(self, asr_pipeline):
        """Teste de processamento quando pipeline não está pronto"""
        asr_pipeline._ready = False

        with pytest.raises(RuntimeError, match="Pipeline ASR não inicializado"):
            await asr_pipeline.process(
                audio_data=b"fake-data",
                language="pt-BR"
            )

    @pytest.mark.asyncio
    async def test_process_audio_too_large(self, asr_pipeline):
        """Teste com arquivo de áudio muito grande"""
        asr_pipeline._ready = True

        # Create audio data larger than max size (10MB default)
        large_audio_data = b"fake-data" * (11 * 1024 * 1024)  # 11MB

        with pytest.raises(ValueError, match="Arquivo de áudio muito grande"):
            await asr_pipeline.process(
                audio_data=large_audio_data,
                language="pt-BR"
            )

    @pytest.mark.asyncio
    async def test_process_audio_too_short(self, asr_pipeline):
        """Teste com arquivo de áudio muito curto"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            'text': 'test',
            'language': 'pt',
            'segments': [
                {'start': 0.0, 'end': 0.1, 'text': 'test'}
            ]
        }

        asr_pipeline.model = mock_model
        asr_pipeline._ready = True

        with patch('tempfile.NamedTemporaryFile') as mock_temp_file, \
             patch('librosa.load') as mock_librosa_load:

            mock_temp_file.return_value.__enter__.return_value.name = "/tmp/test_audio.wav"
            # Very short audio (0.1 seconds)
            mock_audio = np.random.random(1600)
            mock_librosa_load.return_value = (mock_audio, 16000)

            with pytest.raises(ValueError, match="Áudio muito curto"):
                await asr_pipeline.process(
                    audio_data=b"fake-data",
                    language="pt-BR"
                )

    @pytest.mark.asyncio
    async def test_language_detection(self, asr_pipeline):
        """Teste de detecção de idioma"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            'text': 'This is English text',
            'language': 'en',
            'segments': [
                {'start': 0.0, 'end': 2.0, 'text': 'This is English text'}
            ]
        }

        asr_pipeline.model = mock_model
        asr_pipeline._ready = True

        audio_data = b"fake-audio-data" * 100

        with patch('tempfile.NamedTemporaryFile') as mock_temp_file, \
             patch('librosa.load') as mock_librosa_load:

            mock_temp_file.return_value.__enter__.return_value.name = "/tmp/test_audio.wav"
            mock_audio = np.random.random(16000 * 2)
            mock_librosa_load.return_value = (mock_audio, 16000)

            result = await asr_pipeline.process(
                audio_data=audio_data,
                language=None  # Auto-detect
            )

            assert result.language == 'en'
            assert result.text == 'This is English text'

    @pytest.mark.asyncio
    async def test_text_normalization(self, asr_pipeline):
        """Teste de normalização de texto"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            'text': '  Texto   com    espaços    extras  e  ruído  ',
            'language': 'pt',
            'segments': [
                {'start': 0.0, 'end': 2.0, 'text': '  Texto   com    espaços    extras  e  ruído  '}
            ]
        }

        asr_pipeline.model = mock_model
        asr_pipeline._ready = True

        with patch('tempfile.NamedTemporaryFile') as mock_temp_file, \
             patch('librosa.load') as mock_librosa_load:

            mock_temp_file.return_value.__enter__.return_value.name = "/tmp/test_audio.wav"
            mock_audio = np.random.random(16000 * 2)
            mock_librosa_load.return_value = (mock_audio, 16000)

            result = await asr_pipeline.process(
                audio_data=b"fake-audio-data" * 100,
                language="pt-BR"
            )

            # Verify normalization removed extra spaces
            assert result.text == "Texto com espaços extras e ruído"

    @pytest.mark.asyncio
    async def test_timeout_handling(self, asr_pipeline):
        """Teste de tratamento de timeout"""
        mock_model = MagicMock()

        # Simulate slow transcription
        async def slow_transcribe(*args, **kwargs):
            await asyncio.sleep(2)  # Simulate 2 second delay
            return {
                'text': 'slow result',
                'language': 'pt',
                'segments': []
            }

        mock_model.transcribe.side_effect = slow_transcribe

        asr_pipeline.model = mock_model
        asr_pipeline._ready = True
        asr_pipeline.timeout_seconds = 1  # Set 1 second timeout

        with patch('tempfile.NamedTemporaryFile') as mock_temp_file, \
             patch('librosa.load') as mock_librosa_load:

            mock_temp_file.return_value.__enter__.return_value.name = "/tmp/test_audio.wav"
            mock_audio = np.random.random(16000)
            mock_librosa_load.return_value = (mock_audio, 16000)

            with pytest.raises(asyncio.TimeoutError):
                await asr_pipeline.process(
                    audio_data=b"fake-audio-data" * 100,
                    language="pt-BR"
                )

    @pytest.mark.asyncio
    async def test_close_pipeline(self, asr_pipeline):
        """Teste de fechamento do pipeline"""
        asr_pipeline._ready = True
        asr_pipeline.model = MagicMock()

        await asr_pipeline.close()

        assert asr_pipeline.is_ready() is False
        assert asr_pipeline.model is None

    def test_confidence_calculation(self, asr_pipeline):
        """Teste do cálculo de confiança"""
        # Test with segments containing probabilities
        segments_with_prob = [
            {'start': 0.0, 'end': 1.0, 'avg_logprob': -0.1},
            {'start': 1.0, 'end': 2.0, 'avg_logprob': -0.2},
        ]

        confidence = asr_pipeline._calculate_confidence(segments_with_prob, 2.0)

        # Should be between 0 and 1
        assert 0.0 <= confidence <= 1.0
        assert confidence > 0.5  # Should be relatively high for good log probs

        # Test with no segments
        confidence_empty = asr_pipeline._calculate_confidence([], 0.0)
        assert confidence_empty == 0.0

        # Test with very poor log probabilities
        segments_poor = [
            {'start': 0.0, 'end': 1.0, 'avg_logprob': -2.0}
        ]
        confidence_poor = asr_pipeline._calculate_confidence(segments_poor, 1.0)
        assert 0.0 <= confidence_poor <= 0.5  # Should be low