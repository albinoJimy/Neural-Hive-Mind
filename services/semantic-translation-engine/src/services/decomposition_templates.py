"""
DecompositionTemplates - Templates de decomposição por tipo de intent.

Define estruturas de tasks para cada tipo de intent, garantindo:
1. Cobertura de múltiplos domínios semânticos
2. DAG bem formado com dependências claras
3. Tasks atômicas e verificáveis
"""

import structlog
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

from src.services.intent_classifier import IntentType, IntentClassification
from src.models.cognitive_plan import TaskNode

logger = structlog.get_logger(__name__)


@dataclass
class TaskTemplate:
    """Template de uma task individual."""
    id: str  # ID relativo dentro do template (ex: "inventory", "requirements")
    task_type: str  # Tipo da task (query, transform, validate, etc.)
    description_template: str  # Template com placeholders {subject}, {target}, etc.
    semantic_domain: str  # Domínio semântico principal (security, architecture, etc.)
    dependencies: List[str] = field(default_factory=list)  # IDs das tasks dependentes
    estimated_duration_ms: int = 500
    required_capabilities: List[str] = field(default_factory=list)
    is_parallelizable: bool = True


@dataclass
class DecompositionTemplate:
    """Template completo de decomposição para um tipo de intent."""
    intent_type: IntentType
    name: str
    description: str
    tasks: List[TaskTemplate]
    parallel_groups: List[List[str]] = field(default_factory=list)  # Grupos de tasks paralelas


