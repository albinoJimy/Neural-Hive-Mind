"""
ML Predictor Interface.

Defines the interface for ML predictor integration in approval decisions.

R-A4: ML predictor interface for approval decision enhancement.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class MLPredictorInterface(ABC):
    """
    Interface for ML predictor in approval decisions.

    R-A4: Defines the contract for ML prediction integration.
    Implementations can use different ML models or services.
    """

    @abstractmethod
    def is_enabled(self) -> bool:
        """Check if ML predictor is enabled and available."""

    @abstractmethod
    async def predict_from_text(
        self,
        intent_text: str,
        specialist_confidence: float = 0.5,
    ) -> Optional[dict[str, Any]]:
        """
        Get prediction from intent text.

        Args:
            intent_text: Original intent text from user
            specialist_confidence: Average confidence from specialist opinions

        Returns:
            Dictionary with:
                - decision: "approve" or "reject"
                - confidence: float (0-1)
                - model_version: str (optional)
            Or None if prediction unavailable
        """

    @abstractmethod
    async def get_auto_decision(
        self,
        intent_text: str,
        risk_band: str,
        specialist_confidence: float = 0.5,
    ) -> Optional[dict[str, Any]]:
        """
        Get automatic decision for approval request.

        Returns an automatic decision only if:
        - Risk is within configured limits
        - Confidence is above threshold

        Args:
            intent_text: Original intent text
            risk_band: Risk band classification
            specialist_confidence: Average specialist confidence

        Returns:
            Dictionary with:
                - auto_decision: "approve" or "reject"
                - confidence: float
                - reason: str explaining the decision
            Or None if automatic decision not appropriate
        """


class MLPredictor(MLPredictorInterface):
    """
    Default implementation of ML predictor interface.

    This is a stub implementation that can be replaced with a real ML model.
    In production, this would connect to the approval ML model trained on
    historical approval decisions.
    """

    def __init__(
        self,
        enabled: bool = False,
        model_version: str = "stub",
        confidence_threshold: float = 0.8,
    ):
        """
        Initialize ML predictor.

        Args:
            enabled: Whether ML predictions are enabled
            model_version: Model version identifier
            confidence_threshold: Minimum confidence for automatic decisions
        """
        self.enabled = enabled
        self.model_version = model_version
        self.confidence_threshold = confidence_threshold

    def is_enabled(self) -> bool:
        """Check if ML predictor is enabled."""
        return self.enabled

    async def predict_from_text(
        self,
        intent_text: str,
        specialist_confidence: float = 0.5,
    ) -> Optional[dict[str, Any]]:
        """
        Get prediction from intent text.

        This stub implementation returns None.
        Real implementation would:
        1. Extract NLP features from intent_text
        2. Combine with specialist_confidence
        3. Run through trained model
        4. Return prediction with confidence

        Args:
            intent_text: Original intent text from user
            specialist_confidence: Average confidence from specialist opinions

        Returns:
            Prediction dictionary or None
        """
        if not self.enabled:
            return None

        # Stub: In production, call actual ML model
        # return {
        #     "decision": "approve",
        #     "confidence": 0.92,
        #     "model_version": self.model_version,
        # }

        return None

    async def get_auto_decision(
        self,
        intent_text: str,
        risk_band: str,
        specialist_confidence: float = 0.5,
    ) -> Optional[dict[str, Any]]:
        """
        Get automatic decision for approval request.

        This stub implementation returns None.
        Real implementation would only return automatic decisions
        when confidence is above threshold and risk is acceptable.

        Args:
            intent_text: Original intent text
            risk_band: Risk band classification
            specialist_confidence: Average specialist confidence

        Returns:
            Automatic decision dictionary or None
        """
        if not self.enabled:
            return None

        # For CRITICAL risk band, never auto-decide
        if risk_band == "critical":
            return None

        # Get prediction
        prediction = await self.predict_from_text(intent_text, specialist_confidence)
        if not prediction:
            return None

        confidence = prediction.get("confidence", 0.0)

        # Only auto-decide if confidence is high enough
        if confidence < self.confidence_threshold:
            return None

        return {
            "auto_decision": prediction["decision"],
            "confidence": confidence,
            "reason": f"ML prediction with {confidence:.2f} confidence",
        }
