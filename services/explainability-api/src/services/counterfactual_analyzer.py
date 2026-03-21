"""
CounterfactualAnalyzer - Análise de cenários contrafactuais.

Analisa "what-if" com diferentes pesos de senioridade para entender
sensibilidade da decisão a mudanças nos multiplicadores hierárquicos.

Explainability API v3 - Task 4
"""

from typing import Dict, Any, List, Optional
import structlog

# Importar modelos de senioridade do consensus-engine
import sys
from pathlib import Path

# Add consensus-engine to path para importar SENIORITY_MULTIPLIERS
consensus_path = Path(__file__).parent.parent.parent.parent / "consensus-engine" / "src"
if str(consensus_path) not in sys.path:
    sys.path.insert(0, str(consensus_path))

from models.seniority import SENIORITY_MULTIPLIERS, SeniorityLevel

logger = structlog.get_logger(__name__)

# Multiplicadores invertidos para cenário de seniority inversion
INVERTED_MULTIPLIERS: Dict[SeniorityLevel, float] = {
    SeniorityLevel.EXPERT: 0.5,
    SeniorityLevel.SENIOR: 0.75,
    SeniorityLevel.MID_LEVEL: 1.0,
    SeniorityLevel.JUNIOR: 1.5,
    SeniorityLevel.TRAINEE: 2.0,
}


class CounterfactualResult:
    """Resultado de uma análise contrafactual."""

    def __init__(
        self,
        scenario_name: str,
        outcome: str,
        weighted_score: float,
        decision: str,
        breakdown: Dict[str, Any],
    ):
        self.scenario_name = scenario_name
        self.outcome = outcome
        self.weighted_score = weighted_score
        self.decision = decision
        self.breakdown = breakdown

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "scenario_name": self.scenario_name,
            "outcome": self.outcome,
            "weighted_score": self.weighted_score,
            "decision": self.decision,
            "breakdown": self.breakdown,
        }


