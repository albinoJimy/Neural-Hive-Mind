"""
Gerador de código Temporal Python para workflows.

Gera código Python para Temporal a partir de definições de workflow
(Conditional, Parallel, Compensation).
"""

from dataclasses import dataclass
from typing import Any

from src.workflows.compensation_workflow import (
    CompensationStep,
    CompensationWorkflow,
)
from src.workflows.conditional_workflow import ConditionalWorkflow
from src.workflows.parallel_workflow import JoinStrategy, ParallelTask, ParallelWorkflow


@dataclass
class GeneratedCode:
    """Resultado da geração de código."""

    workflow_type: str
    code: str
    imports: set[str]
    dependencies: set[str]
    filename: str

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário."""
        return {
            "workflow_type": self.workflow_type,
            "code": self.code,
            "imports": list(self.imports),
            "dependencies": list(self.dependencies),
            "filename": self.filename,
        }


class TemporalGenerator:
    """Gerador de código Temporal Python.

    Converte definições de workflow em código Python compatível com
    Temporal SDK, incluindo decorators, activities e workflows.
    """

    def __init__(self, package_name: str = "workflows"):
        """Inicializa o gerador.

        Args:
            package_name: Nome do pacote para imports
        """
        self.package_name = package_name
        self._base_imports = {
            "from datetime import timedelta",
            "from typing import Any, Dict, List, Optional",
            "from temporalio import workflow, activity",
            "from temporalio.common import RetryPolicy",
            "from temporalio.exceptions import ApplicationError",
        }

    def generate_conditional_workflow(self, wf: ConditionalWorkflow) -> GeneratedCode:
        """Gera código Temporal para workflow condicional.

        Args:
            wf: ConditionalWorkflow a ser gerado

        Returns:
            GeneratedCode com o Python gerado
        """
        # Importações específicas
        imports = self._base_imports.copy()

        # Header do workflow
        code = f'''"""Workflow {wf.name} gerado automaticamente."""

{self._format_imports(imports)}

@workflow.defn
class {self._to_pascal_case(wf.name)}Workflow:
    """Workflow condicional: {wf.description}."""

    @workflow.run
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Executa workflow condicional."""

        # Avaliar condições e executar branch selecionado
        branch_name = self._evaluate_branch(input_data)

        workflow.logger.info(f"Branch selecionado: {{branch_name}}")

        result = await self._execute_branch(branch_name, input_data)
        return {{"branch": branch_name, "result": result}}

    def _evaluate_branch(self, context: Dict[str, Any]) -> str:
        """Avalia contexto e retorna nome do branch."""
