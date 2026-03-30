"""
Factory para criar dados de teste.

Este módulo fornece factories padronizadas para criar
dados de teste consistentes em todo o projecto.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4


@dataclass
class TestCognitivePlanFactory:
    """Factory para criar CognitivePlan de teste."""

    @staticmethod
    def create(
        plan_id: Optional[str] = None,
        intent_id: Optional[str] = None,
        intent: str = "Test intent",
        domain: str = "TECHNICAL",
        status: str = "PENDING",
        risk_band: str = "medium",
        priority: str = "normal",
        original_intent_text: Optional[str] = None,
        tasks: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Cria um CognitivePlan para testes.

        Args:
            plan_id: ID do plano (gerado automaticamente se None)
            intent_id: ID da intenção (gerado automaticamente se None)
            intent: Texto da intenção
            domain: Domínio da decisão (TECHNICAL, BUSINESS, etc.)
            status: Status do plano
            risk_band: Banda de risco (low, medium, high, critical)
            priority: Prioridade (low, normal, high, critical)
            original_intent_text: Texto original da intenção
            tasks: Lista de tarefas (gera tarefas padrão se None)

        Returns:
            Dict com dados do CognitivePlan
        """
        plan_uuid = plan_id or f"plan-{uuid4().hex[:8]}"
        intent_uuid = intent_id or f"intent-{uuid4().hex[:8]}"

        default_tasks = [
            {
                "task_id": f"task-{uuid4().hex[:8]}",
                "task_type": "ANALYZE",
                "description": "Analisar requisitos",
                "dependencies": [],
                "estimated_duration_ms": 5000,
                "required_capabilities": [],
            }
        ]

        return {
            "plan_id": plan_uuid,
            "intent_id": intent_uuid,
            "intent": intent,
            "original_intent_text": original_intent_text or intent,
            "domain": domain,
            "status": status,
            "risk_band": risk_band,
            "priority": priority,
            "tasks": tasks or default_tasks,
            "estimated_duration_ms": 30000,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def create_batch(
        count: int = 5,
        status: str = "PENDING",
        domain: str = "TECHNICAL",
    ) -> List[Dict[str, Any]]:
        """Cria múltiplos CognitivePlans para testes."""
        return [
            TestCognitivePlanFactory.create(status=status, domain=domain)
            for _ in range(count)
        ]


@dataclass
class TestSpecialistOpinionFactory:
    """Factory para criar SpecialistOpinion de teste."""

    @staticmethod
    def create(
        opinion_id: Optional[str] = None,
        plan_id: str = "plan-123",
        specialist_id: str = "specialist-test",
        recommendation: bool = True,
        confidence: float = 0.8,
        domain: str = "TECHNICAL",
        reasoning: Optional[str] = None,
        reasoning_factors: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Cria um SpecialistOpinion para testes.

        Args:
            opinion_id: ID da opinião (gerado automaticamente se None)
            plan_id: ID do plano associado
            specialist_id: ID do especialista
            recommendation: Recomendação (True/False)
            confidence: Nível de confiança (0.0 a 1.0)
            domain: Domínio da opinião
            reasoning: Justificativa da opinião
            reasoning_factors: Fatores de decisão
            metadata: Metadados adicionais

        Returns:
            Dict com dados do SpecialistOpinion
        """
        return {
            "opinion_id": opinion_id or f"opinion-{uuid4().hex[:8]}",
            "plan_id": plan_id,
            "specialist_id": specialist_id,
            "specialist_type": specialist_id.split("-")[0] if "-" in specialist_id else "test",
            "recommendation": recommendation,
            "confidence": max(0.0, min(1.0, confidence)),  # Clamp entre 0 e 1
            "domain": domain,
            "reasoning": reasoning or "Test reasoning for validation purposes",
            "reasoning_factors": reasoning_factors or {
                "complexity": 0.5,
                "risk": 0.3,
                "clarity": 0.8,
            },
            "metadata": metadata or {
                "processing_time_ms": random.randint(100, 500),
                "model_version": "1.0.0",
            },
            "created_at": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def create_batch(
        count: int = 5,
        plan_id: str = "plan-123",
        confidence_min: float = 0.5,
        confidence_max: float = 1.0,
    ) -> List[Dict[str, Any]]:
        """Cria múltiplas SpecialistOpinions para testes."""
        return [
            TestSpecialistOpinionFactory.create(
                plan_id=plan_id,
                confidence=random.uniform(confidence_min, confidence_max),
            )
            for _ in range(count)
        ]


@dataclass
class TestConsolidatedDecisionFactory:
    """Factory para criar ConsolidatedDecision de teste."""

    @staticmethod
    def create(
        decision_id: Optional[str] = None,
        plan_id: str = "plan-123",
        final_decision: bool = True,
        consensus_score: float = 0.85,
        approval_rate: float = 0.8,
        total_opinions: int = 5,
        approve_count: int = 4,
        reject_count: int = 1,
        domain: str = "TECHNICAL",
        reasoning: Optional[str] = None,
        hierarchical_weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Cria um ConsolidatedDecision para testes.

        Args:
            decision_id: ID da decisão (gerado automaticamente se None)
            plan_id: ID do plano associado
            final_decision: Decisão final consolidada
            consensus_score: Score de consenso (0.0 a 1.0)
            approval_rate: Taxa de aprovação (0.0 a 1.0)
            total_opinions: Total de opiniões recebidas
            approve_count: Contagem de aprovações
            reject_count: Contagem de rejeições
            domain: Domínio da decisão
            reasoning: Justificativa consolidada
            hierarchical_weights: Pesos hierárquicos dos especialistas

        Returns:
            Dict com dados do ConsolidatedDecision
        """
        return {
            "decision_id": decision_id or f"decision-{uuid4().hex[:8]}",
            "plan_id": plan_id,
            "final_decision": final_decision,
            "consensus_score": max(0.0, min(1.0, consensus_score)),
            "approval_rate": max(0.0, min(1.0, approval_rate)),
            "total_opinions": total_opinions,
            "approve_count": approve_count,
            "reject_count": reject_count,
            "domain": domain,
            "reasoning": reasoning or "Consolidated reasoning based on specialist opinions",
            "hierarchical_weights": hierarchical_weights or {
                "senior": 1.5,
                "mid_level": 1.0,
                "trainee": 0.7,
            },
            "created_at": datetime.utcnow().isoformat(),
        }


@dataclass
class TestExecutionTicketFactory:
    """Factory para criar ExecutionTicket de teste."""

    @staticmethod
    def create(
        ticket_id: Optional[str] = None,
        plan_id: str = "plan-123",
        correlation_id: Optional[str] = None,
        task_type: str = "query",
        task_data: Optional[Dict[str, Any]] = None,
        status: str = "PENDING",
        sla_deadline_ms: Optional[int] = None,
        worker_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Cria um ExecutionTicket para testes.

        Args:
            ticket_id: ID do ticket (gerado automaticamente se None)
            plan_id: ID do plano associado
            correlation_id: ID de correlação
            task_type: Tipo da tarefa (query, transform, validate, etc.)
            task_data: Dados da tarefa
            status: Status do ticket
            sla_deadline_ms: Deadline em milissegundos
            worker_id: ID do worker atribuído

        Returns:
            Dict com dados do ExecutionTicket
        """
        now_ms = int(datetime.utcnow().timestamp() * 1000)
        default_deadline = now_ms + 3_600_000  # 1 hora

        default_task_data = {
            "template_id": "test_template",
            "parameters": {"test": True},
            "target": "test_collection",
        }

        # Mesclar task_data com default
        final_task_data = {**default_task_data, **(task_data or {})}

        return {
            "ticket_id": ticket_id or f"ticket-{uuid4().hex[:8]}",
            "plan_id": plan_id,
            "correlation_id": correlation_id or f"corr-{uuid4().hex[:8]}",
            "task": {
                "type": task_type,
                **final_task_data,
            },
            "status": status,
            "sla_deadline_ms": sla_deadline_ms or default_deadline,
            "worker_id": worker_id or f"worker-{uuid4().hex[:8]}",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def create_batch(count: int = 5, plan_id: str = "plan-123") -> List[Dict[str, Any]]:
        """Cria múltiplos ExecutionTickets para testes."""
        task_types = ["query", "transform", "validate", "compute"]
        return [
            TestExecutionTicketFactory.create(
                plan_id=plan_id,
                task_type=random.choice(task_types),
            )
            for _ in range(count)
        ]


@dataclass
class TestSpecialistFeedbackFactory:
    """Factory para criar SpecialistFeedback para testes de ML."""

    @staticmethod
    def create(
        feedback_id: Optional[str] = None,
        specialist_id: str = "specialist-test",
        plan_id: str = "plan-123",
        opinion_id: str = "opinion-123",
        human_decision: bool = True,
        confidence: float = 0.8,
        domain: str = "TECHNICAL",
        intent_raw_text: Optional[str] = None,
        reasoning_factors: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Cria um SpecialistFeedback para testes.

        Args:
            feedback_id: ID do feedback (gerado automaticamente se None)
            specialist_id: ID do especialista
            plan_id: ID do plano associado
            opinion_id: ID da opinião associada
            human_decision: Decisão humana (approve/reject)
            confidence: Nível de confiança da opinião
            domain: Domínio da decisão
            intent_raw_text: Texto original da intenção
            reasoning_factors: Fatores usados na decisão

        Returns:
            Dict com dados do SpecialistFeedback
        """
        return {
            "feedback_id": feedback_id or f"feedback-{uuid4().hex[:8]}",
            "specialist_id": specialist_id,
            "plan_id": plan_id,
            "opinion_id": opinion_id,
            "human_decision": "approve" if human_decision else "reject",
            "specialist_recommendation": True,
            "specialist_confidence": max(0.0, min(1.0, confidence)),
            "domain": domain,
            "intent_raw_text": intent_raw_text or "Test intent for ML training",
            "reasoning_factors": reasoning_factors or {
                "semantic_similarity": 0.75,
                "complexity_score": 0.5,
                "risk_assessment": 0.3,
            },
            "created_at": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def create_batch(
        count: int = 10,
        approve_ratio: float = 0.7,
        domain: str = "TECHNICAL",
    ) -> List[Dict[str, Any]]:
        """
        Cria múltiplos feedbacks com balanceamento controlado.

        Args:
            count: Total de feedbacks a criar
            approve_ratio: Proporção de aprovações (0.0 a 1.0)
            domain: Domínio dos feedbacks

        Returns:
            Lista de SpecialistFeedback
        """
        feedbacks = []
        approve_count = int(count * approve_ratio)

        for i in range(count):
            is_approve = i < approve_count
            feedbacks.append(
                TestSpecialistFeedbackFactory.create(
                    human_decision=is_approve,
                    confidence=random.uniform(0.5, 1.0) if is_approve else random.uniform(0.3, 0.7),
                    domain=domain,
                )
            )

        return feedbacks


@dataclass
class TestTaskFactory:
    """Factory para criar Tasks de CognitivePlan."""

    @staticmethod
    def create(
        task_id: Optional[str] = None,
        task_type: str = "ANALYZE",
        description: str = "Test task",
        dependencies: Optional[List[str]] = None,
        estimated_duration_ms: int = 5000,
        required_capabilities: Optional[List[str]] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Cria uma Task para testes."""
        return {
            "task_id": task_id or f"task-{uuid4().hex[:8]}",
            "task_type": task_type,
            "description": description,
            "dependencies": dependencies or [],
            "estimated_duration_ms": estimated_duration_ms,
            "required_capabilities": required_capabilities or [],
            "parameters": parameters or {},
            "metadata": {
                "priority": "normal",
            },
        }

    @staticmethod
    def create_with_dependencies(
        dependency_count: int = 2,
    ) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Cria uma task com tarefas dependentes.

        Returns:
            Tupla (task_principal, lista_dependencias)
        """
        dependencies = [
            TestTaskFactory.create(
                task_type="ANALYZE",
                description=f"Dependency task {i}",
            )
            for i in range(dependency_count)
        ]

        main_task = TestTaskFactory.create(
            task_type="BUILD",
            description="Main task with dependencies",
            dependencies=[t["task_id"] for t in dependencies],
        )

        return main_task, dependencies


# Convenience functions
def create_test_plan(
    intent: str = "Test intent",
    domain: str = "TECHNICAL",
) -> Dict[str, Any]:
    """Função de conveniência para criar um plano de teste simples."""
    return TestCognitivePlanFactory.create(intent=intent, domain=domain)


def create_test_opinion(
    plan_id: str = "plan-123",
    confidence: float = 0.8,
) -> Dict[str, Any]:
    """Função de conveniência para criar uma opinião de teste simples."""
    return TestSpecialistOpinionFactory.create(
        plan_id=plan_id,
        confidence=confidence,
    )


def create_test_decision(
    plan_id: str = "plan-123",
    final_decision: bool = True,
) -> Dict[str, Any]:
    """Função de conveniência para criar uma decisão consolidada de teste."""
    return TestConsolidatedDecisionFactory.create(
        plan_id=plan_id,
        final_decision=final_decision,
    )


def create_test_ticket(
    plan_id: str = "plan-123",
    task_type: str = "query",
) -> Dict[str, Any]:
    """Função de conveniência para criar um ticket de execução de teste."""
    return TestExecutionTicketFactory.create(
        plan_id=plan_id,
        task_type=task_type,
    )


def create_test_feedback(
    human_decision: bool = True,
    confidence: float = 0.8,
) -> Dict[str, Any]:
    """Função de conveniência para criar um feedback de teste."""
    return TestSpecialistFeedbackFactory.create(
        human_decision=human_decision,
        confidence=confidence,
    )
