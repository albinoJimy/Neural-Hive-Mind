"""Serviço de resiliência com Circuit Breaker para NLU/PII services.

Implementa T15: Circuit Breaker para chamadas NLU/PII services com fallback local.

INV-12: Graceful Degradation - Se NLU/PII services down, usar implementação local.
"""

import logging
from typing import Any

from neural_hive_resilience import MonitoredCircuitBreaker
from pydantic import BaseModel

from src.config.settings import get_settings
from src.models.classification import NLUResult

logger = logging.getLogger(__name__)

settings = get_settings()


class CircuitBreakerConfig(BaseModel):
    """Configuração do Circuit Breaker."""

    failure_threshold: int = 5  # Falhas consecutivas para abrir
    recovery_timeout: int = 30  # Segundos para tentar recuperar


class ResilienceNLUService:
    """
    Wrapper para NLU Service com Circuit Breaker e fallback local.

    Implementa INV-12: Graceful degradation com implementação local.
    """

    def __init__(self, nlu_client=None, config: CircuitBreakerConfig | None = None):
        """
        Inicializa o serviço resiliente.

        Args:
            nlu_client: Cliente NLU Service gRPC
            config: Configuração do Circuit Breaker
        """
        self._nlu_client = nlu_client
        self._config = config or CircuitBreakerConfig()

        # Criar Circuit Breaker
        self._circuit_breaker = MonitoredCircuitBreaker(
            service_name="unified-gateway",
            circuit_name="nlu_service",
            failure_threshold=self._config.failure_threshold,
            recovery_timeout=self._config.recovery_timeout,
        )

        logger.info(
            "resilience_nlu_initialized",
            failure_threshold=self._config.failure_threshold,
            recovery_timeout=self._config.recovery_timeout,
        )

    async def parse(
        self,
        text: str,
        language: str = "pt",
        context: dict[str, str] | None = None,
        enable_cache: bool = True,
    ) -> NLUResult:
        """
        Processa texto via NLU Service com Circuit Breaker e fallback.

        Args:
            text: Texto para processar
            language: Idioma do texto
            context: Contexto adicional
            enable_cache: Habilitar cache

        Returns:
            NLUResult do NLU Service ou resultado do fallback local
        """

        async def _call_nlu():
            if self._nlu_client is None:
                raise RuntimeError("NLU client not configured")
            return await self._nlu_client.parse(text, language, context, enable_cache)

        try:
            # Tentar via Circuit Breaker
            return await self._circuit_breaker.call_async(_call_nlu)

        except Exception as e:
            logger.warning(
                "nlu_service_failed",
                error=str(e),
                text_length=len(text),
                falling_back=True,
            )
            # Fallback para classificação local (INV-12)
            return self._fallback_parse(text, language, context)

    def _fallback_parse(
        self,
        text: str,
        language: str,
        context: dict[str, str] | None,
    ) -> NLUResult:
        """
        Classificação local quando NLU Service está indisponível (INV-12).

        Implementa classificação por keywords simples.
        """
        text_lower = text.lower()

        # Classificar domínio por keywords
        domain = "DOMAIN_UNKNOWN"
        confidence = 0.4
        keywords = []

        # Keywords BUSINESS
        business_keywords = [
            "consultar",
            "buscar",
            "analisar",
            "listar",
            "mostrar",
            "dashboard",
            "relatório",
            "dados",
            "métrica",
            "kpi",
        ]
        if any(kw in text_lower for kw in business_keywords):
            domain = "BUSINESS"
            confidence = 0.7
            keywords = [kw for kw in business_keywords if kw in text_lower]

        # Keywords TECHNICAL
        technical_keywords = [
            "gerar",
            "criar",
            "build",
            "desenvolver",
            "código",
            "implementar",
            "app",
            "sistema",
            "api",
            "funcão",
        ]
        if any(kw in text_lower for kw in technical_keywords):
            domain = "TECHNICAL"
            confidence = 0.7
            keywords = [kw for kw in technical_keywords if kw in text_lower]

        # Keywords INFRASTRUCTURE
        infra_keywords = [
            "migrar",
            "migration",
            "legado",
            "legacy",
            "atualizar",
            "modernizar",
            "deploy",
            "kubernetes",
            "docker",
        ]
        if any(kw in text_lower for kw in infra_keywords):
            domain = "INFRASTRUCTURE"
            confidence = 0.7
            keywords = [kw for kw in infra_keywords if kw in text_lower]

        # Keywords SECURITY
        security_keywords = [
            "segurança",
            "autenticação",
            "permissão",
            "acesso",
            "criptografia",
            "vulnerabilidade",
            "firewall",
        ]
        if any(kw in text_lower for kw in security_keywords):
            domain = "SECURITY"
            confidence = 0.7
            keywords = [kw for kw in security_keywords if kw in text_lower]

        logger.info(
            "fallback_classification",
            domain=domain,
            confidence=confidence,
            keywords_count=len(keywords),
        )

        return NLUResult(
            text=text,
            domain=domain,
            confidence=confidence,
            entities={},
            keywords=keywords[:5],  # Máx 5 keywords
        )

    async def classify_domain(
        self,
        text: str,
        language: str = "pt",
        context: dict[str, str] | None = None,
    ) -> tuple[str, float, str]:
        """
        Classifica domínio com Circuit Breaker e fallback.

        Returns:
            Tuple (domain, confidence, reasoning)
        """
        nlu_result = await self.parse(text, language, context)

        reasoning = f"Classificação via {'fallback local' if nlu_result.confidence < 0.6 else 'NLU Service'}"

        return nlu_result.domain, nlu_result.confidence, reasoning


