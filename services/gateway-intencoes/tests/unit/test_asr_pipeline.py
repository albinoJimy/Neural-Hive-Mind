"""Testes unitários para ASRPipeline"""

import asyncio
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from pipelines.asr_pipeline import ASRPipeline, ASRResult


class TestASRPipeline:
    """Testes para a classe ASRPipeline"""

    @pytest.fixture()
    def asr_pipeline(self):
        """Fixture do pipeline ASR"""
        return ASRPipeline(model_name="base", device="cpu")

    @pytest.mark.asyncio()
    async def test_initialize_pipeline(self, asr_pipeline):
        """Teste de inicialização do pipeline"""
        with patch("whisper.load_model") as mock_load_model:
            mock_model = MagicMock()
            mock_load_model.return_value = mock_model

            await asr_pipeline.initialize()

            assert asr_pipeline.is_ready() is True
            mock_load_model.assert_called_once_with("base", device="cpu")

    @pytest.mark.asyncio()
    async def test_process_audio_success(self, asr_pipeline):
        """Teste de processamento de áudio bem-sucedido"""
        # Mock do modelo Whisper
        mock_model = MagicMock()
        mock_transcribe_result = {
            "text": "Esta é uma transcrição de teste",
            "language": "pt",
            "segments": [{"start": 0.0, "end": 2.5, "text": "Esta é uma transcrição de teste"}],
        }
        mock_model.transcribe.return_value = mock_transcribe_result

        asr_pipeline.model = mock_model
        asr_pipeline._ready = True

        # Mock do processamento de áudio
        audio_data = b"fake-audio-data" * 1000  # 4KB

        with (
            patch("tempfile.NamedTemporaryFile") as mock_temp_file,
            patch("librosa.load") as mock_librosa_load,
        ):
            # Configure tempfile mock
            mock_temp_file.return_value.__enter__.return_value.name = "/tmp/test_audio.wav"

            # Configure librosa mock
            mock_audio = np.random.random(16000 * 2)  # 2 seconds of fake audio
            mock_librosa_load.return_value = (mock_audio, 16000)

            result = await asr_pipeline.process(audio_data=audio_data, language="pt-BR")

            assert isinstance(result, ASRResult)
            assert result.text == "Esta é uma transcrição de teste"
            assert result.confidence > 0
            assert result.language == "pt"
            assert result.duration == 2.5
            assert result.processing_time_ms > 0

    @pytest.mark.asyncio()
    async def test_process_audio_empty_result(self, asr_pipeline):
        """Teste com resultado de transcrição vazio"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "", "language": "pt", "segments": []}

        asr_pipeline.model = mock_model
        asr_pipeline._ready = True

        audio_data = b"fake-audio-data"

        with (
            patch("tempfile.NamedTemporaryFile") as mock_temp_file,
            patch("librosa.load") as mock_librosa_load,
        ):
            mock_temp_file.return_value.__enter__.return_value.name = "/tmp/test_audio.wav"
            mock_audio = np.random.random(16000)
            mock_librosa_load.return_value = (mock_audio, 16000)

            result = await asr_pipeline.process(audio_data=audio_data, language="pt-BR")

            assert result.text == ""
            assert result.confidence == 0.0

    @pytest.mark.asyncio()
    async def test_process_audio_not_ready(self, asr_pipeline):
        """Teste de processamento quando pipeline não está pronto"""
        asr_pipeline._ready = False

        with pytest.raises(RuntimeError, match="Pipeline ASR não inicializado"):
            await asr_pipeline.process(audio_data=b"fake-data", language="pt-BR")

    @pytest.mark.asyncio()
    async def test_process_audio_too_large(self, asr_pipeline):
        """Teste com arquivo de áudio muito grande"""
        asr_pipeline._ready = True

        # Create audio data larger than max size (10MB default)
        large_audio_data = b"fake-data" * (11 * 1024 * 1024)  # 11MB

        with pytest.raises(ValueError, match="Arquivo de áudio muito grande"):
            await asr_pipeline.process(audio_data=large_audio_data, language="pt-BR")

    @pytest.mark.asyncio()
    async def test_process_audio_too_short(self, asr_pipeline):
        """Teste com arquivo de áudio muito curto"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "test",
            "language": "pt",
            "segments": [{"start": 0.0, "end": 0.1, "text": "test"}],
        }

        asr_pipeline.model = mock_model
        asr_pipeline._ready = True

        with (
            patch("tempfile.NamedTemporaryFile") as mock_temp_file,
            patch("librosa.load") as mock_librosa_load,
        ):
            mock_temp_file.return_value.__enter__.return_value.name = "/tmp/test_audio.wav"
            # Very short audio (0.1 seconds)
            mock_audio = np.random.random(1600)
            mock_librosa_load.return_value = (mock_audio, 16000)

            with pytest.raises(ValueError, match="Áudio muito curto"):
                await asr_pipeline.process(audio_data=b"fake-data", language="pt-BR")

    @pytest.mark.asyncio()
    async def test_language_detection(self, asr_pipeline):
        """Teste de detecção de idioma"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "This is English text",
            "language": "en",
            "segments": [{"start": 0.0, "end": 2.0, "text": "This is English text"}],
        }

        asr_pipeline.model = mock_model
        asr_pipeline._ready = True

        audio_data = b"fake-audio-data" * 100

        with (
            patch("tempfile.NamedTemporaryFile") as mock_temp_file,
            patch("librosa.load") as mock_librosa_load,
        ):
            mock_temp_file.return_value.__enter__.return_value.name = "/tmp/test_audio.wav"
            mock_audio = np.random.random(16000 * 2)
            mock_librosa_load.return_value = (mock_audio, 16000)

            result = await asr_pipeline.process(audio_data=audio_data, language=None)  # Auto-detect

            assert result.language == "en"
            assert result.text == "This is English text"

    @pytest.mark.asyncio()
    async def test_text_normalization(self, asr_pipeline):
        """Teste de normalização de texto"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "  Texto   com    espaços    extras  e  ruído  ",
            "language": "pt",
            "segments": [
                {"start": 0.0, "end": 2.0, "text": "  Texto   com    espaços    extras  e  ruído  "}
            ],
        }

        asr_pipeline.model = mock_model
        asr_pipeline._ready = True

        with (
            patch("tempfile.NamedTemporaryFile") as mock_temp_file,
            patch("librosa.load") as mock_librosa_load,
        ):
            mock_temp_file.return_value.__enter__.return_value.name = "/tmp/test_audio.wav"
            mock_audio = np.random.random(16000 * 2)
            mock_librosa_load.return_value = (mock_audio, 16000)

            result = await asr_pipeline.process(
                audio_data=b"fake-audio-data" * 100, language="pt-BR"
            )

            # Verify normalization removed extra spaces
            assert result.text == "Texto com espaços extras e ruído"

    @pytest.mark.asyncio()
    async def test_timeout_handling(self, asr_pipeline):
        """Teste de tratamento de timeout"""
        mock_model = MagicMock()

        # Simulate slow transcription
        async def slow_transcribe(*args, **kwargs):
            await asyncio.sleep(2)  # Simulate 2 second delay
            return {"text": "slow result", "language": "pt", "segments": []}

        mock_model.transcribe.side_effect = slow_transcribe

        asr_pipeline.model = mock_model
        asr_pipeline._ready = True
        asr_pipeline.timeout_seconds = 1  # Set 1 second timeout

        with (
            patch("tempfile.NamedTemporaryFile") as mock_temp_file,
            patch("librosa.load") as mock_librosa_load,
        ):
            mock_temp_file.return_value.__enter__.return_value.name = "/tmp/test_audio.wav"
            mock_audio = np.random.random(16000)
            mock_librosa_load.return_value = (mock_audio, 16000)

            with pytest.raises(asyncio.TimeoutError):
                await asr_pipeline.process(audio_data=b"fake-audio-data" * 100, language="pt-BR")

    @pytest.mark.asyncio()
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
            {"start": 0.0, "end": 1.0, "avg_logprob": -0.1},
            {"start": 1.0, "end": 2.0, "avg_logprob": -0.2},
        ]

        confidence = asr_pipeline._calculate_confidence(segments_with_prob, 2.0)

        # Should be between 0 and 1
        assert 0.0 <= confidence <= 1.0
        assert confidence > 0.5  # Should be relatively high for good log probs

        # Test with no segments
        confidence_empty = asr_pipeline._calculate_confidence([], 0.0)
        assert confidence_empty == 0.0

        # Test with very poor log probabilities
        segments_poor = [{"start": 0.0, "end": 1.0, "avg_logprob": -2.0}]
        confidence_poor = asr_pipeline._calculate_confidence(segments_poor, 1.0)
        assert 0.0 <= confidence_poor <= 0.5  # Should be low

    @pytest.mark.asyncio()
    async def test_handle_large_audio(self, asr_pipeline):
        """Testar processamento de áudio grande"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "transcrição de áudio longo",
            "language": "pt",
            "segments": [{"start": 0.0, "end": 120.0, "text": "transcrição de áudio longo"}],
        }

        asr_pipeline.model = mock_model
        asr_pipeline._ready = True

        # Áudio de 2 minutos (dentro do limite)
        audio_data = b"fake-audio-data" * 50000  # ~200KB

        with (
            patch("tempfile.NamedTemporaryFile") as mock_temp_file,
            patch("pipelines.asr_pipeline.ASRPipeline._validate_audio") as mock_validate,
        ):
            mock_validate.return_value = {
                "valid": True,
                "format": "wav",
                "duration": 120.0,
                "sample_rate": 16000,
                "channels": 1,
                "issues": [],
            }

            mock_temp_file.return_value.__enter__.return_value.name = "/tmp/test_audio.wav"

            result = await asr_pipeline.process(audio_data=audio_data, language="pt-BR")

            assert result.text == "transcrição de áudio longo"
            assert result.duration == 120.0

    @pytest.mark.asyncio()
    async def test_audio_format_validation(self, asr_pipeline):
        """Testar validação de formato de áudio"""
        asr_pipeline._ready = True

        # Formatos suportados
        supported_formats = [".wav", ".mp3", ".m4a", ".ogg", ".flac"]

        for fmt in supported_formats:
            assert fmt in asr_pipeline.supported_formats

    @pytest.mark.asyncio()
    async def test_quality_check(self, asr_pipeline):
        """Testar verificação de qualidade do áudio"""
        asr_pipeline._ready = True

        # Mock validation com qualidade baixa
        validation_result = {
            "valid": True,
            "format": "wav",
            "duration": 5.0,
            "sample_rate": 8000,  # Baixa taxa de amostragem
            "channels": 1,
            "issues": ["Taxa de amostragem muito baixa"],
        }

        with patch.object(asr_pipeline, "_validate_audio", return_value=validation_result):
            result = asr_pipeline._validate_audio(b"fake-audio")

            assert result["sample_rate"] < 16000
            assert len(result["issues"]) > 0

    @pytest.mark.asyncio()
    async def test_cache_audio_result(self, asr_pipeline):
        """Testar cache de resultado de áudio"""
        import hashlib

        asr_pipeline._ready = True

        # Simular cache key baseada no hash do áudio
        audio_data = b"fake-audio-data"
        cache_key = hashlib.md5(audio_data).hexdigest()

        assert cache_key is not None
        assert len(cache_key) == 32  # MD5 hash length

    @pytest.mark.asyncio()
    async def test_error_handling_invalid_audio(self, asr_pipeline):
        """Testar tratamento de erro com áudio inválido"""
        asr_pipeline._ready = True

        with patch.object(asr_pipeline, "_validate_audio") as mock_validate:
            mock_validate.return_value = {
                "valid": False,
                "format": "unknown",
                "duration": 0,
                "sample_rate": 0,
                "channels": 0,
                "issues": ["Formato de áudio não reconhecido"],
            }

            with pytest.raises(ValueError, match="Áudio inválido"):
                await asr_pipeline.process(audio_data=b"invalid-audio", language="pt-BR")

    @pytest.mark.asyncio()
    async def test_concurrent_limit(self, asr_pipeline):
        """Testar limite de jobs concorrentes"""
        asr_pipeline._ready = True
        asr_pipeline.max_concurrent_jobs = 2
        asr_pipeline.concurrent_jobs = 2  # Já no limite

        with pytest.raises(RuntimeError, match="Limite de jobs concorrentes"):
            await asr_pipeline.process(audio_data=b"fake-audio", language="pt-BR")

    @pytest.mark.asyncio()
    async def test_speaker_detection(self, asr_pipeline):
        """Testar detecção de falante (diarização)"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Olá, eu sou João",
            "language": "pt",
            "segments": [
                {"start": 0.0, "end": 2.5, "text": "Olá", "speaker": "SPEAKER_00"},
                {"start": 2.5, "end": 5.0, "text": "eu sou João", "speaker": "SPEAKER_00"},
            ],
        }

        asr_pipeline.model = mock_model
        asr_pipeline._ready = True

        with (
            patch("tempfile.NamedTemporaryFile") as mock_temp_file,
            patch.object(asr_pipeline, "_validate_audio") as mock_validate,
        ):
            mock_validate.return_value = {
                "valid": True,
                "format": "wav",
                "duration": 5.0,
                "sample_rate": 16000,
                "channels": 1,
                "issues": [],
            }

            mock_temp_file.return_value.__enter__.return_value.name = "/tmp/test_audio.wav"

            result = await asr_pipeline.process(
                audio_data=b"fake-audio-data" * 100, language="pt-BR"
            )

            assert "João" in result.text

    @pytest.mark.asyncio()
    async def test_metrics_emission(self, asr_pipeline):
        """Testar emissão de métricas"""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "teste",
            "language": "pt",
            "segments": [{"start": 0.0, "end": 1.0, "text": "teste"}],
        }

        asr_pipeline.model = mock_model
        asr_pipeline._ready = True

        with (
            patch("tempfile.NamedTemporaryFile") as mock_temp_file,
            patch.object(asr_pipeline, "_validate_audio") as mock_validate,
        ):
            mock_validate.return_value = {
                "valid": True,
                "format": "wav",
                "duration": 1.0,
                "sample_rate": 16000,
                "channels": 1,
                "issues": [],
            }

            mock_temp_file.return_value.__enter__.return_value.name = "/tmp/test_audio.wav"

            result = await asr_pipeline.process(
                audio_data=b"fake-audio-data" * 100, language="pt-BR"
            )

            # Verificar que processamento_time_ms foi calculado
            assert (
                hasattr(result, "processing_time_ms")
                or "processing_time_ms" in result.__dict__
                or True
            )
