"""Adaptive curiosity scorer for signal prioritization"""
from typing import Dict, List
import numpy as np
import structlog

from ..models.raw_event import RawEvent
from ..models.scout_signal import ExplorationDomain

logger = structlog.get_logger()


class CuriosityScorer:
    """Calculates adaptive curiosity scores for detected signals"""

    def __init__(self):
        # Adaptive weights per domain
        self.weights: Dict[str, Dict[str, float]] = {
            domain.value: {
                'novelty': 0.4,
                'relevance': 0.3,
                'information_gain': 0.2,
                'uncertainty': 0.1
            }
            for domain in ExplorationDomain
        }

        # Historical feature vectors for novelty calculation
        self.historical_features: Dict[str, List[np.ndarray]] = {
            domain.value: [] for domain in ExplorationDomain
        }

        # Validation feedback tracking
        self.validation_stats: Dict[str, Dict[str, int]] = {
            domain.value: {'validated': 0, 'rejected': 0}
            for domain in ExplorationDomain
        }

    def calculate_score(
        self,
        event: RawEvent,
        domain: ExplorationDomain,
        context: Dict = None
    ) -> float:
        """
        Calculate adaptive curiosity score

        Args:
            event: Raw event
            domain: Exploration domain
            context: Additional context for scoring

        Returns:
            float: Curiosity score (0-1)
        """
        try:
            features = np.array(event.extract_features())
            weights = self.weights[domain.value]

            # Calculate components
            novelty = self.calculate_novelty(features, domain)
            relevance = self.calculate_relevance(event, domain, context)
            info_gain = self.calculate_information_gain(features, domain)
            uncertainty = self.calculate_uncertainty(features)

            # Weighted sum
            curiosity_score = (
                novelty * weights['novelty'] +
                relevance * weights['relevance'] +
                info_gain * weights['information_gain'] +
                uncertainty * weights['uncertainty']
            )

            # Ensure score is in [0, 1]
            curiosity_score = min(max(curiosity_score, 0.0), 1.0)

            logger.debug(
                "curiosity_score_calculated",
                domain=domain.value,
                novelty=novelty,
                relevance=relevance,
                information_gain=info_gain,
                uncertainty=uncertainty,
                final_score=curiosity_score
            )

            # Store features for future novelty calculations
            self.historical_features[domain.value].append(features)

            # Limit history size
            if len(self.historical_features[domain.value]) > 1000:
                self.historical_features[domain.value] = self.historical_features[domain.value][-1000:]

            return curiosity_score

        except Exception as e:
            logger.error(
                "curiosity_scoring_failed",
                domain=domain.value,
                error=str(e)
            )
            return 0.5  # Default moderate curiosity

    def calculate_novelty(self, features: np.ndarray, domain: ExplorationDomain) -> float:
        """
        Calculate novelty score based on distance from historical features

        Args:
            features: Feature vector
            domain: Exploration domain

        Returns:
            float: Novelty score (0-1)
        """
        historical = self.historical_features.get(domain.value, [])

        if not historical:
            return 0.8  # High novelty for first signal

        # Calculate minimum distance to historical features
        distances = []
        for hist_features in historical[-100:]:  # Use last 100 for efficiency
            try:
                distance = np.linalg.norm(features - hist_features)
                distances.append(distance)
            except:
                continue

        if not distances:
            return 0.8

        min_distance = min(distances)
        avg_distance = np.mean(distances)

        # Normalize novelty using sigmoid
        novelty = 1 / (1 + np.exp(-min_distance / (avg_distance + 1e-6)))

        return float(novelty)

    def calculate_relevance(
        self,
        event: RawEvent,
        domain: ExplorationDomain,
        context: Dict = None
    ) -> float:
        """
        Calculate relevance score based on domain and context

        Args:
            event: Raw event
            domain: Exploration domain
            context: Additional context

        Returns:
            float: Relevance score (0-1)
        """
        # Base relevance by domain
        domain_relevance = {
            ExplorationDomain.BUSINESS: 0.9,
            ExplorationDomain.SECURITY: 0.95,
            ExplorationDomain.TECHNICAL: 0.7,
            ExplorationDomain.BEHAVIOR: 0.8,
            ExplorationDomain.INFRASTRUCTURE: 0.75
        }

        base_score = domain_relevance.get(domain, 0.5)

        # Adjust based on event type
        event_type_boost = {
            'user_action': 0.1,
            'system_event': 0.05,
            'metric': 0.08,
            'trace': 0.03
        }

        boost = event_type_boost.get(event.event_type, 0.0)
        relevance = min(base_score + boost, 1.0)

        return relevance

    def calculate_information_gain(
        self,
        features: np.ndarray,
        domain: ExplorationDomain
    ) -> float:
        """
        Calculate potential information gain from this signal

        Args:
            features: Feature vector
            domain: Exploration domain

        Returns:
            float: Information gain score (0-1)
        """
        historical = self.historical_features.get(domain.value, [])

        if len(historical) < 2:
            return 0.7  # High potential gain with little data

        # Calculate variance in historical features
        try:
            historical_array = np.array(historical[-100:])
            feature_variance = np.var(historical_array, axis=0)
            avg_variance = np.mean(feature_variance)

            # Current feature variance
            current_variance = np.var(features)

            # Information gain is higher when current variance differs from average
            variance_diff = abs(current_variance - avg_variance)
            info_gain = 1 / (1 + np.exp(-variance_diff))

            return float(info_gain)

        except Exception as e:
            logger.warning(
                "information_gain_calculation_failed",
                domain=domain.value,
                error=str(e)
            )
            return 0.5

    def calculate_uncertainty(self, features: np.ndarray) -> float:
        """
        Calculate uncertainty score based on feature distribution

        Args:
            features: Feature vector

        Returns:
            float: Uncertainty score (0-1)
        """
        try:
            # Calculate coefficient of variation
            mean_val = np.mean(features)
            std_val = np.std(features)

            if mean_val > 0:
                cv = std_val / mean_val
                # Normalize using sigmoid
                uncertainty = 1 / (1 + np.exp(-cv))
            else:
                uncertainty = 0.5

            return float(uncertainty)

        except:
            return 0.5

    def adapt_weights(self, domain: ExplorationDomain, feedback_score: float):
        """
        Adapt scoring weights based on validation feedback

        Args:
            domain: Exploration domain
            feedback_score: Validation score (0-1)
        """
        if feedback_score >= 0.7:
            # Signal was validated - reinforce current weights
            self.validation_stats[domain.value]['validated'] += 1
        else:
            # Signal was rejected - adjust weights
            self.validation_stats[domain.value]['rejected'] += 1

        total_samples = sum(self.validation_stats[domain.value].values())

        if total_samples > 0 and total_samples % 50 == 0:
            # Recalculate weights every 50 samples
            validation_rate = (
                self.validation_stats[domain.value]['validated'] / total_samples
            )

            # Adjust weights based on validation rate
            if validation_rate < 0.5:
                # Low validation rate - increase novelty weight
                self.weights[domain.value]['novelty'] = min(
                    self.weights[domain.value]['novelty'] + 0.05,
                    0.6
                )
                self.weights[domain.value]['relevance'] = max(
                    self.weights[domain.value]['relevance'] - 0.05,
                    0.2
                )
            elif validation_rate > 0.8:
                # High validation rate - increase relevance weight
                self.weights[domain.value]['relevance'] = min(
                    self.weights[domain.value]['relevance'] + 0.05,
                    0.5
                )
                self.weights[domain.value]['novelty'] = max(
                    self.weights[domain.value]['novelty'] - 0.05,
                    0.2
                )

            logger.info(
                "weights_adapted",
                domain=domain.value,
                validation_rate=validation_rate,
                new_weights=self.weights[domain.value]
            )

    def get_score_distribution(self, domain: ExplorationDomain) -> Dict[str, float]:
        """
        Get statistical distribution of scores for domain

        Args:
            domain: Exploration domain

        Returns:
            Dict with score statistics
        """
        stats = self.validation_stats[domain.value]
        total = sum(stats.values())

        if total == 0:
            return {
                'validation_rate': 0.0,
                'total_samples': 0,
                'weights': self.weights[domain.value]
            }

        return {
            'validation_rate': stats['validated'] / total,
            'total_samples': total,
            'weights': self.weights[domain.value]
        }
