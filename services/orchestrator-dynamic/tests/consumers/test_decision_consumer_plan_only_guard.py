"""Guard plan-only em ``_requires_generate_capability`` (remediação Task 5 / CR-003).

Spec: docs/specs/2026-06-26-extrair-capacidade-generate — auditoria de qualidade
da Fase 4 (Task 5). A auditoria detetou que, sem guard explícito, a autoridade
única ``_requires_generate_capability("J1_PLAN_ONLY", "generation")`` devolvia
``True``: ``_select_workflow_class_by_journey("J1_PLAN_ONLY")`` é ``None`` e o
fallback compat (``workflow_class is None and workflow_type == "generation"``)
classificava-o como geração. Em produção o erro nunca se manifestava (os call
sites verificam ``_is_plan_only`` antes), mas o contrato da função era
auto-inconsistente. Este teste congela o contrato corrigido: plan-only NUNCA
requer execução de geração, independentemente do ``workflow_type``.
"""

from src.consumers.decision_consumer import _requires_generate_capability


class TestPlanOnlyNeverRequiresGeneration:
    """J1_PLAN_ONLY não executa — nem por fallback de workflow_type."""

    def test_plan_only_with_generation_workflow_type_is_false(self):
        # O caso exato que a auditoria expôs: antes do guard devolvia True.
        assert _requires_generate_capability("J1_PLAN_ONLY", "generation") is False

    def test_plan_only_with_orchestration_workflow_type_is_false(self):
        assert _requires_generate_capability("J1_PLAN_ONLY", "orchestration") is False

    def test_plan_only_with_empty_workflow_type_is_false(self):
        assert _requires_generate_capability("J1_PLAN_ONLY", "") is False