class ResiliencePIIService:
    """
    Wrapper para PII Service com Circuit Breaker e fallback local.

    Implementa INV-12: Graceful degradation com implementação local.
    """

    def __init__(self, pii_client=None, config: CircuitBreakerConfig | None = None):
        """
        Inicializa o serviço resiliente.

        Args:
            pii_client: Cliente PII Service gRPC
            config: Configuração do Circuit Breaker
        """
        self._pii_client = pii_client
        self._config = config or CircuitBreakerConfig()

        # Criar Circuit Breaker
        self._circuit_breaker = MonitoredCircuitBreaker(
            service_name="unified-gateway",
            circuit_name="pii_service",
            failure_threshold=self._config.failure_threshold,
            recovery_timeout=self._config.recovery_timeout,
        )

        logger.info(
            "resilience_pii_initialized",
            failure_threshold=self._config.failure_threshold,
            recovery_timeout=self._config.recovery_timeout,
        )

    async def detect_pii(
        self,
        text: str,
        language: str = "pt",
    ) -> list[dict[str, Any]]:
        """
        Detecta PII com Circuit Breaker e fallback local.

        Args:
            text: Texto para analisar
            language: Idioma do texto

        Returns:
            Lista de PII encontrados (dict com type, value, start, end)
        """

        async def _call_pii():
            if self._pii_client is None:
                raise RuntimeError("PII client not configured")
            return await self._pii_client.detect(text=text, language=language)

        try:
            # Tentar via Circuit Breaker
            return await self._circuit_breaker.call_async(_call_pii)

        except Exception as e:
            logger.warning(
                "pii_service_failed",
                error=str(e),
                text_length=len(text),
                falling_back=True,
            )
            # Fallback para detecção local (INV-12)
            return self._fallback_detect_pii(text)

    def _fallback_detect_pii(self, text: str) -> list[dict[str, Any]]:
        """
        Detecção PII local quando PII Service está indisponível (INV-12).

        Implementa detecção básica por regex para tipos comuns.
        """
        import re

        pii_found = []

        # PII types e patterns básicos
        pii_patterns = {
            "EMAIL": (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", 0.9),
            "PHONE": (r"\b\d{2}[- ]?\d{4,5}[- ]?\d{4}\b", 0.8),
            "CPF": (r"\b\d{3}[.\s]?\d{3}[.\s]?\d{3}[-]?\d{2}\b", 0.95),
            "CNPJ": (r"\b\d{2}[.\s]?\d{3}[.\s]?\d{3}[\/]?\d{4}[-]?\d{2}\b", 0.95),
        }

        for pii_type, (pattern, confidence) in pii_patterns.items():
            for match in re.finditer(pattern, text):
                pii_found.append(
                    {
                        "type": pii_type,
                        "value": match.group(),
                        "confidence": confidence,
                        "start": match.start(),
                        "end": match.end(),
                    }
                )

        logger.info(
            "fallback_pii_detection",
            pii_count=len(pii_found),
            pii_types=[p["type"] for p in pii_found],
        )

        return pii_found

    async def mask_pii(
        self,
        text: str,
        strategy: str = "MASK_FULL",
        language: str = "pt",
    ) -> str:
        """
        Mascarea PII com Circuit Breaker e fallback local.

        Args:
            text: Texto para mascarar
            strategy: Estratégia de mascaramento
            language: Idioma do texto

        Returns:
            Texto mascarado
        """

        async def _call_pii():
            if self._pii_client is None:
                raise RuntimeError("PII client not configured")
            return await self._pii_client.mask(text=text, strategy=strategy, language=language)

        try:
            # Tentar via Circuit Breaker
            return await self._circuit_breaker.call_async(_call_pii)

        except Exception as e:
            logger.warning(
                "pii_mask_failed",
                error=str(e),
                falling_back=True,
            )
            # Fallback para mascaramento local (INV-12)
            return self._fallback_mask_pii(text, strategy)

    def _fallback_mask_pii(self, text: str, strategy: str) -> str:
        """
        Mascaramento PII local quando PII Service está indisponível (INV-12).
        """
        import re

        masked_text = text

        # PII patterns
        pii_patterns = {
            "EMAIL": (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL]"),
            "PHONE": (r"\b\d{2}[- ]?\d{4,5}[- ]?\d{4}\b", "[PHONE]"),
            "CPF": (r"\b\d{3}[.\s]?\d{3}[.\s]?\d{3}[-]?\d{2}\b", "[CPF]"),
            "CNPJ": (r"\b\d{2}[.\s]?\d{3}[.\s]?\d{3}[\/]?\d{4}[-]?\d{2}\b", "[CNPJ]"),
        }

        for pattern, replacement in pii_patterns.values():
            masked_text = re.sub(pattern, replacement, masked_text)

        logger.info(
            "fallback_pii_masking",
            strategy=strategy,
            original_length=len(text),
            masked_length=len(masked_text),
        )

        return masked_text


# Singleton global
_resilience_nlu: ResilienceNLUService | None = None
_resilience_pii: ResiliencePIIService | None = None


def get_resilience_nlu() -> ResilienceNLUService:
    """Obtém ou cria o singleton do NLU Service resiliente."""
    global _resilience_nlu
    if _resilience_nlu is None:
        _resilience_nlu = ResilienceNLUService()
    return _resilience_nlu


def get_resilience_pii() -> ResiliencePIIService:
    """Obtém ou cria o singleton do PII Service resiliente."""
    global _resilience_pii
    if _resilience_pii is None:
        _resilience_pii = ResiliencePIIService()
    return _resilience_pii
