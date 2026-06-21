import asyncio
import json
import uuid
from datetime import datetime, timezone

UTC = timezone.utc  # type: ignore
from typing import Any, ClassVar

import structlog

from neural_hive_observability import get_tracer

logger = structlog.get_logger()


class TaskExecutionError(Exception):
    pass


class ExecutionEngine:
    """Orquestrador principal de execução de tarefas"""

    # TTL para deduplicação de tickets (7 dias - alinhado com retention Kafka)
    DEDUPLICATION_TTL_SECONDS = 604800
    # TTL para chave de processing (10 minutos - tempo máximo esperado de processamento)
    PROCESSING_TTL_SECONDS = 600

    def __init__(
        self,
        config,
        ticket_client,
        result_producer,
        dependency_coordinator,
        executor_registry,
        redis_client=None,
        metrics=None,
    ):
        self.config = config
        self.ticket_client = ticket_client
        self.result_producer = result_producer
        self.dependency_coordinator = dependency_coordinator
        self.executor_registry = executor_registry
        self.redis_client = redis_client
        self.metrics = metrics
        self.logger = logger.bind(service="execution_engine")

        # Rastrear tarefas em execução
        self.active_tasks: dict[str, asyncio.Task] = {}

        # Limitar concorrência
        self.task_semaphore = asyncio.Semaphore(config.max_concurrent_tasks)

    async def _is_duplicate_ticket(self, ticket_id: str) -> bool:
        """
        F2: Verificar se ticket já foi processado usando Redis com fallback MongoDB.

        Implementa deduplicação em duas fases:
        1. Verifica se já existe chave 'processed' (processamento concluído anteriormente)
        2. Verifica se já existe chave 'processing' (processamento em andamento)
        3. Se nenhuma existe, marca como 'processing' com TTL curto
        4. F2: Fallback para MongoDB se Redis indisponível

        Args:
            ticket_id: ID do execution ticket

        Returns:
            True se duplicata (já processado ou em processamento), False caso contrário
        """
        # Tenta Redis primeiro (mais rápido)
        if self.redis_client:
            try:
                processed_key = f"ticket:processed:{ticket_id}"
                processing_key = f"ticket:processing:{ticket_id}"

                # Fase 1: Verificar se já foi processado com sucesso
                if await self.redis_client.exists(processed_key):
                    self.logger.info(
                        "duplicate_ticket_detected",
                        ticket_id=ticket_id,
                        source="redis",
                        message="Ticket já foi processado com sucesso, ignorando",
                    )
                    if self.metrics and hasattr(self.metrics, "duplicates_detected_total"):
                        self.metrics.duplicates_detected_total.labels(
                            component="execution_engine", source="redis"
                        ).inc()
                    return True

                # Fase 2: Tentar marcar como em processamento (SETNX)
                is_new = await self.redis_client.set(
                    processing_key, "1", ex=self.PROCESSING_TTL_SECONDS, nx=True
                )

                if not is_new:
                    self.logger.info(
                        "ticket_already_processing",
                        ticket_id=ticket_id,
                        source="redis",
                        message="Ticket já está em processamento por outro worker, ignorando",
                    )
                    if self.metrics and hasattr(self.metrics, "duplicates_detected_total"):
                        self.metrics.duplicates_detected_total.labels(
                            component="execution_engine", source="redis"
                        ).inc()
                    return True

                self.logger.debug(
                    "ticket_marked_as_processing", ticket_id=ticket_id, source="redis"
                )
                return False

            except Exception as e:
                self.logger.warning(
                    "redis_deduplication_failed",
                    ticket_id=ticket_id,
                    error=str(e),
                    message="Tentando fallback MongoDB",
                )

        # F2: Fallback para MongoDB
        return await self._check_mongodb_dup(ticket_id)

    async def _check_mongodb_dup(self, ticket_id: str) -> bool:
        """
        F2: Verificar duplicata no MongoDB como fallback.

        Usa índice unique em ticket_id na coleção execution_tickets.

        Args:
            ticket_id: ID do execution ticket

        Returns:
            True se duplicata, False caso contrário
        """
        if not self.ticket_client:
            self.logger.warning(
                "F2_mongodb_client_unavailable",
                ticket_id=ticket_id,
                message="MongoDB client não disponível - fail-open, permitindo processamento",
            )
            return False

        try:
            # Verificar se ticket já existe no MongoDB
            existing_ticket = await self.ticket_client.get_ticket(ticket_id)

            if existing_ticket:
                # Ticket já existe - verificar status
                status = existing_ticket.get("status", "UNKNOWN")

                # Se status é COMPLETED ou FAILED, é duplicata
                if status in ("COMPLETED", "FAILED", "CANCELLED"):
                    self.logger.info(
                        "F2_duplicate_ticket_detected_mongodb",
                        ticket_id=ticket_id,
                        source="mongodb",
                        existing_status=status,
                        message="Ticket já processado no MongoDB, ignorando",
                    )
                    if self.metrics and hasattr(self.metrics, "duplicates_detected_total"):
                        self.metrics.duplicates_detected_total.labels(
                            component="execution_engine", source="mongodb"
                        ).inc()
                    return True

                # Se status é PENDING ou RUNNING, pode ser reprocessamento (permitir)
                self.logger.warning(
                    "F2_ticket_reprocessamento_mongodb",
                    ticket_id=ticket_id,
                    source="mongodb",
                    existing_status=status,
                    message="Ticket com status não-final no MongoDB - permitindo reprocessamento",
                )
                return False

            # Ticket não existe no MongoDB - marcar como processamento no MongoDB também
            # Usamos um campo 'processing_started_at' para tracking
            await self.ticket_client.update_ticket_status(
                ticket_id,
                "PENDING",
                metadata={
                    "processing_started_at": datetime.now(timezone.utc).isoformat(),
                    "dedup_method": "mongodb_fallback",
                },
            )

            self.logger.debug("F2_ticket_marked_processing_mongodb", ticket_id=ticket_id)
            return False

        except Exception as e:
            self.logger.exception(
                "F2_mongodb_deduplication_failed",
                ticket_id=ticket_id,
                error=str(e),
                error_type=type(e).__name__,
                message="Fail-open - permitindo processamento sem deduplicação",
            )
            # Fail-open: permitir processamento se ambos Redis e MongoDB falharem
            return False

    async def _mark_ticket_processed(self, ticket_id: str) -> None:
        """
        Marca ticket como processado com sucesso e remove chave de processing.
        F2: Tenta Redis primeiro, depois MongoDB como fallback.

        Args:
            ticket_id: ID do execution ticket
        """
        if not ticket_id:
            return

        # Tenta Redis primeiro
        if self.redis_client:
            try:
                processed_key = f"ticket:processed:{ticket_id}"
                processing_key = f"ticket:processing:{ticket_id}"

                # Marcar como processado com TTL longo
                await self.redis_client.set(processed_key, "1", ex=self.DEDUPLICATION_TTL_SECONDS)

                # Remover chave de processing
                await self.redis_client.delete(processing_key)

                self.logger.debug("ticket_marked_as_processed_redis", ticket_id=ticket_id)
                return  # Sucesso no Redis, não precisa tentar MongoDB

            except Exception as e:
                self.logger.warning(
                    "redis_mark_processed_failed",
                    ticket_id=ticket_id,
                    error=str(e),
                    message="Tentando fallback MongoDB",
                )

        # F2: Fallback para MongoDB
        if self.ticket_client:
            try:
                await self.ticket_client.update_ticket_status(
                    ticket_id,
                    "COMPLETED",
                    metadata={
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                        "dedup_method": "mongodb_fallback",
                    },
                )
                self.logger.debug("F2_ticket_marked_processed_mongodb", ticket_id=ticket_id)
            except Exception as e:
                self.logger.exception(
                    "F2_mongodb_mark_processed_failed", ticket_id=ticket_id, error=str(e)
                )

    async def _clear_ticket_processing(self, ticket_id: str) -> None:
        """
        Limpa chave de processing para permitir reprocessamento após falha.
        F2: Tenta Redis primeiro, depois MongoDB como fallback.

        Args:
            ticket_id: ID do execution ticket
        """
        if not ticket_id:
            return

        # Tenta Redis primeiro
        if self.redis_client:
            try:
                processing_key = f"ticket:processing:{ticket_id}"
                await self.redis_client.delete(processing_key)
                self.logger.debug("ticket_processing_cleared_redis", ticket_id=ticket_id)
                return  # Sucesso no Redis
            except Exception as e:
                self.logger.warning(
                    "redis_clear_processing_failed",
                    ticket_id=ticket_id,
                    error=str(e),
                    message="Tentando fallback MongoDB",
                )

        # F2: Fallback para MongoDB (marca como FAILED para permitir reprocessamento)
        if self.ticket_client:
            try:
                await self.ticket_client.update_ticket_status(
                    ticket_id,
                    "PENDING",
                    metadata={
                        "processing_cleared_at": datetime.now(timezone.utc).isoformat(),
                        "dedup_method": "mongodb_fallback",
                    },
                )
                self.logger.debug("F2_ticket_processing_cleared_mongodb", ticket_id=ticket_id)
            except Exception as e:
                self.logger.exception(
                    "F2_mongodb_clear_processing_failed", ticket_id=ticket_id, error=str(e)
                )

    async def process_ticket(self, ticket: dict[str, Any]):
        """Processar ticket de execução"""
        ticket_id = ticket.get("ticket_id")

        # Validar que ticket_id está presente e não é vazio
        if not ticket_id:
            self.logger.error(
                "ticket_id_missing_or_empty",
                ticket=ticket,
                message="Ticket inválido: ticket_id ausente ou vazio. Ignorando processamento.",
            )
            if self.metrics and hasattr(self.metrics, "tickets_failed_total"):
                task_type = ticket.get("task_type", "unknown")
                self.metrics.tickets_failed_total.labels(
                    task_type=task_type, error_type="invalid_ticket_id"
                ).inc()
            return

        # F1: Validar e garantir correlation_id no ticket
        correlation_id = ticket.get("correlation_id") or ticket.get("correlationId")
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
            ticket["correlation_id"] = correlation_id
            self.logger.warning(
                "F1: correlation_id ausente no ticket - UUID gerado no Worker Agent",
                ticket_id=ticket_id,
                generated_correlation_id=correlation_id,
                action_required="Verificar propagação de correlation_id upstream (Orchestrator Dynamic)",
            )

        # Verificar duplicata via Redis (idempotência)
        if await self._is_duplicate_ticket(ticket_id):
            self.logger.info("duplicate_ticket_skipped", ticket_id=ticket_id)
            if self.metrics and hasattr(self.metrics, "duplicates_detected_total"):
                self.metrics.duplicates_detected_total.labels(component="execution_engine").inc()
            return

        # Validar se já está em execução
        if ticket_id in self.active_tasks:
            self.logger.warning("ticket_already_processing", ticket_id=ticket_id)
            return

        # Criar task assíncrona
        task = asyncio.create_task(self._execute_ticket(ticket))
        self.active_tasks[ticket_id] = task

        self.logger.info(
            "ticket_processing_started",
            ticket_id=ticket_id,
            task_type=ticket.get("task_type"),
            active_tasks_count=len(self.active_tasks),
        )

        if self.metrics:
            if hasattr(self.metrics, "tickets_processing_total"):
                self.metrics.tickets_processing_total.labels(
                    task_type=ticket.get("task_type")
                ).inc()
            if hasattr(self.metrics, "active_tasks"):
                self.metrics.active_tasks.set(len(self.active_tasks))

    async def _inject_dependency_outputs(self, ticket: dict[str, Any]) -> None:
        """Injeta os outputs das dependências como input da task atual (data flow).

        Cada dependência já COMPLETED tem o seu output persistido em
        metadata["result"] (via update_ticket_status result_data). Recolhe-os e:
        - regista todos em parameters["dependency_outputs"] (mapa ticket_id→output);
        - se a task não tiver `input_data` próprio, usa o output da última
          dependência como input_data (encadeamento simples A→B→C).

        Best-effort: falhas a obter um output não abortam a execução (a task
        degrada para o seu comportamento sem input).
        """
        dependencies = ticket.get("dependencies") or []
        if not dependencies:
            return

        parameters = ticket.setdefault("parameters", {})
        dependency_outputs: dict[str, Any] = {}
        last_output = None
        for dep_id in dependencies:
            try:
                dep_ticket = await self.ticket_client.get_ticket(dep_id)
                dep_meta = dep_ticket.get("metadata") or {}
                dep_result = dep_meta.get("result")
                # Defensivo: se o result foi persistido como string JSON, desserializar.
                if isinstance(dep_result, str):
                    try:
                        dep_result = json.loads(dep_result)
                    except (ValueError, TypeError):
                        pass
                if dep_result is not None:
                    dependency_outputs[dep_id] = dep_result
                    # O output efetivo do executor está em result["output"] (contrato
                    # normalizado); cai para o result completo se ausente.
                    last_output = (
                        dep_result.get("output")
                        if isinstance(dep_result, dict) and "output" in dep_result
                        else dep_result
                    )
                    # Defensivo: se o output veio como string JSON (serialização
                    # aninhada), desserializar para que a TRANSFORM receba dict/list
                    # e não uma string (que partiria aggregate/filter).
                    if isinstance(last_output, str):
                        try:
                            last_output = json.loads(last_output)
                        except (ValueError, TypeError):
                            pass
            except Exception as e:
                self.logger.warning(
                    "dependency_output_fetch_failed",
                    ticket_id=ticket.get("ticket_id"),
                    dependency_id=dep_id,
                    error=str(e),
                )

        if dependency_outputs:
            parameters["dependency_outputs"] = dependency_outputs
            # Encadeamento simples: alimenta input_data com o output da dependência
            # quando a task não traz um input_data próprio (placeholder do template).
            current_input = parameters.get("input_data")
            if current_input in (None, "None", "", {}, []) and last_output is not None:
                parameters["input_data"] = last_output
            self.logger.info(
                "dependency_outputs_injected",
                ticket_id=ticket.get("ticket_id"),
                dependencies_count=len(dependency_outputs),
            )

    @staticmethod
    def _result_correlation_kwargs(ticket: dict[str, Any]) -> dict[str, Any]:
        """I4: Extrai plan_id/workflow_id/correlation_id do ticket para propagar
        ao ExecutionResultConsumer do orchestrator.

        Sem estes campos no resultado, o consumer depende sempre do lookup Redis
        (workflow:by:ticket:*). O ticket gerado pelo orchestrator traz plan_id e
        correlation_id no topo e workflow_id em metadata.workflow_id. Só inclui
        chaves cujo valor exista (não inventa nada).
        """
        metadata = ticket.get("metadata") or {}
        kwargs: dict[str, Any] = {}
        plan_id = ticket.get("plan_id")
        workflow_id = ticket.get("workflow_id") or metadata.get("workflow_id")
        correlation_id = ticket.get("correlation_id") or ticket.get("correlationId")
        if plan_id:
            kwargs["plan_id"] = plan_id
        if workflow_id:
            kwargs["workflow_id"] = workflow_id
        if correlation_id:
            kwargs["correlation_id"] = correlation_id
        return kwargs

    # Mapa executor->label usado na métrica simulated_total (alinhado com o
    # nome lógico do executor por task_type, em minúsculas).
    _EXECUTOR_LABEL_BY_TASK_TYPE: ClassVar[dict[str, str]] = {
        "QUERY": "query",
        "TRANSFORM": "transform",
        "VALIDATE": "validate",
        "BUILD": "build",
        "DEPLOY": "deploy",
        "EXECUTE": "execute",
        "GENERATE_CODE": "generate_code",
        "TEST": "test",
        "COMPENSATE": "compensate",
    }

    # --- Validadores de evidência por task_type (contrato technical-spec) ------
    # Cada validador recebe o ``output`` (dict) e devolve ``(ok, reason)``. A regra
    # transversal (simulated/noop) é aplicada antes, no dispatcher.

    @staticmethod
    def _evidence_query(output: dict[str, Any]) -> tuple[bool, str | None]:
        # Aceita TODAS as formas reais do query_executor:
        #   - Coleções/listas (MongoDB, Neo4j, Kafka, Redis SCAN/KEYS): count + lista
        #     em documents/results/messages/keys.
        #   - Redis GET: {key, value, exists} (SEM count nem lista) — o GET ocorreu,
        #     logo é trabalho real, incluindo o caso exists=False (chave ausente).
        is_redis_get = "exists" in output or ("key" in output and "value" in output)
        if is_redis_get:
            return True, None
        if output.get("count") is None:
            return False, "query sem output.count"
        has_records = any(
            isinstance(output.get(k), list) for k in ("documents", "results", "messages", "keys")
        )
        if not has_records:
            return False, "query sem documentos/results reais"
        return True, None

    @staticmethod
    def _evidence_transform(output: dict[str, Any]) -> tuple[bool, str | None]:
        # noop já tratado no dispatcher; output derivado deve existir e não ser None.
        # Cobre TODAS as chaves reais do transform_executor:
        #   json/mongodb -> transformed_data; aggregate -> aggregated_data;
        #   format -> formatted_data; filter -> filtered_data; json (validação) ->
        #   validated; csv -> rows (lista de linhas parseadas).
        has_derived = any(
            output.get(k) is not None
            for k in (
                "transformed_data",
                "aggregated_data",
                "formatted_data",
                "filtered_data",
                "validated",
                "rows",
            )
        )
        if not output or not has_derived:
            return False, "transform sem output derivado (noop ou vazio)"
        return True, None

    @staticmethod
    def _evidence_validate(output: dict[str, Any]) -> tuple[bool, str | None]:
        # simulated já tratado; exige decisão OPA com result ou scan com findings.
        has_result = output.get("result") is not None
        has_findings = output.get("findings") is not None or output.get("violations") is not None
        if not (has_result or has_findings):
            return False, "validate sem result OPA nem findings (policy_undefined/vazio)"
        return True, None

    @staticmethod
    def _evidence_build(output: dict[str, Any]) -> tuple[bool, str | None]:
        # Contrato §4: {registry}/{artifact}:{version} + digest verificável.
        artifact = output.get("artifact") or output.get("artifact_uri") or output.get("image")
        if not artifact:
            return False, "build sem referência de artefacto"
        if not output.get("digest"):
            return False, "build sem digest verificável"
        return True, None

    @staticmethod
    def _evidence_deploy(output: dict[str, Any]) -> tuple[bool, str | None]:
        # simulated já tratado; exige recurso reconciliado.
        reconciled = (
            output.get("resource")
            or output.get("status")
            or output.get("synced")
            or output.get("healthy")
        )
        if not reconciled:
            return False, "deploy sem recurso reconciliado"
        return True, None

    @staticmethod
    def _evidence_execute(output: dict[str, Any]) -> tuple[bool, str | None]:
        if output.get("exit_code") is None:
            return False, "execute sem exit code real"
        stdout = output.get("stdout") or ""
        if isinstance(stdout, str) and stdout.lstrip().startswith("[SIMULAÇÃO]"):
            return False, "execute com stdout simulado ([SIMULAÇÃO])"
        return True, None

    @staticmethod
    def _evidence_generate_code(output: dict[str, Any]) -> tuple[bool, str | None]:
        if not output.get("code_artifact_id"):
            return False, "generate_code sem code_artifact_id"
        return True, None

    # Dispatch table task_type -> validador de evidência. Definida abaixo da classe
    # (após as definições dos staticmethods) via _build_evidence_validators.

    def _has_real_evidence(self, task_type: str, result: dict[str, Any]) -> tuple[bool, str | None]:
        """Valida o contrato de evidência de trabalho real por ``task_type``.

        Materializa a tabela do contrato (technical-spec §Contrato de evidência):
        um resultado só é considerado trabalho real se produzir a evidência
        verificável do seu tipo. Despacha para o validador específico do tipo.

        Regra transversal (aplica-se a todos os tipos): ``metadata.simulated == True``
        OU ``output.noop == True`` => NÃO é trabalho real.

        Args:
            task_type: tipo da task (case-insensitive).
            result: dicionário de resultado do executor
                (``{"success", "output", "metadata", ...}``).

        Returns:
            ``(ok, reason)`` onde ``ok`` indica se há evidência real e ``reason``
            descreve o motivo quando ``ok`` é ``False``. Para tipos sem contrato
            definido devolve ``(True, "unverified")``.
        """
        tt = (task_type or "").upper()
        output = result.get("output")
        output = output if isinstance(output, dict) else {}
        metadata = result.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}

        # Regra transversal: simulação/noop nunca são trabalho real.
        if metadata.get("simulated") is True:
            return False, "metadata.simulated=True (simulação não é trabalho real)"
        if output.get("noop") is True:
            return False, "output.noop=True (no-op não é trabalho real)"

        validator = self._EVIDENCE_VALIDATORS.get(tt)
        if validator is None:
            # task_type sem evidência definida: aceitar mas marcar como não verificado.
            return True, "unverified"
        return validator(output)

    async def _enforce_evidence_gate(
        self,
        *,
        ticket: dict[str, Any],
        result: dict[str, Any],
        task_type: str,
        ticket_id: str,
        duration_ms: int,
        span: Any,
    ) -> bool:
        """Aplica o gate de evidência (Caminho Real First-Class) a um resultado.

        Só relevante para resultados de sucesso (``success=True``); para
        ``success=False`` o gate não interfere (o chamador trata a falha real).
        Quando não há evidência real (ou é ``unverified``), marca/mede a degradação
        (``simulated_total``, log WARNING, anotação em ``result.metadata``). Em modo
        estrito (``config.strict_real_path``), ausência de evidência real (excluindo
        ``unverified``, que é tolerado) termina o ticket como FAILED com razão
        ``real_path_unverified``.

        Args:
            ticket: dados do ticket em execução.
            result: dicionário de resultado do executor.
            task_type: tipo da task.
            ticket_id: identificador do ticket.
            duration_ms: duração da execução em milissegundos.
            span: span de tracing ativo.

        Returns:
            ``True`` se o chamador deve prosseguir para a marcação normal
            (COMPLETED/FAILED); ``False`` se o gate já terminou o ticket como FAILED
            (modo estrito sem evidência real).
        """
        evidence_ok, evidence_reason = (True, None)
        is_unverified = False
        strict_real_path = getattr(self.config, "strict_real_path", False)
        if result.get("success"):
            evidence_ok, evidence_reason = self._has_real_evidence(task_type, result)
            is_unverified = evidence_ok and evidence_reason == "unverified"

        # Marcar e medir sempre que não há evidência real (ou é unverified).
        if result.get("success") and (not evidence_ok or is_unverified):
            executor_label = self._EXECUTOR_LABEL_BY_TASK_TYPE.get(
                (task_type or "").upper(), "unknown"
            )
            if self.metrics and hasattr(self.metrics, "simulated_total"):
                self.metrics.simulated_total.labels(
                    executor=executor_label, task_type=task_type
                ).inc()
            # Anotar o resultado para auditoria a jusante.
            if isinstance(result, dict):
                result.setdefault("metadata", {})
                if isinstance(result["metadata"], dict):
                    result["metadata"]["evidence"] = "unverified" if is_unverified else "missing"
                    result["metadata"]["evidence_reason"] = evidence_reason
            self.logger.warning(
                "ticket_evidence_missing",
                ticket_id=ticket_id,
                task_type=task_type,
                degraded=True,
                reason=evidence_reason,
                strict_real_path=strict_real_path,
                unverified=is_unverified,
            )

        # Enforcement: em modo estrito, ausência de evidência real
        # (excluindo `unverified`, que é tolerado) -> FAILED.
        if strict_real_path and not evidence_ok:
            error_msg = f"real_path_unverified: {evidence_reason}"
            span.set_attribute("error", True)
            span.set_attribute("error.type", "real_path_unverified")

            await self._clear_ticket_processing(ticket_id)

            await self.ticket_client.update_ticket_status(
                ticket_id,
                "FAILED",
                error_message=error_msg,
                actual_duration_ms=duration_ms,
            )

            await self.result_producer.publish_result(
                ticket_id,
                "FAILED",
                result,
                error_message=error_msg,
                actual_duration_ms=duration_ms,
                **self._result_correlation_kwargs(ticket),
            )

            self.logger.warning(
                "ticket_execution_failed",
                ticket_id=ticket_id,
                task_type=task_type,
                error=error_msg,
                duration_ms=duration_ms,
            )

            if self.metrics:
                if hasattr(self.metrics, "tickets_failed_total"):
                    self.metrics.tickets_failed_total.labels(
                        task_type=task_type, error_type="real_path_unverified"
                    ).inc()
                if hasattr(self.metrics, "task_duration_seconds"):
                    self.metrics.task_duration_seconds.labels(task_type=task_type).observe(
                        duration_ms / 1000
                    )
            return False

        return True

    async def _execute_ticket(self, ticket: dict[str, Any]):
        """Executar ticket com coordenação de dependências e retry logic"""
        ticket_id = ticket.get("ticket_id")
        task_type = ticket.get("task_type")
        start_time = datetime.now()

        tracer = get_tracer()
        with tracer.start_as_current_span("ticket_execution") as span:
            span.set_attribute("neural.hive.ticket_id", ticket_id)
            span.set_attribute("neural.hive.task_type", task_type)
            span.set_attribute("neural.hive.plan_id", ticket.get("plan_id", ""))
            span.set_attribute("neural.hive.intent_id", ticket.get("intent_id", ""))

            try:
                # Adquirir semaphore (limitar concorrência)
                async with self.task_semaphore:
                    self.logger.info(
                        "ticket_execution_started",
                        ticket_id=ticket_id,
                        task_type=task_type,
                        plan_id=ticket.get("plan_id"),
                        intent_id=ticket.get("intent_id"),
                    )

                    # Atualizar status para RUNNING
                    await self.ticket_client.update_ticket_status(ticket_id, "RUNNING")

                    # Verificar dependências
                    try:
                        await self.dependency_coordinator.wait_for_dependencies(ticket)
                    except Exception as dep_error:
                        self.logger.exception(
                            "dependency_check_failed", ticket_id=ticket_id, error=str(dep_error)
                        )
                        span.set_attribute("error", True)
                        span.set_attribute("error.type", "dependency")

                        # Limpar chave de processing para permitir retry (two-phase scheme)
                        await self._clear_ticket_processing(ticket_id)

                        # Marcar como FAILED
                        await self.ticket_client.update_ticket_status(
                            ticket_id,
                            "FAILED",
                            error_message=f"Dependency check failed: {dep_error!s}",
                        )
                        # Publicar resultado
                        await self.result_producer.publish_result(
                            ticket_id,
                            "FAILED",
                            {"success": False},
                            error_message=str(dep_error),
                            **self._result_correlation_kwargs(ticket),
                        )
                        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                        if self.metrics:
                            if hasattr(self.metrics, "tickets_failed_total"):
                                self.metrics.tickets_failed_total.labels(
                                    task_type=task_type, error_type="dependency"
                                ).inc()
                            if hasattr(self.metrics, "task_duration_seconds"):
                                self.metrics.task_duration_seconds.labels(
                                    task_type=task_type
                                ).observe(duration_ms / 1000)
                        return

                    # Data flow: injetar os outputs das dependências como input
                    # da task atual (a task seguinte consome o resultado da anterior).
                    await self._inject_dependency_outputs(ticket)

                    # Executar tarefa com retry
                    try:
                        result = await self._execute_task_with_retry(ticket)
                        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

                        # Contrato de evidência (Caminho Real First-Class): aplica o gate
                        # de evidência antes de marcar COMPLETED. Em modo estrito, ausência
                        # de evidência real termina o ticket como FAILED (retorna False).
                        proceed = await self._enforce_evidence_gate(
                            ticket=ticket,
                            result=result,
                            task_type=task_type,
                            ticket_id=ticket_id,
                            duration_ms=duration_ms,
                            span=span,
                        )
                        if not proceed:
                            return

                        # Verificar se a execução foi bem-sucedida
                        if result.get("success"):
                            # Sucesso - marcar como COMPLETED, persistindo o output
                            # (result_data) para data flow: as tasks dependentes leem-no
                            # como input das suas dependências.
                            await self.ticket_client.update_ticket_status(
                                ticket_id,
                                "COMPLETED",
                                actual_duration_ms=duration_ms,
                                result_data=result,
                            )

                            await self.result_producer.publish_result(
                                ticket_id,
                                "COMPLETED",
                                result,
                                actual_duration_ms=duration_ms,
                                **self._result_correlation_kwargs(ticket),
                            )

                            self.logger.info(
                                "ticket_execution_completed",
                                ticket_id=ticket_id,
                                task_type=task_type,
                                duration_ms=duration_ms,
                            )

                            # Marcar ticket como processado com sucesso (two-phase scheme)
                            await self._mark_ticket_processed(ticket_id)

                            if self.metrics:
                                if hasattr(self.metrics, "tickets_completed_total"):
                                    self.metrics.tickets_completed_total.labels(
                                        task_type=task_type
                                    ).inc()
                                if hasattr(self.metrics, "task_duration_seconds"):
                                    self.metrics.task_duration_seconds.labels(
                                        task_type=task_type
                                    ).observe(duration_ms / 1000)
                        else:
                            # Falha na execução mas sem exceção - marcar como FAILED
                            error_msg = result.get(
                                "error", "Task execution failed without exception"
                            )
                            span.set_attribute("error", True)
                            span.set_attribute("error.type", "execution_failed")

                            # Limpar chave de processing para permitir retry (two-phase scheme)
                            await self._clear_ticket_processing(ticket_id)

                            await self.ticket_client.update_ticket_status(
                                ticket_id,
                                "FAILED",
                                error_message=error_msg,
                                actual_duration_ms=duration_ms,
                            )

                            await self.result_producer.publish_result(
                                ticket_id,
                                "FAILED",
                                result,
                                error_message=error_msg,
                                actual_duration_ms=duration_ms,
                                **self._result_correlation_kwargs(ticket),
                            )

                            self.logger.warning(
                                "ticket_execution_failed",
                                ticket_id=ticket_id,
                                task_type=task_type,
                                error=error_msg,
                                duration_ms=duration_ms,
                            )

                            if self.metrics:
                                if hasattr(self.metrics, "tickets_failed_total"):
                                    self.metrics.tickets_failed_total.labels(
                                        task_type=task_type, error_type="execution_failed"
                                    ).inc()
                                if hasattr(self.metrics, "task_duration_seconds"):
                                    self.metrics.task_duration_seconds.labels(
                                        task_type=task_type
                                    ).observe(duration_ms / 1000)

                    except TaskExecutionError as exec_error:
                        # Falha após todas as tentativas
                        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                        span.set_attribute("error", True)
                        span.set_attribute("error.type", "execution_error")

                        # Limpar chave de processing para permitir retry (two-phase scheme)
                        await self._clear_ticket_processing(ticket_id)

                        await self.ticket_client.update_ticket_status(
                            ticket_id,
                            "FAILED",
                            error_message=str(exec_error),
                            actual_duration_ms=duration_ms,
                        )

                        await self.result_producer.publish_result(
                            ticket_id,
                            "FAILED",
                            {"success": False},
                            error_message=str(exec_error),
                            actual_duration_ms=duration_ms,
                            **self._result_correlation_kwargs(ticket),
                        )

                        self.logger.exception(
                            "ticket_execution_failed",
                            ticket_id=ticket_id,
                            task_type=task_type,
                            error=str(exec_error),
                            duration_ms=duration_ms,
                        )

                        if self.metrics:
                            if hasattr(self.metrics, "tickets_failed_total"):
                                self.metrics.tickets_failed_total.labels(
                                    task_type=task_type, error_type="execution_error"
                                ).inc()
                            if hasattr(self.metrics, "task_duration_seconds"):
                                self.metrics.task_duration_seconds.labels(
                                    task_type=task_type
                                ).observe(duration_ms / 1000)

            except asyncio.CancelledError:
                # Task was cancelled (preemption or graceful shutdown)
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                span.set_attribute("error", True)
                span.set_attribute("error.type", "cancelled")
                self.logger.info(
                    "ticket_execution_cancelled", ticket_id=ticket_id, duration_ms=duration_ms
                )
                # Note: Status update and result publish are handled by cancel_active_task
                # Just clean up and re-raise to signal cancellation
                raise

            except TimeoutError:
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                span.set_attribute("error", True)
                span.set_attribute("error.type", "timeout")
                self.logger.exception("ticket_execution_timeout", ticket_id=ticket_id)

                # Limpar chave de processing para permitir retry (two-phase scheme)
                await self._clear_ticket_processing(ticket_id)

                await self.ticket_client.update_ticket_status(
                    ticket_id,
                    "FAILED",
                    error_message="Execution timeout",
                    actual_duration_ms=duration_ms,
                )
                try:
                    await self.result_producer.publish_result(
                        ticket_id,
                        "FAILED",
                        {"success": False},
                        error_message="Execution timeout",
                        actual_duration_ms=duration_ms,
                        **self._result_correlation_kwargs(ticket),
                    )
                except Exception as pub_exc:
                    self.logger.exception(
                        "result_publish_failed_timeout", ticket_id=ticket_id, error=str(pub_exc)
                    )
                if self.metrics:
                    if hasattr(self.metrics, "tickets_failed_total"):
                        self.metrics.tickets_failed_total.labels(
                            task_type=task_type, error_type="timeout"
                        ).inc()
                    if hasattr(self.metrics, "task_duration_seconds"):
                        self.metrics.task_duration_seconds.labels(task_type=task_type).observe(
                            duration_ms / 1000
                        )

            except Exception as e:
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                span.set_attribute("error", True)
                span.set_attribute("error.type", "exception")
                self.logger.error(
                    "ticket_execution_error", ticket_id=ticket_id, error=str(e), exc_info=True
                )

                # Limpar chave de processing para permitir retry (two-phase scheme)
                await self._clear_ticket_processing(ticket_id)

                await self.ticket_client.update_ticket_status(
                    ticket_id, "FAILED", error_message=str(e), actual_duration_ms=duration_ms
                )
                try:
                    await self.result_producer.publish_result(
                        ticket_id,
                        "FAILED",
                        {"success": False},
                        error_message=str(e),
                        actual_duration_ms=duration_ms,
                        **self._result_correlation_kwargs(ticket),
                    )
                except Exception as pub_exc:
                    self.logger.exception(
                        "result_publish_failed_error", ticket_id=ticket_id, error=str(pub_exc)
                    )
                if self.metrics:
                    if hasattr(self.metrics, "tickets_failed_total"):
                        self.metrics.tickets_failed_total.labels(
                            task_type=task_type, error_type="exception"
                        ).inc()
                    if hasattr(self.metrics, "task_duration_seconds"):
                        self.metrics.task_duration_seconds.labels(task_type=task_type).observe(
                            duration_ms / 1000
                        )

            finally:
                # Remover de active_tasks
                if ticket_id in self.active_tasks:
                    del self.active_tasks[ticket_id]
                if self.metrics and hasattr(self.metrics, "active_tasks"):
                    self.metrics.active_tasks.set(len(self.active_tasks))

    def _normalize_executor_result(
        self, result: Any, ticket_id: str | None, task_type: str | None
    ) -> dict[str, Any]:
        """Garante que o resultado do executor cumpre o contrato {"success": bool}.

        Os executores devem devolver sempre um dict com a chave `success`. Quando
        tal não acontece (dict sem `success` ou valor não-dict), esta função
        normaliza o resultado para um dict de falha explícito, evitando a falha
        silenciosa em `_execute_ticket` (que marca FAILED com a mensagem genérica
        "Task execution failed without exception" sempre que `success` é falsy).

        Args:
            result: Valor devolvido pelo executor.
            ticket_id: ID do ticket (para log).
            task_type: Tipo da tarefa (para log).

        Returns:
            Dict com a chave `success` garantida.
        """
        if isinstance(result, dict) and "success" in result:
            return result

        self.logger.warning(
            "executor_result_missing_success",
            ticket_id=ticket_id,
            task_type=task_type,
            result_type=type(result).__name__,
        )

        if isinstance(result, dict):
            # Preserva o conteúdo devolvido, apenas garante a chave `success`.
            normalized = dict(result)
            normalized["success"] = False
            normalized.setdefault("error", "Executor result missing required 'success' field")
            return normalized

        return {
            "success": False,
            "output": result,
            "error": "Executor returned a non-dict result without 'success' field",
        }

    async def _execute_task_with_retry(self, ticket: dict[str, Any]) -> dict[str, Any]:
        """Executar tarefa com retry logic"""
        task_type = ticket.get("task_type")
        ticket_id = ticket.get("ticket_id")
        sla = ticket.get("sla", {})
        max_retries = sla.get("max_retries", self.config.max_retries_per_ticket)
        timeout_ms = sla.get("timeout_ms", 60000)

        # Calcular timeout
        timeout_seconds = (timeout_ms * self.config.task_timeout_multiplier) / 1000

        # Obter executor
        executor = self.executor_registry.get_executor(task_type)

        last_error = None

        for attempt in range(max_retries + 1):
            try:
                self.logger.debug(
                    "task_execution_attempt",
                    ticket_id=ticket_id,
                    task_type=task_type,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                )

                # Executar com timeout
                exec_result = await asyncio.wait_for(
                    executor.execute(ticket), timeout=timeout_seconds
                )
                # Contrato: o executor deve devolver sempre {"success": bool, ...}.
                # Defensivo: se um executor devolver um dict sem a chave `success`
                # (ou um valor não-dict), normalizar para evitar a falha silenciosa
                # "Task execution failed without exception" em _execute_ticket.
                return self._normalize_executor_result(exec_result, ticket_id, task_type)

            except TimeoutError:
                last_error = f"Timeout after {timeout_seconds}s"
                self.logger.warning(
                    "task_execution_timeout",
                    ticket_id=ticket_id,
                    task_type=task_type,
                    attempt=attempt + 1,
                    timeout_seconds=timeout_seconds,
                )
                if self.metrics and hasattr(self.metrics, "task_retries_total"):
                    self.metrics.task_retries_total.labels(
                        task_type=task_type, attempt=str(attempt + 1)
                    ).inc()

            except Exception as e:
                last_error = str(e)
                self.logger.warning(
                    "task_execution_failed_retry",
                    ticket_id=ticket_id,
                    task_type=task_type,
                    attempt=attempt + 1,
                    error=str(e),
                )
                if self.metrics and hasattr(self.metrics, "task_retries_total"):
                    self.metrics.task_retries_total.labels(
                        task_type=task_type, attempt=str(attempt + 1)
                    ).inc()

            # Backoff exponencial
            if attempt < max_retries:
                backoff = min(
                    self.config.retry_backoff_base_seconds * (2**attempt),
                    self.config.retry_backoff_max_seconds,
                )
                await asyncio.sleep(backoff)

        # Todas as tentativas falharam
        raise TaskExecutionError(
            f"Task execution failed after {max_retries + 1} attempts: {last_error}"
        )

    async def shutdown(self, timeout_seconds: int = 30):
        """Shutdown graceful do execution engine"""
        if not self.active_tasks:
            self.logger.info("no_active_tasks_to_shutdown")
            return

        self.logger.info(
            "shutting_down_execution_engine",
            active_tasks_count=len(self.active_tasks),
            timeout_seconds=timeout_seconds,
        )

        # Aguardar conclusão de tarefas ativas
        try:
            await asyncio.wait_for(
                asyncio.gather(*self.active_tasks.values(), return_exceptions=True),
                timeout=timeout_seconds,
            )
            self.logger.info("all_active_tasks_completed")

        except TimeoutError:
            # Cancelar tarefas que não concluíram
            cancelled_count = 0
            for ticket_id, task in self.active_tasks.items():
                if not task.done():
                    task.cancel()
                    cancelled_count += 1
                    self.logger.warning("task_cancelled", ticket_id=ticket_id)

            if self.metrics and cancelled_count > 0:
                for _ in range(cancelled_count):
                    self.metrics.tasks_cancelled_total.inc()
            self.logger.warning("shutdown_timeout_tasks_cancelled", cancelled_count=cancelled_count)

    async def cancel_active_task(
        self,
        ticket_id: str,
        reason: str = "preemption",
        preempted_by: str | None = None,
        grace_period_seconds: int = 30,
    ) -> dict[str, Any]:
        """
        Cancel an active task with optional checkpointing.

        Called by the HTTP endpoint when the Orchestrator requests preemption.

        Args:
            ticket_id: ID of the ticket to cancel
            reason: Reason for cancellation (preemption, timeout, user_request)
            preempted_by: ID of the ticket that is preempting this one
            grace_period_seconds: Time to wait for graceful cancellation

        Returns:
            Dict with cancellation result
        """
        if ticket_id not in self.active_tasks:
            self.logger.warning("cancel_task_not_active", ticket_id=ticket_id)
            return {"success": False, "message": f"Task {ticket_id} is not active"}

        task = self.active_tasks[ticket_id]
        checkpoint_saved = False
        checkpoint_key = None

        self.logger.info(
            "cancelling_active_task",
            ticket_id=ticket_id,
            reason=reason,
            preempted_by=preempted_by,
            grace_period_seconds=grace_period_seconds,
        )

        try:
            # Save checkpoint before cancellation if Redis is available
            if self.redis_client:
                checkpoint_result = await self._save_checkpoint(
                    ticket_id, reason=reason, preempted_by=preempted_by
                )
                checkpoint_saved = checkpoint_result.get("success", False)
                checkpoint_key = checkpoint_result.get("checkpoint_key")

            # Cancel the task
            task.cancel()

            # Wait for graceful cancellation with timeout
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=grace_period_seconds)
            except asyncio.CancelledError:
                pass  # Expected
            except TimeoutError:
                self.logger.warning(
                    "graceful_cancellation_timeout",
                    ticket_id=ticket_id,
                    grace_period_seconds=grace_period_seconds,
                )

            # Update ticket status to PREEMPTED
            status = "PREEMPTED" if reason == "preemption" else "CANCELLED"
            try:
                await self.ticket_client.update_ticket_status(
                    ticket_id,
                    status,
                    error_message=(
                        f"Task {reason}: preempted by {preempted_by}"
                        if preempted_by
                        else f"Task {reason}"
                    ),
                )
            except Exception as status_error:
                self.logger.exception(
                    "update_status_failed", ticket_id=ticket_id, error=str(status_error)
                )

            # Publish result
            try:
                await self.result_producer.publish_result(
                    ticket_id,
                    status,
                    {
                        "success": False,
                        "reason": reason,
                        "preempted_by": preempted_by,
                        "checkpoint_key": checkpoint_key,
                    },
                    error_message=f"Task {reason}",
                )
            except Exception as pub_error:
                self.logger.exception(
                    "publish_result_failed", ticket_id=ticket_id, error=str(pub_error)
                )

            # Clear processing key to allow retry
            await self._clear_ticket_processing(ticket_id)

            # Record metrics
            if self.metrics:
                if hasattr(self.metrics, "tasks_cancelled_total"):
                    self.metrics.tasks_cancelled_total.labels(reason=reason).inc()
                if hasattr(self.metrics, "tasks_preempted_total") and reason == "preemption":
                    self.metrics.tasks_preempted_total.inc()
                if hasattr(self.metrics, "checkpoint_saves_total") and checkpoint_saved:
                    self.metrics.checkpoint_saves_total.labels(success="true").inc()

            self.logger.info(
                "task_cancelled_successfully",
                ticket_id=ticket_id,
                reason=reason,
                checkpoint_saved=checkpoint_saved,
                checkpoint_key=checkpoint_key,
            )

            return {
                "success": True,
                "ticket_id": ticket_id,
                "reason": reason,
                "checkpoint_saved": checkpoint_saved,
                "checkpoint_key": checkpoint_key,
                "message": f"Task {ticket_id} cancelled successfully",
            }

        except Exception as e:
            self.logger.exception("cancel_task_failed", ticket_id=ticket_id, error=str(e))
            return {
                "success": False,
                "ticket_id": ticket_id,
                "message": f"Failed to cancel task: {e!s}",
            }

    async def _save_checkpoint(
        self, ticket_id: str, reason: str = "preemption", preempted_by: str | None = None
    ) -> dict[str, Any]:
        """
        Save task checkpoint to Redis for later retry.

        Args:
            ticket_id: ID of the ticket being checkpointed
            reason: Reason for checkpoint
            preempted_by: ID of preempting ticket

        Returns:
            Dict with checkpoint result
        """
        if not self.redis_client:
            return {"success": False, "message": "Redis not available"}

        checkpoint_key = f"checkpoint:{ticket_id}"

        try:
            import json as json_lib

            checkpoint_data = {
                "ticket_id": ticket_id,
                "reason": reason,
                "preempted_by": preempted_by,
                "timestamp": datetime.now().isoformat(),
                "worker_id": getattr(self.config, "agent_id", "unknown"),
            }

            # Store checkpoint with 24h TTL
            await self.redis_client.set(
                checkpoint_key, json_lib.dumps(checkpoint_data), ex=86400  # 24 hours
            )

            self.logger.info("checkpoint_saved", ticket_id=ticket_id, checkpoint_key=checkpoint_key)

            return {"success": True, "checkpoint_key": checkpoint_key}

        except Exception as e:
            self.logger.exception("checkpoint_save_failed", ticket_id=ticket_id, error=str(e))
            if self.metrics and hasattr(self.metrics, "checkpoint_saves_total"):
                self.metrics.checkpoint_saves_total.labels(success="false").inc()
            return {"success": False, "message": str(e)}


# Dispatch table do contrato de evidência (task_type -> validador). Definida após a
# classe para que os staticmethods já estejam acessíveis como funções planas.
ExecutionEngine._EVIDENCE_VALIDATORS = {
    "QUERY": ExecutionEngine._evidence_query,
    "TRANSFORM": ExecutionEngine._evidence_transform,
    "VALIDATE": ExecutionEngine._evidence_validate,
    "BUILD": ExecutionEngine._evidence_build,
    "DEPLOY": ExecutionEngine._evidence_deploy,
    "EXECUTE": ExecutionEngine._evidence_execute,
    "GENERATE_CODE": ExecutionEngine._evidence_generate_code,
}
