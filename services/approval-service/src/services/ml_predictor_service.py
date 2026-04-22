"""
ML Predictor Service - Serviço de predição ML para aprovações

Este serviço fornece predições automáticas de aprovação/rejeição
baseadas no modelo ML treinado com features NLP.
"""

import asyncio
from pathlib import Path
from typing import Any, Optional

import structlog

from src.config.settings import Settings

logger = structlog.get_logger()


class MLPredictorService:
    """
    Serviço de predição ML para aprovação de planos cognitivos.

    Usa o modelo RandomForest v6 treinado com 50 amostras balanceadas
    e 30 features NLP.
    """

    # Risco máximo para decisão automática (em ordem crescente)
    RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}

    def __init__(self, settings: Settings):
        """
        Inicializa o serviço de predição ML.

        Args:
            settings: Configurações do approval service
        """
        self.settings = settings
        self.enabled = settings.enable_ml_prediction
        self.predictor = None
        self.model_info = None

        if self.enabled:
            self._load_predictor()

    def _load_predictor(self) -> None:
        """Carrega o predictor do modelo ML."""
        try:
            # Importar o predictor (pode falhar se biblioteca não disponível)
            from ml_pipelines.inference.approval_predictor import ApprovalPredictor

            model_path = Path(self.settings.ml_model_path)
            self.predictor = ApprovalPredictor(model_path=model_path)
            self.model_info = self.predictor.get_model_info()

            logger.info(
                "ml_predictor_loaded",
                model_version=self.model_info.get("version"),
                model_path=self.settings.ml_model_path,
                auto_approve_threshold=self.settings.ml_auto_approve_threshold,
                auto_reject_threshold=self.settings.ml_auto_reject_threshold,
            )

        except ImportError as e:
            logger.warning(
                "ml_predictor_library_not_available", error=str(e), note="ML prediction disabled"
            )
            self.enabled = False
            self.predictor = None

        except FileNotFoundError as e:
            logger.warning(
                "ml_predictor_model_not_found",
                model_path=self.settings.ml_model_path,
                error=str(e),
                note="ML prediction disabled",
            )
            self.enabled = False
            self.predictor = None

        except Exception as e:
            logger.error("ml_predictor_load_failed", error=str(e), note="ML prediction disabled")
            self.enabled = False
            self.predictor = None

    def is_enabled(self) -> bool:
        """Verifica se a predição ML está habilitada e disponível."""
        return self.enabled and self.predictor is not None

    def can_auto_decide(self, risk_band: str) -> bool:
        """
        Verifica se uma decisão automática é permitida para o nível de risco.

        Args:
            risk_band: Banda de risco (low, medium, high, critical)

        Returns:
            True se decisão automática é permitida
        """
        if not self.is_enabled():
            return False

        max_risk = self.settings.ml_max_risk_for_auto
        current_risk_level = self.RISK_ORDER.get(risk_band, 99)
        max_risk_level = self.RISK_ORDER.get(max_risk, 0)

        return current_risk_level <= max_risk_level

    async def predict_from_text(
        self, intent_text: str, specialist_confidence: float = 0.5
    ) -> Optional[dict[str, Any]]:
        """
        Faz predição a partir do texto da intenção.

        Args:
            intent_text: Texto da intenção
            specialist_confidence: Confiança do especialista (0.0-1.0)

        Returns:
            Dicionário com prediction ou None se ML não disponível
        """
        if not self.is_enabled():
            return None

        if not intent_text:
            logger.debug("ml_predictor_skip_empty_text")
            return None

        try:
            # Executar predição em thread separada para não bloquear
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self.predictor.predict_from_text, intent_text, specialist_confidence
            )

            logger.debug(
                "ml_predictor_prediction_made",
                decision=result["decision"],
                confidence=result["confidence"],
                model_version=result.get("model_version"),
            )

            return result

        except Exception as e:
            logger.error(
                "ml_predictor_prediction_failed",
                error=str(e),
                intent_text_length=len(intent_text) if intent_text else 0,
            )
            return None

    async def get_auto_decision(
        self, intent_text: str, risk_band: str, specialist_confidence: float = 0.5
    ) -> Optional[dict[str, Any]]:
        """
        Tenta obter uma decisão automática baseada em predição ML.

        Args:
            intent_text: Texto da intenção
            risk_band: Banda de risco do plano
            specialist_confidence: Confiança do especialista (0.0-1.0)

        Returns:
            Dicionário com auto_decision ou None se não houver decisão automática
        """
        # Verifica se decisão automática é permitida para este nível de risco
        if not self.can_auto_decide(risk_band):
            logger.debug(
                "ml_predictor_auto_decision_not_allowed",
                risk_band=risk_band,
                max_risk=self.settings.ml_max_risk_for_auto,
            )
            return None

        # Obtém predição
        prediction = await self.predict_from_text(intent_text, specialist_confidence)
        if not prediction:
            return None

        decision = prediction["decision"]
        confidence = prediction["confidence"]

        # Verifica thresholds
        approve_threshold = self.settings.ml_auto_approve_threshold
        reject_threshold = self.settings.ml_auto_reject_threshold

        if decision == "approve" and confidence >= approve_threshold:
            logger.info(
                "ml_predictor_auto_approve",
                decision=decision,
                confidence=confidence,
                threshold=approve_threshold,
            )
            return {
                "auto_decision": "approve",
                "confidence": confidence,
                "reason": f"ML prediction with {confidence:.1%} confidence",
            }

        elif decision == "reject" and confidence >= reject_threshold:
            logger.info(
                "ml_predictor_auto_reject",
                decision=decision,
                confidence=confidence,
                threshold=reject_threshold,
            )
            return {
                "auto_decision": "reject",
                "confidence": confidence,
                "reason": f"ML prediction with {confidence:.1%} confidence",
            }

        else:
            logger.debug(
                "ml_predictor_below_threshold",
                decision=decision,
                confidence=confidence,
                approve_threshold=approve_threshold,
                reject_threshold=reject_threshold,
            )
            return None

    def get_model_info(self) -> Optional[dict[str, Any]]:
        """Retorna informações sobre o modelo carregado."""
        if not self.is_enabled():
            return None
        return self.model_info


# Singleton para uso na aplicação
_ml_predictor_service: Optional[MLPredictorService] = None


def get_ml_predictor_service(settings: Settings) -> MLPredictorService:
    """Retorna instância singleton do serviço de predição ML."""
    global _ml_predictor_service
    if _ml_predictor_service is None:
        _ml_predictor_service = MLPredictorService(settings)
    return _ml_predictor_service
