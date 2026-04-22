"""
Locust load test file para Fluxo G Pipeline.

Uso:
    locust -f tests/load/locustfile.py --host http://localhost:8003
    locust -f tests/load/locustfile.py --headless --users 100 --spawn-rate 10 --run-time 5m
"""

import random
import time

from locust import HttpUser, between, events, task


class FluxoGUser(HttpUser):
    """
    Simula usuário interagindo com o Fluxo G Pipeline.

    Tasks:
    - start_pipeline: Inicia novo pipeline Fluxo G (weight 3 - mais frequente)
    - check_pipeline_status: Verifica status de pipeline existente (weight 2)
    - list_pipelines: Lista todos os pipelines (weight 1)
    - health_check: Health check do serviço (weight 1)
    """

    wait_time = between(1, 3)
    host = "http://localhost:8003"

    def on_start(self):
        """Setup inicial de cada usuário."""
        self.pipeline_id = None
        self.user_id = f"load-test-user-{random.randint(1000, 9999)}"
        self.project_names = [
            "api-usuarios",
            "sistema-auth",
            "microservico-pagamentos",
            "dashboard-admin",
            "fila-processamento",
            "servico-notificacoes",
            "cache-distribuido",
            "api-produtos",
            "sistema-email",
            "api-analytics",
            "servico-arquivos",
            "portal-clientes",
        ]
        self.intents = [
            "Criar uma API REST de usuários com CRUD completo",
            "Implementar sistema de autenticação JWT com refresh tokens",
            "Criar microserviço de pagamentos com integração Stripe",
            "Desenvolver dashboard administrativo com gráficos",
            "Implementar fila de processamento assíncrono com RabbitMQ",
            "Criar serviço de notificações via email e SMS",
            "Implementar cache distribuído com Redis",
            "Criar API de produtos com busca e filtros avançados",
            "Desenvolver sistema de comentários com threading",
            "Implementar webhook receiver para eventos externos",
            "Criar serviço de upload de arquivos com S3",
            "Desenvolver portal de clientes com histórico",
        ]

    @task(3)
    def start_pipeline(self):
        """
        Inicia um novo pipeline Fluxo G.

        Esta é a tarefa mais frequente (weight 3).
        """
        intent_text = random.choice(self.intents)
        project_name = random.choice(self.project_names)
        unique_suffix = random.randint(1000, 9999)

        response = self.client.post(
            "/api/v1/workflows",
            json={
                "workflow_name": "fluxo_g",
                "input_data": {
                    "cognitive_plan": {
                        "plan_id": f"PLAN-{unique_suffix}",
                        "intent_id": f"INTENT-{unique_suffix}",
                        "summary": intent_text[:50] + "...",
                        "description": intent_text,
                        "tasks": [
                            {"task_id": f"T{i}", "description": f"Task {i}"} for i in range(1, 4)
                        ],
                    },
                    "original_intent": intent_text,
                    "skip_approvals": True,  # Mais rápido para load test
                },
            },
            name="/api/v1/workflows (POST Fluxo G)",
            timeout=30,
        )

        if response.status_code == 200 or response.status_code == 202:
            data = response.json()
            self.pipeline_id = data.get("workflow_id") or data.get("run_id")
            if hasattr(self.environment, "pipelines_started"):
                self.environment.pipelines_started += 1
            else:
                self.environment.pipelines_started = 1
        elif hasattr(self.environment, "pipeline_errors"):
            self.environment.pipeline_errors += 1
        else:
            self.environment.pipeline_errors = 1

    @task(2)
    def check_pipeline_status(self):
        """
        Verifica status de pipeline existente.

        Weight 2 - segunda tarefa mais frequente.
        """
        if not self.pipeline_id:
            return

        response = self.client.get(
            f"/api/v1/workflows/{self.pipeline_id}",
            name="/api/v1/workflows/:id (GET)",
            timeout=10,
        )

        if response.status_code == 200:
            data = response.json()
            status = data.get("status", "").lower()

            # Reset pipeline_id se finalizado
            if status in ["completed", "failed", "canceled", "terminated"]:
                if status == "completed" and hasattr(self.environment, "pipelines_completed"):
                    self.environment.pipelines_completed += 1
                elif status == "failed" and hasattr(self.environment, "pipelines_failed"):
                    self.environment.pipelines_failed += 1
                self.pipeline_id = None

    @task(1)
    def list_pipelines(self):
        """
        Lista pipelines.

        Weight 1 - tarefa menos frequente.
        """
        self.client.get(
            "/api/v1/workflows?page=1&page_size=20",
            name="/api/v1/workflows (GET list)",
            timeout=10,
        )

    @task(1)
    def health_check(self):
        """
        Health check do serviço.

        Weight 1 - tarefa menos frequente.
        """
        self.client.get(
            "/health/ready",
            name="/health/ready (GET)",
            timeout=5,
        )


