"""Pipeline ASR usando Whisper para conversão de áudio em texto"""
import asyncio
import tempfile
import whisper
import os
import subprocess
import wave
import struct
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path
import hashlib
from models.intent_envelope import ASRResult
from config.settings import get_settings

logger = logging.getLogger(__name__)

class ASRPipeline:
    def __init__(self, model_name: str = None, device: str = None):
        self.settings = get_settings()
        self.model_name = model_name or self.settings.asr_model_name
        self.device = device or self.settings.asr_device
        self.model: Optional[whisper.Whisper] = None
        self._ready = False
        self._model_lock = asyncio.Lock()  # Lock para sincronização de carregamento
        self._loading = False  # Flag para indicar carregamento em andamento
        self.lazy_loading = self.settings.asr_lazy_loading
        self.model_cache_dir = Path(self.settings.asr_model_cache_dir)
        self.model_cache_dir.mkdir(parents=True, exist_ok=True)
        self.supported_formats = {'.wav', '.mp3', '.m4a', '.ogg', '.flac'}
        self.fallback_models = ['tiny', 'base', 'small']  # Fallback hierarchy
        self.concurrent_jobs = 0
        self.max_concurrent_jobs = self.settings.asr_max_concurrent_jobs

    async def initialize(self):
        """Inicializar modelo Whisper com cache e fallback"""
        try:
            if self.lazy_loading:
                # Apenas validar que diretório de cache existe e está acessível
                logger.info(f"Lazy loading habilitado - modelo {self.model_name} será carregado sob demanda")
                if not self.model_cache_dir.exists():
                    logger.warning(f"Diretório de cache {self.model_cache_dir} não existe, criando...")
                    self.model_cache_dir.mkdir(parents=True, exist_ok=True)
                self._ready = True
                logger.info(f"Pipeline ASR inicializado com lazy loading para modelo {self.model_name}")
            else:
                # Carregar modelo imediatamente
                logger.info(f"Carregando modelo Whisper: {self.model_name}")
                self.model = await self._load_model_with_cache(self.model_name)
                self._ready = True
                logger.info(f"Modelo Whisper {self.model_name} carregado com sucesso")
        except Exception as e:
            logger.error(f"Erro carregando modelo {self.model_name}: {e}")
            # Tentar fallback para modelos menores
            await self._try_fallback_models()

    async def _load_model_with_cache(self, model_name: str) -> whisper.Whisper:
        """Carregar modelo com cache em disco do volume persistente"""
        try:
            # Verificar se modelo já existe no volume persistente
            model_cache_path = self.model_cache_dir / f"{model_name}.pt"

            if model_cache_path.exists():
                logger.info(f"Modelo encontrado no cache do volume persistente: {model_cache_path}")
            else:
                logger.info(f"Modelo não encontrado no cache, será baixado para {self.model_cache_dir}")

            # Configurar diretório de cache do Whisper para usar volume persistente
            os.environ['XDG_CACHE_HOME'] = str(self.model_cache_dir.parent)

            # whisper.load_model baixa e faz cache automaticamente
            return await asyncio.get_event_loop().run_in_executor(
                None, whisper.load_model, model_name, self.device
            )
        except Exception as e:
            logger.error(f"Erro carregando modelo {model_name}: {e}")
            raise

    async def _try_fallback_models(self):
        """Tentar modelos de fallback em caso de erro de memória"""
        for fallback_model in self.fallback_models:
            if fallback_model == self.model_name:
                continue  # Pular modelo que já falhou

            try:
                logger.warning(f"Tentando fallback para modelo: {fallback_model}")
                self.model = await self._load_model_with_cache(fallback_model)
                self.model_name = fallback_model  # Atualizar modelo atual
                self._ready = True
                logger.info(f"Fallback bem-sucedido para modelo {fallback_model}")
                return
            except Exception as e:
                logger.error(f"Fallback falhou para modelo {fallback_model}: {e}")
                continue

        # Se todos os fallbacks falharam
        raise RuntimeError("Não foi possível carregar nenhum modelo Whisper")

    async def _ensure_model_loaded(self):
        """Garantir que modelo está carregado (para lazy loading) com sincronização"""
        # Verificação rápida sem lock
        if self.model is not None:
            return

        # Usar lock para garantir que apenas uma corrotina carregue o modelo
        async with self._model_lock:
            # Verificar novamente dentro do lock (double-check locking)
            if self.model is not None:
                return

            # Evitar reentrância
            if self._loading:
                # Aguardar até que o carregamento termine
                while self._loading:
                    await asyncio.sleep(0.1)
                return

            self._loading = True
            try:
                logger.info(f"Carregando modelo sob demanda: {self.model_name}")
                self.model = await self._load_model_with_cache(self.model_name)
                logger.info(f"Modelo {self.model_name} carregado sob demanda com sucesso")
            except Exception as e:
                logger.error(f"Erro carregando modelo sob demanda: {e}")
                await self._try_fallback_models()
            finally:
                self._loading = False

    def is_ready(self) -> bool:
        if self.lazy_loading:
            return self._ready  # Pipeline pronto mesmo sem modelo carregado
        return self._ready and self.model is not None

    def _validate_audio(self, audio_data: bytes) -> Dict[str, Any]:
        """Validar formato e qualidade do áudio"""
        validation_result = {
            "valid": True,
            "format": "unknown",
            "duration": 0,
            "sample_rate": 0,
            "channels": 0,
            "issues": []
        }

        try:
            # Salvar temporariamente para análise
            with tempfile.NamedTemporaryFile(suffix=".tmp", delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_path = temp_file.name

            try:
                # Tentar detectar formato usando ffprobe
                result = subprocess.run([
                    'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', temp_path
                ], capture_output=True, text=True, timeout=10)

                if result.returncode == 0:
                    import json
                    metadata = json.loads(result.stdout)

                    if 'streams' in metadata and len(metadata['streams']) > 0:
                        audio_stream = metadata['streams'][0]

                        validation_result.update({
                            "format": metadata['format'].get('format_name', 'unknown'),
                            "duration": float(metadata['format'].get('duration', 0)),
                            "sample_rate": int(audio_stream.get('sample_rate', 0)),
                            "channels": int(audio_stream.get('channels', 0))
                        })

                        # Validações
                        if validation_result["duration"] < 0.1:
                            validation_result["issues"].append("Áudio muito curto (< 0.1s)")

                        if validation_result["duration"] > 300:  # 5 minutos
                            validation_result["issues"].append("Áudio muito longo (> 5min)")

                        if validation_result["sample_rate"] < 8000:
                            validation_result["issues"].append("Taxa de amostragem muito baixa")

                        if len(audio_data) > 50 * 1024 * 1024:  # 50MB
                            validation_result["issues"].append("Arquivo muito grande")

                        if validation_result["issues"]:
                            validation_result["valid"] = False

                else:
                    validation_result["valid"] = False
                    validation_result["issues"].append("Formato de áudio não reconhecido")

            finally:
                os.unlink(temp_path)

        except subprocess.TimeoutExpired:
            validation_result["valid"] = False
            validation_result["issues"].append("Timeout na análise do áudio")
        except Exception as e:
            validation_result["valid"] = False
            validation_result["issues"].append(f"Erro na validação: {str(e)}")

        return validation_result

    async def _convert_audio_format(self, audio_data: bytes, target_format: str = "wav") -> bytes:
        """Converter áudio para formato suportado usando ffmpeg"""
        with tempfile.NamedTemporaryFile(suffix=".input", delete=False) as input_file:
            input_file.write(audio_data)
            input_path = input_file.name

        output_path = f"{input_path}.{target_format}"

        try:
            # Converter usando ffmpeg
            result = await asyncio.get_event_loop().run_in_executor(
                None, subprocess.run, [
                    'ffmpeg', '-i', input_path, '-ar', '16000', '-ac', '1', '-f', target_format, output_path, '-y'
                ], subprocess.DEVNULL, subprocess.DEVNULL
            )

            if result.returncode != 0:
                raise RuntimeError(f"Erro na conversão de áudio: código {result.returncode}")

            # Ler áudio convertido
            with open(output_path, 'rb') as f:
                converted_data = f.read()

            logger.info(f"Áudio convertido para {target_format}: {len(audio_data)} -> {len(converted_data)} bytes")
            return converted_data

        finally:
            # Limpar arquivos temporários
            for path in [input_path, output_path]:
                if os.path.exists(path):
                    os.unlink(path)

    def get_supported_languages(self) -> List[str]:
        """Retornar lista de idiomas suportados pelo modelo"""
        if not self.model:
            return []

        # Lista de idiomas suportados pelo Whisper
        return [
            'pt', 'en', 'es', 'fr', 'de', 'it', 'ja', 'ko', 'zh', 'ru',
            'ar', 'hi', 'tr', 'pl', 'nl', 'sv', 'da', 'no', 'fi'
        ]

    async def process(self, audio_data: bytes, language: str = "pt") -> ASRResult:
        """Processar áudio para texto com validação e controle de concorrência"""
        if not self.is_ready():
            raise RuntimeError("Pipeline ASR não inicializado")

        # Garantir que modelo está carregado (lazy loading)
        await self._ensure_model_loaded()

        # Verificar limite de jobs concorrentes
        if self.concurrent_jobs >= self.max_concurrent_jobs:
            raise RuntimeError(f"Limite de jobs concorrentes atingido: {self.max_concurrent_jobs}")

        try:
            self.concurrent_jobs += 1

            # Validar áudio antes do processamento
            validation = self._validate_audio(audio_data)
            if not validation["valid"]:
                raise ValueError(f"Áudio inválido: {', '.join(validation['issues'])}")

            logger.info(f"Áudio validado: {validation['format']}, {validation['duration']:.2f}s")

            # Verificar se precisa converter formato
            processed_audio = audio_data
            if validation["format"] not in ["wav", "wave"]:
                logger.info(f"Convertendo áudio de {validation['format']} para WAV")
                processed_audio = await self._convert_audio_format(audio_data, "wav")

            # Calcular timeout baseado na duração do áudio
            audio_duration = validation.get("duration", 60)  # Default 60s se não detectado
            timeout = max(self.settings.asr_timeout_seconds, int(audio_duration * 3))  # 3x a duração

            # Salvar áudio temporariamente
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(processed_audio)
                temp_path = temp_file.name

            try:
                # Executar Whisper em thread separada com timeout
                result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, self._transcribe, temp_path, language, validation
                    ),
                    timeout=timeout
                )
                return result

            except asyncio.TimeoutError:
                logger.error(f"Timeout na transcrição após {timeout}s")
                raise RuntimeError(f"Timeout na transcrição do áudio (limite: {timeout}s)")

            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

        finally:
            self.concurrent_jobs -= 1

    def _transcribe(self, audio_path: str, language: str, validation: Dict[str, Any]) -> ASRResult:
        """Transcrever áudio usando Whisper com métricas melhoradas"""
        try:
            # Configurar parâmetros do Whisper baseados na validação
            whisper_params = {
                "language": language,
                "task": "transcribe",
                "fp16": self.device != "cpu",  # FP16 apenas em GPU
                "verbose": False
            }

            # Ajustar parâmetros baseados na qualidade do áudio
            if validation.get("sample_rate", 0) < 16000:
                # Áudio de baixa qualidade - parâmetros mais conservadores
                whisper_params.update({
                    "temperature": 0.0,  # Mais determinístico
                    "compression_ratio_threshold": 2.2,
                    "logprob_threshold": -0.8
                })

            result = self.model.transcribe(audio_path, **whisper_params)

            # Calcular confidence baseado nos segments
            confidence = 0.9  # Default
            if "segments" in result and result["segments"]:
                # Usar média das probabilidades dos segments se disponível
                segment_probs = []
                for segment in result["segments"]:
                    if "avg_logprob" in segment:
                        # Converter log probability para probability
                        prob = min(1.0, max(0.0, segment["avg_logprob"] + 1.0))
                        segment_probs.append(prob)

                if segment_probs:
                    confidence = sum(segment_probs) / len(segment_probs)

            # Detectar possíveis problemas na transcrição
            text = result["text"].strip()
            detected_language = result.get("language", language)

            # Validações de qualidade
            quality_issues = []
            if len(text) == 0:
                quality_issues.append("Nenhum texto detectado")
                confidence = 0.0
            elif len(text) < 5 and validation.get("duration", 0) > 2:
                quality_issues.append("Texto muito curto para duração do áudio")
                confidence *= 0.5

            if quality_issues:
                logger.warning(f"Problemas de qualidade na transcrição: {quality_issues}")

            logger.info(
                f"Transcrição concluída: {len(text)} caracteres, "
                f"confidence: {confidence:.2f}, idioma: {detected_language}"
            )

            return ASRResult(
                text=text,
                confidence=confidence,
                language=detected_language,
                duration=validation.get("duration", 0)
            )

        except Exception as e:
            logger.error(f"Erro na transcrição Whisper: {e}")
            raise RuntimeError(f"Falha na transcrição: {str(e)}")

    async def batch_process(self, audio_batch: List[tuple]) -> List[ASRResult]:
        """Processar múltiplos áudios em paralelo"""
        if not self.is_ready():
            raise RuntimeError("Pipeline ASR não inicializado")

        # Garantir que modelo está carregado (lazy loading)
        await self._ensure_model_loaded()

        if len(audio_batch) > self.max_concurrent_jobs:
            raise ValueError(f"Batch muito grande: {len(audio_batch)} > {self.max_concurrent_jobs}")

        tasks = []
        for audio_data, language in audio_batch:
            task = asyncio.create_task(self.process(audio_data, language))
            tasks.append(task)

        try:
            # Aguardar todos os processamentos
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Converter exceções em resultados de erro
            final_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Erro no batch item {i}: {result}")
                    # Criar resultado de erro
                    final_results.append(ASRResult(
                        text="",
                        confidence=0.0,
                        language="unknown",
                        duration=0
                    ))
                else:
                    final_results.append(result)

            return final_results

        except Exception as e:
            logger.error(f"Erro no processamento em lote: {e}")
            raise

    async def close(self):
        """Limpar recursos"""
        self.model = None
        self._ready = False