import pytest
import subprocess
import json


@pytest.fixture(scope="module")
def k8s_core():
    from kubernetes import client, config
    config.load_kube_config()
    return client.CoreV1Api()


@pytest.fixture(scope="module")
def k8s_apps():
    from kubernetes import client, config
    config.load_kube_config()
    return client.AppsV1Api()


class TestIstio:
    def test_istiod_running(self, k8s_apps):
        deployments = k8s_apps.list_namespaced_deployment("istio-system")
        istiod = [d for d in deployments.items if "istiod" in d.metadata.name]
        assert len(istiod) > 0
        assert istiod[0].status.ready_replicas >= 1

    def test_ingress_gateway_exists(self, k8s_core):
        services = k8s_core.list_namespaced_service("istio-system")
        gateway = [s for s in services.items if "ingressgateway" in s.metadata.name.lower()]
        assert len(gateway) > 0

    def test_neural_hive_namespace_injected(self, k8s_core):
        pods = k8s_core.list_namespaced_pod("neural-hive")
        running_pods = [p for p in pods.items if p.status.phase == "Running"]
        injected_pods = 0
        for pod in running_pods:
            containers = [c.name for c in pod.spec.containers]
            if "istio-proxy" in containers:
                injected_pods += 1
        # Verifica que pelo menos 80% dos pods estão com sidecar
        injection_rate = injected_pods / len(running_pods) if running_pods else 0
        assert injection_rate >= 0.8, f"Sidecar injection rate: {injection_rate:.2%}"


class TestGatekeeper:
    def test_gatekeeper_running(self, k8s_apps):
        deployments = k8s_apps.list_namespaced_deployment("gatekeeper-system")
        controller = [d for d in deployments.items if "controller-manager" in d.metadata.name]
        assert len(controller) > 0
        assert controller[0].status.ready_replicas >= 1

    def test_constraint_templates_exist(self):
        result = subprocess.run(
            ["kubectl", "get", "constrainttemplates"],
            capture_output=True, text=True
        )
        assert "k8srequiredlabels" in result.stdout
        assert "k8sdisallowanonymous" in result.stdout
        assert "k8scontainerlimits" in result.stdout


class TestRedisCluster:
    def test_redis_cluster_pods_running(self, k8s_core):
        pods = k8s_core.list_namespaced_pod("redis-cluster")
        redis_pods = [p for p in pods.items if "redis" in p.metadata.name.lower() and p.status.phase == "Running"]
        assert len(redis_pods) >= 6

    def test_redis_cluster_healthy(self):
        result = subprocess.run(
            ["kubectl", "exec", "-n", "redis-cluster", "redis-cluster-0", "--",
             "redis-cli", "-c", "cluster", "info"],
            capture_output=True, text=True
        )
        assert "cluster_state:ok" in result.stdout


class TestIntegration:
    def test_cluster_health_overall(self):
        nodes = subprocess.run(
            ["kubectl", "get", "nodes", "--no-headers"],
            capture_output=True, text=True
        )
        assert nodes.returncode == 0
        node_lines = [line for line in nodes.stdout.split('\n') if 'Ready' in line]
        assert len(node_lines) >= 5

    def test_critical_namespaces_exist(self):
        result = subprocess.run(
            ["kubectl", "get", "namespaces", "-o", "jsonpath='{.items[*].metadata.name}'"],
            capture_output=True, text=True
        )
        assert "istio-system" in result.stdout
        assert "gatekeeper-system" in result.stdout
        assert "redis-cluster" in result.stdout