class FluxoGUserWithApproval(FluxoGUser):
    """
    Usuário que testa pipelines com aprovação.

    Usa Approval Gateway, simulando casos mais complexos.
    """

    @task
    def start_complex_pipeline(self):
        """Inicia pipeline complexo que requer aprovação."""
        intent_text = (
            "Criar sistema completo de e-commerce com catálogo, " "carrinho, checkout e pagamentos"
        )
        unique_suffix = random.randint(100, 999)

        response = self.client.post(
            "/api/v1/workflows",
            json={
                "workflow_name": "fluxo_g",
                "input_data": {
                    "cognitive_plan": {
                        "plan_id": f"ECOM-{unique_suffix}",
                        "intent_id": f"INTENT-{unique_suffix}",
                        "summary": "E-commerce completo",
                        "description": intent_text,
                        "complexity": "high",
                    },
                    "original_intent": intent_text,
                    "skip_approvals": False,  # Requer aprovação
                    "consolidated_decision": {
                        "decision_id": f"DEC-{unique_suffix}",
                        "status": "approved",
                    },
                },
            },
            name="/api/v1/workflows (POST Fluxo G with approval)",
            timeout=60,
        )

        if response.status_code == 200 or response.status_code == 202:
            self.pipeline_id = response.json().get("workflow_id")


# Event handlers para métricas e reporting


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Inicializa contadores no início do teste."""
    environment.pipelines_started = 0
    environment.pipelines_completed = 0
    environment.pipelines_failed = 0
    environment.pipeline_errors = 0
    environment.start_time = time.time()

    environment.events.request.fire(
        request_type="INFO",
        name="test_start",
        response_time=0,
        response_length=0,
        context={"message": "Fluxo G Load Test Started"},
    )


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Reporta métricas finais."""
    duration = time.time() - environment.start_time
    total_requests = environment.pipelines_started or 0
    completed = environment.pipelines_completed or 0
    failed = environment.pipelines_failed or 0
    errors = environment.pipeline_errors or 0

    success_rate = (completed / max(total_requests, 1)) * 100
    throughput = total_requests / duration if duration > 0 else 0

    print("\n" + "=" * 70)
    print(" FLUXO G LOAD TEST RESULTS")
    print("=" * 70)
    print(f" Duration:            {duration:.2f} seconds ({duration/60:.1f} minutes)")
    print(f" Pipelines Started:   {total_requests}")
    print(f" Pipelines Completed: {completed}")
    print(f" Pipelines Failed:    {failed}")
    print(f" Request Errors:      {errors}")
    print(f" Success Rate:        {success_rate:.2f}%")
    print(f" Throughput:          {throughput:.2f} pipelines/second")
    print("=" * 70 + "\n")

    # Enviar métricas como eventos do Locust
    environment.events.request.fire(
        request_type="SUMMARY",
        name="test_complete",
        response_time=duration * 1000,  # em ms
        response_length=0,
        context={
            "duration_seconds": duration,
            "pipelines_started": total_requests,
            "pipelines_completed": completed,
            "pipelines_failed": failed,
            "success_rate": success_rate,
            "throughput_per_second": throughput,
        },
    )


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """
    Log de requisições lentas e falhas.

    Marca requisições que levam mais de 5 segundos.
    """
    if exception:
        print(f"ERROR: {name} - {exception}")

    # Alertar sobre requisições lentas (mais de 5 segundos)
    if response_time > 5000:
        print(f"SLOW REQUEST: {name} took {response_time}ms")

    # Alertar sobre requisições muito lentas (mais de 30 segundos)
    if response_time > 30000:
        print(f"VERY SLOW REQUEST: {name} took {response_time}ms - potential bottleneck!")


@events.spawning_complete.add_listener
def on_spawning_complete(user_count, **kwargs):
    """Log quando todos os usuários foram spawnados."""
    print(f"Spawning complete: {user_count} users ready")


@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    """Log quando Locust está quitting."""
    duration = time.time() - environment.start_time if hasattr(environment, "start_time") else 0
    print(f"Quitting after {duration:.1f} seconds")
