import pytest
from kubernetes import client, config


@pytest.fixture(scope="module")
def k8s_api():
    config.load_kube_config()
    return client.CoreV1Api()


@pytest.fixture(scope="module")
def apps_api():
    config.load_kube_config()
    return client.AppsV1Api()


def test_istio_namespace_exists(k8s_api):
    """Verify istio-system namespace exists"""
    namespaces = [ns.metadata.name for ns in k8s_api.list_namespace().items]
    assert "istio-system" in namespaces


def test_istiod_deployment_ready(apps_api):
    """Verify istiod deployment has 2 replicas ready"""
    deployments = apps_api.list_namespaced_deployment("istio-system")
    istiod = [d for d in deployments.items if d.metadata.name.startswith("istiod")]
    assert len(istiod) > 0, "istiod deployment not found"

    for deployment in istiod:
        assert deployment.spec.replicas == 2
        assert deployment.status.ready_replicas == 2


def test_ingress_gateway_service_exists(k8s_api):
    """Verify ingress gateway service exists"""
    services = k8s_api.list_namespaced_service("istio-system")
    gateway = [s for s in services.items if "ingressgateway" in s.metadata.name.lower()]
    assert len(gateway) > 0, "ingress gateway service not found"


def test_webhook_configurations_exist(k8s_api):
    """Validate webhook configurations are registered"""
    apiextensions = client.ApiextensionsV1Api()
    mutating = [webhook.metadata.name for webhook in
                 k8s_api.list_mutating_webhook_configuration().items]
    validating = [webhook.metadata.name for webhook in
                  k8s_api.list_validating_webhook_configuration().items]

    assert any("istiod" in name for name in validating)