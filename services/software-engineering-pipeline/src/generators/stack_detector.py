import re

from pydantic import BaseModel, ConfigDict, Field

from src.models.schemas import ProjectStack


class StackDetectionResult(BaseModel):
    """Resultado da detecção de stack."""

    model_config = ConfigDict(extra="forbid")

    detected: bool = Field(description="Se foi possível detectar a stack")
    stack: ProjectStack = Field(description="Informações da stack detectada")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confiança da detecção (0.0 a 1.0)",
    )


class StackDetector:
    """Detecta a stack tecnológica de um repositório."""

    PYTHON_INDICATORS = [
        (r"requirements\.txt", 1.0),
        (r"pyproject\.toml", 1.0),
        (r"setup\.py", 0.9),
        (r"Pipfile", 0.8),
        (r"\.py$", 0.5),
    ]

    NODE_INDICATORS = [
        (r"package\.json", 1.0),
        (r"yarn\.lock", 0.9),
        (r"package-lock\.json", 0.9),
        (r"\.js$", 0.3),
        (r"\.ts$", 0.3),
        (r"\.jsx$", 0.3),
        (r"\.tsx$", 0.3),
    ]

    JAVA_INDICATORS = [
        (r"pom\.xml", 1.0),
        (r"build\.gradle", 1.0),
        (r"\.java$", 0.5),
    ]

    GO_INDICATORS = [
        (r"go\.mod", 1.0),
        (r"go\.sum", 0.9),
        (r"\.go$", 0.5),
    ]

    DOCKER_INDICATORS = [
        (r"Dockerfile", 1.0),
        (r"\.dockerignore", 0.5),
    ]

    K8S_INDICATORS = [
        (r"deployment\.yaml", 0.9),
        (r"service\.yaml", 0.9),
        (r"helm/", 1.0),
        (r"k8s/", 0.9),
        (r"kubernetes/", 0.9),
    ]

    PACKAGE_MANAGER_MAP = {
        "python": "pip",
        "node": "npm",
        "java": "maven",
        "go": "go",
    }

    FRAMEWORK_PATTERNS = {
        "python": [
            (r"fastapi", "fastapi"),
            (r"django", "django"),
            (r"flask", "flask"),
            (r"tornado", "tornado"),
        ],
        "node": [
            (r"react", "react"),
            (r"next", "next.js"),
            (r"vue", "vue"),
            (r"express", "express"),
            (r"nest", "nestjs"),
        ],
    }

    def __init__(self, file_list: list[str], file_contents: dict[str, str] | None = None) -> None:
        self.file_list = file_list
        self.file_contents = file_contents or {}

    def detect(self) -> StackDetectionResult:
        """Detecta a stack do projeto.

        Returns:
            StackDetectionResult com informações detectadas
        """
        language, lang_confidence = self._detect_language()
        framework = self._detect_framework(language)

        has_dockerfile = any(
            re.search(p, f, re.IGNORECASE)
            for f in self.file_list
            for p, _ in self.DOCKER_INDICATORS
        )

        has_docker_compose = any("docker-compose" in f.lower() for f in self.file_list)

        has_helm_chart = any("helm" in f.lower() or "Chart.yaml" in f for f in self.file_list)

        kubernetes_manifests = any(
            any(re.search(p, f, re.IGNORECASE) for p, _ in self.K8S_INDICATORS)
            for f in self.file_list
        )

        stack = ProjectStack(
            language=language,
            framework=framework,
            package_manager=self._infer_package_manager(language),
            has_dockerfile=has_dockerfile,
            has_docker_compose=has_docker_compose,
            has_helm_chart=has_helm_chart,
            kubernetes_manifests=kubernetes_manifests,
        )

        return StackDetectionResult(
            detected=lang_confidence > 0.5,
            stack=stack,
            confidence=lang_confidence,
        )

    def _detect_language(self) -> tuple[str, float]:
        """Detecta a linguagem principal do projeto.

        Returns:
            Tupla (linguagem, confiança)
        """
        scores = {
            "python": self._score_indicators(self.PYTHON_INDICATORS),
            "node": self._score_indicators(self.NODE_INDICATORS),
            "java": self._score_indicators(self.JAVA_INDICATORS),
            "go": self._score_indicators(self.GO_INDICATORS),
        }

        top_language = max(scores, key=scores.get)
        return top_language, scores[top_language]

    def _score_indicators(self, indicators: list[tuple[str, float]]) -> float:
        """Calcula pontuação para uma lista de indicadores.

        Args:
            indicators: Lista de (padrão regex, peso)

        Returns:
            Pontuação total (limitada a 1.0)
        """
        total_score = 0.0
        for pattern, weight in indicators:
            for filename in self.file_list:
                if re.search(pattern, filename, re.IGNORECASE):
                    total_score += weight
        return min(total_score, 1.0)

    def _detect_framework(self, language: str) -> str | None:
        """Detecta o framework usado.

        Args:
            language: Linguagem detectada

        Returns:
            Nome do framework ou None
        """
        if language not in self.FRAMEWORK_PATTERNS:
            return None

        patterns = self.FRAMEWORK_PATTERNS[language]

        for pattern, framework in patterns:
            for filename in self.file_list:
                if re.search(pattern, filename, re.IGNORECASE):
                    return framework

        if language == "node" and "package.json" in self.file_list:
            content = self.file_contents.get("package.json", "")
            for pattern, framework in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    return framework

        if language == "python":
            for filename in ["requirements.txt", "pyproject.toml"]:
                if filename in self.file_list:
                    content = self.file_contents.get(filename, "")
                    for pattern, framework in patterns:
                        if re.search(pattern, content, re.IGNORECASE):
                            return framework

        return None

    def _infer_package_manager(self, language: str) -> str:
        """Infere o gerenciador de pacotes pela linguagem.

        Args:
            language: Linguagem detectada

        Returns:
            Nome do gerenciador de pacotes
        """
        managers = {
            "python": "pip",
            "node": "npm",
            "java": "maven",
            "go": "go",
        }
        return managers.get(language, "unknown")
