"""
Testes da Task 7 (lado STE) — geração de data-flow semântico para transform.

DoD do lado STE: uma task transform COM dependências passa a gerar `input_ref`
(não None) + `operations` não-vazias, em vez do no-op eterno
`{"input_data": None, "operations": []}`.

Transform SEM dependências mantém o comportamento atual (input_data None).

NÃO modifica testes existentes (contrato). Ficheiro NOVO.
"""

from src.services.decomposition_templates import DecompositionTemplates, TaskTemplate


def _templates():
    return DecompositionTemplates()


class TestBuildTaskParametersTransform:
    def test_transform_com_dependencias_gera_input_ref_e_operations(self):
        templates = _templates()
        task_template = TaskTemplate(
            id="aggregate",
            task_type="transform",
            description_template="Transformar {subject}",
            semantic_domain="quality",
            dependencies=["inventory"],
        )

        params = templates._build_task_parameters(
            task_template,
            subject="kubernetes",
            target="relatorio",
            entities=["cluster"],
            intent_text="analisar kubernetes",
        )

        assert params.get("input_ref") not in (None, "")
        assert params.get("operations")  # lista não-vazia
        # mantém subject/target/entities
        assert params["subject"] == "kubernetes"
        assert params["target"] == "relatorio"
        assert params["entities"] == ["cluster"]

    def test_transform_sem_dependencias_mantem_noop(self):
        templates = _templates()
        task_template = TaskTemplate(
            id="standalone",
            task_type="transform",
            description_template="Transformar {subject}",
            semantic_domain="quality",
            dependencies=[],
        )

        params = templates._build_task_parameters(
            task_template,
            subject="kubernetes",
            target="relatorio",
            entities=[],
            intent_text="analisar kubernetes",
        )

        assert params.get("input_data") is None
        assert params.get("operations") == []
        assert params.get("input_ref") is None

    def test_input_ref_formato_generico_dep_output(self):
        templates = _templates()
        task_template = TaskTemplate(
            id="aggregate",
            task_type="transform",
            description_template="x",
            semantic_domain="quality",
            dependencies=["inventory"],
        )

        params = templates._build_task_parameters(task_template, "sap", "out", [], "intent")

        # formato genérico resolvido pelo executor contra dependency_outputs
        assert params["input_ref"].startswith("${dep.output.")
