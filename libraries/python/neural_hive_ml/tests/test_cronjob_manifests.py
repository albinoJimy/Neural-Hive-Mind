"""Testes para manifests Kubernetes CronJob."""

import os
import yaml
from pathlib import Path
import pytest


CRONJOB_DIR = Path(__file__).parent.parent / "k8s"


class TestCronJobManifests:
    """Testes para arquivos de manifesto YAML."""

    def test_daily_cronjob_file_exists(self):
        """Verifica que arquivo do CronJob diário existe."""
        path = CRONJOB_DIR / "ml-retraining-cronjob.yaml"
        assert path.exists(), "Arquivo ml-retraining-cronjob.yaml não encontrado"
        assert path.is_file(), "Caminho não é um arquivo"

    def test_weekly_cronjob_file_exists(self):
        """Verifica que arquivo do CronJob semanal existe."""
        path = CRONJOB_DIR / "ml-retraining-weekly-cronjob.yaml"
        assert path.exists(), "Arquivo ml-retraining-weekly-cronjob.yaml não encontrado"

    def test_daily_cronjob_valid_yaml(self):
        """Verifica que YAML diário é válido."""
        path = CRONJOB_DIR / "ml-retraining-cronjob.yaml"
        with open(path) as f:
            data = yaml.safe_load_all(f)
            # Verifica que pelo menos um documento foi parseado
            docs = list(data)
            assert len(docs) > 0, "Nenhum documento YAML encontrado"

    def test_weekly_cronjob_valid_yaml(self):
        """Verifica que YAML semanal é válido."""
        path = CRONJOB_DIR / "ml-retraining-weekly-cronjob.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
            assert data is not None

    def test_daily_cronjob_required_fields(self):
        """Verifica campos obrigatórios no CronJob diário."""
        path = CRONJOB_DIR / "ml-retraining-cronjob.yaml"
        with open(path) as f:
            docs = list(yaml.safe_load_all(f))
            cronjob = next((d for d in docs if d.get("kind") == "CronJob"), None)

        assert cronjob is not None, "CronJob não encontrado no manifesto"
        assert cronjob["apiVersion"] == "batch/v1"
        assert cronjob["kind"] == "CronJob"
        assert "metadata" in cronjob
        assert "spec" in cronjob
        assert "schedule" in cronjob["spec"]
        assert "jobTemplate" in cronjob["spec"]

    def test_weekly_cronjob_required_fields(self):
        """Verifica campos obrigatórios no CronJob semanal."""
        path = CRONJOB_DIR / "ml-retraining-weekly-cronjob.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)

        assert data["apiVersion"] == "batch/v1"
        assert data["kind"] == "CronJob"
        assert data["spec"]["schedule"] == "0 3 * * 0"  # Domingo 3h

    def test_daily_schedule(self):
        """Verifica agendamento diário correto."""
        path = CRONJOB_DIR / "ml-retraining-cronjob.yaml"
        with open(path) as f:
            docs = list(yaml.safe_load_all(f))
            cronjob = next((d for d in docs if d.get("kind") == "CronJob"), None)

        assert cronjob["spec"]["schedule"] == "0 2 * * *"  # Diário 2h

    def test_concurrency_policy(self):
        """Verifica política de concorrência configurada."""
        path = CRONJOB_DIR / "ml-retraining-cronjob.yaml"
        with open(path) as f:
            docs = list(yaml.safe_load_all(f))
            cronjob = next((d for d in docs if d.get("kind") == "CronJob"), None)

        assert cronjob["spec"]["concurrencyPolicy"] in ["Forbid", "Replace"]

    def test_resource_limits(self):
        """Verifica que recursos estão configurados."""
        path = CRONJOB_DIR / "ml-retraining-cronjob.yaml"
        with open(path) as f:
            docs = list(yaml.safe_load_all(f))
            cronjob = next((d for d in docs if d.get("kind") == "CronJob"), None)

        container = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
        assert "resources" in container
        assert "requests" in container["resources"]
        assert "limits" in container["resources"]

    def test_environment_variables(self):
        """Verifica variáveis de ambiente configuradas."""
        path = CRONJOB_DIR / "ml-retraining-cronjob.yaml"
        with open(path) as f:
            docs = list(yaml.safe_load_all(f))
            cronjob = next((d for d in docs if d.get("kind") == "CronJob"), None)

        envs = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["env"]
        env_names = [e["name"] for e in envs]

        assert "MONGODB_URL" in env_names
        assert "KAFKA_BOOTSTRAP_SERVERS" in env_names
        assert "MLFLOW_TRACKING_URI" in env_names

    def test_secret_refs_configured(self):
        """Verifica referências a secrets configuradas."""
        path = CRONJOB_DIR / "ml-retraining-cronjob.yaml"
        with open(path) as f:
            docs = list(yaml.safe_load_all(f))
            cronjob = next((d for d in docs if d.get("kind") == "CronJob"), None)

        envs = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["env"]
        mongodb_url = next((e for e in envs if e["name"] == "MONGODB_URL"), None)

        assert mongodb_url is not None
        assert "valueFrom" in mongodb_url
        assert "secretKeyRef" in mongodb_url["valueFrom"]

    def test_rbac_resources(self):
        """Verifica recursos RBAC configurados."""
        path = CRONJOB_DIR / "ml-retraining-cronjob.yaml"
        with open(path) as f:
            docs = list(yaml.safe_load_all(f))

        service_account = next((d for d in docs if d.get("kind") == "ServiceAccount"), None)
        role = next((d for d in docs if d.get("kind") == "Role"), None)
        role_binding = next((d for d in docs if d.get("kind") == "RoleBinding"), None)

        assert service_account is not None, "ServiceAccount não encontrado"
        assert role is not None, "Role não encontrado"
        assert role_binding is not None, "RoleBinding não encontrado"

    def test_priority_class(self):
        """Verifica PriorityClass configurada."""
        path = CRONJOB_DIR / "ml-retraining-cronjob.yaml"
        with open(path) as f:
            docs = list(yaml.safe_load_all(f))
            priority_class = next((d for d in docs if d.get("kind") == "PriorityClass"), None)

        assert priority_class is not None
        assert priority_class["metadata"]["name"] == "low-priority"
        assert priority_class["value"] < 10000  # Baixa prioridade

    def test_restart_policy(self):
        """Verifica política de restart configurada."""
        path = CRONJOB_DIR / "ml-retraining-cronjob.yaml"
        with open(path) as f:
            docs = list(yaml.safe_load_all(f))
            cronjob = next((d for d in docs if d.get("kind") == "CronJob"), None)

        restart_policy = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]["restartPolicy"]
        assert restart_policy in ["OnFailure", "Never"]

    def test_active_deadline(self):
        """Verifica deadline ativo configurado."""
        path = CRONJOB_DIR / "ml-retraining-cronjob.yaml"
        with open(path) as f:
            docs = list(yaml.safe_load_all(f))
            cronjob = next((d for d in docs if d.get("kind") == "CronJob"), None)

        deadline = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"].get(
            "activeDeadlineSeconds"
        )
        assert deadline is not None
        assert deadline > 0
        assert deadline <= 10800  # Max 3 horas