class DecompositionTemplates:
    """
    Biblioteca de templates de decomposição.

    Cada template define:
    - Estrutura de tasks para o tipo de intent
    - Dependências entre tasks
    - Domínios semânticos cobertos
    - Capacidades requeridas
    """

    # Templates organizados por tipo de intent
    TEMPLATES: Dict[IntentType, DecompositionTemplate] = {}

    @classmethod
    def _init_templates(cls):
        """Inicializa todos os templates."""
        if cls.TEMPLATES:
            return  # Já inicializado

        # ========================================
        # VIABILITY_ANALYSIS Template
        # ========================================
        cls.TEMPLATES[IntentType.VIABILITY_ANALYSIS] = DecompositionTemplate(
            intent_type=IntentType.VIABILITY_ANALYSIS,
            name="Análise de Viabilidade",
            description="Template para análise de viabilidade técnica completa",
            tasks=[
                TaskTemplate(
                    id="inventory",
                    task_type="query",
                    description_template="Inventariar sistema atual de {subject} - mapear componentes, endpoints e integrações existentes",
                    semantic_domain="architecture",
                    dependencies=[],
                    estimated_duration_ms=800,
                    required_capabilities=["read", "analyze"]
                ),
                TaskTemplate(
                    id="requirements",
                    task_type="query",
                    description_template="Definir requisitos técnicos para {target} - especificar funcionalidades, padrões e constraints",
                    semantic_domain="architecture",
                    dependencies=[],
                    estimated_duration_ms=600,
                    required_capabilities=["read", "analyze"]
                ),
                TaskTemplate(
                    id="dependencies",
                    task_type="query",
                    description_template="Mapear dependências do sistema de {subject} - identificar serviços, APIs e integrações afetadas",
                    semantic_domain="architecture",
                    dependencies=[],
                    estimated_duration_ms=700,
                    required_capabilities=["read", "analyze"]
                ),
                TaskTemplate(
                    id="security_impact",
                    task_type="validate",
                    description_template="Avaliar impacto de segurança da migração para {target} - analisar vulnerabilidades, compliance e auditoria",
                    semantic_domain="security",
                    dependencies=["inventory", "requirements"],
                    estimated_duration_ms=900,
                    required_capabilities=["read", "analyze", "security"]
                ),
                TaskTemplate(
                    id="complexity",
                    task_type="query",
                    description_template="Analisar complexidade de integração de {target} - avaliar mudanças em APIs, SDKs e backward compatibility",
                    semantic_domain="architecture",
                    dependencies=["inventory", "requirements", "dependencies"],
                    estimated_duration_ms=800,
                    required_capabilities=["read", "analyze"]
                ),
                TaskTemplate(
                    id="effort",
                    task_type="query",
                    description_template="Estimar esforço de migração para {target} - calcular recursos, timeline e custos",
                    semantic_domain="quality",
                    dependencies=["complexity"],
                    estimated_duration_ms=600,
                    required_capabilities=["read", "analyze"]
                ),
                TaskTemplate(
                    id="risks",
                    task_type="validate",
                    description_template="Identificar riscos técnicos da migração para {target} - listar riscos e propor mitigações",
                    semantic_domain="security",
                    dependencies=["security_impact", "complexity"],
                    estimated_duration_ms=700,
                    required_capabilities=["read", "analyze", "security"]
                ),
                TaskTemplate(
                    id="report",
                    task_type="transform",
                    description_template="Gerar relatório de viabilidade para {target} - consolidar análise com recomendação final",
                    semantic_domain="quality",
                    dependencies=["effort", "risks"],
                    estimated_duration_ms=500,
                    required_capabilities=["write", "analyze"]
                )
            ],
            parallel_groups=[
                ["inventory", "requirements", "dependencies"],  # Grupo 1: paralelo
                ["security_impact", "complexity"],  # Grupo 2: após grupo 1
                ["effort", "risks"],  # Grupo 3: após grupo 2
            ]
        )

        # ========================================
        # MIGRATION Template
        # ========================================
        cls.TEMPLATES[IntentType.MIGRATION] = DecompositionTemplate(
            intent_type=IntentType.MIGRATION,
            name="Migração de Sistema",
            description="Template para migração de componentes ou sistemas",
            tasks=[
                TaskTemplate(
                    id="source_analysis",
                    task_type="query",
                    description_template="Analisar sistema fonte de {subject} - documentar estado atual e dependências",
                    semantic_domain="architecture",
                    dependencies=[],
                    estimated_duration_ms=800,
                    required_capabilities=["read", "analyze"]
                ),
                TaskTemplate(
                    id="target_spec",
                    task_type="query",
                    description_template="Especificar sistema alvo {target} - definir arquitetura e requisitos",
                    semantic_domain="architecture",
                    dependencies=[],
                    estimated_duration_ms=700,
                    required_capabilities=["read", "analyze"]
                ),
                TaskTemplate(
                    id="data_mapping",
                    task_type="transform",
                    description_template="Mapear dados de {subject} para {target} - definir transformações e validações",
                    semantic_domain="architecture",
                    dependencies=["source_analysis", "target_spec"],
                    estimated_duration_ms=900,
                    required_capabilities=["read", "analyze", "transform"]
                ),
                TaskTemplate(
                    id="security_validation",
                    task_type="validate",
                    description_template="Validar segurança da migração para {target} - verificar autenticação, autorização e criptografia",
                    semantic_domain="security",
                    dependencies=["target_spec"],
                    estimated_duration_ms=800,
                    required_capabilities=["read", "security"]
                ),
                TaskTemplate(
                    id="migration_plan",
                    task_type="transform",
                    description_template="Criar plano de migração para {target} - definir fases, rollback e validação",
                    semantic_domain="quality",
                    dependencies=["data_mapping", "security_validation"],
                    estimated_duration_ms=700,
                    required_capabilities=["write", "analyze"]
                ),
                TaskTemplate(
                    id="testing_strategy",
                    task_type="validate",
                    description_template="Definir estratégia de testes para migração de {subject} - testes de integração, carga e rollback",
                    semantic_domain="quality",
                    dependencies=["migration_plan"],
                    estimated_duration_ms=600,
                    required_capabilities=["read", "analyze"]
                ),
                TaskTemplate(
                    id="execution_checklist",
                    task_type="transform",
                    description_template="Gerar checklist de execução da migração para {target} - passos, verificações e contingências",
                    semantic_domain="quality",
                    dependencies=["testing_strategy"],
                    estimated_duration_ms=500,
                    required_capabilities=["write"]
                ),
                TaskTemplate(
                    id="rollback_plan",
                    task_type="transform",
                    description_template="Criar plano de rollback da migração de {subject} - procedimentos de reversão e validação",
                    semantic_domain="security",
                    dependencies=["migration_plan"],
                    estimated_duration_ms=600,
                    required_capabilities=["write", "analyze"]
                )
            ],
            parallel_groups=[
                ["source_analysis", "target_spec"],
                ["data_mapping", "security_validation"],
                ["testing_strategy", "rollback_plan"]
            ]
        )

        # ========================================
        # SECURITY_AUDIT Template
        # ========================================
        cls.TEMPLATES[IntentType.SECURITY_AUDIT] = DecompositionTemplate(
            intent_type=IntentType.SECURITY_AUDIT,
            name="Auditoria de Segurança",
            description="Template para auditoria de segurança completa",
            tasks=[
                TaskTemplate(
                    id="scope_definition",
                    task_type="query",
                    description_template="Definir escopo da auditoria de segurança de {subject} - sistemas, dados e perímetro",
                    semantic_domain="security",
                    dependencies=[],
                    estimated_duration_ms=500,
                    required_capabilities=["read", "security"]
                ),
                TaskTemplate(
                    id="vulnerability_scan",
                    task_type="validate",
                    description_template="Executar scan de vulnerabilidades em {subject} - identificar CVEs, configurações inseguras",
                    semantic_domain="security",
                    dependencies=["scope_definition"],
                    estimated_duration_ms=1200,
                    required_capabilities=["read", "security", "scan"]
                ),
                TaskTemplate(
                    id="auth_review",
                    task_type="validate",
                    description_template="Revisar autenticação e autorização de {subject} - políticas, tokens, sessões",
                    semantic_domain="security",
                    dependencies=["scope_definition"],
                    estimated_duration_ms=800,
                    required_capabilities=["read", "security"]
                ),
                TaskTemplate(
                    id="data_protection",
                    task_type="validate",
                    description_template="Avaliar proteção de dados em {subject} - criptografia, mascaramento, backup",
                    semantic_domain="security",
                    dependencies=["scope_definition"],
                    estimated_duration_ms=700,
                    required_capabilities=["read", "security"]
                ),
                TaskTemplate(
                    id="compliance_check",
                    task_type="validate",
                    description_template="Verificar compliance de {subject} - LGPD, SOC2, PCI-DSS conforme aplicável",
                    semantic_domain="security",
                    dependencies=["auth_review", "data_protection"],
                    estimated_duration_ms=900,
                    required_capabilities=["read", "security", "compliance"]
                ),
                TaskTemplate(
                    id="risk_assessment",
                    task_type="validate",
                    description_template="Avaliar riscos de segurança de {subject} - classificar por severidade e probabilidade",
                    semantic_domain="security",
                    dependencies=["vulnerability_scan", "compliance_check"],
                    estimated_duration_ms=800,
                    required_capabilities=["read", "analyze", "security"]
                ),
                TaskTemplate(
                    id="remediation_plan",
                    task_type="transform",
                    description_template="Criar plano de remediação para {subject} - priorizar correções e timeline",
                    semantic_domain="quality",
                    dependencies=["risk_assessment"],
                    estimated_duration_ms=600,
                    required_capabilities=["write", "security"]
                )
            ],
            parallel_groups=[
                ["vulnerability_scan", "auth_review", "data_protection"]
            ]
        )

        # ========================================
        # FEATURE_IMPLEMENTATION Template
        # ========================================
        cls.TEMPLATES[IntentType.FEATURE_IMPLEMENTATION] = DecompositionTemplate(
            intent_type=IntentType.FEATURE_IMPLEMENTATION,
            name="Implementação de Feature",
            description="Template para implementação de nova funcionalidade",
            tasks=[
                TaskTemplate(
                    id="requirements",
                    task_type="query",
                    description_template="Detalhar requisitos de {subject} - casos de uso, critérios de aceite",
                    semantic_domain="quality",
                    dependencies=[],
                    estimated_duration_ms=500,
                    required_capabilities=["read", "analyze"]
                ),
                TaskTemplate(
                    id="design",
                    task_type="transform",
                    description_template="Projetar arquitetura de {subject} - componentes, interfaces, fluxos",
                    semantic_domain="architecture",
                    dependencies=["requirements"],
                    estimated_duration_ms=700,
                    required_capabilities=["analyze", "write"]
                ),
                TaskTemplate(
                    id="implementation",
                    task_type="transform",
                    description_template="Implementar {subject} - código, configurações, migrações",
                    semantic_domain="architecture",
                    dependencies=["design"],
                    estimated_duration_ms=2000,
                    required_capabilities=["write", "code"]
                ),
                TaskTemplate(
                    id="testing",
                    task_type="validate",
                    description_template="Testar {subject} - testes unitários, integração, e2e",
                    semantic_domain="quality",
                    dependencies=["implementation"],
                    estimated_duration_ms=1000,
                    required_capabilities=["read", "test"]
                ),
                TaskTemplate(
                    id="documentation",
                    task_type="transform",
                    description_template="Documentar {subject} - API docs, README, changelog",
                    semantic_domain="quality",
                    dependencies=["implementation"],
                    estimated_duration_ms=400,
                    required_capabilities=["write"]
                )
            ],
            parallel_groups=[
                ["testing", "documentation"]
            ]
        )

        # ========================================
        # INFRASTRUCTURE_CHANGE Template
        # ========================================
        cls.TEMPLATES[IntentType.INFRASTRUCTURE_CHANGE] = DecompositionTemplate(
            intent_type=IntentType.INFRASTRUCTURE_CHANGE,
            name="Mudança de Infraestrutura",
            description="Template para mudanças de infraestrutura",
            tasks=[
                TaskTemplate(
                    id="current_state",
                    task_type="query",
                    description_template="Documentar estado atual da infraestrutura de {subject}",
                    semantic_domain="architecture",
                    dependencies=[],
                    estimated_duration_ms=600,
                    required_capabilities=["read", "analyze"]
                ),
                TaskTemplate(
                    id="target_architecture",
                    task_type="transform",
                    description_template="Projetar arquitetura alvo para {target} - recursos, topologia, sizing",
                    semantic_domain="architecture",
                    dependencies=["current_state"],
                    estimated_duration_ms=800,
                    required_capabilities=["analyze", "write"]
                ),
                TaskTemplate(
                    id="capacity_planning",
                    task_type="query",
                    description_template="Planejar capacidade para {target} - CPU, memória, storage, rede",
                    semantic_domain="performance",
                    dependencies=["target_architecture"],
                    estimated_duration_ms=600,
                    required_capabilities=["analyze"]
                ),
                TaskTemplate(
                    id="security_config",
                    task_type="validate",
                    description_template="Configurar segurança de {target} - firewalls, secrets, IAM",
                    semantic_domain="security",
                    dependencies=["target_architecture"],
                    estimated_duration_ms=700,
                    required_capabilities=["security", "write"]
                ),
                TaskTemplate(
                    id="provisioning",
                    task_type="transform",
                    description_template="Provisionar recursos para {target} - IaC, deployment, configuração",
                    semantic_domain="architecture",
                    dependencies=["capacity_planning", "security_config"],
                    estimated_duration_ms=1200,
                    required_capabilities=["write", "deploy"]
                ),
                TaskTemplate(
                    id="validation",
                    task_type="validate",
                    description_template="Validar infraestrutura de {target} - health checks, smoke tests",
                    semantic_domain="quality",
                    dependencies=["provisioning"],
                    estimated_duration_ms=500,
                    required_capabilities=["read", "test"]
                )
            ],
            parallel_groups=[
                ["capacity_planning", "security_config"]
            ]
        )

        # ========================================
        # GENERIC Template (fallback)
        # ========================================
        cls.TEMPLATES[IntentType.GENERIC] = DecompositionTemplate(
            intent_type=IntentType.GENERIC,
            name="Decomposição Genérica",
            description="Template genérico para intents não classificados",
            tasks=[
                TaskTemplate(
                    id="analysis",
                    task_type="query",
                    description_template="Analisar requisitos de {subject}",
                    semantic_domain="architecture",
                    dependencies=[],
                    estimated_duration_ms=500,
                    required_capabilities=["read", "analyze"]
                ),
                TaskTemplate(
                    id="planning",
                    task_type="transform",
                    description_template="Planejar execução de {subject}",
                    semantic_domain="quality",
                    dependencies=["analysis"],
                    estimated_duration_ms=400,
                    required_capabilities=["analyze", "write"]
                ),
                TaskTemplate(
                    id="execution",
                    task_type="transform",
                    description_template="Executar {subject}",
                    semantic_domain="architecture",
                    dependencies=["planning"],
                    estimated_duration_ms=1000,
                    required_capabilities=["write"]
                ),
                TaskTemplate(
                    id="validation",
                    task_type="validate",
                    description_template="Validar resultado de {subject}",
                    semantic_domain="quality",
                    dependencies=["execution"],
                    estimated_duration_ms=400,
                    required_capabilities=["read", "test"]
                )
            ],
            parallel_groups=[]
        )

        logger.info(
            "DecompositionTemplates initialized",
            num_templates=len(cls.TEMPLATES)
        )

    def __init__(self):
        """Inicializa templates."""
        self._init_templates()

    def get_template(self, intent_type: IntentType) -> DecompositionTemplate:
        """
        Retorna template para o tipo de intent.

        Args:
            intent_type: Tipo de intent classificado

        Returns:
            DecompositionTemplate correspondente
        """
        self._init_templates()
        return self.TEMPLATES.get(intent_type, self.TEMPLATES[IntentType.GENERIC])

    def generate_tasks(
        self,
        classification: IntentClassification,
        intent_text: str,
        entities: List[str],
        base_task_id: int = 0
    ) -> List[TaskNode]:
        """
        Gera TaskNodes a partir do template.

        Args:
            classification: Classificação do intent
            intent_text: Texto original do intent
            entities: Entidades extraídas do intent
            base_task_id: ID base para numeração das tasks

        Returns:
            Lista de TaskNode prontas para o DAG
        """
        template = self.get_template(classification.intent_type)

        # Extrair subject e target do intent
        subject, target = self._extract_subject_target(intent_text, entities)

        tasks = []
        id_mapping = {}  # Mapeia template_id -> task_id real

        for idx, task_template in enumerate(template.tasks):
            task_id = f"task_{base_task_id + idx}"
            id_mapping[task_template.id] = task_id

            # Preencher template da descrição
            description = task_template.description_template.format(
                subject=subject,
                target=target
            )

            # Mapear dependências para IDs reais
            dependencies = [
                id_mapping[dep_id]
                for dep_id in task_template.dependencies
                if dep_id in id_mapping
            ]

            task = TaskNode(
                task_id=task_id,
                task_type=task_template.task_type,
                description=description,
                dependencies=dependencies,
                estimated_duration_ms=task_template.estimated_duration_ms,
                required_capabilities=task_template.required_capabilities,
                parameters={
                    "subject": subject,
                    "target": target,
                    "entities": entities
                },
                metadata={
                    "template_id": task_template.id,
                    "semantic_domain": task_template.semantic_domain,
                    "intent_type": classification.intent_type.value,
                    "decomposition_method": "template_based",
                    "is_parallelizable": task_template.is_parallelizable
                }
            )

            tasks.append(task)

        logger.info(
            "Tasks generated from template",
            intent_type=classification.intent_type.value,
            template_name=template.name,
            num_tasks=len(tasks),
            subject=subject,
            target=target
        )

        return tasks

    def _extract_subject_target(
        self,
        intent_text: str,
        entities: List[str]
    ) -> tuple[str, str]:
        """
        Extrai subject e target do intent.

        Args:
            intent_text: Texto do intent
            entities: Entidades extraídas

        Returns:
            Tupla (subject, target)
        """
        # Heurística simples: procurar padrões comuns
        intent_lower = intent_text.lower()

        # Padrões de migração/transição
        migration_patterns = [
            ("de ", " para "),
            ("from ", " to "),
            ("migrar ", " para "),
            ("migrate ", " to "),
        ]

        for from_marker, to_marker in migration_patterns:
            if from_marker in intent_lower and to_marker in intent_lower:
                from_idx = intent_lower.find(from_marker)
                to_idx = intent_lower.find(to_marker)

                if from_idx < to_idx:
                    subject_start = from_idx + len(from_marker)
                    subject = intent_text[subject_start:to_idx].strip()
                    target = intent_text[to_idx + len(to_marker):].strip()

                    # Limpar pontuação final
                    target = target.rstrip('.,;:')

                    if subject and target:
                        return subject, target

        # Fallback: usar primeira entidade como subject, resto como target
        if entities:
            subject = entities[0]
            target = entities[1] if len(entities) > 1 else intent_text[:50]
        else:
            # Extrair substantivos principais do texto
            words = intent_text.split()
            subject = " ".join(words[:3]) if len(words) >= 3 else intent_text
            target = " ".join(words[3:6]) if len(words) >= 6 else subject

        return subject, target

    def get_semantic_coverage(self, intent_type: IntentType) -> Dict[str, int]:
        """
        Retorna cobertura de domínios semânticos para um tipo de intent.

        Args:
            intent_type: Tipo de intent

        Returns:
            Dicionário com contagem de tasks por domínio
        """
        template = self.get_template(intent_type)
        coverage = {}

        for task in template.tasks:
            domain = task.semantic_domain
            coverage[domain] = coverage.get(domain, 0) + 1

        return coverage
