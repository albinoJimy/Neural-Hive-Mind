"""Pipeline NLU usando NLU Service via gRPC (T11 refactor).

Este arquivo substitui a implementação local de NLU (1.303 LOC) por
chamadas ao NLU Service via gRPC, mantendo a mesma interface para
compatibilidade com o gateway-intencoes.
"""

import logging
from typing import Any

from config.settings import get_settings
from services.nlu_service_adapter import NLUServiceAdapter

from models.intent_envelope import NLUResult

logger = logging.getLogger(__name__)
settings = get_settings()


class NLUPipeline:
    """
    Pipeline NLU usando NLU Service via gRPC.

    Implementa T11: substitui implementação local (spaCy, regras locais)
    por chamadas ao NLU Service (:8020) via gRPC.

    Mantém a mesma interface `process()` para compatibilidade.
    """

    def __init__(
        self,
        language_model: str | None = None,
        confidence_threshold: float | None = None,
    ):
        """
        Inicializa pipeline NLU.

        Args:
            language_model: Ignorado (NLU Service gerencia modelos)
            confidence_threshold: Threshold de confiança
        """
        self.settings = get_settings()
        self.language_model = language_model or self.settings.nlu_language_model
        self.confidence_threshold = (
            confidence_threshold or self.settings.nlu_confidence_threshold
        )
        self._ready = False
        self._adapter: NLUServiceAdapter | None = None
        self.last_adaptive_threshold = self.confidence_threshold

        logger.info(
            f"NLUPipeline configurado para usar NLU Service via gRPC (T11 refactor). "
            f"Threshold: {self.confidence_threshold}"
        )

    async def initialize(self):
        """Inicializa conexão com NLU Service."""
        try:
            from grpc_clients.nlu_client import get_nlu_client
            from grpc_clients.pii_client import get_pii_client

            nlu_client = await get_nlu_client()
            pii_client = await get_pii_client()

            self._adapter = NLUServiceAdapter(
                nlu_client=nlu_client,
                pii_client=pii_client,
            )

            self._ready = True
            logger.info("NLUPipeline inicializado com NLU Service gRPC")

        except Exception as e:
            logger.error(f"Falha ao inicializar NLU Service: {e}")
            raise

    def is_ready(self) -> bool:
        """Verifica se pipeline está pronto."""
        return self._ready

    async def process(
        self, text: str, language: str = "pt-AO", context: dict[str, Any] | None = None
    ) -> NLUResult:
        """
        Processar texto via NLU Service.

        Mantém a mesma assinatura do método original para compatibilidade.

        Args:
            text: Texto para processar
            language: Idioma do texto (formato pt-AO mapeado para pt)
            context: Contexto adicional

        Returns:
            NLUResult com o resultado do processamento
        """
        if not self.is_ready():
            raise RuntimeError("Pipeline NLU não inicializado")

        # Normalizar idioma (pt-AO → pt, en-US → en)
        normalized_language = language.split("-")[0] if "-" in language else language

        # Processar via NLU Service
        result = await self._adapter.process(
            text=text,
            language=normalized_language,
            context=context or {},
        )

        # Aplicar threshold adaptativo se habilitado
        if self.settings.nlu_adaptive_threshold_enabled:
            self.last_adaptive_threshold = self._calculate_adaptive_threshold(
                text, context, result.confidence
            )
        else:
            self.last_adaptive_threshold = self.confidence_threshold

        return result

    def _calculate_adaptive_threshold(
        self,
        text: str,
        context: dict[str, Any] | None,
        base_confidence: float,
    ) -> float:
        """Calcula threshold adaptativo baseado em contexto."""
        # Implementação simplificada - pode ser expandida
        if len(text) < 20:
            # Textos curtos têm threshold mais baixo
            return max(0.3, self.confidence_threshold - 0.1)
        elif len(text) > 200:
            # Textos longos têm threshold mais alto
            return min(0.9, self.confidence_threshold + 0.1)
        return self.confidence_threshold

    async def close(self):
        """Fecha conexões."""
        self._ready = False
        logger.info("NLUPipeline fechado")

    async def _warmup_cache(self):
        """Warmup de cache - não aplicável para NLU Service (gerenciado internamente)."""
        pass

    async def load_classification_rules(self):
        """Carregar regras - não aplicável para NLU Service (gerenciado internamente)."""
        pass

    def explain_classification(self, text: str, result: NLUResult) -> dict[str, Any]:
        """Explica classificação - retorna dados do resultado."""
        return {
            "domain": result.domain.value,
            "confidence": result.confidence,
            "entities": [e.dict() for e in result.entities],
            "keywords": result.keywords,
            "processed_via": "NLU Service gRPC (T11 refactor)",
        }
