"""
OntologyBasedEvaluator: Avaliação baseada em ontologia e regras semânticas.

Usa ontologias carregadas (intents_taxonomy.json, architecture_patterns.json)
para classificação e raciocínio semântico sem string-match.
"""

from typing import Dict, List, Any, Optional
import structlog
import json
from pathlib import Path

logger = structlog.get_logger(__name__)


class OntologyBasedEvaluator:
    """Avaliador baseado em ontologia e regras semânticas."""

    def __init__(self, config: Dict[str, Any]):
        """
        Inicializa avaliador baseado em ontologia.

        Args:
            config: Configuração com ontology_path
        """
        self.config = config
        self.ontology_path = config.get("ontology_path")

        # Ontologias carregadas
        self.intents_taxonomy: Optional[Dict[str, Any]] = None
        self.architecture_patterns: Optional[Dict[str, Any]] = None

        # Carregar ontologias
        self._load_ontologies()

        logger.info(
            "OntologyBasedEvaluator initialized",
            ontology_path=self.ontology_path,
            intents_loaded=self.intents_taxonomy is not None,
            patterns_loaded=self.architecture_patterns is not None,
        )

    def _load_ontologies(self):
        """Carrega ontologias de arquivos JSON."""
        if not self.ontology_path:
            logger.warning("No ontology_path configured")
            return

        ontology_dir = Path(self.ontology_path)

        # Carregar taxonomia de intents
        intents_file = ontology_dir / "intents_taxonomy.json"
        if intents_file.exists():
            try:
                with open(intents_file, "r", encoding="utf-8") as f:
                    self.intents_taxonomy = json.load(f)
                logger.info("Intents taxonomy loaded", file=str(intents_file))
            except Exception as e:
                logger.error("Failed to load intents taxonomy", error=str(e))

        # Carregar padrões arquiteturais
        patterns_file = ontology_dir / "architecture_patterns.json"
        if patterns_file.exists():
            try:
                with open(patterns_file, "r", encoding="utf-8") as f:
                    self.architecture_patterns = json.load(f)
                logger.info("Architecture patterns loaded", file=str(patterns_file))
            except Exception as e:
                logger.error("Failed to load architecture patterns", error=str(e))

    def evaluate_security_level(
        self, cognitive_plan: Dict[str, Any], extracted_features: Dict[str, Any]
    ) -> float:
        """
        Avalia nível de segurança baseado em ontologia.

        Args:
            cognitive_plan: Plano cognitivo
            extracted_features: Features extraídas

        Returns:
            Score de segurança (0.0-1.0)
        """
        if not self.intents_taxonomy:
            return 0.5

        try:
            # Obter domínio mapeado
            domain = extracted_features.get("metadata_features", {}).get("domain")

            if not domain:
                return 0.5

            # Buscar domínio na taxonomia
            domains = self.intents_taxonomy.get("domains", {})
            domain_info = domains.get(domain)

            if not domain_info:
                # Domínio não encontrado, retornar neutro
                return 0.5

            # Obter risk_weight do domínio
            risk_weight = domain_info.get("risk_weight", 0.5)

            # Se domínio tem alto risk_weight, segurança é mais importante
            # Inverter para score de segurança (maior risco = menor score base)
            base_security_score = 1.0 - risk_weight

            # Ajustar baseado em subcategorias e task_types
            subcategories = domain_info.get("subcategories", [])

            # Verificar se há subcategorias relacionadas a segurança
            security_subcats = [
                sub
                for sub in subcategories
                if "security" in sub.lower() or "authentication" in sub.lower()
            ]

            if security_subcats:
                # Boost se domínio já considera segurança
                base_security_score = min(1.0, base_security_score + 0.2)

            logger.debug(
                "Security level evaluated via ontology",
                domain=domain,
                risk_weight=risk_weight,
                security_score=base_security_score,
            )

            return float(max(0.0, min(1.0, base_security_score)))

        except Exception as e:
            logger.error("Failed to evaluate security level", error=str(e))
            return 0.5

    def evaluate_architecture_compliance(
        self, cognitive_plan: Dict[str, Any], extracted_features: Dict[str, Any]
    ) -> float:
        """
        Avalia conformidade arquitetural baseada em padrões conhecidos.

        Args:
            cognitive_plan: Plano cognitivo
            extracted_features: Features extraídas

        Returns:
            Score de conformidade arquitetural (0.0-1.0)
        """
        if not self.architecture_patterns:
            return 0.5

        try:
            # Verificar padrões arquiteturais nas features de grafo
            graph_features = extracted_features.get("graph_features", {})

            # Indicadores de boa arquitetura:
            # 1. Densidade moderada (não muito acoplado)
            density = graph_features.get("density", 0.5)
            density_score = 1.0 - abs(density - 0.3)  # Ideal ~0.3

            # 2. Baixa centralidade máxima (não há gargalos)
            max_centrality = graph_features.get("max_centrality", 0.0)
            centrality_score = 1.0 - max_centrality

            # 3. Alto paralelismo (tarefas independentes)
            max_parallelism = graph_features.get("max_parallelism", 1)
            num_tasks = len(cognitive_plan.get("tasks", []))
            parallelism_ratio = max_parallelism / max(1, num_tasks)
            parallelism_score = min(1.0, parallelism_ratio * 2)

            # Score agregado
            architecture_score = (
                density_score * 0.3 + centrality_score * 0.3 + parallelism_score * 0.4
            )

            logger.debug(
                "Architecture compliance evaluated",
                density=density,
                max_centrality=max_centrality,
                max_parallelism=max_parallelism,
                architecture_score=architecture_score,
            )

            return float(max(0.0, min(1.0, architecture_score)))

        except Exception as e:
            logger.error("Failed to evaluate architecture compliance", error=str(e))
            return 0.5

    def evaluate_complexity(
        self, cognitive_plan: Dict[str, Any], extracted_features: Dict[str, Any]
    ) -> float:
        """
        Avalia complexidade do plano baseado em ontologia e features.

        Args:
            cognitive_plan: Plano cognitivo
            extracted_features: Features extraídas

        Returns:
            Score de complexidade (0.0-1.0), onde maior = mais complexo
        """
        try:
            # Obter complexity_factor do domínio
            domain = extracted_features.get("metadata_features", {}).get("domain")
            complexity_factor = 0.5

            if self.intents_taxonomy and domain:
                domains = self.intents_taxonomy.get("domains", {})
                domain_info = domains.get(domain, {})

                # Buscar task_types para obter complexity_factor
                task_types = domain_info.get("task_types", [])
                if task_types:
                    # Pegar complexity_factor médio
                    factors = [
                        tt.get("complexity_factor", 1.0)
                        for tt in task_types
                        if isinstance(tt, dict)
                    ]
                    if factors:
                        complexity_factor = sum(factors) / len(factors)

            # Combinar com features estruturais
            graph_features = extracted_features.get("graph_features", {})

            # Normalizar comprimento de caminho crítico (típico: 1-10 tarefas)
            critical_path = graph_features.get("critical_path_length", 0)
            path_complexity = min(1.0, critical_path / 10.0)

            # Densidade de dependências
            density = graph_features.get("density", 0.0)

            # Score final de complexidade
            complexity_score = (
                complexity_factor * 0.4 + path_complexity * 0.3 + density * 0.3
            )

            logger.debug(
                "Complexity evaluated",
                domain=domain,
                complexity_factor=complexity_factor,
                critical_path=critical_path,
                complexity_score=complexity_score,
            )

            return float(max(0.0, min(1.0, complexity_score)))

        except Exception as e:
            logger.error("Failed to evaluate complexity", error=str(e))
            return 0.5

    def evaluate_risk_patterns(
        self, cognitive_plan: Dict[str, Any], extracted_features: Dict[str, Any]
    ) -> float:
        """
        Detecta padrões de risco conhecidos na ontologia.

        Args:
            cognitive_plan: Plano cognitivo
            extracted_features: Features extraídas

        Returns:
            Score de risco (0.0-1.0)
        """
        if not self.intents_taxonomy:
            return 0.5

        try:
            domain = extracted_features.get("metadata_features", {}).get("domain")

            if not domain:
                return 0.5

            # Buscar risk_patterns do domínio
            domains = self.intents_taxonomy.get("domains", {})
            domain_info = domains.get(domain, {})

            risk_patterns = domain_info.get("risk_patterns", [])

            if not risk_patterns:
                # Usar risk_weight como proxy
                return domain_info.get("risk_weight", 0.5)

            # Analisar padrões de risco
            total_risk_score = 0.0
            pattern_count = 0

            for pattern in risk_patterns:
                if isinstance(pattern, dict):
                    threshold = pattern.get("threshold", 0.5)
                    severity = pattern.get("severity", "medium")

                    # Mapear severidade para score
                    severity_scores = {
                        "low": 0.3,
                        "medium": 0.5,
                        "high": 0.7,
                        "critical": 0.9,
                    }

                    risk_contribution = severity_scores.get(severity, 0.5) * threshold
                    total_risk_score += risk_contribution
                    pattern_count += 1

            if pattern_count > 0:
                avg_risk = total_risk_score / pattern_count
            else:
                avg_risk = 0.5

            logger.debug(
                "Risk patterns evaluated",
                domain=domain,
                num_patterns=pattern_count,
                risk_score=avg_risk,
            )

            return float(max(0.0, min(1.0, avg_risk)))

        except Exception as e:
            logger.error("Failed to evaluate risk patterns", error=str(e))
            return 0.5

    def get_domain_recommendations(
        self, domain: str, risk_score: float, confidence_score: float
    ) -> str:
        """
        Obtém recomendação baseada em domínio e scores.

        Args:
            domain: Domínio do plano
            risk_score: Score de risco
            confidence_score: Score de confiança

        Returns:
            Recomendação (approve, reject, review_required, conditional)
        """
        # Regras básicas
        if confidence_score >= 0.8 and risk_score < 0.3:
            return "approve"
        elif confidence_score < 0.5 or risk_score > 0.7:
            return "reject"
        elif risk_score > 0.5:
            return "review_required"
        else:
            return "conditional"