'''

        # Gerar código de avaliação de branches
        for i, branch in enumerate(wf.branches):
            i == len(wf.branches) - 1

            if branch.condition:
                # Branch com condição
                condition_code = self._generate_condition_check(branch.condition)
                code += f'''
        # Branch: {branch.name}
        if {condition_code}:
            return "{branch.name}"'''
            else:
                # Branch else/default
                code += f'''
        # Branch: {branch.name} (default)
        return "{branch.name}"'''

        # Método _execute_branch
        code += '''

    async def _execute_branch(
        self, branch_name: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executa atividades do branch selecionado."""

'''

        # Gerar switch case para branches
        code += "        match branch_name:\n"
        for branch in wf.branches:
            code += f"""
            case "{branch.name}":
"""
            if branch.activities:
                for j, act in enumerate(branch.activities):
                    act_name = act.get("name", f"activity_{j}")
                    code += f"""                # {act.get("type", "unknown")}: {act_name}
                result = await workflow.execute_activity(
                    "{act.get('type', 'activity')}",
                    {self._format_activity_args(act)},
                    start_to_close_timeout=timedelta(seconds={act.get('timeout', 300)}),
                )
"""
            else:
                code += """                # Sem atividades
                result = None
"""
            code += "                return result\n\n"

        code += """            case _:
                raise ApplicationError(f"Branch desconhecido: {branch_name}")
"""

        return GeneratedCode(
            workflow_type="conditional",
            code=code,
            imports=imports,
            dependencies={"temporal"},
            filename=f"{wf.name}_workflow.py",
        )

    def generate_parallel_workflow(self, wf: ParallelWorkflow) -> GeneratedCode:
        """Gera código Temporal para workflow paralelo.

        Args:
            wf: ParallelWorkflow a ser gerado

        Returns:
            GeneratedCode com o Python gerado
        """
        imports = self._base_imports.copy()
        imports.add("import asyncio")

        # Header
        code = f'''"""Workflow {wf.name} gerado automaticamente."""

{self._format_imports(imports)}

@workflow.defn
class {self._to_pascal_case(wf.name)}Workflow:
    """Workflow paralelo: {wf.description}."""

    def __init__(self):
        self._completed_tasks: List[str] = []
        self._results: Dict[str, Any] = {{}}

    @workflow.run
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Executa workflow paralelo com fan-out/fan-in."""

        # Executar tarefas em ordem de dependências
        batches = self._get_execution_batches()
        all_results = {{}}

        for batch_num, batch in enumerate(batches):
            workflow.logger.info(
                f"Executando batch {{batch_num + 1}}/{{len(batches)}}: {{batch}}"
            )

            # Executar tarefas do batch em paralelo
            batch_results = await self._execute_batch(batch, input_data)
            all_results.update(batch_results)

            # Atualizar tarefas completadas
            self._completed_tasks.extend(batch)

        # Aplicar estratégia de join
        final_result = self._apply_join_strategy(all_results)
        return final_result

    def _get_execution_batches(self) -> List[List[str]]:
        """Calcula batches de execução baseado em dependências."""
'''

        # Gerar código de determinação de batches
        execution_order = wf.get_execution_order()
        code += "        return [\n"
        for batch in execution_order:
            code += f"            {batch},  # Batch {execution_order.index(batch) + 1}\n"
        code += "        ]\n"

        # Método _execute_batch
        code += '''
    async def _execute_batch(
        self, task_ids: List[str], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executa lista de tarefas em paralelo."""

        # Criar coroutines para cada tarefa
        tasks = []
        for task_id in task_ids:
            task = self._get_task(task_id)
            if task:
                tasks.append(self._execute_task(task, context))

        # Executar em paralelo
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Processar resultados
        return self._process_results(task_ids, results)

    async def _execute_task(
        self, task_data: Dict[str, Any], context: Dict[str, Any]
    ) -> tuple[str, Any]:
        """Executa uma tarefa individual."""

        task_id = task_data["task_id"]
        activity_type = task_data["activity"]["type"]

        workflow.logger.info(f"Executando tarefa: {task_id}")

        try:
            result = await workflow.execute_activity(
                activity_type,
                task_data["activity"],
                start_to_close_timeout=timedelta(seconds=task_data.get("timeout", 300)),
            )
            return (task_id, result)
        except Exception as e:
            workflow.logger.error(f"Erro na tarefa {task_id}: {e}")
            return (task_id, {{"error": str(e)}})

    def _process_results(
        self, task_ids: List[str], results: List[tuple[str, Any]]
    ) -> Dict[str, Any]:
        """Processa resultados de um batch."""

        return dict(results)

    def _get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retorna dados de uma tarefa por ID."""

'''

        # Mapeamento de tarefas
        for task in wf.tasks:
            code += f"""        if task_id == "{task.task_id}":
            return {self._format_task_dict(task)}

"""
        code += "        return None\n"

        # Método _apply_join_strategy
        code += f'''
    def _apply_join_strategy(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Aplica estratégia de join/fan-in."""

        strategy = "{wf.join_config.strategy.value}"

        match strategy:
            case "{JoinStrategy.WAIT_ALL}":
                return {{"all_results": results}}
            case "{JoinStrategy.WAIT_FIRST}":
                # Retornar primeiro resultado não-erro
                for task_id, result in results.items():
                    if isinstance(result, dict) and "error" not in result:
                        return {{"first_success": result}}
                return {{"first_success": None}}
            case "{JoinStrategy.WAIT_MAJORITY}":
                success_count = sum(
                    1 for r in results.values()
                    if isinstance(r, dict) and "error" not in r
                )
                return {{"results": results, "success_count": success_count}}
            case "{JoinStrategy.WAIT_N}":
                return {{"results": results, "n_value": {wf.join_config.n_value}}}
            case "{JoinStrategy.ANY_SUCCESS}":
                for task_id, result in results.items():
                    if isinstance(result, dict) and "error" not in result:
                        return {{"any_success": result}}
                return {{"any_success": None}}
            case _:
                return {{"results": results}}
'''

        return GeneratedCode(
            workflow_type="parallel",
            code=code,
            imports=imports,
            dependencies={"temporal"},
            filename=f"{wf.name}_workflow.py",
        )

    def generate_compensation_workflow(self, wf: CompensationWorkflow) -> GeneratedCode:
        """Gera código Temporal para workflow com compensação (Saga).

        Args:
            wf: CompensationWorkflow a ser gerado

        Returns:
            GeneratedCode com o Python gerado
        """
        imports = self._base_imports.copy()

        # Header
        code = f'''"""Workflow {wf.name} gerado automaticamente com Saga Pattern."""

{self._format_imports(imports)}

@workflow.defn
class {self._to_pascal_case(wf.name)}Workflow:
    """Workflow com compensação: {wf.description}."""

    def __init__(self):
        self._completed_steps: List[str] = []
        self._compensation_triggered = False
        self._saga_state: Optional[Dict[str, Any]] = None

    @workflow.run
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Executa workflow Saga com compensação."""

        self._saga_state = {{
            "saga_id": workflow.info().workflow_id,
            "status": "running",
            "completed_steps": [],
        }}

        try:
            # Executar passos em sequência
            for step in self._get_steps():
                await self._execute_step(step, input_data)
                self._completed_steps.append(step["step_id"])
                self._saga_state["completed_steps"] = self._completed_steps.copy()

            self._saga_state["status"] = "completed"
            return {{
                "status": "completed",
                "saga_id": self._saga_state["saga_id"],
                "completed_steps": self._completed_steps,
            }}

        except Exception as e:
            workflow.logger.error(f"Erro no workflow: {{e}}")

            if {str(wf.auto_compensate).lower()}:
                await self._compensate(input_data)

            self._saga_state["status"] = "failed"
            self._saga_state["error"] = str(e)

            raise ApplicationError(
                f"Workflow falhou: {{e}}",
                type="WorkflowError",
                details={{"compensated": self._compensation_triggered}}
            )

    async def _compensate(self, context: Dict[str, Any]) -> None:
        """Executa compensação em ordem reversa."""

        self._compensation_triggered = True
        workflow.logger.warning("Iniciando compensação (Saga rollback)")

        compensation_steps = self._get_compensation_order()

        for step_id in compensation_steps:
            if step_id not in self._completed_steps:
                continue  # Pular passos não executados

            step = self._get_step(step_id)
            if not step:
                continue

            try:
                await self._execute_compensation(step, context)
                workflow.logger.info(f"Compensação executada: {{step_id}}")
            except Exception as e:
                workflow.logger.error(f"Erro na compensação de {{step_id}}: {{e}}")
                # Continuar compensação mesmo com erro

    async def _execute_step(
        self, step: Dict[str, Any], context: Dict[str, Any]
    ) -> Any:
        """Executa um passo do workflow."""

        step_id = step["step_id"]
        activity_type = step["original_activity"]["type"]

        workflow.logger.info(f"Executando passo: {{step_id}}")

        result = await workflow.execute_activity(
            activity_type,
            step["original_activity"],
            start_to_close_timeout=timedelta(seconds=step.get("timeout", 300)),
        )

        return result

    async def _execute_compensation(
        self, step: Dict[str, Any], context: Dict[str, Any]
    ) -> Any:
        """Executa atividade de compensação."""

        step_id = step["step_id"]
        activity_type = step["compensation_activity"]["type"]

        result = await workflow.execute_activity(
            activity_type,
            step["compensation_activity"],
            start_to_close_timeout=timedelta(seconds=step.get("timeout", 300)),
        )

        return result

    def _get_steps(self) -> List[Dict[str, Any]]:
        """Retorna todos os passos do workflow."""

'''

        # Lista de passos
        for i, step in enumerate(wf.steps):
            code += f"""        # Passo {i + 1}: {step.name}
        {self._format_step_dict(step)}
"""

        code += '''
    def _get_step(self, step_id: str) -> Optional[Dict[str, Any]]:
        """Retorna um passo específico por ID."""

'''

        # Mapeamento _get_step
        for step in wf.steps:
            code += f"""        if step_id == "{step.step_id}":
            return {self._format_step_dict(step)}

"""
        code += "        return None\n"

        # Método _get_compensation_order
        code += '''
    def _get_compensation_order(self) -> List[str]:
        """Retorna ordem de compensação (inverso da execução)."""

'''

        for i, step_id in enumerate(wf.get_compensation_order()):
            code += f'        "{step_id}",  # {i + 1}\n'

        code += "    ]\n"

        return GeneratedCode(
            workflow_type="compensation",
            code=code,
            imports=imports,
            dependencies={"temporal"},
            filename=f"{wf.name}_workflow.py",
        )

    def _format_imports(self, imports: set[str]) -> str:
        """Formata bloco de imports."""
        return "\n".join(sorted(imports))

    def _to_pascal_case(self, snake_str: str) -> str:
        """Converte snake_case para PascalCase."""
        return "".join(word.capitalize() for word in snake_str.split("_"))

    def _generate_condition_check(self, condition) -> str:
        """Gera código Python para verificar condição."""
        field_var = f"context.get('{condition.field}')"

        match condition.operator:
            case "eq":
                return f"{field_var} == {self._format_value(condition.value)}"
            case "ne":
                return f"{field_var} != {self._format_value(condition.value)}"
            case "gt":
                return f"{field_var} > {self._format_value(condition.value)}"
            case "gte":
                return f"{field_var} >= {self._format_value(condition.value)}"
            case "lt":
                return f"{field_var} < {self._format_value(condition.value)}"
            case "lte":
                return f"{field_var} <= {self._format_value(condition.value)}"
            case "in":
                return f"{field_var} in {self._format_value(condition.value)}"
            case "nin":
                return f"{field_var} not in {self._format_value(condition.value)}"
            case "contains":
                return f"{self._format_value(condition.value)} in {field_var}"
            case "starts_with":
                return f"str({field_var}).startswith({self._format_value(condition.value)})"
            case "ends_with":
                return f"str({field_var}).endswith({self._format_value(condition.value)})"
            case _:
                return "True"

    def _format_value(self, value: Any) -> str:
        """Formata valor para código Python."""
        if isinstance(value, str):
            return f'"{value}"'
        if isinstance(value, bool):
            return "True" if value else "False"
        if isinstance(value, (list, dict)):
            import json

            return json.dumps(value)
        return str(value)

    def _format_activity_args(self, activity: dict[str, Any]) -> str:
        """Formata argumentos de atividade."""
        import json

        return json.dumps(activity, indent=6)[1:-1]  # Remove chaves externas

    def _format_task_dict(self, task: ParallelTask) -> str:
        """Formata ParallelTask como dicionário Python."""
        return f"""{{
            "task_id": "{task.task_id}",
            "name": "{task.name}",
            "activity": {self._format_value(task.activity)},
            "timeout": {task.timeout_seconds},
        }}"""

    def _format_step_dict(self, step: CompensationStep) -> str:
        """Formata CompensationStep como dicionário Python."""
        return f"""{{
            "step_id": "{step.step_id}",
            "name": "{step.name}",
            "original_activity": {self._format_value(step.original_activity)},
            "compensation_activity": {self._format_value(step.compensation_activity)},
            "timeout": {step.timeout_seconds},
        }}"""

    def generate_all(
        self,
        conditional_workflows: list[ConditionalWorkflow] | None = None,
        parallel_workflows: list[ParallelWorkflow] | None = None,
        compensation_workflows: list[CompensationWorkflow] | None = None,
    ) -> list[GeneratedCode]:
        """Gera código para múltiplos workflows.

        Args:
            conditional_workflows: Lista de workflows condicionais
            parallel_workflows: Lista de workflows paralelos
            compensation_workflows: Lista de workflows com compensação

        Returns:
            Lista de GeneratedCode
        """
        results = []

        for wf in conditional_workflows or []:
            results.append(self.generate_conditional_workflow(wf))

        for wf in parallel_workflows or []:
            results.append(self.generate_parallel_workflow(wf))

        for wf in compensation_workflows or []:
            results.append(self.generate_compensation_workflow(wf))

        return results