class CounterfactualAnalyzer:
    """
    Analyzer para cenários contrafactuais de consenso hierárquico.

    Permite analisar como a decisão mudaria sob diferentes configurações
    de pesos de senioridade, ajudando a entender a sensibilidade da decisão
    à hierarquia de especialistas.
    """

    # Threshold para decisão (approve se score > 0)
    DECISION_THRESHOLD = 0.0

    def __init__(self):
        """Inicializa o analyzer contrafactual."""
        self.logger = logger

    def analyze_equal_weights(
        self, votes: List[Dict[str, Any]]
    ) -> CounterfactualResult:
        """
        Analisa cenário onde todos os especialistas têm peso igual (1.0x).

        Args:
            votes: Lista de votos dos especialistas

        Returns:
            CounterfactualResult com outcome da análise
        """
        if not votes:
            return CounterfactualResult(
                scenario_name="equal_weights",
                outcome="no_votes",
                weighted_score=0.0,
                decision="neutral",
                breakdown={},
            )

        # Aplicar peso 1.0 para todos
        weighted_sum = 0.0
        breakdown = {}

        for vote in votes:
            vote_type = vote.get("vote", "neutral")
            confidence = vote.get("confidence", 0.5)
            specialist_id = vote.get("specialist_id", "unknown")

            # Valor do voto sem multiplicador de senioridade
            vote_value = 0.0
            if vote_type == "approve":
                vote_value = confidence
            elif vote_type == "reject":
                vote_value = -confidence

            weighted_sum += vote_value

            # Adicionar ao breakdown
            breakdown[specialist_id] = {
                "vote": vote_type,
                "confidence": confidence,
                "multiplier": 1.0,
                "contribution": vote_value,
            }

        decision = self._make_decision(weighted_sum)
        outcome = self._determine_outcome(decision, votes)

        return CounterfactualResult(
            scenario_name="equal_weights",
            outcome=outcome,
            weighted_score=weighted_sum,
            decision=decision,
            breakdown=breakdown,
        )

    def analyze_no_trainee(self, votes: List[Dict[str, Any]]) -> CounterfactualResult:
        """
        Analisa cenário ignorando opiniões de trainees.

        Args:
            votes: Lista de votos dos especialistas

        Returns:
            CounterfactualResult com outcome da análise
        """
        if not votes:
            return CounterfactualResult(
                scenario_name="no_trainee",
                outcome="no_votes",
                weighted_score=0.0,
                decision="neutral",
                breakdown={},
            )

        # Filtrar trainees
        non_trainee_votes = [
            v
            for v in votes
            if v.get("seniority_level", SeniorityLevel.MID_LEVEL)
            != SeniorityLevel.TRAINEE
        ]

        if not non_trainee_votes:
            return CounterfactualResult(
                scenario_name="no_trainee",
                outcome="all_trainees",
                weighted_score=0.0,
                decision="neutral",
                breakdown={},
            )

        # Calcular com multiplicadores normais (sem trainees)
        weighted_sum = 0.0
        breakdown = {}

        for vote in non_trainee_votes:
            vote_type = vote.get("vote", "neutral")
            confidence = vote.get("confidence", 0.5)
            level = vote.get("seniority_level", SeniorityLevel.MID_LEVEL)
            specialist_id = vote.get("specialist_id", "unknown")

            multiplier = SENIORITY_MULTIPLIERS.get(level, 1.0)

            vote_value = 0.0
            if vote_type == "approve":
                vote_value = confidence
            elif vote_type == "reject":
                vote_value = -confidence

            weighted_sum += vote_value * multiplier

            breakdown[specialist_id] = {
                "vote": vote_type,
                "confidence": confidence,
                "seniority_level": level,
                "multiplier": multiplier,
                "contribution": vote_value * multiplier,
            }

        decision = self._make_decision(weighted_sum)
        outcome = self._determine_outcome(decision, non_trainee_votes)

        return CounterfactualResult(
            scenario_name="no_trainee",
            outcome=outcome,
            weighted_score=weighted_sum,
            decision=decision,
            breakdown=breakdown,
        )

    def analyze_seniority_inversion(
        self, votes: List[Dict[str, Any]]
    ) -> CounterfactualResult:
        """
        Analisa cenário com multiplicadores de senioridade invertidos.

        Expert = 0.5x, Trainee = 2.0x (inversão completa).

        Args:
            votes: Lista de votos dos especialistas

        Returns:
            CounterfactualResult com outcome da análise
        """
        if not votes:
            return CounterfactualResult(
                scenario_name="seniority_inversion",
                outcome="no_votes",
                weighted_score=0.0,
                decision="neutral",
                breakdown={},
            )

        weighted_sum = 0.0
        breakdown = {}

        for vote in votes:
            vote_type = vote.get("vote", "neutral")
            confidence = vote.get("confidence", 0.5)
            level = vote.get("seniority_level", SeniorityLevel.MID_LEVEL)
            specialist_id = vote.get("specialist_id", "unknown")

            # Usar multiplicador invertido
            multiplier = INVERTED_MULTIPLIERS.get(level, 1.0)

            vote_value = 0.0
            if vote_type == "approve":
                vote_value = confidence
            elif vote_type == "reject":
                vote_value = -confidence

            weighted_sum += vote_value * multiplier

            breakdown[specialist_id] = {
                "vote": vote_type,
                "confidence": confidence,
                "seniority_level": level,
                "normal_multiplier": SENIORITY_MULTIPLIERS.get(level, 1.0),
                "inverted_multiplier": multiplier,
                "contribution": vote_value * multiplier,
            }

        decision = self._make_decision(weighted_sum)
        outcome = self._determine_outcome(decision, votes)

        return CounterfactualResult(
            scenario_name="seniority_inversion",
            outcome=outcome,
            weighted_score=weighted_sum,
            decision=decision,
            breakdown=breakdown,
        )

    def generate_all_counterfactuals(
        self, votes: List[Dict[str, Any]], original_decision: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Gera todos os cenários contrafactuais e compara com decisão original.

        Args:
            votes: Lista de votos dos especialistas
            original_decision: Decisão original para comparação (opcional)

        Returns:
            Dicionário com todos os cenários e análise de sensibilidade
        """
        # Executar todos os cenários
        equal_weights = self.analyze_equal_weights(votes)
        no_trainee = self.analyze_no_trainee(votes)
        seniority_inversion = self.analyze_seniority_inversion(votes)

        # Calcular decisão original (com multiplicadores normais)
        original_score = self._calculate_original_score(votes)
        original_dec = self._make_decision(original_score)

        # Determinar se houve flip de decisão
        scenarios = {
            "original": {
                "decision": original_dec,
                "score": original_score,
                "scenario": "baseline",
            },
            "equal_weights": equal_weights.to_dict(),
            "no_trainee": no_trainee.to_dict(),
            "seniority_inversion": seniority_inversion.to_dict(),
        }

        # Analisar sensibilidade
        sensitivity_analysis = self._analyze_sensitivity(scenarios, original_dec)

        return {"scenarios": scenarios, "sensitivity_analysis": sensitivity_analysis}

    def _calculate_original_score(self, votes: List[Dict[str, Any]]) -> float:
        """Calcula score com multiplicadores originais de senioridade."""
        if not votes:
            return 0.0

        weighted_sum = 0.0

        for vote in votes:
            vote_type = vote.get("vote", "neutral")
            confidence = vote.get("confidence", 0.5)
            level = vote.get("seniority_level", SeniorityLevel.MID_LEVEL)

            multiplier = SENIORITY_MULTIPLIERS.get(level, 1.0)

            vote_value = 0.0
            if vote_type == "approve":
                vote_value = confidence
            elif vote_type == "reject":
                vote_value = -confidence

            weighted_sum += vote_value * multiplier

        return weighted_sum

    def _make_decision(self, weighted_score: float) -> str:
        """
        Determina decisão baseada no score ponderado.

        Args:
            weighted_score: Score ponderado acumulado

        Returns:
            "approve" se score > 0, "reject" se score < 0, "neutral" se igual
        """
        if weighted_score > self.DECISION_THRESHOLD:
            return "approve"
        elif weighted_score < self.DECISION_THRESHOLD:
            return "reject"
        return "neutral"

    def _determine_outcome(self, decision: str, votes: List[Dict[str, Any]]) -> str:
        """
        Determina outcome detalhado do cenário.

        Args:
            decision: Decisão tomada
            votes: Lista de votos analisados

        Returns:
            String descrevendo o outcome
        """
        if not votes:
            return "no_votes"

        # Outcome padrão
        return decision

    def _analyze_sensitivity(
        self, scenarios: Dict[str, Any], original_decision: str
    ) -> Dict[str, Any]:
        """
        Analisa sensibilidade da decisão aos diferentes cenários.

        Args:
            scenarios: Todos os cenários calculados
            original_decision: Decisão original (baseline)

        Returns:
            Análise de sensibilidade com flips detectados
        """
        flips = []
        robust = True

        for scenario_name, scenario_data in scenarios.items():
            if scenario_name == "original":
                continue

            decision = scenario_data.get("decision", "neutral")
            if decision != original_decision:
                robust = False
                flips.append(
                    {
                        "scenario": scenario_name,
                        "from_decision": original_decision,
                        "to_decision": decision,
                    }
                )

        return {"is_robust": robust, "decision_flips": flips, "flip_count": len(flips)}
