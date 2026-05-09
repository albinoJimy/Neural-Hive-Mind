"""Adapter para NLU Service gRPC → formato local NLUResult.

Implementa T11: converte resultado do NLU Service para o formato
esperado pelo gateway-intencoes, mantendo compatibilidade.
"""

import logging
from typing import Any

from grpc_clients.nlu_client import NLUServiceClient
from grpc_clients.pii_client import PIIServiceClient
from neural_hive_domain import UnifiedDomain

from models.intent_envelope import Entity, NLUResult

logger = logging.getLogger(__name__)


class NLUServiceAdapter:
    """
    Adapter para NLU Service.

    Converte chamadas ao NLU Service gRPC para o formato NLUResult
    esperado pelo gateway-intencoes.
    """

    def __init__(
        self,
        nlu_client: NLUServiceClient | None = None,
        pii_client: PIIServiceClient | None = None,
    ):
        """
        Inicializa adapter.

        Args:
            nlu_client: Cliente gRPC do NLU Service
            pii_client: Cliente gRPC do PII Service (para masking)
        """
        self._nlu_client = nlu_client
        self._pii_client = pii_client
        self._fallback_enabled = True  # INV-12: Graceful degradation

        logger.info("NLUServiceAdapter initialized")

    async def process(
        self,
        text: str,
        language: str = "pt",
        context: dict[str, Any] | None = None,
    ) -> NLUResult:
        """
        Processa texto via NLU Service e retorna NLUResult compatível.

        Args:
            text: Texto para processar
            language: Idioma do texto
            context: Contexto adicional

        Returns:
            NLUResult no formato esperado pelo gateway-intencoes
        """
        try:
            # Chamar NLU Service
            nlu_response = await self._nlu_client.parse(
                text=text,
                language=language,
                context=context,
                enable_cache=True,
            )

            # Converter domain string para UnifiedDomain
            domain = self._convert_domain(nlu_response.domain)

            # Converter entidades
            entities = [
                Entity(
                    type=entity.type,
                    value=entity.value,
                    confidence=entity.confidence,
                    start=entity.start if entity.start > 0 else None,
                    end=entity.end if entity.end > 0 else None,
                )
                for entity in nlu_response.entities
            ]

            # Converter keywords
            keywords = list(nlu_response.keywords)

            # Determinar confidence_status
            if nlu_response.confidence >= 0.75:
                confidence_status = "high"
            elif nlu_response.confidence >= 0.5:
                confidence_status = "medium"
            else:
                confidence_status = "low"

            # Aplicar PII masking se PII client disponível
            processed_text = nlu_response.processed_text
            if self._pii_client:
                try:
                    processed_text = await self._pii_client.mask(
                        text=nlu_response.processed_text,
                        strategy="MASK_FULL",
                        language=language,
                    )
                except Exception as e:
                    logger.warning(f"PII masking failed, using original text: {e}")
                    processed_text = nlu_response.processed_text

            # Criar NLUResult compatível
            return NLUResult(
                processed_text=processed_text,
                domain=domain,
                classification=nlu_response.domain,  # Usar domain como classification
                confidence=nlu_response.confidence,
                entities=entities,
                keywords=keywords,
                requires_manual_validation=nlu_response.confidence < 0.5,
                confidence_status=confidence_status,
                adaptive_threshold=None,  # NLU Service não retorna adaptive threshold
            )

        except Exception as e:
            logger.error(f"NLU Service call failed: {e}")
            if self._fallback_enabled:
                logger.warning("Falling back to keyword-only classification")
                return self._fallback_classify(text, language)
            raise

    def _convert_domain(self, domain_str: str) -> UnifiedDomain:
        """Converte string do NLU Service para UnifiedDomain."""
        try:
            # Mapeamento NLU Service → UnifiedDomain
            domain_mapping = {
                "BUSINESS": UnifiedDomain.BUSINESS,
                "TECHNICAL": UnifiedDomain.TECHNICAL,
                "INFRASTRUCTURE": UnifiedDomain.INFRASTRUCTURE,
                "SECURITY": UnifiedDomain.SECURITY,
                "DOMAIN_UNKNOWN": UnifiedDomain.UNKNOWN,
            }
            return domain_mapping.get(domain_str.upper(), UnifiedDomain.UNKNOWN)
        except (KeyError, ValueError):
            return UnifiedDomain.UNKNOWN

    def _fallback_classify(self, text: str, language: str) -> NLUResult:
        """Classificação por keywords quando NLU Service está down (INV-12)."""
        text_lower = text.lower()

        # Classificar por keywords simples
        if any(kw in text_lower for kw in ["consultar", "buscar", "dashboard", "relatório"]):
            domain = UnifiedDomain.BUSINESS
        elif any(kw in text_lower for kw in ["gerar", "criar", "código", "app", "sistema"]):
            domain = UnifiedDomain.TECHNICAL
        elif any(kw in text_lower for kw in ["migrar", "legado", "migration"]):
            domain = UnifiedDomain.INFRASTRUCTURE
        else:
            domain = UnifiedDomain.UNKNOWN

        return NLUResult(
            processed_text=text,
            domain=domain,
            classification=domain.value,
            confidence=0.4,
            entities=[],
            keywords=[],
            requires_manual_validation=True,
            confidence_status="low",
            adaptive_threshold=0.5,
        )
