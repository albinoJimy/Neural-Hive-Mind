"""Pipeline NLU refatorado usando componentes modulares.

Autor: Neural Hive Mind
Criado: 2026-04-20 (REFACTOR-A-001)

Este módulo contém o NLUPipeline refatorado que utiliza os componentes extraídos:
- ClassifierEngine para classificação de intenções
- CacheManager para cache Redis
- TextProcessor para processamento de texto
- LanguageDetector para detecção de idioma
- ThresholdCalculator para threshold adaptativo
"""

import asyncio
import logging
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import spacy
from cache.redis_client import get_redis_client
from config.settings import get_settings
from models.intent_envelope import NLUResult

# Importar componentes NLU refatorados
from pipelines.nlu import (
    CacheManager,
    ClassifierEngine,
    LanguageDetector,
    TextProcessor,
    ThresholdCalculator,
)

# Importar métricas
try:
    from observability.metrics import (
        gateway_nlu_processing_duration,
        gateway_slo_violations_total,
    )

    CACHE_METRICS_AVAILABLE = True
except ImportError:
    CACHE_METRICS_AVAILABLE = False

logger = logging.getLogger(__name__)

# Importar tracer
try:
    from neural_hive_observability import get_tracer

    tracer = get_tracer()
except ImportError:
    tracer = None


