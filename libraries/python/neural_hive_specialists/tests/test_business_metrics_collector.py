"""
Testes para BusinessMetricsCollector.

Testa:
- Correlação de opiniões com decisões
- Cálculo de métricas derivadas (agreement_rate, precision, recall, F1)
- Busca de execution outcomes
- Coleta end-to-end de business metrics
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from collections import defaultdict

from neural_hive_specialists.observability.business_metrics_collector import (
    BusinessMetricsCollector,
)
from neural_hive_specialists.metrics import SpecialistMetrics


@pytest.fixture
def mock_config():
    """Config mock para testes."""
    return {
        "mongodb_uri": "mongodb://localhost:27017",
        "mongodb_database": "neural_hive_test",
        "mongodb_opinions_collection": "opinions_test",
        "consensus_mongodb_uri": "mongodb://localhost:27017",
        "consensus_mongodb_database": "neural_hive_test",
        "consensus_collection_name": "consensus_test",
        "consensus_timestamp_field": "timestamp",
        "enable_business_metrics": True,
        "business_metrics_window_hours": 24,
        "enable_business_value_tracking": True,
        "execution_ticket_api_url": "http://execution-ticket-api:8080",
    }


@pytest.fixture
def mock_metrics_registry():
    """Registry de métricas mock."""
    # Mock SpecialistMetrics ao invés de criar instâncias reais
    mock_metrics = {}

    for specialist_type in ["technical", "business", "behavior"]:
        metrics = Mock(spec=SpecialistMetrics)
        metrics.specialist_type = specialist_type

        # Mock dos contadores e gauges
        metrics.business_true_positives_total = Mock()
        metrics.business_true_positives_total.labels.return_value.inc = Mock()

        metrics.business_true_negatives_total = Mock()
        metrics.business_true_negatives_total.labels.return_value.inc = Mock()

        metrics.business_false_positives_total = Mock()
        metrics.business_false_positives_total.labels.return_value.inc = Mock()

        metrics.business_false_negatives_total = Mock()
        metrics.business_false_negatives_total.labels.return_value.inc = Mock()

        # Mock dos métodos
        metrics.set_consensus_agreement_rate = Mock()
        metrics.set_false_positive_rate = Mock()
        metrics.set_false_negative_rate = Mock()
        metrics.set_precision_score = Mock()
        metrics.set_recall_score = Mock()
        metrics.set_f1_score = Mock()
        metrics.update_business_metrics_timestamp = Mock()
        metrics.increment_business_value = Mock()

        # Mock get_summary
        metrics.get_summary.return_value = {
            "avg_processing_time_ms": 100,
            "accuracy_score": 0.85,
            "business_metrics": {
                "consensus_agreement_rate": 0.85,
                "false_positive_rate": 0.10,
                "false_negative_rate": 0.08,
                "precision": 0.80,
                "recall": 0.82,
                "f1_score": 0.81,
            },
        }

        mock_metrics[specialist_type] = metrics

    return mock_metrics


@pytest.fixture
def collector(mock_config, mock_metrics_registry):
    """Instância de BusinessMetricsCollector para testes."""
    with patch(
        "neural_hive_specialists.observability.business_metrics_collector.MongoClient"
    ):
        collector = BusinessMetricsCollector(mock_config, mock_metrics_registry)

        # Mock das collections
        collector._ledger_client = Mock()
        collector._consensus_client = Mock()

        return collector


class TestCorrelateOpinionsWithDecisions:
    """Testes para _correlate_opinions_with_decisions."""

    def test_all_agree_tp(self, collector):
        """Testa caso onde todos aprovam (TP)."""
        opinions = [
            {"opinion_id": "op1", "specialist_type": "technical"},
            {"opinion_id": "op2", "specialist_type": "business"},
        ]

        decisions = [
            {
                "final_decision": "APPROVE",
                "specialist_votes": [
                    {
                        "opinion_id": "op1",
                        "recommendation": "approve",
                        "specialist_type": "technical",
                    },
                    {
                        "opinion_id": "op2",
                        "recommendation": "approve",
                        "specialist_type": "business",
                    },
                ],
                "plan_id": "plan1",
            }
        ]

        correlations = collector._correlate_opinions_with_decisions(opinions, decisions)

        assert len(correlations) == 2
        assert all(c["category"] == "tp" for c in correlations)
        assert all(c["final_decision"] == "APPROVE" for c in correlations)

    def test_all_agree_tn(self, collector):
        """Testa caso onde todos rejeitam (TN)."""
        opinions = [
            {"opinion_id": "op1", "specialist_type": "technical"},
            {"opinion_id": "op2", "specialist_type": "business"},
        ]

        decisions = [
            {
                "final_decision": "REJECT",
                "specialist_votes": [
                    {
                        "opinion_id": "op1",
                        "recommendation": "reject",
                        "specialist_type": "technical",
                    },
                    {
                        "opinion_id": "op2",
                        "recommendation": "reject",
                        "specialist_type": "business",
                    },
                ],
                "plan_id": "plan1",
            }
        ]

        correlations = collector._correlate_opinions_with_decisions(opinions, decisions)

        assert len(correlations) == 2
        assert all(c["category"] == "tn" for c in correlations)
        assert all(c["final_decision"] == "REJECT" for c in correlations)

    def test_false_positive(self, collector):
        """Testa falso positivo (aprovou mas consenso rejeitou)."""
        opinions = [{"opinion_id": "op1", "specialist_type": "technical"}]

        decisions = [
            {
                "final_decision": "REJECT",
                "specialist_votes": [
                    {
                        "opinion_id": "op1",
                        "recommendation": "approve",
                        "specialist_type": "technical",
                    }
                ],
                "plan_id": "plan1",
            }
        ]

        correlations = collector._correlate_opinions_with_decisions(opinions, decisions)

        assert len(correlations) == 1
        assert correlations[0]["category"] == "fp"
        assert correlations[0]["specialist_recommendation"] == "approve"
        assert correlations[0]["final_decision"] == "REJECT"

    def test_false_negative(self, collector):
        """Testa falso negativo (rejeitou mas consenso aprovou)."""
        opinions = [{"opinion_id": "op1", "specialist_type": "technical"}]

        decisions = [
            {
                "final_decision": "APPROVE",
                "specialist_votes": [
                    {
                        "opinion_id": "op1",
                        "recommendation": "reject",
                        "specialist_type": "technical",
                    }
                ],
                "plan_id": "plan1",
            }
        ]

        correlations = collector._correlate_opinions_with_decisions(opinions, decisions)

        assert len(correlations) == 1
        assert correlations[0]["category"] == "fn"
        assert correlations[0]["specialist_recommendation"] == "reject"
        assert correlations[0]["final_decision"] == "APPROVE"

    def test_ignore_review_required(self, collector):
        """Testa que review_required e conditional são ignorados."""
        opinions = [
            {"opinion_id": "op1", "specialist_type": "technical"},
            {"opinion_id": "op2", "specialist_type": "business"},
        ]

        decisions = [
            {
                "final_decision": "APPROVE",
                "specialist_votes": [
                    {
                        "opinion_id": "op1",
                        "recommendation": "review_required",
                        "specialist_type": "technical",
                    },
                    {
                        "opinion_id": "op2",
                        "recommendation": "conditional",
                        "specialist_type": "business",
                    },
                ],
                "plan_id": "plan1",
            }
        ]

        correlations = collector._correlate_opinions_with_decisions(opinions, decisions)

        assert len(correlations) == 2
        assert all(c["category"] == "unknown" for c in correlations)

    def test_mixed_scenario(self, collector):
        """Testa cenário misto com TP, TN, FP, FN."""
        opinions = [
            {"opinion_id": "op1"},
            {"opinion_id": "op2"},
            {"opinion_id": "op3"},
            {"opinion_id": "op4"},
        ]

        decisions = [
            {
                "final_decision": "APPROVE",
                "specialist_votes": [
                    {
                        "opinion_id": "op1",
                        "recommendation": "approve",
                        "specialist_type": "technical",
                    },  # TP
                    {
                        "opinion_id": "op2",
                        "recommendation": "reject",
                        "specialist_type": "business",
                    },  # FN
                ],
                "plan_id": "plan1",
            },
            {
                "final_decision": "REJECT",
                "specialist_votes": [
                    {
                        "opinion_id": "op3",
                        "recommendation": "reject",
                        "specialist_type": "behavior",
                    },  # TN
                    {
                        "opinion_id": "op4",
                        "recommendation": "approve",
                        "specialist_type": "technical",
                    },  # FP
                ],
                "plan_id": "plan2",
            },
        ]

        correlations = collector._correlate_opinions_with_decisions(opinions, decisions)

        categories = [c["category"] for c in correlations]
        assert "tp" in categories
        assert "tn" in categories
        assert "fp" in categories
        assert "fn" in categories


class TestCalculateDerivedMetrics:
    """Testes para _calculate_derived_metrics."""

    def test_perfect_agreement(self, collector):
        """Testa métricas com concordância perfeita (todos TP/TN)."""
        confusion_matrix = {"tp": 80, "tn": 20, "fp": 0, "fn": 0}

        metrics = collector._calculate_derived_metrics(confusion_matrix)

        assert metrics["agreement_rate"] == 1.0
        assert metrics["fp_rate"] == 0.0
        assert metrics["fn_rate"] == 0.0
        assert metrics["precision"] == 1.0
        assert metrics["recall"] == 1.0
        assert metrics["f1_score"] == 1.0

    def test_all_disagree(self, collector):
        """Testa métricas com discordância total (todos FP/FN)."""
        confusion_matrix = {"tp": 0, "tn": 0, "fp": 50, "fn": 50}

        metrics = collector._calculate_derived_metrics(confusion_matrix)

        assert metrics["agreement_rate"] == 0.0
        assert metrics["fp_rate"] == 1.0  # FP / (FP + TN)
        assert metrics["fn_rate"] == 1.0  # FN / (FN + TP)
        assert metrics["precision"] == 0.0
        assert metrics["recall"] == 0.0
        assert metrics["f1_score"] == 0.0

    def test_realistic_scenario(self, collector):
        """Testa cenário realista com valores mistos."""
        confusion_matrix = {"tp": 70, "tn": 15, "fp": 10, "fn": 5}

        metrics = collector._calculate_derived_metrics(confusion_matrix)

        # Agreement rate = (TP + TN) / total = (70 + 15) / 100 = 0.85
        assert pytest.approx(metrics["agreement_rate"], 0.01) == 0.85

        # FP rate = FP / (FP + TN) = 10 / (10 + 15) = 0.4
        assert pytest.approx(metrics["fp_rate"], 0.01) == 0.4

        # FN rate = FN / (FN + TP) = 5 / (5 + 70) = 0.0667
        assert pytest.approx(metrics["fn_rate"], 0.01) == 0.0667

        # Precision = TP / (TP + FP) = 70 / (70 + 10) = 0.875
        assert pytest.approx(metrics["precision"], 0.01) == 0.875

        # Recall = TP / (TP + FN) = 70 / (70 + 5) = 0.933
        assert pytest.approx(metrics["recall"], 0.01) == 0.933

        # F1 = 2 * (P * R) / (P + R) = 2 * (0.875 * 0.933) / (0.875 + 0.933) = 0.903
        assert pytest.approx(metrics["f1_score"], 0.01) == 0.903

    def test_zero_total(self, collector):
        """Testa caso com total zero."""
        confusion_matrix = {"tp": 0, "tn": 0, "fp": 0, "fn": 0}

        metrics = collector._calculate_derived_metrics(confusion_matrix)

        assert all(v == 0.0 for v in metrics.values())


class TestFetchExecutionOutcomes:
    """Testes para _fetch_execution_outcomes."""

    @patch("requests.post")
    def test_successful_fetch(self, mock_post, collector):
        """Testa busca bem-sucedida de outcomes."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tickets": [
                {"plan_id": "plan1", "status": "COMPLETED"},
                {"plan_id": "plan2", "status": "FAILED"},
                {"plan_id": "plan3", "status": "IN_PROGRESS"},
            ]
        }
        mock_post.return_value = mock_response

        plan_ids = ["plan1", "plan2", "plan3"]
        outcomes = collector._fetch_execution_outcomes(plan_ids)

        assert outcomes == {
            "plan1": "COMPLETED",
            "plan2": "FAILED",
            "plan3": "IN_PROGRESS",
        }

        # Verificar chamada correta à API
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "by-plans" in call_args[0][0]
        assert call_args[1]["json"] == {"plan_ids": plan_ids}
        assert call_args[1]["timeout"] == 10

    @patch("requests.post")
    def test_timeout_handling(self, mock_post, collector):
        """Testa tratamento de timeout."""
        import requests

        mock_post.side_effect = requests.exceptions.Timeout()

        plan_ids = ["plan1", "plan2"]
        outcomes = collector._fetch_execution_outcomes(plan_ids)

        assert outcomes == {}

    @patch("requests.post")
    def test_error_handling(self, mock_post, collector):
        """Testa tratamento de erro HTTP."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        plan_ids = ["plan1"]
        outcomes = collector._fetch_execution_outcomes(plan_ids)

        assert outcomes == {}

    def test_no_api_url_configured(self, collector):
        """Testa quando execution_ticket_api_url não está configurado."""
        collector.execution_ticket_api_url = None

        outcomes = collector._fetch_execution_outcomes(["plan1"])

        assert outcomes == {}

    def test_empty_plan_ids(self, collector):
        """Testa com lista vazia de plan_ids."""
        outcomes = collector._fetch_execution_outcomes([])

        assert outcomes == {}


class TestCollectBusinessMetrics:
    """Testes para collect_business_metrics (end-to-end)."""

    def test_disabled_collection(self, collector):
        """Testa quando business metrics está desabilitado."""
        collector.enable_business_metrics = False

        result = collector.collect_business_metrics()

        assert result["status"] == "disabled"

    def test_no_data(self, collector):
        """Testa quando não há dados para processar."""
        with patch.object(collector, "ledger_collection") as mock_ledger, patch.object(
            collector, "consensus_collection"
        ) as mock_consensus:
            mock_ledger.find.return_value = []
            mock_consensus.find.return_value = []

            result = collector.collect_business_metrics()

            assert result["status"] == "no_data"
            assert result["opinions"] == 0
            assert result["decisions"] == 0

    @patch("requests.post")
    def test_successful_collection(self, mock_post, collector, mock_metrics_registry):
        """Testa coleta bem-sucedida end-to-end."""
        # Mock de opiniões
        opinions = [
            {
                "opinion_id": "op1",
                "evaluated_at": datetime.utcnow(),
                "specialist_type": "technical",
            },
            {
                "opinion_id": "op2",
                "evaluated_at": datetime.utcnow(),
                "specialist_type": "business",
            },
            {
                "opinion_id": "op3",
                "evaluated_at": datetime.utcnow(),
                "specialist_type": "technical",
            },
        ]

        # Mock de decisões
        decisions = [
            {
                "timestamp": datetime.utcnow(),
                "final_decision": "APPROVE",
                "specialist_votes": [
                    {
                        "opinion_id": "op1",
                        "recommendation": "approve",
                        "specialist_type": "technical",
                    },  # TP
                    {
                        "opinion_id": "op2",
                        "recommendation": "reject",
                        "specialist_type": "business",
                    },  # FN
                ],
                "plan_id": "plan1",
            },
            {
                "timestamp": datetime.utcnow(),
                "final_decision": "REJECT",
                "specialist_votes": [
                    {
                        "opinion_id": "op3",
                        "recommendation": "reject",
                        "specialist_type": "technical",
                    }  # TN
                ],
                "plan_id": "plan2",
            },
        ]

        with patch.object(collector, "ledger_collection") as mock_ledger, patch.object(
            collector, "consensus_collection"
        ) as mock_consensus:
            mock_ledger.find.return_value = opinions
            mock_consensus.find.return_value = decisions

            # Mock execution outcomes
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "tickets": [{"plan_id": "plan1", "status": "COMPLETED"}]
            }
            mock_post.return_value = mock_response

            result = collector.collect_business_metrics()

            # Verificar resultado
            assert result["status"] == "success"
            assert result["opinions_processed"] == 3
            assert result["decisions_processed"] == 2
            assert result["correlations_created"] == 3
            assert result["specialists_updated"] == 2  # technical e business

            # Verificar que métricas Prometheus foram atualizadas
            technical_metrics = mock_metrics_registry["technical"]
            summary = technical_metrics.get_summary()

            # Technical teve 1 TP e 1 TN
            assert "business_metrics" in summary

    def test_cache_usage(self, collector):
        """Testa uso de cache."""
        opinions = [{"opinion_id": "op1", "evaluated_at": datetime.utcnow()}]
        decisions = [
            {
                "timestamp": datetime.utcnow(),
                "final_decision": "APPROVE",
                "specialist_votes": [
                    {
                        "opinion_id": "op1",
                        "recommendation": "approve",
                        "specialist_type": "technical",
                    }
                ],
            }
        ]

        with patch.object(collector, "ledger_collection") as mock_ledger, patch.object(
            collector, "consensus_collection"
        ) as mock_consensus:
            mock_ledger.find.return_value = opinions
            mock_consensus.find.return_value = decisions

            # Primeira chamada
            result1 = collector.collect_business_metrics()
            assert result1["status"] == "success"

            # Segunda chamada (deve usar cache)
            result2 = collector.collect_business_metrics()
            assert result2["status"] == "success"

            # MongoDB deve ter sido chamado apenas uma vez
            assert mock_ledger.find.call_count == 1
            assert mock_consensus.find.call_count == 1
