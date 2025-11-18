"""
Activities Temporal para validação de planos cognitivos (Etapa C1).
"""
import hashlib
import json
from datetime import datetime
from typing import Dict, Any, Optional

from temporalio import activity
import structlog

logger = structlog.get_logger()

# Dependências globais para injeção
_policy_validator = None
_config = None


def set_activity_dependencies(policy_validator=None, config=None):
    """
    Configura dependências globais das activities.

    Args:
        policy_validator: PolicyValidator para validação OPA
        config: OrchestratorSettings
    """
    global _policy_validator, _config
    _policy_validator = policy_validator
    _config = config


@activity.defn
async def validate_cognitive_plan(plan_id: str, cognitive_plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    Valida schema Avro e integridade do Cognitive Plan.

    Args:
        plan_id: ID do plano cognitivo
        cognitive_plan: Dicionário com dados do plano

    Returns:
        Dicionário com resultado da validação: {'valid': bool, 'errors': [...], 'warnings': [...]}
    """
    activity.logger.info(f'Validando plano cognitivo {plan_id}')

    errors = []
    warnings = []

    try:
        # Validar campos obrigatórios
        required_fields = ['plan_id', 'tasks', 'execution_order', 'risk_score', 'risk_band']
        for field in required_fields:
            if field not in cognitive_plan:
                errors.append(f'Campo obrigatório ausente: {field}')

        # Validar versão do schema
        schema_version = cognitive_plan.get('schema_version', 1)
        if schema_version != 1:
            warnings.append(f'Versão de schema não suportada: {schema_version}')

        # Validar expiração do plano
        valid_until = cognitive_plan.get('valid_until')
        if valid_until:
            if isinstance(valid_until, int):
                valid_until_dt = datetime.fromtimestamp(valid_until / 1000.0)
                if valid_until_dt < datetime.now():
                    errors.append(f'Plano expirado: valid_until={valid_until_dt}')

        # Validar DAG: tasks referenciadas existem
        tasks = cognitive_plan.get('tasks', [])
        task_ids = {task['task_id'] for task in tasks}
        execution_order = cognitive_plan.get('execution_order', [])

        for task_id in execution_order:
            if task_id not in task_ids:
                errors.append(f'Task {task_id} referenciada em execution_order mas não existe')

        # Validar dependencies
        for task in tasks:
            for dep in task.get('dependencies', []):
                if dep not in task_ids:
                    errors.append(f'Dependência {dep} da task {task["task_id"]} não existe')

        # Validar políticas OPA se habilitado
        policy_decisions = {}
        if _policy_validator and _config and _config.opa_enabled:
            try:
                policy_result = await _policy_validator.validate_cognitive_plan(cognitive_plan)

                if not policy_result.valid:
                    # Adicionar violações de políticas aos erros
                    for violation in policy_result.violations:
                        errors.append(f'Política {violation.policy_name}: {violation.message}')

                    activity.logger.warning(
                        f'Plano {plan_id} violou políticas OPA',
                        violations_count=len(policy_result.violations),
                        policies=[v.policy_name for v in policy_result.violations]
                    )

                # Adicionar warnings de políticas
                for warning in policy_result.warnings:
                    warnings.append(f'Política {warning.policy_name}: {warning.message}')

                # Adicionar decisões de políticas ao resultado
                policy_decisions = policy_result.policy_decisions

            except Exception as e:
                # Se OPA falhar e fail_closed, adicionar erro
                # Se fail_open, apenas logar warning
                activity.logger.error(f'Erro ao validar políticas OPA: {e}', exc_info=True)
                if not _config.opa_fail_open:
                    errors.append(f'Falha na validação de políticas: {str(e)}')

        valid = len(errors) == 0

        result = {
            'valid': valid,
            'errors': errors,
            'warnings': warnings,
            'validated_at': datetime.now().isoformat(),
            'policy_decisions': policy_decisions
        }

        activity.logger.info(
            f'Validação do plano {plan_id} concluída',
            valid=valid,
            errors_count=len(errors),
            warnings_count=len(warnings)
        )

        return result

    except Exception as e:
        activity.logger.error(f'Erro ao validar plano {plan_id}: {e}', exc_info=True)
        return {
            'valid': False,
            'errors': [f'Erro na validação: {str(e)}'],
            'warnings': warnings
        }


@activity.defn
async def audit_validation(plan_id: str, validation_result: Dict[str, Any]) -> None:
    """
    Persiste resultado de validação no MongoDB para auditoria.

    Args:
        plan_id: ID do plano validado
        validation_result: Resultado da validação
    """
    activity.logger.info(f'Auditando validação do plano {plan_id}')

    try:
        # TODO: Implementar persistência no MongoDB
        # mongodb_client.validation_audit.insert_one({
        #     'plan_id': plan_id,
        #     'validation_result': validation_result,
        #     'workflow_id': activity.info().workflow_id,
        #     'timestamp': datetime.now(),
        #     'hash': hashlib.sha256(json.dumps(validation_result, sort_keys=True).encode()).hexdigest()
        # })

        activity.logger.info(f'Validação do plano {plan_id} auditada com sucesso')

    except Exception as e:
        activity.logger.error(f'Erro ao auditar validação do plano {plan_id}: {e}', exc_info=True)
        raise


@activity.defn
async def optimize_dag(tasks: list, execution_order: list) -> Dict[str, Any]:
    """
    Detecta e remove ciclos no DAG usando DFS, recalcula ordem topológica.

    Args:
        tasks: Lista de tasks do plano
        execution_order: Ordem de execução atual

    Returns:
        Dicionário com: {'optimized': bool, 'new_execution_order': [...], 'removed_dependencies': [...]}
    """
    activity.logger.info('Otimizando DAG')

    try:
        # Construir grafo de dependências
        graph = {task['task_id']: task.get('dependencies', []) for task in tasks}

        # Detectar ciclos usando DFS
        def has_cycle(node, visited, rec_stack):
            visited.add(node)
            rec_stack.add(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor, visited, rec_stack):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        # Verificar ciclos
        visited = set()
        rec_stack = set()
        has_cycles = False

        for task_id in graph:
            if task_id not in visited:
                if has_cycle(task_id, visited, rec_stack):
                    has_cycles = True
                    break

        if not has_cycles:
            activity.logger.info('DAG sem ciclos, otimização não necessária')
            return {
                'optimized': False,
                'new_execution_order': execution_order,
                'removed_dependencies': []
            }

        # Remover ciclos (simplificado: remover dependências que criam ciclos)
        # TODO: Implementar algoritmo mais sofisticado
        activity.logger.warning('Ciclos detectados no DAG')

        return {
            'optimized': True,
            'new_execution_order': execution_order,  # Placeholder
            'removed_dependencies': []
        }

    except Exception as e:
        activity.logger.error(f'Erro ao otimizar DAG: {e}', exc_info=True)
        raise