class NLUPipelineRefactored:
    """Pipeline NLU refatorado com componentes modulares."""

    def __init__(
        self,
        language_model: str | None = None,
        confidence_threshold: float | None = None,
    ):
        """Inicializa pipeline NLU refatorado.

        Args:
            language_model: Modelo spaCy para usar
            confidence_threshold: Threshold base de confiança
        """
        self.settings = get_settings()
        self.language_model = language_model or self.settings.nlu_language_model
        self.model_cache_dir = Path(self.settings.nlu_model_cache_dir)
        self.confidence_threshold = confidence_threshold or self.settings.nlu_confidence_threshold

        # Modelos spaCy
        self.nlp = None
        self.nlp_models: dict[str, Any] = {}
        self.supported_models = {
            "pt": "pt_core_news_sm",
            "en": "en_core_web_sm",
            "es": "es_core_news_sm",
        }

        # Componentes NLU
        self.classifier: ClassifierEngine | None = None
        self.cache_manager: CacheManager | None = None
        self.text_processor: TextProcessor | None = None
        self.language_detector: LanguageDetector | None = None
        self.threshold_calculator: ThresholdCalculator | None = None

        self._ready = False

    async def initialize(self) -> None:
        """Inicializa pipeline e componentes."""
        try:
            logger.info("Inicializando NLUPipeline Refatorado...")

            # Inicializar componentes
            self.classifier = ClassifierEngine(
                rules_config_path=self.settings.nlu_rules_config_path,
                enable_custom_rules=True,
            )
            await self.classifier.initialize()

            redis_client = None
            if self.settings.nlu_cache_enabled:
                redis_client = await get_redis_client()

            self.cache_manager = CacheManager(
                redis_client=redis_client,
                enabled=self.settings.nlu_cache_enabled,
                default_ttl=3600,
                key_prefix="nlu",
            )

            self.text_processor = TextProcessor(
                enable_pii_masking=self.settings.nlu_pii_masking_enabled,
                pii_mask_strategy="redact",
                enable_entity_extraction=True,
            )

            self.language_detector = LanguageDetector(
                default_language="pt",
                supported_languages=["pt", "en", "es"],
                confidence_threshold=0.6,
                enabled=self.settings.nlu_language_detection_enabled,
            )

            self.threshold_calculator = ThresholdCalculator(
                base_threshold=self.confidence_threshold,
                min_threshold=0.4,
                max_threshold=0.8,
                adjustment_factor=0.05,
                history_size=100,
            )

            # Carregar modelo spaCy principal
            logger.info(f"Carregando modelo spaCy: {self.language_model}")
            self.nlp = self._load_model_from_cache(self.language_model)
            self.nlp_models["default"] = self.nlp

            # Aquecer cache
            if self.settings.nlu_cache_warming_enabled:
                await self._warm_up_cache()

            self._ready = True
            logger.info("NLUPipeline Refatorado inicializado com sucesso")

        except Exception as e:
            logger.exception(f"Erro inicializando NLUPipeline: {e}")
            raise

    async def process(
        self, text: str, language: str = "pt-AO", context: dict[str, Any] | None = None
    ) -> NLUResult:
        """Processa texto e retorna resultado NLU.

        Args:
            text: Texto para processar
            language: Idioma do texto
            context: Contexto adicional

        Returns:
            Resultado NLU processado
        """
        if not self.is_ready():
            raise RuntimeError("Pipeline NLU não inicializado")

        import time

        nlu_start_time = time.time()

        span_context = tracer.start_as_current_span("nlu.process") if tracer else nullcontext()
        with span_context as span:
            if span:
                span.set_attribute("neural.hive.component", "gateway")
                span.set_attribute("neural.hive.layer", "experiencia")
                span.set_attribute("neural.hive.nlu.language", language)
                span.set_attribute("neural.hive.nlu.text_length", len(text))

            # Validar qualidade do texto
            is_valid, reason = self.classifier.validate_text_quality(text)
            if not is_valid:
                if span:
                    span.set_attribute("neural.hive.nlu.validation_failed", True)
                raise ValueError(f"Texto inválido: {reason}")

            # Verificar cache
            cache_key = None
            if self.cache_manager.is_enabled():
                detected_lang = language if language else "pt"
                cached_result = await self.cache_manager.get(text, detected_lang)
                if cached_result:
                    if span:
                        span.set_attribute("neural.hive.nlu.cache_hit", True)
                    logger.debug("Cache hit para texto processado")
                    return cached_result
                if span:
                    span.set_attribute("neural.hive.nlu.cache_hit", False)

            # Detectar idioma
            detected_language, lang_confidence = self.language_detector.detect(text)
            if span:
                span.set_attribute("neural.hive.nlu.detected_language", detected_language)
                span.set_attribute("neural.hive.nlu.lang_confidence", lang_confidence)

            # Obter modelo spaCy
            nlp_model = self._get_model_for_language(detected_language)

            # Normalizar texto
            normalized_text = self.text_processor.normalize(text)

            # Processar com spaCy
            doc = nlp_model(normalized_text)

            # Mascarar PII
            masked_text, pii_entities = self.text_processor.mask_pii(text)

            # Extrair entidades
            entities = self.text_processor.extract_entities(doc, masked=bool(pii_entities))
            entities.extend(pii_entities)

            if span:
                span.set_attribute("neural.hive.nlu.entities_count", len(entities))

            # Classificar intenção
            domain, confidence, subcategory = self.classifier.classify(text, entities, context)

            if span:
                span.set_attribute("neural.hive.nlu.domain", domain.value)
                span.set_attribute("neural.hive.nlu.confidence", confidence)

            # Extrair keywords
            keywords = self.text_processor.extract_keywords(text)

            # Calcular threshold adaptativo
            adaptive_threshold = await self.threshold_calculator.calculate_threshold()
            if span:
                span.set_attribute("neural.hive.nlu.adaptive_threshold", adaptive_threshold)

            # Determinar status de confiança
            if confidence >= 0.75:
                confidence_status = "high"
            elif confidence >= 0.5:
                confidence_status = "medium"
            else:
                confidence_status = "low"

            # Criar resultado
            result = NLUResult(
                processed_text=masked_text,
                domain=domain,
                classification=subcategory or domain.value,
                confidence=confidence,
                entities=entities,
                keywords=keywords,
                requires_manual_validation=confidence < adaptive_threshold,
                confidence_status=confidence_status,
                adaptive_threshold=adaptive_threshold,
            )

            # Salvar no cache
            if self.cache_manager.is_enabled():
                await self.cache_manager.set(text, result, detected_language)

            # Registrar métricas
            nlu_duration = time.time() - nlu_start_time
            if CACHE_METRICS_AVAILABLE:
                gateway_nlu_processing_duration.observe(nlu_duration)

                SLO_THRESHOLD_MS = 0.200
                if nlu_duration > SLO_THRESHOLD_MS:
                    gateway_slo_violations_total.labels(slo_threshold_ms="200").inc()
                    logger.warning(f"SLO violation: NLU levou {nlu_duration*1000:.0f}ms")

            # Atualizar threshold com feedback
            await self.threshold_calculator.update_from_result(
                result, accepted=result.confidence >= adaptive_threshold
            )

            logger.info(
                f"NLU: domain={domain.value}, confidence={confidence:.2f}, "
                f"status={confidence_status}, threshold={adaptive_threshold:.2f}"
            )

            return result

    def _load_model_from_cache(self, model_name: str):
        """Carrega modelo spaCy do cache ou instalação padrão."""
        model_path = self.model_cache_dir / model_name

        if model_path.exists():
            logger.info(f"Carregando modelo do cache: {model_path}")
            import sys

            cache_str = str(self.model_cache_dir)
            if cache_str not in sys.path:
                sys.path.insert(0, cache_str)
            try:
                return spacy.load(str(model_path))
            except Exception as e:
                logger.warning(f"Falha ao carregar do cache: {e}")

        logger.info(f"Carregando modelo padrão: {model_name}")
        return spacy.load(model_name)

    def _get_model_for_language(self, language: str) -> Any:
        """Retorna modelo spaCy para idioma."""
        # Mapear código de idioma para modelo
        lang_code = language.split("-")[0].lower() if "-" in language else language.lower()

        model_name = self.supported_models.get(lang_code)
        if not model_name:
            logger.warning(f"Modelo não encontrado para {language}, usando padrão")
            return self.nlp

        # Verificar se já está carregado
        if lang_code in self.nlp_models:
            return self.nlp_models[lang_code]

        # Carregar modelo
        try:
            model = self._load_model_from_cache(model_name)
            self.nlp_models[lang_code] = model
            return model
        except Exception as e:
            logger.warning(f"Erro carregando modelo {model_name}: {e}, usando padrão")
            return self.nlp

    async def _warm_up_cache(self) -> None:
        """Aquece cache com queries comuns."""
        common_queries = [
            ("Preciso de um relatório de vendas", "pt"),
            ("Quero analisar as métricas de marketing", "pt"),
            ("Como criar um dashboard de analytics", "pt"),
            ("Gostaria de ver o faturamento do mês", "pt"),
            ("Sales report for last quarter", "en"),
            ("Customer analytics dashboard", "en"),
        ]

        async def warmup_single(query: str, lang: str) -> None:
            try:
                result = await self.process(query, lang)
                logger.debug(f"Cache warmed: {query[:30]}... -> {result.domain.value}")
            except Exception as e:
                logger.warning(f"Cache warm-up error: {e}")

        tasks = [warmup_single(q, l) for q, l in common_queries]
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(f"Cache warming concluído para {len(common_queries)} queries")

    def is_ready(self) -> bool:
        """Verifica se pipeline está pronto."""
        return self._ready and self.nlp is not None

    async def health_check(self) -> dict[str, Any]:
        """Retorna status de saúde do pipeline."""
        return {
            "ready": self.is_ready(),
            "language_model": self.language_model,
            "components": {
                "classifier": self.classifier is not None,
                "cache_manager": self.cache_manager is not None,
                "text_processor": self.text_processor is not None,
                "language_detector": self.language_detector is not None,
                "threshold_calculator": self.threshold_calculator is not None,
            },
            "cache_stats": await self.cache_manager.get_stats() if self.cache_manager else {},
            "threshold_stats": (
                self.threshold_calculator.get_stats() if self.threshold_calculator else {}
            ),
        }

    async def clear_cache(self) -> dict[str, Any]:
        """Limpa cache NLU."""
        result = {"success": False}
        if self.cache_manager:
            result["success"] = await self.cache_manager.clear()
        return result

    def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas do pipeline."""
        return {
            "ready": self.is_ready(),
            "language_model": self.language_model,
            "models_loaded": list(self.nlp_models.keys()),
            "classifier_stats": self.classifier.get_stats() if self.classifier else {},
            "text_processor_stats": self.text_processor.get_stats() if self.text_processor else {},
            "language_detector_stats": (
                self.language_detector.get_stats() if self.language_detector else {}
            ),
        }
