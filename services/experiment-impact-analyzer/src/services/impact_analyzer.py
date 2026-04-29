"""Core impact analyzer service."""

from datetime import datetime, timezone, timedelta
from typing import Any

import structlog
from scipy import stats
from src.clients.mongodb_client import MongoDBClient
from src.config.settings import Settings, get_settings
from src.models.impact import (
    ExperimentCorrelation,
    ExperimentImpact,
    ImpactCategory,
    ImpactDirection,
    ImpactMagnitude,
    ImpactTimeframe,
    LongTermImpact,
    MetricImpact,
    ShortTermImpact,
)

UTC = timezone.utc
logger = structlog.get_logger()


class ImpactAnalyzer:
    """Core service for analyzing experiment impact."""

    def __init__(
        self,
        settings: Settings | None = None,
        mongodb_client: MongoDBClient | None = None,
    ):
        """Initialize impact analyzer.

        Args:
            settings: Configuration settings
            mongodb_client: MongoDB client instance
        """
        self.settings = settings or get_settings()
        self.mongodb = mongodb_client

        # Analysis windows
        self.short_term_window = timedelta(days=self.settings.short_term_window_days)
        self.long_term_window = timedelta(days=self.settings.long_term_window_days)

        # Thresholds
        self.significance_threshold = self.settings.statistical_significance_threshold
        self.correlation_threshold = self.settings.correlation_threshold

        logger.info(
            "impact_analyzer_initialized",
            short_term_days=self.settings.short_term_window_days,
            long_term_days=self.settings.long_term_window_days,
        )

    async def analyze_experiment_impact(
        self,
        experiment_id: str,
        timeframes: list[ImpactTimeframe] | None = None,
        include_correlations: bool = True,
        force_refresh: bool = False,
    ) -> ExperimentImpact:
        """Analyze impact of an experiment.

        Args:
            experiment_id: Experiment ID to analyze
            timeframes: Timeframes to analyze (default: SHORT_TERM)
            include_correlations: Whether to analyze correlations
            force_refresh: Force new analysis (skip cache)

        Returns:
            ExperimentImpact analysis result
        """
        if timeframes is None:
            timeframes = [ImpactTimeframe.SHORT_TERM]

        logger.info(
            "analyzing_experiment_impact",
            experiment_id=experiment_id,
            timeframes=[tf.value for tf in timeframes],
        )

        # Check for existing analysis
        if not force_refresh:
            existing = await self.mongodb.get_impact_by_experiment(experiment_id)
            if existing:
                logger.info("using_cached_impact", experiment_id=experiment_id)
                return ExperimentImpact(**existing)

        # Get experiment data
        experiment = await self._get_experiment_data(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment not found: {experiment_id}")

        # Get baseline and post-experiment metrics
        created_at = datetime.fromtimestamp(experiment.get("created_at", 0) / 1000, tz=UTC)
        baseline_metrics = self._extract_baseline_metrics(experiment)
        post_metrics = await self._get_post_experiment_metrics(experiment_id, created_at)

        # Analyze short-term impact
        short_term = None
        if ImpactTimeframe.SHORT_TERM in timeframes or ImpactTimeframe.BOTH in timeframes:
            short_term = await self._analyze_short_term(
                experiment_id, baseline_metrics, post_metrics, created_at
            )

        # Analyze long-term impact
        long_term = None
        if (
            ImpactTimeframe.LONG_TERM in timeframes or ImpactTimeframe.BOTH in timeframes
        ) and self.settings.enable_long_term_analysis:
            long_term = await self._analyze_long_term(experiment_id, baseline_metrics, created_at)

        # Determine overall direction and magnitude
        overall_direction = self._determine_direction(short_term, long_term)
        overall_magnitude = self._determine_magnitude(short_term, long_term)

        # Determine affected categories
        categories = self._determine_categories(experiment, short_term, long_term)

        # Analyze correlations
        correlations = []
        if include_correlations and self.settings.enable_correlation_analysis:
            correlations = await self._analyze_correlations(experiment_id, categories)

        # Generate recommendation
        recommendation = self._generate_recommendation(
            overall_direction, overall_magnitude, short_term, long_term
        )

        # Calculate confidence level
        confidence = self._calculate_confidence(short_term, long_term)

        # Create impact object
        impact = ExperimentImpact(
            experiment_id=experiment_id,
            hypothesis_id=experiment.get("hypothesis_id"),
            overall_direction=overall_direction,
            overall_magnitude=overall_magnitude,
            categories=categories,
            short_term_impact=short_term,
            long_term_impact=long_term,
            correlated_experiments=correlations,
            recommendation=recommendation,
            confidence_level=confidence,
            metadata={
                "experiment_type": experiment.get("experiment_type"),
                "target_component": experiment.get("target_component"),
                "sample_size": experiment.get("sample_size"),
            },
        )

        # Save to database
        await self.mongodb.save_impact(impact.to_dict())

        logger.info(
            "impact_analysis_completed",
            experiment_id=experiment_id,
            direction=overall_direction.value,
            magnitude=overall_magnitude.value,
            confidence=confidence,
        )

        return impact

    async def _get_experiment_data(self, experiment_id: str) -> dict[str, Any] | None:
        """Get experiment data from database."""
        return await self.mongodb.get_experiment(experiment_id)

    def _extract_baseline_metrics(self, experiment: dict[str, Any]) -> dict[str, float]:
        """Extract baseline metrics from experiment."""
        baseline_config = experiment.get("baseline_configuration", {})
        # Convert string values to float
        return {k: float(v) for k, v in baseline_config.items() if self._is_numeric(v)}

    def _is_numeric(self, value: Any) -> bool:
        """Check if value is numeric."""
        try:
            float(value)
            return True
        except (ValueError, TypeError):
            return False

    async def _get_post_experiment_metrics(
        self, experiment_id: str, created_at: datetime
    ) -> dict[str, list[float]]:
        """Get metrics collected after experiment start."""
        # For now, extract from control_metrics if available
        experiment = await self.mongodb.get_experiment(experiment_id)
        if not experiment:
            return {}

        # Try to get metrics from the experiment document
        control_metrics = experiment.get("control_metrics", {})
        treatment_metrics = experiment.get("treatment_metrics", {})

        # Combine metrics from both groups
        all_metrics = {}
        for metric_name, values in control_metrics.items():
            if isinstance(values, list):
                all_metrics[metric_name] = values

        for metric_name, values in treatment_metrics.items():
            if isinstance(values, list):
                if metric_name in all_metrics:
                    all_metrics[metric_name].extend(values)
                else:
                    all_metrics[metric_name] = values

        return all_metrics

    async def _analyze_short_term(
        self,
        experiment_id: str,
        baseline_metrics: dict[str, float],
        post_metrics: dict[str, list[float]],
        created_at: datetime,
    ) -> ShortTermImpact:
        """Analyze short-term impact."""
        metric_impacts = {}

        for metric_name, baseline_value in baseline_metrics.items():
            if metric_name not in post_metrics or not post_metrics[metric_name]:
                continue

            values = post_metrics[metric_name]
            post_value = sum(values) / len(values)  # Average

            absolute_change = post_value - baseline_value
            relative_change = (
                (absolute_change / abs(baseline_value)) * 100 if baseline_value != 0 else 0
            )

            # Statistical significance test (t-test)
            is_significant = False
            p_value = None
            ci_lower = None
            ci_upper = None

            if len(values) >= 3:
                try:
                    # One-sample t-test against baseline
                    t_stat, p_value = stats.ttest_1samp(values, baseline_value)
                    is_significant = p_value < (1 - self.significance_threshold)

                    # Confidence interval
                    sem = stats.sem(values)
                    ci = stats.t.interval(
                        self.significance_threshold, len(values) - 1, loc=post_value, scale=sem
                    )
                    ci_lower, ci_upper = ci
                except Exception as e:
                    logger.warning("statistical_test_failed", metric=metric_name, error=str(e))

            metric_impacts[metric_name] = MetricImpact(
                metric_name=metric_name,
                baseline_value=baseline_value,
                post_experiment_value=post_value,
                absolute_change=absolute_change,
                relative_change_percent=relative_change,
                statistical_significance=is_significant,
                confidence_interval=(ci_lower, ci_upper) if ci_lower is not None else None,
                p_value=p_value,
            )

        # Determine immediate effects
        immediate_effects = []
        for impact in metric_impacts.values():
            if impact.statistical_significance:
                direction = "increased" if impact.relative_change_percent > 0 else "decreased"
                immediate_effects.append(
                    f"{impact.metric_name} {direction} by {abs(impact.relative_change_percent):.1f}%"
                )

        # Assess system stability
        stability = "stable"
        error_rate_impact = metric_impacts.get("error_rate")
        if error_rate_impact and error_rate_impact.relative_change_percent > 5:
            stability = "degraded"
        elif error_rate_impact and error_rate_impact.relative_change_percent < -5:
            stability = "improved"

        # Extract specific changes
        error_rate_change = None
        if error_rate_impact:
            error_rate_change = error_rate_impact.relative_change_percent

        latency_change = None
        latency_impact = metric_impacts.get("latency_p95") or metric_impacts.get("latency_p99")
        if latency_impact:
            latency_change = latency_impact.relative_change_percent

        throughput_change = None
        throughput_impact = metric_impacts.get("throughput") or metric_impacts.get(
            "requests_per_second"
        )
        if throughput_impact:
            throughput_change = throughput_impact.relative_change_percent

        return ShortTermImpact(
            timeframe_days=self.settings.short_term_window_days,
            immediate_effects=immediate_effects,
            metric_impacts=metric_impacts,
            system_stability=stability,
            error_rate_change=error_rate_change,
            latency_change=latency_change,
            throughput_change=throughput_change,
        )

    async def _analyze_long_term(
        self,
        experiment_id: str,
        baseline_metrics: dict[str, float],
        created_at: datetime,
    ) -> LongTermImpact:
        """Analyze long-term impact."""
        end_date = datetime.now(timezone.utc)
        start_date = created_at
        days_analyzed = (end_date - start_date).days

        # Get historical metrics
        metric_names = list(baseline_metrics.keys())
        history = await self.mongodb.get_metrics_history(metric_names, start_date, end_date)

        # Analyze trends
        trend_analysis = {}
        degradation_detected = False
        adaptation_observed = False
        sustained_effects = []

        for metric_name in metric_names:
            if not history:
                trend_analysis[metric_name] = "insufficient_data"
                continue

            # Extract values for this metric
            values = [m.get("value", 0) for m in history if m.get("metric_name") == metric_name]

            if len(values) < 3:
                trend_analysis[metric_name] = "insufficient_data"
                continue

            # Calculate trend using linear regression
            try:
                x = list(range(len(values)))
                slope, intercept, r_value, p_value, std_err = stats.lineregress(x, values)

                if slope > 0 and p_value < 0.05:
                    trend_analysis[metric_name] = "increasing"
                    if metric_name in ["error_rate", "latency_p95", "latency_p99"]:
                        degradation_detected = True
                    else:
                        sustained_effects.append(f"{metric_name} shows sustained improvement")
                elif slope < 0 and p_value < 0.05:
                    trend_analysis[metric_name] = "decreasing"
                    if metric_name not in ["error_rate", "latency_p95", "latency_p99"]:
                        degradation_detected = True
                    else:
                        sustained_effects.append(f"{metric_name} shows sustained reduction")
                else:
                    trend_analysis[metric_name] = "stable"

                # Check for adaptation (improvement over time)
                if len(values) > 10:
                    early_avg = sum(values[:5]) / 5
                    late_avg = sum(values[-5:]) / 5
                    if metric_name in ["error_rate", "latency_p95", "latency_p99"]:
                        if late_avg < early_avg * 0.9:
                            adaptation_observed = True
                            sustained_effects.append(f"{metric_name} shows adaptive improvement")
                    else:
                        if late_avg > early_avg * 1.1:
                            adaptation_observed = True
                            sustained_effects.append(f"{metric_name} shows adaptive improvement")

            except Exception as e:
                logger.warning("trend_analysis_failed", metric=metric_name, error=str(e))
                trend_analysis[metric_name] = "analysis_failed"

        # Calculate cumulative benefit (simplified)
        cumulative_benefit = None
        if "throughput" in trend_analysis and trend_analysis["throughput"] == "increasing":
            # Rough estimate: 5% improvement compounded over period
            cumulative_benefit = 0.05 * days_analyzed

        return LongTermImpact(
            timeframe_days=min(days_analyzed, self.settings.long_term_window_days),
            sustained_effects=sustained_effects,
            cumulative_benefit=cumulative_benefit,
            degradation_detected=degradation_detected,
            adaptation_observed=adaptation_observed,
            trend_analysis=trend_analysis,
        )

    async def _analyze_correlations(
        self, experiment_id: str, categories: list[ImpactCategory]
    ) -> list[ExperimentCorrelation]:
        """Analyze correlations with other experiments."""
        if not categories:
            return []

        # Find experiments with overlapping categories
        category_strs = [c.value for c in categories]
        correlated = await self.mongodb.find_correlated_experiments(
            experiment_id, category_strs, self.settings.correlation_threshold
        )

        correlations = []
        for exp in correlated[:10]:  # Limit to top 10
            # Calculate correlation based on shared categories
            exp_categories = exp.get("categories", [])
            shared = set(category_strs) & set(exp_categories)

            if shared:
                # Simplified correlation coefficient based on category overlap
                overlap_ratio = len(shared) / max(len(category_strs), len(exp_categories))
                correlation = min(overlap_ratio * 1.5, 1.0)  # Scale up slightly

                if correlation >= self.settings.correlation_threshold:
                    correlation_type = (
                        "positive" if correlation > 0 else "negative" if correlation < 0 else "none"
                    )

                    correlations.append(
                        ExperimentCorrelation(
                            experiment_id=exp.get("experiment_id", ""),
                            correlation_coefficient=correlation,
                            correlation_type=correlation_type,
                            shared_metrics=list(shared),
                            description=f"Shared {len(shared)} impact categories",
                        )
                    )

        return correlations

    def _determine_direction(
        self, short_term: ShortTermImpact | None, long_term: LongTermImpact | None
    ) -> ImpactDirection:
        """Determine overall impact direction."""
        positive_count = 0
        negative_count = 0

        if short_term:
            # Check error rate
            if short_term.error_rate_change is not None:
                if short_term.error_rate_change < 0:
                    positive_count += 2
                elif short_term.error_rate_change > 5:
                    negative_count += 2

            # Check latency
            if short_term.latency_change is not None:
                if short_term.latency_change < 0:
                    positive_count += 1
                elif short_term.latency_change > 10:
                    negative_count += 1

            # Check throughput
            if short_term.throughput_change is not None:
                if short_term.throughput_change > 0:
                    positive_count += 1
                elif short_term.throughput_change < -5:
                    negative_count += 1

        if long_term and long_term.degradation_detected:
            negative_count += 2
        elif long_term and long_term.adaptation_observed:
            positive_count += 1

        # Determine direction
        if positive_count > negative_count * 1.5:
            return ImpactDirection.POSITIVE
        elif negative_count > positive_count * 1.5:
            return ImpactDirection.NEGATIVE
        elif positive_count > 0 and negative_count > 0:
            return ImpactDirection.MIXED
        else:
            return ImpactDirection.NEUTRAL

    def _determine_magnitude(
        self, short_term: ShortTermImpact | None, long_term: LongTermImpact | None
    ) -> ImpactMagnitude:
        """Determine overall impact magnitude."""
        score = 0

        if short_term:
            # Significant changes increase magnitude
            for impact in short_term.metric_impacts.values():
                if impact.statistical_significance:
                    score += abs(impact.relative_change_percent) / 10

        if long_term:
            if long_term.degradation_detected:
                score += 30
            if long_term.sustained_effects:
                score += 10 * len(long_term.sustained_effects)

        if score >= 50:
            return ImpactMagnitude.CRITICAL
        elif score >= 30:
            return ImpactMagnitude.HIGH
        elif score >= 15:
            return ImpactMagnitude.MEDIUM
        elif score >= 5:
            return ImpactMagnitude.LOW
        else:
            return ImpactMagnitude.NEGLIGIBLE

    def _determine_categories(
        self,
        experiment: dict[str, Any],
        short_term: ShortTermImpact | None,
        long_term: LongTermImpact | None,
    ) -> list[ImpactCategory]:
        """Determine affected categories."""
        categories = set()
        target_component = experiment.get("target_component", "")

        # Based on metrics affected
        if short_term:
            if "error_rate" in short_term.metric_impacts:
                categories.add(ImpactCategory.RELIABILITY)
            if (
                "latency_p95" in short_term.metric_impacts
                or "latency_p99" in short_term.metric_impacts
            ):
                categories.add(ImpactCategory.PERFORMANCE)
            if (
                "throughput" in short_term.metric_impacts
                or "requests_per_second" in short_term.metric_impacts
            ):
                categories.add(ImpactCategory.SCALABILITY)

        # Based on target component
        if "consensus" in target_component.lower():
            categories.add(ImpactCategory.USER_EXPERIENCE)
        if "security" in target_component.lower():
            categories.add(ImpactCategory.SECURITY)

        return list(categories)

    def _generate_recommendation(
        self,
        direction: ImpactDirection,
        magnitude: ImpactMagnitude,
        short_term: ShortTermImpact | None,
        long_term: LongTermImpact | None,
    ) -> str:
        """Generate recommendation based on analysis."""
        if direction == ImpactDirection.POSITIVE:
            if magnitude in [ImpactMagnitude.CRITICAL, ImpactMagnitude.HIGH]:
                return (
                    "PROMOTE: Strong positive impact detected. Recommend promoting to production."
                )
            else:
                return "ACCEPT: Positive impact observed. Continue monitoring."
        elif direction == ImpactDirection.NEGATIVE:
            if magnitude in [ImpactMagnitude.CRITICAL, ImpactMagnitude.HIGH]:
                return (
                    "REVERT: Significant negative impact detected. Immediate rollback recommended."
                )
            else:
                return "MONITOR: Negative impact detected. Consider rollback or mitigation."
        elif direction == ImpactDirection.MIXED:
            return "EVALUATE: Mixed impact detected. Review trade-offs before deciding."
        else:
            return "HOLD: No significant impact detected. Continue monitoring."

    def _calculate_confidence(
        self, short_term: ShortTermImpact | None, long_term: LongTermImpact | None
    ) -> float:
        """Calculate confidence level in the analysis."""
        confidence = 0.5  # Base confidence

        if short_term:
            # Increase confidence based on statistical significance
            significant_count = sum(
                1 for m in short_term.metric_impacts.values() if m.statistical_significance
            )
            total_metrics = len(short_term.metric_impacts)
            if total_metrics > 0:
                confidence += 0.2 * (significant_count / total_metrics)

            # Increase confidence if system stability is clear
            if short_term.system_stability in ["improved", "degraded"]:
                confidence += 0.1

        if long_term and long_term.trend_analysis:
            # Increase confidence if trends are clear
            clear_trends = sum(
                1
                for t in long_term.trend_analysis.values()
                if t in ["increasing", "decreasing", "stable"]
            )
            if clear_trends > 0:
                confidence += 0.15

        return min(confidence, 1.0)
