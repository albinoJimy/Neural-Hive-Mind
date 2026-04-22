"""Engine de Classificação de Intenções para NLU.

Autor: Neural Hive Mind
Criado: 2026-04-20 (REFACTOR-A-001)
"""

import logging
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from neural_hive_domain import UnifiedDomain

logger = logging.getLogger(__name__)


class ClassifierEngine:
    """Engine de classificação baseado em regras configuráveis."""

    def __init__(
        self,
        rules_config_path: Optional[str] = None,
        enable_custom_rules: bool = True,
    ):
        """Inicializa engine de classificação.

        Args:
            rules_config_path: Caminho para arquivo de regras customizadas
            enable_custom_rules: Se permite carregar regras de arquivo
        """
        self.rules_config_path = rules_config_path
        self.enable_custom_rules = enable_custom_rules
        self.classification_rules: dict[str, Any] = {}

        # Estruturas otimizadas
        self.compiled_patterns: dict[str, list[re.Pattern]] = {}
        self.keyword_sets: dict[str, set[str]] = {}
        self.subcategory_keyword_sets: dict[str, dict[str, set[str]]] = {}

    async def initialize(self) -> None:
        """Carrega e prepara regras de classificação."""
        self.classification_rules = self._get_default_classification_rules()

        # Tentar carregar regras customizadas
        if self.enable_custom_rules and self.rules_config_path:
            await self._load_custom_rules()

        # Preparar estruturas otimizadas
        self._prepare_optimized_structures()

    async def _load_custom_rules(self) -> None:
        """Carrega regras de arquivo de configuração."""
        try:
            rules_path = Path(self.rules_config_path)
            if rules_path.exists():
                with open(rules_path, encoding="utf-8") as f:
                    custom_rules = yaml.safe_load(f)
                    if custom_rules:
                        self._merge_classification_rules(custom_rules)
                        logger.info(f"Regras customizadas carregadas de {rules_path}")
        except Exception as e:
            logger.warning(f"Erro carregando regras customizadas: {e}")

    def _prepare_optimized_structures(self) -> None:
        """Pré-compila patterns e cria keyword sets."""
        domains_config = self.classification_rules.get("domains", {})

        for domain_name, domain_config in domains_config.items():
            # Compilar regex patterns
            patterns = domain_config.get("patterns", [])
            self.compiled_patterns[domain_name] = [re.compile(p) for p in patterns]

            # Converter keywords para set
            keywords = domain_config.get("keywords", [])
            self.keyword_sets[domain_name] = set(keywords)

            # Converter subcategory keywords
            subcategories = domain_config.get("subcategories", {})
            self.subcategory_keyword_sets[domain_name] = {
                subcat_name: set(subcat_keywords)
                for subcat_name, subcat_keywords in subcategories.items()
            }

        logger.debug(f"Estruturas preparadas para {len(self.compiled_patterns)} domínios")

    def _merge_classification_rules(self, custom_rules: dict[str, Any]) -> None:
        """Mescla regras customizadas com padrão."""
        if "domains" in custom_rules:
            for domain_name, domain_config in custom_rules["domains"].items():
                if domain_name in self.classification_rules["domains"]:
                    default_domain = self.classification_rules["domains"][domain_name]
                    if "keywords" in domain_config:
                        default_domain["keywords"].extend(domain_config["keywords"])
                    if "patterns" in domain_config:
                        default_domain["patterns"].extend(domain_config["patterns"])
                    if "subcategories" in domain_config:
                        default_domain["subcategories"].update(domain_config["subcategories"])
                else:
                    self.classification_rules["domains"][domain_name] = domain_config

        if "quality_thresholds" in custom_rules:
            self.classification_rules["quality_thresholds"].update(
                custom_rules["quality_thresholds"]
            )

        if "confidence_boosters" in custom_rules:
            self.classification_rules["confidence_boosters"].update(
                custom_rules["confidence_boosters"]
            )

    def classify(
        self,
        text: str,
        entities: Optional[list] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> tuple[UnifiedDomain, float, Optional[str]]:
        """Classifica texto em domínio e subcategoria.

        Args:
            text: Texto para classificar
            entities: Entidades extraídas (boosts confiança)
            context: Contexto adicional

        Returns:
            Tupla (domínio, confiança, subcategoria)
        """
        text_lower = text.lower()

        # Calcular score para cada domínio
        domain_scores = {}

        for domain_name, domain_config in self.classification_rules.get("domains", {}).items():
            score = self._calculate_domain_score(text_lower, domain_name, entities, context)
            domain_scores[domain_name] = score

        # Encontrar melhor domínio
        best_domain = max(domain_scores, key=domain_scores.get)
        best_score = domain_scores[best_domain]

        # Normalizar score para 0-1 (divisor ajustado para máximo esperado de 2.0)
        confidence = min(best_score / 2.0, 1.0)

        # Detectar subcategoria
        subcategory = self._detect_subcategory(text_lower, best_domain)

        try:
            domain_enum = UnifiedDomain[best_domain]
        except KeyError:
            domain_enum = UnifiedDomain.BUSINESS

        return domain_enum, confidence, subcategory

    def _calculate_domain_score(
        self,
        text: str,
        domain_name: str,
        entities: Optional[list] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> float:
        """Calcula score de confiança para um domínio."""
        score = 0.0

        # 1. Match de keywords (até 1.0 ponto)
        keyword_set = self.keyword_sets.get(domain_name, set())
        keyword_matches = sum(1 for kw in keyword_set if kw.lower() in text)
        score += min(keyword_matches * 0.2, 1.0)

        # 2. Match de patterns (até 1.0 ponto)
        patterns = self.compiled_patterns.get(domain_name, [])
        pattern_matches = sum(1 for p in patterns if p.search(text))
        score += min(pattern_matches * 0.3, 1.0)

        # 3. Presença de entidades relacionadas (até 0.5 pontos)
        if entities:
            entity_types = {e.type for e in entities}
            domain_entity_types = self._get_domain_entity_types(domain_name)
            if entity_types & domain_entity_types:
                score += 0.5

        # 4. Context role match (até 0.5 pontos)
        if context and "role" in context:
            role = context["role"].lower()
            if self._role_matches_domain(role, domain_name):
                score += 0.5

        return score

    def _get_domain_entity_types(self, domain_name: str) -> set[str]:
        """Retorna tipos de entidades relevantes para domínio."""
        mapping = {
            "BUSINESS": {"ORGANIZATION", "PERSON", "MONEY", "PERCENTAGE"},
            "TECHNICAL": {"ORGANIZATION", "PRODUCT"},
            "INFRASTRUCTURE": {"ORGANIZATION", "LOCATION"},
            "SECURITY": {"PERSON", "ORGANIZATION"},
        }
        return set(mapping.get(domain_name, set()))

    def _role_matches_domain(self, role: str, domain_name: str) -> bool:
        """Verifica se role de contexto combina com domínio."""
        mapping = {
            "business": "BUSINESS",
            "developer": "TECHNICAL",
            "devops": "INFRASTRUCTURE",
            "security": "SECURITY",
        }
        return mapping.get(role) == domain_name

    def _detect_subcategory(self, text: str, domain_name: str) -> Optional[str]:
        """Detecta subcategoria dentro do domínio."""
        subcategories = self.subcategory_keyword_sets.get(domain_name, {})

        for subcat_name, keywords in subcategories.items():
            matches = sum(1 for kw in keywords if kw.lower() in text)
            if matches >= 2:  # Mínimo de 2 matches
                return subcat_name

        return None

    def validate_text_quality(self, text: str) -> tuple[bool, Optional[str]]:
        """Valida qualidade do texto para processamento.

        Args:
            text: Texto para validar

        Returns:
            Tupla (válido, razão se inválido)
        """
        thresholds = self.classification_rules.get("quality_thresholds", {})

        # Validar comprimento
        min_length = thresholds.get("min_text_length", 3)
        max_length = thresholds.get("max_text_length", 10000)

        if len(text) < min_length:
            return False, f"Texto muito curto (mínimo: {min_length})"

        if len(text) > max_length:
            return False, f"Texto muito longo (máximo: {max_length})"

        # Validar palavras mínimas
        min_words = thresholds.get("min_words", 2)
        words = text.split()
        if len(words) < min_words:
            return False, f"Poucas palavras (mínimo: {min_words})"

        # Validar contra padrões de spam
        spam_patterns = thresholds.get("spam_patterns", [])
        for pattern in spam_patterns:
            if re.match(pattern, text.strip()):
                return False, "Texto corresponde a padrão de spam"

        return True, None

    def get_supported_domains(self) -> list[str]:
        """Retorna lista de domínios suportados."""
        return list(self.classification_rules.get("domains", {}).keys())

    def get_domain_config(self, domain_name: str) -> Optional[dict[str, Any]]:
        """Retorna configuração de um domínio."""
        return self.classification_rules.get("domains", {}).get(domain_name)

    def update_domain_rules(
        self,
        domain_name: str,
        keywords: Optional[list[str]] = None,
        patterns: Optional[list[str]] = None,
    ) -> bool:
        """Atualiza regras de um domínio em runtime.

        Args:
            domain_name: Nome do domínio
            keywords: Keywords para adicionar
            patterns: Patterns para adicionar

        Returns:
            True se atualizado com sucesso
        """
        if domain_name not in self.classification_rules.get("domains", {}):
            return False

        domain_config = self.classification_rules["domains"][domain_name]

        if keywords:
            domain_config.setdefault("keywords", []).extend(keywords)

        if patterns:
            domain_config.setdefault("patterns", []).extend(patterns)

        # Re-preparar estruturas
        self._prepare_optimized_structures()
        return True

    def _get_default_classification_rules(self) -> dict[str, Any]:
        """Retorna regras de classificação padrão."""
        return {
            "domains": {
                "BUSINESS": {
                    "keywords": [
                        "negócio",
                        "venda",
                        "vendas",
                        "cliente",
                        "clientes",
                        "relatório",
                        "dashboard",
                        "analytics",
                        "métrica",
                        "kpi",
                        "receita",
                        "faturamento",
                        "lucro",
                        "marketing",
                        "campanha",
                        "conversão",
                        "funil",
                        "lead",
                        "prospect",
                        "business",
                        "sales",
                        "customer",
                        "report",
                        "revenue",
                        "profit",
                        "campaign",
                        "conversion",
                        "funnel",
                    ],
                    "patterns": [
                        r"\b(relatório|dashboard|report)\b",
                        r"\b(vendas?|sales|selling)\b",
                        r"\b(clientes?|customers?|client)\b",
                        r"\b(receita|revenue|income)\b",
                        r"\b(marketing|campanha|campaign)\b",
                    ],
                    "subcategories": {
                        "reporting": [
                            "relatório",
                            "dashboard",
                            "report",
                            "analytics",
                            "métrica",
                            "kpi",
                        ],
                        "sales": ["venda", "vendas", "sales", "selling", "conversão", "conversion"],
                        "customer": [
                            "cliente",
                            "clientes",
                            "customer",
                            "client",
                            "prospect",
                            "lead",
                        ],
                        "marketing": ["marketing", "campanha", "campaign", "anúncio", "ad"],
                    },
                },
                "TECHNICAL": {
                    "keywords": [
                        "api",
                        "bug",
                        "erro",
                        "performance",
                        "otimizar",
                        "código",
                        "função",
                        "método",
                        "classe",
                        "algoritmo",
                        "database",
                        "query",
                        "sql",
                        "implementar",
                        "desenvolver",
                        "programar",
                        "debug",
                        "teste",
                        "integração",
                        "code",
                        "function",
                        "method",
                        "class",
                        "algorithm",
                        "develop",
                        "implement",
                        "programming",
                        "debugging",
                        "testing",
                        "system",
                        "technical",
                        "development",
                    ],
                    "patterns": [
                        r"\b(api|rest|graphql|grpc)\b",
                        r"\b(bug|erro|error|issue|falha)\b",
                        r"\b(performance|otimizar|optimize|slow|lento)\b",
                        r"\b(código|code|function|método|class)\b",
                        r"\b(database|sql|query|banco)\b",
                    ],
                    "subcategories": {
                        "bug": ["bug", "erro", "error", "issue", "falha", "problem"],
                        "performance": [
                            "performance",
                            "otimizar",
                            "optimize",
                            "slow",
                            "lento",
                            "latency",
                        ],
                        "development": [
                            "código",
                            "code",
                            "desenvolver",
                            "develop",
                            "implementar",
                            "implement",
                        ],
                        "testing": ["teste", "test", "unit", "integration", "qa"],
                    },
                },
                "INFRASTRUCTURE": {
                    "keywords": [
                        "deploy",
                        "deployment",
                        "servidor",
                        "server",
                        "kubernetes",
                        "k8s",
                        "docker",
                        "container",
                        "pod",
                        "cluster",
                        "node",
                        "infra",
                        "infraestrutura",
                        "devops",
                        "pipeline",
                        "helm",
                        "terraform",
                        "ansible",
                        "infrastructure",
                        "orchestration",
                        "provisioning",
                        "scaling",
                        "monitoring",
                        "ci/cd",
                    ],
                    "patterns": [
                        r"\b(deploy|deployment|release)\b",
                        r"\b(servidor|server|host|vm)\b",
                        r"\b(kubernetes|k8s|docker|container)\b",
                        r"\b(infra|infrastructure|devops)\b",
                        r"\b(ci/cd|pipeline|automation)\b",
                    ],
                    "subcategories": {
                        "deployment": ["deploy", "deployment", "release", "rollout"],
                        "containers": ["docker", "kubernetes", "k8s", "container", "pod"],
                        "servers": ["servidor", "server", "host", "vm", "node"],
                        "automation": ["ci/cd", "pipeline", "terraform", "ansible", "automation"],
                    },
                },
                "SECURITY": {
                    "keywords": [
                        "segurança",
                        "security",
                        "autenticação",
                        "authentication",
                        "autorização",
                        "authorization",
                        "permissão",
                        "permission",
                        "acesso",
                        "access",
                        "token",
                        "jwt",
                        "oauth",
                        "saml",
                        "ssl",
                        "tls",
                        "criptografia",
                        "encryption",
                        "vulnerabilidade",
                        "vulnerability",
                        "firewall",
                        "iam",
                        "auth",
                        "login",
                        "credential",
                        "certificate",
                        "key",
                    ],
                    "patterns": [
                        r"\b(segurança|security|secure)\b",
                        r"\b(autenticação|authentication|auth|login)\b",
                        r"\b(autorização|authorization|permission|acesso)\b",
                        r"\b(criptografia|encryption|crypto|ssl|tls)\b",
                        r"\b(vulnerabilidade|vulnerability|exploit|cve)\b",
                    ],
                    "subcategories": {
                        "authentication": [
                            "autenticação",
                            "authentication",
                            "login",
                            "auth",
                            "credential",
                        ],
                        "authorization": [
                            "autorização",
                            "authorization",
                            "permission",
                            "acesso",
                            "access",
                            "iam",
                        ],
                        "encryption": [
                            "criptografia",
                            "encryption",
                            "ssl",
                            "tls",
                            "certificate",
                            "key",
                        ],
                        "security": [
                            "segurança",
                            "security",
                            "vulnerabilidade",
                            "vulnerability",
                            "firewall",
                        ],
                    },
                },
            },
            "quality_thresholds": {
                "min_text_length": 3,
                "max_text_length": 10000,
                "min_words": 2,
                "spam_patterns": [
                    r"^(.)\1{10,}$",
                    r"^\d+$",
                    r"^[!@#$%^&*()]+$",
                ],
            },
            "confidence_boosters": {
                "text_length_boost": {"threshold": 50, "boost": 0.05},
                "entity_presence_boost": {"threshold": 2, "boost": 0.05},
                "multiple_subcategories_boost": {"threshold": 2, "boost": 0.05},
                "context_role_match_boost": {"boost": 0.10},
            },
        }

    def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas do engine."""
        return {
            "domains_supported": len(self.classification_rules.get("domains", {})),
            "domains": list(self.classification_rules.get("domains", {}).keys()),
            "patterns_compiled": sum(len(p) for p in self.compiled_patterns.values()),
            "keyword_sets": len(self.keyword_sets),
        }
