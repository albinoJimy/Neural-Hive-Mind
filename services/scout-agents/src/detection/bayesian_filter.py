"""Bayesian filter for noise reduction in signal detection"""
from typing import Dict, Tuple
import numpy as np
from scipy import stats
import structlog

from ..models.raw_event import RawEvent
from neural_hive_domain import UnifiedDomain

logger = structlog.get_logger()


class BayesianFilter:
    """Applies Bayesian inference to filter false positive signals"""

    def __init__(self):
        # Prior distributions per domain (Beta distribution parameters)
        # Start with uniform prior Beta(1, 1)
        self.priors: Dict[str, Tuple[float, float]] = {
            domain.value: (1.0, 1.0) for domain in UnifiedDomain
        }

        # Likelihood parameters (mean and std for normal distribution)
        self.likelihoods: Dict[str, Tuple[float, float]] = {}

    def filter(self, event: RawEvent, domain: UnifiedDomain) -> Tuple[bool, float]:
        """
        Apply Bayesian filter to event

        Args:
            event: Raw event to filter
            domain: Exploration domain

        Returns:
            Tuple of (should_process, posterior_probability)
        """
        try:
            # Extract features from event
            features = event.extract_features()
            if not features:
                return False, 0.0

            # Calculate feature mean for this event
            feature_mean = np.mean(features)

            # Get prior for this domain
            alpha, beta = self.priors.get(domain.value, (1.0, 1.0))

            # Calculate prior probability (mean of Beta distribution)
            prior_prob = alpha / (alpha + beta)

            # Calculate likelihood
            likelihood = self.calculate_likelihood(feature_mean, domain)

            # Calculate posterior using Bayes' theorem
            # P(signal|features) = P(features|signal) * P(signal) / P(features)
            # Using complementary probability for normalization
            p_signal_given_features = (likelihood * prior_prob)
            p_noise_given_features = ((1 - likelihood) * (1 - prior_prob))

            # Normalize to get true posterior probability
            total_prob = p_signal_given_features + p_noise_given_features
            if total_prob > 0:
                posterior = p_signal_given_features / total_prob
            else:
                posterior = 0.5

            # Normalize to [0, 1] (redundant but safe)
            posterior = min(max(posterior, 0.0), 1.0)

            # Decision threshold - lowered to allow signals with neutral priors
            threshold = 0.4
            should_process = posterior >= threshold

            logger.debug(
                "bayesian_filter_applied",
                domain=domain.value,
                prior=prior_prob,
                likelihood=likelihood,
                posterior=posterior,
                decision=should_process
            )

            return should_process, posterior

        except Exception as e:
            logger.error(
                "bayesian_filter_failed",
                domain=domain.value,
                error=str(e)
            )
            # Default to processing on error
            return True, 0.5

    def calculate_likelihood(self, feature_mean: float, domain: UnifiedDomain) -> float:
        """
        Calculate likelihood P(features|signal)

        Args:
            feature_mean: Mean of extracted features
            domain: Exploration domain

        Returns:
            float: Likelihood probability
        """
        # Get likelihood parameters for domain
        if domain.value not in self.likelihoods:
            # Initialize with default parameters
            self.likelihoods[domain.value] = (0.0, 1.0)

        mean, std = self.likelihoods[domain.value]

        # Calculate likelihood using normal distribution
        if std > 0:
            likelihood = stats.norm.pdf(feature_mean, loc=mean, scale=std)
            # Normalize to [0, 1] range
            likelihood = min(likelihood * 2, 1.0)
        else:
            likelihood = 0.5

        return likelihood

    def update_prior(self, domain: UnifiedDomain, is_valid_signal: bool):
        """
        Update prior distribution based on feedback

        Args:
            domain: Exploration domain
            is_valid_signal: Whether the signal was validated as true positive
        """
        alpha, beta = self.priors.get(domain.value, (1.0, 1.0))

        # Update Beta distribution parameters
        if is_valid_signal:
            alpha += 1
        else:
            beta += 1

        self.priors[domain.value] = (alpha, beta)

        logger.debug(
            "prior_updated",
            domain=domain.value,
            alpha=alpha,
            beta=beta,
            mean=alpha / (alpha + beta)
        )

    def update_likelihood(
        self,
        domain: UnifiedDomain,
        feature_mean: float,
        weight: float = 0.1
    ):
        """
        Update likelihood parameters using exponential moving average

        Args:
            domain: Exploration domain
            feature_mean: Observed feature mean
            weight: Update weight (0-1)
        """
        if domain.value not in self.likelihoods:
            self.likelihoods[domain.value] = (feature_mean, 1.0)
            return

        old_mean, old_std = self.likelihoods[domain.value]

        # Update mean using exponential moving average
        new_mean = (1 - weight) * old_mean + weight * feature_mean

        # Update std (simplified approach)
        new_std = (1 - weight) * old_std + weight * abs(feature_mean - old_mean)
        new_std = max(new_std, 0.1)  # Prevent std from becoming too small

        self.likelihoods[domain.value] = (new_mean, new_std)

        logger.debug(
            "likelihood_updated",
            domain=domain.value,
            mean=new_mean,
            std=new_std
        )

    def get_posterior_stats(self, domain: UnifiedDomain) -> Dict[str, float]:
        """
        Get statistical summary of posterior distribution

        Args:
            domain: Exploration domain

        Returns:
            Dict with mean, variance, confidence interval
        """
        alpha, beta = self.priors.get(domain.value, (1.0, 1.0))

        mean = alpha / (alpha + beta)
        variance = (alpha * beta) / ((alpha + beta) ** 2 * (alpha + beta + 1))

        # 95% confidence interval for Beta distribution
        ci_lower = stats.beta.ppf(0.025, alpha, beta)
        ci_upper = stats.beta.ppf(0.975, alpha, beta)

        return {
            'mean': mean,
            'variance': variance,
            'ci_lower': ci_lower,
            'ci_upper': ci_upper,
            'samples': alpha + beta - 2  # Number of observations
        }