class TestCronJobManagerScript:
    """Testes para script de gerenciamento."""

    def test_manager_script_exists(self):
        """Verifica que script de gerenciamento existe."""
        path = CRONJOB_DIR / "manage_cronjobs.sh"
        assert path.exists(), "Script manage_cronjobs.sh não encontrado"
        assert path.is_file()

    def test_manager_script_executable(self):
        """Verifica que script tem permissão de execução."""
        path = CRONJOB_DIR / "manage_cronjobs.sh"
        assert os.access(path, os.X_OK), "Script não tem permissão de execução"

    def test_manager_script_has_functions(self):
        """Verifica que script tem funções principais."""
        path = CRONJOB_DIR / "manage_cronjobs.sh"
        with open(path) as f:
            content = f.read()

        required_functions = [
            "apply",
            "delete",
            "list",
            "status",
            "trigger",
            "suspend",
            "resume",
            "logs",
            "validate",
        ]
        for func in required_functions:
            assert func in content, f"Função '{func}' não encontrada no script"


class TestCronJobLabels:
    """Testes para labels e seletores."""

    def test_consistent_labels(self):
        """Verifica labels consistentes across recursos."""
        path = CRONJOB_DIR / "ml-retraining-cronjob.yaml"
        with open(path) as f:
            docs = list(yaml.safe_load_all(f))

        for doc in docs:
            if doc.get("kind") in ["CronJob", "ServiceAccount", "Role", "RoleBinding"]:
                labels = doc.get("metadata", {}).get("labels", {})
                assert "app" in labels or doc["kind"] == "Role"

    def test_selector_labels(self):
        """Verifica que jobs podem ser selecionados."""
        path = CRONJOB_DIR / "ml-retraining-cronjob.yaml"
        with open(path) as f:
            docs = list(yaml.safe_load_all(f))
            cronjob = next((d for d in docs if d.get("kind") == "CronJob"), None)

        job_labels = cronjob["spec"]["jobTemplate"]["metadata"]["labels"]
        assert "app" in job_labels
        assert job_labels["app"] == "ml-retraining"
